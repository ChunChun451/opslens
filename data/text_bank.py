"""Ticket text for the generator: Bitext requests + food-delivery templates (English + Hinglish).

What it does: `TextBank.make_text(rng, category, language, ...)` returns one realistic
customer message for a ticket.

Why this design:
- Bitext (data/SOURCES.md) gives varied, noisy, human-like requests for refunds, payments,
  accounts and order tracking. It is written for generic e-commerce, so we swap words
  ("shipment" → "order", "product" → "food").
- Bitext has nothing for missing items, wrong items, restaurants or app bugs, so those come
  from templates with slots (dish, restaurant, minutes, amount). Hindi-language customers
  write Hinglish (Hindi in Latin letters), as most do in chat.
- Realism on purpose: ~10% of tickets mention a second issue, ~20% get typos, and many
  contain an order ID or phone number (which privacy.py must then mask).
- The text is partly synthetic, and we say so (data/SOURCES.md).

Example:
    >>> bank = TextBank.from_bitext_csv(path)
    >>> bank.make_text(rng, "missing_item", "hi", restaurant="Biryani Junction", order_id="4815162342")
    'raita nahi aaya biryani ke saath, order id 4815162342. refund chahiye'
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# ---- Bitext intents we use, mapped to OpsLens categories ------------------------------------

BITEXT_INTENT_TO_CATEGORY: dict[str, str] = {
    "delivery_period": "late_delivery",
    "track_order": "late_delivery",
    "get_refund": "refund",
    "track_refund": "refund",
    "check_refund_policy": "refund",
    "payment_issue": "payment_failure",
    "recover_password": "account",
    "edit_account": "account",
    "switch_account": "account",
    "delete_account": "account",
    "registration_problems": "account",
}

# Share of a category's English tickets that come from Bitext (the rest from templates).
BITEXT_SHARE: dict[str, float] = {
    "late_delivery": 0.3,
    "refund": 0.5,
    "payment_failure": 0.5,
    "account": 0.6,
}

# Bitext is generic e-commerce; make it sound like food delivery.
WORD_SWAPS: list[tuple[str, str]] = [
    (r"\bshipments?\b", "order"),
    (r"\bparcels?\b", "order"),
    (r"\bpackages?\b", "order"),
    (r"\bproducts?\b", "food"),
    (r"\bshipping\b", "delivery"),
    (r"\bshipped\b", "delivered"),
]

# ---- Slot values (all fictional) -------------------------------------------------------------

DISHES = [
    "chicken biryani", "paneer butter masala", "veg thali", "masala dosa", "chole bhature",
    "butter chicken", "margherita pizza", "veg burger", "hakka noodles", "dal makhani",
    "rajma chawal", "pav bhaji", "momos", "shawarma roll", "idli sambar", "fried rice",
]
SIDES = ["raita", "coke", "garlic naan", "gulab jamun", "fries", "extra chutney", "salad", "papad"]
RESTAURANTS = [
    "Biryani Junction", "Spice Route Kitchen", "Dosa Corner", "Punjab Grill House",
    "Pizza Point", "Momo Street", "Thali Express", "Wok This Way", "Royal Tandoor",
    "Chaat Bazaar", "Burger Hub", "Kerala Kitchen",
]

# ---- English templates -----------------------------------------------------------------------

TEMPLATES_EN: dict[str, list[str]] = {
    "late_delivery": [
        "my order from {restaurant} is {mins} minutes late, where is it?",
        "food still not delivered, app says arriving but its been {mins} min",
        "delivery partner not moving on the map for {mins} minutes. order {order_ref}",
        "ordered {dish} an hour ago, still waiting. this is too late",
        "why is my order delayed? it showed 30 min and now its {mins}",
        "rider is not picking up the call and the order is late",
        "estimated time keeps increasing, order {order_ref} still not here",
        "food was supposed to arrive by 8 pm, its way past that",
        "please check my order status, very late, kids are hungry",
        "order stuck at 'out for delivery' for {mins} minutes",
        "still no sign of my {dish}, very delayed",
        "how much longer? order from {restaurant} delayed again",
    ],
    "missing_item": [
        "{side} missing from my order {order_ref}",
        "I ordered {dish} and {side} but {side} was not in the bag",
        "one item is missing, only got {dish}",
        "half my order is missing. paid for 3 items received 2",
        "the {side} is not there in the package, please refund it",
        "items missing in my order from {restaurant}",
        "where is my {side}? it was in the bill but not delivered",
        "my {dish} came without the {side} I paid for",
        "you missed one item in order {order_ref}",
        "bag was sealed but {side} was not inside",
        "received incomplete order, {side} missing",
    ],
    "wrong_item": [
        "I got the wrong order, ordered {dish} but received something else",
        "received non veg instead of veg! I am vegetarian, this is serious",
        "wrong dish delivered from {restaurant}, this is not what I ordered",
        "the order belongs to someone else, wrong name on the bill",
        "got {dish} instead of what I ordered, order {order_ref}",
        "they sent the wrong items, please fix",
        "ordered medium spicy, got extra spicy and wrong size",
        "my {dish} was replaced with some other dish without asking",
        "completely different food delivered to me",
        "wrong order again from {restaurant}, second time this week",
    ],
    "refund": [
        "when will I get my refund of Rs {amount}?",
        "refund for order {order_ref} not received yet",
        "you said refund in 5 days, its been a week",
        "I cancelled my order but money not returned",
        "please refund Rs {amount} for the bad food",
        "refund status shows processed but not in my account",
        "need my money back for order {order_ref}",
        "how long does refund take to bank account",
        "refund was promised by your agent yesterday, nothing yet",
    ],
    "payment_failure": [
        "money debited but order not placed",
        "payment failed but Rs {amount} deducted from my account",
        "UPI payment stuck in pending, order not confirmed",
        "charged twice for the same order {order_ref}",
        "card payment declined but bank shows debit",
        "payment went through but app shows payment failed",
        "amount cut from wallet, no order created",
        "tried to pay 3 times, every time it fails",
    ],
    "app_bug": [
        "app keeps crashing when I open my cart",
        "cannot apply coupon, button not working",
        "the app shows blank screen after the latest update",
        "unable to track my order, map not loading",
        "checkout page freezes every time",
        "app logged me out and OTP is not coming",
        "address not saving in the app",
        "promo code error even though it is valid",
        "app is very slow and keeps showing error 500",
    ],
    "account": [
        "how do I change my phone number on my account",
        "I want to delete my account",
        "cannot log in, forgot password",
        "please update my email id in profile",
        "my account got blocked, why?",
        "how to remove my saved card from the account",
        "I want to merge my two accounts",
        "gold membership not showing in my account",
    ],
    "restaurant_partner": [
        "{restaurant} cancelled my order after 40 minutes",
        "restaurant said item not available after I paid",
        "{restaurant} is charging more than the menu price",
        "food quality from {restaurant} was terrible, stale and cold",
        "restaurant is closed but still showing open in app",
        "found hair in my {dish} from {restaurant}",
        "restaurant packaging was leaking, food spilled",
        "{restaurant} refused to give the bill",
        "portion size of {dish} much smaller than shown",
    ],
}

# ---- Hinglish templates (Hindi in Latin letters) ---------------------------------------------

TEMPLATES_HI: dict[str, list[str]] = {
    "late_delivery": [
        "khana abhi tak nahi aaya, {mins} minute ho gaye",
        "order kab aayega? bahut late ho gaya hai",
        "delivery boy ka phone nahi lag raha, order late hai",
        "{restaurant} se order kiya tha, ab tak nahi pahuncha",
        "bhai order {order_ref} kahan hai? {mins} min se wait kar raha hoon",
        "map pe rider hil hi nahi raha, kitna time lagega",
    ],
    "missing_item": [
        "{side} nahi aaya order ke saath",
        "{dish} ke saath {side} missing hai, refund chahiye",
        "ek item kam aaya hai order {order_ref} mein",
        "bill mein {side} hai par bag mein nahi tha",
        "pura order nahi aaya, aadha saman missing hai",
    ],
    "wrong_item": [
        "galat order aa gaya, maine {dish} manga tha",
        "veg manga tha non veg aa gaya, bahut galat hai",
        "kisi aur ka order mujhe de diya",
        "{restaurant} ne galat khana bhej diya",
        "order {order_ref} mein dusra item aaya hai",
    ],
    "refund": [
        "refund kab milega? Rs {amount} abhi tak nahi aaye",
        "order cancel kiya tha paisa wapas nahi aaya",
        "refund ka status batao order {order_ref}",
        "aapne bola tha 5 din mein refund, ek hafta ho gaya",
        "mera paisa wapas karo please",
    ],
    "payment_failure": [
        "paisa kat gaya but order place nahi hua",
        "UPI se payment kiya, paise kat gaye, order fail",
        "do baar paise kat gaye ek hi order ke",
        "payment fail dikha raha hai par bank se Rs {amount} cut gaye",
    ],
    "app_bug": [
        "app baar baar band ho raha hai",
        "coupon apply nahi ho raha, error aa raha hai",
        "update ke baad app khul hi nahi raha",
        "OTP nahi aa raha login ke liye",
    ],
    "account": [
        "mobile number change karna hai account mein",
        "account delete kaise karu",
        "password bhool gaya, login nahi ho raha",
        "mera account block kyun hua?",
    ],
    "restaurant_partner": [
        "{restaurant} ne order cancel kar diya paise lene ke baad",
        "khana thanda aur basi tha {restaurant} se",
        "restaurant menu se zyada paise le raha hai",
        "{dish} mein baal mila, bahut ganda",
    ],
}

# Short second-issue sentences for multi-issue tickets (~10%).
SECOND_ISSUE_EN: dict[str, str] = {
    "late_delivery": "also it came very late",
    "missing_item": "and one item was missing too",
    "wrong_item": "plus they sent a wrong item",
    "refund": "I want a refund for this",
    "payment_failure": "and my payment also showed failed",
    "app_bug": "and the app is not working properly",
    "account": "also please update my phone number",
    "restaurant_partner": "the restaurant quality is also bad",
}
SECOND_ISSUE_HI: dict[str, str] = {
    "late_delivery": "aur bahut late bhi aaya",
    "missing_item": "aur ek item bhi missing tha",
    "wrong_item": "aur galat item bhi aaya",
    "refund": "refund chahiye iska",
    "payment_failure": "aur payment bhi fail dikha",
    "app_bug": "aur app bhi kaam nahi kar raha",
    "account": "aur mera number bhi update karo",
    "restaurant_partner": "restaurant ka khana bhi kharab tha",
}


@dataclass
class TextBank:
    """Holds the Bitext pools and produces one message per ticket."""

    bitext_pool: dict[str, list[str]] = field(default_factory=dict)
    multi_issue_prob: float = 0.10
    typo_prob: float = 0.20
    phone_prob: float = 0.05
    email_prob: float = 0.02
    order_ref_prob: float = 0.45

    @classmethod
    def from_bitext_csv(cls, path: Path) -> "TextBank":
        pool: dict[str, list[str]] = {}
        with path.open("r", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                category = BITEXT_INTENT_TO_CATEGORY.get(row["intent"])
                if category is None:
                    continue
                pool.setdefault(category, []).append(food_flavour(row["instruction"]))
        return cls(bitext_pool=pool)

    def make_text(
        self,
        rng: np.random.Generator,
        category: str,
        language: str,
        restaurant: str,
        order_id: str,
    ) -> str:
        use_bitext = (
            language != "hi"
            and category in self.bitext_pool
            and rng.random() < BITEXT_SHARE.get(category, 0.0)
        )
        if use_bitext:
            text = str(rng.choice(self.bitext_pool[category]))
        else:
            templates = TEMPLATES_HI if language == "hi" else TEMPLATES_EN
            text = str(rng.choice(templates[category]))
        text = fill_slots(rng, text, restaurant, order_id, self.order_ref_prob)

        if rng.random() < self.multi_issue_prob:
            others = [c for c in TEMPLATES_EN if c != category]
            second = str(rng.choice(others))
            cue = SECOND_ISSUE_HI[second] if language == "hi" else SECOND_ISSUE_EN[second]
            text = f"{text}, {cue}"
        if rng.random() < self.phone_prob:
            text += f". call me on {random_phone(rng)}"
        elif rng.random() < self.email_prob:
            text += f". mail me at {random_email(rng)}"
        if rng.random() < self.typo_prob:
            text = add_typos(rng, text, rate=0.08)
        return text


def food_flavour(text: str) -> str:
    """Swap generic e-commerce words for food-delivery words (case-insensitive)."""
    for pattern, replacement in WORD_SWAPS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def fill_slots(rng: np.random.Generator, text: str, restaurant: str, order_id: str, order_ref_prob: float) -> str:
    """Fill {slots} and Bitext {{placeholders}} with concrete values."""
    # "order {order_ref}" would read "order my order"; the slot itself says "order".
    text = re.sub(r"(?:my )?order \{order_ref\}", "{order_ref}", text)
    if "{order_ref}" in text:
        order_ref = f"order id {order_id}" if rng.random() < order_ref_prob else "my order"
        text = text.replace("{order_ref}", order_ref)
    values = {
        "{{Order Number}}": order_id,
        "{{Account Type}}": str(rng.choice(["gold", "free", "premium"])),
        "{{Account Category}}": str(rng.choice(["gold", "family", "business"])),
        "{{Refund Amount}}": str(int(rng.integers(80, 1200))),
        "{{Currency Symbol}}": "Rs",
        "{restaurant}": restaurant,
        "{dish}": str(rng.choice(DISHES)),
        "{side}": str(rng.choice(SIDES)),
        "{mins}": str(int(rng.choice([25, 30, 40, 45, 50, 60, 75, 90]))),
        "{amount}": str(int(rng.integers(80, 1200))),
    }
    for slot, value in values.items():
        text = text.replace(slot, value)
    # Any Bitext placeholder we did not expect: drop it rather than leave {{...}} in the text.
    return re.sub(r"\{\{[^}]+\}\}", "", text).strip()


def add_typos(rng: np.random.Generator, text: str, rate: float) -> str:
    """Swap two neighbouring letters in about `rate` of the longer words."""
    words = text.split(" ")
    for i, word in enumerate(words):
        if len(word) > 3 and word.isalpha() and rng.random() < rate:
            j = int(rng.integers(0, len(word) - 1))
            words[i] = word[:j] + word[j + 1] + word[j] + word[j + 2 :]
    return " ".join(words)


def random_phone(rng: np.random.Generator) -> str:
    first = int(rng.integers(6, 10))
    rest = "".join(str(int(d)) for d in rng.integers(0, 10, size=9))
    return f"{first}{rest}"


def random_email(rng: np.random.Generator) -> str:
    name = str(rng.choice(["priya", "rahul", "amit", "sneha", "arjun", "neha"]))
    return f"{name}{int(rng.integers(10, 99))}@gmail.com"
