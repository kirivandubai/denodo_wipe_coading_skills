"""REST transport for Data Marketplace — standard library only.

Decisions from spike T11 (section 2): HTTP Basic with the VDP account on every request
and no cookie jar (the server opens a session per call; that is the price of stateless
mode); ``serverId`` from the profile is added only when set and not already given;
HTTP errors are not raised — the status is returned separately from the body, because
``409`` and ``403`` often arrive with an empty body.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from ..profiles import Profile
from .base import HttpResult

DEFAULT_TIMEOUT = 300  # element-management/all/synchronize can be slow on a big catalog

# field → (filename or None, content bytes, content type)
MultipartParts = dict[str, tuple[str | None, bytes, str]]


class RestTransport:
    def __init__(self, profile: Profile) -> None:
        if not profile.marketplace_url:
            raise ValueError(
                f"profile {profile.name!r} has no marketplace_url; add it to the profile to use the REST API"
            )
        self.base_url = profile.marketplace_url.rstrip("/")
        self.server_id = profile.marketplace_server_id
        token = base64.b64encode(f"{profile.user}:{profile.password}".encode()).decode()
        self._auth_header = "Basic " + token

    def call(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        multipart: MultipartParts | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> HttpResult:
        query = dict(params or {})
        if self.server_id is not None and "serverId" not in query:
            query["serverId"] = self.server_id
        url = self.base_url + "/" + path.lstrip("/")
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)

        headers = {"Accept": "application/json", "Authorization": self._auth_header}
        data: bytes | None = None
        if multipart is not None:
            data, content_type = _encode_multipart(multipart)
            headers["Content-Type"] = content_type
        elif json_body is not None:
            data = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw, status, response_headers = response.read(), response.status, dict(response.headers)
        except urllib.error.HTTPError as err:
            raw, status, response_headers = err.read(), err.code, dict(err.headers)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return HttpResult(status=status, body=_parse_body(raw), headers=response_headers, elapsed_ms=elapsed_ms)


def _parse_body(raw: bytes) -> Any:
    if not raw:
        return None
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        return text


def _encode_multipart(parts: MultipartParts) -> tuple[bytes, str]:
    boundary = "----denodo-cli-" + uuid.uuid4().hex
    chunks = []
    for field, (filename, content, content_type) in parts.items():
        disposition = f'form-data; name="{field}"'
        if filename:
            disposition += f'; filename="{filename}"'
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: {disposition}\r\nContent-Type: {content_type}\r\n\r\n".encode()
            + content
            + b"\r\n"
        )
    body = b"".join(chunks) + f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"
