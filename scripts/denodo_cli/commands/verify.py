"""``verify``: run the v1 chain of skill templates against a stand and clean up.

The plan is data (``verification/chain.toml``), the mechanics are here. A step either
points at a block of a skill (``template`` — the thing being verified) or carries its own
body (``fixture`` — scaffolding that makes the chain reachable). Substitutions are exact
strings, and one that does not occur in the block is an error: silently skipping it would
send the run into somebody else's database.
"""

from __future__ import annotations

import datetime as dt
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import EXIT_EXECUTION, EXIT_OK
from .vql import run_statements
from ..output import envelope
from ..profiles import Profile
from ..templates import TemplateError, load_block
from ..vql_split import split_statements

KINDS = ("template", "fixture")
CHANNELS = ("vql", "http")
EXPECTS = ("rows", "no rows")
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


@dataclass(frozen=True)
class Chain:
    values: dict[str, str]
    steps: list[Step]
    cleanup: list[str] = field(default_factory=list)


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
    cleanup = [str(s) for s in (document.get("cleanup") or {}).get("vql", [])]
    return Chain(values=values, steps=steps, cleanup=cleanup)


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
    return Step(id=step_id, kind=kind, channel=channel, address=address, vql=vql,
                calls=_int_calls(raw.get("calls", []), step_id),
                substitute={str(k): str(v) for k, v in (raw.get("substitute") or {}).items()},
                capture={str(k): str(v) for k, v in (raw.get("capture") or {}).items()},
                check=raw.get("check"), expect=expect, marketplace=marketplace)


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
    values_override: dict[str, str] | None = None,
) -> tuple[dict, int]:
    """Run every vql-channel step of ``chain`` in order and report what happened.

    Each step runs in its own VQL session — ``_run_step`` calls ``run_statements``
    fresh every time — which works because every template but the first opens with its
    own ``CONNECT DATABASE``, rewritten by substitution to the test database; nothing
    is lost by not sharing a session across steps. The chain stops at the first failed
    step; every later step is reported ``skipped`` with a reason instead of attempted,
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

    ``values_override`` is merged into the run's values after ``database``, so a caller
    (a test, or later the CLI) can supply values the manifest itself does not define —
    e.g. a ``tag_prefix`` used only by ``[cleanup]``. Before anything touches the network,
    every ``{placeholder}`` in ``chain.cleanup`` is checked against the merged values
    (``_check_cleanup_placeholders``) and raises ``ChainError`` if one is missing: a
    cleanup statement's placeholders are not covered by ``render``'s own unknown-value
    check (that check only inspects the ``substitute`` mapping, and cleanup renders with
    none), so an unresolved placeholder would otherwise reach the live server verbatim
    and fail there with a confusing remote syntax error instead of a local, immediate one.

    ``rest_factory`` and ``update_marks`` are accepted so the call signature already
    matches what the http channel and mark-rewriting (later tasks) will need; neither
    does anything yet — a marketplace step is simply skipped unless ``with_marketplace``
    is set.
    """
    values = dict(chain.values)
    if database:
        values["database"] = database
    if values_override:
        values.update(values_override)
    _check_cleanup_placeholders(chain, values)
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
            report = _run_step(profile, step, values=values, root=root, vql_factory=vql_factory)
            reports.append(report)
            if not report["ok"]:
                stop = True
    finally:
        # Runs on the way out no matter how the loop ended — normal completion, an
        # earlier `stop`, or an exception propagating through — so an exception raised
        # here (see the docstring) still leaves cleanup done before it surfaces.
        cleanup_report = _cleanup(profile, chain, values=values, vql_factory=vql_factory, keep=keep)
    ok = all(r["ok"] for r in reports if not r["skipped"])
    ok = ok and (cleanup_report["ran"] is False or all(s["ok"] for s in cleanup_report["statements"]))
    doc = envelope(ok, profile, "verify", database=values.get("database"), steps=reports,
                   summary=_summary(reports), cleanup=cleanup_report)
    return doc, EXIT_OK if ok else EXIT_EXECUTION


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
             keep: bool) -> dict:
    """Always runs, including after a failure: a run that did not clean up must say so.

    Cleanup statements are destructive by definition (``DROP ...``), so they run with
    ``allow_destructive=True`` — a production profile must not be able to refuse a run's
    own cleanup — and ``continue_on_error=True``, so one failed drop does not hide the
    drops that were still meant to happen after it.

    Statement order is exactly the manifest's order — never sorted, deduplicated, or
    reordered. It is load-bearing: e.g. ``DROP TAG`` is refused while the tag is still
    assigned to a view, and only succeeds after an earlier ``DROP DATABASE ... CASCADE``
    has removed the views carrying that assignment.
    """
    if keep:
        return {"ran": False, "reason": "--keep was given; objects were left on the stand",
                "statements": []}
    if not chain.cleanup:
        return {"ran": False, "reason": "the manifest has no cleanup section", "statements": []}
    statements = [render(s, {}, values) for s in chain.cleanup]
    doc, _ = run_statements(profile, statements, transport_factory=vql_factory, max_rows=MAX_ROWS,
                            allow_destructive=True, continue_on_error=True)
    return {"ran": True, "reason": None,
            "statements": [{"statement": s["statement"], "ok": s["ok"], "error": s["error"]}
                           for s in doc.get("statements") or []]}


def _skipped(step: Step, reason: str) -> dict:
    return {"id": step.id, "kind": step.kind, "channel": step.channel, "source": step.address,
            "ok": True, "skipped": True, "reason": reason, "error": None, "check": None}


def _summary(reports: list[dict]) -> dict:
    return {
        "verified": sum(1 for r in reports if r["kind"] == "template" and r["ok"] and not r["skipped"]),
        "failed": sum(1 for r in reports if not r["ok"]),
        "skipped": sum(1 for r in reports if r["skipped"]),
    }


def _run_step(profile: Profile, step: Step, *, values: dict[str, str], root: Path, vql_factory: Callable) -> dict:
    report = {"id": step.id, "kind": step.kind, "channel": step.channel, "source": step.address,
              "ok": False, "skipped": False, "error": None, "check": None, "statements": None}
    try:
        body = _body(step, root=root, values=values)
    except (TemplateError, ChainError) as exc:
        report["error"] = {"kind": "template", "message": str(exc)}
        return report

    statements = split_statements(body)
    doc, code = run_statements(profile, statements, transport_factory=vql_factory, max_rows=MAX_ROWS)
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
        return report
    report["ok"] = True
    return report


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
