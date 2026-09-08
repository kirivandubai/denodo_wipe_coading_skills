"""``env list | check | init``: which Denodo installations this machine knows about.

``env init`` is interactive on purpose: the human runs it themselves (in Claude Code:
``! scripts/denodo env init``) so the password is typed into a hidden prompt and never
lands in a command line or a session transcript.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from . import EXIT_EXECUTION, EXIT_OK, EXIT_USAGE
from ..errors import normalize_error
from ..output import envelope
from ..profiles import (
    DEFAULT_DATABASE, DEFAULT_PORT, DEFAULT_TRANSPORT, Profile, ProfileError, list_profiles, write_profile,
)

_VERSION = re.compile(r"Denodo Platform ([0-9]+(?:\.[0-9]+)*)")


def list_environments(path: Path) -> tuple[dict, int]:
    try:
        profiles = list_profiles(path)
    except ProfileError as exc:
        return envelope(False, None, "env list", path=str(path),
                        error={"kind": "config", "message": str(exc)}), EXIT_USAGE
    return envelope(True, None, "env list", path=str(path), profiles=profiles), EXIT_OK


def _check_vdp(profile: Profile, vql_factory: Callable) -> dict:
    try:
        transport = vql_factory(profile)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": normalize_error(exc)}
    try:
        transport.execute("SELECT 1 AS alive FROM DUAL()")
        version = None
        try:
            # First line of the database export names the server version (spike T2, 3.6).
            result = transport.execute(f"DESC VQL DATABASE {profile.database}")
            if result.rows:
                match = _VERSION.search(str(result.rows[0][0]))
                version = match.group(1) if match else None
        except Exception:  # noqa: BLE001 — version is a nicety, not a check
            version = None
        return {"ok": True, "server_version": version}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": normalize_error(exc)}
    finally:
        transport.close()


def _check_marketplace(profile: Profile, rest_factory: Callable) -> dict:
    try:
        result = rest_factory(profile).call("GET", "/public/api/tags/count", timeout=30)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": normalize_error(exc)}
    doc = {"ok": result.ok, "status": result.status, "url": profile.marketplace_url}
    if not result.ok:
        doc["body"] = result.body
    return doc


def check_environment(profile: Profile, *, vql_factory: Callable, rest_factory: Callable) -> tuple[dict, int]:
    vdp = _check_vdp(profile, vql_factory)
    marketplace = _check_marketplace(profile, rest_factory) if profile.marketplace_url else None
    ok = vdp["ok"] and (marketplace is None or marketplace["ok"])
    doc = envelope(ok, profile, "env check", vdp=vdp, marketplace=marketplace, connection=profile.public())
    return doc, EXIT_OK if ok else EXIT_EXECUTION


def init_environment(path: Path, *, ask: Callable[..., str], ask_secret: Callable[[str], str]) -> tuple[dict, int]:
    """Build one profile from answers and append it to ``path``."""
    def usage(message: str) -> tuple[dict, int]:
        return envelope(False, None, "env init", path=str(path),
                        error={"kind": "usage", "message": message}), EXIT_USAGE

    name = ask("Profile name", "dev").strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", name):
        return usage("profile name may contain letters, digits, '_' and '-' only")
    host = ask("Virtual DataPort host", "localhost").strip()
    port_text = ask("Port (PostgreSQL protocol)", str(DEFAULT_PORT)).strip()
    if not port_text.isdigit():
        return usage(f"port must be a number, got {port_text!r}")
    database = ask("Database to connect to", DEFAULT_DATABASE).strip() or DEFAULT_DATABASE
    user = ask("User", "").strip()
    if not host or not user:
        return usage("host and user are required")
    password = ask_secret("Password (hidden): ")
    if not password:
        return usage("password must not be empty; use password_env in the file for env-based secrets")
    production = ask("Is this a production environment? [y/N]", "n").strip().lower().startswith("y")
    marketplace_url = ask("Data Marketplace URL (empty if none)", "").strip() or None
    server_id_text = ask("Data Marketplace serverId (empty unless several VDP servers are registered)", "").strip()
    if server_id_text and not server_id_text.isdigit():
        return usage(f"serverId must be a number, got {server_id_text!r}")

    profile = Profile(
        name=name, host=host, port=int(port_text), database=database, user=user, password=password,
        production=production, transport=DEFAULT_TRANSPORT,
        marketplace_url=marketplace_url.rstrip("/") if marketplace_url else None,
        marketplace_server_id=int(server_id_text) if server_id_text else None,
    )
    try:
        write_profile(path, profile)
    except ProfileError as exc:
        return usage(str(exc))
    return envelope(True, None, "env init", path=str(path), connection=profile.public()), EXIT_OK
