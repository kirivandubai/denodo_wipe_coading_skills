"""``api``: one REST call to Data Marketplace, status reported separately from body."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any, Callable

from . import EXIT_EXECUTION, EXIT_OK, EXIT_USAGE
from ..errors import normalize_error
from ..output import envelope
from ..profiles import Profile
from ..safety import classify_http
from ..transports.api_rest import DEFAULT_TIMEOUT


def api_call(
    profile: Profile,
    method: str,
    path: str,
    *,
    transport_factory: Callable,
    json_body: Any = None,
    params: dict[str, Any] | None = None,
    multipart: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    allow_destructive: bool = False,
) -> tuple[dict, int]:
    method = method.upper()
    destructive = classify_http(method, path, json_body)
    base = {"method": method, "path": path, "destructive": destructive}

    if destructive and profile.production and not allow_destructive:
        error = {
            "kind": "refused",
            "message": (
                f"profile {profile.name!r} is marked production and {method} {path} is destructive "
                f"({destructive}); nothing was sent. Re-run with --allow-destructive after a human has confirmed."
            ),
        }
        return envelope(False, profile, "api", **base, error=error), EXIT_USAGE

    try:
        transport = transport_factory(profile)
    except ValueError as exc:  # profile lacks marketplace_url
        return envelope(False, profile, "api", **base, error={"kind": "config", "message": str(exc)}), EXIT_USAGE

    try:
        result = transport.call(method, path, json_body=json_body, params=params, multipart=multipart, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — network-level failure, no HTTP status to report
        return envelope(False, profile, "api", **base,
                        error={"kind": "connection", **normalize_error(exc)}), EXIT_EXECUTION

    doc = envelope(result.ok, profile, "api", **base, status=result.status, body=result.body,
                   elapsed_ms=result.elapsed_ms)
    return doc, EXIT_OK if result.ok else EXIT_EXECUTION


def parse_params(specs: list[str]) -> dict[str, str]:
    """``key=value`` strings → query parameters (value may contain ``=``)."""
    params: dict[str, str] = {}
    for spec in specs:
        key, sep, value = spec.partition("=")
        if not sep or not key:
            raise ValueError(f"--param expects key=value, got {spec!r}")
        params[key] = value
    return params


def parse_multipart_specs(specs: list[str]) -> dict[str, tuple[str | None, bytes, str]]:
    """``field=@path[;content-type]`` reads a file part; ``field=json:<text>`` is an
    application/json part; anything else is a text/plain part."""
    parts: dict[str, tuple[str | None, bytes, str]] = {}
    for spec in specs:
        field, sep, value = spec.partition("=")
        if not sep or not field:
            raise ValueError(f"--part expects field=@file, field=json:{{...}} or field=text, got {spec!r}")
        if value.startswith("@"):
            location, _, content_type = value[1:].partition(";")
            file = Path(location).expanduser()
            if not file.is_file():
                raise ValueError(f"--part {field}: file not found: {file}")
            guessed = content_type or mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            parts[field] = (file.name, file.read_bytes(), guessed)
        elif value.startswith("json:"):
            text = value[len("json:"):]
            json.loads(text)  # fail early on malformed JSON
            parts[field] = (None, text.encode(), "application/json")
        else:
            parts[field] = (None, value.encode(), "text/plain")
    return parts
