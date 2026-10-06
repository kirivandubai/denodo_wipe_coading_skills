import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from denodo_cli.commands import verify as verify_module
from denodo_cli.commands.verify import ChainError, load_chain, parse_api_calls, render, run_chain
from denodo_cli.profiles import Profile
from denodo_cli.transports.base import VqlResult

MANIFEST = """
[values]
database = "denodo_skills_test"
csv_dir = "/opt/denodo/demos/csv"

[[step]]
id = "database"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Database"
substitute = { sales_analytics = "{database}" }
check = "SELECT db_name FROM GET_DATABASES() WHERE db_name = '{database}'"

[[step]]
id = "fixture-base-views"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
expect = "no rows"

[[step]]
id = "mp-tag"
kind = "template"
channel = "http"
address = "skills/marketplace/SKILL.md#Tag, with an assignment"
marketplace = true
calls = [0, 1]
capture = { tag_id = "id" }
"""


class LoadChainTest(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "chain.toml"
        self.path.write_text(MANIFEST, encoding="utf-8")

    def test_values_and_step_order(self):
        chain = load_chain(self.path)
        self.assertEqual(chain.values["database"], "denodo_skills_test")
        self.assertEqual([s.id for s in chain.steps], ["database", "fixture-base-views", "mp-tag"])

    def test_defaults(self):
        chain = load_chain(self.path)
        first, fixture, http = chain.steps
        self.assertEqual(first.expect, "rows")          # default
        self.assertEqual(fixture.expect, "no rows")
        self.assertFalse(first.marketplace)
        self.assertTrue(http.marketplace)
        self.assertEqual(http.calls, [0, 1])
        self.assertEqual(http.capture, {"tag_id": "id"})
        self.assertEqual(first.substitute, {"sales_analytics": "{database}"})

    def test_template_step_without_address_is_rejected(self):
        self.path.write_text('[[step]]\nid = "x"\nkind = "template"\nchannel = "vql"\n', encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.path)
        self.assertIn("address", str(ctx.exception))

    def test_fixture_step_without_body_is_rejected(self):
        self.path.write_text('[[step]]\nid = "x"\nkind = "fixture"\nchannel = "vql"\n', encoding="utf-8")
        with self.assertRaises(ChainError):
            load_chain(self.path)

    def test_unknown_kind_is_rejected(self):
        self.path.write_text('[[step]]\nid = "x"\nkind = "magic"\nchannel = "vql"\n', encoding="utf-8")
        with self.assertRaises(ChainError):
            load_chain(self.path)

    def test_duplicate_step_id_is_rejected(self):
        self.path.write_text(
            '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "vql"\nvql = "SELECT 1"\n'
            '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "vql"\nvql = "SELECT 2"\n', encoding="utf-8")
        with self.assertRaises(ChainError):
            load_chain(self.path)

    def test_http_step_without_marketplace_is_rejected(self):
        # The executor only implements the vql channel; an http step is guarded behind
        # --with-marketplace. Without marketplace = true, an http step could slip into the
        # default run and be handled as if it were vql.
        self.path.write_text(
            '[[step]]\nid = "sneaky"\nkind = "template"\nchannel = "http"\n'
            'address = "skills/marketplace/SKILL.md#Tag"\n', encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.path)
        self.assertIn("sneaky", str(ctx.exception))

    def test_ai_on_an_http_step_is_rejected(self):
        # ai = true gates a VQL step that calls the server's LLM; an http step has no such
        # call, and the flag on it would read as a guarantee nobody checks.
        self.path.write_text(
            '[[step]]\nid = "odd"\nkind = "template"\nchannel = "http"\nmarketplace = true\nai = true\n'
            'address = "skills/marketplace/SKILL.md#Tag"\n', encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.path)
        self.assertIn("odd", str(ctx.exception))

    def test_writes_on_an_http_step_is_rejected(self):
        # writes = true gates a VQL step that changes rows in a source database; an http
        # step writes nothing there, and the flag on it would claim a gate nothing enforces.
        self.path.write_text(
            '[[step]]\nid = "odd"\nkind = "template"\nchannel = "http"\nmarketplace = true\nwrites = true\n'
            'address = "skills/marketplace/SKILL.md#Tag"\n', encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.path)
        self.assertIn("odd", str(ctx.exception))

    def test_cleanup_writes_must_be_a_list_of_statements(self):
        self.path.write_text(
            '[cleanup]\nwrites = "DROP X"\n[[step]]\nid = "a"\nkind = "fixture"\nchannel = "vql"\nvql = "SELECT 1"\n',
            encoding="utf-8")
        with self.assertRaises(ChainError):
            load_chain(self.path)

    def test_non_string_id_is_rejected(self):
        self.path.write_text(
            '[[step]]\nid = 5\nkind = "fixture"\nchannel = "vql"\nvql = "SELECT 1"\n', encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.path)
        self.assertIn("id", str(ctx.exception))

    def test_calls_entry_non_integer_is_rejected(self):
        self.path.write_text(
            '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "vql"\nvql = "SELECT 1"\ncalls = ["a"]\n',
            encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.path)
        self.assertIn("x", str(ctx.exception))
        self.assertIn("'a'", str(ctx.exception))

    def test_calls_entry_float_is_rejected(self):
        self.path.write_text(
            '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "vql"\nvql = "SELECT 1"\ncalls = [0.9]\n',
            encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.path)
        self.assertIn("x", str(ctx.exception))
        self.assertIn("0.9", str(ctx.exception))

    def test_calls_entry_bool_is_rejected(self):
        # bool is an int subclass in Python; a TOML `true`/`false` must not pass as 0/1.
        self.path.write_text(
            '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "vql"\nvql = "SELECT 1"\ncalls = [true]\n',
            encoding="utf-8")
        with self.assertRaises(ChainError):
            load_chain(self.path)

    def test_template_step_with_non_string_address_is_rejected(self):
        self.path.write_text(
            '[[step]]\nid = "x"\nkind = "template"\nchannel = "vql"\naddress = 5\n', encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.path)
        self.assertIn("address", str(ctx.exception))

    def test_fixture_step_with_non_string_vql_is_rejected(self):
        self.path.write_text(
            '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "vql"\nvql = 5\n', encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.path)
        self.assertIn("vql", str(ctx.exception))

    def test_step_database_is_parsed(self):
        self.path.write_text(
            '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "vql"\nvql = "SELECT 1"\n'
            'database = "{database}"\n', encoding="utf-8")
        chain = load_chain(self.path)
        self.assertEqual(chain.steps[0].database, "{database}")

    def test_step_without_database_defaults_to_none(self):
        chain = load_chain(self.path)
        self.assertIsNone(chain.steps[0].database)

    def test_non_string_database_is_rejected(self):
        self.path.write_text(
            '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "vql"\nvql = "SELECT 1"\ndatabase = 5\n',
            encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.path)
        self.assertIn("x", str(ctx.exception))
        self.assertIn("database", str(ctx.exception))


class RenderTest(unittest.TestCase):
    def test_exact_string_is_replaced_everywhere(self):
        body = "CREATE DATABASE sales_analytics;\nCONNECT DATABASE sales_analytics;"
        out = render(body, {"sales_analytics": "{database}"}, {"database": "denodo_skills_test"})
        self.assertNotIn("sales_analytics", out)
        self.assertEqual(out.count("denodo_skills_test"), 2)

    def test_missing_substitution_fails_loudly(self):
        with self.assertRaises(ChainError) as ctx:
            render("SELECT 1", {"sales_analytics": "{database}"}, {"database": "d"})
        self.assertIn("sales_analytics", str(ctx.exception))

    def test_unknown_value_name_fails_loudly(self):
        with self.assertRaises(ChainError) as ctx:
            render("x sales_analytics", {"sales_analytics": "{nope}"}, {"database": "d"})
        self.assertIn("nope", str(ctx.exception))

    def test_placeholders_in_plain_text_are_filled_too(self):
        out = render("SELECT '{database}'", {}, {"database": "denodo_skills_test"})
        self.assertEqual(out, "SELECT 'denodo_skills_test'")

    def test_a_placeholder_with_no_value_is_left_alone(self):
        out = render("SELECT '{unknown}'", {}, {"database": "d"})
        self.assertEqual(out, "SELECT '{unknown}'")


SKILL_TEXT = """### Database

```sql
-- verified: 9.5.1 (live, 2026-09-01)
CREATE OR REPLACE DATABASE sales_analytics 'x';
```

### Boom

```sql
-- verified: 9.5.1 (live, 2026-09-01)
CONNECT DATABASE sales_analytics;
BOOM;
```
"""


def profile(**over):
    base = dict(name="lab", host="h", port=29996, database="admin", user="u", password="p",
                production=False, transport="vql_psycopg2", marketplace_url=None, marketplace_server_id=None)
    base.update(over)
    return Profile(**base)


class FakeVql:
    instances = []

    def __init__(self, profile, database=None):
        self.database, self.executed, self.closed = database, [], False
        FakeVql.instances.append(self)

    def execute(self, statement):
        self.executed.append(statement)
        if "BOOM" in statement:
            raise RuntimeError("ERROR:  boom\nDETAIL:  java.sql.SQLException: Syntax error near 'BOOM'\n")
        if statement.upper().startswith(("SELECT", "DESC")):
            if "VERSION()" in statement.upper():
                # Mirrors the real server (confirmed on the lab stand): the version
                # number is the last token, wrapped in a product-name prefix.
                rows = [["Denodo Virtual DataPort 9.5.1"]]
            elif "GET_VIEWS" in statement:
                rows = []
            else:
                rows = [["denodo_skills_test"]]
            return VqlResult(statement=statement, columns=["c"], rows=rows)
        return VqlResult(statement=statement, columns=None, rows=None)

    def close(self):
        self.closed = True


class FakeVqlUnknownVersion(FakeVql):
    """Behaves exactly like ``FakeVql`` except for the version probe (``SELECT
    version()``), which fails in a configurable way — set ``mode`` before use.

    Proves ``--update-marks`` refuses to stamp a fabricated version: when the real
    version cannot be determined, ``_server_version`` must return ``None``, not a
    guessed placeholder, or a passing template step would get an unconfirmed version
    written into its mark.
    """
    mode = "raise"  # "raise" | "empty" | "unparsable"

    def execute(self, statement):
        if "VERSION()" in statement.upper():
            if self.mode == "raise":
                raise RuntimeError(
                    "ERROR:  connection reset\nDETAIL:  java.sql.SQLException: reset\n")
            if self.mode == "empty":
                return VqlResult(statement=statement, columns=["c"], rows=[])
            if self.mode == "unparsable":
                return VqlResult(statement=statement, columns=["c"], rows=[["unknown"]])
        return super().execute(statement)


class RunChainTest(unittest.TestCase):
    def setUp(self):
        FakeVql.instances.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "catalog").mkdir(parents=True)
        (self.root / "skills" / "catalog" / "SKILL.md").write_text(SKILL_TEXT, encoding="utf-8")
        self.manifest = self.root / "chain.toml"

    def chain(self, text):
        self.manifest.write_text(text, encoding="utf-8")
        return load_chain(self.manifest)

    def test_template_step_runs_the_block_with_substitutions_applied(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "database"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Database"
substitute = { sales_analytics = "{database}" }
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["command"], "verify")
        self.assertEqual(doc["steps"][0]["id"], "database")
        self.assertEqual(doc["steps"][0]["source"], "skills/catalog/SKILL.md#Database")
        executed = " ".join(FakeVql.instances[0].executed)
        self.assertIn("denodo_skills_test", executed)
        self.assertNotIn("sales_analytics", executed)

    def test_step_with_database_field_connects_to_it_directly(self):
        # A block that does not carry its own CONNECT DATABASE (an unqualified SET
        # IMPLEMENTATION or ENDPOINT, say) still has to land in the test database — via
        # the transport's own database kwarg, not by rewriting the block's text.
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "database"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Database"
substitute = { sales_analytics = "{database}" }
database = "{database}"
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0, doc)
        self.assertEqual(FakeVql.instances[0].database, "denodo_skills_test")

    def test_step_without_database_field_does_not_set_it(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "database"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Database"
substitute = { sales_analytics = "{database}" }
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0, doc)
        self.assertIsNone(FakeVql.instances[0].database)

    def test_check_is_run_against_the_test_database_and_must_return_rows(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "database"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Database"
substitute = { sales_analytics = "{database}" }
check = "SELECT db_name FROM GET_DATABASES() WHERE db_name = '{database}'"
""")
        doc, _ = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertTrue(doc["steps"][0]["check"]["ok"])
        self.assertEqual(doc["steps"][0]["check"]["row_count"], 1)

    def test_expect_no_rows_passes_on_an_empty_result(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "nothing-invalid"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
check = "SELECT name FROM GET_VIEWS() WHERE input_database_name = '{database}'"
expect = "no rows"
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0, doc)
        self.assertTrue(doc["steps"][0]["check"]["ok"])

    def test_a_failing_statement_stops_the_chain_and_marks_the_rest_skipped(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "boom"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Boom"
substitute = { sales_analytics = "{database}" }
[[step]]
id = "after"
kind = "fixture"
channel = "vql"
vql = "SELECT 1 FROM DUAL()"
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 1)
        self.assertFalse(doc["ok"])
        self.assertFalse(doc["steps"][0]["ok"])
        self.assertIn("Syntax error", doc["steps"][0]["error"]["message"])
        self.assertTrue(doc["steps"][1]["skipped"])
        self.assertEqual(doc["summary"], {"verified": 0, "failed": 1, "skipped": 1, "skipped_because": {"failure": 1}, "not_run": 0})

    def test_fixture_steps_do_not_count_as_verified(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "fix"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
""")
        doc, _ = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(doc["summary"]["verified"], 0)
        self.assertEqual(doc["steps"][0]["kind"], "fixture")

    def test_marketplace_steps_are_skipped_unless_asked_for(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "mp"
kind = "fixture"
channel = "vql"
vql = "SELECT 1 FROM DUAL()"
marketplace = true
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0)
        self.assertTrue(doc["steps"][0]["skipped"])
        self.assertEqual(doc["steps"][0]["reason"], "marketplace steps need --with-marketplace")

    def test_ai_steps_are_skipped_unless_asked_for(self):
        # An AI step calls the server's LLM once per row it projects: every run costs money
        # and needs an LLM the server may not have. Like the marketplace tail, opt-in.
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "llm"
kind = "fixture"
channel = "vql"
vql = "SELECT SENTIMENT_AI('fine') FROM DUAL()"
ai = true
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0)
        self.assertTrue(doc["steps"][0]["skipped"])
        self.assertEqual(doc["steps"][0]["reason"],
                         "AI steps call the server's LLM, one paid request per row; they need --with-ai")

    def test_ai_steps_run_with_the_flag(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "llm"
kind = "fixture"
channel = "vql"
vql = "SELECT SENTIMENT_AI('fine') FROM DUAL()"
ai = true
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql, with_ai=True)
        self.assertEqual(code, 0)
        self.assertFalse(doc["steps"][0]["skipped"])
        self.assertTrue(doc["steps"][0]["ok"])

    def test_write_steps_are_skipped_unless_asked_for(self):
        # A write step creates a table in a source database the manifest names and writes
        # rows into it: a server without that data source, or an account that may not create
        # tables there, fails it. Like the AI steps, opt-in.
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "write"
kind = "fixture"
channel = "vql"
vql = "UPDATE t SET a = 1 WHERE b = 2"
writes = true
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0)
        self.assertTrue(doc["steps"][0]["skipped"])
        self.assertEqual(doc["steps"][0]["reason"],
                         "write steps create a table in a source database and change its rows; "
                         "they need --with-writes")

    def test_write_steps_run_with_the_flag(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "write"
kind = "fixture"
channel = "vql"
vql = "UPDATE t SET a = 1 WHERE b = 2"
writes = true
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql, with_writes=True)
        self.assertEqual(code, 0)
        self.assertFalse(doc["steps"][0]["skipped"])
        self.assertTrue(doc["steps"][0]["ok"])

    def test_a_broken_address_is_a_failed_step_not_a_crash(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "gone"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#No Such Section"
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 1)
        self.assertIn("No Such Section", doc["steps"][0]["error"]["message"])


TESTING_SKILL = """# Testing

### The key is unique

```text
# verified: 9.5.1 (live, 2026-09-01)
%NAME iv_household_income_key_is_unique
%EXECUTION[query] {ds:vdp}
SELECT household_sk, COUNT(*) AS row_count FROM iv_household_income
WHERE 'sales_analytics' = 'sales_analytics'
GROUP BY household_sk HAVING COUNT(*) > 1
%RESULTS[data]
household_sk,row_count
```
"""

TOOL_OK = """[EXECUTION:START]
--[TEST:END][OK][/tmp/x/key.denodotest][iv_household_income_key_is_unique][12ms][0] Test run: iv_household_income_key_is_unique. Test executed OK: Obtained and expected results match. Time elapsed: 12ms.
Results:
Tests run: 1, OK: 1
"""

TOOL_FAILED = """[EXECUTION:START]
--[TEST:END][FAILED][/tmp/x/key.denodotest][iv_household_income_key_is_unique][12ms][1] Test run: iv_household_income_key_is_unique. Test FAILED!: Expected results are only a subset of the obtained data set. Obtained 1 rows, but expected 0. Time elapsed: 12ms.
--[TEST:END][FAILED][/tmp/x/key.denodotest][iv_household_income_key_is_unique][12ms][1] Test run: iv_household_income_key_is_unique. Test FAILED!: Expected results are only a subset of the obtained data set. Obtained 1 rows, but expected 0. Time elapsed: 12ms.
Results:
Tests run: 1, OK: 0 (FAILED: 1)
"""


class FakeTestingTool:
    """Stands in for ``bin/denodo-test.sh``: records what it was given, answers a canned output."""

    def __init__(self, returncode=0, output=TOOL_OK):
        self.returncode, self.output, self.calls = returncode, output, []

    def __call__(self, command, cwd, env=None):
        config = Path(command[2][len("file:"):])
        tests = Path(command[3][len("file:"):])
        self.calls.append({
            "command": command, "cwd": cwd,
            "config": config.read_text(encoding="iso-8859-1"),
            "config_mode": config.stat().st_mode & 0o777,
            "tests": {p.name: p.read_text(encoding="utf-8") for p in tests.iterdir()},
            "config_path": config,
        })
        return self.returncode, self.output


class TestingToolStepTest(unittest.TestCase):
    MANIFEST = """
[values]
database = "denodo_skills_test"
[[step]]
id = "testing-key"
kind = "template"
channel = "denodotest"
address = "skills/testing/SKILL.md#The key is unique"
substitute = { sales_analytics = "{database}" }
database = "{database}"
"""

    def setUp(self):
        FakeVql.instances.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "testing").mkdir(parents=True)
        self.skill = self.root / "skills" / "testing" / "SKILL.md"
        self.skill.write_text(TESTING_SKILL, encoding="utf-8")
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text(self.MANIFEST, encoding="utf-8")
        self.tool = Path(tempfile.mkdtemp()) / "denodo-testing-tool"
        (self.tool / "bin").mkdir(parents=True)
        (self.tool / "bin" / "denodo-test.sh").write_text("#!/bin/bash\n", encoding="utf-8")

    def run_it(self, runner=None, **kw):
        return run_chain(profile(jdbc_port=29999), load_chain(self.manifest), root=self.root,
                         vql_factory=FakeVql, testing_runner=runner, **kw)

    def test_testing_tool_steps_are_skipped_unless_a_tool_is_named(self):
        runner = FakeTestingTool()
        doc, code = self.run_it(runner)
        self.assertEqual(code, 0)
        self.assertTrue(doc["steps"][0]["skipped"])
        self.assertIn("--testing-tool", doc["steps"][0]["reason"])
        self.assertEqual(runner.calls, [])

    def test_the_block_runs_as_a_test_file_through_the_tool(self):
        runner = FakeTestingTool()
        doc, code = self.run_it(runner, testing_tool=self.tool)
        self.assertEqual(code, 0, doc)
        step = doc["steps"][0]
        self.assertTrue(step["ok"])
        call = runner.calls[0]
        self.assertEqual(call["command"][:2], ["bash", str(self.tool / "bin" / "denodo-test.sh")])
        self.assertEqual(Path(call["cwd"]), self.tool / "bin")
        (name, text), = call["tests"].items()
        self.assertEqual(name, "testing-key.denodotest")
        self.assertIn("'denodo_skills_test' = 'denodo_skills_test'", text)
        self.assertIn("vdp.jdbcUrl=jdbc:denodo://h:29999/denodo_skills_test", call["config"])
        self.assertIn("vdp.password=p", call["config"])
        self.assertEqual(call["config_mode"], 0o600)
        self.assertEqual(step["statements"], [{"test": "iv_household_income_key_is_unique", "status": "OK",
                                               "message": "Test executed OK: Obtained and expected results "
                                                          "match. Time elapsed: 12ms."}])

    def test_the_configuration_with_the_password_is_gone_after_the_step(self):
        runner = FakeTestingTool()
        self.run_it(runner, testing_tool=self.tool)
        self.assertFalse(runner.calls[0]["config_path"].exists())
        self.assertFalse(runner.calls[0]["config_path"].parent.exists())

    def test_a_failed_test_fails_the_step_with_the_tool_s_reason(self):
        doc, code = self.run_it(FakeTestingTool(returncode=1, output=TOOL_FAILED), testing_tool=self.tool)
        self.assertEqual(code, 1)
        step = doc["steps"][0]
        self.assertFalse(step["ok"])
        self.assertEqual(step["error"]["kind"], "testing-tool")
        self.assertIn("Obtained 1 rows, but expected 0", step["error"]["message"])
        self.assertEqual(len(step["statements"]), 1)

    def test_an_exit_code_of_zero_without_a_passed_test_is_a_failure(self):
        # The tool prints its usage and exits 0 when its arguments are wrong.
        doc, code = self.run_it(FakeTestingTool(returncode=0, output="Required parameters: ..."),
                                testing_tool=self.tool)
        self.assertEqual(code, 1)
        self.assertEqual(doc["steps"][0]["error"]["kind"], "testing-tool")

    def test_a_directory_without_the_launcher_is_a_failed_step(self):
        doc, code = self.run_it(FakeTestingTool(), testing_tool=self.tool / "nowhere")
        self.assertEqual(code, 1)
        self.assertIn("denodo-test.sh", doc["steps"][0]["error"]["message"])

    def test_a_passed_step_gets_the_hash_mark_rewritten(self):
        self.run_it(FakeTestingTool(), testing_tool=self.tool, update_marks=True, today=dt.date(2026, 10, 5))
        self.assertIn("# verified: 9.5.1 (live, 2026-10-05)", self.skill.read_text(encoding="utf-8"))

    def test_the_channel_takes_writes_but_not_ai_or_marketplace(self):
        for flag, ok in (("writes", True), ("ai", False), ("marketplace", False)):
            self.manifest.write_text(self.MANIFEST + f"{flag} = true\n", encoding="utf-8")
            if ok:
                self.assertTrue(load_chain(self.manifest).steps[0].writes)
            else:
                with self.assertRaises(ChainError):
                    load_chain(self.manifest)


class FakeVqlSecondSessionFails:
    """First session (the step's own body) behaves normally; opening a second one fails.

    Models a session dropped between running a step and running its check: the check's
    own ``run_statements`` call never gets far enough to execute a statement, so its
    envelope carries only a top-level ``error`` and no ``statements`` list at all.
    """

    calls = 0

    def __init__(self, profile, database=None):
        type(self).calls += 1
        if type(self).calls == 2:
            raise RuntimeError(
                "ERROR:  could not connect\nDETAIL:  java.sql.SQLException: session dropped\n")
        self.executed = []

    def execute(self, statement):
        self.executed.append(statement)
        return VqlResult(statement=statement, columns=None, rows=None)

    def close(self):
        pass


class CleanupTest(unittest.TestCase):
    def setUp(self):
        FakeVql.instances.clear()
        self.root = Path(tempfile.mkdtemp())
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"
tag_prefix = "verify_"

[cleanup]
vql = [
  "DROP DATABASE IF EXISTS {database} CASCADE",
  "DROP TAG IF EXISTS {tag_prefix}pii",
]

[[step]]
id = "fix"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_cleanup_runs_after_a_successful_chain(self):
        doc, code = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0)
        self.assertTrue(doc["cleanup"]["ran"])
        dropped = " ".join(FakeVql.instances[-1].executed)
        self.assertIn("DROP DATABASE IF EXISTS denodo_skills_test CASCADE", dropped)
        self.assertIn("DROP TAG IF EXISTS verify_pii", dropped)

    def test_cleanup_runs_after_a_failed_chain_too(self):
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            'vql = "CONNECT DATABASE {database};"', 'vql = "BOOM"'), encoding="utf-8")
        doc, code = run_chain(profile(), load_chain(self.manifest), root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 1)
        self.assertTrue(doc["cleanup"]["ran"])

    def test_cleanup_writes_run_first_and_only_with_the_flag(self):
        # The table a write step created lives in a source database, outside the test
        # database: it has to go before DROP DATABASE takes away the base view that names it,
        # and a default run, which created nothing there, must not touch that database at all.
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            "[cleanup]\n", '[cleanup]\nwrites = ["SELECT * FROM DROP_REMOTE_TABLE() WHERE base_view_name = \'t\'"]\n'),
            encoding="utf-8")
        chain = load_chain(self.manifest)
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0)
        self.assertNotIn("DROP_REMOTE_TABLE", " ".join(s["statement"] for s in doc["cleanup"]["statements"]))
        FakeVql.instances.clear()
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql, with_writes=True)
        self.assertEqual(code, 0)
        statements = [s["statement"] for s in doc["cleanup"]["statements"]]
        self.assertIn("DROP_REMOTE_TABLE", statements[0])
        self.assertIn("DROP DATABASE", statements[1])

    def test_keep_skips_cleanup_and_says_so(self):
        doc, _ = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql, keep=True)
        self.assertFalse(doc["cleanup"]["ran"])
        self.assertIn("--keep", doc["cleanup"]["reason"])
        self.assertNotIn("DROP DATABASE", " ".join(FakeVql.instances[-1].executed))

    def test_cleanup_only_runs_no_step_and_cleans_up(self):
        # What a run with --keep left behind is removed by the manifest's cleanup alone: no
        # step runs (the fixture is not rebuilt only to be dropped), every step says why.
        doc, code = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql, cleanup_only=True)
        self.assertEqual(code, 0)
        self.assertTrue(doc["cleanup"]["ran"])
        executed = [s for fake in FakeVql.instances for s in fake.executed]
        self.assertNotIn("CONNECT DATABASE denodo_skills_test", " ".join(executed))
        self.assertIn("DROP DATABASE IF EXISTS denodo_skills_test CASCADE", " ".join(executed))
        self.assertEqual([(s["id"], s["skipped"]) for s in doc["steps"]], [("fix", True)])
        self.assertIn("--cleanup-only", doc["steps"][0]["reason"])
        self.assertEqual(doc["summary"]["skipped_because"], {"cleanup-only": 1})

    def test_cleanup_only_keeps_the_gates(self):
        # The writes statements stay behind --with-writes: a cleanup-only run of a manifest
        # whose write steps never ran must not touch the source database either.
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            "[cleanup]\n", '[cleanup]\nwrites = ["SELECT * FROM DROP_REMOTE_TABLE() WHERE base_view_name = \'t\'"]\n'),
            encoding="utf-8")
        chain = load_chain(self.manifest)
        doc, _ = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql, cleanup_only=True)
        self.assertNotIn("DROP_REMOTE_TABLE", " ".join(s["statement"] for s in doc["cleanup"]["statements"]))
        doc, _ = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql, cleanup_only=True,
                           with_writes=True)
        self.assertIn("DROP_REMOTE_TABLE", doc["cleanup"]["statements"][0]["statement"])

    def test_a_failing_cleanup_statement_is_reported_and_the_rest_still_run(self):
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            '"DROP TAG IF EXISTS {tag_prefix}pii",', '"DROP TAG BOOM", "DROP TAG IF EXISTS x",'),
            encoding="utf-8")
        doc, code = run_chain(profile(), load_chain(self.manifest), root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 1)                       # a cleanup that failed to clean up fails the run
        self.assertTrue(doc["cleanup"]["ran"])
        kinds = [s["ok"] for s in doc["cleanup"]["statements"]]
        self.assertEqual(kinds, [True, False, True])

    def test_cleanup_refuses_on_a_production_profile_without_allow_destructive(self):
        # allow_destructive is not hardcoded True inside _cleanup: a production profile
        # must be able to refuse its own DROPs exactly like any other destructive call.
        # Driven straight at _cleanup, because run_chain no longer lets such a run get as
        # far as cleanup — it refuses the whole run before step 1 (ProductionGateTest).
        report = verify_module._cleanup(
            profile(production=True), self.chain,
            values={"database": "denodo_skills_test", "tag_prefix": "verify_"},
            vql_factory=FakeVql, rest_factory=None, allow_destructive=False, keep=False)
        self.assertTrue(report["ran"])
        self.assertFalse(report["statements"][0]["ok"])
        self.assertEqual(report["statements"][0]["error"]["kind"], "refused")
        self.assertEqual(FakeVql.instances, [])  # refused before a transport was created

    def test_cleanup_proceeds_on_a_production_profile_with_allow_destructive(self):
        doc, code = run_chain(profile(production=True), self.chain, root=self.root, vql_factory=FakeVql,
                              allow_destructive=True)
        self.assertEqual(code, 0, doc)
        self.assertTrue(doc["cleanup"]["ran"])
        self.assertTrue(all(s["ok"] for s in doc["cleanup"]["statements"]))


class CleanupOnUnexpectedExceptionTest(unittest.TestCase):
    """Nothing in today's step loop actually raises past ``_run_step`` — it catches
    ``TemplateError``/``ChainError``, and ``run_statements`` catches broadly around both
    the transport factory and ``execute()``. But that is an accident of what the vql
    channel happens to do today, not a structural guarantee: a later channel (http) could
    add a code path that raises something neither of those catches, and without a
    ``try``/``finally`` around the loop, that exception would skip cleanup entirely and
    leave objects on a shared stand. Simulate that by making ``_run_step`` itself raise.
    """

    def setUp(self):
        FakeVql.instances.clear()
        self.root = Path(tempfile.mkdtemp())
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"

[cleanup]
vql = [
  "DROP DATABASE IF EXISTS {database} CASCADE",
]

[[step]]
id = "fix"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_cleanup_still_runs_and_the_exception_still_surfaces(self):
        with mock.patch.object(verify_module, "_run_step", side_effect=RuntimeError("kaboom")):
            with self.assertRaises(RuntimeError):
                run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql)
        dropped = " ".join(FakeVql.instances[-1].executed)
        self.assertIn("DROP DATABASE IF EXISTS denodo_skills_test CASCADE", dropped)


class CleanupPlaceholderTest(unittest.TestCase):
    def setUp(self):
        FakeVql.instances.clear()
        self.root = Path(tempfile.mkdtemp())
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"

[cleanup]
vql = [
  "DROP DATABASE IF EXISTS {database} CASCADE",
  "DROP TAG IF EXISTS {tag_prefix}pii",
]

[[step]]
id = "fix"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_resolved_placeholders_run_the_chain_normally(self):
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            'database = "denodo_skills_test"', 'database = "denodo_skills_test"\ntag_prefix = "verify_"',
            1), encoding="utf-8")
        doc, code = run_chain(profile(), load_chain(self.manifest), root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0)
        self.assertTrue(doc["cleanup"]["ran"])

    def test_an_unresolved_cleanup_placeholder_fails_before_touching_the_network(self):
        # No tag_prefix supplied: {tag_prefix} in the cleanup section cannot resolve.
        with self.assertRaises(ChainError) as ctx:
            run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql)
        self.assertIn("tag_prefix", str(ctx.exception))
        self.assertIn("DROP TAG IF EXISTS {tag_prefix}pii", str(ctx.exception))
        self.assertEqual(FakeVql.instances, [])  # failed before any session was opened

    def test_keep_skips_the_placeholder_check_too(self):
        # --keep means cleanup never runs, so an unresolved cleanup placeholder must not
        # abort a run that has nothing to do with cleanup — same as before this check
        # existed. No tag_prefix supplied, same as the unresolved case above.
        doc, code = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql, keep=True)
        self.assertEqual(code, 0)
        self.assertFalse(doc["cleanup"]["ran"])
        self.assertIn("--keep", doc["cleanup"]["reason"])


class UpdateMarksTest(unittest.TestCase):
    def setUp(self):
        FakeVql.instances.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "catalog").mkdir(parents=True)
        self.skill = self.root / "skills" / "catalog" / "SKILL.md"
        self.skill.write_text(SKILL_TEXT, encoding="utf-8")
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"
[[step]]
id = "database"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Database"
substitute = { sales_analytics = "{database}" }
[[step]]
id = "fix"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_marks_are_untouched_without_the_flag(self):
        run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql)
        self.assertIn("2026-09-01", self.skill.read_text(encoding="utf-8"))

    def test_a_passed_template_step_gets_todays_mark(self):
        doc, _ = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql,
                           update_marks=True, today=dt.date(2026, 9, 10))
        self.assertIn("-- verified: 9.5.1 (live, 2026-09-10)", self.skill.read_text(encoding="utf-8"))
        self.assertTrue(doc["steps"][0]["mark"]["updated"])

    def test_a_fixture_step_has_no_mark_in_the_report(self):
        doc, _ = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql,
                           update_marks=True, today=dt.date(2026, 9, 10))
        self.assertIsNone(doc["steps"][1]["mark"])

    def test_a_failed_step_keeps_its_old_mark(self):
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            "#Database", "#Boom"), encoding="utf-8")
        run_chain(profile(), load_chain(self.manifest), root=self.root, vql_factory=FakeVql,
                  update_marks=True, today=dt.date(2026, 9, 10))
        self.assertIn("2026-09-01", self.skill.read_text(encoding="utf-8"))
        self.assertNotIn("2026-09-10", self.skill.read_text(encoding="utf-8"))

    def test_a_step_whose_check_fails_keeps_its_old_mark(self):
        # The realistic failure mode, unlike test_a_failed_step_keeps_its_old_mark above:
        # every statement in the step's own body succeeds (CREATE DATABASE runs fine),
        # but the check meant to confirm it does not hold. expect="no rows" here
        # deliberately mismatches FakeVql's (non-empty) response, so the check fails
        # without any statement ever raising — report["ok"] only goes False inside the
        # `if step.check:` branch, which is exactly the branch the mark-writing tail has
        # to still reach after the _run_step restructuring.
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"
[[step]]
id = "database"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Database"
substitute = { sales_analytics = "{database}" }
check = "SELECT db_name FROM GET_DATABASES() WHERE db_name = '{database}'"
expect = "no rows"
""", encoding="utf-8")
        doc, code = run_chain(profile(), load_chain(self.manifest), root=self.root, vql_factory=FakeVql,
                              update_marks=True, today=dt.date(2026, 9, 10))
        self.assertEqual(code, 1)
        self.assertFalse(doc["steps"][0]["ok"])
        self.assertIsNone(doc["steps"][0]["mark"])
        self.assertIn("2026-09-01", self.skill.read_text(encoding="utf-8"))
        self.assertNotIn("2026-09-10", self.skill.read_text(encoding="utf-8"))

    def test_a_raising_version_query_writes_no_marks(self):
        FakeVqlUnknownVersion.mode = "raise"
        doc, code = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVqlUnknownVersion,
                              update_marks=True, today=dt.date(2026, 9, 10))
        self.assertEqual(code, 0)
        self.assertTrue(doc["ok"])  # an unknown version must not fail the run
        self.assertEqual(doc["steps"][0]["mark"], {"updated": False, "reason": "server version unknown"})
        self.assertIn("2026-09-01", self.skill.read_text(encoding="utf-8"))
        self.assertNotIn("2026-09-10", self.skill.read_text(encoding="utf-8"))

    def test_an_empty_version_result_writes_no_marks(self):
        FakeVqlUnknownVersion.mode = "empty"
        doc, code = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVqlUnknownVersion,
                              update_marks=True, today=dt.date(2026, 9, 10))
        self.assertEqual(code, 0)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["steps"][0]["mark"], {"updated": False, "reason": "server version unknown"})
        self.assertIn("2026-09-01", self.skill.read_text(encoding="utf-8"))
        self.assertNotIn("2026-09-10", self.skill.read_text(encoding="utf-8"))

    def test_an_unparsable_version_writes_no_marks(self):
        FakeVqlUnknownVersion.mode = "unparsable"
        doc, code = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVqlUnknownVersion,
                              update_marks=True, today=dt.date(2026, 9, 10))
        self.assertEqual(code, 0)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["steps"][0]["mark"], {"updated": False, "reason": "server version unknown"})
        self.assertIn("2026-09-01", self.skill.read_text(encoding="utf-8"))
        self.assertNotIn("2026-09-10", self.skill.read_text(encoding="utf-8"))


class RunCheckConnectionErrorTest(unittest.TestCase):
    def setUp(self):
        FakeVqlSecondSessionFails.calls = 0
        self.root = Path(tempfile.mkdtemp())
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"
[[step]]
id = "fix"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
check = "SELECT 1 FROM DUAL()"
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_a_connection_failure_in_the_check_is_reported_not_masked_as_a_mismatch(self):
        doc, code = run_chain(profile(), self.chain, root=self.root,
                              vql_factory=FakeVqlSecondSessionFails)
        self.assertEqual(code, 1)
        self.assertFalse(doc["steps"][0]["check"]["ok"])
        self.assertIn("session dropped", doc["steps"][0]["check"]["error"]["message"])
        self.assertIn("session dropped", doc["steps"][0]["error"]["message"])
        self.assertNotIn("check expected", doc["steps"][0]["error"]["message"])


BASH_BLOCK = """# verified: 9.5.1 (live, 2026-09-10)

# 1. does it exist?
api get --env lab /public/api/tag-management/tags --param serverId=306 \\
    --param offset=0 --param limit=50 --param nameFilter=pii
# → {"count":1}

# 2a. missing → create it
api post --env lab /public/api/tags --param serverId=306 \\
    --json '{"name":"pii","description":"Personal data","descriptionType":"TEXT"}'
"""


class ParseApiCallsTest(unittest.TestCase):
    def test_calls_are_found_with_method_path_params_and_body(self):
        calls = parse_api_calls(BASH_BLOCK)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["method"], "GET")
        self.assertEqual(calls[0]["path"], "/public/api/tag-management/tags")
        self.assertEqual(calls[0]["params"]["nameFilter"], "pii")
        self.assertIsNone(calls[0]["json"])
        self.assertEqual(calls[1]["method"], "POST")
        self.assertEqual(calls[1]["json"]["name"], "pii")

    def test_env_flag_is_dropped(self):
        self.assertNotIn("env", parse_api_calls(BASH_BLOCK)[0]["params"])

    def test_comment_lines_are_not_calls(self):
        self.assertTrue(all(c["path"].startswith("/") for c in parse_api_calls(BASH_BLOCK)))


class HttpStepTest(unittest.TestCase):
    class FakeRest:
        calls = []

        def __init__(self, profile, server="marketplace"):
            self.profile = profile

        def call(self, method, path, *, json_body=None, params=None, multipart=None, timeout=None):
            from denodo_cli.transports.base import HttpResult
            HttpStepTest.FakeRest.calls.append((method, path, params, json_body))
            if method == "POST" and path == "/public/api/tags":
                return HttpResult(status=200, body={"id": 4242, "name": "verify_pii"})
            return HttpResult(status=200, body={"count": 0, "elements": []})

    def setUp(self):
        FakeVql.instances.clear()
        HttpStepTest.FakeRest.calls.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "marketplace").mkdir(parents=True)
        (self.root / "skills" / "marketplace" / "SKILL.md").write_text(
            "### Tag\n\n```bash\n" + BASH_BLOCK + "```\n", encoding="utf-8")
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"
server_id = "306"
[[step]]
id = "mp-tag"
kind = "template"
channel = "http"
address = "skills/marketplace/SKILL.md#Tag"
marketplace = true
calls = [0, 1]
capture = { tag_id = "id" }
substitute = { "\\"pii\\"" = "\\"verify_pii\\"" }
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_marketplace_step_runs_only_the_listed_calls_and_captures(self):
        doc, code = run_chain(profile(marketplace_url="http://x/y"), self.chain, root=self.root,
                              vql_factory=FakeVql, rest_factory=HttpStepTest.FakeRest,
                              with_marketplace=True)
        self.assertEqual(code, 0, doc)
        self.assertEqual(len(HttpStepTest.FakeRest.calls), 2)
        self.assertEqual(doc["values"]["tag_id"], "4242")

    def test_a_non_2xx_answer_fails_the_step(self):
        class Failing(HttpStepTest.FakeRest):
            def call(self, method, path, **kw):
                from denodo_cli.transports.base import HttpResult
                return HttpResult(status=409, body=None)

        doc, code = run_chain(profile(marketplace_url="http://x/y"), self.chain, root=self.root,
                              vql_factory=FakeVql, rest_factory=Failing, with_marketplace=True)
        self.assertEqual(code, 1)
        self.assertFalse(doc["steps"][0]["ok"])
        self.assertEqual(doc["steps"][0]["error"]["status"], 409)

    def test_a_409_carries_a_hint_about_the_leftover_it_means(self):
        # The marketplace answers a duplicate name with 409 and an empty body (skills/
        # marketplace/SKILL.md, "common mistakes"), so the report alone used to say only
        # "409, body: null" — true and useless. The leftover is almost always what a
        # previous --keep run left in the shared catalog, and the way out is two DELETEs
        # the operator has to be told about.
        class Duplicate(HttpStepTest.FakeRest):
            def call(self, method, path, **kw):
                from denodo_cli.transports.base import HttpResult
                return HttpResult(status=409, body=None)

        doc, code = run_chain(profile(marketplace_url="http://x/y"), self.chain, root=self.root,
                              vql_factory=FakeVql, rest_factory=Duplicate, with_marketplace=True)
        self.assertEqual(code, 1)
        hint = doc["steps"][0]["error"].get("hint")
        self.assertIsNotNone(hint, doc["steps"][0]["error"])
        self.assertIn("--keep", hint)
        self.assertIn("/public/api/tags/", hint)

    def test_another_status_carries_no_hint(self):
        # The hint is knowledge about one status, not decoration on every failure: a 400
        # (a body the server rejected) has nothing to do with a leftover, and claiming it
        # does would send the operator hunting for an object that is not there.
        class BadRequest(HttpStepTest.FakeRest):
            def call(self, method, path, **kw):
                from denodo_cli.transports.base import HttpResult
                return HttpResult(status=400, body={"type": "VALIDATE_FIELD"})

        doc, code = run_chain(profile(marketplace_url="http://x/y"), self.chain, root=self.root,
                              vql_factory=FakeVql, rest_factory=BadRequest, with_marketplace=True)
        self.assertEqual(code, 1)
        self.assertEqual(doc["steps"][0]["error"]["status"], 400)
        self.assertNotIn("hint", doc["steps"][0]["error"])

    def test_a_capture_field_missing_from_the_response_fails_the_step(self):
        # A response shaped differently than the template expects must not leave the step
        # silently uncaptured: that is exactly how the id-less object it just created stops
        # being trackable by [cleanup] http (T9 fix round 1, finding 2).
        class NoId(HttpStepTest.FakeRest):
            def call(self, method, path, *, json_body=None, params=None, multipart=None, timeout=None):
                from denodo_cli.transports.base import HttpResult
                HttpStepTest.FakeRest.calls.append((method, path, params, json_body))
                if method == "POST" and path == "/public/api/tags":
                    return HttpResult(status=200, body={"name": "verify_pii"})  # no "id"
                return HttpResult(status=200, body={"count": 0, "elements": []})

        doc, code = run_chain(profile(marketplace_url="http://x/y"), self.chain, root=self.root,
                              vql_factory=FakeVql, rest_factory=NoId, with_marketplace=True)
        self.assertEqual(code, 1)
        self.assertFalse(doc["steps"][0]["ok"])
        self.assertEqual(doc["steps"][0]["error"]["kind"], "capture")
        self.assertIn("mp-tag", doc["steps"][0]["error"]["message"])
        self.assertIn("id", doc["steps"][0]["error"]["message"])
        self.assertNotIn("tag_id", doc["values"])

    def test_a_captured_field_is_read_correctly_when_present(self):
        # The positive direction, alongside the missing-field test above: an ordinary
        # response with the declared field captures exactly as before.
        doc, code = run_chain(profile(marketplace_url="http://x/y"), self.chain, root=self.root,
                              vql_factory=FakeVql, rest_factory=HttpStepTest.FakeRest,
                              with_marketplace=True)
        self.assertEqual(code, 0, doc)
        self.assertEqual(doc["values"]["tag_id"], "4242")


class ExpectBodyTest(unittest.TestCase):
    """``expect_body`` asserts on the last response instead of only recording it.

    ``capture`` remembers a field for later steps and never judges it. A template whose whole
    point is that a field survives a change — the marketplace rename block: the element keeps
    its id when the pair is matched — needs the run to compare, or a run where the server
    ignored the pair and handed out a new id would still report the step green.
    """

    def setUp(self):
        FakeVql.instances.clear()
        HttpStepTest.FakeRest.calls.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "marketplace").mkdir(parents=True)
        (self.root / "skills" / "marketplace" / "SKILL.md").write_text(
            "### Tag\n\n```bash\n" + BASH_BLOCK + "```\n", encoding="utf-8")
        self.manifest = self.root / "chain.toml"

    def _run(self, expect_body: str, values: str = ""):
        self.manifest.write_text(f"""
[values]
database = "denodo_skills_test"
{values}
[[step]]
id = "mp-tag"
kind = "template"
channel = "http"
address = "skills/marketplace/SKILL.md#Tag"
marketplace = true
calls = [0, 1]
expect_body = {expect_body}
""", encoding="utf-8")
        return run_chain(profile(marketplace_url="http://x/y"), load_chain(self.manifest),
                         root=self.root, vql_factory=FakeVql,
                         rest_factory=HttpStepTest.FakeRest, with_marketplace=True)

    def test_a_matching_field_passes(self):
        doc, code = self._run('{ id = "4242" }')
        self.assertEqual(code, 0, doc)
        self.assertTrue(doc["steps"][0]["ok"])

    def test_the_expected_value_is_rendered_from_values(self):
        # The rename chain compares against an id an earlier step captured, so the expected
        # value is a placeholder, not a literal.
        doc, code = self._run('{ id = "{earlier_id}" }', values='earlier_id = "4242"')
        self.assertEqual(code, 0, doc)

    def test_a_different_value_fails_the_step_and_says_both(self):
        doc, code = self._run('{ id = "{earlier_id}" }', values='earlier_id = "7446"')
        self.assertEqual(code, 1)
        error = doc["steps"][0]["error"]
        self.assertEqual(error["kind"], "expect_body")
        self.assertIn("7446", error["message"])
        self.assertIn("4242", error["message"])
        self.assertIn("mp-tag", error["message"])

    def test_a_missing_field_fails_the_step(self):
        doc, code = self._run('{ nope = "x" }')
        self.assertEqual(code, 1)
        self.assertEqual(doc["steps"][0]["error"]["kind"], "expect_body")
        self.assertIn("nope", doc["steps"][0]["error"]["message"])

    def test_it_is_rejected_on_a_vql_step(self):
        self.manifest.write_text("""
[[step]]
id = "x"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE d;"
expect_body = { id = "1" }
""", encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.manifest)
        self.assertIn("expect_body", str(ctx.exception))

    def test_it_must_be_a_table(self):
        self.manifest.write_text("""
[[step]]
id = "x"
kind = "template"
channel = "http"
address = "skills/marketplace/SKILL.md#Tag"
marketplace = true
expect_body = "id"
""", encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.manifest)
        self.assertIn("expect_body", str(ctx.exception))


DESTRUCTIVE_BASH_BLOCK = """# verified: 9.5.1 (live, 2026-09-10)
api delete --env lab /public/api/tags/999 --param serverId=306
"""


class HttpDestructiveGateTest(unittest.TestCase):
    """``_run_http`` used to hardcode ``allow_destructive=True`` — fine for the tag/category
    steps (never destructive: neither ``POST /public/api/tags`` nor a bare category create
    matches ``safety.classify_http``'s destructive rules), wrong for ``marketplace-sync``'s
    ``POST .../synchronize`` calls, which do (T9 fix round 1, finding 1). A plain ``DELETE``
    is the simplest destructive call to drive this through an http step end to end.
    """

    class FakeRest:
        calls = []

        def __init__(self, profile, server="marketplace"):
            self.profile = profile

        def call(self, method, path, *, json_body=None, params=None, multipart=None, timeout=None):
            from denodo_cli.transports.base import HttpResult
            HttpDestructiveGateTest.FakeRest.calls.append((method, path))
            return HttpResult(status=200, body=None)

    def setUp(self):
        FakeVql.instances.clear()
        HttpDestructiveGateTest.FakeRest.calls.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "marketplace").mkdir(parents=True)
        (self.root / "skills" / "marketplace" / "SKILL.md").write_text(
            "### Untag\n\n```bash\n" + DESTRUCTIVE_BASH_BLOCK + "```\n", encoding="utf-8")
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"
[[step]]
id = "mp-untag"
kind = "template"
channel = "http"
address = "skills/marketplace/SKILL.md#Untag"
marketplace = true
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_refuses_on_a_production_profile_without_allow_destructive(self):
        # Driven straight at the step: run_chain refuses a production run without the flag
        # before step 1 (ProductionGateTest), so this is the only way left to prove
        # _run_http still forwards allow_destructive instead of hardcoding it True.
        report = verify_module._run_step(
            profile(marketplace_url="http://x/y", production=True), self.chain.steps[0],
            values=dict(self.chain.values), root=self.root, vql_factory=FakeVql,
            rest_factory=HttpDestructiveGateTest.FakeRest, allow_destructive=False)
        self.assertFalse(report["ok"])
        self.assertEqual(report["error"]["kind"], "refused")
        self.assertEqual(HttpDestructiveGateTest.FakeRest.calls, [])  # nothing was sent

    def test_proceeds_on_a_production_profile_with_allow_destructive(self):
        doc, code = run_chain(profile(marketplace_url="http://x/y", production=True), self.chain,
                              root=self.root, vql_factory=FakeVql,
                              rest_factory=HttpDestructiveGateTest.FakeRest, with_marketplace=True,
                              allow_destructive=True)
        self.assertEqual(code, 0, doc)
        self.assertTrue(doc["steps"][0]["ok"])
        self.assertEqual(len(HttpDestructiveGateTest.FakeRest.calls), 1)

    def test_a_non_production_profile_needs_no_flag(self):
        doc, code = run_chain(profile(marketplace_url="http://x/y", production=False), self.chain,
                              root=self.root, vql_factory=FakeVql,
                              rest_factory=HttpDestructiveGateTest.FakeRest, with_marketplace=True)
        self.assertEqual(code, 0, doc)
        self.assertEqual(len(HttpDestructiveGateTest.FakeRest.calls), 1)


class CaptureFailurePartialCleanupTest(unittest.TestCase):
    """A step whose capture fails still leaves an earlier step's capture in ``values``, and
    cleanup must still remove exactly what was captured — the scenario the live stand hit
    for real in the original task-9 run (a tag left behind after a --keep run, removed by
    hand). This drives it through two http steps instead."""

    class FakeRest:
        calls = []

        def __init__(self, profile, server="marketplace"):
            self.profile = profile

        def call(self, method, path, *, json_body=None, params=None, multipart=None, timeout=None):
            from denodo_cli.transports.base import HttpResult
            CaptureFailurePartialCleanupTest.FakeRest.calls.append((method, path))
            if method == "POST" and path == "/public/api/tags":
                return HttpResult(status=200, body={"id": 4242, "name": "verify_pii"})
            if method == "POST" and path == "/public/api/category-management/categories":
                return HttpResult(status=200, body={"name": "verify_Consumer marts"})  # no "id"
            if method == "DELETE":
                return HttpResult(status=200, body=None)
            return HttpResult(status=200, body={"count": 0, "elements": []})

    def setUp(self):
        FakeVql.instances.clear()
        CaptureFailurePartialCleanupTest.FakeRest.calls.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "marketplace").mkdir(parents=True)
        (self.root / "skills" / "marketplace" / "SKILL.md").write_text(
            "### Tag\n\n```bash\n" + BASH_BLOCK + "```\n\n"
            "### Category\n\n```bash\n"
            "api post --env lab /public/api/category-management/categories --param serverId=306 \\\n"
            "    --json '{\"name\":\"Consumer marts\",\"description\":\"x\",\"descriptionType\":\"TEXT\"}'\n"
            "```\n", encoding="utf-8")
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"
server_id = "306"

[cleanup]
http = [
  { method = "delete", path = "/public/api/tags/{tag_id}", params = { serverId = "{server_id}" } },
  { method = "delete", path = "/public/api/category-management/categories/{category_id}", params = { serverId = "{server_id}" } },
]

[[step]]
id = "mp-tag"
kind = "template"
channel = "http"
address = "skills/marketplace/SKILL.md#Tag"
marketplace = true
calls = [0, 1]
capture = { tag_id = "id" }
substitute = { "\\"pii\\"" = "\\"verify_pii\\"" }

[[step]]
id = "mp-category"
kind = "template"
channel = "http"
address = "skills/marketplace/SKILL.md#Category"
marketplace = true
calls = [0]
capture = { category_id = "id" }
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_the_earlier_captured_id_is_cleaned_up_even_though_the_later_step_fails(self):
        doc, code = run_chain(profile(marketplace_url="http://x/y"), self.chain, root=self.root,
                              vql_factory=FakeVql, rest_factory=CaptureFailurePartialCleanupTest.FakeRest,
                              with_marketplace=True)
        self.assertEqual(code, 1)
        self.assertTrue(doc["steps"][0]["ok"])                     # mp-tag captured fine
        self.assertFalse(doc["steps"][1]["ok"])                    # mp-category: capture failed
        self.assertEqual(doc["steps"][1]["error"]["kind"], "capture")
        self.assertEqual(doc["values"]["tag_id"], "4242")
        self.assertNotIn("category_id", doc["values"])

        http_cleanup = {h["path"]: h for h in doc["cleanup"]["http"]}
        tag_cleanup = http_cleanup["/public/api/tags/4242"]
        self.assertFalse(tag_cleanup["skipped"])
        self.assertTrue(tag_cleanup["ok"])
        category_cleanup = http_cleanup["/public/api/category-management/categories/{category_id}"]
        self.assertTrue(category_cleanup["skipped"])


class ProductionGateTest(unittest.TestCase):
    """A production profile refuses the whole run, before step 1 — not only at cleanup.

    ``CREATE OR REPLACE …`` is not destructive by ``safety.classify_vql``, so a gate that
    only fires on the cleanup batch would let every step run first: the test database, its
    views and two *server-level* tags would be created on a production server, and only the
    ``DROP``s meant to remove them again would be refused. That is the one outcome this
    command exists to prevent, so the refusal has to come before anything is created.
    """

    def setUp(self):
        FakeVql.instances.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "catalog").mkdir(parents=True)
        (self.root / "skills" / "catalog" / "SKILL.md").write_text(SKILL_TEXT, encoding="utf-8")
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"

[cleanup]
vql = ["DROP DATABASE IF EXISTS {database} CASCADE"]

[[step]]
id = "database"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Database"
substitute = { sales_analytics = "{database}" }
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_the_whole_run_is_refused_before_any_step(self):
        doc, code = run_chain(profile(production=True), self.chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 2)                       # same exit code as any refused destructive call
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["error"]["kind"], "refused")
        self.assertIn("--allow-destructive", doc["error"]["message"])
        self.assertEqual(doc["steps"], [])
        self.assertFalse(doc["cleanup"]["ran"])
        self.assertEqual(FakeVql.instances, [])         # nothing was created, so nothing leaked

    def test_keep_does_not_bypass_the_gate(self):
        # --keep only turns cleanup off; the steps would still create objects.
        doc, code = run_chain(profile(production=True), self.chain, root=self.root, vql_factory=FakeVql,
                              keep=True)
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "refused")
        self.assertEqual(FakeVql.instances, [])

    def test_update_marks_does_not_probe_the_server_either(self):
        # The version probe is a round trip; a refused run must not make it.
        run_chain(profile(production=True), self.chain, root=self.root, vql_factory=FakeVql,
                  update_marks=True)
        self.assertEqual(FakeVql.instances, [])

    def test_the_flag_lets_the_run_through(self):
        doc, code = run_chain(profile(production=True), self.chain, root=self.root, vql_factory=FakeVql,
                              allow_destructive=True)
        self.assertEqual(code, 0, doc)
        self.assertTrue(doc["steps"][0]["ok"])
        self.assertTrue(doc["cleanup"]["ran"])

    def test_a_non_production_profile_needs_no_flag(self):
        doc, code = run_chain(profile(production=False), self.chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0, doc)
        self.assertTrue(doc["cleanup"]["ran"])


class CleanupHttpBodyTest(unittest.TestCase):
    """``[cleanup] http`` entries carry a JSON body, so cleanup can undo a catalog sync.

    The marketplace tail's ``synchronize`` calls import the throwaway database and its views
    into the shared marketplace catalog; the only way to take them back out is to run the
    same calls again once VDP no longer has them. Those calls need a body
    (``proceedWithConflicts``), which a DELETE-shaped cleanup entry had no way to carry.
    """

    class FakeRest:
        calls = []

        def __init__(self, profile, server="marketplace"):
            self.profile = profile

        def call(self, method, path, *, json_body=None, params=None, multipart=None, timeout=None):
            from denodo_cli.transports.base import HttpResult
            CleanupHttpBodyTest.FakeRest.calls.append((method, path, params, json_body))
            return HttpResult(status=200, body={"inserted": [], "modified": [], "removed": []})

    def setUp(self):
        FakeVql.instances.clear()
        CleanupHttpBodyTest.FakeRest.calls.clear()
        self.root = Path(tempfile.mkdtemp())
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"
server_id = "306"

[cleanup]
http = [
  { method = "post", path = "/public/api/element-management/DATABASES/synchronize", params = { serverId = "{server_id}" }, json = { proceedWithConflicts = "SERVER_WITH_LOCAL_CHANGES" } },
]

[[step]]
id = "fix"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_the_body_reaches_the_transport(self):
        doc, code = run_chain(profile(marketplace_url="http://x/y"), self.chain, root=self.root,
                              vql_factory=FakeVql, rest_factory=CleanupHttpBodyTest.FakeRest,
                              with_marketplace=True)
        self.assertEqual(code, 0, doc)
        method, path, params, json_body = CleanupHttpBodyTest.FakeRest.calls[0]
        self.assertEqual(method, "POST")   # api_call normalises the manifest's "post"
        self.assertEqual(path, "/public/api/element-management/DATABASES/synchronize")
        self.assertEqual(params, {"serverId": "306"})
        self.assertEqual(json_body, {"proceedWithConflicts": "SERVER_WITH_LOCAL_CHANGES"})
        entry = doc["cleanup"]["http"][0]
        self.assertTrue(entry["ok"])
        self.assertFalse(entry["skipped"])
        self.assertEqual(entry["json"], {"proceedWithConflicts": "SERVER_WITH_LOCAL_CHANGES"})

    def test_a_body_placeholder_is_filled_from_values(self):
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            'json = { proceedWithConflicts = "SERVER_WITH_LOCAL_CHANGES" }',
            'json = { databaseName = "{database}" }'), encoding="utf-8")
        doc, code = run_chain(profile(marketplace_url="http://x/y"), load_chain(self.manifest),
                              root=self.root, vql_factory=FakeVql,
                              rest_factory=CleanupHttpBodyTest.FakeRest, with_marketplace=True)
        self.assertEqual(code, 0, doc)
        self.assertEqual(CleanupHttpBodyTest.FakeRest.calls[0][3], {"databaseName": "denodo_skills_test"})

    def test_an_unresolved_body_placeholder_skips_the_entry(self):
        # Same rule the path and params already follow: a value nothing ever captured means
        # there is nothing to undo, so the call must not be sent half-rendered.
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            'json = { proceedWithConflicts = "SERVER_WITH_LOCAL_CHANGES" }',
            'json = { tagId = "{tag_id}" }'), encoding="utf-8")
        doc, code = run_chain(profile(marketplace_url="http://x/y"), load_chain(self.manifest),
                              root=self.root, vql_factory=FakeVql,
                              rest_factory=CleanupHttpBodyTest.FakeRest, with_marketplace=True)
        self.assertEqual(code, 0, doc)
        self.assertEqual(CleanupHttpBodyTest.FakeRest.calls, [])
        self.assertTrue(doc["cleanup"]["http"][0]["skipped"])
        self.assertIn("captured", doc["cleanup"]["http"][0]["reason"])

    def test_a_default_run_never_touches_the_shared_catalog(self):
        # The gate that matters most: a re-sync entry names no captured value, so nothing
        # would have stopped it from firing on a plain `verify --env lab` — a run the design
        # requires to stay inside its own database — and removing from the catalog whatever
        # anybody else had orphaned there.
        doc, code = run_chain(profile(marketplace_url="http://x/y"), self.chain, root=self.root,
                              vql_factory=FakeVql, rest_factory=CleanupHttpBodyTest.FakeRest)
        self.assertEqual(code, 0, doc)
        self.assertEqual(CleanupHttpBodyTest.FakeRest.calls, [])
        self.assertTrue(doc["cleanup"]["ran"])
        self.assertTrue(doc["cleanup"]["http"][0]["skipped"])
        self.assertIn("--with-marketplace", doc["cleanup"]["http"][0]["reason"])

    def test_a_non_table_json_is_rejected_at_load_time(self):
        self.manifest.write_text("""
[cleanup]
http = [ { method = "post", path = "/x", json = "not a table" } ]

[[step]]
id = "fix"
kind = "fixture"
channel = "vql"
vql = "SELECT 1"
""", encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.manifest)
        self.assertIn("json", str(ctx.exception))

    def test_a_production_profile_refuses_the_sync_without_the_flag(self):
        # POST .../synchronize classifies as "replace"; the gate now refuses the whole run
        # up front, so nothing reaches the marketplace either.
        doc, code = run_chain(profile(marketplace_url="http://x/y", production=True), self.chain,
                              root=self.root, vql_factory=FakeVql,
                              rest_factory=CleanupHttpBodyTest.FakeRest, with_marketplace=True)
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "refused")
        self.assertEqual(CleanupHttpBodyTest.FakeRest.calls, [])


THREE_CALL_BLOCK = """# verified: 9.5.1 (live, 2026-09-01)
api get --env lab /public/api/tag-management/tags --param serverId=306 --param nameFilter=pii
api post --env lab /public/api/tags --param serverId=306 --json '{"name":"pii"}'
api put --env lab /public/api/tags/4242 --param serverId=306 --json '{"name":"pii"}'
"""


class PartialBlockMarkTest(unittest.TestCase):
    """``--update-marks`` must not re-date a block the run only partly executed.

    An http step runs the calls its ``calls`` list names, not the whole block: the
    manifest's ``marketplace-tag`` step runs 2 of its block's 4 calls, ``marketplace-category``
    1 of 3. Stamping the block's mark from such a run would claim the whole template was
    verified when two thirds of it never left the machine.
    """

    class FakeRest:
        def __init__(self, profile, server="marketplace"):
            self.profile = profile

        def call(self, method, path, *, json_body=None, params=None, multipart=None, timeout=None):
            from denodo_cli.transports.base import HttpResult
            return HttpResult(status=200, body={"id": 4242})

    def setUp(self):
        FakeVql.instances.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "marketplace").mkdir(parents=True)
        self.skill = self.root / "skills" / "marketplace" / "SKILL.md"
        self.skill.write_text("### Tag\n\n```bash\n" + THREE_CALL_BLOCK + "```\n", encoding="utf-8")
        self.manifest = self.root / "chain.toml"

    def chain(self, calls: str):
        self.manifest.write_text(f"""
[values]
database = "denodo_skills_test"
[[step]]
id = "mp-tag"
kind = "template"
channel = "http"
address = "skills/marketplace/SKILL.md#Tag"
marketplace = true
calls = {calls}
""", encoding="utf-8")
        return load_chain(self.manifest)

    def stamped(self, calls: str):
        """Run the chain with --update-marks, for the given ``calls`` list."""
        return run_chain(profile(marketplace_url="http://x/y"), self.chain(calls), root=self.root,
                         vql_factory=FakeVql, rest_factory=PartialBlockMarkTest.FakeRest,
                         with_marketplace=True, update_marks=True, today=dt.date(2026, 9, 10))

    def test_a_partly_executed_block_keeps_its_mark_and_says_why(self):
        doc, code = self.stamped("[0, 1]")
        self.assertEqual(code, 0, doc)
        self.assertFalse(doc["steps"][0]["mark"]["updated"])
        self.assertIn("2", doc["steps"][0]["mark"]["reason"])
        self.assertIn("3", doc["steps"][0]["mark"]["reason"])
        self.assertIn("2026-09-01", self.skill.read_text(encoding="utf-8"))
        self.assertNotIn("2026-09-10", self.skill.read_text(encoding="utf-8"))

    def test_a_fully_executed_block_is_stamped(self):
        doc, code = self.stamped("[0, 1, 2]")
        self.assertEqual(code, 0, doc)
        self.assertTrue(doc["steps"][0]["mark"]["updated"])
        self.assertIn("2026-09-10", self.skill.read_text(encoding="utf-8"))

    def test_an_empty_calls_list_means_the_whole_block_and_is_stamped(self):
        doc, code = self.stamped("[]")
        self.assertEqual(code, 0, doc)
        self.assertTrue(doc["steps"][0]["mark"]["updated"])
        self.assertIn("2026-09-10", self.skill.read_text(encoding="utf-8"))


class MalformedApiBlockTest(unittest.TestCase):
    """Malformed input is a reported failure, never a traceback.

    Every invocation of this tool prints exactly one JSON document. An ``api`` line a skill
    file no longer has, an unbalanced quote, a mistyped ``--json`` body — each used to reach
    the user as an ``IndexError``/``ValueError``/``JSONDecodeError`` traceback with no
    document at all.
    """

    def test_an_out_of_range_call_index_names_the_step(self):
        root = Path(tempfile.mkdtemp())
        (root / "skills" / "marketplace").mkdir(parents=True)
        (root / "skills" / "marketplace" / "SKILL.md").write_text(
            "### Tag\n\n```bash\n" + THREE_CALL_BLOCK + "```\n", encoding="utf-8")
        manifest = root / "chain.toml"
        manifest.write_text("""
[values]
database = "denodo_skills_test"
[[step]]
id = "mp-tag"
kind = "template"
channel = "http"
address = "skills/marketplace/SKILL.md#Tag"
marketplace = true
calls = [0, 7]
""", encoding="utf-8")
        doc, code = run_chain(profile(marketplace_url="http://x/y"), load_chain(manifest), root=root,
                              vql_factory=FakeVql, rest_factory=PartialBlockMarkTest.FakeRest,
                              with_marketplace=True)
        self.assertEqual(code, 1)
        self.assertFalse(doc["steps"][0]["ok"])
        self.assertEqual(doc["steps"][0]["error"]["kind"], "template")
        self.assertIn("mp-tag", doc["steps"][0]["error"]["message"])
        self.assertIn("7", doc["steps"][0]["error"]["message"])
        self.assertIn("3", doc["steps"][0]["error"]["message"])

    def test_a_negative_call_index_is_rejected_too(self):
        # int(-1) is a perfectly valid list index in Python and would silently pick the
        # block's last call — a different call than the manifest meant to name.
        with self.assertRaises(ChainError) as ctx:
            verify_module._select_calls(parse_api_calls(THREE_CALL_BLOCK), [-1])
        self.assertIn("-1", str(ctx.exception))


class ParseApiCallsFailureTest(unittest.TestCase):
    def test_an_unbalanced_quote_is_a_chain_error(self):
        with self.assertRaises(ChainError) as ctx:
            parse_api_calls("api post /public/api/tags --json '{\"name\":\"pii\"}\n")
        self.assertIn("api post", str(ctx.exception))

    def test_a_malformed_json_body_is_a_chain_error(self):
        with self.assertRaises(ChainError) as ctx:
            parse_api_calls("api post /public/api/tags --json '{\"name\",}'\n")
        self.assertIn("JSON", str(ctx.exception))

    def test_an_api_line_with_no_method_is_a_chain_error(self):
        # parse_api_calls' own filter never hands _api_call a line this short; the guard is
        # what keeps that filter from being the only thing between shlex and an IndexError.
        with self.assertRaises(ChainError) as ctx:
            verify_module._api_call("api")
        self.assertIn("method", str(ctx.exception))

    def test_an_api_line_with_no_path_is_a_chain_error(self):
        with self.assertRaises(ChainError) as ctx:
            parse_api_calls("api get --param serverId=306\n")
        self.assertIn("path", str(ctx.exception))

    def test_a_flag_with_no_value_is_a_chain_error(self):
        with self.assertRaises(ChainError) as ctx:
            parse_api_calls("api get /public/api/tags --param\n")
        self.assertIn("--param", str(ctx.exception))


class FakeVqlEncrypting(FakeVql):
    """``FakeVql`` plus the one statement the throwaway-password mechanism needs.

    The stand answers ``ENCRYPT_PASSWORD '<plaintext>'`` with one row holding the
    ciphertext; a data source refuses any other string with ``Invalid encrypted value``
    (verified on a live 9.5.1 server), which is why the chain cannot simply carry a
    literal one in the manifest.
    """

    def execute(self, statement):
        if statement.startswith("ENCRYPT_PASSWORD"):
            self.executed.append(statement)
            return VqlResult(statement=statement, columns=["encrypted"], rows=[["Rr+OdGTW=="]])
        return super().execute(statement)


class FakeVqlEncryptionFails(FakeVql):
    def execute(self, statement):
        if statement.startswith("ENCRYPT_PASSWORD"):
            self.executed.append(statement)
            raise RuntimeError(
                "ERROR:  connection reset\nDETAIL:  java.sql.SQLException: reset\n")
        return super().execute(statement)


ENCRYPTED_SKILL = """### Source

```sql
-- verified: 9.5.1 (live, 2026-09-01)
CREATE OR REPLACE DATASOURCE JDBC ds_orders_db
    USERPASSWORD = '<ciphertext — fill it in before applying>' ENCRYPTED;
```
"""


class ThrowawayPasswordTest(unittest.TestCase):
    """``@encrypt-throwaway``: a ciphertext the run itself produces on the stand.

    The JDBC template carries ``USERPASSWORD … ENCRYPTED`` and the server validates the
    ciphertext at creation time, so the step needs a real one — and a real one must never
    be committed (it is a credential, and it is bound to the server that made it). The
    manifest therefore declares the *intent* and the run fills in the value.
    """

    def setUp(self):
        FakeVql.instances.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "datasources").mkdir(parents=True)
        (self.root / "skills" / "datasources" / "SKILL.md").write_text(ENCRYPTED_SKILL, encoding="utf-8")
        self.manifest = self.root / "chain.toml"

    def chain(self, text):
        self.manifest.write_text(text, encoding="utf-8")
        return load_chain(self.manifest)

    MANIFEST = """
[values]
database = "denodo_skills_test"
jdbc_password = "@encrypt-throwaway"
[[step]]
id = "jdbc-source"
kind = "template"
channel = "vql"
address = "skills/datasources/SKILL.md#Source"
substitute = { "<ciphertext — fill it in before applying>" = "{jdbc_password}" }
"""

    def test_the_marker_is_replaced_by_a_ciphertext_from_the_stand(self):
        doc, code = run_chain(profile(), self.chain(self.MANIFEST), root=self.root,
                              vql_factory=FakeVqlEncrypting)
        self.assertEqual(code, 0, doc)
        self.assertEqual(doc["values"]["jdbc_password"], "Rr+OdGTW==")
        executed = " ".join(s for i in FakeVql.instances for s in i.executed)
        self.assertIn("ENCRYPT_PASSWORD", executed)
        self.assertIn("USERPASSWORD = 'Rr+OdGTW==' ENCRYPTED", executed)
        self.assertNotIn("@encrypt-throwaway", executed)

    def test_the_plaintext_never_reaches_the_report(self):
        # The password is a throwaway, but the report is what a session keeps: the
        # mechanism is worth nothing if the plaintext rides along in it.
        doc, _ = run_chain(profile(), self.chain(self.MANIFEST), root=self.root,
                           vql_factory=FakeVqlEncrypting)
        sent = [s for i in FakeVql.instances for s in i.executed if s.startswith("ENCRYPT_PASSWORD")]
        plaintext = sent[0][len("ENCRYPT_PASSWORD '"):-1]
        self.assertTrue(plaintext, "the probe statement carried no password at all")
        self.assertNotIn(plaintext, json.dumps(doc, ensure_ascii=False))

    def test_a_failed_encryption_stops_the_run_before_the_first_step(self):
        # A step whose body still says "{jdbc_password}" would reach the server verbatim
        # and fail there with a confusing remote error; worse, it would report the
        # template as broken when the stand simply could not be reached.
        doc, code = run_chain(profile(), self.chain(self.MANIFEST), root=self.root,
                              vql_factory=FakeVqlEncryptionFails)
        self.assertEqual(code, 1, doc)
        self.assertFalse(doc["ok"])
        self.assertIn("jdbc_password", doc["error"]["message"])
        self.assertNotIn("steps", doc)
        executed = " ".join(s for i in FakeVql.instances for s in i.executed)
        self.assertNotIn("CREATE OR REPLACE DATASOURCE", executed)

    def test_an_ordinary_value_is_left_alone(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "jdbc-source"
kind = "template"
channel = "vql"
address = "skills/datasources/SKILL.md#Source"
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVqlEncrypting)
        self.assertEqual(code, 0, doc)
        executed = " ".join(s for i in FakeVql.instances for s in i.executed)
        self.assertNotIn("ENCRYPT_PASSWORD", executed)


class MultipartApiCallTest(unittest.TestCase):
    """``--part``: the one marketplace call that is not a JSON body.

    ``POST /public/api/external-providers-types`` takes multipart, and a flag this parser
    does not know is dropped together with its value — so before this, that line parsed
    into a POST with no body at all and went to the server empty. A step is allowed to
    skip a call (``calls``); it must never send a mutilated one.
    """

    LINE = ("api post --env lab /public/api/external-providers-types "
            "--part 'request=json:{\"name\":\"ACME_BI\",\"visualName\":\"Acme BI\"}'\n")

    def test_a_part_becomes_a_multipart_body(self):
        call = parse_api_calls(self.LINE)[0]
        self.assertEqual(call["method"], "POST")
        self.assertIsNone(call["json"])
        name, content, content_type = call["multipart"]["request"]
        self.assertIsNone(name)
        self.assertEqual(content_type, "application/json")
        self.assertIn(b"ACME_BI", content)

    def test_a_call_without_parts_carries_no_multipart(self):
        call = parse_api_calls("api get /public/api/tags --param nameFilter=pii\n")[0]
        self.assertIsNone(call["multipart"])

    def test_a_malformed_part_is_a_chain_error(self):
        with self.assertRaises(ChainError) as ctx:
            parse_api_calls("api post /public/api/external-providers-types --part 'request'\n")
        self.assertIn("--part", str(ctx.exception))

    def test_a_part_with_invalid_json_is_a_chain_error(self):
        with self.assertRaises(ChainError) as ctx:
            parse_api_calls("api post /x --part 'request=json:{\"name\",}'\n")
        self.assertIn("--part", str(ctx.exception))


class MultipartStepTest(unittest.TestCase):
    """The multipart body has to survive all the way to the transport, substitutions and all."""

    class FakeRest:
        calls = []

        def __init__(self, profile, server="marketplace"):
            self.profile = profile

        def call(self, method, path, *, json_body=None, params=None, multipart=None, timeout=None):
            from denodo_cli.transports.base import HttpResult
            MultipartStepTest.FakeRest.calls.append((method, path, json_body, multipart))
            return HttpResult(status=201, body={"externalProviderTypeId": 30})

    BLOCK = ("api post --env lab /public/api/external-providers-types \\\n"
             "    --part 'request=json:{\"name\":\"ACME_BI\",\"visualName\":\"Acme BI\"}'\n")

    def setUp(self):
        FakeVql.instances.clear()
        MultipartStepTest.FakeRest.calls.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "marketplace").mkdir(parents=True)
        (self.root / "skills" / "marketplace" / "SKILL.md").write_text(
            "### External element\n\n```bash\n" + self.BLOCK + "```\n", encoding="utf-8")
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"
tag_prefix = "verify_"
[[step]]
id = "provider-type"
kind = "template"
channel = "http"
address = "skills/marketplace/SKILL.md#External element"
marketplace = true
calls = [0]
capture = { provider_type_id = "externalProviderTypeId" }
substitute = { "\\"ACME_BI\\"" = "\\"{tag_prefix}ACME_BI\\"" }
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_the_part_reaches_the_transport_with_substitutions_applied(self):
        doc, code = run_chain(profile(marketplace_url="http://x/y"), self.chain, root=self.root,
                              vql_factory=FakeVql, rest_factory=MultipartStepTest.FakeRest,
                              with_marketplace=True)
        self.assertEqual(code, 0, doc)
        _, path, json_body, multipart = MultipartStepTest.FakeRest.calls[0]
        self.assertEqual(path, "/public/api/external-providers-types")
        self.assertIsNone(json_body)
        self.assertIn(b"verify_ACME_BI", multipart["request"][1])
        self.assertEqual(doc["values"]["provider_type_id"], "30")


class MultiLineApiCallTest(unittest.TestCase):
    """A quoted argument may span lines — bash keeps the newline, and so must this.

    ``skills/marketplace/SKILL.md`` writes the external-tool-server body across three
    lines inside one pair of single quotes. That is ordinary shell (a newline inside
    quotes is just a character; a trailing backslash would end up *inside* the JSON), so
    the executor has to follow the template's form rather than the template following the
    executor's.
    """

    BLOCK = """api post --env lab /public/api/external-tool-servers \\
    --json '{"type":"CUSTOM","name":"acme_bi_server",
             "externalProviderTypeId":30,
             "databaseName":"sales_analytics","viewName":"i_acme_bi_elements"}'
# → {"id":217, …}
api get --env lab /public/api/external-tool-servers/217/vql-metadata
"""

    def test_a_quoted_body_spanning_lines_is_one_call(self):
        calls = parse_api_calls(self.BLOCK)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["json"]["viewName"], "i_acme_bi_elements")
        self.assertEqual(calls[0]["json"]["externalProviderTypeId"], 30)
        self.assertEqual(calls[1]["path"], "/public/api/external-tool-servers/217/vql-metadata")

    def test_an_unbalanced_quote_still_fails_rather_than_swallowing_the_block(self):
        with self.assertRaises(ChainError) as ctx:
            parse_api_calls("api post /x --json '{\"a\":1}\napi get /y\n")
        self.assertIn("api post", str(ctx.exception))


class ExternalElementBlockTest(unittest.TestCase):
    """The real block, as the skill writes it: four calls, one of them multipart."""

    ADDRESS = ("skills/marketplace/SKILL.md#External element — a dashboard, job or "
               "contract from another tool[0]")

    def test_the_skill_block_parses_into_four_calls(self):
        # the block names its ids as placeholders, as every template must (rule 1 of the
        # skill); the chain substitutes captured ids, and so does this test
        from denodo_cli.templates import load_block
        repo = Path(__file__).resolve().parents[1]
        body = render(load_block(repo, self.ADDRESS).body,
                      {"<provider_type_id>": "30", "<tool_server_id>": "217"}, {})
        calls = parse_api_calls(body)
        self.assertEqual([c["method"] for c in calls], ["POST", "POST", "GET", "POST"])
        self.assertIsNotNone(calls[0]["multipart"])
        self.assertEqual(calls[1]["json"]["type"], "CUSTOM")
        self.assertEqual(calls[1]["json"]["externalProviderTypeId"], 30)
        self.assertIn("vql-metadata", calls[2]["path"])
        self.assertEqual(calls[3]["json"], {"externalToolServerIds": [217]})

    def test_no_literal_id_is_left_in_the_skill_block(self):
        from denodo_cli.templates import load_block
        repo = Path(__file__).resolve().parents[1]
        body = load_block(repo, self.ADDRESS).body
        self.assertIn("<provider_type_id>", body)
        self.assertIn("<tool_server_id>", body)


SCHEDULER_SKILL = """### Refresh a cache

```json
{
  "type": "VDPCache",
  "name": "iv_household_income_cache",
  "extractionSection": {"loadprocesses": [{"viewName": "sales_analytics.iv_household_income",
                                           "cacheInvalidationMode": "ALL_ROWS"}]}
}
```

```bash
# create the job from its file
api --server scheduler post /public/api/projects/<project_id>/jobs --json-file scheduler/iv_household_income_cache.json --env dev
api --server scheduler get /public/api/projects/<project_id>/jobs/<job_id> --env dev
```

### Run it once

```bash
api --server scheduler put /public/api/projects/<project_id>/jobs/<job_id>/status --json '{"action": "start"}' --env dev
api --server scheduler get /public/api/projects/<project_id>/jobs/<job_id>/status --env dev
```
"""

SCHEDULER_MANIFEST = """
[values]
database = "denodo_skills_test"

[cleanup]
http = [
  { server = "scheduler", method = "delete", path = "/public/api/projects/{project_id}" },
]

[[step]]
id = "scheduler-project"
kind = "fixture"
channel = "http"
scheduler = true
vql = "api --server scheduler post /public/api/projects --json '{\\"name\\": \\"verify_jobs\\"}'"
capture = { project_id = "id" }

[[step]]
id = "scheduler-cache-job"
kind = "template"
channel = "http"
scheduler = true
address = "skills/scheduler/SKILL.md#Refresh a cache[1]"
substitute = { "<project_id>" = "{project_id}", "<job_id>" = "{job_id}" }
files = { "scheduler/iv_household_income_cache.json" = { address = "skills/scheduler/SKILL.md#Refresh a cache[0]", substitute = { sales_analytics = "{database}" } } }
capture = { job_id = "id" }
capture_from = 0
expect_body = { "extractionSection.loadprocesses.0.cacheInvalidationMode" = "ALL_ROWS" }

[[step]]
id = "scheduler-run"
kind = "template"
channel = "http"
scheduler = true
address = "skills/scheduler/SKILL.md#Run it once"
substitute = { "<project_id>" = "{project_id}", "<job_id>" = "{job_id}" }
poll = { field = "state", until = "NOT_RUNNING", seconds = 10, every = 1 }
expect_body = { result = "COMPLETE" }
"""


class FakeScheduler:
    """A Scheduler that keeps one project and one job; a started job runs for two polls."""
    calls = []
    jobs = {}
    polls_while_running = 2

    def __init__(self, profile, server="marketplace"):
        self.server = server

    def call(self, method, path, *, json_body=None, params=None, multipart=None, timeout=None):
        from denodo_cli.transports.base import HttpResult
        FakeScheduler.calls.append((self.server, method, path, json_body))
        if method == "POST" and path == "/public/api/projects":
            return HttpResult(status=201, body={"id": 101, "projectDetails": json_body})
        if method == "POST" and path == "/public/api/projects/101/jobs":
            FakeScheduler.jobs[7] = dict(json_body, id=7, state="NOT_RUNNING", result="NEVER_EXECUTED")
            return HttpResult(status=201, body=FakeScheduler.jobs[7])
        if method == "GET" and path == "/public/api/projects/101/jobs/7":
            return HttpResult(status=200, body=FakeScheduler.jobs[7])
        if method == "PUT" and path == "/public/api/projects/101/jobs/7/status":
            FakeScheduler.jobs[7]["remaining"] = FakeScheduler.polls_while_running
            return HttpResult(status=204, body=None)
        if method == "GET" and path == "/public/api/projects/101/jobs/7/status":
            job = FakeScheduler.jobs[7]
            if job.get("remaining", 0) > 0:
                job["remaining"] -= 1
                return HttpResult(status=200, body={"state": "RUNNING", "result": "NEVER_EXECUTED"})
            return HttpResult(status=200, body={"state": "NOT_RUNNING", "result": "COMPLETE"})
        if method == "DELETE":
            return HttpResult(status=204, body=None)
        return HttpResult(status=404, body={"message": f"unexpected {method} {path}"})


class SchedulerChainTest(unittest.TestCase):
    """The Scheduler tail (T36): its own gate, the server named on each api line, a job body
    taken from the json block of the same skill, nested fields, and waiting for a run."""

    def setUp(self):
        FakeVql.instances.clear()
        FakeScheduler.calls.clear()
        FakeScheduler.jobs.clear()
        FakeScheduler.polls_while_running = 2
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "scheduler").mkdir(parents=True)
        (self.root / "skills" / "scheduler" / "SKILL.md").write_text(SCHEDULER_SKILL, encoding="utf-8")
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text(SCHEDULER_MANIFEST, encoding="utf-8")
        sleeper = mock.patch.object(verify_module.time, "sleep", lambda seconds: None)
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def run_chain(self, **kw):
        kw.setdefault("with_scheduler", True)
        return run_chain(profile(), load_chain(self.manifest), root=self.root, vql_factory=FakeVql,
                         rest_factory=FakeScheduler, **kw)

    def test_parse_api_calls_reads_the_server_and_the_json_file(self):
        calls = parse_api_calls("api --server scheduler post /p/jobs --json-file x/job.json --env dev\n")
        self.assertEqual(calls[0]["server"], "scheduler")
        self.assertEqual((calls[0]["method"], calls[0]["path"]), ("POST", "/p/jobs"))
        self.assertEqual(calls[0]["json_file"], "x/job.json")
        self.assertEqual(parse_api_calls("api get /public/api/tags\n")[0]["server"], "marketplace")

    def test_the_chain_creates_reads_back_runs_and_cleans_up(self):
        doc, code = self.run_chain()
        self.assertEqual(code, 0, json.dumps(doc, indent=1)[:3000])
        self.assertEqual(doc["values"]["project_id"], "101")
        self.assertEqual(doc["values"]["job_id"], "7")
        self.assertTrue(all(server == "scheduler" for server, *_ in FakeScheduler.calls))
        created = [body for _, method, path, body in FakeScheduler.calls
                   if method == "POST" and path.endswith("/jobs")][0]
        # the body is the json block, with the step's file substitution applied
        self.assertEqual(created["extractionSection"]["loadprocesses"][0]["viewName"],
                         "denodo_skills_test.iv_household_income")
        status_reads = [c for c in FakeScheduler.calls if c[1] == "GET" and c[2].endswith("/status")]
        self.assertEqual(len(status_reads), 3)  # RUNNING, RUNNING, NOT_RUNNING
        self.assertEqual(doc["cleanup"]["http"][0]["status"], 204)
        self.assertEqual(FakeScheduler.calls[-1][1:3], ("DELETE", "/public/api/projects/101"))

    def test_scheduler_steps_and_their_cleanup_are_skipped_unless_asked_for(self):
        doc, code = self.run_chain(with_scheduler=False)
        self.assertEqual(code, 0)
        self.assertTrue(all(s["skipped"] for s in doc["steps"]))
        self.assertIn("--with-scheduler", doc["steps"][0]["reason"])
        self.assertTrue(doc["cleanup"]["http"][0]["skipped"])
        self.assertEqual(FakeScheduler.calls, [])

    def test_a_nested_expected_field_that_differs_fails_the_step(self):
        self.manifest.write_text(SCHEDULER_MANIFEST.replace('= "ALL_ROWS" }', '= "NONE" }'), encoding="utf-8")
        doc, code = self.run_chain()
        self.assertEqual(code, 1)
        step = doc["steps"][1]
        self.assertEqual(step["error"]["kind"], "expect_body")
        self.assertIn("extractionSection.loadprocesses.0.cacheInvalidationMode", step["error"]["message"])

    def test_a_run_that_does_not_finish_in_time_fails_the_step(self):
        FakeScheduler.polls_while_running = 100
        doc, code = self.run_chain()
        self.assertEqual(code, 1)
        self.assertEqual(doc["steps"][2]["error"]["kind"], "poll")
        self.assertIn("RUNNING", doc["steps"][2]["error"]["message"])
        self.assertTrue(doc["cleanup"]["ran"])  # the project is still removed

    def test_a_json_file_the_step_does_not_map_is_a_template_error(self):
        self.manifest.write_text(SCHEDULER_MANIFEST.replace(
            'files = { "scheduler/iv_household_income_cache.json"', 'files = { "scheduler/other.json"'),
            encoding="utf-8")
        doc, code = self.run_chain()
        self.assertEqual(code, 1)
        self.assertEqual(doc["steps"][1]["error"]["kind"], "template")
        self.assertIn("scheduler/iv_household_income_cache.json", doc["steps"][1]["error"]["message"])

    def test_capture_from_names_the_call_whose_body_is_captured(self):
        # the create call answers with the new job's id; the read-back after it is what
        # expect_body judges
        doc, _ = self.run_chain()
        self.assertEqual(doc["values"]["job_id"], "7")

    def test_manifest_shape_errors(self):
        bad = {
            "scheduler on a vql step": '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "vql"\nvql = "SELECT 1"\nscheduler = true\n',
            "both gates": '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "http"\nvql = "api get /x"\nscheduler = true\nmarketplace = true\n',
            "poll without until": '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "http"\nvql = "api get /x"\nscheduler = true\npoll = { field = "state" }\n',
            "files not a table": '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "http"\nvql = "api get /x"\nscheduler = true\nfiles = "a.json"\n',
            "unknown cleanup server": '[cleanup]\nhttp = [ { server = "nope", method = "delete", path = "/x" } ]\n[[step]]\nid = "a"\nkind = "fixture"\nchannel = "vql"\nvql = "SELECT 1"\n',
        }
        for name, text in bad.items():
            with self.subTest(name):
                self.manifest.write_text(text, encoding="utf-8")
                with self.assertRaises(ChainError):
                    load_chain(self.manifest)
