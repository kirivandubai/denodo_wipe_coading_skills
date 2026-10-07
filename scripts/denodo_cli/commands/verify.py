"""``verify``: run the v1 chain of skill templates against a live server and clean up.

The plan is data (``verification/chain.toml``), the mechanics are here. A step either
points at a block of a skill (``template`` — the thing being verified) or carries its own
body (``fixture`` — scaffolding that makes the chain reachable). Substitutions are exact
strings, and one that does not occur in the block is an error: silently skipping it would
send the run into somebody else's database.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import secrets
import shlex
import subprocess
import tempfile
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import EXIT_EXECUTION, EXIT_OK, EXIT_USAGE
from .api import api_call, parse_multipart_specs
from .secret import encrypt_password
from .testing import run_testing_tool
from .vql import run_statements
from ..features import (FEATURE_NAMES, FEATURE_REASONS, can_impersonate, feature_state, is_admin,
                        read_features, scheduler_data_source, server_values)
from ..output import envelope
from ..profiles import Profile, profiles_path
from ..templates import TemplateError, format_mark, load_block, update_mark
from ..vql_split import split_statements

KINDS = ("template", "fixture")
CHANNELS = ("vql", "http", "denodotest")
EXPECTS = ("rows", "no rows")
THROWAWAY = "@encrypt-throwaway"
# T40: a value that belongs to an installation is filled in by the run — from what the server
# says, or from the manifest's table for the write data source's product.
SERVER = "@server"
DIALECT = "@dialect"
HTTP_SERVERS = ("marketplace", "scheduler")
PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
# A catalog synchronisation of the marketplace (safety.py: it replaces a whole set), and the two
# halves of the catalog whose pending changes it would take along.
CATALOG_SYNC = re.compile(r"^/public/api/element-management/[A-Za-z_]+/synchronize(?:-async|/all-servers)?$")
CATALOG_HALVES = ("DATABASES", "VIEWS")


class ChainError(Exception):
    """The manifest is malformed or a substitution does not apply. Message is user-facing."""


@dataclass(frozen=True)
class Step:
    id: str
    kind: str
    channel: str
    address: str | None = None
    vql: str | None = None
    calls: list[int] = field(default_factory=list)
    substitute: dict[str, str] = field(default_factory=dict)
    capture: dict[str, str] = field(default_factory=dict)
    expect_body: dict[str, str] = field(default_factory=dict)
    check: str | None = None
    expect: str = "rows"
    marketplace: bool = False
    ai: bool = False
    writes: bool = False
    database: str | None = None
    # T36, the Scheduler tail: its own gate; a file an api call reads (--json-file) mapped to
    # a block of a skill; which call's body a capture reads; waiting for a started job.
    scheduler: bool = False
    files: dict[str, dict] = field(default_factory=dict)
    capture_from: int | None = None
    poll: dict | None = None
    # T40: the features of the server the step needs (features.FEATURE_NAMES); a step whose
    # feature the server is known to lack is skipped with the reason.
    requires: list[str] = field(default_factory=list)
    # The earlier steps whose objects this one uses: when one of them was skipped, so is this
    # one, with that step's reason (T40) — a skip must not turn into a failure further down.
    needs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Chain:
    values: dict[str, str]
    steps: list[Step]
    cleanup: list[str] = field(default_factory=list)
    cleanup_http: list[dict] = field(default_factory=list)
    cleanup_writes: list[str] = field(default_factory=list)
    # T40: values that depend on the product of the write data source, one table per product
    # (``[dialects.sqlserver]``), and the marked blocks the chain does not run, with the reason.
    dialects: dict[str, dict[str, str]] = field(default_factory=dict)
    not_run: dict[str, str] = field(default_factory=dict)
    # The literal values an installation may replace from its values file (where the fixture
    # files are read from). Every other literal value is the chain's own.
    local_values: list[str] = field(default_factory=list)

    def known_values(self) -> set[str]:
        """Every value name the manifest declares: ``[values]`` and every dialect table's keys."""
        names = set(self.values)
        for table in self.dialects.values():
            names.update(table)
        return names

    def settable_values(self) -> set[str]:
        """The names a values file may set: what belongs to an installation — the ``@server`` and
        ``@dialect`` values, every dialect key, and ``local_values``. Never the test database, the
        prefix every server-wide object and every cleanup statement is named by, or a throwaway
        password: a values file that moved those would move what the run drops."""
        names = {name for name, value in self.values.items() if value in (SERVER, DIALECT)}
        for table in self.dialects.values():
            names.update(table)
        return names | set(self.local_values)


def load_chain(path: Path) -> Chain:
    try:
        document = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ChainError(f"cannot read chain manifest {path}: {exc}") from exc
    values = {str(k): str(v) for k, v in (document.get("values") or {}).items()}
    steps: list[Step] = []
    seen: set[str] = set()
    for raw in document.get("step") or []:
        step = _step(raw)
        if step.id in seen:
            raise ChainError(f"duplicate step id {step.id!r} in {path}")
        seen.add(step.id)
        steps.append(step)
    if not steps:
        raise ChainError(f"chain manifest {path} has no steps")
    cleanup_section = document.get("cleanup") or {}
    cleanup = [str(s) for s in cleanup_section.get("vql", [])]
    cleanup_http = _cleanup_http_entries(cleanup_section.get("http", []), path)
    cleanup_writes = cleanup_section.get("writes", [])
    if not isinstance(cleanup_writes, list) or not all(isinstance(s, str) for s in cleanup_writes):
        raise ChainError(f"[cleanup] writes in {path} must be a list of VQL statements, got {cleanup_writes!r}")
    by_id = {step.id: index for index, step in enumerate(steps)}
    for index, step in enumerate(steps):
        for needed in step.needs:
            if by_id.get(needed, index) >= index:
                raise ChainError(f"step {step.id!r} needs {needed!r}, which is not an earlier step of {path}")
    if "local_values" in (document.get("values") or {}):
        raise ChainError(f"local_values in {path} is a list at the top of the manifest, before [values], "
                         f"not a value inside it")
    local_values = document.get("local_values", [])
    if not isinstance(local_values, list) or not all(isinstance(name, str) and name in values for name in local_values):
        raise ChainError(f"local_values in {path} must list names of [values], got {local_values!r}")
    return Chain(values=values, steps=steps, cleanup=cleanup, cleanup_http=cleanup_http,
                 cleanup_writes=list(cleanup_writes), dialects=_dialects(document.get("dialects"), path),
                 not_run=_not_run(document.get("not_run"), path), local_values=list(local_values))


def _dialects(raw: object, path: Path) -> dict[str, dict[str, str]]:
    """``[dialects.<product>]`` — the values of the write steps one product spells its own way."""
    if raw is None:
        return {}
    if not isinstance(raw, dict) or not all(isinstance(table, dict) for table in raw.values()):
        raise ChainError(f"[dialects] in {path} must hold one table per product, got {raw!r}")
    dialects: dict[str, dict[str, str]] = {}
    for product, table in raw.items():
        if not all(isinstance(value, str) for value in table.values()):
            raise ChainError(f"[dialects.{product}] in {path} must map value names to strings, got {table!r}")
        dialects[str(product)] = {str(k): v for k, v in table.items()}
    return dialects


def _not_run(raw: object, path: Path) -> dict[str, str]:
    """``[not_run]`` — a marked block the chain does not run, keyed by its address, with why."""
    if raw is None:
        return {}
    if not isinstance(raw, dict) or not all(isinstance(reason, str) and reason for reason in raw.values()):
        raise ChainError(f"[not_run] in {path} must map block addresses to a reason, got {raw!r}")
    return {str(address): reason for address, reason in raw.items()}


def default_values_path() -> Path:
    """The local values file: beside the profiles file, so ``DENODO_PROFILES`` moves both."""
    return profiles_path().parent / "verify.toml"


def load_values_file(path: Path, profile_name: str, known: set[str],
                     own: set[str] | None = None) -> dict[str, str]:
    """The values the profile's own table of the local values file sets — ``{}`` without one.

    The file holds one table per profile (``[dev]``) because the values belong to an
    installation, and a profile names one. A key the manifest does not declare is refused,
    naming the file, the table and the known keys: a typo would otherwise change nothing and
    say nothing, and the run would go on with the value it was meant to replace. A key in
    ``own`` — a value of the chain itself, such as the test database — is refused too, saying
    why: it decides what the run creates and drops, and only the command line may change it.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ChainError(f"cannot read the values file {path}: {exc}") from exc
    table = document.get(profile_name)
    if table is None:
        return {}
    if not isinstance(table, dict):
        raise ChainError(f"[{profile_name}] in {path} must be a table of value = \"text\", got {table!r}")
    values: dict[str, str] = {}
    for key, value in table.items():
        if isinstance(value, (dict, list)):
            raise ChainError(f"{key} in [{profile_name}] of {path} must be a plain value, got {value!r}")
        if key in (own or set()):
            hint = " (--database names another test database)" if key == "database" else ""
            raise ChainError(f"{key!r} in [{profile_name}] of {path} is a value of the chain itself: it decides "
                             f"what the run creates and drops, so a values file may not change it{hint}; "
                             f"the values a file may set are: {', '.join(sorted(known))}")
        if key not in known:
            raise ChainError(f"{key!r} in [{profile_name}] of {path} is not a value of the chain; "
                             f"the values a file may set are: {', '.join(sorted(known))}")
        values[str(key)] = str(value)
    return values


def _cleanup_http_entries(raw: object, path: Path) -> list[dict]:
    """Validate ``[cleanup] http`` — a list of ``{method, path, params, json}`` tables.

    Shape errors are caught here, at load time, for the same reason ``_int_calls``
    validates ``calls``: a malformed manifest must fail as ``ChainError`` naming the
    manifest, not surface later as a bare ``KeyError``/``AttributeError`` from deep inside
    cleanup, after the chain has already touched the server.

    ``json`` is optional and holds the request body. Cleanup started out as a list of
    ``DELETE``s keyed on captured ids, which need none; undoing a marketplace catalog sync
    does need one, because the same ``POST .../synchronize`` call that imported the objects
    is also the only call that takes them back out, and it carries
    ``proceedWithConflicts``.
    """
    if not isinstance(raw, list):
        raise ChainError(f"[cleanup] http in {path} must be a list of tables, got {raw!r}")
    entries: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ChainError(f"[cleanup] http entry in {path} must be a table, got {item!r}")
        method, call_path = item.get("method"), item.get("path")
        if not isinstance(method, str) or not method:
            raise ChainError(f"[cleanup] http entry in {path} needs a string method, got {method!r}")
        if not isinstance(call_path, str) or not call_path:
            raise ChainError(f"[cleanup] http entry in {path} needs a string path, got {call_path!r}")
        params = {str(k): str(v) for k, v in (item.get("params") or {}).items()}
        body = item.get("json")
        if body is not None and not isinstance(body, dict):
            raise ChainError(f"[cleanup] http entry in {path} needs a table for json, got {body!r}")
        server = item.get("server", "marketplace")
        if server not in HTTP_SERVERS:
            raise ChainError(f"[cleanup] http entry in {path}: server must be one of {HTTP_SERVERS}, "
                             f"got {server!r}")
        entries.append({"server": server, "method": method, "path": call_path, "params": params, "json": body})
    return entries


def _step(raw: dict) -> Step:
    step_id = raw.get("id")
    # Not just falsy: a non-string id (e.g. a bare TOML integer) would build a Step whose
    # id violates the declared type, then poison the duplicate-id check and every later
    # report line that assumes a string.
    if not isinstance(step_id, str) or not step_id:
        raise ChainError(f"every step needs a non-empty string id, got {step_id!r}")
    kind, channel = raw.get("kind"), raw.get("channel")
    if kind not in KINDS:
        raise ChainError(f"step {step_id!r}: kind must be one of {KINDS}, got {kind!r}")
    if channel not in CHANNELS:
        raise ChainError(f"step {step_id!r}: channel must be one of {CHANNELS}, got {channel!r}")
    expect = raw.get("expect", "rows")
    if expect not in EXPECTS:
        raise ChainError(f"step {step_id!r}: expect must be one of {EXPECTS}, got {expect!r}")
    address = raw.get("address")
    if kind == "template" and not (isinstance(address, str) and address):
        raise ChainError(f"step {step_id!r}: a template step needs a string address")
    vql = raw.get("vql")
    if kind == "fixture" and not (isinstance(vql, str) and vql):
        raise ChainError(f"step {step_id!r}: a fixture step needs a string vql body")
    marketplace = bool(raw.get("marketplace", False))
    scheduler = bool(raw.get("scheduler", False))
    if channel == "http" and marketplace == scheduler:
        # Every http step writes server-wide objects — the shared marketplace catalog or the
        # Scheduler's projects and jobs — so each is behind its own flag and a default run
        # stays inside its database. Without a gate an http step would run on every run.
        raise ChainError(f"step {step_id!r}: an http-channel step must set exactly one of "
                         "marketplace = true or scheduler = true")
    if scheduler and channel != "http":
        raise ChainError(f"step {step_id!r}: scheduler = true only applies to an http-channel step")
    if channel == "denodotest" and marketplace:
        raise ChainError(f"step {step_id!r}: a denodotest step runs a test file against VDP; "
                         "marketplace = true does not apply")
    ai = bool(raw.get("ai", False))
    if ai and channel != "vql":
        # ai = true gates a VQL step that calls the server's LLM or embedding model; an http
        # step makes no such call, and the flag on it would claim a gate nothing enforces.
        raise ChainError(f"step {step_id!r}: ai = true only applies to a vql-channel step")
    writes = bool(raw.get("writes", False))
    if writes and channel == "http":
        # writes = true gates a step that needs the tables of a source database the manifest
        # names; an http step writes nothing there. A denodotest step may read them (T35).
        raise ChainError(f"step {step_id!r}: writes = true only applies to a vql or denodotest step")
    database = raw.get("database")
    if database is not None and not isinstance(database, str):
        raise ChainError(f"step {step_id!r}: database must be a string, got {database!r}")
    expect_body = raw.get("expect_body") or {}
    if not isinstance(expect_body, dict):
        raise ChainError(f"step {step_id!r}: expect_body must be a table of field = value, "
                         f"got {expect_body!r}")
    if expect_body and channel != "http":
        # Only an http step has a response body to compare; on a vql step the table would
        # be read by nothing and the run would report a check it never made.
        raise ChainError(f"step {step_id!r}: expect_body only applies to an http-channel step")
    files = _files(raw.get("files"), step_id)
    poll = _poll(raw.get("poll"), step_id)
    capture_from = raw.get("capture_from")
    if capture_from is not None and type(capture_from) is not int:
        raise ChainError(f"step {step_id!r}: capture_from must be an integer, got {capture_from!r}")
    if (files or poll or capture_from is not None) and channel != "http":
        raise ChainError(f"step {step_id!r}: files, poll and capture_from only apply to an http-channel step")
    requires = raw.get("requires", [])
    if not isinstance(requires, list) or not all(isinstance(name, str) for name in requires):
        raise ChainError(f"step {step_id!r}: requires must be a list of feature names, got {requires!r}")
    unknown = [name for name in requires if name not in FEATURE_NAMES]
    if unknown:
        raise ChainError(f"step {step_id!r}: requires names {unknown}, which are not features; "
                         f"the features are {', '.join(FEATURE_NAMES)}")
    needs = raw.get("needs", [])
    if not isinstance(needs, list) or not all(isinstance(name, str) and name for name in needs):
        raise ChainError(f"step {step_id!r}: needs must be a list of step ids, got {needs!r}")
    return Step(id=step_id, kind=kind, channel=channel, address=address, vql=vql,
                scheduler=scheduler, files=files, poll=poll, capture_from=capture_from,
                calls=_int_calls(raw.get("calls", []), step_id),
                substitute={str(k): str(v) for k, v in (raw.get("substitute") or {}).items()},
                capture={str(k): str(v) for k, v in (raw.get("capture") or {}).items()},
                expect_body={str(k): str(v) for k, v in expect_body.items()},
                check=raw.get("check"), expect=expect, marketplace=marketplace, ai=ai, writes=writes,
                database=database, requires=list(requires), needs=list(needs))


def _files(raw: object, step_id: str) -> dict[str, dict]:
    """``files = { "<path an api line names in --json-file>" = { address, substitute } }``.

    A Scheduler job is a JSON file in the project, created with ``--json-file``; in a skill
    the file is the json block beside the call. The step names which block stands for which
    path, so the run sends exactly the text the skill shows (T36).
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ChainError(f"step {step_id!r}: files must be a table of path = {{ address, substitute }}, got {raw!r}")
    files: dict[str, dict] = {}
    for path, spec in raw.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("address"), str) or not spec["address"]:
            raise ChainError(f"step {step_id!r}: files entry {path!r} needs a string address")
        substitute = spec.get("substitute") or {}
        if not isinstance(substitute, dict):
            raise ChainError(f"step {step_id!r}: files entry {path!r}: substitute must be a table")
        files[str(path)] = {"address": spec["address"],
                            "substitute": {str(k): str(v) for k, v in substitute.items()}}
    return files


def _poll(raw: object, step_id: str) -> dict | None:
    """``poll = { field, until, seconds, every }``: repeat the step's last call until ``field``
    of its answer equals ``until`` — a started Scheduler job runs on its own (T36)."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("field"), str) or "until" not in raw:
        raise ChainError(f"step {step_id!r}: poll needs a string field and an until value, got {raw!r}")
    seconds, every = raw.get("seconds", 120), raw.get("every", 2)
    if not all(isinstance(n, (int, float)) and not isinstance(n, bool) and n > 0 for n in (seconds, every)):
        raise ChainError(f"step {step_id!r}: poll seconds and every must be positive numbers")
    return {"field": raw["field"], "until": str(raw["until"]), "seconds": seconds, "every": every}


def _int_calls(raw_calls: object, step_id: str) -> list[int]:
    """Validate ``calls`` — indexes into a template's http calls.

    A bad manifest must fail as ``ChainError`` here, not as a bare ``ValueError`` from
    ``int()`` on a non-numeric string, and not as a silently truncated index from a float
    (``int(0.9) == 0`` would pick the wrong call without any error at all). ``bool`` is
    rejected too: it is an ``int`` subclass in Python, so a stray TOML ``true``/``false``
    would otherwise pass through as ``1``/``0``.
    """
    if not isinstance(raw_calls, list):
        raise ChainError(f"step {step_id!r}: calls must be a list of integers, got {raw_calls!r}")
    for item in raw_calls:
        if type(item) is not int:
            raise ChainError(f"step {step_id!r}: calls entries must be integers, got {item!r}")
    return list(raw_calls)


def render(text: str, substitute: dict[str, str], values: dict[str, str]) -> str:
    """Apply exact-string substitutions, then fill ``{value}`` placeholders."""
    out = text
    for needle, replacement in substitute.items():
        if needle not in out:
            raise ChainError(f"substitution {needle!r} does not occur in the block")
        out = out.replace(needle, replacement)
    for name in {m.group(1) for m in PLACEHOLDER.finditer("".join(substitute.values()))}:
        if name not in values:
            raise ChainError(f"substitution refers to unknown value {{{name}}}")
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), out)


def parse_api_calls(body: str) -> list[dict]:
    """``api <method> <path> [--param k=v] [--json '<text>'] [--part 'f=json:<text>']`` lines.

    A marketplace template block is not a script to run verbatim — it interleaves real
    calls with ``# ...`` commentary and ``# → ...`` response illustrations, and sometimes
    carries mutually exclusive alternatives (create *or* update). This only recognizes the
    lines that actually invoke ``api``; a step then picks which ones it means by index
    (``Step.calls``). ``--env`` is dropped: the profile the chain runs under supplies it,
    never the template text.

    Anything that does not parse raises ``ChainError``, never the bare ``ValueError`` /
    ``IndexError`` / ``JSONDecodeError`` it would otherwise surface as: this tool prints
    exactly one JSON document per invocation, and a traceback is not one. The input is a
    block of a skill file, so an ordinary skill edit — an unbalanced quote, a mistyped
    ``--json`` body, a half-deleted line — is exactly how one gets here.
    """
    joined = re.sub(r"\\\s*\n\s*", " ", body)
    return [_api_call(line) for line in _api_lines(joined)]


def _api_lines(text: str) -> list[str]:
    """The ``api ...`` lines of a block, each rejoined into one parseable line.

    Two different things wrap a call across lines, and only one of them is a backslash
    (already handled by the caller). The other is a quoted argument that simply contains
    newlines — how ``skills/marketplace/SKILL.md`` writes the external-tool-server body:

        api post /public/api/external-tool-servers \
            --json '{"type":"CUSTOM","name":"acme_bi_server",
                     "externalProviderTypeId":30}'

    That is ordinary shell — inside single quotes a newline is just a character, and a
    backslash there would land *inside* the JSON — so the block is right and a line-at-a-
    time reader is wrong: it used to hand ``shlex`` a fragment ending mid-quote and report
    the template as broken. A line is therefore extended with the ones after it until
    ``shlex`` can parse it. An argument that never closes swallows the rest of the block
    and is then reported by ``_api_call``, naming the line it started on — the same
    failure as before, still loud, and still pointing at where the quote opened.
    """
    lines: list[str] = []
    pending: str | None = None
    for line in text.splitlines():
        if pending is None:
            if not line.strip().startswith("api "):
                continue
            pending = line.strip()
        else:
            pending = f"{pending} {line.strip()}"
        if _parses(pending):
            lines.append(pending)
            pending = None
    if pending is not None:
        lines.append(pending)
    return lines


def _parses(line: str) -> bool:
    try:
        shlex.split(line)
    except ValueError:
        return False
    return True


def _api_call(line: str) -> dict:
    """One ``api ...`` line as ``{server, method, path, params, json, json_file, multipart}``.

    ``--part`` is parsed rather than dropped like the other flags this does not recognise
    (``--env`` and friends): the marketplace has exactly one multipart call — creating an
    external provider type — and dropping a flag drops its value too, which turned that
    line into a POST with an empty body and sent it that way. A step may leave a call out
    (``calls``); sending a call the template does not describe is a different thing.

    Flags may stand anywhere: the Scheduler's lines name their server first
    (``api --server scheduler post …``), so the method is the first word that is not a flag
    or a flag's value, and the path the second. ``--json-file`` is kept as a path, for the
    step's ``files`` to resolve.
    """
    try:
        tokens = shlex.split(line)[1:]
    except ValueError as exc:
        raise ChainError(f"api line {line!r} does not parse: {exc}") from exc
    positional: list[str] = []
    server = "marketplace"
    params: dict[str, str] = {}
    body_text: str | None = None
    json_file: str | None = None
    part_specs: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("-"):
            positional.append(token)
            index += 1
            continue
        if index + 1 >= len(tokens):
            raise ChainError(f"api line {line!r}: {token} has no value")
        value = tokens[index + 1]
        if token == "--param":
            key, _, param_value = value.partition("=")
            params[key] = param_value
        elif token == "--json":
            body_text = value
        elif token == "--json-file":
            json_file = value
        elif token == "--part":
            part_specs.append(value)
        elif token == "--server":
            if value not in HTTP_SERVERS:
                raise ChainError(f"api line {line!r}: --server must be one of {HTTP_SERVERS}, got {value!r}")
            server = value
        index += 2       # --env, and every other flag, is dropped together with its value
    if not positional:
        raise ChainError(f"api line {line!r} names no method")
    if len(positional) < 2:
        raise ChainError(f"api line {line!r} names no path")
    method, path = positional[0].upper(), positional[1]
    if body_text is not None and json_file is not None:
        raise ChainError(f"api line {line!r} gives both --json and --json-file")
    try:
        json_body = json.loads(body_text) if body_text else None
    except json.JSONDecodeError as exc:
        raise ChainError(f"api line {line!r}: --json body is not valid JSON: {exc}") from exc
    try:
        multipart = parse_multipart_specs(part_specs) if part_specs else None
    except (ValueError, json.JSONDecodeError) as exc:
        # parse_multipart_specs is the same parser `api --part` uses on the command line,
        # so a template and a hand-run call fail on the same inputs; only the wrapper
        # differs, because a manifest-level failure has to arrive as ChainError.
        raise ChainError(f"api line {line!r}: --part does not parse: {exc}") from exc
    return {"server": server, "method": method, "path": path, "params": params, "json": json_body,
            "json_file": json_file, "multipart": multipart}


def _select_calls(calls: list[dict], indexes: list[int]) -> list[dict]:
    """The calls ``indexes`` names, in that order — or all of them when it is empty.

    An index the block does not have used to raise a bare ``IndexError``, and deleting a
    single ``api`` line from a skill file is enough to get there. A negative index is
    refused as well: Python would read it as "counting from the end" and quietly run a
    different call than the manifest names.
    """
    if not indexes:
        return list(calls)
    out_of_range = [i for i in indexes if not 0 <= i < len(calls)]
    if out_of_range:
        raise ChainError(f"calls names index(es) {out_of_range}, but the block has "
                         f"{len(calls)} api call(s)")
    return [calls[i] for i in indexes]


MAX_ROWS = 10  # a check only proves rows exist or don't; it never needs to see them
ABSENT = "<absent>"  # an expect_body value: the field must not be in the last response


def run_chain(
    profile: Profile,
    chain: Chain,
    *,
    root: Path,
    vql_factory: Callable,
    rest_factory: Callable | None = None,
    database: str | None = None,
    with_marketplace: bool = False,
    with_ai: bool = False,
    with_writes: bool = False,
    with_scheduler: bool = False,
    keep: bool = False,
    update_marks: bool = False,
    today: dt.date | None = None,
    allow_destructive: bool = False,
    testing_tool: Path | None = None,
    testing_runner: Callable | None = None,
    file_values: dict[str, str] | None = None,
    values_file: Path | None = None,
    assume_missing: tuple[str, ...] | list[str] = (),
    cleanup_only: bool = False,
) -> tuple[dict, int]:
    """Run every vql-channel step of ``chain`` in order and report what happened.

    Each step runs in its own VQL session — ``_run_step`` calls ``run_statements``
    fresh every time — which works because every step but the first either opens with
    its own ``CONNECT DATABASE`` (rewritten by substitution to the test database) or
    declares ``database`` in the manifest, connecting the session directly instead;
    nothing is lost by not sharing a session across steps. The chain stops at the first
    failed step; every later step is reported ``skipped`` with a reason instead of attempted,
    and a skipped step does not by itself make the run fail.

    Cleanup (``_cleanup``) runs after the chain regardless of how it ended — success, the
    first failed step, or even an exception escaping the step loop — unless ``keep`` is
    set: a run that did not clean up must say so in the report rather than leaving
    objects on the server silently. The step loop is wrapped in ``try``/``finally`` so
    that guarantee is structural, not an accident of what today's vql channel happens to
    catch: an exception the loop does not otherwise handle still triggers cleanup, and is
    then left to propagate — a crash must still be a crash, just not a leaking one. A
    cleanup statement that fails makes the whole run fail, even if every step passed,
    because an object left behind on a shared server is what the next run trips over.

    Unless ``keep`` is set — the same condition that later makes ``_cleanup`` a no-op —
    every ``{placeholder}`` in ``chain.cleanup`` is checked against the run's values
    before anything touches the network (``_check_cleanup_placeholders``), and raises ``ChainError`` if one is
    missing: a cleanup statement's placeholders are not covered by ``render``'s own
    unknown-value check (that check only inspects the ``substitute`` mapping, and cleanup
    renders with none), so an unresolved placeholder would otherwise reach the live
    server verbatim and fail there with a confusing remote syntax error instead of a
    local, immediate one. With ``keep`` set the check is skipped too, for the same reason
    ``_cleanup`` itself is skipped: cleanup will not run, so an unresolved placeholder in
    it must not abort a run that has nothing to do with cleanup.

    The final ``values`` — the manifest's own (with every ``@encrypt-throwaway`` marker
    already replaced by a ciphertext this server produced, see ``_encrypt_throwaways``),
    plus ``database``, plus whatever an ``http``
    step's ``capture`` added along the way (e.g. ``tag_id`` from the
    Tag template's create call) — is returned verbatim as the report's ``values`` field, so
    both the next step and ``[cleanup] http`` can be seen to have used the same identifiers
    a reader of the report sees.

    ``rest_factory`` builds the transport an ``http``-channel step and ``[cleanup] http``
    use to reach Data Marketplace — the same role ``vql_factory`` plays for Virtual
    DataPort. It is only ever called for a step that actually runs (a marketplace step
    still needs ``with_marketplace``) or a cleanup entry whose placeholders resolved, so a
    run with no http traffic at all — the common case without ``--with-marketplace`` — can
    leave it ``None``.

    Before the first marketplace step that would run, the catalog is read (``catalog_pending``):
    the tail synchronises the whole catalog with VDP, and no call narrows that to the test
    database. Anything pending besides the run's own database skips every marketplace step,
    with the entries in the reason (cause ``catalog``); a catalog that cannot be read fails the
    first of them, before it sends anything. Cleanup's own synchronisations are sent only when a
    marketplace step ran (or under ``cleanup_only``), and ``_cleanup_http`` reads the catalog
    again before them.

    ``with_ai`` gates the steps marked ``ai = true`` the same way ``with_marketplace`` gates
    the marketplace tail, for a different reason: they write nothing outside the test
    database, but each calls the LLM or the embedding model the server is configured with,
    one paid request per row the query projects, and a server without that configuration
    (or without the Enterprise Plus bundle) fails them. A default run must stay free and
    portable, so they are skipped unless asked for.

    ``with_writes`` gates the steps marked ``writes = true`` and the ``[cleanup] writes``
    statements together (T33). Those steps create a table in a source database the manifest
    names (``[values]``), outside the test database, and insert, update and delete its rows
    through Virtual DataPort; a server without that data source, or an account that may not
    create tables there, fails them, and a default run must not touch that database at all.
    ``[cleanup] writes`` runs before the rest of cleanup: the table is dropped through the
    base view that names it, which ``DROP DATABASE ... CASCADE`` would otherwise take away.

    ``cleanup_only`` runs no step — each is reported skipped — and then the cleanup, under the
    same gates: what a run with ``keep`` left behind goes without the fixture being built again
    only to be dropped (T42: the outcome scenarios reset their fixtures this way).

    ``update_marks`` rewrites the ``-- verified: ...`` mark of every ``template`` step
    that passed, with the version the server actually reported and ``today`` (or
    ``dt.date.today()`` when ``today`` is not given). The version is read once, before
    the first step, with ``_server_version`` — one extra round trip per run rather than
    one per step, since it never changes mid-run. Reading it eagerly, even though the
    first template step might fail before any mark would be written, keeps the timing
    simple; the query is one row and cheap enough that the slight waste on a run that
    fails immediately is not worth a lazier, harder-to-follow path.

    ``allow_destructive`` gates the run as a whole, and is then forwarded verbatim to every
    destructive call it makes — an ``http`` step's own calls (``_run_http``) *and* cleanup,
    both the ``vql`` ``DROP``s and the ``http`` ``DELETE``s and re-syncs (``_cleanup``). It
    defaults to ``False``, matching ``vql run`` and ``api``: on a profile that is not marked
    ``production`` nothing changes (the execution layer only ever refuses a destructive call
    when the profile says ``production``), but on one that is, the run is refused before its
    first step — see ``_refused_on_production``. Cleanup deliberately does not hardcode its
    way past the flag either: a run's own ``DROP DATABASE ... CASCADE`` is exactly the kind
    of operation the gate exists for, not an exception to it.
    """
    if keep and cleanup_only:
        raise ChainError("cleanup_only and keep contradict each other: one removes what the other keeps")
    if profile.production and not allow_destructive:
        values = {**chain.values, **({"database": database} if database else {})}
        return _refused_on_production(profile, values), EXIT_USAGE
    if not keep:
        # Gated on the same condition _cleanup itself checks first: when --keep is set,
        # cleanup never renders or runs, so an unresolved cleanup placeholder must not
        # abort a run that has nothing to do with cleanup. Checked against the names the
        # manifest declares, before the server is asked anything: a value the run then fails
        # to fill in is a reason to hold its statement, not a broken manifest.
        _check_cleanup_placeholders(chain, chain.known_values() | {"database"})
    # T40: the server is asked once, before anything is created, and only when the manifest
    # needs it — a value it fills in, or a step that requires a feature.
    features = _probe(profile, vql_factory) if (_needs_server(chain) or assume_missing) else None
    for name in assume_missing:
        # --without: the server is treated as lacking the feature, whatever it said.
        features[name] = {**(features.get(name) or {}), "on": False} if isinstance(features.get(name), dict) \
            else False
    server = server_values(features) if features else {}
    scheduler_note = "the Scheduler tail did not run (--with-scheduler)"
    if (with_scheduler and chain.values.get("scheduler_data_source_id") == SERVER and rest_factory is not None
            and "scheduler_data_source_id" not in (file_values or {})):
        found, candidates = _scheduler_source(profile, rest_factory)
        if found:
            server["scheduler_data_source_id"] = found
        else:
            scheduler_note = (f"no single VDP data source of the Scheduler logs in as {profile.user!r}; "
                              f"its VDP data sources: {candidates or 'none'}")
    values, values_from, unresolved = resolve_values(
        chain, database=database, file_values=file_values, server=server, values_file=values_file,
        profile_name=profile.name, scheduler_note=scheduler_note)
    # After the local checks above and before anything is created: a value the manifest
    # cannot hold literally (see _encrypt_throwaways) is filled in here, and a server that
    # cannot produce it stops the run while nothing has been written yet.
    failure = _encrypt_throwaways(profile, values, vql_factory=vql_factory)
    if failure is not None:
        return envelope(False, profile, "verify", database=values.get("database"),
                        error=failure), EXIT_EXECUTION
    version = _server_version(profile, vql_factory) if update_marks else None
    day = today or dt.date.today()
    reports: list[dict] = []
    skipped_why: dict[str, str] = {}
    # Ids a skipped step would have captured: they skip the steps naming them, and stay out of
    # the report's `unresolved`, which lists the values an installation has to give.
    lost: dict[str, str] = {}
    # What the marketplace catalog had pending before the tail's first step: (entries, error).
    catalog: tuple[list[str], str | None] | None = None
    marketplace_ran = False
    stop = False
    try:
        for step in chain.steps:
            if cleanup_only:
                reports.append(_skipped(step, "--cleanup-only: only the manifest's cleanup runs",
                                        cause="cleanup-only"))
                continue
            if stop:
                reports.append(_skipped(step, "an earlier step failed", cause="failure"))
                continue
            why, cause = _why_skip(step, features=features, unresolved={**lost, **unresolved}, skipped_why=skipped_why,
                                   root=root, with_marketplace=with_marketplace, with_scheduler=with_scheduler,
                                   with_ai=with_ai, with_writes=with_writes, testing_tool=testing_tool,
                                   assumed=assume_missing)
            if not why and step.marketplace:
                # The tail synchronises the whole catalog, which no call narrows to one database:
                # it runs only while nothing but the run's own database is pending there.
                if catalog is None:
                    catalog = catalog_pending(profile, rest_factory, ignore=values.get("database"))
                pending, error = catalog
                if error:
                    reports.append(_catalog_unread(step, error))
                    stop = True
                    continue
                if pending:
                    why, cause = (f"the marketplace catalog has changes pending that this run did not make, "
                                  f"which the tail's synchronisation would publish or remove with its own: "
                                  f"{_listing(pending)}; the tail was skipped and nothing was synchronised"), "catalog"
            if why:
                reports.append(_skipped(step, why, cause=cause))
                skipped_why[step.id] = why
                # What the step would have captured (an id of an object it creates) is now a value
                # nobody will fill in: every later step naming it is skipped, not failed.
                for name in step.capture:
                    if name not in values:
                        lost.setdefault(name, f"step {step.id!r}, which captures it, was skipped: {why}")
                continue
            # Only a tail that ran can have put the run's database into the catalog for cleanup's
            # synchronisations to take back out.
            marketplace_ran = marketplace_ran or step.marketplace
            report = _run_step(profile, step, values=values, root=root, vql_factory=vql_factory,
                               rest_factory=rest_factory, allow_destructive=allow_destructive,
                               update_marks=update_marks, version=version, day=day,
                               testing_tool=testing_tool, testing_runner=testing_runner)
            reports.append(report)
            if not report["ok"]:
                stop = True
    finally:
        # Runs on the way out no matter how the loop ended — normal completion, an
        # earlier `stop`, or an exception propagating through — so an exception raised
        # here (see the docstring) still leaves cleanup done before it surfaces.
        cleanup_report = _cleanup(profile, chain, values=values, vql_factory=vql_factory,
                                  rest_factory=rest_factory, allow_destructive=allow_destructive,
                                  keep=keep, with_marketplace=with_marketplace, with_writes=with_writes,
                                  with_scheduler=with_scheduler, unresolved=unresolved,
                                  marketplace_ran=marketplace_ran, cleanup_only=cleanup_only)
    ok = all(r["ok"] for r in reports if not r["skipped"])
    ok = ok and (cleanup_report["ran"] is False or (
        all(s["ok"] for s in cleanup_report["statements"]) and
        all(h["ok"] for h in cleanup_report["http"])))
    extra = {"features": features} if features is not None else {}
    if assume_missing:
        extra["assumed_missing"] = list(assume_missing)
    doc = envelope(ok, profile, "verify", database=values.get("database"), steps=reports,
                   summary=_summary(reports, not_run=len(chain.not_run), cleanup=cleanup_report),
                   cleanup=cleanup_report,
                   values=values, values_from=values_from, unresolved=unresolved,
                   values_file=str(values_file) if values_file else None, **extra)
    return doc, EXIT_OK if ok else EXIT_EXECUTION


# Where each @server value comes from, for the reason of a value the server did not give.
SERVER_SOURCES = {
    "embedding_model": "GET_PARAMETER of the embedding model, which only an administrator may read",
    "write_datasource_database": "the cache data source in GET_CACHE_CONFIGURATION",
    "write_datasource_name": "the cache data source in GET_CACHE_CONFIGURATION",
    "write_catalog": "target_catalog in GET_CACHE_CONFIGURATION, empty when the cache database sets none",
    "write_schema": "target_schema in GET_CACHE_CONFIGURATION, empty when the cache database sets none",
    "write_dialect": "adapter_database_name in GET_CACHE_CONFIGURATION",
}


def _needs_server(chain: Chain) -> bool:
    return (any(value in (SERVER, DIALECT) for value in chain.values.values())
            or any(step.requires for step in chain.steps))


def _probe(profile: Profile, vql_factory: Callable) -> dict:
    """The server's features (``features.read_features``) and the user's rights, read once.

    A server that cannot be reached leaves every feature unknown; the first step then fails
    with the real reason, which is a better report than a failed probe.
    """
    unknown = {"enterprise_plus": None, "mpp": None, "cache": None, "llm": None, "embedding": None,
               "summary_rewrite": None, "data_movement": None, "admin": None, "impersonation": None}
    try:
        transport = vql_factory(profile)
    except Exception:  # noqa: BLE001
        return unknown
    try:
        features = read_features(transport)
        features.update(admin=is_admin(transport, profile.user),
                        impersonation=can_impersonate(transport, profile.user))
        return features
    except Exception:  # noqa: BLE001
        return unknown
    finally:
        try:
            transport.close()
        except Exception:  # noqa: BLE001
            pass


def _scheduler_source(profile: Profile, rest_factory: Callable) -> tuple[str | None, list[dict]]:
    try:
        rest = rest_factory(profile, server="scheduler")
    except Exception:  # noqa: BLE001
        return None, []
    return scheduler_data_source(rest, profile.user)


def catalog_pending(profile: Profile, rest_factory: Callable | None, *,
                    ignore: str | None) -> tuple[list[str], str | None]:
    """What a catalog synchronisation would take along now: the ``serverElements`` (it would
    publish them) and ``localElements`` (it would remove them, with their tags, categories and
    endorsements) of both halves' ``changes``, without the entries of ``ignore`` — the run's own
    database, which its synchronisations publish and take back out. A modified description is not
    counted: ``SERVER_WITH_LOCAL_CHANGES`` keeps it. The same reading as ``catalog_pending`` of
    ``evals/outcome/run.py``, which drives the tool from outside and so cannot import this.

    Returns the entries and, when a ``changes`` call did not answer, why: a catalog that could not
    be read is not one known to have nothing pending."""
    pending: list[str] = []
    for half in CATALOG_HALVES:
        path = f"/public/api/element-management/{half}/changes"
        try:
            doc, code = api_call(profile, "GET", path, transport_factory=rest_factory)
        except Exception as exc:  # noqa: BLE001 — no transport (a profile without a marketplace)
            return pending, f"GET {path} failed: {exc}"
        body = doc.get("body")
        if code != EXIT_OK or not isinstance(body, dict):
            detail = (doc.get("error") or {}).get("message") or f"status {doc.get('status')}, body {body!r}"
            return pending, f"GET {path} did not answer with the pending changes: {detail}"
        for listing in ("serverElements", "localElements"):
            for entry in body.get(listing) or []:
                entry = entry if isinstance(entry, dict) else {"elementName": entry}
                if ignore and str(entry.get("databaseName") or "").lower() == ignore.lower():
                    continue
                name = ".".join(str(entry[key]) for key in ("databaseName", "elementName") if entry.get(key))
                pending.append(f"{half} {listing}: {name}")
    return pending, None


def _listing(pending: list[str], limit: int = 8) -> str:
    more = f"; and {len(pending) - limit} more" if len(pending) > limit else ""
    return "; ".join(pending[:limit]) + more


def _held_sync(catalog: tuple[list[str], str | None], *, database: str | None,
               cleanup_only: bool) -> dict | None:
    """Why cleanup holds a catalog synchronisation back — ``reason`` and ``error`` of its failed
    entry — or ``None`` when it may go. After a run whose tail ran, the run's own entries are in
    the catalog for certain; under ``--cleanup-only`` only an earlier run may have put them there."""
    pending, error = catalog
    if not error and not pending:
        return None
    left = (f"whatever an earlier run of {database} put into the catalog may stay in the catalog as orphans"
            if cleanup_only else f"this run's database {database} and its views stay in the catalog as orphans")
    retry = "once nothing else is pending, `verify --cleanup-only --with-marketplace` takes them out"
    if error:
        return {"reason": f"the catalog could not be read, so this synchronisation was not sent: {left}; {retry}",
                "error": {"kind": "catalog", "message": error}}
    return {"reason": (f"the marketplace catalog has changes pending that this run did not make, which this "
                       f"synchronisation would publish or remove with its own: {_listing(pending)}; it was not "
                       f"sent, so {left}; {retry}"),
            "error": {"kind": "catalog", "message": f"changes pending that this run did not make: "
                                                    f"{_listing(pending)}"}}


def _catalog_unread(step: Step, error: str) -> dict:
    """The tail's first step, failed before it sent anything: its own first call reads the same
    ``changes``, and a tail that cannot tell what else is pending must not synchronise."""
    return {"id": step.id, "kind": step.kind, "channel": step.channel, "source": step.address,
            "ok": False, "skipped": False, "check": None, "statements": None, "mark": None,
            "error": {"kind": "catalog", "message": f"{error}; the marketplace tail did not start"}}


def resolve_values(chain: Chain, *, database: str | None, file_values: dict[str, str] | None,
                   server: dict[str, str], values_file: Path | None, profile_name: str,
                   scheduler_note: str = "") -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """The run's values, where each came from, and why each unresolved one is.

    Precedence: ``--database``, then the values file, then the server (``@server``) or the
    dialect table (``@dialect``), then the manifest. A value nobody filled in is left out of
    the values, so no text naming it can be rendered and sent; the reason ends with the line to
    add to the values file.
    """
    values: dict[str, str] = {}
    origin: dict[str, str] = {}
    why: dict[str, str] = {}
    for name, value in chain.values.items():
        if value == SERVER:
            if name in server:
                values[name], origin[name] = server[name], "server"
            elif name == "scheduler_data_source_id":
                why[name] = scheduler_note
            else:
                why[name] = f"the server did not say ({SERVER_SOURCES.get(name, 'no source is known')})"
        elif value != DIALECT:
            values[name], origin[name] = value, "manifest"
    for name, value in (file_values or {}).items():
        values[name], origin[name] = value, "file"
        why.pop(name, None)
    dialect = values.get("write_dialect")
    for name, value in chain.values.items():
        if value != DIALECT or origin.get(name) == "file":
            continue
        table = chain.dialects.get((dialect or "").lower())
        if table is not None and name in table:
            values[name], origin[name] = table[name], "dialect"
        elif dialect:
            why[name] = (f"the manifest has no {name} for {dialect!r}, the product of the write data source "
                         f"(its dialects: {', '.join(sorted(chain.dialects)) or 'none'})")
        else:
            why[name] = "the product of the write data source is unknown (write_dialect)"
    if database:
        values["database"], origin["database"] = database, "flag"
    where = str(values_file or default_values_path())
    unresolved = {name: f"{reason}; set {name} = \"…\" in [{profile_name}] of {where}"
                  for name, reason in why.items()}
    origin.update({name: "unresolved" for name in unresolved})
    return values, origin, unresolved


def _step_value_names(step: Step, root: Path | None = None) -> set[str]:
    """The ``{value}`` names ``step`` sends: the manifest's texts for it, and the block of a skill
    it runs (a block that does not resolve fails the step itself, with the reason)."""
    texts = [step.vql or "", step.check or "", step.database or "", *step.substitute.values(),
             *step.expect_body.values()]
    for spec in step.files.values():
        texts.extend(spec["substitute"].values())
    if root is not None:
        blocks = [(step.address, step.substitute)] + [(spec["address"], spec["substitute"])
                                                      for spec in step.files.values()]
        for address, substitute in blocks:
            if not address:
                continue
            try:
                body = load_block(root, address).body
            except TemplateError:
                continue
            for needle, replacement in substitute.items():
                body = body.replace(needle, replacement)
            texts.append(body)
    return {match.group(1) for text in texts for match in PLACEHOLDER.finditer(text)}


def _why_skip(step: Step, *, features: dict | None, unresolved: dict[str, str], skipped_why: dict[str, str],
              root: Path, with_marketplace: bool, with_scheduler: bool, with_ai: bool, with_writes: bool,
              testing_tool: Path | None, assumed: tuple[str, ...] | list[str] = ()) -> tuple[str | None, str | None]:
    """Why ``step`` does not run, and the kind of reason: a flag not given (``flag``), a feature
    the server lacks (``server``), a value nobody filled in (``value``), or an earlier step it
    needs that did not run (``needs``). ``(None, None)`` when it runs."""
    if step.marketplace and not with_marketplace:
        return "marketplace steps need --with-marketplace", "flag"
    if step.scheduler and not with_scheduler:
        return ("Scheduler steps create a project and jobs on the shared Scheduler and run them; they need "
                "--with-scheduler"), "flag"
    if step.ai and not with_ai:
        return "AI steps call the server's LLM, one paid request per row; they need --with-ai", "flag"
    if step.writes and not with_writes:
        return ("write steps create a table in a source database and change its rows; they need "
                "--with-writes"), "flag"
    if step.channel == "denodotest" and testing_tool is None:
        return ("Testing Tool steps run a .denodotest file with the Denodo Testing Tool; they need "
                "--testing-tool <its install directory>"), "flag"
    lacking = [name for name in step.requires if feature_state(features or {}, name) is False]
    if lacking:
        return "the server lacks " + "; ".join(
            f"{name}: treated as missing (--without {name})" if name in assumed else f"{name}: {FEATURE_REASONS[name]}"
            for name in lacking), "server"
    named = sorted(_step_value_names(step, root) & set(unresolved))
    if named:
        return "; ".join(f"value {{{name}}} is unresolved: {unresolved[name]}" for name in named), "value"
    missing = [needed for needed in step.needs if needed in skipped_why]
    if missing:
        return "; ".join(f"it needs step {needed!r}, which was skipped: {skipped_why[needed]}"
                         for needed in missing), "needs"
    return None, None


def _encrypt_throwaways(profile: Profile, values: dict[str, str], *, vql_factory: Callable) -> dict | None:
    """Replace every ``@encrypt-throwaway`` value with a ciphertext this server just made.

    The JDBC data source template carries ``USERPASSWORD '<...>' ENCRYPTED``, and the
    server validates the ciphertext when the source is created: any other string is
    refused with ``error creating new data source: Invalid encrypted value`` (9.5.1, lab
    server). So the step needs a real ciphertext — and a real one cannot live in this
    repository. It is a credential, it is bound to the server that produced it (a fork
    verifying against its own server could not use ours anyway), and the whole point of
    ``secret encrypt`` is that such a string is never written down by hand.

    Hence the marker: the manifest declares *that* a value is a throwaway password, and
    the run fills in *what* it is — a random password encrypted on the server it is about
    to run against, thrown away with the run. Rewriting the template to drop ``ENCRYPTED``
    and pass a plaintext instead would have needed no code at all, and is exactly what
    makes this worth the code: the block carries one verification mark, and a run that
    silently skipped the ``ENCRYPTED`` half of it would claim more than it checked
    (design spec 11.1).

    Returns ``None`` on success, having rewritten ``values`` in place; on failure it
    returns the error to report, and the caller stops the run before its first step.
    The plaintext never leaves this function — ``encrypt_password`` keeps it out of the
    statement it reports and scrubs it from any server error (``commands/secret.py``).
    """
    for name in [key for key, value in values.items() if value == THROWAWAY]:
        doc, code = encrypt_password(profile, f"verify-throwaway-{secrets.token_urlsafe(12)}",
                                     transport_factory=vql_factory)
        if code != EXIT_OK:
            error = dict(doc.get("error") or {"kind": "execution"})
            error["message"] = (
                f"value {{{name}}} = {THROWAWAY!r} asks for a throwaway password encrypted on "
                f"{profile.name!r}, and that failed: {error.get('message', 'no message')}")
            return error
        values[name] = str(doc["encrypted"])
    return None


def _refused_on_production(profile: Profile, values: dict[str, str]) -> dict:
    """The whole run, refused before step 1 — not merely its cleanup.

    ``verify`` is destructive by construction: it creates a database and its views, two
    *server-level* tags, and with ``--with-marketplace`` writes to the shared marketplace
    catalog, then removes all of it again. None of the creating statements classify as
    destructive on their own, though — ``CREATE OR REPLACE`` does not — so a gate applied
    only per call would let every step run and refuse just the cleanup ``DROP``s, leaving
    behind exactly the objects this command exists to remove. Hence a whole-run refusal,
    carrying the ``kind: "refused"`` shape and the ``EXIT_USAGE`` code the execution layer
    already uses for one refused destructive call.
    """
    error = {
        "kind": "refused",
        "message": (
            f"profile {profile.name!r} is marked production and `verify` creates objects on "
            f"the server it runs against (a test database with its views, two server-level "
            f"tags, and with --with-marketplace the shared marketplace catalog) before "
            f"dropping them again; nothing was sent. Re-run with --allow-destructive after "
            f"a human has confirmed."
        ),
    }
    return envelope(False, profile, "verify", database=values.get("database"), steps=[],
                    summary=_summary([]), values=values, error=error,
                    cleanup={"ran": False, "statements": [], "http": [],
                             "reason": "the run was refused before it created anything"})


def _check_cleanup_placeholders(chain: Chain, values: "dict[str, str] | set[str]") -> None:
    """Fail fast, before any network call, on an unresolved cleanup placeholder.

    ``_cleanup`` renders each statement with ``render(s, {}, values)`` — an empty
    ``substitute`` — and ``render``'s own unknown-value check only inspects
    ``substitute.values()``, so it never sees a ``{name}`` occurring directly in the
    cleanup text; left alone, ``render`` would pass such a placeholder through verbatim.
    Checking here, ahead of the whole run, turns that into a local ``ChainError`` naming
    the missing value and the statement, instead of a remote syntax error discovered only
    after the run has already touched the server.
    """
    for statement in chain.cleanup_writes + chain.cleanup:
        for match in PLACEHOLDER.finditer(statement):
            name = match.group(1)
            if name not in values:
                raise ChainError(
                    f"cleanup statement {statement!r} refers to unknown value {{{name}}}")


def _cleanup(profile: Profile, chain: Chain, *, values: dict[str, str], vql_factory: Callable,
             rest_factory: Callable | None, allow_destructive: bool, keep: bool,
             with_marketplace: bool = False, with_writes: bool = False, with_scheduler: bool = False,
             unresolved: dict[str, str] | None = None, marketplace_ran: bool = False,
             cleanup_only: bool = False) -> dict:
    """Always runs, including after a failure: a run that did not clean up must say so.

    Cleanup statements are destructive by definition (``DROP ...``, ``DELETE``, and the
    catalog re-sync below), so
    whether they may actually run is decided the same way any other destructive call in
    this run is: ``allow_destructive`` is forwarded, not hardcoded — a production profile
    now refuses its own cleanup exactly like it refuses anything else destructive, until a
    human passes ``--allow-destructive``. ``continue_on_error=True`` on the vql side means
    one failed drop does not hide the drops that were still meant to happen after it.

    Statement order is exactly the manifest's order — never sorted, deduplicated, or
    reordered. It is load-bearing: e.g. ``DROP TAG`` is refused while the tag is still
    assigned to a view, and only succeeds after an earlier ``DROP DATABASE ... CASCADE``
    has removed the views carrying that assignment.

    The ``http`` tail (``chain.cleanup_http``) runs after the vql statements above, and that
    order is load-bearing for the marketplace: the tail ends by re-running the catalog
    ``synchronize`` calls, which remove from the marketplace whatever VDP no longer has
    (``safety.classify_http``). They only take the run's own database and views back out of
    the shared catalog if the ``DROP DATABASE ... CASCADE`` above has already removed them
    from VDP — run in the other order they would faithfully re-import everything the run
    had just created.

    The tail is gated on ``with_marketplace``, the same flag that gates the http steps
    themselves. It exists only to undo what those steps did, so without them there is
    nothing to undo — and a default run, which the design requires to stay safe, must not
    touch a catalog everyone shares. That the ``DELETE`` entries would skip themselves
    anyway (nothing captured their ids) is not enough: the re-sync entries name no captured
    value at all and would otherwise fire on every run, removing whatever *anybody* had
    orphaned in the catalog.
    """
    if keep:
        return {"ran": False, "reason": "--keep was given; objects were left on the server",
                "statements": [], "http": []}
    if not chain.cleanup and not chain.cleanup_http and not chain.cleanup_writes:
        return {"ran": False, "reason": "the manifest has no cleanup section",
                "statements": [], "http": []}
    # The write steps' table lives in a source database, not in the test database: it goes
    # first, through the base view DROP DATABASE would take away, and only when those steps
    # could have run.
    vql_cleanup = (chain.cleanup_writes if with_writes else []) + chain.cleanup
    # A statement naming a value the run never had (T40) is reported, not sent: its target was
    # never created either, since every step naming that value was skipped.
    held: list[dict] = []
    sendable: list[str] = []
    for statement in vql_cleanup:
        names = sorted({m.group(1) for m in PLACEHOLDER.finditer(statement)} & set(unresolved or {}))
        if names:
            held.append({"statement": statement, "ok": True, "skipped": True, "error": None,
                         "reason": "; ".join(f"value {{{n}}} is unresolved: {(unresolved or {})[n]}"
                                             for n in names)})
        else:
            sendable.append(statement)
    vql_report: list[dict] = list(held)
    if sendable:
        statements = [render(s, {}, values) for s in sendable]
        doc, _ = run_statements(profile, statements, transport_factory=vql_factory, max_rows=MAX_ROWS,
                                allow_destructive=allow_destructive, continue_on_error=True)
        if doc.get("statements") is None:
            # A whole-batch failure before any statement ran — a production refusal (all
            # of chain.cleanup is destructive by construction) or a connection error.
            # run_statements reports that as a top-level "error" with no per-statement
            # list at all; treating "no statements" as "nothing failed" (the empty list an
            # unguarded comprehension over None would produce) would let a refused cleanup
            # report itself as having succeeded — the `all(s["ok"] ...)` in run_chain is
            # vacuously true over an empty list. One synthetic failed entry keeps the
            # refusal visible and keeps the run's overall ok computation honest.
            vql_report += [{"statement": "; ".join(statements), "ok": False, "error": doc.get("error")}]
        else:
            vql_report += [{"statement": s["statement"], "ok": s["ok"], "error": s["error"]}
                          for s in doc["statements"]]
    http_report = _cleanup_http(profile, chain.cleanup_http, values=values, rest_factory=rest_factory,
                                allow_destructive=allow_destructive, with_marketplace=with_marketplace,
                                with_scheduler=with_scheduler, marketplace_ran=marketplace_ran,
                                cleanup_only=cleanup_only)
    return {"ran": True, "reason": None, "statements": vql_report, "http": http_report}


def _fill(value: object, values: dict[str, str]) -> object:
    """Fill ``{placeholder}``s in every string of a cleanup entry's JSON body."""
    if isinstance(value, dict):
        return {key: _fill(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [_fill(item, values) for item in value]
    if isinstance(value, str):
        return render(value, {}, values)
    return value


def _unresolved(value: object) -> bool:
    """True when a ``{placeholder}`` survived rendering — i.e. nothing ever captured it."""
    if isinstance(value, dict):
        return any(_unresolved(item) for item in value.values())
    if isinstance(value, list):
        return any(_unresolved(item) for item in value)
    return isinstance(value, str) and bool(PLACEHOLDER.search(value))


def _cleanup_http(profile: Profile, entries: list[dict], *, values: dict[str, str],
                  rest_factory: Callable | None, allow_destructive: bool,
                  with_marketplace: bool, with_scheduler: bool = False, marketplace_ran: bool = False,
                  cleanup_only: bool = False) -> list[dict]:
    """Run each ``[cleanup] http`` entry, skipping the ones nothing was ever captured for.

    Unlike ``chain.cleanup`` (vql), whose placeholders are all known before the run even
    starts and checked eagerly by ``_check_cleanup_placeholders``, an http cleanup entry
    typically names a value — ``{tag_id}``, ``{category_id}`` — that only exists once the
    matching step's response captured it. ``render(text, {}, values)`` mirrors exactly what
    ``_cleanup`` already does for vql statements: with an empty ``substitute`` mapping its
    own "unknown value" check never triggers (that check only inspects
    ``substitute.values()``), so a ``{name}`` missing from ``values`` is left in the
    rendered text verbatim rather than raising — which is exactly the signal used here to
    tell "never captured" (skip, report ``skipped: true``) apart from "captured, go ahead".

    The entry's ``json`` body goes through the same two steps, so a body may name a captured
    value too and an entry whose body never resolved is skipped rather than sent
    half-rendered. The body is echoed into the report next to the method and path: for the
    catalog re-sync it is the body, not the path, that says which conflict mode the run
    used, and cleanup is part of the report rather than a line in a log.

    A catalog re-sync has something to take back out only when a marketplace step ran in this
    run (``marketplace_ran``), or, with ``cleanup_only``, when an earlier ``--keep`` run may have
    synchronised; otherwise it is skipped without a word to the marketplace. When it has, it goes
    only while nothing but the run's own database is pending: the catalog is read again first
    (``catalog_pending``), because the pair takes along whatever became pending since the tail
    read it. When something else is pending, or the catalog cannot be read, the pair is not
    sent and its entries fail (``_held_sync``): the run's entries stay in the shared catalog as
    orphans, and a run that leaves them must not report itself green.
    """
    reports: list[dict] = []
    catalog: tuple[list[str], str | None] | None = None
    for entry in entries:
        path = render(entry["path"], {}, values)
        params = {key: render(val, {}, values) for key, val in entry["params"].items()}
        body = _fill(entry["json"], values)
        server = entry.get("server", "marketplace")
        described = {"server": server, "method": entry["method"], "path": path, "params": params, "json": body}
        skipped = None
        if server == "marketplace" and not with_marketplace:
            skipped = "the marketplace tail did not run; pass --with-marketplace"
        elif server == "scheduler" and not with_scheduler:
            skipped = "the Scheduler tail did not run; pass --with-scheduler"
        elif _unresolved(path) or _unresolved(params) or _unresolved(body):
            skipped = "nothing was captured for a placeholder of this entry"
        elif server == "marketplace" and CATALOG_SYNC.match(path.split("?")[0].rstrip("/")):
            if not marketplace_ran and not cleanup_only:
                skipped = ("no marketplace step ran in this run, so the catalog holds nothing of this run's to "
                           "take back out; the synchronisation was not sent")
            else:
                if catalog is None:
                    catalog = catalog_pending(profile, rest_factory, ignore=values.get("database"))
                held = _held_sync(catalog, database=values.get("database"), cleanup_only=cleanup_only)
                if held:
                    reports.append({**described, "ok": False, "skipped": True, "status": None, **held})
                    continue
        if skipped:
            reports.append({**described, "ok": True, "skipped": True, "reason": skipped,
                            "status": None, "error": None})
            continue
        doc, code = api_call(profile, entry["method"], path, transport_factory=rest_factory,
                             json_body=body, params=params, allow_destructive=allow_destructive,
                             server=server)
        reports.append({**described, "ok": bool(doc.get("ok")) and code == EXIT_OK, "skipped": False,
                        "reason": None, "status": doc.get("status"), "error": doc.get("error")})
    return reports


def _skipped(step: Step, reason: str, cause: str | None = None) -> dict:
    return {"id": step.id, "kind": step.kind, "channel": step.channel, "source": step.address,
            "ok": True, "skipped": True, "reason": reason, "cause": cause, "error": None, "check": None,
            "mark": None}


VERSION_NUMBER = re.compile(r"\d+(?:\.\d+)+")


def _server_version(profile: Profile, vql_factory: Callable) -> str | None:
    """The server's reported version, once per run — or ``None`` when it cannot be read.

    ``GET_SERVER_INFO()`` — the stored procedure a first draft of this function assumed
    — does not exist on Denodo 9.5.1; the server answers "View 'get_server_info' not
    found". What does work, confirmed against a live 9.5.1 server, is ``SELECT version()``
    (the Postgres-wire-protocol compatibility layer VDP exposes on the same channel used
    everywhere else in this file), which answers a single row like
    ``"Denodo Virtual DataPort 9.5.1"`` — the version is the *last* token, wrapped in a
    product name prefix, not the first bare token a differently-shaped answer might have
    suggested. Picking the dotted-number substring out with a regex, rather than trusting
    a fixed token position, survives either shape (a prefix here, a trailing build suffix
    elsewhere) without caring which.

    Any failure to determine it — the query itself failing, an empty result, or a row
    with no recognizable version number — returns ``None`` rather than a guessed
    placeholder: a fabricated version (an earlier draft returned a bare ``"9.5"`` here)
    is truthy, so it would sail straight through the caller's ``and version:`` guard and
    get stamped onto every passing template step as if the run had actually confirmed
    that version — writing an unconfirmed claim into the project's public record of what
    has been proven. ``None`` makes that guard do the right thing: stamp nothing this
    run. The caller is responsible for saying so in the report instead of leaving the
    step's mark silently indistinguishable from "already up to date".
    """
    doc, code = run_statements(profile, ["SELECT version()"],
                               transport_factory=vql_factory, max_rows=1)
    rows = ((doc.get("statements") or [{}])[0]).get("rows") if code == EXIT_OK else None
    if not rows:
        return None
    match = VERSION_NUMBER.search(str(rows[0][0]))
    return match.group(0) if match else None


def _summary(reports: list[dict], not_run: int = 0, cleanup: dict | None = None) -> dict:
    cleanup_entries = (cleanup or {}).get("statements", []) + (cleanup or {}).get("http", [])
    return {
        "verified": sum(1 for r in reports if r["kind"] == "template" and r["ok"] and not r["skipped"]),
        "failed": sum(1 for r in reports if not r["ok"]),
        "skipped": sum(1 for r in reports if r["skipped"]),
        # why: a flag not given, a feature the server lacks, a value nobody filled in, a step
        # needed that did not run, changes pending in the marketplace catalog, an earlier failure
        "skipped_because": {cause: sum(1 for r in reports if r["skipped"] and r.get("cause") == cause)
                            for cause in ("flag", "server", "value", "needs", "catalog", "failure",
                                          "cleanup-only")
                            if any(r["skipped"] and r.get("cause") == cause for r in reports)},
        # marked blocks of the skills the manifest lists under [not_run], with the reason
        "not_run": not_run,
        # cleanup entries that failed or were held back — what the run left on the server
        "cleanup_failed": sum(1 for entry in cleanup_entries if entry.get("ok") is False),
    }


def _run_step(profile: Profile, step: Step, *, values: dict[str, str], root: Path, vql_factory: Callable,
             rest_factory: Callable | None = None, allow_destructive: bool = False,
             update_marks: bool = False, version: str | None = None, day: dt.date | None = None,
             testing_tool: Path | None = None, testing_runner: Callable | None = None) -> dict:
    report = {"id": step.id, "kind": step.kind, "channel": step.channel, "source": step.address,
              "ok": False, "skipped": False, "error": None, "check": None, "statements": None, "mark": None}
    try:
        # A value this step captures itself (a job's id, read back by the step's next call)
        # is not known yet when the block is rendered: it stays a placeholder until then.
        own = {key: "{" + key + "}" for key in step.capture if key not in values}
        body = _body(step, root=root, values={**values, **own})
        # Optional per-step database, e.g. "{database}" — the mechanism a check already
        # uses (see _run_check below), now available to the step's own body too: a
        # template that does not carry its own CONNECT DATABASE (an unqualified SET
        # IMPLEMENTATION or ENDPOINT, say) still has to land in the test database, and
        # rewriting the block's text to add one would run text the skill does not have.
        database = render(step.database, {}, values) if step.database else None
    except (TemplateError, ChainError) as exc:
        report["error"] = {"kind": "template", "message": str(exc)}
        return report

    partial = None
    if step.channel == "http":
        outcome = _run_http(profile, step, body=body, values=values, rest_factory=rest_factory,
                            allow_destructive=allow_destructive, root=root)
        report["statements"] = outcome["calls"]
        partial = outcome["partial"]
        if not outcome["ok"]:
            report["error"] = outcome["error"]
            return report
    elif step.channel == "denodotest":
        outcome = _run_denodotest(profile, step, body=body, database=database or values.get("database"),
                                  testing_tool=testing_tool, runner=testing_runner,
                                  allow_destructive=allow_destructive)
        report["statements"] = outcome["tests"]
        if not outcome["ok"]:
            report["error"] = outcome["error"]
            return report
    else:
        statements = split_statements(body)
        doc, code = run_statements(profile, statements, transport_factory=vql_factory, max_rows=MAX_ROWS,
                                   database=database, allow_destructive=allow_destructive)
        report["statements"] = doc.get("statements")
        if code != EXIT_OK:
            failed = (doc.get("statements") or [{}])[doc.get("failed_at") or 0]
            report["error"] = failed.get("error") or doc.get("error")
            return report
    if step.check:
        # Its own call, against the test database by name: the check must not depend on
        # a CONNECT the step body happened to issue, because nothing requires a step's
        # last statement to leave the session pointed at that database.
        report["check"] = _run_check(profile, step, values=values, vql_factory=vql_factory)
        report["ok"] = report["check"]["ok"]
        if not report["ok"]:
            report["error"] = report["check"].get("error") or {
                "kind": "check", "message": f"check expected {step.expect}"}
    else:
        report["ok"] = True

    # Only a template step that actually passed is even considered for a mark rewrite: a
    # fixture verifies nothing, and a failed step must keep whatever mark it already had
    # — the run just disproved it, it did not confirm it. Two things still stop a
    # considered step from being stamped, and each says so with its own ``reason`` rather
    # than an ``updated: False`` that looks like "the mark was already current":
    #   - the step ran only part of its block (``calls`` naming a subset), so re-dating the
    #     block's single mark would claim more than this run established;
    #   - ``version`` is unknown (``_server_version`` returned None — see its docstring).
    if report["ok"] and step.kind == "template" and update_marks:
        if partial:
            report["mark"] = {"updated": False, "reason": partial}
        elif version:
            block = load_block(root, step.address or "")
            report["mark"] = {"updated": update_mark(block, version=version, day=day),
                              "text": format_mark(version, day)}
        else:
            report["mark"] = {"updated": False, "reason": "server version unknown"}
    return report


HTTP_HINTS = {
    # The one marketplace status whose own answer says nothing: a duplicate name comes back
    # 409 with an *empty body* (skills/marketplace/SKILL.md, "Tag, with an assignment"), so
    # the report used to read "status: 409, body: null" — true, and no help to whoever has to
    # act on it. The cause is almost never a bug in the template: the marketplace tail
    # creates rather than looks up (verification/chain.toml explains why), so a name that is
    # taken means an object from an earlier --keep run is still in the shared catalog.
    409: ("duplicate name: the marketplace addresses objects by numeric id and refuses a "
          "second object of the same name with 409 and an empty body. On this chain that is "
          "normally what a previous --keep run left behind in the shared catalog — remove it "
          "by id (DELETE /public/api/tags/<id>, DELETE "
          "/public/api/category-management/categories/<id>) or let a run without --keep clean "
          "up after itself."),
}


def _http_failure(doc: dict) -> dict:
    """One failed call, in the shape a failed statement uses elsewhere in this file.

    ``hint`` is added only for a status ``HTTP_HINTS`` knows, and is absent otherwise: a
    hint on every failure would eventually explain a 400 as a leftover and send the
    operator hunting for an object that was never created.
    """
    error = {"kind": "http", "status": doc.get("status"), "body": doc.get("body")}
    hint = HTTP_HINTS.get(doc.get("status"))
    if hint:
        error["hint"] = hint
    return error


def _field(body: object, path: str) -> object:
    """``a.b.0.c`` of a parsed JSON body; ``None`` when any part is missing. A field name
    without dots is a top-level field, as it always was."""
    current = body
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
        if current is None:
            return None
    return current


def _file_body(step: Step, json_file: str, *, root: Path, values: dict[str, str]) -> object:
    """The JSON a ``--json-file`` call sends: the block ``step.files`` maps its path to."""
    spec = step.files.get(json_file)
    if spec is None:
        raise ChainError(f"the call reads --json-file {json_file!r}, which the step's files do not map "
                         f"to a block (files: {sorted(step.files)})")
    block = load_block(root, spec["address"])
    text = render(block.body, spec["substitute"], values)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ChainError(f"the block for {json_file!r} ({spec['address']}) is not valid JSON: {exc}") from exc


def _run_http(profile: Profile, step: Step, *, body: str, values: dict[str, str],
              rest_factory: Callable | None, allow_destructive: bool, root: Path | None = None) -> dict:
    """Run the http-channel calls ``step.calls`` names out of ``body``'s ``api ...`` lines.

    ``step.calls`` is a list of indexes into ``parse_api_calls(body)`` (resolved by
    ``_select_calls``, which rejects an index the block does not have) — an empty list
    means every call the block has, in order (a template with no alternatives, e.g. the
    marketplace-sync block's four read-then-write calls, two of which — the ``synchronize``
    calls — are themselves classified destructive by ``safety.classify_http``: rewriting
    the shared catalog is exactly the kind of operation a production profile should be able
    to refuse). ``allow_destructive`` is forwarded to every call, not assumed — the tag and
    category steps only ever touch objects a manifest scopes with its own ``verify_``
    prefix, but ``marketplace-sync`` does not, and hardcoding it past the gate here would
    have let a production run rewrite the whole catalog with no confirmation.

    The first non-2xx answer stops the step. When ``api_call`` itself carries a structured
    ``error`` (a refused destructive call, or a connection failure — cases where there is
    no real HTTP status to report), that error is reported verbatim so the refusal's own
    message survives into the step's report; otherwise the failure goes through
    ``_http_failure``, which reports it the same shape a failed statement uses elsewhere in
    this file — ``{"kind": "http", "status": ..., "body": ...}`` — plus a ``hint`` for the
    statuses whose own answer explains nothing (``HTTP_HINTS``).

    ``step.capture`` is read only from the *last* executed call's response body, by
    top-level field name — a lookup call earlier in the sequence never carries the id a
    create/update call answers with, and reading every call's body would risk a later,
    unrelated field silently overwriting an earlier capture. A declared ``capture`` whose
    field is missing from that body — a response shaped differently than the template
    expects — fails the step instead of silently leaving the value uncaptured: letting the
    step report ``ok`` in that case is exactly how the object it just created stops being
    trackable by ``[cleanup] http``, which only knows to remove what it finds in ``values``.

    The returned ``partial`` is the reason string for a step that ran only some of its
    block's calls, and ``None`` for one that ran all of them. ``--update-marks`` needs it:
    a block carries one mark for the whole block, so re-dating it off a run of two of its
    four calls would claim more than the run established.
    """
    try:
        calls = parse_api_calls(body)
        selected = _select_calls(calls, step.calls)
        for call in selected:
            if call.get("json_file"):
                call["json"] = _file_body(step, call["json_file"], root=root or Path("."), values=values)
    except (ChainError, TemplateError) as exc:
        return {"ok": False, "calls": [], "partial": None,
                "error": {"kind": "template", "message": f"step {step.id!r}: {exc}"}}
    partial = (f"the step ran {len(selected)} of the block's {len(calls)} calls"
               if len(selected) < len(calls) else None)
    executed: list[dict] = []
    bodies: list[object] = []
    last_body: object = None

    def send(call: dict) -> tuple[dict, int]:
        # Rendered again here: a value captured by an earlier call of this step (a job's id)
        # only exists now.
        path = render(call["path"], {}, values)
        doc, code = api_call(profile, call["method"], path,
                             transport_factory=rest_factory, json_body=call["json"], params=call["params"],
                             multipart=call["multipart"], allow_destructive=allow_destructive,
                             server=call.get("server", "marketplace"))
        executed.append({"method": call["method"], "path": path,
                         "status": doc.get("status"), "ok": bool(doc.get("ok"))})
        return doc, code

    for index, call in enumerate(selected):
        doc, code = send(call)
        if code != EXIT_OK:
            error = doc.get("error") or _http_failure(doc)
            return {"ok": False, "calls": executed, "partial": partial, "error": error}
        last_body = doc.get("body")
        bodies.append(last_body)
        if step.capture and index == (step.capture_from if step.capture_from is not None else len(selected) - 1):
            # Captured as soon as the call answers: a later call of the same step may name
            # the value (the read-back of a job just created names its id).
            captured_body = last_body
            missing = [f for f in step.capture.values() if _field(captured_body, f) is None]
            if missing:
                shape = sorted(captured_body) if isinstance(captured_body, dict) else type(captured_body).__name__
                return {"ok": False, "calls": executed, "partial": partial, "error": {
                    "kind": "capture",
                    "message": (f"step {step.id!r}: capture field(s) {missing} not found in the "
                               f"response body of call {index} (shape: {shape!r})"),
                }}
            for key, field_name in step.capture.items():
                values[key] = str(_field(captured_body, field_name))
    if step.poll and selected:
        # A number of attempts rather than a clock: every attempt waits `every` seconds, so
        # the budget is the same however slow each call is.
        attempts = max(1, int(step.poll["seconds"] / step.poll["every"]))
        seen = _field(last_body, step.poll["field"])
        while str(seen) != step.poll["until"]:
            if attempts == 0:
                return {"ok": False, "calls": executed, "partial": partial, "error": {
                    "kind": "poll",
                    "message": (f"step {step.id!r}: {step.poll['field']} was still {seen!r} after "
                               f"{step.poll['seconds']} s; waited for {step.poll['until']!r}"),
                }}
            attempts -= 1
            time.sleep(step.poll["every"])
            doc, code = send(selected[-1])
            if code != EXIT_OK:
                error = doc.get("error") or _http_failure(doc)
                return {"ok": False, "calls": executed, "partial": partial, "error": error}
            last_body = doc.get("body")
            seen = _field(last_body, step.poll["field"])
    mismatches = []
    for field_name, expected in step.expect_body.items():
        wanted = render(expected, {}, values)
        got = _field(last_body, field_name)
        if wanted == ABSENT:
            # A removal is proved by what is no longer there: "views.0" of an emptied list. The
            # place it is missing from must be there — a list for an index, an object for a key —
            # or an empty answer, a text or a misspelled path would prove it too.
            head, _, last = field_name.rpartition(".")
            parent = _field(last_body, head) if head else last_body
            wanted_type = list if last.isdigit() else dict
            if not isinstance(parent, wanted_type):
                mismatches.append(f"{field_name}: expected it absent from a JSON "
                                  f"{'list' if wanted_type is list else 'object'}, got {parent!r} there")
            elif got is not None:
                mismatches.append(f"{field_name}: expected it absent, got {got!r}")
        elif got is None or str(got) != wanted:
            mismatches.append(f"{field_name}: expected {wanted!r}, got {got!r}")
    if mismatches:
        return {"ok": False, "calls": executed, "partial": partial, "error": {
            "kind": "expect_body",
            "message": f"step {step.id!r}: the last call's response differs — " + "; ".join(mismatches),
        }}
    return {"ok": True, "calls": executed, "partial": partial, "error": None}


def _run_denodotest(profile: Profile, step: Step, *, body: str, database: str | None,
                    testing_tool: Path | None, runner: Callable | None, allow_destructive: bool) -> dict:
    """Run one ``.denodotest`` block through the Denodo Testing Tool (T35).

    The block becomes the only file of a fresh temporary folder and ``testing run`` runs it:
    the tool's configuration exists for that run only, the launcher starts from the tool's
    ``bin``. Passing needs exactly one test run and one OK, besides the tool's own exit code —
    a block the tool did not recognise as a test is skipped by it without a word.
    """
    with tempfile.TemporaryDirectory(prefix="denodo-verify-") as tmp:
        folder = Path(tmp) / "tests"
        folder.mkdir()
        (folder / f"{step.id}.denodotest").write_text(body + "\n", encoding="utf-8")
        doc, code = run_testing_tool(profile, tests=folder, tool=Path(testing_tool or ""), database=database,
                                     runner=runner, allow_destructive=allow_destructive)
    tests = doc.get("tests") or []
    summary = doc.get("summary")
    if code == EXIT_OK and summary and summary["run"] == 1 and summary["ok"] == 1:
        return {"ok": True, "tests": tests, "error": None}
    if doc.get("error"):
        error = dict(doc["error"])
        if error.get("kind") == "usage":
            error["kind"] = "testing-tool"
        return {"ok": False, "tests": tests, "error": error}
    failed = [t["message"] for t in tests if t["status"] != "OK"]
    message = failed[0] if failed else (f"exit code {doc.get('exit_code')}, summary {summary}: "
                                        + " | ".join((doc.get("output_tail") or "").splitlines()[-5:]))
    return {"ok": False, "tests": tests, "error": {"kind": "testing-tool", "message": message}}


def _body(step: Step, *, root: Path, values: dict[str, str]) -> str:
    if step.kind == "fixture":
        return render(step.vql or "", step.substitute, values)
    block = load_block(root, step.address or "")
    return render(block.body, step.substitute, values)


def _run_check(profile: Profile, step: Step, *, values: dict[str, str], vql_factory: Callable) -> dict:
    statement = render(step.check or "", {}, values)
    doc, code = run_statements(profile, [statement], transport_factory=vql_factory,
                               max_rows=MAX_ROWS, database=values.get("database"))
    entry = (doc.get("statements") or [{}])[0]
    if code != EXIT_OK:
        # Mirrors _run_step's own failure path: when the failure happens before any
        # statement runs (the transport factory itself raised), entry carries nothing
        # and the real cause is only on the envelope's top-level "error".
        return {"ok": False, "statement": statement, "row_count": None, "expect": step.expect,
                "error": entry.get("error") or doc.get("error")}
    count = entry.get("row_count") or 0
    ok = count > 0 if step.expect == "rows" else count == 0
    return {"ok": ok, "statement": statement, "row_count": count, "expect": step.expect, "error": None}
