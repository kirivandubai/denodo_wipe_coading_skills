"""Split a VQL script into individual statements.

Statements are separated by ``;`` outside of string literals, quoted identifiers and
comments. Comments (``--``, ``#`` and ``/* ... */``) are stripped so that a semicolon
inside a comment never splits a statement. The user's VQL is otherwise passed through
untouched — the execution layer never rewrites it.
"""

from __future__ import annotations


def split_statements(text: str) -> list[str]:
    """Return the non-empty statements of ``text`` without their trailing ``;``."""
    statements: list[str] = []
    current: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "'" or ch == '"':
            end = _skip_quoted(text, i, ch)
            current.append(text[i:end])
            i = end
        elif ch == "#" or (ch == "-" and nxt == "-"):
            i = _skip_to_end_of_line(text, i)
        elif ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif ch == ";":
            _flush(statements, current)
            i += 1
        else:
            current.append(ch)
            i += 1
    _flush(statements, current)
    return statements


def _skip_quoted(text: str, start: int, quote: str) -> int:
    """Return the index just past the literal opened at ``start`` (doubled quote escapes)."""
    i = start + 1
    n = len(text)
    while i < n:
        if text[i] == quote:
            if i + 1 < n and text[i + 1] == quote:
                i += 2
                continue
            return i + 1
        i += 1
    return n  # unterminated literal: swallow the rest, the server will report it


def _skip_to_end_of_line(text: str, start: int) -> int:
    end = text.find("\n", start)
    return len(text) if end < 0 else end  # keep the newline itself as whitespace


def _flush(statements: list[str], current: list[str]) -> None:
    statement = "".join(current).strip()
    current.clear()
    if statement:
        statements.append(statement)
