"""``api``: one REST call to Data Marketplace or the Scheduler, status reported separately
from body."""

from __future__ import annotations

import json
import mimetypes
import re
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from . import EXIT_EXECUTION, EXIT_OK, EXIT_USAGE
from ..errors import normalize_error
from ..ledger import server_key
from ..output import envelope
from ..planner import YES_NOTE
from ..profiles import Profile
from ..safety import classify_http
from ..statements import ObjectRef
from ..transports.api_rest import DEFAULT_TIMEOUT

_CATALOG_SYNC = re.compile(r"^/public/api/element-management/(DATABASES|VIEWS)/synchronize$")
_AFTER_SYNC = ("after the call, read removed and inserted against this radius, then both changes again — removed "
               "can be empty while elements went (/denodo:marketplace)")


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
    server: str = "marketplace",
    plan: bool = False,
    ledger=None,
) -> tuple[dict, int]:
    method = method.upper()
    destructive = classify_http(method, path, json_body, server=server)
    base = {"server": server, "method": method, "path": path, "destructive": destructive}

    if _climbs_out(path):
        # The account goes with every call; a path that climbs out of the server's base URL
        # would hand it to another web application of the same container (T36 baselines tried
        # `../webadmin/...` to reach the Scheduler through the marketplace).
        return envelope(False, profile, "api", **base, error={
            "kind": "usage",
            "message": f"the path {path!r} contains a '..' segment; nothing was sent. The Scheduler is "
                       "`api --server scheduler`, the Data Marketplace the default server"}), EXIT_USAGE

    if plan:
        return _plan_call(profile, method, path, json_body, base, transport_factory=transport_factory,
                          server=server, ledger=ledger, timeout=timeout)

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
        transport = transport_factory(profile, server=server)
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


def _plan_call(profile: Profile, method: str, path: str, body: Any, base: dict, *, transport_factory: Callable,
               server: str, ledger, timeout: float) -> tuple[dict, int]:
    """``api … --plan``: the call is not sent. Whether the core's table puts it under the human's yes,
    and for a catalog synchronisation the radius read against the session's ledger (T39)."""
    route = urllib.parse.urlsplit(path).path.rstrip("/")
    doc = envelope(True, profile, "api", **base, sent=False)

    def decide(needs_yes, why, conditions=None):
        doc.update(needs_yes=needs_yes, why=why, conditions=conditions or [])
        if needs_yes is True:
            doc["yes"] = YES_NOTE
        return doc, EXIT_OK

    destructive = base["destructive"]
    if method == "GET":
        return decide(False, "a read")
    if profile.production and destructive:
        return decide(True, "the profile is production: every change waits for the human's yes")
    if server == "scheduler":
        if destructive == "delete":
            return decide(True, "a deletion on the Scheduler (/denodo:scheduler)")
        return decide(None, "whose job or project it changes decides (/denodo:scheduler)")
    sync = _CATALOG_SYNC.match(route)
    if sync and method == "POST":
        return _plan_radius(profile, body, doc, decide, transport_factory=transport_factory, ledger=ledger,
                            timeout=timeout)
    if destructive == "delete":
        return decide(True, "a DELETE removes the object and everything attached to it (/denodo:vql)")
    if destructive == "replace":
        conditions = []
        if "/external-tool-servers/" in route + "/":
            conditions.append("the first import on an external tool server you created in this session is yours "
                              "(/denodo:vql, second exception) — the ledger records no marketplace objects")
        return decide(True, "it replaces a whole set, or deletes what is missing from the body (/denodo:vql)",
                      conditions)
    return decide(None, "not a destructive call: whose element it changes decides (/denodo:marketplace)")


def _plan_radius(profile: Profile, body: Any, doc: dict, decide, *, transport_factory: Callable, ledger,
                 timeout: float) -> tuple[dict, int]:
    server = server_key(profile.host, profile.port)
    body = body if isinstance(body, dict) else {}
    try:
        transport = transport_factory(profile, server="marketplace")
    except ValueError as exc:
        return envelope(False, profile, "api", **{k: doc[k] for k in ("server", "method", "path", "destructive")},
                        error={"kind": "config", "message": str(exc)}), EXIT_USAGE
    radius = {"own": True, "not_own": [], "modified": 0, "entries": 0}
    for half in ("DATABASES", "VIEWS"):
        try:
            result = transport.call("GET", f"/public/api/element-management/{half}/changes", timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            return decide(True, f"the radius could not be read ({half}/changes: {normalize_error(exc)['message']})")
        if not result.ok or not isinstance(result.body, dict):
            return decide(True, f"the radius could not be read ({half}/changes answered {result.status})")
        changes = result.body
        radius["modified"] += len(changes.get("modifiedElements") or [])
        for listing in ("serverElements", "localElements"):
            for element in changes.get(listing) or []:
                radius["entries"] += 1
                if not _own_element(ledger, server, half, listing, element):
                    radius["not_own"].append({"half": half, "list": listing, **element})
    for pair in body.get("matchedElements") or []:
        old, new = pair.get("localElement") or {}, pair.get("serverElement") or {}
        if not _own_rename(ledger, server, old, new):
            radius["not_own"].append({"half": "VIEWS", "list": "matchedElements", "localElement": old,
                                      "serverElement": new})
    radius["own"] = not radius["not_own"]
    doc["radius"] = radius
    mode = body.get("proceedWithConflicts")
    if mode != "SERVER_WITH_LOCAL_CHANGES":
        return decide(True, f"proceedWithConflicts is {mode!r}: only SERVER_WITH_LOCAL_CHANGES keeps the descriptions "
                            "edited in the marketplace (/denodo:marketplace)")
    if not radius["own"]:
        return decide(True, "the radius holds what you did not create in this session — the body goes in a file and "
                            "the call waits for the yes (/denodo:vql, first exception)")
    return decide(False, "every entry of both changes is yours from this session (/denodo:vql, first exception)",
                  [_AFTER_SYNC])


def _own_element(ledger, server: str, half: str, listing: str, element: dict) -> bool:
    if ledger is None:
        return False
    database = element.get("databaseName")
    if half == "DATABASES":
        ref = ObjectRef("database", None, str(database))
    else:
        ref = ObjectRef("view", str(database), str(element.get("elementName")))
    if listing == "serverElements":
        return ledger.find(server, ref) is not None
    return ledger.former(server, ref) is not None


def _own_rename(ledger, server: str, old: dict, new: dict) -> bool:
    if ledger is None or old.get("databaseName") != new.get("databaseName"):
        return False
    current = ledger.find(server, ObjectRef("view", str(new.get("databaseName")), str(new.get("elementName"))))
    if current is None:
        return False
    return str(old.get("elementName", "")).lower() in [n.lower() for n in current.get("names", [])]


def _climbs_out(path: str) -> bool:
    route = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
    return ".." in route.split("/")


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
