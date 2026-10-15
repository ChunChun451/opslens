# data/generate_ops.py, data/text_bank.py, config/roster.yaml — the synthetic support floor

## What it does
- Creates 56 days of food-delivery support tickets (Mon 31 Aug – Sun 25 Oct 2026): **71,530 tickets**.
- Each ticket has a time, channel, category, the category the customer *picked*, priority,
  language, gold/normal tier, order value, restaurant cluster and a customer message.
- Plants 5 problems (6 including the test-period surge) and 3 decoys, written to `data/planted.json`.
- Runs **Baseline A** in the simulator over all 56 days. The result is `history.csv`: the
  "helpdesk export" a company would hand us. The engine reads only this file.
- Public data has text but no timestamps, agents or SLAs, so we generate that layer and say so.

## How it works, step by step
1. **Day totals.** 1,130 tickets on a weekday, ×1.15 at weekends, ×1.35 on the two sale days
   (known events), ×1.12 on one busy-but-normal decoy day, times small random noise.
2. **Hour shares.** `hourly_profile` gives lunch and dinner peaks. Ticket peaks are smoother
   than order peaks, because complaints come during and after delivery.
3. **Category lifts.** Late deliveries ×1.35 and missing items ×1.2 at meal peaks. Planted
   spikes multiply one category in a few hours.
4. **Counts.** For every day × hour × category the number of tickets is a Poisson draw.
5. **Attributes.** Channel, priority (by category; email is never P1), language, tier, order
   value, restaurant cluster (a few big clusters, a long tail).
6. **Picked category.** Customers pick the wrong category 5% of the time; in the IVR phone
   menu 25% of the time (planted problem 5).
7. **Text.** Bitext requests (refunds, payments, accounts, tracking; "shipment" → "order")
   or our food templates (missing/wrong items, restaurants, app bugs). Hindi customers write
   Hinglish. 10% mention a second issue, 20% get typos, some contain phone numbers or emails.
8. **History.** Baseline A runs over all 56 days; outcomes are joined to the tickets.

## Worked example (real numbers from our config)
Saturday 20:00, missing items:
- day total 1,130 × 1.15 = 1,299.5 tickets
- 20:00 share of the day = 7.3 / 92.9 = 7.86% → 102.1 tickets in that hour
- missing-item share 0.14 × meal-peak lift 1.2 × weekend-dinner lift 1.35 (planted) → **23.2 expected**
- the actual count is a Poisson draw around 23.2 (for example 21 or 26).

## The roster (`config/roster.yaml`)
40 agents, every one listed with team, start hour, days off, languages and extra skills.
Start hours and days off were chosen with a small search that keeps each team's load as flat
as possible across the 168 hours of the week. That makes the status quo **reasonable, not a
strawman**. Then two problems were planted on purpose:
- Only 3 agents (Kavita, Arjun, Pooja; none at night) speak Hindi *and* handle refunds/payments.
- Two Team C evening agents are off every weekend, while weekend-dinner missing/wrong items rise ×1.35.
  Three Team D evening agents are cross-trained on those categories: the fix OpsLens should find.

## Calibration (printed by `mingw32-make gen`)
| Target (Baseline A, history) | Range | Result |
|---|---|---|
| Breach % | 12–18 | **13.1** |
| Mean utilisation | 0.70–0.80 | **0.80** |
| Team C weekend-dinner ρ | 1.2–1.5 | **1.40** |

Planted signals visible in the raw history: Hindi refund/payment tickets wait **301.7 min** vs
**46.7 min** for English; cluster 17 sends **5.1%** of wrong-item tickets but only **2.0%** of all
tickets; phone tickets get **12.8** transfers per 100 vs **2.6** for chat.

How we got there: the first version had 44.5% breaches (shifts did not follow demand). Fixes:
shorter handle times, a smoother hourly profile, the roster search, a third Hindi refund agent
(with two, Hindi waits averaged 15 hours and never cleared), and sale days at ×1.35 instead of ×1.6.

## Weaknesses
- Text is partly synthetic (templates). Real tickets are messier.
- Volume is Poisson around a fixed pattern; real days have more surprises.
- Agents are identical apart from skills and languages (no "fast" or "new" agents).

## How to read the code
`data/generate_ops.py`: read `main()` first, then `make_tickets()` → `one_ticket()`.
`data/text_bank.py`: `TextBank.make_text()`. The planted problems are all in
`config/generator.yaml` (section "Planted problems") and `config/roster.yaml` (comments at the top).
