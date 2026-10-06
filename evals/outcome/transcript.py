"""A headless Claude Code run, read for the checks of the outcome scenarios.

`claude -p --output-format stream-json --verbose` prints one JSON event per line: the agent's
tool calls in `assistant` events, their results in `user` events, the last answer, the cost and
the session id in the `result` event. The checks need more than the events: what the plugin's
tool did. Every `scripts/denodo` command prints one JSON document — for `vql run` each
statement with its text, `ok`, the tool's `destructive` class, `affected` and the `source` it
came from (the file applied, `<inline>` for `-e`, `<stdin>` for `-`) — so the documents in each
result are decoded here too.

A result can reach the trace cut. When Claude Code saved the whole output to a file and left a
preview, the file is read instead. Otherwise the call is listed in `Transcript.cut`, and a
check that needs a statement it could not read fails saying so.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

sys.path.append(str(Path(__file__).resolve().parents[2] / "scripts"))
from denodo_cli.vql_split import split_statements  # noqa: E402  (standard library only)

# The first keywords of a statement that changes something, besides what the tool itself
# classifies as destructive (a cache load, a state-changing procedure called as a SELECT).
CHANGING = {"CREATE", "ALTER", "DROP", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFRESH",
            "GRANT", "REVOKE", "CHOWN"}
READING = {"SELECT", "DESC", "DESCRIBE", "LIST", "WITH"}

COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
DOCUMENT_START = re.compile(r"(?m)^\{")
SAVED_OUTPUT = re.compile(r"Full output saved to: (\S+)")


@dataclass
class Call:
    index: int
    turn: int
    tool: str
    input: dict
    result: str | None = None
    is_error: bool = False
    docs: list[dict] = field(default_factory=list)
    cut: bool = False

    @property
    def command(self) -> str:
        return str(self.input.get("command", "")) if self.tool == "Bash" else ""


@dataclass
class Statement:
    call: int
    turn: int
    command: str          # "vql run", "vql plan" or "vql desc"
    text: str
    ok: bool | None       # None for a plan: nothing was executed
    destructive: str | None
    affected: int | None
    rows: list | None
    source: str | None
    needs_yes: bool | None = None


@dataclass
class Transcript:
    calls: list[Call] = field(default_factory=list)
    final_text: str = ""
    cost_usd: float | None = None
    turns: int | None = None
    session_id: str | None = None
    # the last answer of each turn, by turn number (merge fills it; parse gives its own turn's)
    finals: dict[int, str] = field(default_factory=dict)

    @property
    def cut(self) -> list[int]:
        return [c.index for c in self.calls if c.cut]


def first_keyword(text: str) -> str:
    stripped = COMMENTS.sub(" ", text).strip()
    match = re.match(r"[A-Za-z_]+", stripped)
    return match.group(0).upper() if match else ""


def changes_state(text: str, destructive: str | None) -> bool:
    return bool(destructive) or first_keyword(text) in CHANGING


def is_read(text: str, destructive: str | None) -> bool:
    return not changes_state(text, destructive) and first_keyword(text) in READING


def json_documents(text: str) -> tuple[list[dict], bool]:
    """Every top-level JSON object printed in ``text`` (a line starting with ``{``), and whether
    one that started could not be decoded — the output was cut."""
    decoder = json.JSONDecoder()
    docs: list[dict] = []
    cut = False
    position = 0
    for match in DOCUMENT_START.finditer(text):
        if match.start() < position:
            continue
        try:
            doc, end = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            cut = True
            continue
        if isinstance(doc, dict):
            docs.append(doc)
        position = end
    return docs, cut


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


def _read_documents(text: str) -> tuple[list[dict], bool]:
    saved = SAVED_OUTPUT.search(text)
    if saved:
        path = Path(saved.group(1))
        if path.is_file():
            return json_documents(path.read_text(encoding="utf-8", errors="replace"))
        return [], True
    return json_documents(text)


def parse(lines: Iterable[str], turn: int = 1) -> Transcript:
    t = Transcript()
    by_id: dict[str, Call] = {}
    last_text = ""
    final = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if kind == "assistant" and isinstance(content, list):
            for part in content:
                if part.get("type") == "tool_use":
                    call = Call(index=len(t.calls), turn=turn, tool=part.get("name", ""), input=part.get("input") or {})
                    t.calls.append(call)
                    by_id[part.get("id", "")] = call
                elif part.get("type") == "text" and part.get("text", "").strip():
                    last_text = part["text"]
        elif kind == "user" and isinstance(content, list):
            for part in content:
                if part.get("type") != "tool_result":
                    continue
                call = by_id.get(part.get("tool_use_id", ""))
                if call is None:
                    continue
                call.result = _result_text(part.get("content"))
                call.is_error = bool(part.get("is_error"))
                if call.tool == "Bash":
                    call.docs, call.cut = _read_documents(call.result)
        elif kind == "result":
            final = event.get("result")
            t.cost_usd = event.get("total_cost_usd")
            t.turns = event.get("num_turns")
            t.session_id = event.get("session_id")
    t.final_text = final if isinstance(final, str) and final.strip() else last_text
    t.finals = {turn: t.final_text}
    return t


def merge(transcripts: list[Transcript]) -> Transcript:
    """The turns of one run as one transcript: calls renumbered in order, each keeping its turn;
    the last answer is the last turn's, the cost the sum."""
    merged = Transcript()
    for part in transcripts:
        for call in part.calls:
            merged.calls.append(Call(index=len(merged.calls), turn=call.turn, tool=call.tool, input=call.input,
                                     result=call.result, is_error=call.is_error, docs=call.docs, cut=call.cut))
        merged.finals.update(part.finals)
        if part.final_text:
            merged.final_text = part.final_text
        if part.cost_usd is not None:
            merged.cost_usd = (merged.cost_usd or 0.0) + part.cost_usd
        if part.turns is not None:
            merged.turns = (merged.turns or 0) + part.turns
        merged.session_id = part.session_id or merged.session_id
    return merged


def _flat(text: str) -> str:
    return " ".join(text.split())


def _inline_texts(command: str) -> list[str]:
    """The statements a `vql run -e … [-e …]` command carried, whole."""
    try:
        words = shlex.split(command)
    except ValueError:
        return []
    texts = []
    for i, word in enumerate(words):
        if word in ("-e", "--execute") and i + 1 < len(words):
            texts.append(words[i + 1])
        elif word.startswith("--execute="):
            texts.append(word.split("=", 1)[1])
    return [part for text in texts for part in split_statements(text)]


def _file_texts(source: str, project: Path | None) -> list[str]:
    if project is None:
        return []
    path = Path(source)
    path = path if path.is_absolute() else project / path
    try:
        return split_statements(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return []


def _whole(head: str, candidates: list[str]) -> str:
    """The tool echoes a statement's first 160 characters, whitespace flattened, ending in "…" when
    cut; the whole text is the candidate it begins."""
    if not head.endswith("…"):
        return head
    prefix = head[:-1]
    for candidate in candidates:
        flat = _flat(candidate)
        if flat.startswith(prefix):
            return flat
    return head


def statements(t: Transcript, project: Path | None = None) -> list[Statement]:
    """Every statement of every `vql run`, `vql plan` and `vql desc` in the transcript, in order. A
    statement the tool cut to its head is given whole when the command (`-e`) or the file it came
    from — relative to ``project``, the agent's directory — still has it."""
    out: list[Statement] = []
    for call in t.calls:
        for doc in call.docs:
            command = doc.get("command")
            if command == "vql desc" and doc.get("statement"):
                out.append(Statement(call=call.index, turn=call.turn, command=command, text=str(doc["statement"]),
                                     ok=bool(doc.get("ok")), destructive=None, affected=None, rows=doc.get("rows"),
                                     source=None))
                continue
            if command not in ("vql run", "vql plan") or not isinstance(doc.get("statements"), list):
                continue
            source = doc.get("source") or ""
            candidates = (_inline_texts(call.command) if source == "<inline>"
                          else [] if source.startswith("<") else _file_texts(source, project))
            for s in doc["statements"]:
                out.append(Statement(
                    call=call.index, turn=call.turn, command=command,
                    text=_whole(str(s.get("statement", "")), candidates),
                    ok=s.get("ok") if command == "vql run" else None, destructive=s.get("destructive"),
                    affected=s.get("affected"), rows=s.get("rows"), source=doc.get("source"),
                    needs_yes=s.get("needs_yes")))
    return out
