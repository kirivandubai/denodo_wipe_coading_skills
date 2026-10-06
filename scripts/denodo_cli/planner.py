"""``vql plan``: the core's safety table applied to each statement of an input, on this server.

For every statement: what it does to which object, whether the object exists at that point of the
input, whether it is the session's own (the ledger, identity checked — or an earlier statement of
the same input created it), and whether the table of ``/denodo:vql`` puts it under the human's yes
— with the row that decides (``why``) and what that row also needs and the tool cannot see
(``conditions``). It informs; it never refuses. The rule itself lives in the skill (design spec
6.3); this module is its reading on a live catalog, and the table in
``docs/superpowers/specs/2026-10-06-session-ledger-and-plan-design.md`` maps one onto the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .project import Declarations, normalize
from .safety import classify_vql
from .statements import ObjectRef, Statement, parse_statement

HEAD = 160
_TABLE_KINDS = ("remote table", "summary", "materialized table")
_COLUMNS_CONDITION = ("it keeps every column the views that read it use — dropping or renaming one breaks them "
                      "without an error (/denodo:views, Before a column changes)")
_TEXTS_CONDITION = ("a new description, field description, primary key or tag is a text the human approves "
                    "(/denodo:semantics)")
_TARGET_CONDITIONS = ["the data source and schema are the ones the human named (/denodo:materialize)",
                      "the table name is free in that schema — the reads show it (/denodo:materialize)"]


@dataclass
class PlanContext:
    server: str
    database: str
    production: bool
    catalog: Any                 # Catalog, or anything with lookup / used_by / policies_naming
    ledger: Any                  # Ledger or None
    declarations: Declarations


# What "the human's yes" means, said where the agent decides (T42): an outcome scenario's agent read
# "a DROP waits for the human's yes" in a plan and took the request that asked for the DROP as it.
YES_NOTE = ("needs_yes: show these statements to the human and wait for their yes to them, in this "
            "conversation. The request that asked for the change is not that yes, however clear; when nobody "
            "can answer, the file and your message are the result, not the statement run (/denodo:vql).")


def _head(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= HEAD else flat[: HEAD - 1] + "…"


class _Walk:
    """The state of the server as the input changes it, statement by statement.

    ``exists`` and ``own`` are tracked apart: a ``CREATE OR REPLACE`` of someone else's object
    leaves it someone else's, and a rename of it moves the name, not the ownership."""

    def __init__(self, ctx: PlanContext):
        self.ctx = ctx
        self.state: dict[tuple, tuple[bool, bool]] = {}   # key -> (exists, own), set by the input
        self.new: dict[tuple, ObjectRef] = {}               # created by an earlier statement of the input
        self.renamed: dict[tuple, ObjectRef] = {}           # old key -> the object under its new name
        self.dropped: set[tuple] = set()                    # dropped by an earlier statement of the input
        self.declared: dict[tuple, tuple[int, str]] = {}    # the statement of the input that last declared it, and its text

    def exists(self, ref: ObjectRef) -> bool | None:
        if ref.key() in self.state:
            return self.state[ref.key()][0]
        return self.ctx.catalog.lookup(ref).exists

    def own(self, ref: ObjectRef) -> bool:
        if ref.key() in self.state:
            return self.state[ref.key()][1]
        if self.ctx.ledger is None:
            return False
        entry = self.ctx.ledger.find(self.ctx.server, ref)
        if entry is None:
            return False
        found = self.ctx.catalog.lookup(ref)
        if found.exists is False:
            return False
        recorded = entry.get("internal_id")
        return not (recorded and found.internal_id and recorded != found.internal_id)

    def kind(self, ref: ObjectRef) -> str | None:
        if ref.key() in self.new:
            return self.new[ref.key()].kind
        if self.ctx.ledger is not None and self.own(ref):
            entry = self.ctx.ledger.find(self.ctx.server, ref)
            if entry and entry.get("kind"):
                return entry.get("kind")
        subtype = self.ctx.catalog.lookup(ref).subtype
        return {"metric": "metric view", "summary": "summary"}.get(subtype or "", subtype)

    def dependents(self, ref: ObjectRef) -> list[dict] | None:
        if ref.type != "view" or ref.key() in self.new:
            return []
        rows = self.ctx.catalog.used_by(ref.database, ref.name)
        if rows is None:
            return None
        out = []
        for db, name in rows:
            reader = ObjectRef("view", db, name)
            if reader.key() == ref.key() or reader.key() in self.dropped:
                continue                                  # itself, or gone before this statement runs
            while reader.key() in self.renamed:           # the server still lists the old name
                reader = self.renamed[reader.key()]
            out.append({"database": reader.database, "name": reader.name, "own": self.own(reader)})
        return out

    def create(self, ref: ObjectRef) -> None:
        self.state[ref.key()] = (True, True)
        self.new[ref.key()] = ref

    def drop(self, ref: ObjectRef) -> None:
        self.state[ref.key()] = (False, False)
        self.new.pop(ref.key(), None)
        self.dropped.add(ref.key())

    def rename(self, ref: ObjectRef, new_name: str) -> None:
        own, kind = self.own(ref), self.kind(ref)
        renamed = ObjectRef(ref.type, ref.database, new_name, kind)
        self.state[ref.key()] = (False, False)
        self.new.pop(ref.key(), None)
        self.state[renamed.key()] = (True, own)
        self.renamed[ref.key()] = renamed
        if own:
            self.new[renamed.key()] = renamed


def _decision(entry: dict, needs_yes: bool | None, why: str, conditions: list[str] | None = None) -> dict:
    entry["needs_yes"] = needs_yes
    entry["why"] = why
    entry["conditions"] = conditions or []
    return entry


def plan_statements(statements: list[str], ctx: PlanContext) -> list[dict]:
    walk = _Walk(ctx)
    database = ctx.database
    entries = []
    for index, text in enumerate(statements):
        st = parse_statement(text, database)
        if st.connect:
            database = st.connect
        entry = _plan_one(index, st, walk, ctx)
        entries.append(entry)
        _advance(st, walk, entry)
    return entries


def _advance(st: Statement, walk: _Walk, entry: dict) -> None:
    """What the statement leaves behind, for the statements after it.

    A second declaration of one object in the same input is named (``duplicate_of``): in a file
    generated for many objects it is a naming rule that gave two sources one name, and the later
    definition silently replaces the earlier one."""
    if st.action == "create" and st.obj is not None:
        earlier = walk.declared.get(st.obj.key())
        if earlier is not None and earlier[1] != normalize(st.text):
            entry["duplicate_of"] = earlier[0]
        if earlier is None or earlier[1] != normalize(st.text):
            walk.declared[st.obj.key()] = (entry["index"], normalize(st.text))
        if entry["exists"] is False:
            walk.create(st.obj)          # new: the input's own from here on
    elif st.action == "drop" and st.obj is not None:
        walk.declared.pop(st.obj.key(), None)
        walk.drop(st.obj)
    elif st.action == "rename" and st.obj is not None and st.new_name:
        walk.declared.pop(st.obj.key(), None)
        walk.rename(st.obj, st.new_name)
    elif st.action == "call" and st.procedure == "CREATE_REMOTE_TABLE":
        view = _remote_table_view(st)
        if view is not None and entry["exists"] is False:
            walk.create(view)


def _remote_table_view(st: Statement) -> ObjectRef | None:
    name = st.proc_named.get("base_view_name")
    if not name:
        return None
    database = st.proc_named.get("base_view_database_name") or (st.obj.database if st.obj else None)
    return ObjectRef("view", database, name, "remote table")


def _object_fields(ref: ObjectRef | None) -> dict | None:
    if ref is None:
        return None
    out = {"type": ref.type, "database": ref.database, "name": ref.name}
    if ref.kind:
        out["kind"] = ref.kind
    return out


def _plan_one(index: int, st: Statement, walk: _Walk, ctx: PlanContext) -> dict:
    entry: dict[str, Any] = {
        "index": index, "statement": _head(st.text), "action": st.action, "object": _object_fields(st.obj),
        "exists": None, "own": None, "destructive": classify_vql(st.text),
    }
    ref = st.obj
    if ref is not None:
        entry["exists"] = walk.exists(ref)
        entry["own"] = walk.own(ref) if entry["exists"] is not False else (st.action == "create")
        if st.action == "create" and entry["exists"] and st.or_replace:
            entry["action"] = "replace"

    if ctx.production and st.action not in ("read", "session"):
        return _decision(entry, True, "the profile is production: every change waits for the human's yes")

    action = st.action
    if action == "cache":
        return _cache(entry, st, walk)
    if action == "read":
        if st.ai_over_rows:
            return _decision(entry, True, "an AI function evaluated over the rows of a view: every row is a paid "
                                          "request to the provider; the human agrees to the number (/denodo:ai)")
        return _decision(entry, False, "a read")
    if action == "session":
        return _decision(entry, False, "a setting of this session only")
    if action == "setting":
        return _decision(entry, True, "the configuration of the whole server, not your session")
    if action == "other":
        return _decision(entry, None, "the plan does not recognise this statement: the table of /denodo:vql decides")
    if action == "create":
        return _create(entry, st, walk, ctx)
    if action in ("alter", "rename"):
        return _alter(entry, st, walk)
    if action == "drop":
        return _decision(entry, True, "a DROP waits for the human's yes, whatever it hits — your own object too")
    if action == "insert":
        if ref is not None and entry["own"] and walk.kind(ref) == "materialized table":
            return _decision(entry, False, "an INSERT into a materialized table you created in this session")
        return _decision(entry, True, "the rows land in the source behind the view at once (/denodo:dml)")
    if action in ("update", "delete"):
        return _decision(entry, True, "the rows change in the source behind the view at once (/denodo:dml)")
    if action == "refresh":
        if ref is not None and entry["own"] and walk.kind(ref) == "remote table":
            return _decision(entry, False, "a REFRESH of a remote table you created in this session")
        return _decision(entry, True, "a REFRESH empties a table older than this session, or loads a summary — "
                                      "from then on it answers other people's queries (/denodo:materialize)")
    if action == "call":
        return _call(entry, st, walk)
    return _decision(entry, None, "the plan does not recognise this statement: the table of /denodo:vql decides")


def _cache_target(st: Statement) -> ObjectRef | None:
    return ObjectRef("view", st.cache_view[0], st.cache_view[1]) if st.cache_view else None


def _call(entry: dict, st: Statement, walk: _Walk) -> dict:
    name = st.procedure
    if name == "CREATE_REMOTE_TABLE":
        view = _remote_table_view(st)
        replace_table = st.proc_named.get("replace_remote_table_if_exist")
        replace_view = st.proc_named.get("replace_base_view_if_exist")
        if view is not None:
            entry["object"] = _object_fields(view)
            entry["exists"] = walk.exists(view)
            entry["own"] = walk.own(view) if entry["exists"] else True
        if replace_table == "false" and not (replace_view == "true" and entry["exists"] and not entry["own"]):
            return _decision(entry, False, "a new table, by a call that cannot overwrite one", list(_TARGET_CONDITIONS))
        if view is not None and entry["exists"] and entry["own"] and walk.kind(view) == "remote table":
            return _decision(entry, False, "replaces the remote table you created in this session")
        return _decision(entry, True, "it may drop or replace a table older than this session "
                                      "(replace_remote_table_if_exist is not false) — /denodo:materialize")
    if name == "CLEAN_CACHE_DATABASE":
        if len(st.proc_args) >= 2:
            view = ObjectRef("view", st.proc_args[0], st.proc_args[1])
            entry["object"] = _object_fields(view)
            entry["exists"] = walk.exists(view)
            entry["own"] = walk.own(view)
            if entry["own"]:
                return _decision(entry, False, "clears the cache of a view you created in this session (/denodo:cache)")
            return _decision(entry, True, "clears the cache of a view you did not create in this session (/denodo:cache)")
        return _decision(entry, True, "without the view it cleans the cache of a whole database (/denodo:cache)")
    if st.cache_view:
        return _cache(entry, st, walk)
    return _decision(entry, True, f"{name} changes state outside the objects of this session (/denodo:procedures)")


def _cache(entry: dict, st: Statement, walk: _Walk) -> dict:
    view = _cache_target(st)
    entry["object"] = _object_fields(view)
    entry["exists"] = walk.exists(view)
    entry["own"] = walk.own(view)
    if entry["own"]:
        return _decision(entry, False, "loads the cache of a view you created in this session (/denodo:cache)")
    return _decision(entry, True, "loads or invalidates the cache of a view you did not create in this session "
                                  "(/denodo:cache)")


def _create(entry: dict, st: Statement, walk: _Walk, ctx: PlanContext) -> dict:
    ref = st.obj
    exists, own, kind = entry["exists"], entry["own"], ref.kind
    if ref.type in ("role", "user", "globalSecurityPolicy") or entry["destructive"] == "security":
        return _security(entry, st, walk)

    if exists is None:
        decision = _decision(entry, True, "the server could not be read: whether this replaces something is unknown")
    elif exists and not st.or_replace:
        decision = _decision(entry, False, "the name exists: the statement fails and changes nothing",
                             ["the server refuses the statement — the name is taken"])
    elif kind == "summary" and st.load_immediate:
        decision = _decision(entry, True, "every load of a summary changes other people's answers — create it with "
                                          "DATA_LOAD_IMMEDIATE = FALSE (/denodo:materialize)")
    elif not exists:
        others = _foreign_endpoints(st, walk)
        if kind == "remote table":
            decision = _decision(entry, False, "a new table in a source database", list(_TARGET_CONDITIONS))
        elif others:
            decision = _decision(entry, True, "a new association that names views you did not create in this "
                                              "session: " + ", ".join(others) + " — it becomes a dependant of them, "
                                              "and their owner's DROP VIEW then needs CASCADE (/denodo:semantics)")
        else:
            decision = _decision(entry, False, "a new object")
    elif own:
        others = _foreign_endpoints(st, walk)
        if others:
            decision = _decision(entry, True, "re-declares your association onto views you did not create in this "
                                              "session: " + ", ".join(others) + " (/denodo:semantics)")
        else:
            decision = _decision(entry, False, "replaces an object you created in this session")
    else:
        decision = _replace_older(entry, st, walk, ctx)
    if decision["needs_yes"] is not True and st.tags_assigned:
        return _tags(decision, st, walk)
    return decision


def _foreign_endpoints(st: Statement, walk: _Walk) -> list[str]:
    """The views an association names that are not the session's own — or could not be read."""
    out = []
    for db, view in st.endpoints:
        ref = ObjectRef("view", db, view)
        exists = walk.exists(ref)
        if exists is None:
            out.append(f"{ref.label()} (could not be read)")
        elif exists and not walk.own(ref):
            out.append(ref.label())
    return out


def _replace_older(entry: dict, st: Statement, walk: _Walk, ctx: PlanContext) -> dict:
    ref = st.obj
    kind = walk.kind(ref) or ref.kind
    if ref.type == "view":
        entry["dependents"] = walk.dependents(ref)
    if ref.kind == "metric view" or kind == "metric view":
        return _decision(entry, True, "replaces a metric view you did not create in this session: a changed join, "
                                      "filter or metric changes every figure built on it (/denodo:metrics)")
    if ref.kind in _TABLE_KINDS or kind in _TABLE_KINDS:
        return _decision(entry, True, "OR REPLACE drops or empties a table this session did not create "
                                      "(/denodo:materialize)")
    declaration = ctx.declarations.get(ref)
    if declaration is None:
        return _decision(entry, True, "replaces an object this session did not create and that no project file "
                                      "declared before the session — its whole configuration goes (/denodo:vql)")
    entry["declared_in"] = declaration.path
    if normalize(declaration.text) == normalize(st.text):
        return _decision(entry, False, f"re-applies the declaration of {declaration.path} unchanged")
    conditions = []
    if ref.type == "view":
        if entry.get("dependents"):
            conditions.append(_COLUMNS_CONDITION)
        conditions.append(_TEXTS_CONDITION)
    return _decision(entry, False, f"re-declares an object {declaration.path} declared before this session",
                     conditions)


def _alter(entry: dict, st: Statement, walk: _Walk) -> dict:
    ref = st.obj
    if ref is None or ref.type in ("role", "user", "globalSecurityPolicy"):
        return _security(entry, st, walk)
    if entry["exists"] is None:
        return _decision(entry, True, "the server could not be read: whose object this is is unknown")
    if entry["exists"] is False:
        return _decision(entry, True, "the object does not exist at this point of the input: the server would "
                                      "refuse the statement now, and whose it is — and whose the views it names "
                                      "are — can be read only once it exists",
                         ["create it first — apply the file that does, then plan this one again"])
    if not entry["own"]:
        return _decision(entry, True, "an ALTER of an object this session did not create")
    if ref.type == "view":
        dependents = walk.dependents(ref)
        entry["dependents"] = dependents
        if dependents is None:
            return _decision(entry, True, "its readers could not be read (USED_BY failed)")
        others = [d for d in dependents if not d["own"]]
        if others:
            names = ", ".join(f"{d['database']}.{d['name']}" for d in others)
            return _decision(entry, True, f"something you did not create in this session reads it: {names}")
    readers = "read only by objects of this session" if entry.get("dependents") else "which nothing reads"
    decision = _decision(entry, False, f"an ALTER of an object you created in this session, {readers}")
    if st.tags_assigned:
        return _tags(decision, st, walk)
    return decision


def _tags(decision: dict, st: Statement, walk: _Walk) -> dict:
    others = []
    for db, view in st.tag_targets:
        target = ObjectRef("view", db, view)
        if not walk.own(target):
            others.append(target.label())
    if others:
        return _decision(decision, True, "puts or removes a tag on a view you did not create in this session: "
                                         + ", ".join(others) + " (/denodo:catalog, /denodo:semantics)")
    for tag in st.tags_assigned:
        tag_ref = ObjectRef("tag", None, tag)
        if walk.own(tag_ref):
            continue
        policies = walk.ctx.catalog.policies_naming(tag)
        if policies is None:
            return _decision(decision, True, f"whether a global security policy names the tag {tag} could not be read")
        if policies:
            return _decision(decision, True, f"the tag {tag} is named by the global security policy "
                                             f"{', '.join(policies)}: putting it on a column changes who reads what "
                                             "(/denodo:security)")
    return decision


def _security(entry: dict, st: Statement, walk: _Walk) -> dict:
    ref = st.obj
    if ref is not None and ref.type == "user" or "USER" in st.text.upper().split()[:2]:
        return _decision(entry, True, "a user is a person: creating one, or granting to one, is the human's "
                                      "(/denodo:security)")
    if ref is not None and entry["exists"] and not entry["own"]:
        return _decision(entry, True, "re-declaring or changing a role or policy this session did not create — "
                                      "CREATE OR REPLACE of a role adds to it (/denodo:security)")
    touches = []
    for name in st.identifiers:
        if ref is not None and name == ref.name.lower():
            continue
        for candidate in _candidates(name, ref.database if ref else None, walk.ctx.database):
            if walk.exists(candidate) and not walk.own(candidate):
                touches.append({"type": candidate.type, "name": name})
                break
    entry["touches"] = touches
    if touches:
        return _decision(entry, True, "it changes who may read what, and touches what existed before this "
                                      "session (/denodo:security)")
    return _decision(entry, False, "a new security object whose every named object you created in this session")


def _candidates(name: str, database: str | None, current: str) -> list[ObjectRef]:
    parts = name.split(".")
    if len(parts) >= 2:
        return [ObjectRef("view", parts[-2], parts[-1])]
    return [ObjectRef("role", None, name), ObjectRef("user", None, name), ObjectRef("database", None, name),
            ObjectRef("tag", None, name)]
