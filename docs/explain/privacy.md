# privacy.py — masking personal data

## What it does
- Finds personal data in ticket text: email, UPI ID, card number, Aadhaar, PAN, phone,
  order ID, house/flat number, PIN code, other long ID numbers.
- Replaces each one with a tag: `[EMAIL]`, `[UPI]`, `[CARD]`, `[GOVT_ID]`, `[PHONE]`,
  `[ORDER_ID]`, `[ADDRESS]`, `[PINCODE]`, `[NUMBER]`.
- It runs inside the LLM client, before any text leaves the laptop. Nobody can forget to call it.
- The cache stores only masked text.
- It also counts what it masked, so we can show "3 phone numbers masked today".

## How it works, step by step
1. Ten regular expressions run in a fixed order (top of the file).
2. **Order matters.** Email before UPI (both have `@`; an email has a dot after the `@`,
   a UPI ID does not). Cards before phones (a 16-digit card contains a 10-digit run).
   Order IDs before phones (a 10-digit order ID can start with 9, like a mobile number).
3. Order IDs are found by the word "order" in front ("order id 4815162342"). We keep the
   words and replace only the number, so the LLM still knows an order was mentioned.
4. Card candidates must pass the **Luhn checksum** (the check digit every real card has).
   A long number that fails Luhn is masked as `[NUMBER]` instead.
5. Anything still left with 8 or more digits becomes `[NUMBER]`. We prefer over-masking.

## Worked example
Input: `Paisa kat gaya, call +91 98765 43210, order id 4815162342, flat 302 pin 560034`
- `+91 98765 43210` → matches PHONE (optional +91, then 10 digits starting 6–9, split 5-5).
- `order id 4815162342` → ORDER_ID keeps "order id ", replaces the number.
- `flat 302` → ADDRESS. `560034` → PINCODE.
Output: `Paisa kat gaya, call [PHONE], order id [ORDER_ID], [ADDRESS] pin [PINCODE]`
Counts: `{"[PHONE]": 1, "[ORDER_ID]": 1, "[ADDRESS]": 1, "[PINCODE]": 1}`.
Normal text like "biryani came 45 min late, refund Rs 250" is not changed (numbers are short).

## Weaknesses (say them before a judge does)
- **Names** ("my name is Rahul") and free-text street names are not masked. Production
  would add a named-entity model such as Microsoft Presidio (docs/PRODUCTION.md).
- A 6-digit amount ("Rs 125000") is masked as a PIN code. Harmless, but it loses context.
- Phone formats from other countries are only caught by the "8+ digits" rule.

## How to read the code
Open `opslens/privacy.py`, read `mask_pii()` at the bottom first: it is the list of steps in
order. Then look at the pattern for each step at the top. Tests: `tests/test_privacy.py`
(one line per kind of PII).
