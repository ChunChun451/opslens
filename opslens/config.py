from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def load_config(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / f"{name}.yaml"
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping at the top level")
    return data


def load_env_file(path: Path | None = None) -> dict[str, str]:
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
        if key not in os.environ and value:
            os.environ[key] = value
    return found


def project_path(relative: str) -> Path:
    path = Path(relative)
    return path if path.is_absolute() else PROJECT_ROOT / path
