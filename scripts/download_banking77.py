"""Download BANKING77 (W6 benchmark) into data/public/banking77/.

Run:  python scripts/download_banking77.py

Source: github.com/PolyAI-LDN/task-specific-datasets (banking_data/train.csv, test.csv).
Licence: CC BY 4.0. Citation: Casanueva et al. (2020), Efficient Intent Detection with Dual
Sentence Encoders, NLP4ConvAI. Files that already exist are not downloaded again; the SHA-256
of each file is printed for data/SOURCES.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.download_data import PUBLIC, download, report  # noqa: E402

BASE = "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/"


def main() -> int:
    for name in ("train.csv", "test.csv"):
        report(download(BASE + name, PUBLIC / "banking77" / name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
