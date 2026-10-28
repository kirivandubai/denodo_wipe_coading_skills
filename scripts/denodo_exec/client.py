"""denodo_cli as a process: ``python -m denodo_cli <command> --env <profile>`` on the derived
profile, never a client of our own -- its statement parser and its safety table are kept in one
place, and a tool server that ran VQL another way would judge one text and run another.

The process is started by a Runner the tool server hands in, so every test runs on a fake and no
test reaches Denodo. denodo_cli is the one installed beside this package (the same distribution):
the interpreter that runs it is the tool server's own, and nothing is put on PYTHONPATH.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from denodo_exec.canonical import decimalise_floats
from denodo_exec.errors import Refused, Unavailable
from denodo_exec.profile import DenodoProfile
from denodo_exec.scrub import scrub

EXIT_ENVIRONMENT = 3
TIMEOUT_S = 300
MAX_ROWS = 100


@dataclass(frozen=True)
class Ran:
    code: int
    out: str
    err: str


class Answer(Protocol):
    """What a Runner hands back: an agent's own Ran serves as long as it has these."""

    code: int
    out: str
    err: str


class Runner(Protocol):
    def __call__(self, argv: Sequence[str], *, timeout: float,
                 env: Mapping[str, str] | None = None) -> Answer: ...


class Denodo:
    """denodo_cli on the derived profile; every answer parsed, floats made decimal strings and
    the password scrubbed."""

    def __init__(self, profile: DenodoProfile, profiles_file: Path, runner: Runner, *,
                 python: str, timeout_s: float = TIMEOUT_S) -> None:
        self.profile = profile
        self.profiles_file = profiles_file
        self.runner = runner
        self.python = python
        self.timeout_s = timeout_s

    def _env(self) -> dict[str, str]:
        # No DENODO_SESSION: denodo_cli's own session ledger would live beside the profiles'
        # copy, in the runtime folder, and vanish with the container; the workspace's ledger is
        # the record. No PYTHONPATH: the denodo_cli that runs is the installed one.
        return {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                "DENODO_PROFILES": str(self.profiles_file),
                "HOME": str(self.profiles_file.parent), "LANG": "C.UTF-8"}

    def call(self, *argv: str) -> tuple[dict[str, Any], int]:
        ran = self.runner([self.python, "-m", "denodo_cli", *argv, "--env", self.profile.name],
                          timeout=self.timeout_s, env=self._env())
        try:
            doc = json.loads(ran.out)
        except ValueError:
            # Scrub the whole text before slicing: a cut through the password would leave a
            # fragment that no later scrub can recognise.
            tail = scrub(ran.err.strip(), self.profile.password)[-300:]
            raise Unavailable(f"denodo_cli answered no JSON (exit {ran.code}): {tail}") from None
        if not isinstance(doc, dict):
            raise Unavailable(f"denodo_cli answered JSON that is no object (exit {ran.code})")
        doc = scrub(decimalise_floats(doc), self.profile.password)
        error = doc.get("error")
        if ran.code == EXIT_ENVIRONMENT:
            raise Unavailable("the Denodo driver is not installed in this image: "
                              f"{(error or {}).get('message')}")
        if isinstance(error, dict) and error.get("kind") == "connection":
            raise Unavailable(f"the Denodo stand does not answer at {self.profile.host}:"
                              f"{self.profile.port}: {error.get('message')}")
        if isinstance(error, dict) and error.get("kind") in ("usage", "config"):
            raise Refused(f"denodo_cli refused: {error.get('message')}")
        return doc, ran.code

    def hold(self, data: bytes) -> Path:
        """`data` in a file of mode 0600 beside the profile's copy, in the folder no one else
        writes: what denodo_cli plans and runs is what was read, not what the agent's folder
        holds by then."""
        path = self.profiles_file.parent / f"vql-{secrets.token_hex(8)}.vql"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        return path

    def plan(self, file: Path, database: str) -> dict[str, Any]:
        return self.call("vql", "plan", str(file), "--database", database)[0]

    def plan_text(self, vql: str, database: str) -> dict[str, Any]:
        return self.call("vql", "plan", "-e", vql, "--database", database)[0]

    def plan_texts(self, texts: Sequence[str], database: str) -> dict[str, Any]:
        return self.call("vql", "plan", *(part for text in texts for part in ("-e", text)),
                         "--database", database)[0]

    def run_file(self, file: Path, database: str) -> dict[str, Any]:
        return self.call("vql", "run", str(file), "--database", database,
                         "--max-rows", str(MAX_ROWS))[0]

    def run_text(self, vql: str, database: str, max_rows: int = MAX_ROWS) -> dict[str, Any]:
        return self.call("vql", "run", "-e", vql, "--database", database,
                         "--max-rows", str(max_rows))[0]

    def run_texts(self, texts: Sequence[str], database: str,
                  max_rows: int = MAX_ROWS) -> dict[str, Any]:
        """Several reads in one call, each answered whatever the one before met."""
        return self.call("vql", "run", *(part for text in texts for part in ("-e", text)),
                         "--database", database, "--max-rows", str(max_rows),
                         "--continue-on-error")[0]

    def check_env(self) -> dict[str, Any]:
        return self.call("env", "check")[0]
