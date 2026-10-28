"""Canonical JSON, digests and timestamps: what a record hashes to tell a changed input.

Wherever bytes are hashed, they are the output of `canonical_json`. The rules
are few and each one exists because its absence would make a hash unstable:

    keys sorted by code point      two writers must agree on order
    tight separators               whitespace is not information
    UTF-8, no \\u escaping         one spelling per string
    no floats, anywhere            text form varies across runtimes
    RFC 3339 UTC, milliseconds     one spelling per instant

The float rule is the one that looks excessive and is not. `0.1` may serialise
as `0.1` in one runtime and `0.1000000000000000055511151231257827` in another;
a chain of hashes over that is a chain that breaks when the reader changes.
A value we author is an integer where a fraction would be tempting. Numbers
from external services that enter canonical records are recorded as decimal
strings (decimalise_floats).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from denodo_exec.errors import CanonicalError

UTC = timezone.utc


def _check(value: Any) -> None:
    """Walk a value and refuse anything canonical form cannot represent.

    json.dumps would accept most of this and quietly change it -- floats keep a
    runtime-specific spelling, and non-string keys are coerced to strings. Both
    would produce a record that no longer means what the caller wrote.
    """
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        raise CanonicalError(f"floats are not canonical: {value!r}")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalError(f"object keys must be strings, got {type(key).__name__}")
            _check(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _check(item)
        return
    raise CanonicalError(f"{type(value).__name__} has no canonical representation")


def canonical_json(value: Any) -> str:
    """The one text form of `value`."""
    _check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_bytes(value: Any) -> bytes:
    """UTF-8 bytes of `canonical_json(value)` -- what actually gets hashed."""
    return canonical_json(value).encode("utf-8")


def decimalise_floats(value: Any) -> Any:
    """Rewrite floats as their decimal string form, recursively: `0.5` -> `"0.5"`.

    For numbers that arrive from somewhere we do not control -- a value in a row of the Denodo
    server, a setting of another service -- and that have to enter a record or a digest all the
    same. Dropping the field would make two different inputs digest alike, and a record would
    look current when it is not; refusing the whole digest would let one descriptive number,
    chosen by somebody else's server, stop work that has nothing else wrong with it. A decimal
    string keeps the value legible to `jq` and to a human, and keeps the hash stable, which is
    all the no-floats rule was ever protecting.

    The string is Python's shortest round-tripping spelling of the double.
    That is stable for a given value on any runtime this code runs on, and --
    unlike a float -- it is stable *through* the record: once written, the
    bytes are the bytes, whatever reads them next.

    Integers pass through as integers, and booleans stay booleans:
    `isinstance(True, int)` is true, so bools are answered first or `True`
    would come back as `1`.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, dict):
        return {key: decimalise_floats(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [decimalise_floats(item) for item in value]
    return value


def digest_bytes(data: bytes) -> str:
    """`sha256:` followed by 64 lowercase hex digits."""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def digest_canonical(value: Any) -> str:
    """The digest of `value`'s canonical bytes -- independent of key order."""
    return digest_bytes(canonical_bytes(value))


def format_timestamp(moment: datetime) -> str:
    """RFC 3339 UTC with milliseconds.

    A naive datetime is refused rather than assumed to be UTC: the assumption
    is right about half the time, and the record keeps no note of which half.
    """
    if moment.tzinfo is None:
        raise CanonicalError("timestamps must carry a timezone")
    utc = moment.astimezone(UTC)
    # Truncation, not rounding: rounding could carry into the next second and
    # move an event across a boundary it was recorded before.
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{utc.microsecond // 1000:03d}Z"


def now_timestamp() -> str:
    """The current instant, already in canonical form."""
    return format_timestamp(datetime.now(UTC))
