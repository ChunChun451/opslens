"""PII masking must catch Indian-format personal data and leave normal ticket text alone."""

import pytest

from opslens.privacy import contains_pii, luhn_valid, mask_pii


@pytest.mark.parametrize(
    "text, expected",
    [
        ("mail me at priya.s@gmail.com", "mail me at [EMAIL]"),
        ("paid via rahul.k@okaxis but failed", "paid via [UPI] but failed"),
        ("call +91 98765 43210 now", "call [PHONE] now"),
        ("call 9876543210", "call [PHONE]"),
        ("my number is 09876543210", "my number is [PHONE]"),
        ("card 4111 1111 1111 1111 charged twice", "card [CARD] charged twice"),
        ("aadhaar 2345 6789 0123", "aadhaar [GOVT_ID]"),
        ("PAN ABCDE1234F", "PAN [GOVT_ID]"),
        ("order id 4815162342 missing fries", "order id [ORDER_ID] missing fries"),
        ("Order #ZOM-1234567 was late", "Order #[ORDER_ID] was late"),
        ("deliver to flat 302, pin 560034", "deliver to [ADDRESS], pin [PINCODE]"),
        ("ref 123456789012345 pending", "ref [NUMBER] pending"),
    ],
)
def test_masks_each_kind(text: str, expected: str) -> None:
    assert mask_pii(text).text == expected


def test_normal_ticket_text_is_unchanged() -> None:
    text = "My biryani came 45 min late and the raita was missing. Refund Rs 250 please."
    result = mask_pii(text)
    assert result.text == text
    assert result.total == 0
    assert not contains_pii(text)


def test_order_id_is_not_mistaken_for_phone() -> None:
    # A 10-digit order ID that starts with 9 looks like a phone number on its own.
    result = mask_pii("order no 9123456780 is wrong")
    assert result.text == "order no [ORDER_ID] is wrong"
    assert "[PHONE]" not in result.counts


def test_long_non_luhn_number_is_not_a_card() -> None:
    # 16 digits that fail Luhn are an ID, not a card — still masked, but as [NUMBER].
    assert not luhn_valid("1234567812345678")
    assert mask_pii("txn 1234567812345678").text == "txn [NUMBER]"


def test_counts_are_reported() -> None:
    result = mask_pii("call 9876543210 or 9123456789, mail a@b.com")
    assert result.counts == {"[EMAIL]": 1, "[PHONE]": 2}
    assert result.total == 3


def test_hinglish_ticket_with_phone() -> None:
    result = mask_pii("khana abhi tak nahi aaya, mera number 98765-43210 hai")
    assert result.text == "khana abhi tak nahi aaya, mera number [PHONE] hai"
