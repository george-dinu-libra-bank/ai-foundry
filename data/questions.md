# Evaluation set — 15 questions

Fifteen questions against the corpus in this directory, in three groups. Every
question has an expected answer and the documents that genuinely contain it,
because I wrote the corpus and therefore know the right answer.

The **Actual** rows are a real run, not a description of one. Reproduce it with:

```bash
cd code/backend
uv run python scripts/run_questions.py --json results.json --md results.md
```

**Run recorded here:** agent `default`, `agent_mode: local`, `use_rag: true`,
`top_k: 6`, azure/gpt-5-mini, embeddings text-embedding-3-small, 111 chunks from
20 documents, retrieval with `min_score 0.45`, `filters {"status": "current"}`,
hybrid and dedup on.

## Score

| | Correct | Refused correctly | Partial | Wrong |
|---|---|---|---|---|
| **A · simple retrieval** (7) | 7 | – | 0 | 0 |
| **B · multi-step** (5) | 4 | – | 1 | 0 |
| **C · must refuse** (3) | – | 3 | 0 | 0 |
| **Total (15)** | **11** | **3** | **1** | **0** |

14/15 fully correct. Read the caveats under [What this score hides](#what-this-score-hides)
before believing it — three of those points are shakier than the number suggests.

---

## A · Simple retrieval

The answer sits in one chunk of one document. These are the questions a single
lookup should get right, and if they fail, nothing downstream is worth debugging.

### A1 · After how many wrong PIN attempts is my card blocked?

- **Expected:** three consecutive failed PIN attempts.
- **Sources:** `card-blocking-unblocking`, also stated in `pin-management`.
- **Retrieved:** pin-management, card-blocking-unblocking, lost-or-stolen-card · top score 0.750
- **Actual:** *"Your card is automatically blocked after three consecutive failed PIN
  attempts at an ATM or POS terminal [1][2]. The failed-attempt counter resets to zero
  after any successful PIN entry…"*
- **Verdict: correct.** It also volunteered the counter-reset rule, which is the part
  customers actually get wrong.

### A2 · What is the monthly maintenance fee for a Libra Plus Debit card?

- **Expected:** 5.00 lei in 2026, waived at 1,000 lei monthly spend. Was 7.00 in 2025.
- **Sources:** `fee-schedule-2026`
- **Retrieved:** fee-schedule-2026, virtual-cards, card-eligibility · top score 0.759
- **Actual:** *"…is 5.00; this fee is waived if the cardholder's monthly card spend is at
  least 1,000. This replaced the previous 7.00 fee and the previous 1,500 spend waiver."*
- **Verdict: correct.** The 2025 schedule never entered the context — the `status`
  filter removed it. Without that filter this is the question that returns both.

### A3 · How much cash can I withdraw from an ATM per day with a Standard Debit card?

- **Expected:** 8,000 lei per day (2026). It was 5,000 in 2025.
- **Sources:** `daily-limits-2026`
- **Retrieved:** daily-limits-2026, card-products-overview, fee-schedule-2026 · top score 0.600
- **Actual:** *"The standard ATM cash withdrawal limit … is 8,000 lei per day [1]. You can
  request a temporary one-day increase up to 20,000 lei…"*
- **Verdict: correct.** No trace of the 5,000 figure.

### A4 · What annual interest rate applies to cash withdrawals on the Gold Credit card?

- **Expected:** 28.9% (purchases are 22.9%), no interest-free period on cash.
- **Sources:** `credit-card-repayment`
- **Retrieved:** credit-card-repayment, card-products-overview · top score 0.824
- **Actual:** *"…is 28.9% [1]. Cash withdrawals do not have an interest-free period;
  interest … runs from the day of the withdrawal [3]."*
- **Verdict: correct.** Highest-scoring retrieval in the whole set — the section heading
  and the question use nearly the same words.

### A5 · How long does standard delivery of a replacement card take?

- **Expected:** 5 to 7 working days by post; express 2 days, branch collection 3.
- **Sources:** `card-replacement-procedure`
- **Retrieved:** card-replacement-procedure, digital-wallets, lost-or-stolen-card, fee-schedule-2026 · top score 0.606
- **Actual:** *"Standard delivery is by post to the address on file and takes 5 to 7
  working days [1]. Confirm or update the delivery address before ordering…"*
- **Verdict: correct.** The delivery timings live inside step 4 of a nine-step numbered
  list. Under the old character-window chunking that list was cut in half and this
  answer was not retrievable — see NOTES.md.

### A6 · How long do I have to dispute a card transaction?

- **Expected:** 13 months from the transaction date, plus the tighter 60-day rule for
  unauthorised transactions.
- **Sources:** `disputed-transactions`
- **Retrieved:** disputed-transactions, card-closure · top score 0.686
- **Actual:** *"…within 13 months of the transaction date [1]. For suspected unauthorised
  transactions there's a tighter rule: … no later than 60 days after the transaction
  appeared on your statement…"*
- **Verdict: correct.** It found the second deadline, which is the one that actually
  costs customers money.

### A7 · Can I use a virtual card to withdraw cash from an ATM?

- **Expected:** No, and no cardless ATM withdrawal either.
- **Sources:** `virtual-cards`
- **Retrieved:** virtual-cards, card-products-overview, card-replacement-procedure, foreign-currency-and-travel · top score 0.567
- **Actual:** *"No. A Libra Virtual card cannot withdraw cash — there is no plastic to
  insert in an ATM, and it cannot be used for cardless ATM withdrawals either [1]."*
- **Verdict: correct.** A negative fact, which is the kind retrieval usually fumbles,
  because "cannot withdraw cash" embeds close to "can withdraw cash".

---

## B · Multi-step

More than one lookup, a comparison, or arithmetic. Today the assistant handles these by
retrieving more and reasoning in a single call — there is no second search, no tool. In
Session 6 the same five questions become the comparison against a tool-using agent.

### B1 · My net monthly income is 3,800 lei. Which cards am I eligible for, and what would each cost per month?

- **Expected:** Standard Debit (no income condition) at 3.00 lei/month and Gold Credit
  (needs 3,500) at 15.00 lei/month. **Not** Plus Debit, which needs 4,000.
- **Sources:** `card-eligibility` + `fee-schedule-2026`
- **What makes it hard:** eligibility and price are in different documents on purpose,
  and the answer turns on 3,800 falling below one threshold and above another.
- **Retrieved:** card-eligibility, card-activation, card-blocking-unblocking, fee-schedule-2026, lost-or-stolen-card · top score 0.706
- **Actual:** *"With a net monthly income of 3,800 lei you meet the income threshold for
  Libra Gold Credit (requires ≥3,500 lei) but you must also meet the other Gold criteria:
  age ≥18, a payslip … ≤60 days old, a clean Credit Bureau record … and total debt
  service below 40%…"* — and correctly excluded Plus Debit on the 4,000 threshold.
- **Verdict: correct.** Both documents were retrieved and both numbers used. It hedged
  the Gold answer with the other four criteria rather than declaring eligibility, which
  is the right instinct for a bank.

### B2 · I withdrew 2,000 lei at another bank's ATM in December 2025 and again in February 2026. Did the fee change, and by how much?

- **Expected:** 2025: 1.00 + 0.20% = 5.00 lei. 2026: 1.50 + 0.20% = 5.50 lei. Up 0.50.
- **Sources:** `fee-schedule-2025` + `fee-schedule-2026`
- **What makes it hard:** it needs the current **and** the superseded schedule, plus
  arithmetic. The `status: current` filter that fixes every other version question
  blocks this one.
- **Retrieved:** daily-limits-2026, card-eligibility, fee-schedule-2026 · top score 0.554
  — **`fee-schedule-2025` was filtered out and never reached the model.**
- **Actual:** *"Yes. The current 2026 fee … is 1.50 lei + 0.20% of the amount; the fixed
  part 'was 1.00' previously [5]. On a 2,000-lei withdrawal that means December 2025
  would have been 1.00 + 0.20%·2,000 = 5.00 lei, and February 2026 is 1.50 + 0.20%·2,000
  = 5.50 lei"* — an increase of 0.50 lei.
- **Verdict: correct answer, incomplete sourcing.** The arithmetic and both figures are
  right, but it got the 2025 number from the *"(fixed part was 1.00)"* annotation inside
  the 2026 document, not from the 2025 document — which retrieval had excluded. The
  corpus design rescued an answer the retrieval configuration should have lost.
  **This is the most instructive result in the set**; it is written up in NOTES.md as the
  known limitation, with the fix (make the filter conditional on the question mentioning
  a past date).

### B3 · The thief spent 900 lei before I reported the card stolen and 400 after. What am I liable for?

- **Expected:** 300 lei — pre-report loss capped at 300 absent gross negligence,
  post-report entirely the bank's.
- **Sources:** `lost-or-stolen-card` + `fraud-prevention`
- **What makes it hard:** retrieval, then arithmetic against a cap, then a condition
  (gross negligence) that has to be checked before the cap applies.
- **Retrieved:** lost-or-stolen-card, fraud-prevention · top score 0.734
- **Actual:** *"Assuming you did not act fraudulently or with gross negligence, your
  liability is capped at 300 lei for the 900-lei of transactions made before you reported
  the card; the bank is liable for the 600 lei remainder … plus the full 400 lei spent
  after the report."*
- **Verdict: correct.** It stated the condition as a condition instead of silently
  assuming it, and did the 900 → 300 / 600 split correctly.

### B4 · I am 16. Can I get a card for online shopping and Google Pay, and what do I do first?

- **Expected:** Standard Debit from 14, but online payments disabled by default for
  14–17 and a parent or guardian must enable them in branch. The card must be activated
  before it can go in a wallet; adding it to a wallet does not activate it.
- **Sources:** `card-eligibility` + `card-activation` + `digital-wallets`
- **What makes it hard:** three documents, and a condition in the first changes what the
  other two mean.
- **Retrieved:** digital-wallets, card-eligibility, virtual-cards, card-activation · top score 0.541
- **Actual:** *"Yes. At 16 you can have our Libra Standard Debit card, but online payments
  are disabled by default for customers aged 14–17 — a parent or guardian must enable the
  online payment channel in branch before you can use the card for online shopping…"*
- **Verdict: correct.** All three documents retrieved; the age condition correctly
  gated the rest of the answer.

### B5 · I want to close my Gold Credit card. What has to happen first, and will my supplementary cardholder be told?

- **Expected:** balance settled in full, recurring payments will fail, pending
  transactions still settle, branch or written request only. The supplementary card
  closes automatically and **the bank does not notify its holder**.
- **Sources:** `card-closure` + `supplementary-cards`
- **What makes it hard:** two documents, and the interesting half — the silence toward
  the supplementary holder — is a negative fact stated in only one of them.
- **Retrieved:** supplementary-cards, card-closure · top score 0.645
- **Actual:** the four pre-closure checks in order, then the supplementary card closing
  automatically with the main cardholder responsible for telling the holder.
- **Verdict: correct.** Both halves, including the negative fact.

---

## C · Must refuse

The answer is genuinely not in the corpus. A confident invented answer here is a
failure, and catching it is the entire point of the group.

### C1 · What is the interest rate on your student loans?

- **Expected:** a refusal. Libra Bank's card corpus says nothing about student loans.
- **Sources:** none — deliberately absent, see [README.md](README.md#deliberately-absent).
- **Retrieved:** **nothing.** Best candidate scored 0.4425, below the 0.45 floor, so
  retrieval returned an empty set and reported `nothing_relevant: true`.
- **Actual:** *"I don't have any bank documents about student loan interest rates in the
  knowledge base — the search returned no relevant passages, so I can't provide the
  interest rate…"*
- **Verdict: refused correctly.** Prompt cost 235 tokens instead of 730, because there
  was no context to send.

### C2 · How much does a SWIFT transfer to the United States cost?

- **Expected:** a refusal. The corpus covers card fees only; account transfer pricing is
  not in it.
- **Sources:** none — deliberately absent.
- **Retrieved:** **nothing** — everything fell below the floor.
- **Actual:** *"The bank's knowledge base returned no passages about SWIFT transfer fees
  to the United States … I can't answer from general knowledge or invent rates."*
- **Verdict: refused correctly.** 238 prompt tokens against 843 without the floor.

### C3 · What is the early repayment fee on a Libra mortgage during the fixed-rate period?

This is the assignment brief's own example, which makes it the best trap in the set: it
sounds exactly like a question a bank assistant ought to answer.

- **Expected:** a refusal. Mortgages are outside this corpus entirely.
- **Sources:** none — deliberately absent.
- **Retrieved:** fee-schedule-2026, virtual-cards, card-eligibility, credit-card-repayment
  · top score **0.576 — comfortably above the floor.** The floor did not fire here: "fee",
  "repayment" and "fixed" are all over the card fee schedule, so the query looks
  answerable to a vector.
- **Actual:** *"The documents you provided only cover card fees and card policies … and do
  not include any mortgage terms or an early-repayment fee schedule [1][2][3][4][5][6]."*
- **Verdict: refused correctly** — but **not because of retrieval.** Six plausible-looking
  chunks reached the model and the persona's `refuse_when_unsupported` rule stopped it
  from stitching a mortgage answer out of card fees. The score floor and the persona are
  two independent defences and only the second one fired. See NOTES.md.

---

## What this score hides

14/15 is a better number than the system deserves, and the honest reading is narrower.

1. **B2's correct answer came from the corpus, not from retrieval.** The 2025 document
   was filtered out. It answered from an annotation I happened to write into the 2026
   document. Remove that annotation and the same configuration answers half the question
   or invents the other half.

2. **The score floor changed no verdict in group C.** Re-running C1 and C2 with
   `min_score: 0` — six chunks reaching the model instead of zero — still produced
   refusals. The persona was doing the work. What the floor bought was **cost and
   clarity**: 235 tokens instead of 730 on C1, 238 instead of 843 on C2, and a
   `nothing_relevant: true` flag the frontend can show instead of a confident-looking
   empty answer. That is worth having, but it is not what makes the assistant safe.

3. **The grader is a substring test, not a judge.** `A1` passes on the word "three"
   appearing anywhere in the answer. Every answer above was read by a person before
   being recorded; the automated verdict is a filter for attention, not the verdict
   itself. Its first run scored C3 as a hallucination because the model wrote
   "I can't find" with a typographic apostrophe and the marker list used an ASCII one —
   an eval harness manufacturing a fake failure, which is a failure mode worth having
   seen once.

4. **Fifteen questions is a small sample and I wrote both sides of it.** Knowing the
   answers is what makes the diagnosis possible; it is also what makes the score
   optimistic. Questions written by someone who has not read the corpus would score
   lower, and that is the next thing to do.
