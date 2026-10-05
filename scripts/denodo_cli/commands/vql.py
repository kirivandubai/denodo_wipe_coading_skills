"""``vql run`` and ``vql desc``: apply VQL to Virtual DataPort, one statement at a time.

``vql run`` also keeps the session's ledger (T39): before the first statement it reads whether the
objects the input creates exist, and after the last it records the ones that did not — with the
server's ``internal_id`` — together with the drops and renames of objects already recorded.
"""

from __future__ import annotations

import datetime as dt
from typing import Callable

from . import EXIT_EXECUTION, EXIT_OK, EXIT_USAGE
from ..catalog import Catalog
from ..errors import normalize_error
from ..ledger import server_key
from ..output import envelope, rows_payload
from ..profiles import Profile
from ..safety import classify_vql
from ..statements import ObjectRef, parse_statement

STATEMENT_HEAD = 160  # characters of each statement echoed back in the result


def _head(statement: str) -> str:
    flat = " ".join(statement.split())
    return flat if len(flat) <= STATEMENT_HEAD else flat[: STATEMENT_HEAD - 1] + "…"


def _refuse_if_destructive(profile: Profile, statements: list[str], allow_destructive: bool) -> dict | None:
    """On a production profile, list destructive statements unless explicitly allowed."""
    if not profile.production or allow_destructive:
        return None
    found = [
        {"index": i, "kind": kind, "statement": _head(s)}
        for i, s in enumerate(statements)
        if (kind := classify_vql(s))
    ]
    if not found:
        return None
    return {
        "kind": "refused",
        "message": (
            f"profile {profile.name!r} is marked production and the input contains "
            f"{len(found)} destructive statement(s); nothing was executed. Re-run with "
            f"--allow-destructive after a human has confirmed."
        ),
        "destructive": found,
    }


def statement_effects(statements: list[str], database: str) -> list[list[tuple]]:
    """Per statement, what it does to the ledger: ``("create", ref)``, ``("drop", ref)``,
    ``("rename", ref, new_name)``. ``CONNECT DATABASE`` moves the database for what follows."""
    effects: list[list[tuple]] = []
    for text in statements:
        st = parse_statement(text, database)
        found: list[tuple] = []
        if st.connect:
            database = st.connect
        elif st.action == "create" and st.obj is not None:
            found.append(("create", st.obj))
        elif st.action == "drop" and st.obj is not None:
            found.append(("drop", st.obj))
        elif st.action == "rename" and st.obj is not None and st.new_name:
            found.append(("rename", st.obj, st.new_name))
        elif st.action == "call" and st.procedure == "CREATE_REMOTE_TABLE" and st.proc_named.get("base_view_name"):
            db = st.proc_named.get("base_view_database_name") or database
            found.append(("create", ObjectRef("view", db, st.proc_named["base_view_name"], "remote table")))
        effects.append(found)
    return effects


def _record(ledger, profile: Profile, transport, effects: list[list[tuple]], before: dict, executed_ok: list[int],
            source: str | None, statements: list[str], now: dt.datetime) -> dict:
    """Write what the statements that ran did into the ledger; the ``ledger`` part of the answer."""
    server = server_key(profile.host, profile.port)
    report = {"session": ledger.session, "recorded": [], "dropped": [], "renamed": [], "not_recorded": []}
    exists = dict(before)                      # key -> exists, as the input changes it
    to_record: list[tuple[int, ObjectRef]] = []
    gone_later: set[tuple] = set()
    for index in executed_ok:
        for effect in effects[index]:
            op, ref = effect[0], effect[1]
            if op == "create":
                if exists.get(ref.key()) is False:
                    to_record.append((index, ref))
                elif exists.get(ref.key()) is None:
                    report["not_recorded"].append({"object": ref.label(), "why": "whether it existed could not be read"})
                exists[ref.key()] = True
                gone_later.discard(ref.key())
            elif op == "drop":
                exists[ref.key()] = False
                gone_later.add(ref.key())
            elif op == "rename":
                exists[ref.key()] = False
                gone_later.add(ref.key())
    after = Catalog(transport)
    pending = {ref.key(): (index, ref) for index, ref in to_record}
    for index in executed_ok:
        for effect in effects[index]:
            op, ref = effect[0], effect[1]
            if op == "create" and ref.key() in pending and pending[ref.key()][0] == index:
                internal_id = None if ref.key() in gone_later else after.lookup(ref).internal_id
                ledger.record_created(server, ref, internal_id=internal_id, source=source,
                                      statement=statements[index], now=now)
                report["recorded"].append(ref.label())
            elif op == "drop" and ledger.find(server, ref):
                ledger.record_dropped(server, ref, now=now)
                report["dropped"].append(ref.label())
            elif op == "rename" and ledger.find(server, ref):
                ledger.record_renamed(server, ref, effect[2], now=now)
                report["renamed"].append(f"{ref.label()} → {effect[2]}")
    return report


def run_statements(
    profile: Profile,
    statements: list[str],
    *,
    transport_factory: Callable,
    max_rows: int,
    database: str | None = None,
    allow_destructive: bool = False,
    continue_on_error: bool = False,
    ledger=None,
    source: str | None = None,
    now: dt.datetime | None = None,
) -> tuple[dict, int]:
    if not statements:
        return envelope(False, profile, "vql run", database=database,
                        error={"kind": "usage", "message": "no VQL statements to run"}), EXIT_USAGE
    refusal = _refuse_if_destructive(profile, statements, allow_destructive)
    if refusal:
        return envelope(False, profile, "vql run", database=database, error=refusal), EXIT_USAGE

    try:
        transport = transport_factory(profile, database=database)
    except Exception as exc:  # noqa: BLE001 — any driver/network failure is a connection error here
        info = normalize_error(exc)
        return envelope(False, profile, "vql run", database=database,
                        error={"kind": "connection", **info}), EXIT_EXECUTION

    effects = statement_effects(statements, database or profile.database) if ledger is not None else []
    keep_ledger = any(effects)
    before: dict = {}
    if keep_ledger:
        try:
            catalog = Catalog(transport)
            for found in effects:
                for effect in found:
                    if effect[0] == "create":
                        before[effect[1].key()] = catalog.lookup(effect[1]).exists
        except Exception:  # noqa: BLE001 — unknown, so nothing is recorded as created; the run goes on
            before = {}

    results: list[dict] = []
    failed_at: int | None = None
    ledger_report = None
    try:
        for index, statement in enumerate(statements):
            entry = {"index": index, "statement": _head(statement), "destructive": classify_vql(statement)}
            try:
                result = transport.execute(statement)
            except Exception as exc:  # noqa: BLE001 — server error text is the payload
                entry.update(ok=False, error=normalize_error(exc), **rows_payload(None, None, max_rows),
                             affected=None)
                results.append(entry)
                if failed_at is None:
                    failed_at = index
                if not continue_on_error:
                    break
                continue
            # a write returns no result set: the count the server reports is all there is to see
            entry.update(ok=True, error=None, **rows_payload(result.columns, result.rows, max_rows),
                         affected=result.affected)
            results.append(entry)
        if keep_ledger:
            try:
                ledger_report = _record(ledger, profile, transport, effects, before,
                                        [r["index"] for r in results if r["ok"]], source, statements,
                                        now or dt.datetime.now(dt.timezone.utc))
            except Exception as exc:  # noqa: BLE001 — the ledger never fails a run that the server accepted
                ledger_report = {"session": ledger.session, "error": f"the ledger could not be kept: {exc}"}
    finally:
        transport.close()

    ok = failed_at is None
    doc = envelope(ok, profile, "vql run", database=database, statements=results, failed_at=failed_at,
                   executed=len(results), total=len(statements))
    if ledger_report is not None:
        doc["ledger"] = ledger_report
    return doc, EXIT_OK if ok else EXIT_EXECUTION


def describe(
    profile: Profile,
    name: str,
    *,
    transport_factory: Callable,
    max_rows: int,
    kind: str = "view",
    vql: bool = False,
    database: str | None = None,
) -> tuple[dict, int]:
    """``DESC [VQL] <KIND> <name>`` — schema (rows) or server-generated VQL."""
    statement = f"DESC {'VQL ' if vql else ''}{kind.upper()} {name}"
    doc, code = run_statements(profile, [statement], transport_factory=transport_factory,
                               max_rows=max_rows, database=database)
    doc["command"] = "vql desc"
    if doc.get("statements"):
        entry = doc.pop("statements")[0]
        doc.pop("failed_at", None); doc.pop("executed", None); doc.pop("total", None)
        doc["statement"] = statement
        for key in ("columns", "rows", "row_count", "truncated", "error"):
            doc[key] = entry[key]
    return doc, code
