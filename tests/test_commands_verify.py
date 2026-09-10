import tempfile
import unittest
from pathlib import Path
from unittest import mock

from denodo_cli.commands import verify as verify_module
from denodo_cli.commands.verify import ChainError, load_chain, render, run_chain
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
            rows = [] if "GET_VIEWS" in statement else [["denodo_skills_test"]]
            return VqlResult(statement=statement, columns=["c"], rows=rows)
        return VqlResult(statement=statement, columns=None, rows=None)

    def close(self):
        self.closed = True


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
