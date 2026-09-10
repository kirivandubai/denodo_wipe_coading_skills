"""``vql run`` and ``vql desc``: apply VQL to Virtual DataPort, one statement at a time."""

from __future__ import annotations

from typing import Callable

from . import EXIT_EXECUTION, EXIT_OK, EXIT_USAGE
from ..errors import normalize_error
from ..output import envelope, rows_payload
from ..profiles import Profile
from ..safety import classify_vql

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


def run_statements(
    profile: Profile,
    statements: list[str],
    *,
    transport_factory: Callable,
    max_rows: int,
    database: str | None = None,
    allow_destructive: bool = False,
    continue_on_error: bool = False,
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

    results: list[dict] = []
    failed_at: int | None = None
    try:
        for index, statement in enumerate(statements):
            entry = {"index": index, "statement": _head(statement), "destructive": classify_vql(statement)}
            try:
                result = transport.execute(statement)
            except Exception as exc:  # noqa: BLE001 — server error text is the payload
                entry.update(ok=False, error=normalize_error(exc), **rows_payload(None, None, max_rows))
                results.append(entry)
                if failed_at is None:
                    failed_at = index
                if not continue_on_error:
                    break
                continue
            entry.update(ok=True, error=None, **rows_payload(result.columns, result.rows, max_rows))
            results.append(entry)
    finally:
        transport.close()

    ok = failed_at is None
    doc = envelope(ok, profile, "vql run", database=database, statements=results, failed_at=failed_at,
                   executed=len(results), total=len(statements))
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
