"""``verify``: run the v1 chain of skill templates against a stand and clean up.

The plan is data (``verification/chain.toml``), the mechanics are here. A step either
points at a block of a skill (``template`` — the thing being verified) or carries its own
body (``fixture`` — scaffolding that makes the chain reachable). Substitutions are exact
strings, and one that does not occur in the block is an error: silently skipping it would
send the run into somebody else's database.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

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
    return Chain(values=values, steps=steps)


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
