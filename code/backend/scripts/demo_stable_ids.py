#!/usr/bin/env python
"""Demonstrate what stable chunk ids actually fix.

    uv run python scripts/demo_stable_ids.py

The claim in NOTES.md is that deriving a point id from `source` + chunk index makes
re-ingestion replace rather than duplicate. The before/after run in
`measure_retrieval.py` cannot show this, because by then the fix is in both arms —
so this script isolates the mechanism instead, against a throwaway collection, with
no application code in the way.

It ingests the same five chunks three times under each id scheme and prints the
point count after each pass. `uuid4` is what `vectorstore.upsert()` used before;
`uuid5` is what it uses now.

The throwaway collection is deleted on the way out, whatever happens.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qdrant_client import QdrantClient, models          # noqa: E402

from app.config import settings                          # noqa: E402
from app.vectorstore import POINT_NAMESPACE              # noqa: E402

COLLECTION = "libra_rag__stable_id_demo"
SOURCE = "fee-schedule-2026"
CHUNKS = [f"chunk number {i} of the 2026 fee schedule" for i in range(5)]
DIM = 8


def legacy_id(_source: str, _index: int) -> str:
    """What upsert() did before: a fresh random id for every chunk, every time."""
    return str(uuid.uuid4())


def stable_id(source: str, index: int) -> str:
    """What it does now: the same source and index always give the same id."""
    return str(uuid.uuid5(POINT_NAMESPACE, f"{source}#{index}"))


def run(client: QdrantClient, make_id, passes: int = 3) -> list[int]:
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=models.VectorParams(size=DIM, distance=models.Distance.COSINE),
    )
    counts = []
    for _ in range(passes):
        client.upsert(
            collection_name=COLLECTION,
            points=[
                models.PointStruct(id=make_id(SOURCE, i), vector=[0.1 * i] * DIM,
                                   payload={"text": text, "index": i, "source": SOURCE})
                for i, text in enumerate(CHUNKS)
            ],
        )
        counts.append(client.count(collection_name=COLLECTION, exact=True).count)
    return counts


def main() -> int:
    client = QdrantClient(url=settings.qdrant_url, timeout=10)
    try:
        client.get_collections()
    except Exception as e:                               # noqa: BLE001
        print(f"Qdrant unreachable at {settings.qdrant_url}: {e}", file=sys.stderr)
        return 1

    print(f"Ingesting the same {len(CHUNKS)} chunks of '{SOURCE}' three times.\n")
    print(f"{'id scheme':<28}{'pass 1':>9}{'pass 2':>9}{'pass 3':>9}   verdict")
    print("-" * 72)
    try:
        for label, make_id in [("uuid4()  — before", legacy_id),
                               ("uuid5(source, index) — now", stable_id)]:
            counts = run(client, make_id)
            verdict = "duplicates" if counts[-1] > counts[0] else "replaces in place"
            print(f"{label:<28}{counts[0]:>9}{counts[1]:>9}{counts[2]:>9}   {verdict}")
    finally:
        if client.collection_exists(COLLECTION):
            client.delete_collection(COLLECTION)

    print("\nThe corpus has 20 documents and 111 chunks. Under the old scheme, three")
    print("runs of the loader left 333 points and retrieval returned each passage")
    print("three times, crowding the second fact out of top_k.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
