"""A tool server's records on disk: whole or absent, and appended without following a link.

Every write is a temporary file in the same folder renamed over the old one, so a failure in the
middle leaves the previous record whole. A JSONL line is appended through a descriptor that
follows no link, and a line torn by a full disk or a killed container is mended by the next
append and left out by a read. What is written is canonical JSON (canonical.py), so a digest of
a record is the same whoever reads it.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from denodo_exec.canonical import canonical_bytes, decimalise_floats, digest_canonical
from denodo_exec.errors import Refused


def write_bytes(path: Path, data: bytes) -> None:
    """`data` at `path`, or the old bytes: a temporary file in the same folder, renamed over."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def write_json(path: Path, value: Any) -> None:
    write_bytes(path, canonical_bytes(value) + b"\n")


def write_text(path: Path, text: str) -> None:
    write_bytes(path, text.encode("utf-8"))


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Refused(f"{path.name} is not there yet") from None
    except (ValueError, UnicodeDecodeError) as error:
        raise Refused(f"{path.name} is not valid JSON: {error}") from None


def _whole(line: bytes) -> bool:
    try:
        json.loads(line)
    except ValueError:
        return False
    return True


def append_jsonl(path: Path, value: Any) -> None:
    """One canonical line appended. A last line without its newline -- an append cut off by a
    full disk or a killed container -- is mended first: completed when it is whole JSON, cut
    away when it is not, so the new line never lands glued to its end."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = canonical_bytes(value) + b"\n"
    # O_NOFOLLOW: an append opens the file where it is, so a link at its name would carry the
    # line into whatever it points at -- an agent may write beside its server. Refused.
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o666)
    except OSError as error:
        if path.is_symlink():
            raise Refused(f"{path.name} is a link: no line is appended through it") from None
        raise error
    with os.fdopen(descriptor, "a+b") as stream:
        size = stream.seek(0, os.SEEK_END)
        if size:
            stream.seek(size - 1)
            if stream.read(1) != b"\n":
                stream.seek(0)
                data = stream.read()
                start = data.rfind(b"\n") + 1
                if _whole(data[start:]):
                    stream.write(b"\n")
                else:
                    stream.truncate(start)
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())


def write_jsonl(path: Path, values: Iterable[Any]) -> None:
    """Every value a canonical line, written whole -- a temporary file renamed over, as
    write_bytes does -- where a log is made at once rather than appended to."""
    write_bytes(path, b"".join(canonical_bytes(value) + b"\n" for value in values))


def read_jsonl(path: Path) -> list[Any]:
    """Every line, in order. A malformed line refuses the file -- but the last one when it has
    no newline: that is a torn append, and the line it would have been was never written."""
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Bytes written over a record by whatever else writes beside it refuse what reads it,
        # in a sentence -- never an internal error.
        raise Refused(f"{path.name} is not text: something else was written over it -- "
                      "nothing that reads it goes on; tell the owner") from None
    lines = text.splitlines()
    torn = bool(text) and not text.endswith("\n")
    found = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            found.append(json.loads(line))
        except ValueError:
            if torn and number == len(lines):
                break
            raise Refused(f"{path.name} line {number} is not JSON") from None
    return found


def file_digest(path: Path) -> str | None:
    """`sha256:` and the hex digest of the file's bytes, or None when there is no file."""
    if not path.is_file():
        return None
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            hasher.update(block)
    return f"sha256:{hasher.hexdigest()}"


def bytes_digest(data: bytes) -> str:
    """file_digest of bytes already read: what was checked is what is recorded."""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def digest(value: Any) -> str:
    """The digest of a value that may hold a float from the server or a service: its decimal
    spelling is hashed, so the digest is stable and the value keeps its meaning."""
    return digest_canonical(decimalise_floats(value))
