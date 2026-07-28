---
title: PIN management
product: cards
audience: retail
effective: 2026-01-01
version: 2
status: current
---

# PIN management

## How a PIN is delivered

A new card never travels with its PIN. The PIN is sent by SMS to the registered phone
number when the card is dispatched, and the SMS is delivered once and not repeated. A
customer who deletes it uses the PIN reminder service rather than asking for a new card.

## Changing a PIN

The PIN can be changed at any Libra Bank ATM under **Services → Change PIN**, and requires
the current PIN. The fee is in the current fee schedule. It cannot be changed in the
mobile app, in branch, or over the phone — this is a deliberate control, because an ATM
proves possession of the physical card.

A new PIN must be **four digits** and is rejected if it is:

- four identical digits, such as 1111;
- four consecutive digits ascending or descending, such as 1234 or 9876;
- the last four digits of the card number;
- the customer's year of birth;
- any of the customer's **last three** PINs on that card.

## PIN reminder

A customer who has forgotten the PIN but still holds the card requests a reminder in the
mobile app under **Cards → PIN reminder**. The existing PIN is re-sent by SMS to the
registered phone number within 5 minutes. The fee is in the current fee schedule — it
became free in 2026, having been charged in 2025.

A reminder is refused if the registered phone number was changed in the **last 7 days**.
This delay is a fraud control and cannot be waived by Card Support, a branch, or a
supervisor.

## Blocked PIN

Three consecutive failed PIN attempts block the card; see *Card blocking and unblocking*
for how the block is lifted. The failed-attempt counter is held on the chip and on the
authorisation host, and they are reconciled at the next successful online transaction.

## What the bank never does

Bank staff cannot see a customer's PIN. Nobody at Libra Bank will ever ask for it — not by
phone, not by email, not in branch, and not in the app. A customer reporting that "someone
from the bank" asked for their PIN should be treated as a fraud case and the card blocked
immediately.
