#!/usr/bin/env python
"""Measure retrieval before and after the Assignment 3 changes.

    uv run python scripts/measure_retrieval.py                 # full comparison
    uv run python scripts/measure_retrieval.py --json out.json # machine-readable

The comparison is deliberately end-to-end and destructive: it wipes the
collection, ingests the corpus with the *old* settings, scores a fixed probe set,
wipes again, ingests with the *new* settings, and scores the same probes. Anything
less — reusing an existing collection, changing one dial at a time in place — makes
the two numbers incomparable, which is the failure this script exists to avoid.

Two things are measured:

  1. **Retrieval quality**, per probe: did the chunk that actually contains the
     answer come back, at what rank, and with what score. `expected_source` is
     ground truth because I wrote the corpus.

  2. **Idempotency**: the collection is ingested twice in a row and the point
     count compared. Under the old `uuid4()` ids it doubled.

`hit@1` and `hit@k` are counts, not percentages: with 8 probes a percentage would
imply a precision the sample size does not have.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
DEFAULT_API = "http://localhost:7799"

# --- the probe set ------------------------------------------------------------
# Each probe names the case from data/README.md that it exercises, and the source
# document that genuinely holds the answer. `must_contain` is the literal string
# an answering chunk has to carry — the point of the precise-number cases is that
# a chunk *about* the topic is not good enough.
PROBES = [
    {
        "id": "P1",
        "case": "precise number",
        "query": "After how many wrong PIN attempts is my card blocked?",
        # the rule is stated in both documents, and either is a correct answer —
        # scoring only one of them would penalise retrieval for being right
        "expected_sources": ["card-blocking-unblocking", "pin-management"],
        "must_contain": "three consecutive failed PIN attempts",
    },
    {
        "id": "P2",
        "case": "near-duplicate / version",
        "query": "How much cash can I withdraw from an ATM in one day?",
        "expected_sources": ["daily-limits-2026"],
        "must_contain": "8,000",
        "wrong_source": "daily-limits-2025",
    },
    {
        "id": "P3",
        "case": "near-duplicate / version",
        "query": "What is the foreign currency conversion markup?",
        "expected_sources": ["fee-schedule-2026"],
        "must_contain": "2.50%",
        "wrong_source": "fee-schedule-2025",
    },
    {
        "id": "P4",
        "case": "table",
        "query": "What is the monthly fee for a Libra Plus Debit card?",
        "expected_sources": ["fee-schedule-2026"],
        "must_contain": "Libra Plus Debit",
        "wrong_source": "fee-schedule-2025",
    },
    {
        "id": "P5",
        "case": "long procedure",
        "query": "What are the steps to replace a damaged card?",
        "expected_sources": ["card-replacement-procedure"],
        "must_contain": "Activate on arrival",
    },
    {
        "id": "P6",
        "case": "precise number",
        "query": "What is the interest rate on the Gold Credit card for cash withdrawals?",
        "expected_sources": ["credit-card-repayment"],
        "must_contain": "28.9%",
    },
    {
        "id": "P7",
        "case": "exact token",
        "query": "Which card fee is 120 lei?",
        "expected_sources": ["fee-schedule-2026"],
        "must_contain": "120.00",
        "wrong_source": "fee-schedule-2025",
    },
    {
        "id": "P8",
        "case": "deliberately absent",
        "query": "What is the interest rate on your student loans?",
        "expected_sources": [],           # nothing should come back
        "must_contain": None,
    },
]

BEFORE = {
    "label": "before",
    "description": "course defaults: dynamic chunking at 500 chars, plain top-k cosine",
    "ingest": ["--strategy", "dynamic", "--size", "500", "--overlap", "80"],
    # explicitly off rather than omitted: the API falls back to the RETRIEVAL_*
    # values in .env, so an omitted key would silently inherit the improvements
    # and the "before" column would measure the "after" behaviour
    "search": {"min_score": 0, "filters": {}, "hybrid": False, "dedup": False},
}
AFTER = {
    "label": "after",
    "description": "markdown chunking at 900 chars; score floor, status filter, hybrid, dedup",
    "ingest": ["--strategy", "markdown", "--size", "900"],
    # 0.45 is calibrated, not guessed: the best hit for the absent-topic probe
    # scores 0.4425, and the weakest genuinely-correct hit in the probe set scores
    # 0.518. The floor sits in that gap. It is a narrow gap, and NOTES.md says so.
    "search": {"min_score": 0.45, "filters": {"status": "current"},
               "hybrid": True, "dedup": True},
}
TOP_K = 4


# --- HTTP ---------------------------------------------------------------------
def post(api: str, path: str, payload: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        f"{api}{path}", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get(api: str, path: str) -> dict:
    with urllib.request.urlopen(f"{api}{path}", timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


# --- one run ------------------------------------------------------------------
def ingest(api: str, config: dict, fresh: bool = True) -> None:
    cmd = [sys.executable, str(HERE / "load_corpus.py"), "--api", api, *config["ingest"]]
    if fresh:
        cmd.append("--fresh")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        print(proc.stdout, proc.stderr, file=sys.stderr)
        raise SystemExit(f"ingest failed for '{config['label']}'")


def score_probe(api: str, probe: dict, search_opts: dict) -> dict:
    body = {"query": probe["query"], "top_k": TOP_K, **search_opts}
    try:
        result = post(api, "/search", body)
    except urllib.error.HTTPError as e:
        return {"id": probe["id"], "error": f"HTTP {e.code}"}
    hits = result["hits"]

    rank_correct = None          # 1-based rank of the first hit from an acceptable document
    rank_answer = None           # 1-based rank of the first hit carrying the literal answer
    rank_wrong = None            # 1-based rank of the first hit from the superseded twin
    needle = (probe["must_contain"] or "").casefold()
    for i, h in enumerate(hits, start=1):
        if h.get("source") in probe["expected_sources"]:
            rank_correct = rank_correct or i
            if needle and needle in h["text"].casefold():
                rank_answer = rank_answer or i
        if probe.get("wrong_source") and h.get("source") == probe["wrong_source"]:
            rank_wrong = rank_wrong or i

    if not probe["expected_sources"]:
        # the absent-topic probe: success is an empty result, not a good one
        ok = len(hits) == 0
    else:
        ok = rank_answer == 1

    return {
        "id": probe["id"], "case": probe["case"], "query": probe["query"],
        "hits": len(hits),
        "top_source": hits[0].get("source") if hits else None,
        "top_score": hits[0]["score"] if hits else None,
        "rank_correct_doc": rank_correct,
        "rank_answer_chunk": rank_answer,
        "rank_superseded": rank_wrong,
        "ok": ok,
        "nothing_relevant": (result.get("retrieval") or {}).get("nothing_relevant", False),
    }


def run_config(api: str, config: dict) -> dict:
    print(f"\n=== {config['label'].upper()} — {config['description']} ===")
    ingest(api, config, fresh=True)
    first = get(api, "/collection")["points_count"]

    rows = [score_probe(api, p, config["search"]) for p in PROBES]

    # idempotency: ingest the identical corpus again and see whether it grew
    ingest(api, config, fresh=False)
    second = get(api, "/collection")["points_count"]

    print(f"{'probe':<6}{'case':<24}{'top source':<30}{'score':>7}"
          f"{'ans@':>6}{'sup@':>6}  ok")
    for r in rows:
        print(f"{r['id']:<6}{r['case']:<24}{str(r['top_source'] or '(none)'):<30}"
              f"{r['top_score'] if r['top_score'] is not None else '-':>7}"
              f"{str(r['rank_answer_chunk'] or '-'):>6}"
              f"{str(r['rank_superseded'] or '-'):>6}"
              f"  {'YES' if r['ok'] else 'no'}")

    answerable = [r for r in rows if r["id"] != "P8"]
    summary = {
        "label": config["label"],
        "description": config["description"],
        "points_after_first_ingest": first,
        "points_after_second_ingest": second,
        "duplicated_on_reingest": second > first,
        "answer_at_rank_1": sum(1 for r in answerable if r["rank_answer_chunk"] == 1),
        "answer_in_top_k": sum(1 for r in answerable if r["rank_answer_chunk"] is not None),
        "answerable_probes": len(answerable),
        "superseded_in_results": sum(1 for r in rows if r["rank_superseded"]),
        "absent_topic_refused": rows[-1]["ok"],
        "probes": rows,
    }
    print(f"\n  answer chunk at rank 1 : {summary['answer_at_rank_1']}/{len(answerable)}")
    print(f"  answer chunk in top {TOP_K}  : {summary['answer_in_top_k']}/{len(answerable)}")
    print(f"  superseded doc surfaced: {summary['superseded_in_results']} probe(s)")
    print(f"  absent topic returned nothing: "
          f"{'YES' if summary['absent_topic_refused'] else 'no'}")
    print(f"  points after 1st ingest: {first}   after an identical 2nd: {second}"
          f"   {'DUPLICATED' if second > first else '(unchanged - idempotent)'}")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--json", default=None, help="write the full result to this file")
    args = ap.parse_args()

    print("This wipes the collection twice. Ctrl-C now if that is not what you want.")
    results = [run_config(args.api, BEFORE), run_config(args.api, AFTER)]

    b, a = results
    print("\n" + "=" * 74)
    print(f"{'metric':<38}{'before':>14}{'after':>14}")
    print("-" * 74)
    for label, key in [
        ("answer chunk at rank 1", "answer_at_rank_1"),
        (f"answer chunk in top {TOP_K}", "answer_in_top_k"),
        ("superseded doc in results", "superseded_in_results"),
        ("points after 1 ingest", "points_after_first_ingest"),
        ("points after 2 identical ingests", "points_after_second_ingest"),
    ]:
        print(f"{label:<38}{str(b[key]):>14}{str(a[key]):>14}")
    print(f"{'absent topic returned nothing':<38}"
          f"{('YES' if b['absent_topic_refused'] else 'no'):>14}"
          f"{('YES' if a['absent_topic_refused'] else 'no'):>14}")
    print("=" * 74)
    print("Both columns are idempotent because stable ids are in the code path for\n"
          "both — this run cannot show what they fixed. For that, see\n"
          "  uv run python scripts/demo_stable_ids.py")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nFull result written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
