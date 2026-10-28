"""A VQL file's statements, split by a splitter of the layer's own.

denodo_cli splits a file too (``denodo_cli.vql_split``), and its plan has one entry per
statement it found. The rule of scope reads each statement's text beside its entry, and the two
must align: the file is refused when this splitter and denodo_cli's disagree on the count. That
check is only worth something when the splitters are two -- one shared function would agree with
itself whatever it got wrong -- so this one is written apart, on purpose, and a test holds the two
to the same boundaries on a corpus of everything but a procedure.

The one place they differ by design is a VQL procedure's body, whose semicolons denodo_cli keeps
inside one statement: this splitter cuts there, the counts differ, and the file is refused. A
tool server's workspace never creates a procedure.
"""

from __future__ import annotations


def split_vql(text: str) -> list[str]:
    """Statements split on `;` outside quotes and comments, as denodo_cli's own splitter does
    for everything but a VQL procedure's body."""
    statements, current, index = [], [], 0
    while index < len(text):
        char, following = text[index], text[index + 1:index + 2]
        if char in "'\"":
            end = index + 1
            while end < len(text):
                if text[end] == char:
                    if text[end + 1:end + 2] == char:
                        end += 2
                        continue
                    break
                end += 1
            current.append(text[index:end + 1])
            index = end + 1
        elif char == "#" or (char == "-" and following == "-"):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
        elif char == "/" and following == "*":
            end = text.find("*/", index + 2)
            index = len(text) if end < 0 else end + 2
        elif char == ";":
            statements.append("".join(current).strip())
            current = []
            index += 1
        else:
            current.append(char)
            index += 1
    statements.append("".join(current).strip())
    return [statement for statement in statements if statement]
