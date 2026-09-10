"""Addressing a code block inside a skill file.

A template lives in the skill text, not in a copy: ``verify`` reads the block the agent
reads. The address is the file, the heading of the section and the block's index inside
that section — ``skills/views/SKILL.md#Derived view``, ``…#Folders[1]`` for the second
block of a section. A broken address fails loudly; a copy would have drifted silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MARK = re.compile(r"^\s*(?:--|#|//)\s*((?:un)?verified:.*)$")
FENCE = re.compile(r"^```(\w*)\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
ADDRESS = re.compile(r"^(?P<path>[^#]+)#(?P<section>[^\[\]]+?)(?:\[(?P<index>\d+)\])?$")


class TemplateError(Exception):
    """A block address does not resolve. Message is user-facing."""


@dataclass(frozen=True)
class TemplateBlock:
    path: Path
    section: str
    index: int
    language: str
    body: str               # block content, mark line included
    first_line: int         # 1-based line of the first content line
    mark_line: int | None   # 1-based line of the mark, None when the block carries none
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
    blocks = _blocks_of_section(lines, section)
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
                          body="\n".join(body_lines), first_line=first_line,
                          mark_line=mark_line, mark=mark)


def _blocks_of_section(lines: list[str], section: str) -> list[tuple[str, int, list[str]]]:
    """Fenced blocks of the section whose heading text equals ``section``."""
    blocks: list[tuple[str, int, list[str]]] = []
    depth: int | None = None
    inside = False
    language, start, body = "", 0, []
    for number, line in enumerate(lines, start=1):
        heading = HEADING.match(line)
        if heading and not inside:
            level, text = len(heading.group(1)), heading.group(2)
            if text == section:      # entering the section: start collecting from scratch
                depth, blocks = level, []
            elif depth is not None and level <= depth:
                depth = None         # a sibling or higher heading closes the section
            continue
        if depth is None:
            continue
        fence = FENCE.match(line)
        if fence and not inside:
            inside, language, start, body = True, fence.group(1), number + 1, []
        elif inside and line.startswith("```"):
            inside = False
            blocks.append((language, start, body))
        elif inside:
            body.append(line)
    return blocks
