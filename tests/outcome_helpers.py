"""Synthetic stream-json events for the tests of the outcome scenarios (evals/outcome)."""

import json
import sys
from pathlib import Path

OUTCOME = Path(__file__).resolve().parents[1] / "evals" / "outcome"
if str(OUTCOME) not in sys.path:
    sys.path.insert(0, str(OUTCOME))


class Stream:
    """Builds the lines of one turn the way `claude -p --output-format stream-json` prints them."""

    def __init__(self):
        self.lines = [json.dumps({"type": "system", "subtype": "init", "session_id": "s-1"})]
        self._next = 0

    def call(self, tool, tool_input, result, *, is_error=False):
        self._next += 1
        tool_id = f"toolu_{self._next}"
        self.lines.append(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": tool_id, "name": tool, "input": tool_input}]}}))
        if result is not None:
            self.lines.append(json.dumps({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": tool_id, "content": result, "is_error": is_error}]}}))
        return self

    def bash(self, command, *docs, prefix="", tail=""):
        text = prefix + "\n\n".join(json.dumps(d, indent=2) for d in docs) + tail
        return self.call("Bash", {"command": command, "description": "x"}, text)

    def text(self, text):
        self.lines.append(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}))
        return self

    def result(self, text, cost=1.25, turns=7, session="s-1"):
        self.lines.append(json.dumps({"type": "result", "subtype": "success", "result": text,
                                      "total_cost_usd": cost, "num_turns": turns, "session_id": session}))
        return self


def run_doc(source, *statements):
    """A `vql run` document; each statement is (text, ok, destructive[, affected[, rows]])."""
    out = []
    for i, s in enumerate(statements):
        text, ok, destructive = s[:3]
        affected = s[3] if len(s) > 3 else None
        rows = s[4] if len(s) > 4 else None
        out.append({"index": i, "statement": text, "destructive": destructive, "ok": ok,
                    "error": None if ok else {"message": "boom"}, "columns": None, "rows": rows,
                    "row_count": None if rows is None else len(rows), "truncated": False, "affected": affected})
    return {"ok": all(s[1] for s in statements), "command": "vql run", "statements": out,
            "executed": len(out), "total": len(out), "source": source}


def plan_doc(source, *statements):
    """A `vql plan` document; each statement is (text, needs_yes)."""
    return {"ok": True, "command": "vql plan", "executed": 0, "source": source,
            "statements": [{"index": i, "statement": t, "needs_yes": y, "destructive": None}
                           for i, (t, y) in enumerate(statements)]}


def api_doc(method, path, *, status=200, sent=True, ok=True, body=None, destructive=None):
    doc = {"ok": ok, "command": "api", "method": method, "path": path, "destructive": destructive}
    if sent:
        doc.update(status=status, body=body)
    else:
        doc.update(sent=False, needs_yes=False)
    return doc
