import datetime as dt
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
-- verified: 9.5.1 (стенд, 2026-09-01)
CREATE OR REPLACE DATABASE sales_analytics 'x';
```

### Boom

```sql
-- verified: 9.5.1 (стенд, 2026-09-01)
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
        self.assertEqual(doc["summary"], {"verified": 0, "failed": 1, "skipped": 1})

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
        doc, code = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql,
                              values_override={"tag_prefix": "verify_"})
        self.assertEqual(code, 0)
        self.assertTrue(doc["cleanup"]["ran"])
        dropped = " ".join(FakeVql.instances[-1].executed)
        self.assertIn("DROP DATABASE IF EXISTS denodo_skills_test CASCADE", dropped)
        self.assertIn("DROP TAG IF EXISTS verify_pii", dropped)

    def test_cleanup_runs_after_a_failed_chain_too(self):
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            'vql = "CONNECT DATABASE {database};"', 'vql = "BOOM"'), encoding="utf-8")
        doc, code = run_chain(profile(), load_chain(self.manifest), root=self.root, vql_factory=FakeVql,
                              values_override={"tag_prefix": "verify_"})
        self.assertEqual(code, 1)
        self.assertTrue(doc["cleanup"]["ran"])

    def test_keep_skips_cleanup_and_says_so(self):
        doc, _ = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql, keep=True,
                           values_override={"tag_prefix": "verify_"})
        self.assertFalse(doc["cleanup"]["ran"])
        self.assertIn("--keep", doc["cleanup"]["reason"])
        self.assertNotIn("DROP DATABASE", " ".join(FakeVql.instances[-1].executed))

    def test_a_failing_cleanup_statement_is_reported_and_the_rest_still_run(self):
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            '"DROP TAG IF EXISTS {tag_prefix}pii",', '"DROP TAG BOOM", "DROP TAG IF EXISTS x",'),
            encoding="utf-8")
        doc, code = run_chain(profile(), load_chain(self.manifest), root=self.root, vql_factory=FakeVql,
                              values_override={"tag_prefix": "verify_"})
        self.assertEqual(code, 1)                       # уборка не убралась — это провал прогона
        self.assertTrue(doc["cleanup"]["ran"])
        kinds = [s["ok"] for s in doc["cleanup"]["statements"]]
        self.assertEqual(kinds, [True, False, True])


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
        doc, code = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql,
                              values_override={"tag_prefix": "verify_"})
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
        self.assertIn("-- verified: 9.5.1 (стенд, 2026-09-10)", self.skill.read_text(encoding="utf-8"))
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


BASH_BLOCK = """# verified: 9.5.1 (стенд, 2026-09-10)

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

        def __init__(self, profile):
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
