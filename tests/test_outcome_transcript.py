import json
import tempfile
import unittest
from pathlib import Path

from tests.outcome_helpers import Stream, api_doc, plan_doc, run_doc

import transcript  # evals/outcome, put on the path by outcome_helpers


class ParseTest(unittest.TestCase):
    def test_a_file_run_gives_its_statements_with_the_file_as_source(self):
        stream = Stream().bash("/r/scripts/denodo vql run --env dev model/v.vql",
                               run_doc("/p/model/v.vql", ("CREATE OR REPLACE VIEW v AS SELECT 1 AS x", True, None)))
        t = transcript.parse(stream.lines)
        [s] = transcript.statements(t)
        self.assertEqual((s.command, s.text, s.ok, s.source, s.turn), ("vql run", "CREATE OR REPLACE VIEW v AS SELECT 1 AS x",
                                                                       True, "/p/model/v.vql", 1))

    def test_inline_and_stdin_keep_the_tool_s_source_marker(self):
        stream = (Stream()
                  .bash("d vql run -e 'SELECT 1'", run_doc("<inline>", ("SELECT 1", True, None)))
                  .bash("d vql run -", run_doc("<stdin>", ("DROP VIEW v", True, "drop"))))
        sources = [s.source for s in transcript.statements(transcript.parse(stream.lines))]
        self.assertEqual(sources, ["<inline>", "<stdin>"])

    def test_a_compound_command_gives_both_documents(self):
        stream = Stream().bash("d vql plan a.vql && d vql run a.vql",
                               plan_doc("/p/a.vql", ("CREATE VIEW a AS SELECT 1", False)),
                               run_doc("/p/a.vql", ("CREATE VIEW a AS SELECT 1", True, None)))
        commands = [s.command for s in transcript.statements(transcript.parse(stream.lines))]
        self.assertEqual(commands, ["vql plan", "vql run"])

    def test_vql_desc_is_a_read_statement(self):
        doc = {"ok": True, "command": "vql desc", "statement": "DESC VIEW v", "rows": [["v", "x"]]}
        stream = Stream().bash("d vql desc --type view v", doc)
        [s] = transcript.statements(transcript.parse(stream.lines))
        self.assertEqual((s.command, s.text, s.ok), ("vql desc", "DESC VIEW v", True))

    def test_an_exit_code_line_before_the_document_is_skipped(self):
        stream = Stream().bash("d vql run a.vql", run_doc("/p/a.vql", ("DESC VIEW x", False, None)),
                               prefix="Exit code 1\n")
        [s] = transcript.statements(transcript.parse(stream.lines))
        self.assertFalse(s.ok)

    def test_a_cut_document_marks_the_call(self):
        whole = json.dumps(run_doc("/p/a.vql", ("CREATE VIEW a AS SELECT 1", True, None),
                                   ("DROP VIEW b", True, "drop")), indent=2)
        cut = whole[: whole.index("DROP VIEW b")]
        stream = Stream().call("Bash", {"command": "d vql run a.vql"}, cut + "\n… [output truncated]")
        t = transcript.parse(stream.lines)
        self.assertEqual(t.cut, [0])

    def test_a_persisted_output_is_read_from_its_file(self):
        doc = run_doc("/p/a.vql", ("DROP VIEW b", True, "drop"))
        with tempfile.TemporaryDirectory() as tmp:
            saved = Path(tmp) / "out.txt"
            saved.write_text(json.dumps(doc, indent=2), encoding="utf-8")
            text = f"<persisted-output>\nOutput too large (90KB). Full output saved to: {saved}\n\nPreview (first 2KB):\n{{\n  \"ok\""
            stream = Stream().call("Bash", {"command": "d vql run a.vql"}, text)
            t = transcript.parse(stream.lines)
        self.assertEqual(t.cut, [])
        self.assertEqual([s.text for s in transcript.statements(t)], ["DROP VIEW b"])

    def test_result_list_content_is_joined(self):
        doc = api_doc("GET", "/public/api/tags")
        stream = Stream().call("Bash", {"command": "d api get /public/api/tags"},
                               [{"type": "text", "text": json.dumps(doc)}])
        [call] = transcript.parse(stream.lines).calls
        self.assertEqual(call.docs[0]["path"], "/public/api/tags")

    def test_final_text_cost_turns_and_session_come_from_the_result_event(self):
        stream = Stream().text("thinking aloud").result("Done: the view is cached.", cost=2.5, turns=31, session="abc")
        t = transcript.parse(stream.lines)
        self.assertEqual((t.final_text, t.cost_usd, t.turns, t.session_id),
                         ("Done: the view is cached.", 2.5, 31, "abc"))

    def test_without_a_result_event_the_last_text_is_final(self):
        t = transcript.parse(Stream().text("first").text("last").lines)
        self.assertEqual(t.final_text, "last")

    def test_merge_keeps_turns_and_renumbers_calls(self):
        one = transcript.parse(Stream().bash("d vql run a.vql", run_doc("/p/a.vql", ("SELECT 1", True, None))).lines)
        two = transcript.parse(Stream().bash("d vql run b.vql", run_doc("/p/b.vql", ("SELECT 2", True, None)))
                               .result("ok", cost=1.0).lines, turn=2)
        merged = transcript.merge([one, two])
        self.assertEqual([(c.index, c.turn) for c in merged.calls], [(0, 1), (1, 2)])
        self.assertEqual([s.call for s in transcript.statements(merged)], [0, 1])
        self.assertEqual(merged.final_text, "ok")


class ClassifyTest(unittest.TestCase):
    def test_what_changes_state(self):
        self.assertTrue(transcript.changes_state("CREATE OR REPLACE VIEW v AS SELECT 1", None))
        self.assertTrue(transcript.changes_state("-- comment\n  alter view v cache full", None))
        self.assertTrue(transcript.changes_state("SELECT * FROM v CONTEXT ('cache_preload' = 'true')", "cache"))
        self.assertTrue(transcript.changes_state("SELECT * FROM DROP_REMOTE_TABLE()", "procedure"))
        self.assertFalse(transcript.changes_state("CONNECT DATABASE x", None))
        self.assertFalse(transcript.changes_state("DESC VIEW v", None))
        self.assertFalse(transcript.changes_state("SELECT COUNT(*) FROM v", None))

    def test_what_reads(self):
        self.assertTrue(transcript.is_read("SELECT COUNT(*) FROM v", None))
        self.assertTrue(transcript.is_read("/* x */ DESC VQL VIEW v", None))
        self.assertTrue(transcript.is_read("LIST VIEWS ALL", None))
        self.assertFalse(transcript.is_read("SELECT * FROM v CONTEXT ('cache_preload' = 'true')", "cache"))
        self.assertFalse(transcript.is_read("CREATE VIEW v AS SELECT 1", None))


if __name__ == "__main__":
    unittest.main()
