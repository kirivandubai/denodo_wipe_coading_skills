"""The ledger of the session's own objects (T39).

"Created in this session" decides half of the core's safety table — an ``ALTER`` of your own new
view is yours, of anyone else's it waits for the human — and the agent used to carry that answer
in its context, which a compacted session or a subagent does not have. Every ``vql run`` records
here what it created; ``vql plan`` reads it back.

A session is the conversation with the human, subagents included: ``DENODO_SESSION`` when a
harness or a human sets it, else ``CLAUDE_CODE_SESSION_ID``, which Claude Code puts into every
``Bash`` command (a subagent sees its parent's id). Without either the ledger is off.

One JSON file per session, beside the profiles file and so outside every repository; ``0600`` in
a ``0700`` directory, written under a lock and replaced atomically, deleted after 30 days without
a write. Per VDP server (``host:port``), one entry per object a successful statement created —
identity is the server's ``internal_id``, which ``CREATE OR REPLACE`` and ``RENAME`` keep and a
``DROP`` and ``CREATE`` change.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Iterator

from .statements import ObjectRef

SESSION_VARIABLES = ("DENODO_SESSION", "CLAUDE_CODE_SESSION_ID")
KEEP_DAYS = 30

try:  # POSIX; on Windows the ledger is written without a lock
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


def session_from_env(environ) -> tuple[str | None, str | None]:
    """The session id and the variable it came from, or ``(None, None)``."""
    for name in SESSION_VARIABLES:
        value = (environ.get(name) or "").strip()
        if value:
            return value, name
    return None, None


def server_key(host: str, port: int) -> str:
    return f"{host.strip().lower()}:{port}"


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text: str) -> dt.datetime:
    return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def _same(entry: dict, ref: ObjectRef) -> bool:
    db = (entry.get("database") or "").lower() or None
    return (entry["type"], db) == ref.key()[:2]


class Ledger:
    def __init__(self, directory: Path, session: str):
        self.directory = Path(directory)
        self.session = session
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", session).strip(".") or "session"
        self.path = self.directory / f"{safe}.json"

    # --- file ---------------------------------------------------------------------------------

    def _read(self) -> dict:
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            # A damaged file proves nothing about ownership: set it aside and start over, so a
            # half-written ledger never vouches for an object.
            with contextlib.suppress(OSError):
                self.path.replace(self.path.with_suffix(".damaged"))
            return {}
        return doc if isinstance(doc, dict) else {}

    @contextlib.contextmanager
    def _locked(self) -> Iterator[dict]:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.directory, 0o700)
        lock_path = self.path.with_suffix(".lock")
        with open(lock_path, "a+") as lock:
            if fcntl:
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                doc = self._read()
                doc.setdefault("session", self.session)
                doc.setdefault("servers", {})
                yield doc
                self._write(doc)
            finally:
                if fcntl:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def _write(self, doc: dict) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=".ledger-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(doc, handle, ensure_ascii=False, indent=1)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    # --- writes -------------------------------------------------------------------------------

    def touch(self, now: dt.datetime) -> dt.datetime:
        """Make sure the session file exists; the time of the session's first command."""
        with self._locked() as doc:
            doc.setdefault("started", _iso(now))
            doc["updated"] = _iso(now)
            started = doc["started"]
        return _parse_iso(started)

    def record_created(self, server: str, ref: ObjectRef, *, internal_id: str | None, source: str | None,
                       statement: str, now: dt.datetime) -> None:
        with self._locked() as doc:
            doc.setdefault("started", _iso(now))
            doc["updated"] = _iso(now)
            objects = doc["servers"].setdefault(server, {"objects": []})["objects"]
            for entry in objects:
                if entry["status"] == "present" and _same(entry, ref) and entry["name"].lower() == ref.name.lower():
                    if internal_id and not entry.get("internal_id"):
                        entry["internal_id"] = internal_id
                    return
            objects.append({
                "type": ref.type, "kind": ref.kind, "database": ref.database, "name": ref.name,
                "internal_id": internal_id, "created_at": _iso(now), "source": source,
                "statement": " ".join(statement.split())[:160], "status": "present", "names": [ref.name],
            })

    def record_dropped(self, server: str, ref: ObjectRef, *, now: dt.datetime) -> None:
        """A dropped database takes every object of the session inside it along."""
        with self._locked() as doc:
            doc["updated"] = _iso(now)
            gone = self._present(doc, server, ref)
            if ref.type == "database":
                gone += [e for e in doc.get("servers", {}).get(server, {}).get("objects", [])
                         if e["status"] == "present" and (e.get("database") or "").lower() == ref.name.lower()]
            for entry in gone:
                entry["status"] = "dropped"
                entry["dropped_at"] = _iso(now)

    def record_renamed(self, server: str, ref: ObjectRef, new_name: str, *, now: dt.datetime) -> None:
        with self._locked() as doc:
            doc["updated"] = _iso(now)
            for entry in self._present(doc, server, ref):
                entry["name"] = new_name
                entry["names"].append(new_name)

    @staticmethod
    def _present(doc: dict, server: str, ref: ObjectRef) -> list[dict]:
        objects = doc.get("servers", {}).get(server, {}).get("objects", [])
        return [e for e in objects
                if e["status"] == "present" and _same(e, ref) and e["name"].lower() == ref.name.lower()]

    # --- reads --------------------------------------------------------------------------------

    def objects(self, server: str) -> list[dict]:
        return list(self._read().get("servers", {}).get(server, {}).get("objects", []))

    def started(self) -> dt.datetime | None:
        value = self._read().get("started")
        return _parse_iso(value) if value else None

    def find(self, server: str, ref: ObjectRef) -> dict | None:
        """The entry of an object this session created that still has this name."""
        for entry in reversed(self.objects(server)):
            if entry["status"] == "present" and _same(entry, ref) and entry["name"].lower() == ref.name.lower():
                return entry
        return None

    def former(self, server: str, ref: ObjectRef) -> dict | None:
        """The entry of an object this session created under this name, since dropped or renamed away."""
        for entry in reversed(self.objects(server)):
            if not _same(entry, ref):
                continue
            names = [n.lower() for n in entry.get("names", [entry["name"]])]
            if ref.name.lower() not in names:
                continue
            gone = entry["status"] == "dropped" or entry["name"].lower() != ref.name.lower()
            if gone:
                return entry
        return None


def prune_sessions(directory: Path, now: dt.datetime, keep_days: int = KEEP_DAYS) -> None:
    """Delete session files nobody wrote for ``keep_days``."""
    limit = (now - dt.timedelta(days=keep_days)).timestamp()
    try:
        candidates = list(Path(directory).iterdir())
    except OSError:
        return
    for path in candidates:
        if path.suffix not in (".json", ".lock", ".damaged") or path.name.startswith(".ledger-"):
            continue
        with contextlib.suppress(OSError):
            if path.stat().st_mtime < limit:
                path.unlink()
