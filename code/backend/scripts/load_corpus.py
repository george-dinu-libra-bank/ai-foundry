#!/usr/bin/env python
"""Ingest the whole `data/` corpus in one command.

    uv run python scripts/load_corpus.py                  # ingest everything
    uv run python scripts/load_corpus.py --fresh          # wipe first
    uv run python scripts/load_corpus.py --strategy dynamic --size 500
    uv run python scripts/load_corpus.py --only fee-schedule-2026
    uv run python scripts/load_corpus.py --dry-run        # chunk, print, store nothing

Why a script instead of twenty curl calls: not laziness, reproducibility. The
corpus is re-ingested on every chunking change, and a measurement is only worth
something if the thing being measured was rebuilt identically each time.

What it does that a curl call does not:

  * parses the YAML header of each document and sends it as `metadata`, so title,
    effective date, version and status land in the Qdrant payload and can be
    filtered on (part 4, improvement #2);
  * passes the document title so the `markdown` strategy can prefix every chunk
    with its "[title › section]" breadcrumb (improvement #5);
  * derives `source` from the filename, which combined with the stable ids in
    `vectorstore.point_id()` makes re-ingesting replace rather than duplicate
    (improvement #1).

No third-party YAML dependency: the headers in `data/` are flat `key: value`
pairs, and a 20-line parser is more honest here than a new package.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DEFAULT_API = "http://localhost:7799"

# A Windows console defaults to cp1252 and raises on the em-dashes and box marks
# below. Ask for UTF-8 and degrade rather than crash if the terminal refuses.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Header keys worth storing. Anything else in the YAML block is ignored rather
# than stored, so a typo in a document does not silently become a payload field.
META_KEYS = ("title", "product", "audience", "effective", "expires",
             "version", "status", "supersedes", "superseded_by")
INT_KEYS = ("version",)


# --- the tiny YAML front-matter parser ----------------------------------------
def parse_front_matter(text: str) -> tuple[dict, str]:
    """Split `---\\n key: value \\n---\\n body` into (metadata, body).

    Deliberately strict: no lists, no nesting, no multi-line values. If a document
    needs those, it needs a real YAML parser and this should be replaced rather
    than extended.
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    end = next((i for i, line in enumerate(lines[1:], start=1)
                if line.strip() == "---"), None)
    if end is None:
        return {}, text

    meta: dict = {}
    for line in lines[1:end]:
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip().strip("'\"")
        if key in META_KEYS and value:
            meta[key] = int(value) if key in INT_KEYS and value.isdigit() else value
    return meta, "\n".join(lines[end + 1:]).lstrip("\n")


# --- HTTP ---------------------------------------------------------------------
def post(api: str, path: str, payload: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        f"{api}{path}", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def request(api: str, path: str, method: str = "GET", timeout: int = 30) -> dict:
    req = urllib.request.Request(f"{api}{path}", method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


def explain(err: urllib.error.HTTPError) -> str:
    try:
        detail = json.loads(err.read().decode("utf-8")).get("detail", "")
    except Exception:                              # noqa: BLE001
        detail = ""
    if err.code == 409:
        return (f"{detail}\n  -> the embedding model changed. Run with --fresh, or "
                f"DELETE /collection, then ingest again.")
    return detail or str(err)


# --- main ---------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest data/ into the RAG API.")
    ap.add_argument("--api", default=DEFAULT_API, help=f"API base URL (default {DEFAULT_API})")
    ap.add_argument("--data", default=str(DATA_DIR), help="corpus directory")
    ap.add_argument("--strategy", default="markdown",
                    help="static | dynamic | sentence | semantic | markdown (default markdown)")
    ap.add_argument("--size", type=int, default=900, help="target chunk size in characters")
    ap.add_argument("--overlap", type=int, default=80, help="chunk overlap, non-markdown only")
    ap.add_argument("--fresh", action="store_true",
                    help="DELETE the collection first — the honest way to compare strategies")
    ap.add_argument("--only", default=None, help="ingest one document by filename stem")
    ap.add_argument("--dry-run", action="store_true", help="chunk and report, store nothing")
    args = ap.parse_args()

    data_dir = Path(args.data)
    if not data_dir.is_dir():
        print(f"No corpus directory at {data_dir}", file=sys.stderr)
        return 2

    files = sorted(p for p in data_dir.glob("*.md") if p.stem != "README")
    files = [p for p in files if p.stem != "questions"]
    if args.only:
        files = [p for p in files if p.stem == args.only]
        if not files:
            print(f"No document named '{args.only}' in {data_dir}", file=sys.stderr)
            return 2
    if not files:
        print(f"No documents in {data_dir}", file=sys.stderr)
        return 2

    try:
        health = request(args.api, "/health")
    except Exception as e:                         # noqa: BLE001
        print(f"Cannot reach the API at {args.api} — is it running?\n  {e}", file=sys.stderr)
        return 1
    if health.get("qdrant") != "ok":
        print(f"Qdrant is {health.get('qdrant')} at {health.get('qdrant_url')} — "
              f"start it with: docker compose up qdrant -d", file=sys.stderr)
        return 1

    print(f"API      {args.api}  |  {health['llm']['provider']}/{health['llm']['model']}")
    print(f"Embed    {health['embeddings']['provider']}/{health['embeddings']['model']}")
    print(f"Corpus   {data_dir}  |  {len(files)} document(s)")
    print(f"Chunking {args.strategy}, size {args.size}"
          f"{'' if args.strategy == 'markdown' else f', overlap {args.overlap}'}")
    if args.dry_run:
        print("Mode     DRY RUN — nothing will be stored")
    print()

    if args.fresh and not args.dry_run:
        request(args.api, "/collection", method="DELETE")
        print("Collection deleted — starting from empty.\n")

    started = time.time()
    total_chunks = total_pruned = replaced = failed = 0

    for path in files:
        source = path.stem
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        if not meta.get("title"):
            print(f"  !  {source}: no title in the header — the breadcrumb will be thin")

        payload = {
            "text": body,
            "strategy": args.strategy,
            "chunk_size": args.size,
            "chunk_overlap": args.overlap,
            "source": source,
            "title": meta.get("title"),
            "metadata": meta,
        }
        endpoint = "/chunk" if args.dry_run else "/ingest"
        try:
            result = post(args.api, endpoint, payload)
        except urllib.error.HTTPError as e:
            print(f"  FAIL  {source}: HTTP {e.code} — {explain(e)}")
            failed += 1
            continue
        except Exception as e:                     # noqa: BLE001
            print(f"  FAIL  {source}: {type(e).__name__}: {e}")
            failed += 1
            continue

        count = result["count"]
        total_chunks += count
        sizes = [c["chars"] for c in result["chunks"]]
        note = ""
        if not args.dry_run:
            total_pruned += result.get("pruned", 0)
            replaced += 1 if result.get("replaced") else 0
            bits = []
            if result.get("replaced"):
                bits.append("replaced")
            if result.get("pruned"):
                bits.append(f"pruned {result['pruned']}")
            note = f"  [{', '.join(bits)}]" if bits else ""
        print(f"  ok   {source:<34} {count:>2} chunks  "
              f"{min(sizes):>4}-{max(sizes):<4} chars  "
              f"{meta.get('status', '?'):<10}{note}")

    elapsed = time.time() - started
    print(f"\n{len(files) - failed}/{len(files)} documents | {total_chunks} chunks | "
          f"{elapsed:.1f}s")
    if not args.dry_run:
        if replaced:
            print(f"{replaced} document(s) already existed and were replaced in place — "
                  f"stable ids, so no duplication.")
        if total_pruned:
            print(f"{total_pruned} stale chunk(s) removed from shorter previous versions.")
        info = request(args.api, "/collection")
        print(f"Collection '{info['name']}': {info['points_count']} points, "
              f"dim {info['vector_dimension']}")
        if info["points_count"] != total_chunks and not args.only:
            print(f"  !  {info['points_count']} points but {total_chunks} chunks ingested — "
                  f"leftovers from an earlier run. Re-run with --fresh to be sure.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
