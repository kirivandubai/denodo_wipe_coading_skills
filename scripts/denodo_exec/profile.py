"""The copy of one profile a containerised denodo_cli is pointed at.

The profiles file is mounted read-only into the container; it may hold every server its owner
works with. A copy of the one profile the tool server uses is written into a private runtime
folder (a tmpfs, say), its host moved from localhost to the host the container reaches, and
denodo_cli is pointed at the copy with ``DENODO_PROFILES``. A profile marked
``production = true`` is never opened: the agent's yes is not the owner's yes.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from denodo_exec.errors import Refused, Unavailable

LOCALHOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# What the copy keeps of the owner's section; password_env is resolved into password.
FIELDS = ("host", "port", "database", "user", "production", "transport", "marketplace_url",
          "marketplace_server_id", "jdbc_port", "scheduler_url", "scheduler_uri")
URL_FIELDS = ("marketplace_url", "scheduler_url")
COPY_NAME = "profiles.toml"


@dataclass(frozen=True)
class DenodoProfile:
    name: str
    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)


def derive_profile(source: Path, name: str, host: str, runtime: Path, *,
                   who: str = "the server", hint: str = "") -> tuple[DenodoProfile, Path]:
    """The copy of profile `name` denodo_cli is pointed at, and what the server needs of it.
    `who` names the tool server in a refusal; `hint` follows the sentence for a missing file
    (how the file is meant to reach the container)."""
    try:
        data = tomllib.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Unavailable(f"no Denodo profiles at {source}{hint}") from None
    except tomllib.TOMLDecodeError as error:
        # The decoder names a line and a column, never the line's text.
        raise Unavailable(f"{source.name} is not valid TOML ({error})") from None
    raw = data.get(name)
    if not isinstance(raw, dict):
        raise Unavailable(f"no profile {name!r} in {source.name}")
    if raw.get("production") is True:
        raise Refused(f"profile {name!r} is marked production = true: {who} never opens a "
                      "production server")
    password = raw.get("password")
    if password is None and raw.get("password_env"):
        password = os.environ.get(str(raw["password_env"]))
        if password is None:
            raise Unavailable(f"profile {name!r} takes its password from "
                              f"{raw['password_env']}, which {who} is not given")
    if not isinstance(password, str) or not raw.get("host") or not raw.get("user"):
        raise Unavailable(f"profile {name!r} lacks host, user or password")
    section = {key: raw[key] for key in FIELDS if key in raw}
    if str(raw["host"]).lower() in LOCALHOSTS:
        section["host"] = host
    for key in URL_FIELDS:
        if isinstance(section.get(key), str):
            section[key] = _moved(section[key], host)
    section["password"] = password
    runtime.mkdir(parents=True, exist_ok=True)
    os.chmod(runtime, 0o700)
    path = runtime / COPY_NAME
    text = f"[{name}]\n" + "".join(f"{key} = {_toml(value)}\n" for key, value in section.items())
    _replace_private(path, text)
    profile = DenodoProfile(name=name, host=str(section["host"]),
                            port=int(section.get("port", 9996)),
                            database=str(section.get("database", "admin")),
                            user=str(section["user"]), password=password)
    return profile, path


def _replace_private(path: Path, text: str) -> None:
    """`text` at `path`, mode 0600, renamed over the old copy: a call of denodo_cli already
    running reads the old copy or the new one, never an empty file truncated under it -- as
    writing in place would leave it while the password changes."""
    # mkstemp makes the file 0600 whatever the umask; the rename keeps that mode.
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def _moved(url: str, host: str) -> str:
    parts = urlsplit(url)
    if (parts.hostname or "").lower() not in LOCALHOSTS:
        return url
    netloc = host + (f":{parts.port}" if parts.port else "")
    return urlunsplit(parts._replace(netloc=netloc))


def _toml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return f'"{text}"'
