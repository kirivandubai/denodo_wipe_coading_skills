"""A workspace's ledger: one JSONL line per object it created, replaced, altered or dropped.

The ledger is the only thing the rule of scope trusts to say an object is the workspace's own, so
it lives where only the tool server writes -- never in a folder the agent's own file tool reaches,
where a forged line would widen what a workspace may replace or drop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from denodo_exec.files import read_jsonl

LEDGER_ACTIONS = ("create", "replace", "alter", "drop")


def ledger_key(kind: str, database: str, name: str) -> tuple[str, str, str]:
    """An object by its type, database and name; Denodo's names are not case-sensitive."""
    return (kind, database.lower(), name.lower())


def live_objects(ledger: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    """The objects the ledger's workspace made and has not dropped, by (type, database, name)."""
    live: dict[tuple[str, str, str], dict[str, Any]] = {}
    for line in read_jsonl(ledger):
        if line.get("action") not in LEDGER_ACTIONS:
            continue
        key = ledger_key(line["type"], line["database"], line["name"])
        if line["action"] == "drop":
            live.pop(key, None)
        else:
            live[key] = line
    return live
