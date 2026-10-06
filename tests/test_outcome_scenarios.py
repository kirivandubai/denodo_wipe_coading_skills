import tempfile
import unittest
from pathlib import Path

from tests.outcome_helpers import OUTCOME

import scenarios  # evals/outcome, put on the path by outcome_helpers
from denodo_cli.commands.verify import load_chain

MINIMAL = '''
description = "A view, checked."
max_turns = 40
[[turn]]
prompt = "Make view eval_x in {database}."
[[check]]
name = "no-flag"
kind = "no_flag"
'''

FIXTURE = '''
[values]
database = "eval_x"

[cleanup]
vql = ["DROP DATABASE IF EXISTS {database} CASCADE"]

[[step]]
id = "db"
kind = "fixture"
channel = "vql"
vql = "CREATE OR REPLACE DATABASE {database};"
'''


class LoadTest(unittest.TestCase):
    def write(self, scenario=MINIMAL, fixture=FIXTURE):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name) / "x-scenario"
        directory.mkdir()
        (directory / "scenario.toml").write_text(scenario, encoding="utf-8")
        if fixture is not None:
            (directory / "fixture.toml").write_text(fixture, encoding="utf-8")
        return directory

    def test_a_minimal_scenario_with_defaults(self):
        s = scenarios.load(self.write())
        self.assertEqual((s.name, s.max_turns, s.gates, s.needs_local_files), ("x-scenario", 40, [], False))
        self.assertEqual(s.turns, ["Make view eval_x in {database}."])
        self.assertEqual(s.timeout_seconds, scenarios.DEFAULT_TIMEOUT)
        self.assertEqual(s.fixture.name, "fixture.toml")

    def test_an_unknown_gate_is_refused(self):
        with self.assertRaisesRegex(scenarios.ScenarioError, "gate"):
            scenarios.load(self.write(MINIMAL.replace('max_turns = 40', 'max_turns = 40\ngates = ["ai"]')))

    def test_a_scenario_needs_a_turn_and_a_fixture(self):
        with self.assertRaisesRegex(scenarios.ScenarioError, "turn"):
            scenarios.load(self.write(MINIMAL.replace('[[turn]]\nprompt = "Make view eval_x in {database}."\n', '')))
        with self.assertRaisesRegex(scenarios.ScenarioError, "fixture.toml"):
            scenarios.load(self.write(fixture=None))

    def test_a_check_is_validated_and_its_turn_must_exist(self):
        with self.assertRaisesRegex(scenarios.ScenarioError, "unknown check kind"):
            scenarios.load(self.write(MINIMAL.replace('kind = "no_flag"', 'kind = "magic"')))
        with self.assertRaisesRegex(scenarios.ScenarioError, "turn 2"):
            scenarios.load(self.write(MINIMAL.replace('kind = "no_flag"', 'kind = "no_flag"\nturn = 2')))

    def test_teardown_api_entries_need_lookup_name_and_delete(self):
        bad = MINIMAL + '\n[[teardown_api]]\nlookup = "/public/api/tag-management/tags?nameFilter=eval_t"\n'
        with self.assertRaisesRegex(scenarios.ScenarioError, "teardown_api"):
            scenarios.load(self.write(bad))

    def test_placeholders(self):
        self.assertEqual(scenarios.placeholders("{database} and {fixture_base}/x.csv, {"), {"database", "fixture_base"})


class TheScenariosTest(unittest.TestCase):
    """The scenarios in the repository hold together without a server."""

    @classmethod
    def setUpClass(cls):
        cls.all = scenarios.load_all(OUTCOME)

    def test_the_six(self):
        self.assertEqual(sorted(s.name for s in self.all),
                         ["cache-own-view", "dml-preview", "drop-under-pressure", "marketplace-tag",
                          "mart-from-csv", "metric-view"])

    def test_every_fixture_is_a_verify_manifest_on_an_eval_database(self):
        for s in self.all:
            with self.subTest(s.name):
                chain = load_chain(s.fixture)
                self.assertTrue(chain.values["database"].startswith("eval_"), chain.values["database"])
                self.assertTrue(chain.cleanup, "a fixture must say how it is removed")

    def test_every_placeholder_is_filled_by_the_runner_or_the_fixture(self):
        for s in self.all:
            known = {"env"} | load_chain(s.fixture).known_values() | {"database"}
            texts = s.turns + [str(v) for check in s.checks for k, v in check.items() if k in scenarios.RENDERED]
            for text in texts:
                with self.subTest(s.name, text=text[:40]):
                    self.assertLessEqual(scenarios.placeholders(text), known)

    def test_server_wide_names_start_with_eval(self):
        for s in self.all:
            for entry in s.teardown_api:
                self.assertTrue(entry["name"].startswith("eval_"), entry)

    def test_nothing_here_is_a_plugin_eval_case(self):
        names = {p.name for p in OUTCOME.rglob("*")}
        self.assertFalse(names & {"prompt.md", "case.yaml", "graders"}, names & {"prompt.md", "case.yaml", "graders"})


if __name__ == "__main__":
    unittest.main()
