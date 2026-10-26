from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.download_data import PUBLIC, download, report

BASE = "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/"


def main() -> int:
    for name in ("train.csv", "test.csv"):
        report(download(BASE + name, PUBLIC / "banking77" / name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
