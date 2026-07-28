---
title: Apple Pay and Google Pay
product: cards
audience: retail
effective: 2026-01-01
version: 2
status: current
---

# Apple Pay and Google Pay

Libra Bank supports Apple Pay and Google Pay on all four card products, including the
virtual card. Samsung Pay and Garmin Pay are not supported.

## Adding a card

The card must be **activated** first; see *Card activation*. Adding a card to a wallet does
not activate it.

Add it either from the Libra Assist Mobile app — **Cards → the card → Add to Apple Pay** —
or from the wallet app itself, by scanning the card and confirming with a code sent to the
registered phone number. The app route is faster and does not require the plastic to be to
hand, which matters when the card is a virtual one.

## What is actually stored

The wallet does not store the card number. It stores a **token**: a separate number, tied to
that one device, useless anywhere else. A merchant compromised after a wallet payment leaks
the token, not the card. This is why the bank does not reissue a card after a wallet-related
merchant breach.

## Limits and authentication

Wallet payments are authenticated on the device by face, fingerprint or passcode. Because
strong authentication has already happened, they are **not subject to the contactless
per-transaction or cumulative thresholds** — any amount can be paid by tapping the phone, up
to the card's normal daily POS limit.

The daily POS and online limits from *Card daily limits 2026* still apply. Wallet spending
and plastic spending count against the same limit; they are not separate budgets.

## Card replacement and tokens

When a card is replaced, tokens are re-provisioned automatically within **24 hours** of the
new card being activated. The customer does nothing. Wallet payments work again as soon as
re-provisioning completes, often before the plastic has been used once.

This is the practical reason to tell a customer waiting for a replacement card to keep using
their phone.

## Removing a card

Removing a card from a wallet deletes the token and stops payments from that device
immediately. It does not block or close the card. A customer whose phone is lost should
remove the token remotely through Apple or Google, not block the card — blocking the card
also stops the plastic they still have.
