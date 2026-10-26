from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from opslens.llm.base import LLMUnavailable
from opslens.llm.client import LLMClient
from opslens.privacy import mask_pii

log = logging.getLogger(__name__)

CATEGORIES = [
    "late_delivery", "missing_item", "wrong_item", "refund",
    "payment_failure", "app_bug", "account", "restaurant_partner",
]
CATEGORY_HELP = {
    "late_delivery": "the order is late or has not arrived yet; rider not moving or not reachable",
    "missing_item": "an item from the order did not arrive (rest of the order did)",
    "wrong_item": "received a different dish or someone else's order",
    "refund": "asking for a refund, refund status or money back",
    "payment_failure": "payment failed, money debited without an order, charged twice",
    "app_bug": "the app crashes or a feature fails: coupon, OTP, checkout, tracking, address",
    "account": "profile, login, password, phone or email change, delete or blocked account",
    "restaurant_partner": "restaurant behaviour or food quality: cancelled after payment, overcharged, stale, hygiene",
}
TEAM_OF = {
    "late_delivery": "A", "refund": "B", "payment_failure": "B", "missing_item": "C",
    "wrong_item": "C", "account": "D", "app_bug": "D", "restaurant_partner": "D",
}
BATCH_SIZE = 25


def model_frame(df: pd.DataFrame) -> pd.DataFrame:
    text = df["text"].fillna("").map(lambda t: mask_pii(str(t)).text.lower())
    pick = df["selected_category"].fillna("none").astype(str)
    channel = df["channel"].fillna("none").astype(str)
    return pd.DataFrame({"text": text.to_numpy(), "pick": pick.to_numpy(), "channel": channel.to_numpy(),
                         "pick_channel": (pick + "|" + channel).to_numpy()})


def build_local_model() -> Pipeline:
    features = ColumnTransformer([
        ("words", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True,
                                  token_pattern=r"(?u)\b\w+\b"), "text"),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3,
                                  sublinear_tf=True, max_features=150_000), "text"),
        ("menu", OneHotEncoder(handle_unknown="ignore"), ["pick", "channel", "pick_channel"]),
    ])
    return Pipeline([("features", features), ("clf", LogisticRegression(C=4.0, max_iter=3000))])


def train_local(train: pd.DataFrame) -> CalibratedClassifierCV:
    model = CalibratedClassifierCV(build_local_model(), method="isotonic", cv=3)
    model.fit(model_frame(train), train["final_category"].astype(str))
    return model


def predict_local(model: CalibratedClassifierCV, df: pd.DataFrame) -> pd.DataFrame:
    proba = model.predict_proba(model_frame(df))
    classes = np.asarray(model.classes_)
    best = proba.argmax(axis=1)
    return pd.DataFrame({
        "ticket_id": df["ticket_id"].to_numpy(),
        "pred_local": classes[best],
        "conf_local": proba[np.arange(len(df)), best],
    })


SYSTEM_PROMPT = (
    "You classify customer-support tickets of an Indian food-delivery app.\n"
    "Categories:\n"
    + "\n".join(f"- {c}: {h}" for c, h in CATEGORY_HELP.items())
    + "\nTickets may be English or Hinglish (Hindi in Latin letters), have typos, or mention several "
    "issues: choose the MAIN issue the customer needs solved. Personal data is masked as [PHONE], "
    "[ORDER_ID] etc. The customer's menu choice is only a hint; for phone (IVR) tickets it is often wrong.\n"
    'Reply with JSON only: {"results": [{"id": <ticket number>, "category": <one category>, '
    '"root_cause": <3 to 6 words, no digits>}]} with exactly one entry per ticket.'
)


@dataclass
class LLMLabel:
    category: str
    root_cause: str


def batch_prompt(rows: list[tuple[int, str, str, str]]) -> str:
    lines = [f"{i}. {text} (menu choice: {pick}; channel: {channel})" for i, text, pick, channel in rows]
    return "Tickets:\n" + "\n".join(lines)


def _parse_batch(data: object, expected: set[int]) -> dict[int, LLMLabel]:
    found: dict[int, LLMLabel] = {}
    items = data.get("results", []) if isinstance(data, dict) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            item_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        category = str(item.get("category", "")).strip().lower()
        if item_id in expected and category in CATEGORIES:
            cause = re.sub(r"\d", "", str(item.get("root_cause", ""))).strip()[:60]
            found[item_id] = LLMLabel(category, cause)
    return found


def classify_with_llm(client: LLMClient, df: pd.DataFrame, task: str = "classify") -> dict[str, LLMLabel]:
    labels: dict[str, LLMLabel] = {}
    rows = list(df[["ticket_id", "text", "selected_category", "channel"]].itertuples(index=False))
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        pending = {k + 1: r for k, r in enumerate(batch)}
        for attempt in range(2):
            if not pending:
                break
            prompt = batch_prompt([(i, str(r.text), str(r.selected_category), str(r.channel)) for i, r in pending.items()])
            try:
                result = client.ask_json(task, SYSTEM_PROMPT, prompt)
            except LLMUnavailable as exc:
                log.warning("LLM unavailable for batch at %d: %s", start, exc)
                break
            answered = _parse_batch(result.data, set(pending))
            for i, label in answered.items():
                labels[pending[i].ticket_id] = label
            pending = {i: r for i, r in pending.items() if i not in answered}
    return labels


def cascade(local: pd.DataFrame, llm_labels: dict[str, LLMLabel], threshold: float) -> pd.DataFrame:
    out = local.copy()
    unsure = out["conf_local"] < threshold
    llm_cat = out["ticket_id"].map(lambda t: llm_labels[t].category if t in llm_labels else None)
    use_llm = unsure & llm_cat.notna()
    out["pred_final"] = np.where(use_llm, llm_cat, out["pred_local"])
    out["source"] = np.where(use_llm, "llm", np.where(unsure, "local_fallback", "local"))
    out["root_cause"] = out["ticket_id"].map(lambda t: llm_labels[t].root_cause if t in llm_labels else "")
    return out


def choose_threshold(local: pd.DataFrame, truth: pd.Series, llm_labels: dict[str, LLMLabel],
                     candidates: list[float], max_escalated_pct: float) -> tuple[float, pd.DataFrame]:
    rows = []
    for threshold in candidates:
        pred = cascade(local, llm_labels, threshold)
        escalated = 100.0 * float((pred["conf_local"] < threshold).mean())
        accuracy = float((pred["pred_final"].to_numpy() == truth.to_numpy()).mean())
        rows.append({"threshold": threshold, "escalated_pct": escalated, "accuracy": accuracy})
    table = pd.DataFrame(rows)
    allowed = table[table["escalated_pct"] <= max_escalated_pct]
    best = allowed.sort_values(["accuracy", "threshold"], ascending=[False, True]).iloc[0]
    return float(best["threshold"]), table


def misrouted_per_100(categories: pd.Series, truth: pd.Series) -> float:
    return 100.0 * float((categories.map(TEAM_OF).to_numpy() != truth.map(TEAM_OF).to_numpy()).mean())
