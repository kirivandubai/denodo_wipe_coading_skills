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

    def test_a_reader_renamed_or_dropped_earlier_in_the_input(self):
        self.ledger.record_created(SERVER, ObjectRef("view", "sales", "my_report"), internal_id="_r1", source=None,
                                   statement="", now=NOW)
        existing = {**self.existing, ("view", "sales", "my_report"): ("_r1", "derived"),
                    ("view", "sales", "their_report"): ("_x1", "derived")}
        used = {**self.used_by, ("sales", "mine"): [("sales", "my_report"), ("sales", "their_report")]}
        catalog = FakeCatalog(existing, used)
        renamed = self.plan("ALTER VIEW my_report RENAME my_report2", "DROP VIEW their_report",
                            "ALTER VIEW mine CACHE FULL", catalog=catalog)
        self.assertFalse(renamed[2]["needs_yes"], renamed[2]["why"])
        self.assertEqual(renamed[2]["dependents"], [{"database": "sales", "name": "my_report2", "own": True}])

    def test_a_second_declaration_of_one_object_in_the_input_is_named(self):
        entries = self.plan("CREATE OR REPLACE VIEW fresh AS SELECT 1 AS a FROM Dual()",
                            "CREATE OR REPLACE VIEW other AS SELECT 1 AS a FROM Dual()",
                            "CREATE OR REPLACE VIEW fresh AS SELECT 2 AS a FROM Dual()",
                            "CREATE OR REPLACE VIEW theirs AS SELECT 2 AS a FROM Dual()",
                            "CREATE OR REPLACE VIEW theirs AS SELECT 3 AS a FROM Dual()")
        self.assertEqual([e.get("duplicate_of") for e in entries], [None, None, 0, None, 3])
        self.assertFalse(entries[2]["needs_yes"])   # the input's own: a lost definition, not someone's object

    def test_an_association_waits_unless_both_views_are_yours(self):
        theirs = ("CREATE OR REPLACE ASSOCIATION a_x REFERENTIAL CONSTRAINT FOLDER = '/06 - associations' "
                  "ENDPOINT left_role theirs (0,*) ENDPOINT right_role mine PRINCIPAL (1) ADD MAPPING a = b")
        entry = self.one(theirs)
        self.assertEqual((entry["action"], entry["needs_yes"]), ("create", True))
        self.assertIn("sales.theirs", entry["why"])
        mine = self.plan("CREATE OR REPLACE VIEW fresh AS SELECT 1 AS a FROM Dual()",
                         "CREATE OR REPLACE ASSOCIATION a_y ENDPOINT l sales.fresh (0,*) "
                         "ENDPOINT r mine PRINCIPAL (1) ADD MAPPING a = b")
        self.assertFalse(mine[1]["needs_yes"], mine[1]["why"])

    def test_an_alter_of_an_object_that_does_not_exist_yet_still_waits_and_says_why(self):
        # Planned before the file that creates the tag, a waiting ALTER TAG file must not read as
        # the agent's: whose its targets are is decided once the tag exists.
        entry = self.one("ALTER TAG not_yet ADD_TO ( VIEWS () COLUMNS ( sales.theirs.a ) ) "
                         "REMOVE_FROM ( VIEWS () COLUMNS () )")
        self.assertEqual((entry["exists"], entry["needs_yes"]), (False, True))
        self.assertIn("does not exist", entry["why"])
        self.assertTrue(entry["conditions"])

    def test_an_association_over_a_view_that_cannot_be_read_waits(self):
        class Blind(FakeCatalog):
            def lookup(self, ref):
                from denodo_cli.catalog import Found
                return Found(None) if ref.database == "other" else super().lookup(ref)
        entry = self.one("CREATE OR REPLACE ASSOCIATION a_z ENDPOINT l other.their_view (0,*) "
                         "ENDPOINT r mine PRINCIPAL (1) ADD MAPPING a = b",
                         catalog=Blind(self.existing, self.used_by))
        self.assertTrue(entry["needs_yes"], entry["why"])

    def test_re_declaring_your_association_onto_their_views_waits(self):
        entries = self.plan("CREATE OR REPLACE ASSOCIATION a_m ENDPOINT l sales.mine (0,*) "
                            "ENDPOINT r mine_metrics PRINCIPAL (1) ADD MAPPING a = b",
                            "CREATE OR REPLACE ASSOCIATION a_m ENDPOINT l theirs (0,*) "
                            "ENDPOINT r mine PRINCIPAL (1) ADD MAPPING a = b")
        self.assertEqual([e["needs_yes"] for e in entries], [False, True])

    def test_an_identical_re_declaration_is_not_a_duplicate(self):
        entries = self.plan("CREATE OR REPLACE FOLDER '/01 - connectivity'",
                            "CREATE OR REPLACE VIEW fresh AS SELECT 1 AS a FROM Dual()",
                            "CREATE OR REPLACE FOLDER  '/01 - connectivity'")
        self.assertEqual([e.get("duplicate_of") for e in entries], [None, None, None])

    def test_a_drop_or_rename_between_two_declarations_is_not_a_duplicate(self):
        entries = self.plan("CREATE OR REPLACE VIEW fresh AS SELECT 1 AS a FROM Dual()",
                            "DROP VIEW fresh",
                            "CREATE OR REPLACE VIEW fresh AS SELECT 2 AS a FROM Dual()",
                            "ALTER VIEW fresh RENAME fresh2",
                            "CREATE OR REPLACE VIEW fresh AS SELECT 3 AS a FROM Dual()")
        self.assertEqual([e.get("duplicate_of") for e in entries], [None] * 5)

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

    def test_an_incremental_load_into_your_own_remote_table_is_yours(self):
        # Its REFRESH, which empties the table first, is yours already; adding rows to it, or
        # upserting them by key, changes less (T43, from the owner's T34 rule).
        self.assertFalse(self.one("INSERT INTO bv_rt SELECT a FROM theirs")["needs_yes"])
        self.assertFalse(self.one("INSERT INTO bv_rt ON DUPLICATE KEY ( a ) UPDATE SELECT a FROM theirs")["needs_yes"])
        self.assertTrue(self.one("INSERT INTO theirs SELECT a FROM mine")["needs_yes"])
        self.assertTrue(self.one("UPDATE bv_rt SET a = 2")["needs_yes"])

    def test_an_insert_when_the_server_cannot_be_read_waits(self):
        class Blind(FakeCatalog):
            def lookup(self, ref):
                from denodo_cli.catalog import Found
                return Found(None)
        entry = self.one("INSERT INTO bv_rt SELECT a FROM theirs", catalog=Blind(self.existing, self.used_by))
        self.assertTrue(entry["needs_yes"], entry["why"])

    def test_an_entry_without_an_identity_does_not_vouch_for_a_view_of_that_name(self):
        # CREATE REMOTE TABLE (the command) makes no base view: the ledger keeps its name without an
        # internal_id, and a colleague's base view of the same name later is not the session's.
        self.ledger.record_created(SERVER, ObjectRef("view", "sales", "theirs", "remote table"), internal_id=None,
                                   source=None, statement="CREATE REMOTE TABLE theirs INTO ds AS SELECT 1", now=NOW)
        entry = self.one("INSERT INTO theirs SELECT a FROM mine")
        self.assertEqual((entry["own"], entry["needs_yes"]), (False, True))

    def test_replacing_a_remote_table_denodo_cannot_see(self):
        # OR REPLACE drops a table of that name in the source; with no view over it, whose it is
        # is known only when this session made it.
        self.assertTrue(self.one("CREATE OR REPLACE REMOTE TABLE rt_unknown INTO ds AS SELECT a FROM mine")["needs_yes"])
        self.assertFalse(self.one("CREATE REMOTE TABLE rt_unknown INTO ds AS SELECT a FROM mine")["needs_yes"])
        self.ledger.record_created(SERVER, ObjectRef("view", "sales", "rt_made", "remote table"), internal_id=None,
                                   source=None, statement="CREATE REMOTE TABLE rt_made INTO ds AS SELECT 1", now=NOW)
        self.assertFalse(self.one("CREATE OR REPLACE REMOTE TABLE rt_made INTO ds AS SELECT a FROM mine")["needs_yes"])
        entries = self.plan("CREATE REMOTE TABLE rt_new INTO ds AS SELECT a FROM mine",
                            "CREATE OR REPLACE REMOTE TABLE rt_new INTO ds AS SELECT a FROM mine")
        self.assertEqual([e["needs_yes"] for e in entries], [False, False])

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
        for call in ("SELECT * FROM GET_STATS_FOR_FIELDS() WHERE input_view_name = 'mine' AND input_save = true",
                     "SELECT name FROM CHECK_METADATA()", "CALL CHECK_CACHE_NAMES('sales', false)",
                     "SELECT * FROM MIGRATE_DATE_TYPES() WHERE input_database_name = 'sales'",
                     "CALL OPTIMIZE_LAKEHOUSE_ACCELERATOR_CACHE_TABLES()"):
            self.assertTrue(self.one(call)["needs_yes"], call)

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

    def test_ai_over_rows_into_your_own_table_still_waits(self):
        # The load into your own table is yours; the paid requests it sends are the human's number.
        for text in ("INSERT INTO bv_rt SELECT CLASSIFY_AI(a, 'x') AS a FROM theirs",
                     "INSERT INTO m_table SELECT CLASSIFY_AI(a, 'x') AS a FROM theirs",
                     "CREATE OR REPLACE MATERIALIZED TABLE m_table AS SELECT CLASSIFY_AI(a, 'x') AS a FROM theirs"):
            entry = self.one(text)
            self.assertTrue(entry["needs_yes"], text)
            self.assertIn("AI function", entry["why"])

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

    def test_a_grant_to_a_person_through_your_database_waits(self):
        self.ledger.record_created(SERVER, ObjectRef("database", None, "zq_db"), internal_id=None, source=None,
                                   statement="CREATE DATABASE zq_db", now=NOW)
        self.ledger.record_created(SERVER, ObjectRef("role", None, "zq_role"), internal_id=None, source=None,
                                   statement="CREATE ROLE zq_role", now=NOW)
        self.existing[("database", None, "zq_db")] = (None, None)
        self.existing[("role", None, "zq_role")] = (None, None)
        self.assertFalse(self.one("ALTER DATABASE zq_db 'probe'")["needs_yes"])
        self.assertFalse(self.one("ALTER DATABASE zq_db GRANT CONNECT, EXECUTE TO ROLE zq_role")["needs_yes"])
        for text in ("ALTER DATABASE zq_db GRANT CONNECT TO USER kchen",
                     "ALTER DATABASE zq_db REVOKE EXECUTE TO USER kchen",
                     "ALTER DATABASE zq_db GRANT CONNECT TO ROLE analyst",
                     "ALTER DATABASE zq_db GRANT CONNECT TO ROLE anaylst"):
            self.assertTrue(self.one(text)["needs_yes"], text)

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
