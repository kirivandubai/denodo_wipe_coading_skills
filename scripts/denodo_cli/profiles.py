"""Environment profiles: where a Denodo installation lives and how to log in.

Profiles are kept outside of any project repository, in ``~/.denodo/profiles.toml``
(override with ``DENODO_PROFILES``), so that credentials never reach git or a command
line. A command only ever names a profile (``--env dev``).

Format::

    [dev]
    host = "localhost"                     # Virtual DataPort host
    port = 9996                            # PostgreSQL-protocol port (default 9996)
    database = "admin"                     # database to connect to (default admin)
    user = "admin"
    password = "..."                       # or: password_env = "DENODO_DEV_PASSWORD"
    production = false                     # true → destructive operations need --allow-destructive
    transport = "vql_psycopg2"             # vql_psycopg2 (default) | vql_flightsql (not in v1)
    marketplace_url = "http://localhost:9090/denodo-data-catalog"   # optional; enables `api`
    # marketplace_server_id = 1            # optional; only with several VDP servers registered
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path("~/.denodo/profiles.toml")
DEFAULT_PORT = 9996
DEFAULT_DATABASE = "admin"
DEFAULT_TRANSPORT = "vql_psycopg2"
KNOWN_TRANSPORTS = ("vql_psycopg2", "vql_flightsql")
REQUIRED_FIELDS = ("host", "user")
KNOWN_FIELDS = REQUIRED_FIELDS + (
    "port", "database", "password", "password_env", "production", "transport",
    "marketplace_url", "marketplace_server_id",
)


class ProfileError(Exception):
    """A profile is missing, malformed or incomplete. Message is user-facing."""


@dataclass(frozen=True)
class Profile:
    name: str
    host: str
    port: int
    database: str
    user: str
    password: str
    production: bool
    transport: str
    marketplace_url: str | None
    marketplace_server_id: int | None

    def public(self) -> dict:
        """Everything except the password — safe for output and logs."""
        return {
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "production": self.production,
            "transport": self.transport,
            "marketplace_url": self.marketplace_url,
            "marketplace_server_id": self.marketplace_server_id,
        }


def profiles_path() -> Path:
    return Path(os.environ.get("DENODO_PROFILES") or DEFAULT_PATH).expanduser()


def _read_all(path: Path) -> dict:
    if not path.exists():
        raise ProfileError(
            f"profiles file not found: {path}. Create it with `scripts/denodo env init` "
            f"(interactive, run it yourself so the password never enters a transcript) or point "
            f"DENODO_PROFILES at an existing file."
        )
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"cannot parse {path}: {exc}") from exc


def load_profile(name: str, path: Path | None = None) -> Profile:
    path = path or profiles_path()
    data = _read_all(path)
    if name not in data or not isinstance(data[name], dict):
        available = ", ".join(sorted(k for k, v in data.items() if isinstance(v, dict))) or "none"
        raise ProfileError(f"profile {name!r} not found in {path}; available profiles: {available}")
    raw = data[name]
    missing = [f for f in REQUIRED_FIELDS if not raw.get(f)]
    if "password" not in raw and "password_env" not in raw:
        missing.append("password (or password_env)")
    if missing:
        raise ProfileError(f"profile {name!r} in {path} lacks required field(s): {', '.join(missing)}")
    unknown = sorted(set(raw) - set(KNOWN_FIELDS))
    if unknown:
        raise ProfileError(f"profile {name!r} has unknown field(s): {', '.join(unknown)}")

    if "password_env" in raw:
        var = str(raw["password_env"])
        password = os.environ.get(var)
        if password is None:
            raise ProfileError(f"profile {name!r} takes its password from environment variable "
                               f"{var}, which is not set")
    else:
        password = str(raw["password"])

    transport = str(raw.get("transport", DEFAULT_TRANSPORT))
    if transport not in KNOWN_TRANSPORTS:
        raise ProfileError(f"profile {name!r}: unknown transport {transport!r}; "
                           f"known: {', '.join(KNOWN_TRANSPORTS)}")
    marketplace_url = raw.get("marketplace_url")
    server_id = raw.get("marketplace_server_id")
    return Profile(
        name=name,
        host=str(raw["host"]),
        port=int(raw.get("port", DEFAULT_PORT)),
        database=str(raw.get("database", DEFAULT_DATABASE)),
        user=str(raw["user"]),
        password=password,
        production=bool(raw.get("production", False)),
        transport=transport,
        marketplace_url=str(marketplace_url).rstrip("/") if marketplace_url else None,
        marketplace_server_id=int(server_id) if server_id is not None else None,
    )


def list_profiles(path: Path | None = None) -> list[dict]:
    """Names and connection facts of all profiles, never their passwords."""
    path = path or profiles_path()
    if not path.exists():
        return []
    data = _read_all(path)
    listed = []
    for name, raw in data.items():
        if not isinstance(raw, dict):
            continue
        listed.append({
            "name": name,
            "host": raw.get("host"),
            "port": raw.get("port", DEFAULT_PORT),
            "database": raw.get("database", DEFAULT_DATABASE),
            "user": raw.get("user"),
            "production": bool(raw.get("production", False)),
            "transport": raw.get("transport", DEFAULT_TRANSPORT),
            "marketplace_url": raw.get("marketplace_url"),
            "password_source": "env:" + str(raw["password_env"]) if "password_env" in raw else "file",
        })
    return listed


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_section(profile: Profile) -> str:
    """One ``[name]`` TOML section for ``profile``; password stored inline."""
    lines = [
        f"[{profile.name}]",
        f"host = {_toml_string(profile.host)}",
        f"port = {profile.port}",
        f"database = {_toml_string(profile.database)}",
        f"user = {_toml_string(profile.user)}",
        f"password = {_toml_string(profile.password)}",
        f"production = {'true' if profile.production else 'false'}",
        f"transport = {_toml_string(profile.transport)}",
    ]
    if profile.marketplace_url:
        lines.append(f"marketplace_url = {_toml_string(profile.marketplace_url)}")
    if profile.marketplace_server_id is not None:
        lines.append(f"marketplace_server_id = {profile.marketplace_server_id}")
    return "\n".join(lines) + "\n"


def write_profile(path: Path, profile: Profile) -> None:
    """Append ``profile`` as a new section; the file is created mode 0600 if needed."""
    existing = _read_all(path) if path.exists() else {}
    if profile.name in existing:
        raise ProfileError(f"profile {profile.name!r} already exists in {path}; edit the file to change it")
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.read_text() if path.exists() else ""
    if current and not current.endswith("\n"):
        current += "\n"
    if current:
        current += "\n"
    path.write_text(current + render_section(profile))
    os.chmod(path, 0o600)
