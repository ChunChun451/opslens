"""Every number we say out loud must exist in the CURRENT results (CLAUDE.md: "never show a
number we did not compute").

What it checks: each decimal number (2.20, 0.976, −3.31) and each number with a thousands
separator (1,007) in the rehearsal documents must match a value in eval/results.json at the
precision written, or the same value ×100 (fractions written as percents). Results stored per
seed count as their mean. Limit: a wrong number can still match some other value by chance
(measured: 45% of random one-decimal and 25% of three-decimal numbers do), so this is a
safety net, not a proof.

Why this design: Claude 2 found on 17 Oct that JUDGE_QA still quoted policy v1 (5.08%, P99 474
min) after v3 shipped — numbers that still exist in results.json, but only in the history
record of v1. So the history records of earlier versions are NOT accepted as a source. Whole
small numbers (5 seeds, 14 days) are not checked: they are counts, not results.

Example: "OpsLens 2.20% vs 6.82%" passes (sim.policies.*.kpis.turnaround.breach_pct rounds to
2.20 and 6.82); "FIFO breaches 53.6%" failed, because the stress result 53.5456 rounds to 53.5.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["docs/JUDGE_QA.md", "docs/DEMO_SCRIPT.md", "docs/BOT_QA.md"]  # BOT_QA: the bot's extra answers
# Records of earlier policy versions: true numbers, but not ones to quote as current.
HISTORY = ("details.v1_record", "details.v2_record", "details.design_v2")
# Bulk data nobody quotes (single seeds, replay frames, chart points). Leaving them out matters:
# with all ~7,600 values, 199 of 200 random one-decimal numbers matched something by chance;
# with these out, 55% of random one-decimal numbers are caught.
BULK = re.compile(r"per_seed|replay|horizon|series|confusion|assignments|alerts_used|step_seconds|"
                  r"sensitivity|bottlenecks|clusters|examples|shown_days\[\d+\]\.incidents")
NAMES_A_VERSION = re.compile(r"\bv[12]\b")  # a line about v1 or v2 may quote their history records
# Numbers that come from somewhere other than results.json, each with its source.
OTHER_SOURCES = {
    "24,918": "size of the UCI incident log (data/SOURCES.md)",
    "10.97": "Erlang-C check, simulator average wait (tests/test_simulate.py)",
    "10.79": "Erlang-C check, formula average wait (tests/test_simulate.py)",
    "36.6": "UCI breach rate, computed live by /api/upload (tests/test_upload.py)",
}
NUMBER = re.compile(r"(?<![\w.])[−-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])[−-]?\d+\.\d+")


def result_values(with_history: bool = False) -> list[float]:
    results = json.loads((ROOT / "eval" / "results.json").read_text(encoding="utf-8"))
    values: list[float] = []

    def walk(node, path: str) -> None:
        if path.startswith(HISTORY) and not with_history:
            return
        if path.endswith("per_seed") and isinstance(node, dict):
            add_means(node)  # results kept per seed are quoted as their mean over seeds
        if BULK.search(path):
            return
        if isinstance(node, dict):
            for key, child in node.items():
                walk(child, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for i, child in enumerate(node):
                walk(child, f"{path}[{i}]")
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            values.append(float(node))

    def add_means(per_seed: dict) -> None:
        for runs in per_seed.values():
            if isinstance(runs, list) and runs and isinstance(runs[0], dict):
                for key in runs[0]:
                    numbers = [run[key] for run in runs if isinstance(run.get(key), (int, float))]
                    if numbers:
                        values.append(sum(numbers) / len(numbers))

    walk(results, "")
    return values


def is_computed(token: str, values: list[float]) -> bool:
    text = token.replace("−", "-").replace(",", "")
    written = abs(float(text))
    digits = len(text.split(".")[1]) if "." in text else 0
    for v in values:
        for candidate in (abs(v), abs(v) * 100):
            if round(candidate, digits) == written:
                return True
    return False


def test_every_number_in_the_rehearsal_docs_is_computed() -> None:
    current, with_history = result_values(), result_values(with_history=True)
    orphans = []
    for doc in DOCS:
        for line_no, line in enumerate((ROOT / doc).read_text(encoding="utf-8").splitlines(), 1):
            values = with_history if NAMES_A_VERSION.search(line) else current
            for token in NUMBER.findall(line):
                if token.lstrip("−-") not in OTHER_SOURCES and not is_computed(token, values):
                    orphans.append(f"{doc}:{line_no}: {token}")
    assert not orphans, "numbers not in the current results.json:\n" + "\n".join(orphans)
