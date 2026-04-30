from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VAR_DIR = PROJECT_ROOT / "var"
PLANS_DIR = VAR_DIR / "plans"
TICKETS_DIR = VAR_DIR / "tickets"
REVIEWS_DIR = VAR_DIR / "reviews"
AUDIT_FILE = VAR_DIR / "audit.jsonl"
LATEST_SNAPSHOT_FILE = VAR_DIR / "latest_snapshot.json"


def ensure_var_dirs() -> None:
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    TICKETS_DIR.mkdir(parents=True, exist_ok=True)
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    VAR_DIR.mkdir(parents=True, exist_ok=True)


def load_config(mode: str, config_path: str | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else PROJECT_ROOT / "config" / f"{mode}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
    else:
        data = _parse_minimal_yaml(text)
    data.setdefault("mode", mode)
    return data


def _parse_scalar(value: str) -> Any:
    value = value.strip().strip('"').strip("'")
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in {"null", "none", ""}:
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _parse_minimal_yaml(text: str) -> dict[str, Any]:
    # Minimal parser for the simple nested config files in this project.
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        parts = line.strip().split(":", 1)
        if len(parts) != 2:
            continue
        key, value = parts[0].strip(), parts[1].strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value)
    return root


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False))
