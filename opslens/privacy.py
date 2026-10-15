"""Mask personal data (PII) in ticket text before it leaves this computer.

What it does: replaces emails, UPI IDs, card numbers, Aadhaar/PAN numbers, phone numbers,
order IDs, PIN codes and house/flat numbers with tags like [EMAIL] or [PHONE].

Why this design:
- Plain regular expressions, run in a fixed order. The order matters: an email contains
  an "@", like a UPI ID, so emails go first; a 16-digit card number contains a 10-digit
  run that looks like a phone, so cards go before phones.
- We prefer over-masking. Masking an innocent number costs a little context for the LLM;
  leaking a phone number is a privacy incident.
- Card numbers must pass the Luhn checksum, so long order IDs are not called cards.
- Weakness (said openly): names and free-text street addresses are only partly caught.
  Production would add an NER model (see docs/PRODUCTION.md).

Example:
    >>> mask_pii("Refund not received, call me on +91 98765 43210, order id 4815162342").text
    'Refund not received, call me on [PHONE], order id [ORDER_ID]'
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---- Patterns (applied top to bottom) ---------------------------------------------------

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")

# UPI handles look like name@bank with NO dot after the @ (e.g. rahul.k@okaxis).
UPI = re.compile(r"\b[\w.-]{2,}@[a-zA-Z]{2,}\b")

# 13–19 digits, optionally split by spaces or dashes. Checked with Luhn before masking.
CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")

# Aadhaar: 12 digits, first digit 2-9, often written 4-4-4.
AADHAAR = re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b")

# PAN: 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F).
PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")

# Order IDs are anchored on the word "order" so a 10-digit order ID is not called a phone.
ORDER_ID = re.compile(
    r"(?P<label>\b(?:order|ord)\b\s*(?:id|no\.?|number|#)?\s*[:#-]?\s*)"
    r"(?P<value>#?[A-Za-z]{0,4}-?\d{5,})",
    flags=re.IGNORECASE,
)

# Indian mobile numbers: optional +91 / 91 / 0, then 10 digits starting 6-9 (may be split 5-5).
PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")

# House / flat / plot numbers: the keyword plus the number that follows it.
HOUSE = re.compile(
    r"\b(?:flat|house|h\.?\s?no\.?|plot|door|apt\.?|apartment|room)\s*(?:no\.?|number|#)?\s*[:#-]?\s*[\w/-]*\d[\w/-]*",
    flags=re.IGNORECASE,
)

# Indian PIN code: 6 digits, first digit 1-9. Bare 6-digit numbers are masked (over-masking).
PINCODE = re.compile(r"(?<!\d)[1-9]\d{5}(?!\d)")

# Any other long digit run (8+ digits) is probably an ID of some kind.
LONG_NUMBER = re.compile(r"(?<!\d)\d{8,}(?!\d)")


@dataclass
class MaskResult:
    """The masked text plus how many items of each kind were replaced."""

    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def luhn_valid(digits: str) -> bool:
    """Luhn checksum used by card numbers. Example: 4111111111111111 → True."""
    total = 0
    # Walk from the right; double every second digit.
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _replace(pattern: re.Pattern[str], tag: str, text: str, counts: dict[str, int]) -> str:
    """Replace every match of `pattern` with `tag` and count how many were replaced."""
    new_text, n = pattern.subn(tag, text)
    if n:
        counts[tag] = counts.get(tag, 0) + n
    return new_text


def _mask_cards(text: str, counts: dict[str, int]) -> str:
    """Mask card-like numbers, but only those that pass the Luhn check."""

    def replace_if_card(match: re.Match[str]) -> str:
        digits = re.sub(r"[ -]", "", match.group(0))
        if 13 <= len(digits) <= 19 and luhn_valid(digits):
            counts["[CARD]"] = counts.get("[CARD]", 0) + 1
            return "[CARD]"
        return match.group(0)

    return CARD_CANDIDATE.sub(replace_if_card, text)


def _mask_order_ids(text: str, counts: dict[str, int]) -> str:
    """Keep the word 'order id', replace only the value after it."""

    def replace_value(match: re.Match[str]) -> str:
        counts["[ORDER_ID]"] = counts.get("[ORDER_ID]", 0) + 1
        return match.group("label") + "[ORDER_ID]"

    return ORDER_ID.sub(replace_value, text)


def mask_pii(text: str) -> MaskResult:
    """Return `text` with personal data replaced by tags. Safe to call on any string."""
    counts: dict[str, int] = {}
    masked = text
    masked = _replace(EMAIL, "[EMAIL]", masked, counts)
    masked = _replace(UPI, "[UPI]", masked, counts)
    masked = _mask_cards(masked, counts)
    masked = _mask_order_ids(masked, counts)
    masked = _replace(AADHAAR, "[GOVT_ID]", masked, counts)
    masked = _replace(PAN, "[GOVT_ID]", masked, counts)
    masked = _replace(PHONE, "[PHONE]", masked, counts)
    masked = _replace(HOUSE, "[ADDRESS]", masked, counts)
    masked = _replace(PINCODE, "[PINCODE]", masked, counts)
    masked = _replace(LONG_NUMBER, "[NUMBER]", masked, counts)
    return MaskResult(text=masked, counts=counts)


def contains_pii(text: str) -> bool:
    """True if masking would change the text. Used as a last safety check before an API call."""
    return mask_pii(text).total > 0
