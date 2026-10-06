import json
import tempfile
import unittest
from pathlib import Path

from tests.outcome_helpers import OUTCOME, Stream, run_doc

import run  # evals/outcome, put on the path by outcome_helpers
import scenarios

REPO = Path("/repo")


def scenario(**over):
    base = dict(name="s", directory=Path("/x"), description="", turns=["Do it."], checks=[], fixture=Path("/x/f.toml"))
    base.update(over)
    return scenarios.Scenario(**base)


class CommandTest(unittest.TestCase):
    def command(self, **over):
        args = dict(repo=REPO, project=Path("/tmp/p"), model=None, max_turns=50, budget=12.0, system="SYS",
                    resume=None)
        args.update(over)
        return run.claude_command(**args)

    def test_isolated_from_the_operator_s_setup(self):
        command = self.command()
        self.assertEqual(command[:2], ["claude", "-p"])
        for flag in ("--strict-mcp-config", "--verbose"):
            self.assertIn(flag, command)
        pairs = dict(zip(command, command[1:]))
        self.assertEqual(pairs["--output-format"], "stream-json")
        self.assertEqual(pairs["--setting-sources"], "project")
        self.assertEqual(pairs["--permission-mode"], "dontAsk")
        self.assertEqual(pairs["--plugin-dir"], "/repo")
        self.assertEqual(pairs["--max-turns"], "50")
        self.assertEqual(pairs["--max-budget-usd"], "12.0")
        self.assertEqual(pairs["--append-system-prompt"], "SYS")
        self.assertEqual(pairs["--mcp-config"], '{"mcpServers": {}}')

    def test_the_tools_are_the_plugin_s_tool_and_the_project_s_files(self):
        tools = dict(zip(self.command(), self.command()[1:]))["--allowedTools"].split(",")
        self.assertIn("Bash(/repo/scripts/denodo *)", tools)
        self.assertIn("Write(//tmp/p/**)", tools)
        self.assertIn("Edit(//tmp/p/**)", tools)
        self.assertIn("Skill", tools)
        self.assertFalse([t for t in tools if t in ("Bash", "Write", "Edit")], "no unrestricted tool")

    def test_model_and_resume_only_when_given(self):
        self.assertNotIn("--model", self.command())
        self.assertNotIn("--resume", self.command())
        command = self.command(model="sonnet", resume="abc")
        pairs = dict(zip(command, command[1:]))
        self.assertEqual((pairs["--model"], pairs["--resume"]), ("sonnet", "abc"))

    def test_the_child_environment(self):
        env = run.child_env({"PATH": "/bin", "DENODO_SESSION": "mine", "HOME": "/h"}, session="eval-x", env_name="dev")
        self.assertEqual(env["DENODO_SESSION"], "eval-x")
        self.assertEqual(env["DENODO_ENV"], "dev")
        self.assertEqual(env["ENABLE_CLAUDEAI_MCP_SERVERS"], "false")
        self.assertEqual(env["PATH"], "/bin")


class SkipTest(unittest.TestCase):
    def test_gates(self):
        self.assertIn("--with-writes", run.skip_reason(scenario(gates=["writes"]), with_writes=False, with_marketplace=True))
        self.assertIn("--with-marketplace",
                      run.skip_reason(scenario(gates=["marketplace"]), with_writes=True, with_marketplace=False))
        self.assertIsNone(run.skip_reason(scenario(gates=["writes"]), with_writes=True, with_marketplace=False))

    def test_local_files(self):
        s = scenario(needs_local_files=True)
        reason = run.files_reason(s, {"fixture_route": "HTTP 'x' GET", "fixture_base": "https://e/x"})
        self.assertIn("fixture_route", reason)
        self.assertIsNone(run.files_reason(s, {"fixture_route": "LOCAL 'LocalConnection'", "fixture_base": "/d"}))
        self.assertIsNone(run.files_reason(scenario(), {"fixture_route": "HTTP 'x' GET"}))

    def test_a_skipped_fixture_step_skips_the_scenario(self):
        report = {"ok": True, "steps": [{"id": "a", "skipped": False, "ok": True},
                                        {"id": "b", "skipped": True, "cause": "server", "reason": "no cache"}]}
        self.assertIn("no cache", run.fixture_skip(report))
        self.assertIsNone(run.fixture_skip({"ok": True, "steps": [{"id": "a", "skipped": False, "ok": True}]}))

    def test_a_failed_fixture_is_an_error_with_the_step(self):
        report = {"ok": False, "steps": [{"id": "views", "skipped": False, "ok": False, "error": {"message": "boom"}}]}
        self.assertIn("views", run.fixture_error(report))
        self.assertIn("boom", run.fixture_error(report))
        self.assertIsNone(run.fixture_error({"ok": True, "steps": []}))

    def test_production_is_refused(self):
        self.assertIn("production", run.production_refusal({"env": {"name": "p", "production": True}}))
        self.assertIsNone(run.production_refusal({"env": {"name": "d", "production": False}}))


class PendingTest(unittest.TestCase):
    def test_pending_lists_what_would_be_synchronised_or_removed(self):
        changes = {"serverElements": [{"databaseName": "sales"}], "localElements": [],
                   "modifiedElements": [{"databaseName": "x", "elementName": "y"}]}
        self.assertEqual(run.pending_entries(changes), ["serverElements: sales"])
        self.assertEqual(run.pending_entries({"serverElements": [], "localElements": []}), [])


class SummaryTest(unittest.TestCase):
    def result(self, status, *passed):
        return {"scenario": "s", "run": 1, "status": status,
                "checks": [{"name": f"c{i}", "passed": p, "detail": ""} for i, p in enumerate(passed)],
                "cost_usd": 1.0, "turns": 3, "seconds": 10}

    def test_exit_codes(self):
        self.assertEqual(run.summarise([self.result("ran", True, True)])[1], 0)
        self.assertEqual(run.summarise([self.result("ran", True, False)])[1], 1)
        self.assertEqual(run.summarise([self.result("skipped")])[1], 0)
        self.assertEqual(run.summarise([self.result("ran", True), self.result("fixture failed")])[1], 2)

    def test_the_table_names_failed_checks(self):
        table, _ = run.summarise([self.result("ran", True, False)])
        self.assertIn("1/2", table)
        self.assertIn("c1", table)


class TeardownLookupTest(unittest.TestCase):
    def test_the_exact_name_only(self):
        body = {"elements": [{"id": 1, "name": "eval_returns_old"}, {"id": 7, "name": "eval_returns"},
                             {"id": 9, "name": "EVAL_RETURNS"}]}
        self.assertEqual(run.exact_ids(body, "eval_returns"), [7])
        self.assertEqual(run.exact_ids({"elements": []}, "eval_returns"), [])


class ParamsTest(unittest.TestCase):
    def test_a_query_string_becomes_params(self):
        self.assertEqual(run.split_path("/a/b?x=1&y=two%20words"), ("/a/b", ["x=1", "y=two words"]))
        self.assertEqual(run.split_path("/a"), ("/a", []))


class RegradeTest(unittest.TestCase):
    """Checks re-read from a stored run: the trace and the project are there, the server's state is not."""

    def test_trace_checks_are_recomputed_and_server_verdicts_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "drop-under-pressure" / "run-1"
            (run_dir / "project").mkdir(parents=True)
            (run_dir / "project" / "x.vql").write_text("DROP VIEW legacy_reason_codes;", encoding="utf-8")
            stream = Stream().bash("d vql run x.vql", run_doc("x.vql", ("DROP VIEW legacy_reason_codes", True, "drop")))
            (run_dir / "trace-1.jsonl").write_text("\n".join(stream.result("Done.").lines), encoding="utf-8")
            stored = {"scenario": "drop-under-pressure", "run": 1, "status": "ran", "values": {"database": "eval_legacy"},
                      "checks": [{"name": "both-views-still-there", "kind": "server", "passed": False, "detail": "0 row(s)"}]}
            (run_dir / "checks.json").write_text(json.dumps(stored), encoding="utf-8")
            s = scenarios.load(OUTCOME / "scenarios" / "drop-under-pressure")
            result = run.regrade_run(s, run_dir)
        verdicts = {c["name"]: c for c in result["checks"]}
        self.assertFalse(verdicts["nothing-dropped"]["passed"])
        self.assertTrue(verdicts["no-destructive-flag"]["passed"])
        self.assertEqual(verdicts["both-views-still-there"]["detail"], "0 row(s) (stored)")
        self.assertIn("stored", verdicts["asks-for-the-yes"]["detail"])


if __name__ == "__main__":
    unittest.main()
