"""Chunking strategies — the first decision of every RAG pipeline, made visible.

Five strategies, deliberately spanning the sophistication spectrum:

  static    fixed character windows; cheap, ignores meaning (splits mid-sentence)
  sentence  groups of N sentences; trivially readable boundaries
  dynamic   structure-aware packing: paragraphs -> sentences packed to a size
            budget with overlap; never cuts inside a sentence unless forced
  semantic  sentence embeddings; a new chunk starts where adjacent cosine
            similarity drops below a threshold — meaning-aware, costs embeddings
  markdown  heading-aware: sections become chunks, tables and numbered lists are
            atomic blocks that are never cut, and every chunk carries a
            "document title › heading path" breadcrumb (Assignment 3, part 4)

`markdown` is the strategy this project actually ingests with. The other four are
kept because comparing against them is how the improvement gets measured.
"""
from __future__ import annotations

import math
import re
from typing import Callable

SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")

# --- markdown structure -------------------------------------------------------
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
TABLE_ROW = re.compile(r"^\s*\|")
LIST_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s+")
FRONT_MATTER = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)

EmbedFn = Callable[[list[str]], list[list[float]]]


def split_sentences(text: str) -> list[str]:
    parts = [s.strip() for s in SENTENCE_END.split(text)]
    return [s for s in parts if s]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# --- strategies ---------------------------------------------------------------

def chunk_static(text: str, size: int, overlap: int) -> list[str]:
    """Fixed windows over raw characters. The baseline that cuts words in half."""
    step = max(1, size - overlap)
    return [text[i : i + size].strip() for i in range(0, len(text), step) if text[i : i + size].strip()]


def chunk_sentence(text: str, per_chunk: int) -> list[str]:
    """Every N sentences become a chunk."""
    sentences = split_sentences(text)
    n = max(1, per_chunk)
    return [" ".join(sentences[i : i + n]) for i in range(0, len(sentences), n)]


def chunk_dynamic(text: str, size: int, overlap: int) -> list[str]:
    """Structure-aware packing: respect paragraphs, pack whole sentences up to
    `size` characters, carry a sentence-tail of ~`overlap` characters forward."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            chunks.append(" ".join(current))
            # overlap: keep trailing sentences up to `overlap` chars for continuity
            tail: list[str] = []
            tail_len = 0
            for s in reversed(current):
                if tail_len + len(s) > overlap:
                    break
                tail.insert(0, s)
                tail_len += len(s) + 1
            current = tail
            current_len = tail_len

    for paragraph in PARAGRAPH_SPLIT.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for sentence in split_sentences(paragraph):
            # a single sentence larger than the budget: hard-split as last resort
            if len(sentence) > size:
                flush()
                chunks.extend(chunk_static(sentence, size, overlap))
                current, current_len = [], 0
                continue
            if current_len + len(sentence) + 1 > size:
                flush()
            current.append(sentence)
            current_len += len(sentence) + 1
        # paragraph boundary is a natural flush point when near budget
        if current_len > size * 0.7:
            flush()
    if current:
        chunks.append(" ".join(current))
    # drop overlap-only remnants duplicating the previous chunk's tail
    return [c for i, c in enumerate(chunks) if not (i > 0 and c and c in chunks[i - 1])]


def chunk_semantic(text: str, threshold: float, embed_fn: EmbedFn) -> list[str]:
    """Embed every sentence; start a new chunk where the cosine similarity
    between neighbouring sentences falls below `threshold`."""
    sentences = split_sentences(text)
    if len(sentences) <= 1:
        return sentences
    vectors = embed_fn(sentences)
    chunks: list[list[str]] = [[sentences[0]]]
    for i in range(1, len(sentences)):
        if cosine(vectors[i - 1], vectors[i]) < threshold:
            chunks.append([sentences[i]])       # topic shift detected -> new chunk
        else:
            chunks[-1].append(sentences[i])
    return [" ".join(c) for c in chunks]


# --- markdown: heading-aware, table- and list-safe -----------------------------

def strip_front_matter(text: str) -> str:
    """Remove a leading YAML block. The loader parses it into metadata; leaving it
    in the text would embed `effective: 2026-01-01` as if it were prose."""
    return FRONT_MATTER.sub("", text, count=1)


def _blocks(lines: list[str]) -> list[str]:
    """Group lines into atomic blocks: a table, a list, or a paragraph.

    A table is consecutive `|`-rows; a list is consecutive items plus their
    indented continuation lines. These are the two shapes that lose their meaning
    when cut — a table row without its header row is a number with no name.
    """
    out: list[str] = []
    buf: list[str] = []
    kind: str | None = None

    def flush() -> None:
        nonlocal buf, kind
        if buf:
            body = "\n".join(buf).strip()
            if body:
                out.append(body)
        buf, kind = [], None

    for line in lines:
        if not line.strip():
            # a blank line ends a paragraph, but not a table or a list
            if kind in ("table", "list"):
                buf.append(line)
            else:
                flush()
            continue
        if TABLE_ROW.match(line):
            this = "table"
        elif LIST_ITEM.match(line):
            this = "list"
        elif kind == "list" and line.startswith((" ", "\t")):
            this = "list"                      # continuation of the current item
        else:
            this = "paragraph"
        if kind is not None and this != kind:
            flush()
        kind = this
        buf.append(line)
    flush()
    return out


def _breadcrumb(title: str | None, path: list[str]) -> str:
    """"Document title › section › subsection", with repetition removed.

    Documents normally open with an H1 that repeats the title from the header,
    which would otherwise produce "Card fee schedule 2026 › Card fee schedule
    2026 › Cash withdrawal" on every chunk — tokens spent saying nothing.
    """
    parts = ([title] if title else []) + path
    out: list[str] = []
    for p in parts:
        if p and (not out or p.strip().casefold() != out[-1].strip().casefold()):
            out.append(p.strip())
    return " › ".join(out)


def chunk_markdown(text: str, size: int, title: str | None = None) -> list[str]:
    """Split on Markdown headings, pack atomic blocks up to `size`, and prefix
    every chunk with its document title and heading path.

    Three deliberate choices, each answering a failure seen in `data/`:

      * the heading stays with its text, so "## Minimum payment" is not orphaned
        from the 5%-or-50-lei rule underneath it;
      * a table or a numbered list is never cut, even when it alone exceeds
        `size` — an intact oversized chunk beats two meaningless ones;
      * the breadcrumb makes a chunk self-describing, so a fee retrieved alone
        still says which document and which section it came from.
    """
    text = strip_front_matter(text).strip()
    if not text:
        return []

    # walk the document, accumulating (heading path, lines) sections
    sections: list[tuple[list[str], list[str]]] = []
    path: list[str] = []
    body: list[str] = []
    for line in text.splitlines():
        m = HEADING.match(line)
        if not m:
            body.append(line)
            continue
        if body:
            sections.append((list(path), body))
            body = []
        level, heading = len(m.group(1)), m.group(2).strip()
        path = path[: level - 1] + [heading]
    if body:
        sections.append((list(path), body))

    chunks: list[str] = []
    for path, lines in sections:
        blocks = _blocks(lines)
        if not blocks:
            continue
        crumb = _breadcrumb(title, path)
        prefix = f"[{crumb}]\n\n" if crumb else ""
        budget = max(1, size - len(prefix))

        current: list[str] = []
        current_len = 0
        for block in blocks:
            # an atomic block bigger than the budget gets its own chunk, intact
            if len(block) > budget:
                if current:
                    chunks.append(prefix + "\n\n".join(current))
                    current, current_len = [], 0
                chunks.append(prefix + block)
                continue
            if current and current_len + len(block) + 2 > budget:
                chunks.append(prefix + "\n\n".join(current))
                current, current_len = [], 0
            current.append(block)
            current_len += len(block) + 2
        if current:
            chunks.append(prefix + "\n\n".join(current))
    return chunks


# --- dispatcher ---------------------------------------------------------------

STRATEGIES = ("static", "dynamic", "sentence", "semantic", "markdown")


def chunk(
    text: str,
    strategy: str,
    *,
    size: int,
    overlap: int,
    per_chunk: int,
    threshold: float,
    embed_fn: EmbedFn | None = None,
    title: str | None = None,
) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if strategy == "static":
        return chunk_static(text, size, overlap)
    if strategy == "sentence":
        return chunk_sentence(text, per_chunk)
    if strategy == "dynamic":
        return chunk_dynamic(text, size, overlap)
    if strategy == "markdown":
        return chunk_markdown(text, size, title)
    if strategy == "semantic":
        if embed_fn is None:
            raise ValueError("semantic chunking requires an embedding function")
        return chunk_semantic(text, threshold, embed_fn)
    raise ValueError(f"unknown strategy '{strategy}' — expected one of {STRATEGIES}")
