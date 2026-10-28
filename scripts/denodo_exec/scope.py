"""The rule of scope, read off denodo_cli's plan: which planned statement is the agent's to run.

A workspace has one database, and inside it optionally a folder and a name prefix. A statement
may create an object there, and may replace, alter or drop only an object a line of the
workspace's ledger says it made -- or one the server says is not there. Everything else --
another database, someone else's object, users, roles, settings, a web service, a write into a
source, a cache load -- is refused before anything runs, and the refusal asks for the owner's
word: the agent asks a human, it never widens its own scope.

The rule trusts the plan's ``action``, ``object``, ``exists`` and ``destructive`` (denodo_cli's
planner and safety table) and the ledger. On top of it an agent may hold every statement to a
rule of its own -- what a statement may reach, say: ``rule(entry, statement)`` answers why not,
or None. It is asked for every statement, refused or not, so a rule that remembers what each
statement makes sees the whole file.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from denodo_exec.errors import Refused
from denodo_exec.ledger import LEDGER_ACTIONS, ledger_key
from denodo_exec.vql import split_vql

# What denodo_cli's safety table calls a kind of change that is never a workspace's to make.
FORBIDDEN_KINDS = {"security": "users, roles and privileges",
                   "setting": "a server setting",
                   "publish": "a web service",
                   "procedure": "a procedure that changes state",
                   "write": "a write into a source",
                   "table": "a table in a source database",
                   "cache": "a cache load"}
FORBIDDEN_TYPES = ("database", "role", "user", "globalSecurityPolicy")
CASCADE = re.compile(r"\bCASCADE\b", re.I)
FOLDER_CLAUSE = re.compile(r"\bFOLDER\s*=\s*'((?:[^']|'')*)'", re.I)

# The rule a statement is held to on top of the rule of scope: why it is refused, or None.
Rule = Callable[[Mapping[str, Any], str], str | None]


@dataclass(frozen=True)
class Wording:
    """The words a refusal is said in: `owner` opens every refusal that needs a human's yes, in
    the language the agent speaks to its owner; `unit` is what the agent calls its workspace (a
    demo, a project); `ledger` how a refusal names the ledger."""

    owner: str = "needs the owner's word: "
    unit: str = "workspace"
    ledger: str = "its ledger"


class ScopeLike(Protocol):
    @property
    def database(self) -> str: ...
    @property
    def folder(self) -> str | None: ...
    @property
    def prefix(self) -> str | None: ...


@dataclass(frozen=True)
class Scope:
    """Where a workspace may create objects: a database, and inside it optionally a folder
    (`/a/b`, no trailing slash) and a name prefix."""

    database: str
    folder: str | None = None
    prefix: str | None = None


def judge(plan_doc: Mapping[str, Any], text: str, *, scope: ScopeLike,
          live: Mapping[tuple[str, str, str], Any], rule: Rule | None = None,
          wording: Wording = Wording()) -> list[dict[str, Any]]:
    """Every statement of the plan with `allowed` and, when not, `why`: the rule of scope, then
    `rule`. A file that does not split here as it did for the planner is refused whole."""
    entries = plan_doc.get("statements") or []
    statements = split_vql(text)
    if len(statements) != len(entries):
        raise Refused(f"{wording.owner}the file splits into {len(statements)} statements here "
                      f"and {len(entries)} in denodo_cli's plan: one plain statement per `;`, "
                      "no VQL procedure")
    judged = []
    for entry, statement in zip(entries, statements, strict=True):
        # The rule walks every statement, refused or not: it remembers what each makes.
        added = rule(entry, statement) if rule is not None else None
        why = why_not(entry, statement, scope, live, wording) or added
        judged.append({"index": entry.get("index"), "statement": entry.get("statement"),
                       "action": entry.get("action"), "object": entry.get("object"),
                       "exists": entry.get("exists"), "allowed": why is None, "why": why})
    return judged


def _under(path: str, folder: str | None) -> bool:
    if folder is None:
        return True
    path, folder = path.rstrip("/").lower(), folder.rstrip("/").lower()
    return folder == "" or path == folder or path.startswith(folder + "/")


def why_not(entry: Mapping[str, Any], statement: str, scope: ScopeLike,
            live: Mapping[tuple[str, str, str], Any], wording: Wording = Wording()) -> str | None:
    """Why the rule of scope refuses one planned statement, or None when it is the workspace's
    to run."""
    unit = wording.unit
    action = entry.get("action")
    # The safety table first: a read can still carry a cache load (`'cache_preload'='true'`).
    kind = entry.get("destructive")
    if kind in FORBIDDEN_KINDS:
        return f"{FORBIDDEN_KINDS[kind]} is the owner's to change"
    if action == "read":
        return None
    found = entry.get("object") or {}
    otype, name = found.get("type"), found.get("name")
    if action not in LEDGER_ACTIONS or not otype or not name:
        return f"a statement of kind {action!r} is the owner's to run"
    if otype in FORBIDDEN_TYPES:
        return f"a {otype} is the owner's to change"
    database = found.get("database") or scope.database
    if database.lower() != scope.database.lower():
        return f"{database} is outside the {unit}'s database {scope.database}"
    for folder in FOLDER_CLAUSE.findall(statement):
        if not _under(folder.replace("''", "'"), scope.folder):
            return f"folder {folder} is outside the {unit}'s folder {scope.folder}"
    mine = ledger_key(otype, database, name) in live
    if not mine and entry.get("exists") is None:
        # The planner could not read the server (and keeps `create` for CREATE OR REPLACE):
        # whether this would replace someone's object is unknown, so it is not ours to run.
        return f"{otype} {name}: the server could not say whether it exists"
    if action in ("replace", "alter", "drop") and CASCADE.search(statement):
        return "CASCADE would drop dependents the ledger does not name"
    if action == "drop":
        return None if mine or entry.get("exists") is False else (
            f"{otype} {name} is not this {unit}'s: it is in no line of {wording.ledger}")
    if action in ("replace", "alter") or entry.get("exists"):
        return None if mine else (f"{otype} {name} exists and is not this {unit}'s: it is in "
                                  f"no line of {wording.ledger}")
    # A new object: inside the folder and under the prefix, when the scope has them.
    if otype == "folder":
        return None if _under(name, scope.folder) else (
            f"folder {name} is outside the {unit}'s folder {scope.folder}")
    if scope.prefix and not name.lower().startswith(scope.prefix.lower()):
        return f"{name} lacks the {unit}'s prefix {scope.prefix}"
    if scope.folder and not FOLDER_CLAUSE.search(statement):
        return f"{name} has no FOLDER = '{scope.folder}/...' and would land outside the folder"
    return None


def refusal(judged: Sequence[Mapping[str, Any]], wording: Wording = Wording()) -> str | None:
    """One sentence for every refused statement of a plan, or None when none is."""
    refused = [f"#{row['index']} {row['statement']} -- {row['why']}" for row in judged
               if not row["allowed"]]
    return wording.owner + "; ".join(refused) if refused else None
