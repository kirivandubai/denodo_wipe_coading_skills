"""Turn driver exceptions into the message the Denodo server actually produced.

psycopg2 reports a VDP error as two lines — ``ERROR:  <text>`` and
``DETAIL:  java.sql.SQLException: <text>`` (spike T2, section 5). The skills match
errors by substring, so ``message`` carries just the server text; ``raw`` keeps the
whole thing for humans.
"""

from __future__ import annotations

import re

_DETAIL = re.compile(r"DETAIL:\s*(?:java\.sql\.SQLException:\s*)?(.+)")
_ERROR = re.compile(r"^ERROR:\s*(.+)$", re.MULTILINE)


def normalize_error(exc: BaseException) -> dict:
    raw = str(exc)
    message = None
    match = _DETAIL.search(raw)
    if match:
        message = match.group(1)
    else:
        match = _ERROR.search(raw)
        if match:
            message = match.group(1)
    if message is None:
        message = raw
    return {
        "type": type(exc).__name__,
        "message": " ".join(message.split()),
        "raw": " ".join(raw.split()),
    }
