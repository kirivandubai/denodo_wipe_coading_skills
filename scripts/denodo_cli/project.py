"""Which objects the project declared before this session — from git, not from the working tree.

The core's table lets the agent re-apply ``CREATE OR REPLACE`` of an object "your project's own
file declares": re-applying yesterday's committed file costs no yes. A file the session wrote, or
committed itself, must not vouch for an object someone else created, so only the tree of the last
commit made *before the session started* counts (``git rev-list -1 --before=<start> HEAD``). No
git, or no commit before the session, means no declarations — and the plan says so.
"""

from __future__ import annotations

import datetime as dt
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .statements import ObjectRef, _tokens, parse_statement
from .vql_split import split_statements


@dataclass(frozen=True)
class Declaration:
    path: str     # relative to the repository root
    text: str     # the statement as committed


@dataclass
class Declarations:
    root: Path | None = None
    base: str | None = None       # the commit read, None when there is none before the session
    entries: dict = field(default_factory=dict)
    error: str | None = None

    def get(self, ref: ObjectRef) -> Declaration | None:
        return self.entries.get(ref.key())


def normalize(text: str) -> str:
    """The statement with its whitespace collapsed outside string literals."""
    parts = []
    for tok in _tokens(text):
        parts.append("'" + tok.value.replace("'", "''") + "'" if tok.kind == "str"
                     else '"' + tok.value + '"' if tok.kind == "qid" else tok.value)
    return " ".join(parts)


def _git(root: Path, *args: str, stdin: str | None = None) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(root), *args], input=stdin, capture_output=True,
                              text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def _existing_dir(path: Path) -> Path:
    path = path.expanduser().absolute()
    for candidate in (path, *path.parents):
        if candidate.is_dir():
            return candidate
    return Path.cwd()


def declarations_before(path: Path, started: dt.datetime | None, *, default_database: str) -> Declarations:
    """The objects created by the ``.vql`` files of ``path``'s repository as of ``started``."""
    top = _git(_existing_dir(path), "rev-parse", "--show-toplevel")
    if not top:
        return Declarations()
    root = Path(top.strip()).resolve()
    found = Declarations(root=root)
    if started is None:
        return found
    base = _git(root, "rev-list", "-1", f"--before={started.astimezone(dt.timezone.utc).isoformat()}", "HEAD")
    if not base or not base.strip():
        return found
    found.base = base.strip()
    listing = _git(root, "ls-tree", "-r", "--name-only", found.base)
    if listing is None:
        found.error = "git ls-tree failed"
        return found
    files = [name for name in listing.splitlines() if name.lower().endswith(".vql")]
    for name in files:
        text = _git(root, "show", f"{found.base}:{name}")
        if text is None:
            continue
        database = default_database
        for statement in split_statements(text):
            parsed = parse_statement(statement, database)
            if parsed.connect:
                database = parsed.connect
            elif parsed.action == "create" and parsed.obj is not None:
                found.entries[parsed.obj.key()] = Declaration(name, statement)
    return found
