import datetime as dt
import tempfile
import unittest
from pathlib import Path

from denodo_cli.catalog import Found
from denodo_cli.ledger import Ledger
from denodo_cli.planner import PlanContext, plan_statements
from denodo_cli.project import Declaration, Declarations
from denodo_cli.statements import ObjectRef

NOW = dt.datetime(2026, 10, 6, 9, 0, tzinfo=dt.timezone.utc)
SERVER = "h:9996"


class FakeCatalog:
    """Existing objects as {(type, db, name): (internal_id, subtype)}; dependants per view."""

    def __init__(self, existing=None, used_by=None, policies=None):
        self.existing = {(t, d, n): v for (t, d, n), v in (existing or {}).items()}
        self.used = used_by or {}
        self.policies = policies or {}
        self.errors = []

    def lookup(self, ref):
        value = self.existing.get(ref.key())
        if value is None:
            return Found(False)
        internal_id, subtype = value
        return Found(True, internal_id, subtype)

    def used_by(self, database, view):
        return self.used.get((database, view), [])

    def policies_naming(self, tag):
        return self.policies.get(tag, [])


class PlannerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name), "s1")
        self.existing = {
            ("database", None, "sales"): (None, None),
            ("view", "sales", "mine"): ("_m1", "derived"),
            ("view", "sales", "theirs"): ("_t1", "derived"),
            ("view", "sales", "dashboard"): ("_d1", "derived"),
            ("view", "sales", "mine_metrics"): ("_mm", "metric"),
            ("view", "sales", "their_metrics"): ("_tm", "metric"),
            ("view", "sales", "bv_rt"): ("_rt", "base"),
            ("view", "sales", "m_table"): ("_mt", "base"),
            ("tag", None, "pii"): ("pii_1", None),
            ("role", None, "analyst"): (None, None),
            ("user", None, "mlee"): (None, None),
        }
        self.used_by = {("sales", "theirs"): [("sales", "dashboard")], ("sales", "mine"): []}
        for name, kind, iid in (("mine", "derived view", "_m1"), ("mine_metrics", "metric view", "_mm"),
                                ("bv_rt", "remote table", "_rt"), ("m_table", "materialized table", "_mt")):
            self.ledger.record_created(SERVER, ObjectRef("view", "sales", name, kind), internal_id=iid,
                                       source=None, statement="", now=NOW)
        self.declarations = Declarations()

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, *statements, production=False, catalog=None, ledger="default"):
        ctx = PlanContext(
            server=SERVER, database="sales", production=production,
            catalog=catalog or FakeCatalog(self.existing, self.used_by, {"pii": ["mask_pii"]}),
            ledger=self.ledger if ledger == "default" else ledger, declarations=self.declarations)
        return plan_statements(list(statements), ctx)

    def one(self, statement, **kw):
        return self.plan(statement, **kw)[0]

    # --- reads and sessions ---

    def test_reads_are_yours_on_any_profile(self):
        for production in (False, True):
            entry = self.one("SELECT * FROM theirs", production=production)
            self.assertEqual((entry["action"], entry["needs_yes"]), ("read", False))

    def test_connect_moves_the_database_for_what_follows(self):
        entries = self.plan("CONNECT DATABASE other", "CREATE OR REPLACE VIEW mine AS SELECT 1 AS a FROM Dual()")
        self.assertEqual(entries[1]["object"]["database"], "other")
        self.assertFalse(entries[1]["exists"])

    # --- creates and replaces ---

    def test_a_new_object_is_yours(self):
        entry = self.one("CREATE OR REPLACE VIEW brand_new AS SELECT 1 AS a FROM Dual()")
        self.assertEqual((entry["action"], entry["exists"], entry["own"], entry["needs_yes"]),
                         ("create", False, True, False))

    def test_replacing_your_own_object_is_yours(self):
        entry = self.one("CREATE OR REPLACE VIEW mine AS SELECT 2 AS a FROM Dual()")
        self.assertEqual((entry["action"], entry["exists"], entry["own"], entry["needs_yes"]),
                         ("replace", True, True, False))

    def test_replacing_someone_elses_object_waits(self):
        entry = self.one("CREATE OR REPLACE VIEW theirs AS SELECT 2 AS a FROM Dual()")
        self.assertEqual((entry["own"], entry["needs_yes"]), (False, True))
        self.assertEqual(entry["dependents"], [{"database": "sales", "name": "dashboard", "own": False}])
        self.assertIn("did not create", entry["why"])

    def test_a_project_declaration_makes_the_replacement_yours_with_conditions(self):
        self.declarations = Declarations(root=Path("/repo"), base="abc", entries={
            ("view", "sales", "theirs"): Declaration("model/v.vql", "CREATE OR REPLACE VIEW theirs AS SELECT 1 AS a FROM Dual()")})
        changed = self.one("CREATE OR REPLACE VIEW theirs AS SELECT 2 AS a FROM Dual()")
        self.assertEqual((changed["needs_yes"], changed["declared_in"]), (False, "model/v.vql"))
        self.assertEqual(len(changed["conditions"]), 2)
        same = self.one("CREATE  OR REPLACE VIEW theirs AS SELECT 1 AS a FROM Dual()")
        self.assertEqual((same["needs_yes"], same["conditions"]), (False, []))
        self.assertIn("unchanged", same["why"])

    def test_a_metric_view_needs_the_session_not_a_file(self):
        self.declarations = Declarations(root=Path("/repo"), base="abc", entries={
            ("view", "sales", "their_metrics"): Declaration("m.vql", "CREATE OR REPLACE METRIC VIEW their_metrics AS x")})
        self.assertTrue(self.one("CREATE OR REPLACE METRIC VIEW their_metrics AS y")["needs_yes"])
        self.assertFalse(self.one("CREATE OR REPLACE METRIC VIEW mine_metrics AS y")["needs_yes"])

    def test_create_without_replace_over_an_existing_name_is_refused_by_the_server(self):
        entry = self.one("CREATE VIEW theirs AS SELECT 1 AS a FROM Dual()")
        self.assertFalse(entry["needs_yes"])
        self.assertIn("refuses", entry["conditions"][0])

    def test_an_earlier_create_in_the_input_makes_the_object_yours(self):
        entries = self.plan("CREATE OR REPLACE VIEW fresh AS SELECT 1 AS a FROM Dual()",
                            "ALTER VIEW fresh CACHE FULL")
        self.assertEqual((entries[1]["exists"], entries[1]["own"], entries[1]["needs_yes"]), (True, True, False))

    def test_replacing_someone_elses_object_does_not_make_it_yours(self):
        entries = self.plan("CREATE OR REPLACE VIEW theirs AS SELECT 2 AS a FROM Dual()",
                            "ALTER VIEW theirs RENAME theirs2", "ALTER VIEW theirs2 CACHE FULL")
        self.assertEqual([e["needs_yes"] for e in entries], [True, True, True])
        self.assertEqual((entries[2]["exists"], entries[2]["own"]), (True, False))

    def test_a_renamed_own_view_stays_yours(self):
        entries = self.plan("ALTER VIEW mine RENAME mine2", "ALTER VIEW mine2 CACHE FULL")
        self.assertEqual([e["needs_yes"] for e in entries], [False, False])

    def test_identity_decides_not_the_name(self):
        catalog = FakeCatalog({**self.existing, ("view", "sales", "mine"): ("_other", "derived")})
        entry = self.one("ALTER VIEW mine CACHE FULL", catalog=catalog)
        self.assertEqual((entry["own"], entry["needs_yes"]), (False, True))

    # --- alter, rename, drop ---

    def test_alter_of_your_view_nobody_else_reads(self):
        entry = self.one("ALTER VIEW mine CACHE FULL")
        self.assertEqual((entry["action"], entry["needs_yes"]), ("alter", False))

    def test_alter_of_your_view_that_someone_else_reads(self):
        used = {**self.used_by, ("sales", "mine"): [("sales", "theirs")]}
        entry = self.one("ALTER VIEW mine CACHE FULL", catalog=FakeCatalog(self.existing, used))
        self.assertTrue(entry["needs_yes"])
        self.assertIn("reads it", entry["why"])

    def test_rename_follows_alter(self):
        self.assertFalse(self.one("ALTER VIEW mine RENAME mine2")["needs_yes"])
        self.assertTrue(self.one("ALTER VIEW theirs RENAME theirs2")["needs_yes"])

    def test_a_drop_always_waits(self):
        for name in ("mine", "theirs"):
            entry = self.one(f"DROP VIEW {name}")
            self.assertEqual((entry["action"], entry["needs_yes"]), ("drop", True))

    # --- writes, settings, caches, procedures, tables ---

    def test_writes(self):
        self.assertFalse(self.one("INSERT INTO m_table (a) VALUES (1)")["needs_yes"])
        self.assertTrue(self.one("INSERT INTO theirs (a) VALUES (1)")["needs_yes"])
        self.assertTrue(self.one("UPDATE m_table SET a = 2")["needs_yes"])
        self.assertTrue(self.one("DELETE FROM m_table")["needs_yes"])

    def test_server_settings_wait(self):
        self.assertTrue(self.one("SET 'com.denodo.x' = 'y'")["needs_yes"])
        self.assertFalse(self.one("SET QUERYTIMEOUT TO 100")["needs_yes"])

    def test_cache_load(self):
        load = "SELECT * FROM {} CONTEXT ('cache_preload' = 'true', 'cache_invalidate' = 'all_rows')"
        self.assertFalse(self.one(load.format("mine"))["needs_yes"])
        self.assertTrue(self.one(load.format("theirs"))["needs_yes"])

    def test_clean_cache_of_your_view_only(self):
        self.assertFalse(self.one("CALL CLEAN_CACHE_DATABASE('sales', 'mine')")["needs_yes"])
        self.assertTrue(self.one("CALL CLEAN_CACHE_DATABASE('sales', 'theirs')")["needs_yes"])
        self.assertTrue(self.one("CALL CLEAN_CACHE_DATABASE('sales')")["needs_yes"])

    def test_other_state_changing_procedures_wait(self):
        self.assertTrue(self.one("SELECT * FROM GENERATE_STATS() WHERE input_database_name = 'sales'")["needs_yes"])

    def test_a_new_remote_table_by_the_procedure(self):
        entry = self.one("SELECT phase FROM CREATE_REMOTE_TABLE() WHERE remote_table_name = 'h' "
                         "AND replace_remote_table_if_exist = false AND base_view_name = 'bv_h'")
        self.assertFalse(entry["needs_yes"])
        self.assertEqual(len(entry["conditions"]), 2)
        replacing = self.one("SELECT phase FROM CREATE_REMOTE_TABLE() WHERE remote_table_name = 'h' "
                             "AND replace_remote_table_if_exist = true AND base_view_name = 'theirs'")
        self.assertTrue(replacing["needs_yes"])

    def test_refresh(self):
        self.assertFalse(self.one("REFRESH bv_rt")["needs_yes"])
        self.assertTrue(self.one("REFRESH theirs")["needs_yes"])

    def test_summaries(self):
        self.assertFalse(self.one("CREATE SUMMARY VIEW s_new AS SELECT 1 DATA_LOAD_IMMEDIATE = FALSE")["needs_yes"])
        self.assertTrue(self.one("CREATE SUMMARY VIEW s_new AS SELECT 1")["needs_yes"])

    def test_tables_replaced(self):
        self.assertFalse(self.one("CREATE OR REPLACE MATERIALIZED TABLE m_table (a:int)")["needs_yes"])
        self.assertTrue(self.one("CREATE OR REPLACE MATERIALIZED TABLE theirs (a:int)")["needs_yes"])
        self.assertFalse(self.one("CREATE OR REPLACE MATERIALIZED TABLE m_new (a:int)")["needs_yes"])

    def test_ai_over_rows(self):
        self.assertTrue(self.one("SELECT CLASSIFY_AI(c, 'a,b') FROM theirs")["needs_yes"])
        self.assertFalse(self.one("SELECT CLASSIFY_AI('x', 'a,b') FROM Dual()")["needs_yes"])

    # --- security and tags ---

    def test_a_new_role_over_your_objects(self):
        entry = self.one("CREATE OR REPLACE ROLE fresh_role 'r' GRANT EXECUTE ON sales.mine")
        self.assertEqual((entry["needs_yes"], entry["touches"]), (False, []))

    def test_a_new_role_over_someone_elses_view(self):
        entry = self.one("CREATE OR REPLACE ROLE fresh_role 'r' GRANT EXECUTE ON sales.theirs")
        self.assertTrue(entry["needs_yes"])
        self.assertEqual(entry["touches"], [{"type": "view", "name": "sales.theirs"}])

    def test_an_existing_role_or_any_user(self):
        self.assertTrue(self.one("CREATE OR REPLACE ROLE analyst 'r' GRANT EXECUTE ON sales.mine")["needs_yes"])
        self.assertTrue(self.one("ALTER USER mlee GRANT ROLE fresh_role")["needs_yes"])
        self.assertTrue(self.one("CREATE USER zq_new EXTERNAL")["needs_yes"])

    def test_tags_on_your_view(self):
        self.assertFalse(self.one("CREATE OR REPLACE VIEW mine ( a TAGS ( fresh_tag ) ) AS SELECT 1 AS a FROM Dual()")["needs_yes"])

    def test_a_tag_a_policy_names_on_your_view(self):
        entry = self.one("CREATE OR REPLACE VIEW mine ( a TAGS ( pii ) ) AS SELECT 1 AS a FROM Dual()")
        self.assertTrue(entry["needs_yes"])
        self.assertIn("mask_pii", entry["why"])

    def test_a_tag_on_someone_elses_view(self):
        entry = self.one("CREATE OR REPLACE TAG fresh_tag DESCRIPTION = 'x' "
                         "ADD_TO ( VIEWS ( sales.theirs ) COLUMNS () ) REMOVE_FROM ( VIEWS () COLUMNS () )")
        self.assertTrue(entry["needs_yes"])

    # --- production, unknown, no ledger ---

    def test_production_makes_every_change_wait(self):
        entry = self.one("CREATE OR REPLACE VIEW brand_new AS SELECT 1 AS a FROM Dual()", production=True)
        self.assertTrue(entry["needs_yes"])
        self.assertIn("production", entry["why"])

    def test_an_unknown_statement_is_left_to_the_table(self):
        self.assertIsNone(self.one("FROBNICATE all")["needs_yes"])

    def test_without_a_ledger_only_the_input_is_yours(self):
        entry = self.one("ALTER VIEW mine CACHE FULL", ledger=None)
        self.assertEqual((entry["own"], entry["needs_yes"]), (False, True))

    def test_an_unreadable_catalog_is_unknown(self):
        class Blind(FakeCatalog):
            def lookup(self, ref):
                return Found(None)
        entry = self.one("CREATE OR REPLACE VIEW brand_new AS SELECT 1 AS a FROM Dual()", catalog=Blind())
        self.assertIsNone(entry["exists"])
        self.assertTrue(entry["needs_yes"])


if __name__ == "__main__":
    unittest.main()
