"""Classify operations that destroy or overwrite existing objects, or change state outside
the agent's own project.

The execution layer does not decide whether an operation is allowed — that is the
core skill's job (design spec, section 6.3). It only makes the classification explicit:
every result carries ``destructive``, and on a profile marked ``production = true`` a
destructive operation is refused unless ``--allow-destructive`` is passed.

Destructive means: it destroys or overwrites something that exists (a text classifier cannot
tell whose object it is, so every ``DROP`` and ``ALTER`` counts), or it changes state outside
the agent's own project — server settings, data in sources, objects of other databases,
global objects. ``CREATE`` of a new object is not. The classifier is a deny list and never
complete; a skill that teaches a state-changing statement extends it in the same change.

VQL is classified by its leading keyword, then by the name of the procedure it calls, then by
its CONTEXT: the predefined procedures that change state (``DROP_REMOTE_TABLE``,
``CLEAN_CACHE_DATABASE``, ``GENERATE_STATS`` …) are invoked with ``SELECT … FROM name(…)`` or
``CALL name(…)`` (T20), and a query that loads or invalidates a view's cache is a ``SELECT``
with ``'cache_preload'`` or ``'cache_invalidate'`` in its CONTEXT (T27) — the keyword alone
lets both through. A ``CREATE`` of a user, a role or a global security policy, a ``CHOWN`` and
a ``CREATE DATABASE`` that carries a ``GRANT`` change who may read what across the server, and
``CREATE OR REPLACE`` of an existing role or user adds to it rather than replacing it (T31).
A remote table and a summary are tables in a source database: ``CREATE [OR REPLACE] REMOTE
TABLE`` and ``CREATE [OR REPLACE] SUMMARY VIEW`` create one there and load it, and ``REFRESH``
empties one and loads it again; ``CREATE OR REPLACE MATERIALIZED TABLE`` empties a table whose
rows exist nowhere else (T34).
HTTP calls are classified by method and path, never
by words in the body: the Data Marketplace has ``POST`` endpoints that overwrite whole sets
(spike T11, section 6). The Scheduler (T36) has its own rules: every ``PUT`` replaces a
definition or a setting that exists, a status change starts, stops, enables or disables a job,
and a new job is classified by what it will run on every trigger with nobody watching — a cache
job loads view caches, a VDP job runs its VQL (classified as VQL) and writes what its
exporters write — a table, an index or a file. That is the one place a body is read: the VQL is
the operation.
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
    # a write through a view changes the data in the source behind it; VQL has no MERGE,
    # its merge is INSERT … ON DUPLICATE KEY UPDATE
    "INSERT": "write",
    "UPDATE": "write",
    # SET '<property>' = … rewrites VDBConfiguration.properties of the whole server;
    # WEBCONTAINER sets, stops, starts or reloads the embedded web container
    "SET": "setting",
    "WEBCONTAINER": "setting",
    # the owner of an element decides who may change it and grant on it
    "CHOWN": "security",
    # empties the table behind a remote table or a summary in its source database and loads the
    # result of the stored query into it again
    "REFRESH": "table",
}
# Forms that start with one of the keywords above but only touch the caller's session or
# only read: the ODBC connection settings (SET QUERYTIMEOUT TO …), ALTER SESSION, and
# WEBCONTAINER STATUS. Any other SET counts as a server setting.
_HARMLESS_FORMS = re.compile(
    r"SET\s+[A-Za-z_][A-Za-z0-9_]*\s+TO\b|ALTER\s+SESSION\b|WEBCONTAINER\s+STATUS\b",
    re.IGNORECASE,
)

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
    "COMPACT_CACHE",
    "REFRESH_BASE_VIEW",
    "CREATE_TAGS_FROM_VIEW",
    "CREATE_TAGS_FROM_COLLIBRA",
    "LOGCONTROLLER",
    "GENERATE_STATS_FOR_FIELDS",
    "GENERATE_SMART_STATS_FOR_FIELDS",
    "COMPUTE_SOURCE_TABLE_STATS",
    "MAINTAIN_METADATA_TABLES",
})
# ``FROM name(`` anywhere in the statement (a view defined over the procedure would run it
# on every query), ``CALL name(`` at the start; an optional ``database.`` qualifier.
_PROCEDURE_CALL = re.compile(
    r"(?:\bFROM\s+|^CALL\s+)(?:[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.IGNORECASE,
)

# A query that writes the cache of a view instead of reading it. 'cache_invalidate' deletes
# cached rows (all of them with 'all_rows') before the result is stored; 'cache_preload' =
# 'true' without it appends the result to what is cached, so a second run duplicates every
# row. 'cache' = 'off' and the other cache parameters only change how the query reads. The
# quoted name has to be followed by '=': a doubled quote inside a string literal does not match.
_CACHE_WRITE = re.compile(r"'cache_invalidate'\s*=|'cache_preload'\s*=\s*'true'", re.IGNORECASE)

# Server-wide security objects. CREATE OR REPLACE of an existing role or user keeps every grant
# and role it already had and adds the new ones (checked on 9.5.1), so the statement is never a
# clean "create"; a global security policy restricts every view its tags reach, in every
# database it names. A CREATE DATABASE with a GRANT or REVOKE clause changes privileges too.
_SECURITY_CREATE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:USER|ROLE|GLOBAL_SECURITY_POLICY)\b", re.IGNORECASE)
_DATABASE_CREATE = re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?DATABASE\b", re.IGNORECASE)
# A table in a source database, created and loaded by the statement itself; OR REPLACE drops a
# table of that name first, whoever made it. A materialized table keeps rows that were inserted
# into it and exist nowhere else: OR REPLACE over one empties it (checked on 9.5.1), while a plain
# CREATE is refused when the name exists.
_SOURCE_TABLE_CREATE = re.compile(
    r"CREATE\s+(?:(?:OR\s+REPLACE\s+)?(?:REMOTE\s+TABLE|SUMMARY\s+VIEW)|OR\s+REPLACE\s+MATERIALIZED\s+TABLE)\b",
    re.IGNORECASE)
_GRANT_CLAUSE = re.compile(r"\b(?:GRANT|REVOKE)\b", re.IGNORECASE)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")

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
    # the same "set" semantics on a view's property groups, and a group left out of the body
    # takes the view's values for its properties with it (T30, checked live on 9.5.1)
    re.compile(r"^/public/api/property-management/views/[^/]+/groups$"),
)


def classify_vql(statement: str) -> str | None:
    """``"drop"``, ``"alter"``, ``"delete"`` for destructive statements, ``"write"`` for a
    write into a source, ``"setting"`` for a change of server configuration, ``"procedure"``
    for a call of a predefined procedure that changes state, ``"cache"`` for a query that
    loads or invalidates the cache of a view, ``"security"`` for a statement that creates a
    user, a role or a global security policy, changes an owner, or grants in ``CREATE
    DATABASE``, ``"table"`` for one that creates, replaces or reloads a table in a source
    database (a remote table, a summary, ``REFRESH``) or replaces a materialized table, else
    ``None``."""
    body = _LEADING_NOISE.sub("", statement, count=1)
    match = re.match(r"([A-Za-z_]+)", body)
    if not match:
        return None
    kind = _VQL_KINDS.get(match.group(1).upper())
    if kind and not _HARMLESS_FORMS.match(body):
        return kind
    if _SECURITY_CREATE.match(body):
        return "security"
    if _SOURCE_TABLE_CREATE.match(body):
        return "table"
    if _DATABASE_CREATE.match(body) and _GRANT_CLAUSE.search(_STRING_LITERAL.sub("''", body)):
        return "security"
    for call in _PROCEDURE_CALL.finditer(body):
        if call.group(1).upper() in STATE_CHANGING_PROCEDURES:
            return "procedure"
    if _CACHE_WRITE.search(body):
        return "cache"
    return None


# The Scheduler's REST API (T36, checked against the 9.5.1 OpenAPI of the administration tool).
_SCHEDULER_STATUS = re.compile(r"^/public/api/projects/[^/]+/jobs(?:/[^/]+)?/status$")
_SCHEDULER_NEW_JOB = re.compile(r"^/public/api/projects/[^/]+/jobs$")
_SCHEDULER_DELETE_POSTS = re.compile(r"^/public/api/reports/delete-(?:batch|by-job-batch)$")
_SCHEDULER_SECURITY = re.compile(
    r"^/public/api/(?:roles(?:/.*)?|changePassword|tool-configuration/(?:change|reset)-password)$")
_SCHEDULER_SETTINGS = re.compile(
    r"^/public/api/(?:configuration|tool-configuration)(?:/.*)?$|^/public/api/(?:drivers|plugins)$")


def _classify_scheduler(method: str, route: str, body) -> str | None:
    if method == "DELETE" or (method == "POST" and _SCHEDULER_DELETE_POSTS.match(route)):
        return "delete"
    if _SCHEDULER_SECURITY.match(route) and method in ("POST", "PUT"):
        return "security"
    if route == "/public/api/serverMetadata/import" and method == "POST":
        return "replace"  # the whole metadata of the server: projects, jobs, data sources
    if _SCHEDULER_SETTINGS.match(route) and method in ("POST", "PUT"):
        return "setting"
    if method == "PUT":
        return "job" if _SCHEDULER_STATUS.match(route) else "alter"
    if method == "POST" and _SCHEDULER_NEW_JOB.match(route):
        return _classify_scheduler_job(body)
    return None


def _classify_scheduler_job(body) -> str | None:
    """What a new job will do on every trigger: load caches, or run its VQL and export it."""
    if not isinstance(body, dict):
        return None
    kind = str(body.get("type") or "").upper()
    if kind in ("VDPCACHE", "VDPDAGLOAD"):
        return "cache"
    if kind == "VDPDATALOAD":
        return "table"
    if kind != "VDP":
        return None
    extraction = (body.get("extractionSection") or {}).get("extractionData") or {}
    query_kind = classify_vql(str(extraction.get("parameterizedQuery") or ""))
    if query_kind:
        return query_kind
    # Every exporter writes outside Denodo: a table, an index, or a file on the Scheduler host that
    # each run overwrites — and that an empty run with allowEmptyFile false deletes (T36).
    if (body.get("exportationSection") or {}).get("exporters"):
        return "write"
    return None


def classify_http(method: str, path: str, body=None, server: str = "marketplace") -> str | None:
    """For the Data Marketplace: ``"delete"`` for any DELETE, ``"replace"`` for set-replacing
    POSTs. For the Scheduler: ``"delete"``, ``"alter"`` for a PUT that replaces a job, a project
    or a data source, ``"job"`` for starting, stopping, enabling or disabling jobs, the kind of
    what a new job will run (``"cache"``, ``"table"``, a VQL kind, or ``"write"`` for any exporter), ``"setting"``,
    ``"security"`` and ``"replace"`` for server configuration, roles and a metadata import.
    Else ``None``."""
    method = method.upper()
    route = urlsplit(path).path.rstrip("/")
    if server == "scheduler":
        return _classify_scheduler(method, route, body)
    if method == "DELETE":
        return "delete"
    if method == "POST" and any(p.match(route) for p in _REPLACING_POSTS):
        return "replace"
    return None
