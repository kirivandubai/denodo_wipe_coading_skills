"""The JSON document every command prints — one per invocation, on stdout."""

from __future__ import annotations

import datetime as dt
import decimal
import json
from typing import Any

from .profiles import Profile


def envelope(ok: bool, profile: Profile | None, command: str, **fields: Any) -> dict:
    """Common shape: ``ok``, ``command``, ``env`` (never the password), then fields."""
    env = None
    if profile is not None:
        env = {
            "name": profile.name,
            "production": profile.production,
            "transport": profile.transport,
            "database": profile.database,
        }
    doc: dict[str, Any] = {"ok": ok, "command": command, "env": env}
    doc.update(fields)
    return doc


def rows_payload(columns: list[str] | None, rows: list | None, max_rows: int) -> dict:
    """Result set limited to ``max_rows`` rows; ``row_count`` is the full count."""
    if rows is None:
        return {"columns": columns, "rows": None, "row_count": None, "truncated": False}
    rows = [list(r) for r in rows]
    return {
        "columns": columns,
        "rows": rows[:max_rows],
        "row_count": len(rows),
        "truncated": len(rows) > max_rows,
    }


def _default(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    return str(value)


def to_json(doc: Any) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2, default=_default)
