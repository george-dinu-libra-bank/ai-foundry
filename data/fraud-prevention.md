---
title: Card fraud prevention and customer liability
product: cards
audience: retail
effective: 2026-01-01
version: 2
status: current
---

# Card fraud prevention and customer liability

## How the fraud engine decides

Every card authorisation is scored in real time against the customer's own history: usual
merchants, usual amounts, usual countries, usual hours. A transaction scoring above the
intervention threshold is either challenged or declined. The score is not disclosed to the
customer, and staff cannot see it either — they see only the outcome and the reason
category.

Common triggers, in rough order of frequency:

- a first transaction in a country the customer has never used the card in;
- several small online transactions in quick succession, the classic card-testing pattern;
- an ATM withdrawal at or near the daily limit shortly after an online purchase;
- a purchase at a merchant category the customer has never used, above their usual amount.

A declined transaction of this kind sends an SMS to the registered phone number asking the
customer to confirm or deny. Confirming releases the block within minutes.

## 3-D Secure

Online payments at participating merchants require **3-D Secure** authentication, which
Libra Bank performs in the mobile app: the customer approves the payment with the same
biometrics or code they use to log in. SMS one-time codes were withdrawn in 2025 and are no
longer available as a fallback.

A customer without the app cannot complete a 3-D Secure payment. This is the most common
reason for online payments failing on an otherwise healthy card, and the only fix is to
install and enrol in the app.

## Liability

| Situation | Who bears the loss |
|---|---|
| Transaction after a lost or stolen report | The bank, in full |
| Transaction before the report, ordinary negligence | The customer, capped at 300 lei |
| Transaction before the report, gross negligence | The customer, in full |
| Transaction the customer authorised and now regrets | The customer, in full |
| Merchant fraud, card details never shared | The bank, subject to the dispute process |
| Customer shared the PIN, the card, or a 3-D Secure approval | The customer, in full |

Approving a 3-D Secure prompt for a payment the customer did not make — because a caller
told them to — is treated as gross negligence. This is the dominant fraud pattern in
Romania and the reason the app screen names the merchant and the amount in full.

## What the bank never asks for

No Libra Bank employee will ever ask for a PIN, a full card number, a CVV, an app password,
or approval of a 3-D Secure prompt. Any caller who does is a fraudster, regardless of the
number they appear to call from. Caller ID is trivially forged.
