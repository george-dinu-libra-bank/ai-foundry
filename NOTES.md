# Libra Assist — Assignment 3

Retail card assistant over a 20-document fabricated corpus. Corpus and case mapping:
[data/README.md](data/README.md). Evaluation set and full answers:
[data/questions.md](data/questions.md).

Reproduce everything in this file:

```bash
cd code/backend
docker compose up qdrant -d && az login
uv run uvicorn app.main:app --reload --port 7799

uv run python scripts/load_corpus.py --fresh      # ingest data/
uv run python scripts/measure_retrieval.py        # the before/after table below
uv run python scripts/demo_stable_ids.py          # the idempotency claim
uv run python scripts/run_questions.py            # the 15-question run
```

---

## Ingestion — what I changed and why

**#3+#4 Heading-aware chunking that never cuts a table or a list**
([`app/chunking.py`](code/backend/app/chunking.py), strategy `markdown`). Sections
become chunks; a table or numbered list is an atomic block kept whole even when it
exceeds the size budget. Chosen because the corpus's two worst-affected documents are
exactly these shapes: `card-replacement-procedure` is a 9-step list and the fee
schedules are tables. Under 500-char windows the replacement procedure was cut into 6
fragments and question A5 ("how long does standard delivery take?" — inside step 4) was
not answerable at all. It is now one intact 2,651-char chunk, and A5 answers correctly.
A table row separated from its header row is a number with no name; that cannot happen
any more.

**#1 Stable chunk ids** ([`app/vectorstore.py`](code/backend/app/vectorstore.py) →
`point_id()`). The id is `uuid5(namespace, f"{source}#{index}")` instead of a fresh
`uuid4()`. Re-ingesting now replaces a document rather than piling a second copy on top
of it. Chosen first because it silently corrupts every measurement taken after it: with
duplicates in the collection, `top_k=4` returns the same passage twice and the honest
"before" number is unknowable. `prune_source()` handles the case ids alone do not — a
document edited from 9 chunks down to 6 leaves chunks 6–8 of the old version behind.

Also done, because they were nearly free once the loader existed: **#2 real metadata**
(the YAML header lands in the payload — without it the filters in part 5 have nothing to
filter on) and **#5 chunk context** (every chunk is prefixed `[title › section]`).

The loader is [`scripts/load_corpus.py`](code/backend/scripts/load_corpus.py) —
one command for the whole corpus, with `--dry-run`, `--only` and `--fresh`.

## Retrieval — what I changed and why

**#1 A score floor, as a gate rather than a filter**. If the *best* hit scores below
`RETRIEVAL_MIN_SCORE` (0.45), the search returns nothing and `/ask` tells the model so
explicitly. My first version dropped every hit below the floor individually, and it cost
recall: a floor high enough to refuse *student loans* (best hit 0.4425) also cut the
correct ATM-limit table (0.4918) out of an answerable query. Those are two different
questions — "is this answerable at all" and "is this chunk worth sending" — and only the
first one deserves an absolute threshold. The tail is now trimmed relative to the best
hit instead.

**#2 Metadata filters**, defaulting to `status: current`. This is what stops the 2025 fee
schedule from competing with the 2026 one, and it was the single highest-value change:
superseded documents appeared in 3 of 8 probes before and 0 after.

Also done: **#3 hybrid keyword+vector** with RRF fusion over Qdrant's full-text index,
and **#5 deduplication** by token Jaccard.

The hybrid arm needed two corrections before it earned its place, and both are the
interesting part:

1. My first `_rare_terms` took any word of five characters or more, so *"How much cash
   can I withdraw from an ATM in one day?"* ran a keyword search for **withdraw** — a
   term in a third of the corpus — and the resulting noise demoted a correct dense
   ranking. It cost two probes.
2. Restricting to digit-bearing tokens and capitalised acronyms was still wrong: **PIN**
   and **ATM** look like codes but appear in 22% and 19% of chunks respectively.

So selectivity is now measured, not guessed: a term survives only if its document
frequency is under 10% of the collection. On this corpus that line is clean — 120 (1%),
0800 (4%), 22.9 (1%), IBAN (2%) on one side; PIN (22%), ATM (19%), 2026 (16%), fee (28%)
on the other. Shape proposes, the collection disposes.

What hybrid buys, concretely: *"Which card fee is 120 lei?"* — pure vector ranks
`fee-schedule-2025` first at 0.5491 and never surfaces the chunk containing "120.00" in
the top 5. Hybrid puts it at rank 1 on a cosine score of only 0.3976.

---

## Before / after

`scripts/measure_retrieval.py`, 8 probes, `top_k=4`. Both arms wipe and re-ingest the
whole corpus so the two columns are comparable. **Before** = course defaults (dynamic
chunking at 500 chars, plain top-k cosine). **After** = markdown chunking at 900 plus the
four retrieval dials. "Answer chunk" means the chunk containing the literal fact, not
merely a chunk from the right document.

| | before | after |
|---|---|---|
| answer chunk at rank 1 | 2 / 7 | **4 / 7** |
| answer chunk in top 4 | 5 / 7 | **7 / 7** |
| probes surfacing a superseded document | 3 | **0** |
| absent topic returned nothing | no | **yes** |
| points after 1 ingest | 123 | 111 |
| points after 3 identical ingests (`demo_stable_ids.py`) | 15 / 5 chunks — **duplicates** | 5 / 5 chunks — **replaces** |

The last row is measured separately because by the time the before/after runs, stable ids
are in both code paths and it cannot show what they fixed. `demo_stable_ids.py` isolates
the mechanism against a throwaway collection: `uuid4` gives 5 → 10 → 15 points over three
identical ingests, `uuid5` gives 5 → 5 → 5.

---

## The 15 questions

Full transcript in [data/questions.md](data/questions.md). Agent `default`,
`agent_mode: local`, azure/gpt-5-mini, `top_k=6`.

| | Correct | Refused correctly | Partial | Wrong |
|---|---|---|---|---|
| A · simple retrieval (7) | 7 | – | 0 | 0 |
| B · multi-step (5) | 4 | – | 1 | 0 |
| C · must refuse (3) | – | 3 | 0 | 0 |
| **Total (15)** | **11** | **3** | **1** | **0** |

14/15. Three things that number hides, in descending order of how much they bother me:

**B2 answered correctly for the wrong reason.** The question needs both fee schedules —
2,000 lei withdrawn in December 2025 and again in February 2026 — and the `status:
current` filter excluded the 2025 document entirely. It still produced 5.00 → 5.50 → up
0.50, because it read the 2025 figure out of the *"(fixed part was 1.00)"* annotation I
happened to write into the 2026 document. Corpus design covered for a retrieval
configuration that had lost the question. Delete that annotation and the same setup
answers half the question or invents the other half.

**The score floor changed no verdict in group C.** Re-running C1 and C2 with
`min_score: 0` — six chunks reaching the model instead of zero — still produced refusals.
The persona's `refuse_when_unsupported` rule was doing the work all along. C3 proves it
from the other direction: *"early repayment fee on a mortgage during the fixed-rate
period"* scores 0.5755 against the card fee schedule, sails over the floor, and is
refused by the persona alone. What the floor actually bought was cost and honesty: 235
prompt tokens instead of 730 on C1, 238 instead of 843 on C2, and a `nothing_relevant`
flag the frontend can render as "nothing relevant found" rather than a confident-looking
paragraph. Worth having — but it is not what makes the assistant safe, and I would have
claimed it was if I had not tested it.

**The grader is a substring test.** Its first run scored C3 as a hallucination because
the model wrote "I can't find" with a typographic apostrophe and my marker list used an
ASCII one. An eval harness manufacturing a fake failure is a failure mode worth having
met once. Every answer recorded in `data/questions.md` was read by a person.

---

## Still wrong, and what I would do next

1. **The `status: current` filter is unconditional, and B2 is the proof it should not
   be.** Next: detect a past date or a year in the question and drop the filter for that
   query, or filter on `effective <= <date in the question>` instead of on status. The
   metadata to do it is already stored.
2. **The floor is calibrated on a gap of 0.07** — 0.4425 for the best absent-topic hit
   against 0.518 for the weakest correct one. That is not margin, it is luck. A corpus
   twice the size closes it. The durable fix is a cheap model call judging relevance of
   the top hit, not a tuned constant.
3. **No re-ranking.** Retrieving 10 and having the model pick 3 is the obvious next
   improvement, and probes P1/P2/P5 — answer present in the top 4 but not at rank 1 — are
   exactly the cases it would fix.
4. **Multi-turn is prompt replay, not memory.** The frontend replays the last 4 exchanges
   truncated to 400 characters. It resolves "and what does that cost?" and nothing more
   ambitious; there is no summarisation and no retrieval over the conversation itself.
5. **I wrote both the corpus and the questions.** That is what makes diagnosis possible
   and what makes 14/15 optimistic. Questions from someone who has not read `data/`
   would score lower, and that is the next measurement worth taking.
6. **Group B is answered by one retrieval and one model call.** Nothing decides to search
   again. These five questions exist to be re-run in Session 6 against an agent with
   tools, so the comparison is real rather than asserted.
