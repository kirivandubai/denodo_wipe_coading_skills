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

    def test_keep_skips_cleanup_and_says_so(self):
        doc, _ = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql, keep=True)
        self.assertFalse(doc["cleanup"]["ran"])
        self.assertIn("--keep", doc["cleanup"]["reason"])
        self.assertNotIn("DROP DATABASE", " ".join(FakeVql.instances[-1].executed))

    def test_a_failing_cleanup_statement_is_reported_and_the_rest_still_run(self):
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            '"DROP TAG IF EXISTS {tag_prefix}pii",', '"DROP TAG BOOM", "DROP TAG IF EXISTS x",'),
            encoding="utf-8")
        doc, code = run_chain(profile(), load_chain(self.manifest), root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 1)                       # уборка не убралась — это провал прогона
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


DESTRUCTIVE_BASH_BLOCK = """# verified: 9.5.1 (стенд, 2026-09-10)
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

        def __init__(self, profile):
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

        def __init__(self, profile):
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

        def __init__(self, profile):
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


THREE_CALL_BLOCK = """# verified: 9.5.1 (стенд, 2026-09-01)
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
        def __init__(self, profile):
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
