#!/usr/bin/env python
"""Run the 15-question evaluation set from data/questions.md through /ask.

    uv run python scripts/run_questions.py                    # run all 15
    uv run python scripts/run_questions.py --group C          # only the refusals
    uv run python scripts/run_questions.py --agent compliance # a different persona
    uv run python scripts/run_questions.py --md results.md    # markdown for the report

The question set is defined here rather than parsed out of the Markdown, so the
expected answer and the ground-truth sources travel with the code that checks
them. `data/questions.md` is the human-readable version of this list plus the
results of the last run.

The grading is deliberately shallow: it checks whether the expected sources were
retrieved, and whether the answer contains the literal fact or, for group C, a
refusal. It does not try to judge fluency. Anything it flags still gets read by
a person before it goes in the report — a regex is not a reviewer.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_API = "http://localhost:7799"

# Phrases that mean "I will not answer that". Group C succeeds when one appears
# and no invented figure does.
REFUSAL_MARKERS = (
    "not in", "no information", "does not contain", "do not have", "don't have",
    "not covered", "cannot answer", "can't answer", "not available in",
    "no passage", "nothing in", "not offer", "does not offer", "outside the scope",
    "out of scope", "not something", "no relevant", "unable to",
    # added after the first run: C3 refused perfectly with "I can't find any
    # information about mortgage early-repayment fees" and this list scored it as
    # a hallucination. The grader was wrong, not the model — worth keeping in the
    # write-up, because it is exactly how an eval harness manufactures fake failures.
    "can't find", "cannot find", "couldn't find", "could not find", "no mention",
    "don't cover", "do not cover", "not include", "no details", "not addressed",
)

QUESTIONS = [
    # --- A · simple retrieval: the answer sits in one chunk of one document ----
    {
        "id": "A1", "group": "A",
        "question": "After how many wrong PIN attempts is my card blocked?",
        "expected": "Three consecutive failed PIN attempts.",
        "sources": ["card-blocking-unblocking", "pin-management"],
        "must_contain": ["three"],
    },
    {
        "id": "A2", "group": "A",
        "question": "What is the monthly maintenance fee for a Libra Plus Debit card?",
        "expected": "5.00 lei per month in 2026 (it was 7.00 in 2025), waived if monthly "
                    "card spend is at least 1,000 lei.",
        "sources": ["fee-schedule-2026"],
        "must_contain": ["5.00", "5"],
    },
    {
        "id": "A3", "group": "A",
        "question": "How much cash can I withdraw from an ATM per day with a Standard Debit card?",
        "expected": "8,000 lei per day under the 2026 limits.",
        "sources": ["daily-limits-2026"],
        "must_contain": ["8,000", "8000"],
    },
    {
        "id": "A4", "group": "A",
        "question": "What annual interest rate applies to cash withdrawals on the Gold Credit card?",
        "expected": "28.9% for cash withdrawals (22.9% for purchases), with no "
                    "interest-free period on cash.",
        "sources": ["credit-card-repayment"],
        "must_contain": ["28.9"],
    },
    {
        "id": "A5", "group": "A",
        "question": "How long does standard delivery of a replacement card take?",
        "expected": "5 to 7 working days by post; express courier is 2 working days and "
                    "branch collection 3.",
        "sources": ["card-replacement-procedure"],
        "must_contain": ["5 to 7", "5-7", "5 and 7"],
    },
    {
        "id": "A6", "group": "A",
        "question": "How long do I have to dispute a card transaction?",
        "expected": "13 months from the transaction date, and no later than 60 days after "
                    "an unauthorised transaction appeared on the statement.",
        "sources": ["disputed-transactions"],
        "must_contain": ["13 month"],
    },
    {
        "id": "A7", "group": "A",
        "question": "Can I use a virtual card to withdraw cash from an ATM?",
        "expected": "No. A virtual card cannot withdraw cash, and cardless ATM withdrawal "
                    "is not available for it either.",
        "sources": ["virtual-cards"],
        "must_contain": ["cannot", "no"],
    },

    # --- B · multi-step: more than one lookup, a comparison, or arithmetic -----
    {
        "id": "B1", "group": "B",
        "question": "My net monthly income is 3,800 lei. Which Libra cards am I eligible "
                    "for, and what would each cost me per month?",
        "expected": "Standard Debit (no income condition) at 3.00 lei/month and Gold Credit "
                    "(needs 3,500 lei) at 15.00 lei/month. NOT Plus Debit, which needs "
                    "4,000 lei net income.",
        "sources": ["card-eligibility", "fee-schedule-2026"],
        "must_contain": ["4,000", "4000"],
        "why_hard": "Eligibility and price are in different documents on purpose, and the "
                    "answer turns on 3,800 falling below one threshold and above another.",
    },
    {
        "id": "B2", "group": "B",
        "question": "I withdrew 2,000 lei from another bank's ATM in Romania in December "
                    "2025, and again in February 2026. Did the fee change, and by how much?",
        "expected": "Yes. 2025: 1.00 + 0.20% = 5.00 lei. 2026: 1.50 + 0.20% = 5.50 lei. "
                    "A 0.50 lei increase, from the fixed part only.",
        "sources": ["fee-schedule-2025", "fee-schedule-2026"],
        "must_contain": ["5.50", "0.50", "1.50"],
        "why_hard": "Needs BOTH the current and the superseded fee schedule, plus arithmetic. "
                    "The status filter that fixes every other version question blocks this one.",
    },
    {
        "id": "B3", "group": "B",
        "question": "My card was stolen. The thief spent 900 lei before I reported it and "
                    "another 400 lei after. How much of that am I liable for?",
        "expected": "300 lei. Pre-report loss is capped at 300 lei absent gross negligence; "
                    "everything after the report is the bank's liability.",
        "sources": ["lost-or-stolen-card", "fraud-prevention"],
        "must_contain": ["300"],
        "why_hard": "Retrieval then arithmetic against a cap, and a condition (gross "
                    "negligence) that has to be checked before the cap applies.",
    },
    {
        "id": "B4", "group": "B",
        "question": "I am 16. Can I get a card I can use for online shopping and add to "
                    "Google Pay, and what do I have to do first?",
        "expected": "Yes — a Standard Debit card from age 14, but the online payment channel "
                    "is disabled by default and a parent or guardian must enable it in "
                    "branch. The card must then be activated before it can be added to a "
                    "wallet; adding it to a wallet does not activate it.",
        "sources": ["card-eligibility", "card-activation", "digital-wallets"],
        "must_contain": ["parent", "guardian", "branch"],
        "why_hard": "Three documents, and a condition in the first one changes what the "
                    "other two mean.",
    },
    {
        "id": "B5", "group": "B",
        "question": "I want to close my Gold Credit card. What has to happen first, and "
                    "will the holder of my supplementary card be told?",
        "expected": "The full balance including accrued interest must be settled, recurring "
                    "payments will fail, pending transactions still settle, and it must be "
                    "done in branch or in writing. The supplementary card closes "
                    "automatically and the bank does NOT notify its holder.",
        "sources": ["card-closure", "supplementary-cards"],
        "must_contain": ["not notif", "does not notify", "no notice", "not told",
                         "without", "automatically"],
        "why_hard": "Two documents, and the interesting half of the answer — the silence "
                    "toward the supplementary holder — is a negative fact stated in only "
                    "one of them.",
    },

    # --- C · must refuse: genuinely absent from the corpus ---------------------
    {
        "id": "C1", "group": "C",
        "question": "What is the interest rate on your student loans?",
        "expected": "A refusal. Libra Bank's card knowledge base says nothing about student "
                    "loans; a rate here would be invented.",
        "sources": [],
        "must_refuse": True,
    },
    {
        "id": "C2", "group": "C",
        "question": "How much does a SWIFT transfer to the United States cost?",
        "expected": "A refusal. The corpus covers card fees only; account transfer pricing "
                    "is not in it.",
        "sources": [],
        "must_refuse": True,
    },
    {
        "id": "C3", "group": "C",
        "question": "What is the early repayment fee on a Libra mortgage during the "
                    "fixed-rate period?",
        "expected": "A refusal. Mortgages are outside this corpus entirely — and this is the "
                    "example from the assignment brief, which makes it a good trap: it "
                    "sounds exactly like a question a bank assistant should answer.",
        "sources": [],
        "must_refuse": True,
    },
]


def post(api: str, path: str, payload: dict, timeout: int = 600) -> dict:
    req = urllib.request.Request(
        f"{api}{path}", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def normalise(text: str) -> str:
    """Fold the typographic characters a model actually writes onto the ASCII the
    marker list is written in. The model refused C3 with "I can’t find any
    information" — U+2019, not an apostrophe — and the substring test missed it.
    """
    return (text.casefold()
            .replace("’", "'").replace("‘", "'")
            .replace("“", '"').replace("”", '"')
            .replace("‑", "-").replace("–", "-").replace("—", "-"))


def grade(q: dict, result: dict) -> dict:
    answer = result["answer"]
    low = normalise(answer)
    got_sources = [h["source"] for h in result.get("retrieved", [])]
    wanted = set(q.get("sources") or [])
    found = wanted & set(got_sources)

    refused = any(m in low for m in REFUSAL_MARKERS)
    if q.get("must_refuse"):
        verdict = "refused correctly" if refused else "INVENTED"
    else:
        has_fact = any(normalise(m) in low for m in q.get("must_contain", []))
        if refused and not has_fact:
            verdict = "refused wrongly"
        elif has_fact and wanted <= set(got_sources):
            verdict = "correct"
        elif has_fact:
            verdict = "correct, sources incomplete"
        else:
            verdict = "wrong"

    return {
        "id": q["id"], "group": q["group"], "question": q["question"],
        "expected": q["expected"], "why_hard": q.get("why_hard"),
        "expected_sources": sorted(wanted),
        "retrieved_sources": got_sources,
        "sources_found": sorted(found),
        "sources_missing": sorted(wanted - set(got_sources)),
        "top_score": result["retrieved"][0]["score"] if result.get("retrieved") else None,
        "nothing_relevant": (result.get("retrieval") or {}).get("nothing_relevant", False),
        "answer": answer,
        "verdict": verdict,
        "prompt_tokens": (result.get("usage") or {}).get("prompt_tokens"),
        "completion_tokens": (result.get("usage") or {}).get("completion_tokens"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--agent", default="default")
    ap.add_argument("--group", default=None, choices=["A", "B", "C"])
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--json", default=None)
    ap.add_argument("--md", default=None, help="write a Markdown results table here")
    args = ap.parse_args()

    questions = [q for q in QUESTIONS if not args.group or q["group"] == args.group]
    print(f"{len(questions)} question(s) | agent '{args.agent}' | top_k {args.top_k}\n")

    rows = []
    for q in questions:
        started = time.time()
        try:
            result = post(args.api, "/ask", {
                "question": q["question"], "use_rag": True,
                "top_k": args.top_k, "agent": args.agent, "agent_mode": "local",
            })
        except urllib.error.HTTPError as e:
            print(f"{q['id']}  HTTP {e.code}: {e.read().decode('utf-8')[:200]}")
            continue
        row = grade(q, result)
        row["seconds"] = round(time.time() - started, 1)
        rows.append(row)
        flag = {"correct": "ok  ", "refused correctly": "ok  "}.get(row["verdict"], "  ->")
        print(f"{flag} {row['id']}  {row['verdict']:<28} "
              f"{'sources: ' + ', '.join(row['retrieved_sources'][:3]) if row['retrieved_sources'] else 'NOTHING RETRIEVED'}")

    print("\n--- tally ---")
    by_verdict: dict[str, int] = {}
    for r in rows:
        by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1
    for verdict, n in sorted(by_verdict.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>2}  {verdict}")
    good = sum(n for v, n in by_verdict.items() if v in ("correct", "refused correctly"))
    print(f"  {good}/{len(rows)} fully correct")
    tokens = sum(r["prompt_tokens"] or 0 for r in rows)
    print(f"  {tokens} prompt tokens across the run")

    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"\nJSON  -> {args.json}")
    if args.md:
        Path(args.md).write_text(to_markdown(rows), encoding="utf-8")
        print(f"MD    -> {args.md}")
    return 0


def to_markdown(rows: list[dict]) -> str:
    out = ["| # | Verdict | Sources retrieved | Answer (first line) |", "|---|---|---|---|"]
    for r in rows:
        first = r["answer"].strip().splitlines()[0][:110].replace("|", "\\|")
        srcs = ", ".join(r["retrieved_sources"][:3]) or "_(nothing)_"
        out.append(f"| {r['id']} | {r['verdict']} | {srcs} | {first} |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
