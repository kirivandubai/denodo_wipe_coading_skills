"""Split a VQL script into individual statements.

Statements are separated by ``;`` outside of string literals, quoted identifiers and
comments. Comments (``--``, ``#`` and ``/* ... */``) are stripped so that a semicolon
inside a comment never splits a statement. The user's VQL is otherwise passed through
untouched — the execution layer never rewrites it.

One statement carries semicolons of its own: the body of a VQL procedure
(``CREATE [OR REPLACE] VQL PROCEDURE``), where they end a local variable declaration and
every command between ``BEGIN`` and ``END``. Splitting on them turned one procedure into
five broken fragments, so the scanner below keeps the body whole until the ``END`` that
closes it. This is a single named special case, not a VQL parser: nothing else in the
language nests statements this way.

Comments are the other half of that: stripped everywhere else, passed through inside a
procedure body. Not because the server keeps them — it normalises the body and
``DESC VQL PROCEDURE`` prints it without them — but because the body is the user's text and
this layer does not edit it.
"""

from __future__ import annotations


def split_statements(text: str) -> list[str]:
    """Return the non-empty statements of ``text`` without their trailing ``;``."""
    statements: list[str] = []
    current: list[str] = []
    scanner = _ProcedureScanner()
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "'" or ch == '"':
            end = _skip_quoted(text, i, ch)
            current.append(text[i:end])
            scanner.end_word()
            i = end
        elif ch == "#" or (ch == "-" and nxt == "-"):
            end = _skip_to_end_of_line(text, i)
            if scanner.inside_body():
                current.append(text[i:end])   # a comment of the body is part of the definition
            i = end
        elif ch == "/" and nxt == "*":
            close = text.find("*/", i + 2)
            end = n if close < 0 else close + 2
            if scanner.inside_body():
                current.append(text[i:end])
            i = end
        elif ch == ";":
            if scanner.body_is_open():
                current.append(ch)       # a semicolon of the procedure's own body
            else:
                _flush(statements, current)
                scanner.reset()
            i += 1
        else:
            current.append(ch)
            scanner.feed(ch)
            i += 1
    _flush(statements, current)
    return statements


_BLOCK_ENDINGS = frozenset({"IF", "LOOP", "CASE"})


class _ProcedureScanner:
    """Tells the splitter whether it stands inside the body of a VQL procedure.

    The body opens on the ``PROCEDURE`` of a ``CREATE [OR REPLACE] VQL PROCEDURE`` header
    and closes on the first ``END`` that is not the end of a nested block — ``END IF``,
    ``END LOOP`` and ``END CASE`` close what is inside the body, not the body itself.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._word: list[str] = []
        self._first_word: str | None = None
        self._previous_word: str | None = None
        self._in_procedure = False
        self._end_seen = False

    def feed(self, ch: str) -> None:
        if ch.isalnum() or ch == "_":
            self._word.append(ch)
        else:
            self.end_word()

    def end_word(self) -> None:
        if not self._word:
            return
        word = "".join(self._word).upper()
        self._word.clear()
        if self._in_procedure:
            if self._end_seen:
                self._end_seen = False
                if word not in _BLOCK_ENDINGS:
                    self._in_procedure = False   # the body ended, this word is past it
            elif word == "END":
                self._end_seen = True
        else:
            if self._first_word is None:
                self._first_word = word
            if word == "PROCEDURE" and self._previous_word == "VQL" and self._first_word == "CREATE":
                self._in_procedure = True
        self._previous_word = word

    def inside_body(self) -> bool:
        """Whether the scanner stands inside a body right now; decides nothing about it."""
        self.end_word()
        return self._in_procedure

    def body_is_open(self) -> bool:
        """Called on a ``;``: the pending word ends here, and so may the body."""
        self.end_word()
        if self._in_procedure and self._end_seen:
            self._in_procedure = False           # ``END;`` — the body ends at this semicolon
            self._end_seen = False
        return self._in_procedure


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
