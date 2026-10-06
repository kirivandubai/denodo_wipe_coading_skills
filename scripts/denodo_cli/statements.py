"""What one VQL statement does to which object — the input of ``vql plan`` and of the ledger.

Not a VQL parser: a tokenizer and a handful of statement shapes, enough to name the object a
statement creates, changes, drops, writes or reads a cache of, and the objects a security or
tag statement names. Anything else is ``action = "other"``, and the plan says it does not
recognise it rather than guessing. The safety classifier (``safety.py``) stays the source of
the ``destructive`` kind; this module adds the *what* and the *whose* the classifier cannot see.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .safety import STATE_CHANGING_PROCEDURES, _CACHE_WRITE

# Element types as GET_ELEMENTS() names them; databases, roles and users are listed elsewhere.
GLOBAL_TYPES = frozenset({"database", "tag", "globalSecurityPolicy", "role", "user"})


@dataclass(frozen=True)
class ObjectRef:
    type: str                 # database, folder, datasource, wrapper, view, association, tag, ...
    database: str | None      # None for a database and for the server-wide types
    name: str                 # a folder's name is its path
    # 'derived view', 'summary', 'jdbc' … — informative, not part of identity
    kind: str | None = field(default=None, compare=False)

    def key(self) -> tuple[str, str | None, str]:
        return (self.type, self.database.lower() if self.database else None, self.name.lower())

    def label(self) -> str:
        return self.name if self.database is None else f"{self.database}.{self.name}"


@dataclass
class Statement:
    text: str
    action: str                       # read, session, create, alter, rename, drop, insert, update,
                                      # delete, refresh, call, cache, setting, other
    obj: ObjectRef | None = None
    or_replace: bool = False
    new_name: str | None = None       # ALTER … RENAME
    connect: str | None = None        # CONNECT DATABASE
    tags_assigned: list[str] = field(default_factory=list)
    tag_targets: list[tuple[str, str]] = field(default_factory=list)   # (database, view)
    endpoints: list[tuple[str, str]] = field(default_factory=list)     # (database, view) of an association
    identifiers: list[str] = field(default_factory=list)  # names a security statement may touch
    procedure: str | None = None
    proc_args: list[str] = field(default_factory=list)
    proc_named: dict[str, str] = field(default_factory=dict)
    cache_view: tuple[str, str] | None = None
    ai_over_rows: bool = False
    load_immediate: bool | None = None


# --- tokens ---------------------------------------------------------------------------------

_TOKEN = re.compile(
    r"\s+|(?P<str>'(?:[^']|'')*'?)|(?P<qid>\"[^\"]*\"?)|(?P<word>[A-Za-z_][A-Za-z0-9_$]*)"
    r"|(?P<num>\d+(?:\.\d+)?)|(?P<punct>.)",
    re.DOTALL,
)


@dataclass(frozen=True)
class _Tok:
    kind: str     # str, qid, word, num, punct
    value: str    # a literal without its quotes, a word as written

    @property
    def up(self) -> str:
        return self.value.upper() if self.kind == "word" else ""

    def is_name(self) -> bool:
        return self.kind in ("word", "qid")


def _tokens(text: str) -> list[_Tok]:
    out: list[_Tok] = []
    for m in _TOKEN.finditer(text):
        if m.group("str") is not None:
            raw = m.group("str")
            body = raw[1:-1] if len(raw) > 1 and raw.endswith("'") else raw[1:]
            out.append(_Tok("str", body.replace("''", "'")))
        elif m.group("qid") is not None:
            out.append(_Tok("qid", m.group("qid").strip('"')))
        elif m.group("word") is not None:
            out.append(_Tok("word", m.group("word")))
        elif m.group("num") is not None:
            out.append(_Tok("num", m.group("num")))
        elif m.group("punct") is not None:
            out.append(_Tok("punct", m.group("punct")))
    return out


def _words(toks: list[_Tok], i: int, *words: str) -> bool:
    return all(i + k < len(toks) and toks[i + k].up == w for k, w in enumerate(words))


def _qname(toks: list[_Tok], i: int) -> tuple[list[str], int]:
    """A dotted name starting at ``i``: its parts and the index after it."""
    parts: list[str] = []
    if i < len(toks) and toks[i].is_name():
        parts.append(toks[i].value)
        i += 1
        while i + 1 < len(toks) and toks[i].value == "." and toks[i + 1].is_name():
            parts.append(toks[i + 1].value)
            i += 2
    return parts, i


# --- object kinds ---------------------------------------------------------------------------

# (keywords, element type, kind); the longer shapes first.
_KINDS = (
    (("GLOBAL_SECURITY_POLICY",), "globalSecurityPolicy", None),
    (("INTERFACE", "VIEW"), "view", "interface view"),
    (("METRIC", "VIEW"), "view", "metric view"),
    (("SUMMARY", "VIEW"), "view", "summary"),
    (("MATERIALIZED", "TABLE"), "view", "materialized table"),
    (("REMOTE", "TABLE"), "view", "remote table"),
    (("VQL", "PROCEDURE"), "storedProcedure", "vql procedure"),
    (("VIEW",), "view", "derived view"),
    (("TABLE",), "view", "base view"),
    (("DATABASE",), "database", None),
    (("FOLDER",), "folder", None),
    (("ASSOCIATION",), "association", None),
    (("TAG",), "tag", None),
    (("ROLE",), "role", None),
    (("USER",), "user", None),
    (("PROCEDURE",), "storedProcedure", None),
)
_WITH_SUBTYPE = {"DATASOURCE": "datasource", "WRAPPER": "wrapper"}


def _object(toks: list[_Tok], i: int, database: str | None) -> tuple[ObjectRef | None, int]:
    """The object named at ``i`` (after CREATE [OR REPLACE] / ALTER / DROP)."""
    etype = kind = None
    for words, t, k in _KINDS:
        if _words(toks, i, *words):
            etype, kind, i = t, k, i + len(words)
            break
    else:
        if i + 1 < len(toks) and toks[i].up in _WITH_SUBTYPE and toks[i + 1].kind == "word":
            etype, kind, i = _WITH_SUBTYPE[toks[i].up], toks[i + 1].value.lower(), i + 2
        elif i < len(toks) and toks[i].kind == "word":
            etype, i = toks[i].value.lower(), i + 1
        else:
            return None, i
    if _words(toks, i, "IF", "EXISTS"):
        i += 2
    if etype == "folder":
        if i < len(toks) and toks[i].kind == "str":
            return ObjectRef("folder", database, toks[i].value.lower()), i + 1
        return None, i
    parts, i = _qname(toks, i)
    if not parts:
        return None, i
    if etype in GLOBAL_TYPES:
        return ObjectRef(etype, None, parts[-1], kind), i
    db = parts[0] if len(parts) > 1 else database
    return ObjectRef(etype, db, parts[-1], kind), i


# Words that are never the name of an object a security statement touches.
_KEYWORDS = frozenset("""
CREATE OR REPLACE ALTER DROP ROLE USER GRANT REVOKE ON TO CONNECT EXECUTE METADATA WRITE INSERT
UPDATE DELETE CREATE_VIEW CREATE_DATA_SOURCE CREATE_FOLDER FILE ADMIN ALL PRIVILEGES DATABASE VIEW
GLOBAL_SECURITY_POLICY DESCRIPTION ENABLED TRUE FALSE AUDIENCE ANY ROLES USERS ELEMENTS
VIEW_DATABASES VIEWS COLUMNS TAGGED RESTRICTION FILTER MASKING WITH HIDE REJECT DENY TEXTS
NUMBERS DATETIMES REDACT_ASTERISK ROUND EXTERNAL PASSWORD ENCRYPTED TAG TAGS ADD_TO REMOVE_FROM
EXCEPT NOT AND IS NULL PRIORITY ADMINISTRATOR ASSIGNPRIVILEGES CHOWN TYPE
""".split())


def _identifiers(toks: list[_Tok]) -> list[str]:
    names: list[str] = []
    i = 0
    while i < len(toks):
        if toks[i].is_name():
            parts, j = _qname(toks, i)
            name = ".".join(parts)
            if not (len(parts) == 1 and toks[i].kind == "word" and toks[i].up in _KEYWORDS):
                if name.lower() not in names:
                    names.append(name.lower())
            i = j
        else:
            i += 1
    return names


def _paren_group(toks: list[_Tok], i: int) -> tuple[list[_Tok], int]:
    """Tokens inside the parentheses opening at ``i``; the index after the closing one."""
    if i >= len(toks) or toks[i].value != "(":
        return [], i
    depth, j = 0, i
    while j < len(toks):
        if toks[j].kind == "punct" and toks[j].value == "(":
            depth += 1
        elif toks[j].kind == "punct" and toks[j].value == ")":
            depth -= 1
            if depth == 0:
                return toks[i + 1:j], j + 1
        j += 1
    return toks[i + 1:], j


def _names_in(group: list[_Tok]) -> list[list[str]]:
    out, i = [], 0
    while i < len(group):
        parts, j = _qname(group, i)
        if parts:
            out.append(parts)
            i = j
        else:
            i += 1
    return out


def _tag_assignment(toks: list[_Tok], database: str | None, st: Statement) -> None:
    """``ADD_TO ( VIEWS ( … ) COLUMNS ( … ) )`` and ``REMOVE_FROM`` of a tag statement."""
    for i, tok in enumerate(toks):
        if tok.up not in ("ADD_TO", "REMOVE_FROM"):
            continue
        group, _ = _paren_group(toks, i + 1)
        k = 0
        while k < len(group):
            if group[k].up in ("VIEWS", "COLUMNS"):
                columns = group[k].up == "COLUMNS"
                inner, k = _paren_group(group, k + 1)
                for parts in _names_in(inner):
                    view_parts = parts[:-1] if columns else parts
                    if not view_parts:
                        continue
                    db = view_parts[0] if len(view_parts) > 1 else database
                    target = (db, view_parts[-1])
                    if target not in st.tag_targets:
                        st.tag_targets.append(target)
            else:
                k += 1


def _endpoints(toks: list[_Tok], database: str | None) -> list[tuple[str, str]]:
    """The two views of ``ENDPOINT <role> <view> [PRINCIPAL] (<multiplicity>)``."""
    out: list[tuple[str, str]] = []
    for i, tok in enumerate(toks):
        if tok.up != "ENDPOINT" or i + 2 >= len(toks) or not toks[i + 1].is_name():
            continue
        parts, _ = _qname(toks, i + 2)
        if parts:
            out.append((parts[0] if len(parts) > 1 else database, parts[-1]))
    return out


def _column_tags(toks: list[_Tok]) -> list[str]:
    tags: list[str] = []
    for i, tok in enumerate(toks):
        if tok.up == "TAGS":
            group, _ = _paren_group(toks, i + 1)
            for parts in _names_in(group):
                if parts[-1].lower() not in tags:
                    tags.append(parts[-1].lower())
    return tags


def _named_arguments(toks: list[_Tok]) -> dict[str, str]:
    named: dict[str, str] = {}
    for i in range(len(toks) - 2):
        if toks[i].kind == "word" and toks[i + 1].value == "=" and toks[i + 2].kind in ("str", "word", "num"):
            named.setdefault(toks[i].value.lower(), toks[i + 2].value if toks[i + 2].kind != "word"
                             else toks[i + 2].value.lower())
    return named


def _from_target(toks: list[_Tok], database: str | None) -> tuple[str, str] | None:
    for i, tok in enumerate(toks):
        if tok.up == "FROM":
            parts, j = _qname(toks, i + 1)
            if parts and not (j < len(toks) and toks[j].value == "("):
                return (parts[0] if len(parts) > 1 else database, parts[-1])
    return None


_AI_CALL = re.compile(r"\b(?:[A-Za-z]+_AI|EMBED_AI|VECTOR_DISTANCE)\s*\(", re.IGNORECASE)


def _over_dual(toks: list[_Tok]) -> bool:
    return any(tok.up == "FROM" and i + 1 < len(toks) and toks[i + 1].up == "DUAL"
               for i, tok in enumerate(toks))


def _procedure(toks: list[_Tok]) -> tuple[str | None, list[str]]:
    """``CALL name(…)`` or ``… FROM name(…)``: the name (upper) and the positional literals."""
    for i, tok in enumerate(toks):
        start = (i == 0 and tok.up == "CALL") or tok.up == "FROM"
        if not start:
            continue
        parts, j = _qname(toks, i + 1)
        if parts and j < len(toks) and toks[j].value == "(":
            group, _ = _paren_group(toks, j)
            return parts[-1].upper(), [t.value for t in group if t.kind == "str"]
    return None, []


# --- the statement --------------------------------------------------------------------------

def parse_statement(text: str, database: str | None) -> Statement:
    """What ``text`` does, read in the context of the current ``database``."""
    toks = _tokens(text)
    if not toks:
        return Statement(text, "other")
    head = toks[0].up

    if head == "CREATE":
        i = 1
        or_replace = _words(toks, i, "OR", "REPLACE")
        if or_replace:
            i += 2
        obj, _ = _object(toks, i, database)
        st = Statement(text, "create", obj, or_replace=or_replace)
        if obj is None:
            st.action = "other"
            return st
        st.identifiers = _identifiers(toks)
        if obj.type == "tag":
            _tag_assignment(toks, database, st)
            if st.tag_targets:
                st.tags_assigned = [obj.name.lower()]
        elif obj.type == "association":
            st.endpoints = _endpoints(toks, obj.database)
        elif obj.type == "view":
            st.tags_assigned = _column_tags(toks)
            if st.tags_assigned:
                st.tag_targets = [(obj.database, obj.name)]
            if obj.kind == "summary":
                named = _named_arguments(toks)
                st.load_immediate = named.get("data_load_immediate", "true") != "false"
        return st

    if head == "ALTER":
        if _words(toks, 1, "SESSION"):
            return Statement(text, "session")
        obj, i = _object(toks, 1, database)
        st = Statement(text, "alter", obj)
        if obj is None:
            st.action = "other"
            return st
        st.identifiers = _identifiers(toks)
        for k in range(i, len(toks) - 1):
            if toks[k].up == "RENAME" and toks[k + 1].is_name():
                st.action, st.new_name = "rename", toks[k + 1].value
                break
        if obj.type == "tag":
            _tag_assignment(toks, database, st)
            if st.tag_targets:
                st.tags_assigned = [obj.name.lower()]
        elif obj.type == "view":
            st.tags_assigned = _column_tags(toks)
            if st.tags_assigned:
                st.tag_targets = [(obj.database, obj.name)]
        return st

    if head == "DROP":
        obj, _ = _object(toks, 1, database)
        return Statement(text, "drop" if obj else "other", obj)

    if head in ("INSERT", "DELETE"):
        i = 2 if (len(toks) > 1 and toks[1].up in ("INTO", "FROM")) else 1
        parts, _ = _qname(toks, i)
        obj = ObjectRef("view", parts[0] if len(parts) > 1 else database, parts[-1]) if parts else None
        return Statement(text, head.lower(), obj)

    if head == "UPDATE":
        parts, _ = _qname(toks, 1)
        obj = ObjectRef("view", parts[0] if len(parts) > 1 else database, parts[-1]) if parts else None
        return Statement(text, "update", obj)

    if head == "REFRESH":
        parts, _ = _qname(toks, 1)
        obj = ObjectRef("view", parts[0] if len(parts) > 1 else database, parts[-1]) if parts else None
        return Statement(text, "refresh" if obj else "other", obj)

    if head == "CONNECT":
        if _words(toks, 1, "DATABASE") and len(toks) > 2 and toks[2].is_name():
            return Statement(text, "session", connect=toks[2].value)
        return Statement(text, "session")

    if head == "SET":
        quoted = len(toks) > 1 and toks[1].kind == "str"
        return Statement(text, "setting" if quoted else "session")

    if head == "WEBCONTAINER":
        return Statement(text, "read" if _words(toks, 1, "STATUS") else "setting")

    if head in ("GRANT", "REVOKE", "CHOWN"):
        return Statement(text, "alter", identifiers=_identifiers(toks))

    if head in ("SELECT", "CALL", "DESC", "DESCRIBE", "LIST", "WITH", "EXPLAIN"):
        st = Statement(text, "read")
        name, args = _procedure(toks)
        if name in STATE_CHANGING_PROCEDURES:
            st.action, st.procedure, st.proc_args = "call", name, args
            st.proc_named = _named_arguments(toks)
        if _CACHE_WRITE.search(text):
            st.cache_view = _from_target(toks, database)
            if st.action == "read" and st.cache_view:
                st.action = "cache"
        if head == "SELECT" and _AI_CALL.search(text) and not _over_dual(toks):
            st.ai_over_rows = True
        return st

    return Statement(text, "other")
