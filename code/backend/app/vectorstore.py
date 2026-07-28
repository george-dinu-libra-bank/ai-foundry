"""Qdrant wrapper — collection lifecycle, upsert, similarity search.

The collection is created lazily with the dimension of the first embedding that
arrives. If a later embedding model produces a different dimension, we refuse
loudly: vectors from different models live in different spaces and comparing
them is meaningless — reset the collection and re-ingest instead.

Assignment 3 changes, all driven by a failure seen against `data/`:

  ingestion
    * point ids are derived from `source` + chunk index instead of a fresh UUID,
      so re-ingesting a document replaces it rather than duplicating it;
    * the payload carries the document's real metadata (title, effective date,
      version, status), because nothing can be filtered by what was never stored.

  retrieval
    * `min_score` drops weak hits so "nothing relevant" is a possible answer;
    * `filters` restricts by payload — chiefly `status: current`, which stops the
      2025 fee schedule from competing with the 2026 one;
    * `query_text` adds a full-text arm and fuses it with the vector arm (RRF),
      because exact tokens — "300 lei", "0800 800 210" — are what vectors miss;
    * `dedup` collapses near-identical chunks so three ways of saying the same
      thing do not crowd out the second fact.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from qdrant_client import QdrantClient, models

from .config import settings

# Stable ids need a fixed namespace: the same source + index must map to the same
# UUID on every run, in every process, forever.
POINT_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

# Payload keys the loader may set. Anything outside this list is still stored,
# but these are the ones we index and filter on.
INDEXED_FIELDS = ("source", "product", "audience", "status", "title", "effective")

WORD = re.compile(r"\w+", re.UNICODE)


class DimensionMismatch(Exception):
    def __init__(self, existing: int, incoming: int) -> None:
        self.existing = existing
        self.incoming = incoming
        super().__init__(
            f"Collection stores {existing}-dimensional vectors but the current embedding "
            f"model produces {incoming} dimensions. Vectors from different embedding models "
            f"are not comparable — DELETE /collection and re-ingest."
        )


def point_id(source: str, index: int) -> str:
    """Deterministic id for one chunk of one document.

    This is improvement #1 from part 4 of the assignment. With `uuid4()` every
    re-ingest wrote a new point and the collection grew without bound: ingesting
    the 20-document corpus three times gave 3x the chunks and retrieval returned
    the same text three times. With `uuid5()` the second ingest overwrites the
    first, and the collection is a function of `data/`, not of how many times the
    loader was run.
    """
    return str(uuid.uuid5(POINT_NAMESPACE, f"{source}#{index}"))


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in WORD.findall(text)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _build_filter(filters: dict | None) -> models.Filter | None:
    """Turn {"status": "current", "product": ["cards", "accounts"]} into a Qdrant
    filter. A list becomes MatchAny; a scalar becomes MatchValue."""
    if not filters:
        return None
    must: list[models.FieldCondition] = []
    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            values = [v for v in value if v is not None]
            if not values:
                continue
            must.append(models.FieldCondition(key=key, match=models.MatchAny(any=list(values))))
        else:
            must.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
    return models.Filter(must=must) if must else None


class VectorStore:
    def __init__(self) -> None:
        self.client = QdrantClient(url=settings.qdrant_url, timeout=10)
        self.collection = settings.qdrant_collection
        # document frequency per term, for the selectivity test in _selective_terms.
        # Cleared on every ingest, since the denominator moves.
        self._df_cache: dict[str, int] = {}

    # --- lifecycle -----------------------------------------------------------
    def ensure_collection(self, dim: int) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
            )
            self.ensure_indexes()
            return
        existing = self._vector_size()
        if existing != dim:
            raise DimensionMismatch(existing, dim)

    def ensure_indexes(self) -> None:
        """Payload indexes: keyword indexes for the filter fields, and a full-text
        index on `text` so the keyword arm of hybrid search can run in Qdrant
        rather than in Python. Creating an index that already exists is a no-op
        we swallow, so this is safe to call on every ingest."""
        for field in INDEXED_FIELDS:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception:                     # noqa: BLE001 — already indexed
                pass
        try:
            self.client.create_payload_index(
                collection_name=self.collection,
                field_name="text",
                field_schema=models.TextIndexParams(
                    type=models.TextIndexType.TEXT,
                    tokenizer=models.TokenizerType.WORD,
                    min_token_len=2,
                    max_token_len=25,
                    lowercase=True,
                ),
            )
        except Exception:                         # noqa: BLE001 — already indexed
            pass

    def reset(self) -> bool:
        self._df_cache.clear()
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
            return True
        return False

    # --- data ----------------------------------------------------------------
    def upsert(self, chunks: list[str], vectors: list[list[float]], strategy: str,
               source: str | None, metadata: dict | None = None) -> list[str]:
        src = source or "adhoc"
        self._df_cache.clear()      # the collection changed; so did every frequency
        ids = [point_id(src, i) for i in range(len(chunks))]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        base = {k: v for k, v in (metadata or {}).items() if v is not None}
        self.client.upsert(
            collection_name=self.collection,
            points=[
                models.PointStruct(
                    id=pid,
                    vector=vec,
                    payload={
                        **base,
                        "text": text,
                        "index": i,
                        "strategy": strategy,
                        "source": src,
                        "ingested_at": now,
                    },
                )
                for i, (pid, text, vec) in enumerate(zip(ids, chunks, vectors))
            ],
        )
        return ids

    def prune_source(self, source: str, keep_from: int) -> int:
        """Delete leftover chunks of `source` with an index >= `keep_from`.

        Stable ids make re-ingest idempotent only while the chunk count is stable.
        Edit a document down from 9 chunks to 6 and chunks 6-8 of the previous
        version survive with stale text. This removes them.
        """
        flt = models.Filter(
            must=[
                models.FieldCondition(key="source", match=models.MatchValue(value=source)),
                models.FieldCondition(key="index", range=models.Range(gte=keep_from)),
            ]
        )
        before = self.count(source)
        self.client.delete(collection_name=self.collection,
                           points_selector=models.FilterSelector(filter=flt))
        return max(0, before - self.count(source))

    def delete_by_source(self, source: str) -> int:
        removed = self.count(source)
        self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(filter=models.Filter(
                must=[models.FieldCondition(key="source", match=models.MatchValue(value=source))]
            )),
        )
        return removed

    def count(self, source: str | None = None) -> int:
        if not self.client.collection_exists(self.collection):
            return 0
        flt = None if source is None else models.Filter(
            must=[models.FieldCondition(key="source", match=models.MatchValue(value=source))]
        )
        return self.client.count(collection_name=self.collection,
                                 count_filter=flt, exact=True).count

    def sources(self) -> list[dict]:
        """Every distinct source in the collection, with its chunk count and the
        document metadata carried by its first chunk."""
        if not self.client.collection_exists(self.collection):
            return []
        seen: dict[str, dict] = {}
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection, limit=256,
                offset=offset, with_payload=True, with_vectors=False,
            )
            for p in points:
                pl = p.payload or {}
                src = pl.get("source", "adhoc")
                entry = seen.setdefault(src, {
                    "source": src, "chunks": 0, "title": pl.get("title"),
                    "product": pl.get("product"), "status": pl.get("status"),
                    "effective": pl.get("effective"), "version": pl.get("version"),
                })
                entry["chunks"] += 1
                if pl.get("index") == 0 and pl.get("title"):
                    entry["title"] = pl.get("title")
            if offset is None:
                break
        return sorted(seen.values(), key=lambda e: e["source"])

    # --- retrieval -----------------------------------------------------------
    def search(self, vector: list[float], top_k: int, *,
               min_score: float | None = None,
               relative_floor: float = 0.70,
               filters: dict | None = None,
               query_text: str | None = None,
               dedup: bool = False,
               dedup_threshold: float = 0.85) -> list[dict]:
        """Vector search, optionally hybridised, filtered, thresholded and deduped.

        Order matters and is deliberate: filter in the database, fuse the two
        arms, apply the floor, collapse duplicates, then cut to `top_k`. Doing the
        threshold before fusion would judge RRF ranks against a cosine floor,
        which are not the same units.

        **`min_score` gates the best hit, it does not filter every hit.** The first
        version dropped every chunk below the floor individually, which conflates
        two different questions: "is this query answerable from the corpus at all?"
        and "is this particular chunk worth putting in the prompt?". Measured on the
        probe set, a floor high enough to refuse *student loans* (best hit 0.4425)
        also cut the correct ATM-limit table (0.4918) out of an answerable query,
        and recall fell. So the floor now decides only whether the query is
        answerable; once it is, the tail is trimmed relative to the best hit.
        """
        qfilter = _build_filter(filters)
        # over-fetch: the threshold, dedup and fusion all discard, and cutting to
        # top_k before they run would leave fewer than top_k good hits
        fetch = top_k if not (dedup or query_text) else max(top_k * 3, top_k + 5)

        dense = self.client.query_points(
            collection_name=self.collection, query=vector, limit=fetch,
            query_filter=qfilter, with_payload=True,
        ).points
        results = {str(h.id): self._to_hit(h) for h in dense}
        ranks: dict[str, dict[str, int]] = {
            str(h.id): {"dense": i} for i, h in enumerate(dense)
        }

        if query_text:
            for lex_rank, hit in enumerate(self._lexical(query_text, fetch, qfilter)):
                results.setdefault(hit["id"], hit)
                ranks.setdefault(hit["id"], {})["lexical"] = lex_rank

        if query_text:
            ordered = sorted(results.values(), key=lambda h: -_rrf(ranks[h["id"]]))
            for h in ordered:
                h["rrf"] = round(_rrf(ranks[h["id"]]), 5)
                h["matched"] = sorted(ranks[h["id"]].keys())
        else:
            ordered = sorted(results.values(), key=lambda h: -h["score"])

        if min_score is not None and ordered:
            best = max(h["score"] for h in ordered)
            if best < min_score:
                return []                     # nothing here answers this question
            floor = best * relative_floor
            # a hit found only by the keyword arm has no meaningful cosine score to
            # compare, so it survives on the strength of the exact match instead
            ordered = [h for h in ordered
                       if h["score"] >= floor or "lexical" in ranks.get(h["id"], {})]

        if dedup:
            ordered = self._dedup(ordered, dedup_threshold)

        return ordered[:top_k]

    def _selective_terms(self, query_text: str, max_df_ratio: float = 0.10) -> list[str]:
        """Keep only query terms that are actually rare *in this corpus*.

        `_rare_terms` decides a token is interesting from its shape. That is not
        enough: "PIN" and "ATM" are capitalised acronyms, so they look like codes,
        but they appear in 22% and 19% of the chunks respectively. Matching on them
        returned half of `pin-management` for any PIN question and pushed the
        chunk that held the actual number out of the top 4 — measured, twice.

        So shape proposes and the collection disposes: a term survives only if it
        appears in under `max_df_ratio` of the points. On this corpus that draws a
        clean line — 120 (1%), 0800 (4%), 22.9 (1%), IBAN (2%) on one side; PIN
        (22%), ATM (19%), 2026 (16%), fee (28%) on the other. It is document
        frequency doing what document frequency has always done.
        """
        terms = _rare_terms(query_text)
        if not terms:
            return []
        total = self.count()
        if not total:
            return []
        ceiling = max(1, int(total * max_df_ratio))
        keep: list[str] = []
        for term in terms:
            cached = self._df_cache.get(term)
            if cached is None:
                try:
                    cached = self.client.count(
                        collection_name=self.collection, exact=True,
                        count_filter=models.Filter(must=[models.FieldCondition(
                            key="text", match=models.MatchText(text=term))]),
                    ).count
                except Exception:                 # noqa: BLE001 — no text index yet
                    return []
                self._df_cache[term] = cached
            if 0 < cached <= ceiling:
                keep.append(term)
        return keep

    def _lexical(self, query_text: str, limit: int,
                 qfilter: models.Filter | None) -> list[dict]:
        """The keyword arm: Qdrant's full-text index, asked for the selective tokens
        in the query. `should` means "any of these", so a chunk containing "120" or
        "0800" ranks even when the embedding puts it nowhere near the top."""
        terms = self._selective_terms(query_text)
        if not terms:
            return []
        should = [models.FieldCondition(key="text", match=models.MatchText(text=t))
                  for t in terms]
        must = list(qfilter.must) if qfilter and qfilter.must else []
        try:
            # `should` on its own already means "at least one of these matches"
            points, _ = self.client.scroll(
                collection_name=self.collection, limit=limit, with_payload=True,
                scroll_filter=models.Filter(must=must, should=should),
            )
        except Exception:                         # noqa: BLE001 — no text index yet
            return []
        hits = [self._to_hit(p, score=0.0) for p in points]
        # scroll has no relevance order, so rank by how many query terms matched
        hits.sort(key=lambda h: -sum(t in h["text"].lower() for t in terms))
        return hits

    def _dedup(self, hits: list[dict], threshold: float) -> list[dict]:
        kept: list[dict] = []
        kept_tokens: list[set[str]] = []
        for h in hits:
            toks = _tokens(h["text"])
            if any(_jaccard(toks, k) >= threshold for k in kept_tokens):
                continue
            kept.append(h)
            kept_tokens.append(toks)
        return kept

    @staticmethod
    def _to_hit(point, score: float | None = None) -> dict:
        payload = point.payload or {}
        raw = getattr(point, "score", None) if score is None else score
        return {
            "id": str(point.id),
            "score": round(float(raw or 0.0), 4),
            "text": payload.get("text", ""),
            "index": payload.get("index"),
            "strategy": payload.get("strategy"),
            "source": payload.get("source"),
            "title": payload.get("title"),
            "product": payload.get("product"),
            "audience": payload.get("audience"),
            "effective": payload.get("effective"),
            "version": payload.get("version"),
            "status": payload.get("status"),
        }

    # --- introspection --------------------------------------------------------
    def info(self) -> dict:
        if not self.client.collection_exists(self.collection):
            return {"exists": False, "name": self.collection, "points_count": 0,
                    "vector_dimension": None, "distance": None}
        c = self.client.get_collection(self.collection)
        return {
            "exists": True,
            "name": self.collection,
            "points_count": c.points_count or 0,
            "vector_dimension": self._vector_size(),
            "distance": "cosine",
        }

    def ping(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False

    def _vector_size(self) -> int:
        cfg = self.client.get_collection(self.collection).config.params.vectors
        return cfg.size if hasattr(cfg, "size") else next(iter(cfg.values())).size


# --- hybrid helpers -----------------------------------------------------------

# Words too common to discriminate. Kept short on purpose: the goal is to find the
# rare tokens in a question, not to build a linguistics project.
STOPWORDS = {
    "a", "an", "and", "any", "are", "as", "at", "be", "been", "but", "by", "can",
    "do", "does", "for", "from", "get", "has", "have", "how", "i", "if", "in", "is",
    "it", "its", "many", "me", "much", "my", "no", "not", "of", "on", "or", "our",
    "so", "that", "the", "their", "them", "then", "there", "they", "this", "to", "was",
    "we", "what", "when", "where", "which", "who", "why", "will", "with", "you", "your",
}


def _rare_terms(query: str, limit: int = 6) -> list[str]:
    """The tokens worth matching *exactly*, and nothing else.

    Selectivity is the whole game. The first version of this took any word of five
    characters or more, which meant "How much cash can I withdraw from an ATM in
    one day?" ran a keyword search for "withdraw" — a term appearing in a third of
    the corpus. The lexical arm then fed a pile of weakly-related chunks into the
    fusion and demoted a correct dense ranking. Measured: it cost two probes.

    So the rule is now narrow and defensible: a token qualifies only if it carries
    a digit, or is an acronym the user typed in capitals. That is precisely the
    class of token embeddings smear away — "120", "0800", "22.9", "2026", "IBAN" —
    and precisely the class where an exact match means something. Ordinary prose is
    left entirely to the vector arm, which is good at it.
    """
    terms: list[str] = []
    for raw in WORD.findall(query):
        tok = raw.lower()
        if tok in STOPWORDS or len(tok) < 2 or tok in terms:
            continue
        if any(c.isdigit() for c in tok) or (raw.isupper() and len(raw) >= 3):
            terms.append(tok)
    return terms[:limit]


def _rrf(rank_map: dict[str, int], k: int = 60) -> float:
    """Reciprocal rank fusion: sum of 1/(k + rank) over the arms that found the
    document. Rank-based, so it needs no score calibration between a cosine
    similarity and a keyword match — which is the whole reason to use it."""
    return sum(1.0 / (k + rank + 1) for rank in rank_map.values())
