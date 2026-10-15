"""Download the two public datasets into data/public/ (see data/SOURCES.md for licences).

Run:  mingw32-make data

1. Bitext customer-support dataset (CSV, ~19 MB) -> data/public/bitext/
2. UCI incident management event log (ZIP ~2.3 MB, CSV ~44 MB) -> data/public/uci_incidents/

Files that already exist are not downloaded again. The SHA-256 of each file is printed
so we can record it in data/SOURCES.md and notice if a source ever changes.
Standard library only (urllib, zipfile, hashlib).
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "data" / "public"

BITEXT_URL = (
    "https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset/"
    "resolve/main/Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv"
)
UCI_URL = "https://archive.ics.uci.edu/static/public/498/incident+management+process+enriched+event+log.zip"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, target: Path) -> Path:
    """Download `url` to `target` unless it is already there."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        print(f"exists   {target.relative_to(ROOT)}")
        return target
    print(f"download {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "opslens-data-script"})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as out:
        while True:
            block = response.read(1 << 20)
            if not block:
                break
            out.write(block)
    return target


def extract_zip(zip_path: Path, folder: Path) -> list[Path]:
    """Extract only plain files from the zip, refusing any path that escapes `folder`."""
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            target = (folder / Path(member.filename).name).resolve()
            if folder.resolve() not in target.parents:
                raise ValueError(f"unsafe path in zip: {member.filename}")
            if not target.exists():
                with archive.open(member) as src, target.open("wb") as dst:
                    dst.write(src.read())
            extracted.append(target)
    return extracted


def report(path: Path) -> None:
    size_mb = path.stat().st_size / 1_000_000
    print(f"  {path.relative_to(ROOT)}  {size_mb:.1f} MB  sha256={sha256_of(path)}")


def main() -> int:
    bitext = download(BITEXT_URL, PUBLIC / "bitext" / "bitext_customer_support_27k_v11.csv")
    report(bitext)

    uci_dir = PUBLIC / "uci_incidents"
    uci_zip = download(UCI_URL, uci_dir / "incident_event_log.zip")
    report(uci_zip)
    for path in extract_zip(uci_zip, uci_dir):
        report(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
