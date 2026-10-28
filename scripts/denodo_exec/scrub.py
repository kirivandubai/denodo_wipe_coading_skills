"""The password out of every answer a tool server gives.

The profile's password reaches denodo_cli and nothing else; a server's message can still quote
it (a failed login, a statement echoed back), so every answer is scrubbed before it leaves.
"""

from __future__ import annotations

from typing import Any

# A secret shorter than this is a word (a user's or a database's name, "admin"): scrubbing it
# would rewrite names that merely contain it, so it is neither scrubbed nor scanned for.
SECRET_MIN = 6
SECRET_MARK = "<secret>"


def scrub(value: Any, secret: str) -> Any:
    """`value` with every occurrence of `secret` in its strings replaced by <secret>."""
    if not secret or len(secret) < SECRET_MIN:
        return value
    if isinstance(value, str):
        return value.replace(secret, SECRET_MARK)
    if isinstance(value, dict):
        return {key: scrub(item, secret) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item, secret) for item in value]
    return value
