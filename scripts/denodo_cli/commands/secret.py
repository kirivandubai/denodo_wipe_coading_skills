"""``secret encrypt``: turn a password into the ciphertext a data source can carry.

The plaintext lives inside this one call and nowhere else. It never becomes a command-line
argument (``cli.py`` reads it from a hidden prompt or from stdin), the statement carrying it
is never echoed into the result — which is why this command does not go through
``run_statements``, whose result and error both quote the statement — and a server error
that quotes the statement back is scrubbed before it is reported.

The ciphertext is bound to the server that produced it, so the profile decides where the
password is encrypted, exactly as it decides where VQL is applied.
"""

from __future__ import annotations

from typing import Any, Callable

from . import EXIT_EXECUTION, EXIT_OK
from ..errors import normalize_error
from ..output import envelope
from ..profiles import Profile

REDACTED = "<password>"


def quote_literal(value: str) -> str:
    """A VQL string literal: single quotes, and a quote inside is doubled."""
    return "'" + value.replace("'", "''") + "'"


def _scrub(value: Any, password: str) -> Any:
    """Remove the password from anything the server said before it is printed."""
    if isinstance(value, str):
        return value.replace(password, REDACTED)
    if isinstance(value, dict):
        return {k: _scrub(v, password) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, password) for v in value]
    return value


def encrypt_password(profile: Profile, password: str, *, transport_factory: Callable) -> tuple[dict, int]:
    def failure(kind: str, info: dict) -> tuple[dict, int]:
        return envelope(False, profile, "secret encrypt",
                        error={"kind": kind, **_scrub(info, password)}), EXIT_EXECUTION

    try:
        transport = transport_factory(profile)
    except Exception as exc:  # noqa: BLE001 — any driver/network failure is a connection error here
        return failure("connection", normalize_error(exc))

    try:
        result = transport.execute(f"ENCRYPT_PASSWORD {quote_literal(password)}")
    except Exception as exc:  # noqa: BLE001 — server error text is the payload
        return failure("execution", normalize_error(exc))
    finally:
        transport.close()

    if not result.rows or not result.rows[0]:
        return failure("execution", {"message": "ENCRYPT_PASSWORD returned no row; nothing was encrypted"})
    return envelope(True, profile, "secret encrypt", encrypted=str(result.rows[0][0])), EXIT_OK
