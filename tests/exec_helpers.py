"""What the tests of denodo_exec share: denodo_cli faked as the process it is (its answers in the
shapes `vql plan`, `vql run` and `env check` print), a plan entry, and a workspace. Not a test
module."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from denodo_exec.client import Denodo, Ran
from denodo_exec.profile import derive_profile

AT = "2026-10-09T10:05:07.000Z"
DB = "demo_20261009_1405_acme"
PASSWORD = "s3cret-pass-42"
PROFILES = f"""
[dev]
host = "localhost"
port = 9996
database = "admin"
user = "admin"
password = "{PASSWORD}"
production = false
marketplace_url = "http://localhost:9090/denodo-data-catalog"

[prod]
host = "denodo.bank.example"
user = "svc"
password = "x"
production = true
"""


def env() -> dict[str, Any]:
    return {"name": "dev", "production": False, "transport": "vql_psycopg2", "database": DB}


def entry(index: int, action: str, otype: str | None, name: str | None, *, exists: Any = False,
          database: str | None = None, destructive: str | None = None,
          statement: str = "...") -> dict[str, Any]:
    """One statement of `vql plan`'s answer."""
    found = None if otype is None else {"type": otype, "database": database, "name": name}
    return {"index": index, "statement": statement, "action": action, "object": found,
            "exists": exists, "own": not exists, "destructive": destructive,
            "needs_yes": False, "why": "", "conditions": []}


class FakeCli:
    """denodo_cli by its argv: `plan` answers the statements it was given, `run` runs them."""

    def __init__(self, plan: list[dict[str, Any]] | None = None, run_ok: bool = True,
                 rows: list[list[Any]] | None = None, columns: list[str] | None = None) -> None:
        self.plan_entries = plan or []
        self.run_ok = run_ok
        self.rows = rows if rows is not None else [[1]]
        self.columns = columns or ["n"]
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str]] = []

    def __call__(self, argv, *, timeout, env=None) -> Ran:
        self.calls.append(list(argv))
        self.envs.append(dict(env or {}))
        args = list(argv[3:])
        if args[:2] == ["vql", "plan"]:
            doc = {"ok": True, "command": "vql plan", "env": globals()["env"](),
                   "statements": self.plan_entries}
        elif args[:2] == ["vql", "run"]:
            count = max(len(self.plan_entries), 1)
            doc = {"ok": self.run_ok, "command": "vql run", "env": globals()["env"](),
                   "failed_at": None if self.run_ok else 0, "statements": [
                       {"index": i, "statement": "...", "destructive": None, "ok": self.run_ok,
                        "error": None if self.run_ok else {"message": "Syntax error"},
                        "columns": self.columns, "rows": self.rows,
                        "row_count": len(self.rows), "truncated": False}
                       for i in range(count)]}
        elif args[:2] == ["env", "check"]:
            doc = {"ok": True, "command": "env check", "env": globals()["env"](),
                   "vdp": {"ok": True, "server_version": "9.5.1", "admin": True,
                           "impersonation": True}}
        else:
            raise AssertionError(args)
        return Ran(0 if doc["ok"] else 1, json.dumps(doc, indent=2), "")


@dataclass(frozen=True)
class Space:
    """A workspace as a tool server keeps one: its folder, and a ledger outside it."""

    root: Path
    state: Path

    def path(self, relative: str) -> Path:
        found = self.root.joinpath(*relative.split("/"))
        if ".." in relative.split("/") or not found.resolve().is_relative_to(self.root.resolve()):
            raise AssertionError(relative)
        return found

    @property
    def ledger(self) -> Path:
        return self.state / "ledger.jsonl"


def space(tmp: Path) -> Space:
    root = tmp / "out" / "t-1" / "20261009-1405-acme"
    (root / "denodo").mkdir(parents=True)
    return Space(root, tmp / "state" / root.name)


def profile_and_file(tmp: Path):
    source = tmp / "profiles.toml"
    source.write_text(PROFILES, encoding="utf-8")
    return derive_profile(source, "dev", "host.docker.internal", tmp / "run")


def client(tmp: Path, cli: Any) -> Denodo:
    profile, path = profile_and_file(tmp)
    return Denodo(profile, path, cli, python="/app/.venv/bin/python")


def nothing(entry: Any, statement: str) -> None:
    """No rule beside the rule of scope."""
    return None
