"""The scenarios of the outcome evals: `scenarios/<name>/scenario.toml` and its `fixture.toml`.

`scenario.toml` holds the human's request — one `[[turn]]` per message, a second turn being the
human's answer — the limits of the run and the `[[check]]` list (`checks.py`). `fixture.toml` is
a manifest of `scripts/denodo verify`: its steps build what the request starts from, its
`[cleanup]` removes the fixture and whatever the agent left inside it. What the agent creates
outside it on a server-wide object — a marketplace tag — is removed by name: `[[teardown_api]]`
looks the object up, matches the exact name and deletes it by id.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import checks

GATES = ("writes", "marketplace")
DEFAULT_TURNS = 60
DEFAULT_TIMEOUT = 1800
DEFAULT_BUDGET = 15.0
# Check parameters filled with the fixture's values before they are used.
RENDERED = ("query", "path", "pattern")
PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


class ScenarioError(Exception):
    pass


@dataclass
class Scenario:
    name: str
    directory: Path
    description: str
    turns: list[str]
    checks: list[dict]
    fixture: Path
    gates: list[str] = field(default_factory=list)
    needs_local_files: bool = False
    max_turns: int = DEFAULT_TURNS
    timeout_seconds: int = DEFAULT_TIMEOUT
    max_budget_usd: float = DEFAULT_BUDGET
    teardown_api: list[dict] = field(default_factory=list)


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def load(directory: Path) -> Scenario:
    path = directory / "scenario.toml"
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ScenarioError(f"{path}: {exc}") from exc
    name = directory.name

    def fail(message: str) -> ScenarioError:
        return ScenarioError(f"scenario {name!r}: {message}")

    gates = raw.get("gates", [])
    if not isinstance(gates, list) or any(g not in GATES for g in gates):
        raise fail(f"gates must be a list of {GATES}, got {gates!r}")
    turns = [t.get("prompt") for t in raw.get("turn", []) if isinstance(t, dict)]
    if not turns or not all(isinstance(t, str) and t.strip() for t in turns):
        raise fail("needs at least one [[turn]] with a prompt")
    specs = raw.get("check", [])
    if not specs:
        raise fail("needs at least one [[check]]")
    for spec in specs:
        try:
            checks.validate(spec)
        except ValueError as exc:
            raise fail(str(exc)) from exc
        if "turn" in spec and not (isinstance(spec["turn"], int) and 1 <= spec["turn"] <= len(turns)):
            raise fail(f"check {spec['name']!r} names turn {spec['turn']}, the scenario has {len(turns)}")
    fixture = directory / "fixture.toml"
    if not fixture.is_file():
        raise fail(f"no fixture.toml in {directory}")
    teardown = raw.get("teardown_api", [])
    for entry in teardown:
        if not all(isinstance(entry.get(k), str) and entry[k] for k in ("lookup", "name", "delete")):
            raise fail(f"every [[teardown_api]] needs lookup, name and delete, got {entry!r}")
    return Scenario(
        name=name, directory=directory, description=str(raw.get("description", "")), turns=turns, checks=specs,
        fixture=fixture, gates=list(gates), needs_local_files=bool(raw.get("needs_local_files", False)),
        max_turns=int(raw.get("max_turns", DEFAULT_TURNS)),
        timeout_seconds=int(raw.get("timeout_seconds", DEFAULT_TIMEOUT)),
        max_budget_usd=float(raw.get("max_budget_usd", DEFAULT_BUDGET)), teardown_api=list(teardown))


def load_all(root: Path) -> list[Scenario]:
    """Every scenario under ``<root>/scenarios``, by name."""
    return [load(path.parent) for path in sorted((root / "scenarios").glob("*/scenario.toml"))]
