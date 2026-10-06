"""What exists on the server right now — read-only, each list read once and only when asked.

``GET_DATABASES()`` for databases, ``GET_ELEMENTS()`` per database for its elements (with the
``internal_id`` the ledger checks identity by), ``GET_ELEMENTS()`` without a database for tags and
global security policies, ``LIST ROLES`` / ``LIST USERS``, ``USED_BY()`` per view and ``DESC VQL``
of a policy. A read that fails leaves the answer unknown (``exists = None``) and its error in
``errors`` — never "absent", which would read as a new object.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import normalize_error
from .statements import ObjectRef

@dataclass(frozen=True)
class Found:
    exists: bool | None          # None: the server could not be read
    internal_id: str | None = None
    subtype: str | None = None


def _q(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


class Catalog:
    def __init__(self, transport):
        self.transport = transport
        self.errors: list[dict] = []
        self._databases: set[str] | None = None
        self._elements: dict[str, dict | None] = {}
        self._globals: dict | None = None
        self._roles: set[str] | None = None
        self._users: set[str] | None = None
        self._used_by: dict[tuple[str, str], list | None] = {}
        self._policy_texts: dict[str, str] | None = None

    def _rows(self, statement: str, what: str, expected: tuple[str, ...] = ()) -> list[dict] | None:
        try:
            result = self.transport.execute(statement)
        except Exception as exc:  # noqa: BLE001 — the server's text is the payload
            self.errors.append({"read": what, **normalize_error(exc)})
            return None
        columns = [c.lower() for c in (result.columns or [])]
        rows = [dict(zip(columns, row)) for row in (result.rows or [])]
        missing = [c for c in expected if c not in columns]
        if rows and missing:
            self.errors.append({"read": what, "message": f"unexpected answer: no column {', '.join(missing)}"})
            return None
        return rows

    # --- lists --------------------------------------------------------------------------------

    def databases(self) -> set[str] | None:
        if self._databases is None:
            rows = self._rows("SELECT db_name FROM GET_DATABASES()", "databases", ("db_name",))
            if rows is None:
                return None
            self._databases = {str(r["db_name"]).lower() for r in rows}
        return self._databases

    def _database_elements(self, database: str) -> dict | None:
        key = database.lower()
        if key not in self._elements:
            known = self.databases()
            if known is not None and key not in known:
                self._elements[key] = {}
                return self._elements[key]
            rows = self._rows(
                "SELECT name, type, subtype, folder, internal_id FROM GET_ELEMENTS() "
                f"WHERE input_database_name = {_q(database)}", f"elements of {database}", ("name", "type"))
            self._elements[key] = None if rows is None else self._index(rows)
        return self._elements[key]

    @staticmethod
    def _index(rows: list[dict]) -> dict:
        index = {}
        for r in rows:
            etype, name = str(r.get("type") or ""), str(r.get("name") or "")
            if etype == "folder":
                parent = str(r.get("folder") or "/").rstrip("/")
                name = f"{parent}/{name}"
            index[(etype, name.lower())] = Found(True, r.get("internal_id"), r.get("subtype") or None)
        return index

    def _global_elements(self) -> dict | None:
        if self._globals is None:
            rows = self._rows("SELECT name, type, subtype, folder, internal_id FROM GET_ELEMENTS() "
                              "WHERE type = 'tag' OR type = 'globalSecurityPolicy'", "tags and policies",
                              ("name", "type"))
            if rows is None:
                return None
            self._globals = self._index(rows)
        return self._globals

    def _names(self, statement: str, what: str) -> set[str] | None:
        rows = self._rows(statement, what, ("name",))
        return None if rows is None else {str(r["name"]).lower() for r in rows}

    def roles(self) -> set[str] | None:
        if self._roles is None:
            self._roles = self._names("LIST ROLES", "roles")
        return self._roles

    def users(self) -> set[str] | None:
        if self._users is None:
            self._users = self._names("LIST USERS", "users")
        return self._users

    # --- questions ----------------------------------------------------------------------------

    def lookup(self, ref: ObjectRef) -> Found:
        name = ref.name.lower()
        if ref.type == "database":
            known = self.databases()
            return Found(None) if known is None else Found(name in known)
        if ref.type in ("role", "user"):
            known = self.roles() if ref.type == "role" else self.users()
            return Found(None) if known is None else Found(name in known)
        if ref.type in ("tag", "globalSecurityPolicy"):
            index = self._global_elements()
        elif ref.database:
            index = self._database_elements(ref.database)
        else:
            return Found(None)
        if index is None:
            return Found(None)
        return index.get((ref.type, name), Found(False))

    def used_by(self, database: str, view: str) -> list[tuple[str, str]] | None:
        key = (database.lower(), view.lower())
        if key not in self._used_by:
            rows = self._rows(
                "SELECT used_by_database_name, used_by_name, depth FROM USED_BY() "
                f"WHERE input_view_database_name = {_q(database)} AND input_view_name = {_q(view)}",
                f"dependants of {database}.{view}", ("used_by_database_name", "used_by_name"))
            self._used_by[key] = None if rows is None else [
                (str(r["used_by_database_name"]), str(r["used_by_name"])) for r in rows]
        return self._used_by[key]

    def policies_naming(self, tag: str) -> list[str] | None:
        """The global security policies whose definition names ``tag``."""
        if self._policy_texts is None:
            index = self._global_elements()
            if index is None:
                return None
            texts = {}
            for (etype, name) in index:
                if etype != "globalSecurityPolicy":
                    continue
                rows = self._rows(f"DESC VQL GLOBAL_SECURITY_POLICY {name}", f"policy {name}")
                texts[name] = "" if not rows else " ".join(str(v) for v in rows[0].values())
            self._policy_texts = texts
        pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(tag)}(?![A-Za-z0-9_])", re.IGNORECASE)
        return sorted(name for name, text in self._policy_texts.items() if pattern.search(text))
