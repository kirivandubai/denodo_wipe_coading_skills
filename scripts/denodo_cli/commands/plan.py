"""``vql plan`` and ``vql ledger`` (T39): what an input would do here, and what this session created.

Both only read the server. ``vql plan`` answers ``ok`` with exit code 0 whenever it could read the
server, whatever it found — it informs and never refuses; the refusal stays the production
profile's, in ``vql run`` and ``api``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import EXIT_EXECUTION, EXIT_OK
from ..catalog import Catalog
from ..errors import normalize_error
from ..ledger import server_key
from ..output import envelope
from ..planner import YES_NOTE, PlanContext, plan_statements
from ..profiles import Profile
from ..project import declarations_before
from ..statements import ObjectRef

NO_SESSION = ("no session id in the environment (DENODO_SESSION, or CLAUDE_CODE_SESSION_ID in Claude Code): "
              "the ledger is off, and only an object an earlier statement of this input creates counts as yours")


def _session(ledger, session_source: str | None, server: str) -> dict | None:
    if ledger is None:
        return None
    present = [o for o in ledger.objects(server) if o["status"] == "present"]
    return {"id": ledger.session, "source": session_source, "ledger": str(ledger.path), "objects": len(present)}


def plan_input(profile: Profile, statements: list[str], *, transport_factory: Callable, database: str | None,
               source: str | None, ledger, session_source: str | None) -> tuple[dict, int]:
    server = server_key(profile.host, profile.port)
    try:
        transport = transport_factory(profile, database=database)
    except Exception as exc:  # noqa: BLE001 — any driver/network failure is a connection error here
        return envelope(False, profile, "vql plan", database=database,
                        error={"kind": "connection", **normalize_error(exc)}), EXIT_EXECUTION
    try:
        catalog = Catalog(transport)
        started = ledger.started() if ledger is not None else None
        declarations = declarations_before(Path(source) if source else Path.cwd() / "input.vql", started,
                                           default_database=database or profile.database)
        ctx = PlanContext(server=server, database=database or profile.database, production=profile.production,
                          catalog=catalog, ledger=ledger, declarations=declarations)
        entries = plan_statements(statements, ctx)
    finally:
        transport.close()

    actions: dict[str, int] = {}
    for e in entries:
        actions[e["action"]] = actions.get(e["action"], 0) + 1
    duplicates = []
    for e in entries:
        if "duplicate_of" in e:
            first = e["duplicate_of"]
            known = next((d for d in duplicates if first in d["statements"]), None)
            if known is None:
                duplicates.append({"object": e["object"], "statements": [first, e["index"]]})
            else:
                known["statements"].append(e["index"])
    doc = envelope(True, profile, "vql plan", database=database, statements=entries,
                   needs_yes=[e["index"] for e in entries if e["needs_yes"] is True],
                   not_recognised=[e["index"] for e in entries if e["needs_yes"] is None],
                   actions=actions, duplicates=duplicates,
                   executed=0, total=len(entries), session=_session(ledger, session_source, server),
                   project=None if declarations.root is None else {
                       "root": str(declarations.root), "base": declarations.base,
                       "declarations": len(declarations.entries)})
    if doc["needs_yes"]:
        doc["yes"] = YES_NOTE
    if ledger is None:
        doc["session_note"] = NO_SESSION
    if declarations.root is not None and declarations.base is None:
        doc["project_note"] = ("no commit before this session started: no project file vouches for an object "
                               "that already exists")
    if catalog.errors:
        doc["read_errors"] = catalog.errors
    return doc, EXIT_OK


def list_ledger(profile: Profile, *, transport_factory: Callable, ledger, session_source: str | None) -> tuple[dict, int]:
    server = server_key(profile.host, profile.port)
    if ledger is None:
        doc = envelope(True, profile, "vql ledger", session=None, objects=[])
        doc["session_note"] = NO_SESSION
        return doc, EXIT_OK
    entries = ledger.objects(server)
    try:
        transport = transport_factory(profile, database=None)
    except Exception as exc:  # noqa: BLE001
        return envelope(False, profile, "vql ledger", error={"kind": "connection", **normalize_error(exc)}), EXIT_EXECUTION
    objects = []
    try:
        catalog = Catalog(transport)
        for entry in entries:
            item = {k: entry.get(k) for k in ("type", "kind", "database", "name", "names", "created_at", "source")}
            if entry["status"] == "present":
                found = catalog.lookup(ObjectRef(entry["type"], entry.get("database"), entry["name"]))
                recorded = entry.get("internal_id")
                if found.exists is None:
                    item["state"] = "unknown"
                elif not found.exists:
                    item["state"] = "missing"
                elif recorded and found.internal_id and recorded != found.internal_id:
                    item["state"] = "replaced"    # the name now belongs to another object
                else:
                    item["state"] = "present"
            else:
                item["state"] = entry["status"]
            objects.append(item)
    finally:
        transport.close()
    counts: dict[str, int] = {}
    for item in objects:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
    session = _session(ledger, session_source, server)
    if session is not None:
        session["objects"] = len(objects)
    return envelope(True, profile, "vql ledger", session=session, states=counts, objects=objects), EXIT_OK
