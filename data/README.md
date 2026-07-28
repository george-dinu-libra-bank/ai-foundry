# Libra Assist corpus — retail cards

A fabricated knowledge base for a fictional retail card operation at "Libra Bank".
**Everything here is invented.** No real customer data, no real bank's internal documents,
no real fee schedule. Amounts, phone numbers, product names and rules were made up for this
assignment, which is the point: because I wrote the answers, I always know what the correct
answer is, and any wrong answer is diagnosable.

**Domain:** retail debit and credit cards — issuing, blocking, limits, fees, disputes,
fraud, wallets. Narrow enough that documents genuinely overlap and compete with each other
during retrieval, which is what makes the failure modes visible.

**Scale:** 20 documents, 300–600 words each, Markdown with a YAML header.

## Header fields

Every document opens with the same block. Part 4 turns these into Qdrant payload fields,
and Part 5 filters on them.

```yaml
---
title: Card fee schedule 2026     # human name, also prefixed onto every chunk
product: cards                    # single product family across this corpus
audience: retail                  # retail | staff — all retail here
effective: 2026-01-01             # the date the document started applying
version: 2                        # bumped on every revision
status: current                   # current | superseded
supersedes: fee-schedule-2025     # optional, on the newer of a version pair
superseded_by: fee-schedule-2026  # optional, on the older of a version pair
---
```

`status` is the field that does the real work: the two superseded documents are the
near-duplicates that a naive pipeline confuses with their replacements.

## The seven cases, and which document carries each

All seven cases from the assignment are covered; the table names the document that carries
each one and the question that exposes it.

| Case | Document(s) | The question that breaks a naive pipeline |
|---|---|---|
| **A precise number** | [card-blocking-unblocking.md](card-blocking-unblocking.md) — "three consecutive failed PIN attempts", 15 minutes; [credit-card-repayment.md](credit-card-repayment.md) — 22.9% / 28.9%, 5% or 50 lei | "After how many wrong PIN attempts is my card blocked?" Vector search happily returns a chunk *about* PIN blocking that omits the number. |
| **Two documents that must be combined** | [card-eligibility.md](card-eligibility.md) + [fee-schedule-2026.md](fee-schedule-2026.md); [daily-limits-2026.md](daily-limits-2026.md) + [fee-schedule-2026.md](fee-schedule-2026.md) | "Do I qualify for a Plus Debit card and what would it cost me monthly?" Eligibility and price are deliberately in different files. |
| **Near-duplicates that differ** | [fee-schedule-2025.md](fee-schedule-2025.md) vs [fee-schedule-2026.md](fee-schedule-2026.md); [daily-limits-2025.md](daily-limits-2025.md) vs [daily-limits-2026.md](daily-limits-2026.md) | "What is the FX conversion markup?" — 2.00% in 2025, 2.50% in 2026. The two documents are ~85% identical text, so they score almost identically. |
| **A long procedure with steps** | [card-replacement-procedure.md](card-replacement-procedure.md) — 9 numbered steps; [disputed-transactions.md](disputed-transactions.md) — 8 numbered steps | "Walk me through replacing a damaged card." Character-window chunking cuts the list in half and the answer loses steps 5–9. |
| **A table** | [fee-schedule-2026.md](fee-schedule-2026.md), [daily-limits-2026.md](daily-limits-2026.md), [card-products-overview.md](card-products-overview.md), [fraud-prevention.md](fraud-prevention.md) | "What does a Plus Debit card cost per month?" A table split mid-row leaves rows without their header, so the number arrives with no idea what it is the fee *for*. |
| **Contradiction across versions** | ATM cash limit: 5,000 lei (2025) → 8,000 lei (2026). Emergency replacement abroad: 150 lei → 120 lei. Late payment fee: 40 lei → 50 lei. PIN reminder by SMS: 2 lei → free. Contactless cumulative: 300 → 500 lei. | "How much can I take out of an ATM in a day?" Without a `status` filter, both answers are retrieved and the model picks one — or, worse, averages them. |
| **Something deliberately absent** | *(nothing — that is the case)* | See below. |

## Deliberately absent

These topics are **not** in the corpus, and no document mentions them even in passing. A
confident answer about any of them is a hallucination, and catching it is the point of
group C in [questions.md](questions.md):

- student loans, mortgages, and personal loans of any kind;
- savings accounts, term deposits and interest rates on them;
- crypto, trading and investment products;
- insurance sold as a standalone product (travel insurance is mentioned only as a Gold
  Credit card benefit);
- current account fees that are not card fees — transfers, IBAN, account maintenance;
- anything about a real bank.

Two topics sit deliberately on the boundary, to test the difference between *"I don't
know"* and *"we don't do that"*:

- **prepaid, gift, business and corporate cards** — [card-products-overview.md](card-products-overview.md)
  states we do not issue them. The right answer is a refusal *with a reason*, not "I have
  no information".
- **travel notifications** — [foreign-currency-and-travel.md](foreign-currency-and-travel.md)
  states they were removed in 2024. A customer asking how to notify us should be told there
  is nothing to notify, not given an invented procedure.

## The documents

| File | Title | Effective | Status |
|---|---|---|---|
| [card-blocking-unblocking.md](card-blocking-unblocking.md) | Card blocking and unblocking | 2026-01-15 | current |
| [card-replacement-procedure.md](card-replacement-procedure.md) | Card replacement procedure | 2026-02-01 | current |
| [card-activation.md](card-activation.md) | Card activation | 2026-01-01 | current |
| [card-eligibility.md](card-eligibility.md) | Card eligibility criteria | 2026-01-01 | current |
| [card-products-overview.md](card-products-overview.md) | Card products overview | 2026-01-01 | current |
| [card-closure.md](card-closure.md) | Closing a card | 2026-01-01 | current |
| [fee-schedule-2025.md](fee-schedule-2025.md) | Card fee schedule 2025 | 2025-01-01 | **superseded** |
| [fee-schedule-2026.md](fee-schedule-2026.md) | Card fee schedule 2026 | 2026-01-01 | current |
| [daily-limits-2025.md](daily-limits-2025.md) | Card daily limits 2025 | 2025-03-01 | **superseded** |
| [daily-limits-2026.md](daily-limits-2026.md) | Card daily limits 2026 | 2026-01-01 | current |
| [pin-management.md](pin-management.md) | PIN management | 2026-01-01 | current |
| [lost-or-stolen-card.md](lost-or-stolen-card.md) | Lost or stolen card | 2026-01-01 | current |
| [disputed-transactions.md](disputed-transactions.md) | Disputed transactions and chargebacks | 2026-01-01 | current |
| [fraud-prevention.md](fraud-prevention.md) | Card fraud prevention and customer liability | 2026-01-01 | current |
| [contactless-payments.md](contactless-payments.md) | Contactless payments | 2026-01-01 | current |
| [digital-wallets.md](digital-wallets.md) | Apple Pay and Google Pay | 2026-01-01 | current |
| [virtual-cards.md](virtual-cards.md) | Libra Virtual card | 2026-01-01 | current |
| [foreign-currency-and-travel.md](foreign-currency-and-travel.md) | Using a card abroad and foreign currency conversion | 2026-01-01 | current |
| [credit-card-repayment.md](credit-card-repayment.md) | Gold Credit repayment and interest | 2026-01-01 | current |
| [supplementary-cards.md](supplementary-cards.md) | Supplementary cards | 2026-01-01 | current |

## Ingesting it

```bash
uv run python scripts/load_corpus.py            # from code/backend/
```

See [../code/backend/scripts/load_corpus.py](../code/backend/scripts/load_corpus.py) and
[../NOTES.md](../NOTES.md).
