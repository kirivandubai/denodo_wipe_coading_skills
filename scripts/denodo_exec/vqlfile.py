"""A workspace's VQL file: read once, planned, judged by the rule of scope, applied, recorded.

A workspace is a folder the agent writes with its own file tool (its numbered VQL files under
``denodo/``) and a ledger the tool server alone writes. The file is the agent's to rewrite at any
moment, so its bytes are read once and a private copy of them is what the planner plans, the
rule judges, denodo_cli runs and the ledger's ``vql_sha`` names: a file rewritten between the plan
and the run would otherwise run unjudged.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any, Protocol

from denodo_exec.client import Denodo
from denodo_exec.errors import Refused
from denodo_exec.files import append_jsonl
from denodo_exec.ledger import LEDGER_ACTIONS, live_objects
from denodo_exec.scope import Rule, ScopeLike, Wording, judge, refusal

VQL_FILE = re.compile(r"denodo/[0-9]{2}-[a-z0-9-]+\.vql")
# Rows of a check's answer kept in what it returns: enough to read a value off, not a table.
HELD_ROWS = 20


class Workspace(Protocol):
    """What the layer needs of an agent's workspace: a file by its relative path, never one
    outside the folder (the agent hands the path), and where its ledger is."""

    def path(self, relative: str) -> Path: ...

    @property
    def ledger(self) -> Path: ...


def vql_file(workspace: Workspace, relative: str, wording: Wording = Wording()) -> Path:
    """A numbered VQL file of the workspace, `denodo/NN-name.vql`, that is there."""
    if not VQL_FILE.fullmatch(relative or ""):
        raise Refused(f"{relative!r} is not a {wording.unit} VQL file: denodo/NN-name.vql")
    path = workspace.path(relative)
    if not path.is_file():
        raise Refused(f"{relative} is not there")
    return path


@contextlib.contextmanager
def read_once(workspace: Workspace, denodo: Denodo, relative: str,
              wording: Wording = Wording()) -> Iterator[tuple[Path, str, str]]:
    """The file's bytes read once: a private copy of them, their text and their digest. The
    planner, the rule of scope, the run and the ledger's vql_sha all see these bytes."""
    data = vql_file(workspace, relative, wording).read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused(f"{relative} is not UTF-8 text") from None
    # denodo_cli reads the file with universal newlines: a carriage return alone would end a
    # `--` comment for it and not for split_vql, and what follows would run unjudged.
    if "\r" in text.replace("\r\n", "\n"):
        raise Refused(f"{relative} holds a carriage return without a line feed: lines end in "
                      "\\n or \\r\\n")
    copy = denodo.hold(data)
    try:
        yield copy, text, f"sha256:{hashlib.sha256(data).hexdigest()}"
    finally:
        with contextlib.suppress(FileNotFoundError):
            copy.unlink()


def judged_plan(workspace: Workspace, denodo: Denodo, relative: str, copy: Path, text: str, *,
                scope: ScopeLike, make_rule: Callable[[], Rule] | None = None,
                wording: Wording = Wording()) -> dict[str, Any]:
    """The plan of a copy `read_once` made, every statement judged. `make_rule` makes the
    agent's own rule for this one file (a rule may remember what the file's statements make)."""
    doc = denodo.plan(copy, scope.database)
    judged = judge(doc, text, scope=scope, live=live_objects(workspace.ledger),
                   rule=make_rule() if make_rule is not None else None, wording=wording)
    return {"file": relative, "database": scope.database, "statements": judged,
            "refused": refusal(judged, wording), "server": doc.get("env")}


def plan(workspace: Workspace, denodo: Denodo, relative: str, *, scope: ScopeLike,
         make_rule: Callable[[], Rule] | None = None,
         wording: Wording = Wording()) -> dict[str, Any]:
    """What `relative` would do, statement by statement, and whether the rules let each
    through -- nothing runs."""
    with read_once(workspace, denodo, relative, wording) as (copy, text, _):
        return judged_plan(workspace, denodo, relative, copy, text, scope=scope,
                           make_rule=make_rule, wording=wording)


def apply(workspace: Workspace, denodo: Denodo, relative: str, *, scope: ScopeLike, at: str,
          make_rule: Callable[[], Rule] | None = None,
          wording: Wording = Wording()) -> dict[str, Any]:
    """`relative` run when every statement passes the rules; each object it made, replaced or
    dropped a line of the ledger, and the file's bytes an `applied` line when all of it ran.

    The ledger is written after the run, from the run's answer: a statement the server refused
    made nothing, and one it ran is recorded even when a later one failed."""
    with read_once(workspace, denodo, relative, wording) as (copy, text, sha):
        planned = judged_plan(workspace, denodo, relative, copy, text, scope=scope,
                              make_rule=make_rule, wording=wording)
        if planned["refused"]:
            raise Refused(planned["refused"])
        doc = denodo.run_file(copy, scope.database)
    ran = {row.get("index"): row for row in doc.get("statements") or []}
    for row in planned["statements"]:
        result = ran.get(row["index"])
        if not result or not result.get("ok") or row["action"] not in LEDGER_ACTIONS:
            continue
        action = "replace" if row["action"] == "create" and row["exists"] else row["action"]
        found = row["object"]
        append_jsonl(workspace.ledger, {
            "at": at, "action": action, "type": found["type"],
            "database": found.get("database") or scope.database, "name": found["name"],
            "file": relative, "vql_sha": sha, "statement": row["statement"]})
    if doc.get("ok"):
        append_jsonl(workspace.ledger, {"at": at, "action": "applied", "file": relative,
                                        "vql_sha": sha})
    return {"file": relative, "ok": bool(doc.get("ok")), "failed_at": doc.get("failed_at"),
            "statements": [brief(row) for row in doc.get("statements") or []]}


def brief(row: Mapping[str, Any]) -> dict[str, Any]:
    """A statement of `vql run`'s answer as a tool answers it: its error's message alone."""
    error = row.get("error") or None
    return {"index": row.get("index"), "statement": row.get("statement"), "ok": row.get("ok"),
            "error": error.get("message") if isinstance(error, dict) else error,
            "columns": row.get("columns"), "rows": row.get("rows"),
            "row_count": row.get("row_count")}


def held(name: str, vql: str, row: Mapping[str, Any],
         expect: Mapping[str, Any]) -> dict[str, Any]:
    """A check's answer held to what it expects: the columns, at least so many rows, values at
    a row and a column."""
    failures = []
    columns = row.get("columns") or []
    rows = row.get("rows") or []
    if not row.get("ok"):
        error = row.get("error")
        failures.append(f"the server refused: "
                        f"{error.get('message') if isinstance(error, dict) else error}")
    wanted = expect.get("columns") or []
    missing = [column for column in wanted if column not in columns]
    if missing:
        failures.append(f"columns missing: {', '.join(missing)}")
    least = expect.get("min_rows")
    count = row.get("row_count") or 0
    if isinstance(least, int) and count < least:
        failures.append(f"{count} rows, fewer than {least}")
    for value in expect.get("values") or []:
        at, column, equals = value.get("row", 0), value.get("column"), value.get("equals")
        if column not in columns or at >= len(rows):
            failures.append(f"no row {at} column {column}")
            continue
        got = rows[at][columns.index(column)]
        if str(got) != str(equals):
            failures.append(f"row {at} {column} is {got!r}, not {equals!r}")
    return {"name": name, "vql": vql, "ok": not failures, "failures": failures,
            "columns": columns, "rows": rows[:HELD_ROWS], "row_count": count}
