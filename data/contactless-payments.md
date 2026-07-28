---
title: Contactless payments
product: cards
audience: retail
effective: 2026-01-01
version: 3
status: current
---

# Contactless payments

Every Libra Bank plastic card is contactless by default. There is no version of a Libra
card without the antenna, and the feature cannot be removed — a customer who does not want
it can only be advised to insert the card instead of tapping.

## Paying without a PIN

A contactless payment under the per-transaction threshold in *Card daily limits* is
approved without a PIN. Above the threshold, the terminal asks for the PIN, and the card
must be inserted at some terminals rather than tapped again.

Two separate conditions trigger a PIN request:

- the **single transaction** exceeds the per-transaction contactless threshold;
- the **cumulative** amount of consecutive contactless payments since the last PIN entry
  exceeds the cumulative threshold.

Both thresholds are set by the card schemes in agreement with the National Bank and are
listed in *Card daily limits 2026*. They were raised at the start of 2026.

## Phone and watch payments

A payment from Apple Pay or Google Pay is authenticated on the device — by face, fingerprint
or device passcode — and is therefore **not subject to the contactless thresholds at all**.
A customer paying 2,000 lei from their phone is not asked for the card PIN, because strong
authentication already happened on the device. This is the single most useful thing to tell
a customer who is annoyed by contactless limits.

## Failed contactless payments

| Symptom | Likely cause |
|---|---|
| "Insert card" on the first tap | Cumulative threshold reached; enter the PIN once and tapping resumes |
| Terminal does not react at all | Terminal not contactless-enabled, or the card is in a shielded wallet |
| Two cards in the wallet, payment fails | Card clash — the terminal sees both antennas; present one card only |
| Declined but the account has funds | Daily POS limit reached, or the card is frozen |

## Security

Contactless transactions carry the same liability rules as any card transaction; see
*Lost or stolen card*. The risk customers imagine — someone walking past with a reader —
requires the thief's terminal to be a registered merchant account, which is traceable, and
the amounts are capped by the same thresholds. Losses of this kind are refunded in full.
