"""Load YAML config files and the .env secrets file.

Why this design:
- Every tunable number lives in `config/*.yaml`, never hard-coded in a module, so a judge
  can ask "where does 1.6 come from?" and we open one file.
- We read `.env` with our own 15-line function instead of adding the python-dotenv
  dependency. Keys already set in the real environment win over the file.

Example:
    >>> sla = load_config("sla")
    >>> sla["sla_minutes"]["P1"]
    60
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# The project root is the folder that holds CLAUDE.md (one level above this package).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def load_config(name: str) -> dict[str, Any]:
    """Read `config/<name>.yaml` and return it as a dict."""
    path = CONFIG_DIR / f"{name}.yaml"
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping at the top level")
    return data


def load_env_file(path: Path | None = None) -> dict[str, str]:
    """Read KEY=VALUE lines from `.env` into os.environ (without overwriting).

    Returns the keys that were found in the file (values included), so a caller can
    check what is configured. Blank lines and lines starting with # are skipped.
    """
    env_path = path or (PROJECT_ROOT / ".env")
    found: dict[str, str] = {}
    if not env_path.exists():
        return found
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        found[key] = value
        # A real environment variable beats the file (useful in CI and tests).
        if key not in os.environ and value:
            os.environ[key] = value
    return found


def project_path(relative: str) -> Path:
    """Turn a path from a config file (relative to the project root) into an absolute path."""
    path = Path(relative)
    return path if path.is_absolute() else PROJECT_ROOT / path
