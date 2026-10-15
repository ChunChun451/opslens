"""Find sub-issues inside each category and let the LLM name them.

What it does: inside each category (e.g. refund), group similar messages with TF-IDF + KMeans.
For each group, the LLM reads 10 typical (masked) messages and the group's top words and
returns a short name and a likely root cause ("Refund promised but not received").

Why this design:
- KMeans on TF-IDF is fast, needs no GPU, and the owner can explain it in one sentence:
  "messages that use the same words end up in the same group".
- The number of groups k (3 to 6) is chosen per category by the silhouette score: the k whose
  groups are most clearly separated.
- The LLM only names groups; it never decides which ticket is in which group. Names may not
  contain digits (CLAUDE.md: the LLM never writes a number); a bad name falls back to the
  group's top words.

Example: refund tickets → k = 4 groups; group 2's top words "cancelled, returned, money,
cancel order" → LLM name "Refund missing after cancellation", root cause "refund not
triggered when the order is cancelled".
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score

from opslens.llm.base import LLMUnavailable
from opslens.llm.client import LLMClient
from opslens.privacy import mask_pii

log = logging.getLogger(__name__)

K_CHOICES = [3, 4, 5, 6]
SAMPLE_FOR_K = 3000
NAMING_SYSTEM = (
    "You name groups of customer-support messages for an operations dashboard. "
    'Reply with JSON only: {"name": <at most 6 words>, "root_cause": <at most 12 words>}. '
    "Do not use digits."
)


@dataclass
class CategoryClusters:
    category: str
    vectorizer: TfidfVectorizer
    kmeans: KMeans
    names: dict[int, str] = field(default_factory=dict)
    root_causes: dict[int, str] = field(default_factory=dict)
    top_terms: dict[int, list[str]] = field(default_factory=dict)
    sizes: dict[int, int] = field(default_factory=dict)
    examples: dict[int, list[str]] = field(default_factory=dict)


def clean_texts(texts: pd.Series) -> list[str]:
    return [mask_pii(str(t)).text.lower() for t in texts.fillna("")]


def choose_k(matrix, seed: int = 0) -> int:
    """The k with the best silhouette score on a sample (higher = clearer groups)."""
    rng = np.random.default_rng(seed)
    rows = rng.choice(matrix.shape[0], size=min(SAMPLE_FOR_K, matrix.shape[0]), replace=False)
    sample = matrix[rows]
    scores = {}
    for k in K_CHOICES:
        if sample.shape[0] <= k:
            continue
        labels = KMeans(n_clusters=k, n_init=5, random_state=seed).fit_predict(sample)
        scores[k] = silhouette_score(sample, labels, metric="cosine")
    return max(scores, key=scores.get) if scores else K_CHOICES[0]


def fit_category(category: str, texts: pd.Series, seed: int = 0) -> CategoryClusters:
    docs = clean_texts(texts)
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_df=0.6, sublinear_tf=True,
                                 token_pattern=r"(?u)\b[a-z][a-z]+\b")
    matrix = vectorizer.fit_transform(docs)
    k = choose_k(matrix, seed)
    kmeans = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(matrix)
    result = CategoryClusters(category, vectorizer, kmeans)
    terms = np.asarray(vectorizer.get_feature_names_out())
    distances = kmeans.transform(matrix)
    for c in range(k):
        members = np.nonzero(kmeans.labels_ == c)[0]
        result.sizes[c] = int(len(members))
        result.top_terms[c] = terms[np.argsort(kmeans.cluster_centers_[c])[::-1][:6]].tolist()
        closest = members[np.argsort(distances[members, c])[:10]]
        result.examples[c] = [docs[i] for i in closest]
    return result


def name_clusters(client: LLMClient | None, clusters: CategoryClusters) -> None:
    """Ask the LLM for a name and root cause per group; fall back to top words."""
    for c, examples in clusters.examples.items():
        fallback = ", ".join(clusters.top_terms[c][:3])
        name, cause = fallback, ""
        if client is not None:
            prompt = (
                f"Category: {clusters.category}. Most typical words: {', '.join(clusters.top_terms[c])}.\n"
                "Ten typical messages:\n" + "\n".join(f"- {e}" for e in examples)
            )
            try:
                data = client.ask_json("name_cluster", NAMING_SYSTEM, prompt).data
                raw_name = str(data.get("name", "")).strip() if isinstance(data, dict) else ""
                raw_cause = str(data.get("root_cause", "")).strip() if isinstance(data, dict) else ""
                if raw_name and not re.search(r"\d", raw_name + raw_cause):
                    name, cause = raw_name[:60], raw_cause[:100]
            except LLMUnavailable as exc:
                log.warning("cluster naming fell back to top words: %s", exc)
        clusters.names[c] = name
        clusters.root_causes[c] = cause


def assign(clusters: CategoryClusters, texts: pd.Series) -> np.ndarray:
    """Group number for new tickets of this category."""
    return clusters.kmeans.predict(clusters.vectorizer.transform(clean_texts(texts)))
