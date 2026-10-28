import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["server/answers.md", "README.md"]
HISTORY = ("details.v1_record", "details.v2_record", "details.design_v2", "details.design_v3", "details.v3_record",
           "details.v3_before_sim_fix", "details.design_v4", "details.design_v5", "details.confirm_v5",
           "details.sealed_world_5151_v3", "details.tuning", "details.challengers", "earlier_floor", "worlds",
           "v6", "staffing_opt", "sealed_world.", "sealed_world_rerun")
BULK = re.compile(r"per_seed|replay|horizon|series|confusion|assignments|alerts_used|step_seconds|"
                  r"sensitivity|bottlenecks|clusters|examples|shown_days\[\d+\]\.incidents|"
                  r"worlds\[\d+\]\.params|diagnosis\.worlds|twin\.validation\.grid|\.teams\.|next_week")
NAMES_A_VERSION = re.compile(r"\bv[1-6]\b|earlier floor", re.IGNORECASE)
OTHER_SOURCES = {
    "24,918": "size of the UCI incident log (data/SOURCES.md)",
    "10.97": "Erlang-C check, simulator average wait (tests/test_simulate.py)",
    "10.79": "Erlang-C check, formula average wait (tests/test_simulate.py)",
    "36.6": "UCI breach rate, computed live by /api/upload (tests/test_upload.py)",
    "4.0": "the licence name CC BY 4.0 (data/SOURCES.md), not a result",
    "1,000": "the DEV_103 problem statement's own example (tickets a day), quoted in README.md",
}
NUMBER = re.compile(r"(?<![\w.])[−-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])[−-]?\d+\.\d+")


def result_values(with_history: bool = False) -> list[float]:
    results = json.loads((ROOT / "eval" / "results.json").read_text(encoding="utf-8"))
    values: list[float] = []

    def walk(node, path: str) -> None:
        if path.startswith(HISTORY) and not with_history:
            return
        if path.endswith("per_seed") and isinstance(node, dict):
            add_means(node)
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
