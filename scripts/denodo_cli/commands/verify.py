"""``verify``: run the v1 chain of skill templates against a stand and clean up.

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
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import EXIT_EXECUTION, EXIT_OK, EXIT_USAGE
from .api import api_call, parse_multipart_specs
from .secret import encrypt_password
from .vql import run_statements
from ..output import envelope
from ..profiles import Profile
from ..templates import TemplateError, format_mark, load_block, update_mark
from ..vql_split import split_statements

KINDS = ("template", "fixture")
CHANNELS = ("vql", "http")
EXPECTS = ("rows", "no rows")
THROWAWAY = "@encrypt-throwaway"
PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


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
    check: str | None = None
    expect: str = "rows"
    marketplace: bool = False
    database: str | None = None


@dataclass(frozen=True)
class Chain:
    values: dict[str, str]
    steps: list[Step]
    cleanup: list[str] = field(default_factory=list)
    cleanup_http: list[dict] = field(default_factory=list)


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
    return Chain(values=values, steps=steps, cleanup=cleanup, cleanup_http=cleanup_http)


def _cleanup_http_entries(raw: object, path: Path) -> list[dict]:
    """Validate ``[cleanup] http`` — a list of ``{method, path, params, json}`` tables.

    Shape errors are caught here, at load time, for the same reason ``_int_calls``
    validates ``calls``: a malformed manifest must fail as ``ChainError`` naming the
    manifest, not surface later as a bare ``KeyError``/``AttributeError`` from deep inside
    cleanup, after the chain has already touched the stand.

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
        entries.append({"method": method, "path": call_path, "params": params, "json": body})
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
    if channel == "http" and not marketplace:
        # The executor (a later task) only implements the vql channel; http steps are
        # guarded behind --with-marketplace. Without this, an http step lacking the flag
        # would fall through into the vql branch of a default run.
        raise ChainError(f"step {step_id!r}: an http-channel step must set marketplace = true")
    database = raw.get("database")
    if database is not None and not isinstance(database, str):
        raise ChainError(f"step {step_id!r}: database must be a string, got {database!r}")
    return Step(id=step_id, kind=kind, channel=channel, address=address, vql=vql,
                calls=_int_calls(raw.get("calls", []), step_id),
                substitute={str(k): str(v) for k, v in (raw.get("substitute") or {}).items()},
                capture={str(k): str(v) for k, v in (raw.get("capture") or {}).items()},
                check=raw.get("check"), expect=expect, marketplace=marketplace, database=database)


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
    """One ``api ...`` line as ``{method, path, params, json, multipart}``.

    ``--part`` is parsed rather than dropped like the other flags this does not recognise
    (``--env`` and friends): the marketplace has exactly one multipart call — creating an
    external provider type — and dropping a flag drops its value too, which turned that
    line into a POST with an empty body and sent it that way. A step may leave a call out
    (``calls``); sending a call the template does not describe is a different thing.
    """
    try:
        tokens = shlex.split(line)[1:]
    except ValueError as exc:
        raise ChainError(f"api line {line!r} does not parse: {exc}") from exc
    if not tokens:
        # Unreachable through parse_api_calls, whose own `startswith("api ")` filter on an
        # already-stripped line guarantees a token follows. Kept because that filter is the
        # only thing standing between shlex and an IndexError here.
        raise ChainError(f"api line {line!r} names no method")
    method, path = tokens[0].upper(), None
    params: dict[str, str] = {}
    body_text: str | None = None
    part_specs: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("-"):
            path = token
            index += 1
            continue
        if index + 1 >= len(tokens):
            raise ChainError(f"api line {line!r}: {token} has no value")
        if token == "--param":
            key, _, value = tokens[index + 1].partition("=")
            params[key] = value
        elif token == "--json":
            body_text = tokens[index + 1]
        elif token == "--part":
            part_specs.append(tokens[index + 1])
        index += 2       # --env, and every other flag, is dropped together with its value
    if path is None:
        raise ChainError(f"api line {line!r} names no path")
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
    return {"method": method, "path": path, "params": params, "json": json_body,
            "multipart": multipart}


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


def run_chain(
    profile: Profile,
    chain: Chain,
    *,
    root: Path,
    vql_factory: Callable,
    rest_factory: Callable | None = None,
    database: str | None = None,
    with_marketplace: bool = False,
    keep: bool = False,
    update_marks: bool = False,
    today: dt.date | None = None,
    allow_destructive: bool = False,
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
    objects on the stand silently. The step loop is wrapped in ``try``/``finally`` so
    that guarantee is structural, not an accident of what today's vql channel happens to
    catch: an exception the loop does not otherwise handle still triggers cleanup, and is
    then left to propagate — a crash must still be a crash, just not a leaking one. A
    cleanup statement that fails makes the whole run fail, even if every step passed,
    because an object left behind on a shared stand is what the next run trips over.

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
    already replaced by a ciphertext this stand produced, see ``_encrypt_throwaways``),
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
    values = dict(chain.values)
    if database:
        values["database"] = database
    if profile.production and not allow_destructive:
        return _refused_on_production(profile, values), EXIT_USAGE
    if not keep:
        # Gated on the same condition _cleanup itself checks first: when --keep is set,
        # cleanup never renders or runs, so an unresolved cleanup placeholder must not
        # abort a run that has nothing to do with cleanup.
        _check_cleanup_placeholders(chain, values)
    # After the local checks above and before anything is created: a value the manifest
    # cannot hold literally (see _encrypt_throwaways) is filled in here, and a stand that
    # cannot produce it stops the run while nothing has been written yet.
    failure = _encrypt_throwaways(profile, values, vql_factory=vql_factory)
    if failure is not None:
        return envelope(False, profile, "verify", database=values.get("database"),
                        error=failure), EXIT_EXECUTION
    version = _server_version(profile, vql_factory) if update_marks else None
    day = today or dt.date.today()
    reports: list[dict] = []
    stop = False
    try:
        for step in chain.steps:
            if stop:
                reports.append(_skipped(step, "an earlier step failed"))
                continue
            if step.marketplace and not with_marketplace:
                reports.append(_skipped(step, "marketplace steps need --with-marketplace"))
                continue
            report = _run_step(profile, step, values=values, root=root, vql_factory=vql_factory,
                               rest_factory=rest_factory, allow_destructive=allow_destructive,
                               update_marks=update_marks, version=version, day=day)
            reports.append(report)
            if not report["ok"]:
                stop = True
    finally:
        # Runs on the way out no matter how the loop ended — normal completion, an
        # earlier `stop`, or an exception propagating through — so an exception raised
        # here (see the docstring) still leaves cleanup done before it surfaces.
        cleanup_report = _cleanup(profile, chain, values=values, vql_factory=vql_factory,
                                  rest_factory=rest_factory, allow_destructive=allow_destructive,
                                  keep=keep, with_marketplace=with_marketplace)
    ok = all(r["ok"] for r in reports if not r["skipped"])
    ok = ok and (cleanup_report["ran"] is False or (
        all(s["ok"] for s in cleanup_report["statements"]) and
        all(h["ok"] for h in cleanup_report["http"])))
    doc = envelope(ok, profile, "verify", database=values.get("database"), steps=reports,
                   summary=_summary(reports), cleanup=cleanup_report, values=values)
    return doc, EXIT_OK if ok else EXIT_EXECUTION


def _encrypt_throwaways(profile: Profile, values: dict[str, str], *, vql_factory: Callable) -> dict | None:
    """Replace every ``@encrypt-throwaway`` value with a ciphertext this stand just made.

    The JDBC data source template carries ``USERPASSWORD '<...>' ENCRYPTED``, and the
    server validates the ciphertext when the source is created: any other string is
    refused with ``error creating new data source: Invalid encrypted value`` (9.5.1, lab
    stand). So the step needs a real ciphertext — and a real one cannot live in this
    repository. It is a credential, it is bound to the server that produced it (a fork
    verifying against its own stand could not use ours anyway), and the whole point of
    ``secret encrypt`` is that such a string is never written down by hand.

    Hence the marker: the manifest declares *that* a value is a throwaway password, and
    the run fills in *what* it is — a random password encrypted on the stand it is about
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


def _check_cleanup_placeholders(chain: Chain, values: dict[str, str]) -> None:
    """Fail fast, before any network call, on an unresolved cleanup placeholder.

    ``_cleanup`` renders each statement with ``render(s, {}, values)`` — an empty
    ``substitute`` — and ``render``'s own unknown-value check only inspects
    ``substitute.values()``, so it never sees a ``{name}`` occurring directly in the
    cleanup text; left alone, ``render`` would pass such a placeholder through verbatim.
    Checking here, ahead of the whole run, turns that into a local ``ChainError`` naming
    the missing value and the statement, instead of a remote syntax error discovered only
    after the run has already touched the stand.
    """
    for statement in chain.cleanup:
        for match in PLACEHOLDER.finditer(statement):
            name = match.group(1)
            if name not in values:
                raise ChainError(
                    f"cleanup statement {statement!r} refers to unknown value {{{name}}}")


def _cleanup(profile: Profile, chain: Chain, *, values: dict[str, str], vql_factory: Callable,
             rest_factory: Callable | None, allow_destructive: bool, keep: bool,
             with_marketplace: bool = False) -> dict:
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
        return {"ran": False, "reason": "--keep was given; objects were left on the stand",
                "statements": [], "http": []}
    if not chain.cleanup and not chain.cleanup_http:
        return {"ran": False, "reason": "the manifest has no cleanup section",
                "statements": [], "http": []}
    vql_report: list[dict] = []
    if chain.cleanup:
        statements = [render(s, {}, values) for s in chain.cleanup]
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
            vql_report = [{"statement": "; ".join(statements), "ok": False, "error": doc.get("error")}]
        else:
            vql_report = [{"statement": s["statement"], "ok": s["ok"], "error": s["error"]}
                         for s in doc["statements"]]
    http_report = _cleanup_http(profile, chain.cleanup_http, values=values, rest_factory=rest_factory,
                                allow_destructive=allow_destructive, with_marketplace=with_marketplace)
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
                  with_marketplace: bool) -> list[dict]:
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
    """
    reports: list[dict] = []
    for entry in entries:
        path = render(entry["path"], {}, values)
        params = {key: render(val, {}, values) for key, val in entry["params"].items()}
        body = _fill(entry["json"], values)
        described = {"method": entry["method"], "path": path, "params": params, "json": body}
        skipped = None
        if not with_marketplace:
            skipped = "the marketplace tail did not run; pass --with-marketplace"
        elif _unresolved(path) or _unresolved(params) or _unresolved(body):
            skipped = "nothing was captured for a placeholder of this entry"
        if skipped:
            reports.append({**described, "ok": True, "skipped": True, "reason": skipped,
                            "status": None, "error": None})
            continue
        doc, code = api_call(profile, entry["method"], path, transport_factory=rest_factory,
                             json_body=body, params=params, allow_destructive=allow_destructive)
        reports.append({**described, "ok": bool(doc.get("ok")) and code == EXIT_OK, "skipped": False,
                        "reason": None, "status": doc.get("status"), "error": doc.get("error")})
    return reports


def _skipped(step: Step, reason: str) -> dict:
    return {"id": step.id, "kind": step.kind, "channel": step.channel, "source": step.address,
            "ok": True, "skipped": True, "reason": reason, "error": None, "check": None, "mark": None}


VERSION_NUMBER = re.compile(r"\d+(?:\.\d+)+")


def _server_version(profile: Profile, vql_factory: Callable) -> str | None:
    """The server's reported version, once per run — or ``None`` when it cannot be read.

    ``GET_SERVER_INFO()`` — the stored procedure a first draft of this function assumed
    — does not exist on Denodo 9.5.1; the stand answers "View 'get_server_info' not
    found". What does work, confirmed against the lab stand, is ``SELECT version()``
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


def _summary(reports: list[dict]) -> dict:
    return {
        "verified": sum(1 for r in reports if r["kind"] == "template" and r["ok"] and not r["skipped"]),
        "failed": sum(1 for r in reports if not r["ok"]),
        "skipped": sum(1 for r in reports if r["skipped"]),
    }


def _run_step(profile: Profile, step: Step, *, values: dict[str, str], root: Path, vql_factory: Callable,
             rest_factory: Callable | None = None, allow_destructive: bool = False,
             update_marks: bool = False, version: str | None = None, day: dt.date | None = None) -> dict:
    report = {"id": step.id, "kind": step.kind, "channel": step.channel, "source": step.address,
              "ok": False, "skipped": False, "error": None, "check": None, "statements": None, "mark": None}
    try:
        body = _body(step, root=root, values=values)
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
                            allow_destructive=allow_destructive)
        report["statements"] = outcome["calls"]
        partial = outcome["partial"]
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


def _run_http(profile: Profile, step: Step, *, body: str, values: dict[str, str],
              rest_factory: Callable | None, allow_destructive: bool) -> dict:
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
    except ChainError as exc:
        return {"ok": False, "calls": [], "partial": None,
                "error": {"kind": "template", "message": f"step {step.id!r}: {exc}"}}
    partial = (f"the step ran {len(selected)} of the block's {len(calls)} calls"
               if len(selected) < len(calls) else None)
    executed: list[dict] = []
    last_body: object = None
    for call in selected:
        doc, code = api_call(profile, call["method"], call["path"], transport_factory=rest_factory,
                             json_body=call["json"], params=call["params"],
                             multipart=call["multipart"], allow_destructive=allow_destructive)
        executed.append({"method": call["method"], "path": call["path"],
                         "status": doc.get("status"), "ok": bool(doc.get("ok"))})
        if code != EXIT_OK:
            error = doc.get("error") or _http_failure(doc)
            return {"ok": False, "calls": executed, "partial": partial, "error": error}
        last_body = doc.get("body")
    if step.capture:
        missing = [field for field in step.capture.values()
                  if not (isinstance(last_body, dict) and field in last_body)]
        if missing:
            shape = sorted(last_body) if isinstance(last_body, dict) else type(last_body).__name__
            return {"ok": False, "calls": executed, "partial": partial, "error": {
                "kind": "capture",
                "message": (f"step {step.id!r}: capture field(s) {missing} not found in the last "
                           f"call's response body (shape: {shape!r})"),
            }}
        for key, field_name in step.capture.items():
            values[key] = str(last_body[field_name])
    return {"ok": True, "calls": executed, "partial": partial, "error": None}


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
