"""Classify operations that destroy or overwrite existing objects.

The execution layer does not decide whether an operation is allowed — that is the
core skill's job (design spec, section 6.3). It only makes the classification explicit:
every result carries ``destructive``, and on a profile marked ``production = true`` a
destructive operation is refused unless ``--allow-destructive`` is passed.

VQL is classified by its leading keyword, and then by the name of the procedure it calls:
the predefined procedures that change state (``DROP_REMOTE_TABLE``, ``CLEAN_CACHE_DATABASE``,
``GENERATE_STATS`` …) are invoked with ``SELECT … FROM name(…)`` or ``CALL name(…)``, so the
keyword alone lets them through (T20). HTTP calls are classified by method and path, never
by words in the body: the Data Marketplace has ``POST`` endpoints that overwrite whole sets
(spike T11, section 6).
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_LEADING_NOISE = re.compile(r"^(?:\s+|--[^\n]*|#[^\n]*|/\*.*?\*/)*", re.DOTALL)
_VQL_KINDS = {
    "DROP": "drop",
    "ALTER": "alter",
    "DELETE": "delete",
    "TRUNCATE": "delete",
}

# Predefined procedures that change state although they are invoked like a read. A deny
# list, not an allow list: ``GET_ELEMENTS()``, ``DUAL()`` and the other hundred readers
# must keep passing. The same list is written out for the agent in
# skills/procedures/references/predefined.md ("A call that looks like a read and is not");
# tests/test_safety.py fails when the two copies differ, so change both together.
# A user-written VQL procedure that runs DDL through EXECUTE is not caught by name.
STATE_CHANGING_PROCEDURES = frozenset({
    "GENERATE_STATS",
    "CREATE_REMOTE_TABLE",
    "DROP_REMOTE_TABLE",
    "CLEAN_CACHE_DATABASE",
    "DROP_NONACTIVE_CACHE_TABLES",
    "CREATE_SCHEMA_ON_SOURCE",
    "DROP_SCHEMA_ON_SOURCE",
    "REMOVE_ICEBERG_VIEW_SNAPSHOTS",
    "ROLLBACK_ICEBERG_VIEW_TO_SNAPSHOT",
})
# ``FROM name(`` anywhere in the statement (a view defined over the procedure would run it
# on every query), ``CALL name(`` at the start; an optional ``database.`` qualifier.
_PROCEDURE_CALL = re.compile(
    r"(?:\bFROM\s+|^CALL\s+)(?:[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.IGNORECASE,
)

# POST endpoints that replace a whole set instead of adding to it, or that delete what is
# missing from the payload (T11 section 6; T8d re-checked them against the 9.5.1 API).
_REPLACING_POSTS = (
    # the body is the complete set of imported VDP tags; everything absent from it is dropped
    re.compile(r"^/public/api/tags/vdp/synchronize$"),
    # catalog synchronisation: removes from the marketplace whatever VDP no longer has, and
    # with proceedWithConflicts=SERVER overwrites descriptions edited in the marketplace.
    # The per-type form (DATABASES, VIEWS, WEBSERVICES, EXTERNAL_ELEMENTS) does the same as
    # the "all" form for its own type.
    re.compile(r"^/public/api/element-management/all/synchronize(?:/all-servers)?$"),
    re.compile(r"^/public/api/element-management/[A-Za-z_]+/synchronize(?:-async)?$"),
    # importing external elements: an element missing from the interface view's snapshot is
    # deleted, together with its tags and categories
    re.compile(r"^/public/api/external-tool-servers/synchronize(?:-all)?(?:-async)?$"),
    re.compile(r"^/public/api/external-tool-servers/[^/]+/synchronize(?:-async)?$"),
    # "set" semantics on a view's own tags and categories: the previous set is discarded.
    # The additive twins are /tags/{id}/views and /category-management/add/views/{id}/categories.
    re.compile(r"^/public/api/views/[^/]+/tags$"),
    re.compile(r"^/public/api/category-management/views/[^/]+/categories$"),
)


def classify_vql(statement: str) -> str | None:
    """``"drop"``, ``"alter"``, ``"delete"`` for destructive statements, ``"procedure"`` for
    a call of a predefined procedure that changes state, else ``None``."""
    body = _LEADING_NOISE.sub("", statement, count=1)
    match = re.match(r"([A-Za-z_]+)", body)
    if not match:
        return None
    kind = _VQL_KINDS.get(match.group(1).upper())
    if kind:
        return kind
    for call in _PROCEDURE_CALL.finditer(body):
        if call.group(1).upper() in STATE_CHANGING_PROCEDURES:
            return "procedure"
    return None


def classify_http(method: str, path: str, body=None) -> str | None:
    """``"delete"`` for any DELETE, ``"replace"`` for set-replacing POSTs, else ``None``."""
    method = method.upper()
    route = urlsplit(path).path.rstrip("/")
    if method == "DELETE":
        return "delete"
    if method == "POST" and any(p.match(route) for p in _REPLACING_POSTS):
        return "replace"
    return None
