from __future__ import annotations

import re
from dataclasses import dataclass, field


EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")

UPI = re.compile(r"\b[\w.-]{2,}@[a-zA-Z]{2,}\b")

CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")

AADHAAR = re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b")

PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")

ORDER_ID = re.compile(
    r"(?P<label>\b(?:order|ord)\b\s*(?:id|no\.?|number|#)?\s*[:#-]?\s*)"
    r"(?P<value>#?[A-Za-z]{0,4}-?\d{5,})",
    flags=re.IGNORECASE,
)

PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")

HOUSE = re.compile(
    r"\b(?:flat|house|h\.?\s?no\.?|plot|door|apt\.?|apartment|room)\s*(?:no\.?|number|#)?\s*[:#-]?\s*[\w/-]*\d[\w/-]*",
    flags=re.IGNORECASE,
)

PINCODE = re.compile(r"(?<!\d)[1-9]\d{5}(?!\d)")

LONG_NUMBER = re.compile(r"(?<!\d)\d{8,}(?!\d)")


@dataclass
class MaskResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def luhn_valid(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _replace(pattern: re.Pattern[str], tag: str, text: str, counts: dict[str, int]) -> str:
    new_text, n = pattern.subn(tag, text)
    if n:
        counts[tag] = counts.get(tag, 0) + n
    return new_text


def _mask_cards(text: str, counts: dict[str, int]) -> str:
    def replace_if_card(match: re.Match[str]) -> str:
        digits = re.sub(r"[ -]", "", match.group(0))
        if 13 <= len(digits) <= 19 and luhn_valid(digits):
            counts["[CARD]"] = counts.get("[CARD]", 0) + 1
            return "[CARD]"
        return match.group(0)

    return CARD_CANDIDATE.sub(replace_if_card, text)


def _mask_order_ids(text: str, counts: dict[str, int]) -> str:
    def replace_value(match: re.Match[str]) -> str:
        counts["[ORDER_ID]"] = counts.get("[ORDER_ID]", 0) + 1
        return match.group("label") + "[ORDER_ID]"

    return ORDER_ID.sub(replace_value, text)


def mask_pii(text: str) -> MaskResult:
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
    return mask_pii(text).total > 0
