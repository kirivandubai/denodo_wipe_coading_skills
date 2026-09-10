"""Addressing a code block inside a skill file.

A template lives in the skill text, not in a copy: ``verify`` reads the block the agent
reads. The address is the file, the heading of the section and the block's index inside
that section — ``skills/views/SKILL.md#Derived view``, ``…#Folders[1]`` for the second
block of a section. A broken address fails loudly; a copy would have drifted silently.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

MARK = re.compile(r"^\s*(?:--|#|//)\s*((?:un)?verified:.*)$")
# Group 1 is the opening fence's indentation (a fence nested inside a numbered list, for
# instance, is not at column 0); group 2 is the language tag.
FENCE = re.compile(r"^(\s*)```(\w*)\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
ADDRESS = re.compile(r"^(?P<path>[^#]+)#(?P<section>[^\[\]]+?)(?:\[(?P<index>\d+)\])?$")
MARK_BODY = re.compile(r"^(?:un)?verified:\s*[^(]*\((?P<place>[^,]+),\s*[^)]*\)(?P<note>.*)$")


class TemplateError(Exception):
    """A block address does not resolve. Message is user-facing."""


@dataclass(frozen=True)
class TemplateBlock:
    path: Path
    section: str
    index: int
    language: str
    body: str               # block content, mark line included, dedented
    mark_line: int | None   # 1-based line of the mark in the file, None when the block carries none
    mark: str | None        # "verified: 9.5.1 (стенд, 2026-09-09)" or None


def parse_address(address: str) -> tuple[str, str, int]:
    match = ADDRESS.match(address.strip())
    if not match:
        raise TemplateError(
            f"template address {address!r} is not <file>#<section> or <file>#<section>[<n>]")
    return match["path"], match["section"], int(match["index"] or 0)


def load_block(root: Path, address: str) -> TemplateBlock:
    relative, section, index = parse_address(address)
    path = Path(root) / relative
    if not path.is_file():
        raise TemplateError(f"template file not found: {relative}")
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks = _blocks_of_section(lines, section, relative)
    if not blocks:
        raise TemplateError(f"section {section!r} not found in {relative}")
    if index >= len(blocks):
        raise TemplateError(
            f"section {section!r} in {relative} has {len(blocks)} block(s), asked for [{index}]")
    language, first_line, body_lines = blocks[index]
    mark_line = mark = None
    for offset, line in enumerate(body_lines):
        found = MARK.match(line)
        if found:
            mark_line, mark = first_line + offset, found.group(1).strip()
            break
    return TemplateBlock(path=path, section=section, index=index, language=language,
                          body="\n".join(body_lines), mark_line=mark_line, mark=mark)


def _dedent_line(line: str, width: int) -> str:
    """Strip up to ``width`` leading spaces/tabs from a fenced block's body line.

    A fence nested inside a list item is indented to line up under the list marker, and
    every body line normally repeats that same indentation. Blank or shorter lines are
    common inside a body though, so this only removes whitespace it actually finds instead
    of assuming every line carries the full width.
    """
    cut = 0
    while cut < width and cut < len(line) and line[cut] in (" ", "\t"):
        cut += 1
    return line[cut:]


def _blocks_of_section(lines: list[str], section: str, relative: str) -> list[tuple[str, int, list[str]]]:
    """Fenced blocks of the section whose heading text equals ``section``.

    ``relative`` is only used to name the file in the error raised when ``section``'s
    heading text occurs more than once: an address must resolve to exactly one place, and
    silently returning "whichever occurrence came last" would be a worse failure than
    raising loudly.
    """
    blocks: list[tuple[str, int, list[str]]] = []
    depth: int | None = None
    seen_section = False
    inside = False
    language, start, body, indent_width = "", 0, [], 0
    for number, line in enumerate(lines, start=1):
        heading = HEADING.match(line)
        if heading and not inside:
            level, text = len(heading.group(1)), heading.group(2)
            if text == section:      # entering the section: start collecting from scratch
                if seen_section:
                    raise TemplateError(
                        f"section {section!r} occurs more than once in {relative}, "
                        f"address is ambiguous")
                seen_section = True
                depth, blocks = level, []
            elif depth is not None and level <= depth:
                depth = None         # a sibling or higher heading closes the section
            continue
        if depth is None:
            continue
        fence = FENCE.match(line)
        if fence and not inside:
            indent_width = len(fence.group(1))
            inside, language, start, body = True, fence.group(2), number + 1, []
        elif inside and line.lstrip().startswith("```"):   # closes at any indent
            inside = False
            blocks.append((language, start, [_dedent_line(body_line, indent_width) for body_line in body]))
        elif inside:
            body.append(line)
    return blocks


def format_mark(version: str, day: dt.date) -> str:
    """Format a verification mark string with version and date."""
    return f"verified: {version} (стенд, {day.isoformat()})"


def update_mark(block: TemplateBlock, *, version: str, day: dt.date) -> bool:
    """Rewrite the block's mark in place. False when there is nothing to rewrite."""
    if block.mark_line is None or block.mark is None:
        return False
    lines = block.path.read_text(encoding="utf-8").splitlines(keepends=True)
    old = lines[block.mark_line - 1]
    prefix = old[: len(old) - len(old.lstrip())]
    comment = "#" if old.lstrip().startswith("#") else ("//" if old.lstrip().startswith("//") else "--")
    note = ""
    parsed = MARK_BODY.match(block.mark)
    if parsed:
        note = parsed["note"]
    new = f"{prefix}{comment} {format_mark(version, day)}{note}\n"
    if new == old:
        return False
    lines[block.mark_line - 1] = new
    block.path.write_text("".join(lines), encoding="utf-8")
    return True
