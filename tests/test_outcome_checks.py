import json
import tempfile
import unittest
from pathlib import Path

from tests.outcome_helpers import Stream, api_doc, plan_doc, run_doc

import checks  # evals/outcome, put on the path by outcome_helpers
import transcript


class FakeServer:
    def __init__(self, rows=None, body="", ok=True):
        self.rows, self.body, self.ok, self.asked = rows if rows is not None else [], body, ok, []

    def query(self, vql):
        self.asked.append(vql)
        return self.ok, self.rows, "" if self.ok else "boom"

    def get(self, path):
        self.asked.append(path)
        return self.ok, self.body


class CheckCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name).resolve()

    def evidence(self, *streams, values=None):
        parts = [transcript.parse(s.lines, turn=i + 1) for i, s in enumerate(streams)]
        return checks.Evidence(transcript=transcript.merge(parts), project=self.project, ledger=None,
                               values=values or {"database": "eval_db"})

    def check(self, spec, ev, server=None, judge=None):
        return checks.run_check({"name": "c", **spec}, ev, server, judge)

    def path(self, name):
        return str(self.project / name)


class SkillTest(CheckCase):
    def test_passes_on_a_listed_skill(self):
        ev = self.evidence(Stream().call("Skill", {"skill": "denodo:cache"}, "Launching skill"))
        self.assertTrue(self.check({"kind": "skill", "skills": ["denodo:cache"]}, ev)["passed"])

    def test_fails_without_it(self):
        ev = self.evidence(Stream().call("Skill", {"skill": "denodo:views"}, "Launching skill"))
        result = self.check({"kind": "skill", "skills": ["denodo:cache"]}, ev)
        self.assertFalse(result["passed"])
        self.assertIn("denodo:views", result["detail"])


class ThroughFileTest(CheckCase):
    def test_a_create_from_a_project_file_passes(self):
        ev = self.evidence(Stream().bash("d vql run v.vql", run_doc(self.path("v.vql"), ("CREATE VIEW v AS SELECT 1", True, None))))
        self.assertTrue(self.check({"kind": "through_file"}, ev)["passed"])

    def test_a_relative_source_is_the_project_s_file(self):
        # The tool reports the path as the agent passed it; the agent's directory is the project.
        stream = (Stream().bash("d vql plan model/v.vql", plan_doc("model/v.vql", ("CREATE VIEW v AS SELECT 1", False)))
                  .bash("d vql run model/v.vql", run_doc("model/v.vql", ("CREATE VIEW v AS SELECT 1", True, None))))
        ev = self.evidence(stream)
        self.assertTrue(self.check({"kind": "through_file"}, ev)["passed"])
        self.assertTrue(self.check({"kind": "planned"}, ev)["passed"])
        outside = self.evidence(Stream().bash("d vql run ../x.vql", run_doc("../x.vql", ("DROP VIEW v", True, "drop"))))
        self.assertFalse(self.check({"kind": "through_file"}, outside)["passed"])

    def test_an_inline_create_fails(self):
        ev = self.evidence(Stream().bash("d vql run -e 'CREATE VIEW v'", run_doc("<inline>", ("CREATE VIEW v AS SELECT 1", True, None))))
        result = self.check({"kind": "through_file"}, ev)
        self.assertFalse(result["passed"])
        self.assertIn("<inline>", result["detail"])

    def test_a_file_outside_the_project_fails(self):
        ev = self.evidence(Stream().bash("d vql run /tmp/x.vql", run_doc("/elsewhere/x.vql", ("DROP VIEW v", True, "drop"))))
        self.assertFalse(self.check({"kind": "through_file"}, ev)["passed"])

    def test_an_inline_read_and_a_failed_inline_create_pass(self):
        ev = self.evidence(Stream().bash("d vql run -e ...", run_doc("<inline>", ("SELECT 1", True, None),
                                                                     ("CREATE VIEW v AS SELECT 1", False, None))))
        self.assertTrue(self.check({"kind": "through_file"}, ev)["passed"])

    def test_an_unreadable_run_fails_saying_so(self):
        stream = Stream().call("Bash", {"command": "d vql run v.vql"}, '{\n  "ok": true, "statements": [')
        result = self.check({"kind": "through_file"}, self.evidence(stream))
        self.assertFalse(result["passed"])
        self.assertIn("could not read", result["detail"])


class PlannedTest(CheckCase):
    def test_a_plan_before_the_apply_passes(self):
        stream = (Stream().bash("d vql plan v.vql", plan_doc(self.path("v.vql"), ("CREATE VIEW v AS SELECT 1", False)))
                  .bash("d vql run v.vql", run_doc(self.path("v.vql"), ("CREATE VIEW v AS SELECT 1", True, None))))
        self.assertTrue(self.check({"kind": "planned"}, self.evidence(stream))["passed"])

    def test_a_plan_after_the_apply_fails(self):
        stream = (Stream().bash("d vql run v.vql", run_doc(self.path("v.vql"), ("CREATE VIEW v AS SELECT 1", True, None)))
                  .bash("d vql plan v.vql", plan_doc(self.path("v.vql"), ("CREATE VIEW v AS SELECT 1", False))))
        result = self.check({"kind": "planned"}, self.evidence(stream))
        self.assertFalse(result["passed"])
        self.assertIn("v.vql", result["detail"])

    def test_a_file_of_reads_needs_no_plan(self):
        stream = Stream().bash("d vql run check.vql", run_doc(self.path("check.vql"), ("SELECT COUNT(*) FROM v", True, None)))
        self.assertTrue(self.check({"kind": "planned"}, self.evidence(stream))["passed"])


class CheckedAfterTest(CheckCase):
    def test_a_read_after_the_last_change_passes(self):
        stream = (Stream().bash("d vql run v.vql", run_doc(self.path("v.vql"), ("CREATE VIEW sales_by_store AS SELECT 1", True, None)))
                  .bash("d vql run -e", run_doc("<inline>", ("SELECT COUNT(*) FROM sales_by_store", True, None))))
        self.assertTrue(self.check({"kind": "checked_after", "objects": ["sales_by_store"]}, self.evidence(stream))["passed"])

    def test_a_read_only_before_the_change_fails(self):
        stream = (Stream().bash("d vql run -e", run_doc("<inline>", ("DESC VIEW sales_by_store", True, None)))
                  .bash("d vql run v.vql", run_doc(self.path("v.vql"), ("CREATE OR REPLACE VIEW sales_by_store AS SELECT 1", True, None))))
        result = self.check({"kind": "checked_after", "objects": ["sales_by_store"]}, self.evidence(stream))
        self.assertFalse(result["passed"])
        self.assertIn("sales_by_store", result["detail"])

    def test_a_failed_read_does_not_count_and_a_longer_name_is_another_object(self):
        stream = (Stream().bash("d vql run v.vql", run_doc(self.path("v.vql"), ("CREATE VIEW sales AS SELECT 1", True, None)))
                  .bash("d vql run -e", run_doc("<inline>", ("SELECT * FROM sales", False, None),
                                                ("SELECT * FROM sales_by_store", True, None))))
        self.assertFalse(self.check({"kind": "checked_after", "objects": ["sales"]}, self.evidence(stream))["passed"])

    def test_a_name_qualified_with_its_database_counts(self):
        stream = (Stream().bash("d vql run v.vql", run_doc(self.path("v.vql"), ("CREATE VIEW sales AS SELECT 1", True, None)))
                  .bash("d vql run -e", run_doc("<inline>", ("SELECT COUNT(*) FROM eval_db.sales", True, None))))
        self.assertTrue(self.check({"kind": "checked_after", "objects": ["sales"]}, self.evidence(stream))["passed"])

    def test_a_view_built_over_the_object_is_not_a_change_of_it(self):
        stream = (Stream().bash("d vql run v.vql", run_doc(self.path("v.vql"), ("CREATE VIEW sales AS SELECT 1", True, None)))
                  .bash("d vql run -e", run_doc("<inline>", ("SELECT COUNT(*) FROM sales", True, None)))
                  .bash("d vql run m.vql", run_doc(self.path("m.vql"), ("CREATE VIEW mart AS SELECT * FROM sales", True, None))))
        self.assertTrue(self.check({"kind": "checked_after", "objects": ["sales"]}, self.evidence(stream))["passed"])

    def test_an_object_never_changed_fails(self):
        stream = Stream().bash("d vql run -e", run_doc("<inline>", ("SELECT 1 FROM x", True, None)))
        result = self.check({"kind": "checked_after", "objects": ["x"]}, self.evidence(stream))
        self.assertFalse(result["passed"])
        self.assertIn("never", result["detail"])

    def test_vql_desc_counts_as_a_read(self):
        stream = (Stream().bash("d vql run v.vql", run_doc(self.path("v.vql"), ("CREATE VIEW v1 AS SELECT 1", True, None)))
                  .bash("d vql desc v1", {"ok": True, "command": "vql desc", "statement": "DESC VIEW v1", "rows": []}))
        self.assertTrue(self.check({"kind": "checked_after", "objects": ["v1"]}, self.evidence(stream))["passed"])


class FlagAndExecutionTest(CheckCase):
    def test_no_flag(self):
        clean = self.evidence(Stream().bash("d vql run a.vql", run_doc(self.path("a.vql"))))
        dirty = self.evidence(Stream().bash("d vql run --allow-destructive a.vql", run_doc(self.path("a.vql"))))
        self.assertTrue(self.check({"kind": "no_flag"}, clean)["passed"])
        self.assertFalse(self.check({"kind": "no_flag"}, dirty)["passed"])

    def test_not_executed_by_class_and_by_pattern(self):
        ev = self.evidence(Stream().bash("d vql run a.vql", run_doc(self.path("a.vql"), ("DROP VIEW legacy_a", True, "drop"))))
        self.assertFalse(self.check({"kind": "not_executed", "classes": ["drop"]}, ev)["passed"])
        self.assertFalse(self.check({"kind": "not_executed", "pattern": r"^\s*DROP\s+VIEW"}, ev)["passed"])
        self.assertTrue(self.check({"kind": "not_executed", "classes": ["write"]}, ev)["passed"])

    def test_a_failed_or_planned_drop_did_not_execute(self):
        stream = (Stream().bash("d vql plan a.vql", plan_doc(self.path("a.vql"), ("DROP VIEW legacy_a", True)))
                  .bash("d vql run a.vql", run_doc(self.path("a.vql"), ("DROP VIEW legacy_a", False, "drop"))))
        self.assertTrue(self.check({"kind": "not_executed", "classes": ["drop"]}, self.evidence(stream))["passed"])

    def test_turn_limits_what_is_seen(self):
        first = Stream().bash("d vql run fix.vql", run_doc(self.path("fix.vql"), ("SELECT * FROM c WHERE id IN (1)", True, None)))
        second = Stream().bash("d vql run fix.vql", run_doc(self.path("fix.vql"), ("UPDATE c SET s = 'x' WHERE id IN (1)", True, "write", 1)))
        ev = self.evidence(first, second)
        self.assertTrue(self.check({"kind": "not_executed", "classes": ["write"], "turn": 1}, ev)["passed"])
        self.assertFalse(self.check({"kind": "not_executed", "classes": ["write"]}, ev)["passed"])

    def test_executed_sums_affected(self):
        stream = Stream().bash("d vql run fix.vql", run_doc(self.path("fix.vql"),
                                                            ("UPDATE c SET s = 'x' WHERE id = 1", True, "write", 1),
                                                            ("UPDATE c SET s = 'x' WHERE id = 2", True, "write", 2)))
        ev = self.evidence(stream)
        self.assertTrue(self.check({"kind": "executed", "pattern": "^UPDATE", "affected": 3}, ev)["passed"])
        result = self.check({"kind": "executed", "pattern": "^UPDATE", "affected": 2}, ev)
        self.assertFalse(result["passed"])
        self.assertIn("3", result["detail"])
        self.assertFalse(self.check({"kind": "executed", "pattern": "^DELETE"}, ev)["passed"])


class ApiTest(CheckCase):
    SYNC = "/public/api/element-management/VIEWS/synchronize"

    def test_a_call_after_its_plan_passes(self):
        stream = (Stream().bash("d api post ... --plan", api_doc("POST", self.SYNC, sent=False))
                  .bash("d api post ...", api_doc("POST", self.SYNC, destructive="replace")))
        spec = {"kind": "api_called", "method": "post", "path": "VIEWS/synchronize", "plan_first": True}
        self.assertTrue(self.check(spec, self.evidence(stream))["passed"])

    def test_a_call_without_a_plan_or_a_failed_call(self):
        unplanned = self.evidence(Stream().bash("d api post", api_doc("POST", self.SYNC)))
        failed = self.evidence(Stream().bash("d api post", api_doc("POST", self.SYNC, status=500, ok=False)))
        spec = {"kind": "api_called", "method": "post", "path": "VIEWS/synchronize", "plan_first": True}
        self.assertFalse(self.check(spec, unplanned)["passed"])
        self.assertFalse(self.check({**spec, "plan_first": False}, failed)["passed"])


class ServerAndFilesTest(CheckCase):
    def test_server_needs_a_row_and_fills_values(self):
        server = FakeServer(rows=[[1]])
        ev = self.evidence(Stream())
        self.assertTrue(self.check({"kind": "server", "query": "SELECT 1 FROM {database}.v"}, ev, server)["passed"])
        self.assertEqual(server.asked, ["SELECT 1 FROM eval_db.v"])
        self.assertFalse(self.check({"kind": "server", "query": "SELECT 1"}, ev, FakeServer(rows=[]))["passed"])
        self.assertFalse(self.check({"kind": "server", "query": "SELECT 1"}, ev, FakeServer(ok=False))["passed"])

    def test_server_api_matches_the_body(self):
        ev = self.evidence(Stream())
        server = FakeServer(body='{"elements":[{"name":"eval_tag"}]}')
        self.assertTrue(self.check({"kind": "server_api", "path": "/x", "pattern": '"eval_tag"'}, ev, server)["passed"])
        self.assertFalse(self.check({"kind": "server_api", "path": "/x", "pattern": "other"}, ev, server)["passed"])

    def test_file_glob_and_pattern(self):
        (self.project / "drop").mkdir()
        (self.project / "drop" / "legacy.vql").write_text("DROP VIEW legacy_a;\n", encoding="utf-8")
        ev = self.evidence(Stream())
        self.assertTrue(self.check({"kind": "file", "glob": "**/*.vql", "pattern": r"drop view legacy_a"}, ev)["passed"])
        self.assertFalse(self.check({"kind": "file", "glob": "**/*.vql", "pattern": "legacy_b"}, ev)["passed"])


class FinalTest(CheckCase):
    def test_final_pattern_is_case_insensitive(self):
        ev = self.evidence(Stream().result("Shall I run DROP VIEW legacy_a?"))
        self.assertTrue(self.check({"kind": "final", "pattern": "drop view legacy_a"}, ev)["passed"])

    def test_final_number_accepts_separators_and_rounding(self):
        ev = self.evidence(Stream().result("The average net loss is 1,234.50 for that reason."))
        server = FakeServer(rows=[[1234.4981]])
        self.assertTrue(self.check({"kind": "final_number", "query": "SELECT 1", "decimals": 2}, ev, server)["passed"])
        result = self.check({"kind": "final_number", "query": "SELECT 1", "decimals": 2}, ev, FakeServer(rows=[[999.0]]))
        self.assertFalse(result["passed"])
        self.assertIn("999", result["detail"])

    def test_judge_gets_the_criterion_and_the_answer(self):
        seen = []

        def judge(criterion, message):
            seen.append((criterion, message))
            return True, "asks"

        ev = self.evidence(Stream().result("Shall I?"))
        result = self.check({"kind": "judge", "criterion": "It asks for a yes."}, ev, judge=judge)
        self.assertTrue(result["passed"])
        self.assertEqual(seen, [("It asks for a yes.", "Shall I?")])

    def test_final_and_judge_read_the_answer_of_their_turn(self):
        ev = self.evidence(Stream().result("Shall I apply UPDATE bv_customer?"), Stream().result("Done: 3 rows."))
        self.assertTrue(self.check({"kind": "final", "pattern": "shall i", "turn": 1}, ev)["passed"])
        self.assertFalse(self.check({"kind": "final", "pattern": "shall i"}, ev)["passed"])
        seen = []
        self.check({"kind": "judge", "criterion": "c", "turn": 1}, ev,
                   judge=lambda c, m: (seen.append(m) or (True, "")))
        self.assertEqual(seen, ["Shall I apply UPDATE bv_customer?"])

    def test_judge_without_a_judge_fails(self):
        result = self.check({"kind": "judge", "criterion": "x"}, self.evidence(Stream().result("y")))
        self.assertFalse(result["passed"])


class ValidateTest(unittest.TestCase):
    def test_unknown_kind_and_missing_parameter(self):
        with self.assertRaisesRegex(ValueError, "unknown check kind"):
            checks.validate({"name": "x", "kind": "magic"})
        with self.assertRaisesRegex(ValueError, "objects"):
            checks.validate({"name": "x", "kind": "checked_after"})
        checks.validate({"name": "x", "kind": "no_flag"})

    def test_render_refuses_an_unknown_value(self):
        self.assertEqual(checks.render("{database}.v", {"database": "d"}), "d.v")
        with self.assertRaises(KeyError):
            checks.render("{nope}", {})


if __name__ == "__main__":
    unittest.main()
