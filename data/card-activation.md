---
title: Card activation
product: cards
audience: retail
effective: 2026-01-01
version: 2
status: current
---

# Card activation

Every Libra Bank card arrives inactive. An inactive card declines every transaction with
the message *"card not activated"*, which customers frequently misread as the card being
blocked.

## The three activation channels

- **Mobile app** — Cards → the new card → **Activate**. Instant. The customer must be
  logged in; the app does not activate a card for a customer who is only enrolled.
- **Any Libra Bank ATM** — insert the card and complete one PIN-authenticated operation,
  including a balance enquiry. This is the only channel that works for a customer who has
  never used the app.
- **Card Support, 0800 800 210** — after the three-question identity verification.

Activation at a non-Libra ATM does not work: the card is declined before the transaction
reaches our authorisation host.

## Timing

An unactivated card is cancelled automatically **90 days** after dispatch. A card cancelled
this way requires a full replacement, and the replacement is charged as *administrative*,
meaning free — the customer is not penalised for the automatic cancellation.

## When the old card stops working

For a replacement card, the old card stops the instant the new one is activated. There is
no overlap period and no grace day. A customer who activates the new card at an ATM while
travelling should be told plainly that the old card in their pocket is now dead.

For a card renewed at natural expiry the old card keeps working until the last day of its
expiry month, even after the new one is activated. This difference surprises staff as often
as it surprises customers.

## Digital wallets

A card must be activated before it can be added to Apple Pay or Google Pay. Adding a card
to a wallet does **not** activate it. Once activated and provisioned, the wallet token
survives a later card replacement: the tokens are re-provisioned automatically within
24 hours, so wallet payments resume without the customer doing anything.

## Common failures

| Symptom | Cause |
|---|---|
| "Card not activated" at a POS | Activation was never completed |
| App shows no Activate button | Card not yet dispatched, or already active |
| ATM activation declined | Non-Libra ATM, or wrong PIN entered |
| Wallet says "contact your bank" | Card active but daily online limit already reached |
