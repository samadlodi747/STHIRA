from __future__ import annotations

from datetime import datetime
from typing import Any


def get_path(source: dict[str, Any], path: str, default: Any = None) -> Any:
    node: Any = source
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def format_number(value: Any, digits: int = 3, suffix: str = "") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number:.{digits}f}{suffix}"


def format_text(value: Any, default: str = "-") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def report_filename(prefix: str, created_at: datetime) -> str:
    return f"{prefix}_{created_at:%Y-%m-%d}.pdf"
