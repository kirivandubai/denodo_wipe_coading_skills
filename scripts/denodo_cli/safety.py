"""Classify operations that destroy or overwrite existing objects.

The execution layer does not decide whether an operation is allowed — that is the
core skill's job (design spec, section 6.3). It only makes the classification explicit:
every result carries ``destructive``, and on a profile marked ``production = true`` a
destructive operation is refused unless ``--allow-destructive`` is passed.

VQL is classified by its leading keyword. HTTP calls are classified by method and path,
never by words in the body: the Data Marketplace has ``POST`` endpoints that overwrite
whole sets (spike T11, section 6).
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

# POST endpoints that replace a whole set instead of adding to it (T11, section 6).
_REPLACING_POSTS = (
    re.compile(r"^/public/api/tags/vdp/synchronize$"),
    re.compile(r"^/public/api/element-management/all/synchronize$"),
    re.compile(r"^/public/api/views/[^/]+/tags$"),
    re.compile(r"^/public/api/views/[^/]+/categories$"),
)


def classify_vql(statement: str) -> str | None:
    """``"drop"``, ``"alter"``, ``"delete"`` for destructive statements, else ``None``."""
    body = _LEADING_NOISE.sub("", statement, count=1)
    match = re.match(r"([A-Za-z_]+)", body)
    if not match:
        return None
    return _VQL_KINDS.get(match.group(1).upper())


def classify_http(method: str, path: str, body=None) -> str | None:
    """``"delete"`` for any DELETE, ``"replace"`` for set-replacing POSTs, else ``None``."""
    method = method.upper()
    route = urlsplit(path).path.rstrip("/")
    if method == "DELETE":
        return "delete"
    if method == "POST" and any(p.match(route) for p in _REPLACING_POSTS):
        return "replace"
    return None
