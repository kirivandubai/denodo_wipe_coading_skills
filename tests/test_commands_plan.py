import datetime as dt
import itertools
import tempfile
import unittest
from pathlib import Path

from denodo_cli.commands.api import api_call
from denodo_cli.commands.plan import list_ledger, plan_input
from denodo_cli.commands.vql import run_statements
from denodo_cli.ledger import Ledger
from denodo_cli.profiles import Profile
from denodo_cli.statements import ObjectRef, parse_statement
from denodo_cli.transports.base import HttpResult, VqlResult

NOW = dt.datetime(2026, 10, 6, 9, 0, tzinfo=dt.timezone.utc)
SERVER = "h:9996"
_ids = itertools.count(1)


def profile(**over):
    base = dict(name="dev", host="h", port=9996, database="admin", user="u", password="p", production=False,
                transport="vql_psycopg2", marketplace_url="http://m/denodo-data-catalog", marketplace_server_id=None)
    base.update(over)
    return Profile(**base)


class LiveLikeServer:
    """A server whose catalog follows the CREATE / DROP / RENAME it executes; one instance per test."""

    def __init__(self, databases=("admin", "sales"), elements=None):
        self.databases = {d.lower() for d in databases}
        self.elements = {k: dict(v) for k, v in (elements or {}).items()}   # db -> {(type, name): id}
        self.executed = []
        self.database = "admin"

    def __call__(self, profile, database=None):   # the transport factory
        self.database = database or profile.database
        return self

    def close(self):
        pass

    def execute(self, statement):
        self.executed.append(statement)
        if "BOOM" in statement:
            raise RuntimeError("ERROR: boom")
        if "GET_DATABASES" in statement:
            return VqlResult(statement, ["db_name"], [[d] for d in sorted(self.databases)])
        if "GET_ELEMENTS" in statement and "input_database_name" in statement:
            db = statement.split("input_database_name = '")[1].split("'")[0]
            rows = [[name, etype, "", "/", iid] for (etype, name), iid in self.elements.get(db, {}).items()]
            return VqlResult(statement, ["name", "type", "subtype", "folder", "internal_id"], rows)
        if "GET_ELEMENTS" in statement:
            return VqlResult(statement, ["name", "type", "subtype", "folder", "internal_id"], [])
        if "USED_BY" in statement:
            return VqlResult(statement, ["used_by_database_name", "used_by_name", "depth"], [])
        st = parse_statement(statement, self.database)
        if st.connect:
            self.database = st.connect
        elif st.action == "create" and st.obj is not None:
            if st.obj.type == "database":
                self.databases.add(st.obj.name.lower())
            else:
                table = self.elements.setdefault(st.obj.database, {})
                table.setdefault((st.obj.type, st.obj.name.lower()), f"_id{next(_ids)}")
        elif st.action == "drop" and st.obj is not None:
            self.elements.get(st.obj.database, {}).pop((st.obj.type, st.obj.name.lower()), None)
        elif st.action == "rename" and st.obj is not None:
            table = self.elements.get(st.obj.database, {})
            iid = table.pop((st.obj.type, st.obj.name.lower()), None)
            if iid:
                table[(st.obj.type, st.new_name.lower())] = iid
        if statement.upper().startswith("SELECT"):
            return VqlResult(statement, ["n"], [[1]])
        return VqlResult(statement, None, None)


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name), "s1")
        self.ledger.touch(NOW)

    def tearDown(self):
        self.tmp.cleanup()


class RunRecordsTest(LedgerCase):
    def run_it(self, server, statements, **kw):
        return run_statements(profile(), statements, transport_factory=server, max_rows=100, database="sales",
                              ledger=self.ledger, source="model/v.vql", **kw)

    def test_new_objects_are_recorded_with_their_ids(self):
        server = LiveLikeServer()
        doc, code = self.run_it(server, ["CREATE OR REPLACE VIEW fresh AS SELECT 1 AS a FROM Dual()",
                                         "SELECT * FROM fresh"])
        self.assertEqual(code, 0)
        entry = self.ledger.find(SERVER, ObjectRef("view", "sales", "fresh"))
        self.assertEqual(entry["internal_id"], server.elements["sales"][("view", "fresh")])
        self.assertEqual(entry["source"], "model/v.vql")
        self.assertEqual(doc["ledger"]["recorded"], ["sales.fresh"])

    def test_an_object_that_existed_is_not_recorded(self):
        server = LiveLikeServer(elements={"sales": {("view", "theirs"): "_t1"}})
        doc, _ = self.run_it(server, ["CREATE OR REPLACE VIEW theirs AS SELECT 2 AS a FROM Dual()"])
        self.assertIsNone(self.ledger.find(SERVER, ObjectRef("view", "sales", "theirs")))
        self.assertEqual(doc["ledger"]["recorded"], [])

    def test_drops_and_renames_follow(self):
        server = LiveLikeServer()
        self.run_it(server, ["CREATE OR REPLACE VIEW a1 AS SELECT 1 AS a FROM Dual()",
                             "CREATE OR REPLACE VIEW a2 AS SELECT 1 AS a FROM Dual()"])
        doc, _ = self.run_it(server, ["ALTER VIEW a1 RENAME b1", "DROP VIEW a2"])
        self.assertIsNotNone(self.ledger.find(SERVER, ObjectRef("view", "sales", "b1")))
        self.assertIsNone(self.ledger.find(SERVER, ObjectRef("view", "sales", "a2")))
        self.assertEqual(doc["ledger"]["renamed"], ["sales.a1 → b1"])
        self.assertEqual(doc["ledger"]["dropped"], ["sales.a2"])

    def test_only_statements_that_ran_are_recorded(self):
        server = LiveLikeServer()
        self.run_it(server, ["CREATE OR REPLACE VIEW ok1 AS SELECT 1 AS a FROM Dual()", "SELECT BOOM",
                             "CREATE OR REPLACE VIEW never AS SELECT 1 AS a FROM Dual()"])
        self.assertIsNotNone(self.ledger.find(SERVER, ObjectRef("view", "sales", "ok1")))
        self.assertIsNone(self.ledger.find(SERVER, ObjectRef("view", "sales", "never")))

    def test_a_new_database_and_what_is_inside_it(self):
        server = LiveLikeServer()
        self.run_it(server, ["CREATE OR REPLACE DATABASE mart 'm'", "CONNECT DATABASE mart",
                             "CREATE OR REPLACE VIEW v AS SELECT 1 AS a FROM Dual()"])
        self.assertIsNotNone(self.ledger.find(SERVER, ObjectRef("database", None, "mart")))
        self.assertIsNotNone(self.ledger.find(SERVER, ObjectRef("view", "mart", "v")))

    def test_dropping_a_database_the_session_did_not_create_takes_its_objects_along(self):
        server = LiveLikeServer(databases=("admin", "sales", "shared"))
        self.run_it(server, ["CONNECT DATABASE shared", "CREATE OR REPLACE VIEW mine AS SELECT 1 AS a FROM Dual()"])
        self.assertIsNotNone(self.ledger.find(SERVER, ObjectRef("view", "shared", "mine")))
        doc, _ = self.run_it(server, ["DROP DATABASE shared CASCADE"])
        self.assertIsNone(self.ledger.find(SERVER, ObjectRef("view", "shared", "mine")))
        self.assertEqual(doc["ledger"]["dropped"], ["shared"])

    def test_reads_cost_no_catalog_query(self):
        server = LiveLikeServer()
        doc, _ = self.run_it(server, ["SELECT 1 FROM Dual()"])
        self.assertEqual(server.executed, ["SELECT 1 FROM Dual()"])
        self.assertNotIn("ledger", doc)

    def test_without_a_ledger_nothing_is_read_or_written(self):
        server = LiveLikeServer()
        doc, _ = run_statements(profile(), ["CREATE OR REPLACE VIEW x AS SELECT 1 AS a FROM Dual()"],
                                transport_factory=server, max_rows=100, database="sales")
        self.assertEqual(len(server.executed), 1)
        self.assertNotIn("ledger", doc)

    def test_a_remote_table_procedure_records_its_base_view(self):
        server = LiveLikeServer()
        self.run_it(server, ["SELECT phase FROM CREATE_REMOTE_TABLE() WHERE remote_table_name = 'h' "
                             "AND replace_remote_table_if_exist = false AND base_view_name = 'bv_h' "
                             "AND base_view_database_name = 'sales'"])
        entry = self.ledger.find(SERVER, ObjectRef("view", "sales", "bv_h"))
        self.assertEqual(entry["kind"], "remote table")


class PlanCommandTest(LedgerCase):
    def test_plan_reports_each_statement_and_executes_nothing(self):
        server = LiveLikeServer(elements={"sales": {("view", "theirs"): "_t1"}})
        doc, code = plan_input(profile(), ["CREATE OR REPLACE VIEW fresh AS SELECT 1 AS a FROM Dual()",
                                           "CREATE OR REPLACE VIEW theirs AS SELECT 2 AS a FROM Dual()",
                                           "DROP VIEW fresh"],
                               transport_factory=server, database="sales", source=None, ledger=self.ledger,
                               session_source="CLAUDE_CODE_SESSION_ID")
        self.assertEqual(code, 0)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["command"], "vql plan")
        self.assertEqual([s["needs_yes"] for s in doc["statements"]], [False, True, True])
        self.assertEqual(doc["needs_yes"], [1, 2])
        self.assertEqual(doc["executed"], 0)
        self.assertEqual(doc["session"]["id"], "s1")
        self.assertFalse(any(s.startswith(("CREATE", "DROP")) for s in server.executed))
        # What the yes is, where the agent decides (T42: an agent read "waits for the human's yes" and
        # took the request that asked for the DROP as that yes).
        self.assertIn("not that yes", doc["yes"])
        # ... without contradicting the table's own exceptions (review of T42): naming a view to be
        # made visible to an agent is the yes for its tag; a condition can name an exception.
        self.assertIn("visible to an agent", doc["yes"])
        self.assertIn("conditions", doc["yes"])

    def test_a_plan_that_waits_for_nothing_says_nothing_about_the_yes(self):
        doc, _ = plan_input(profile(), ["CREATE OR REPLACE VIEW fresh AS SELECT 1 AS a FROM Dual()"],
                            transport_factory=LiveLikeServer(), database="sales", source=None, ledger=self.ledger,
                            session_source="CLAUDE_CODE_SESSION_ID")
        self.assertEqual(doc["needs_yes"], [])
        self.assertNotIn("yes", doc)

    def test_a_long_input_is_summarised_and_its_duplicates_listed(self):
        server = LiveLikeServer(elements={"sales": {("view", "theirs"): "_t1"}})
        doc, _ = plan_input(profile(), ["CONNECT DATABASE sales",
                                        "CREATE OR REPLACE VIEW a AS SELECT 1 AS x FROM Dual()",
                                        "CREATE OR REPLACE VIEW b AS SELECT 1 AS x FROM Dual()",
                                        "CREATE OR REPLACE VIEW a AS SELECT 2 AS x FROM Dual()",
                                        "CREATE OR REPLACE VIEW theirs AS SELECT 2 AS x FROM Dual()"],
                            transport_factory=server, database="sales", source=None, ledger=self.ledger,
                            session_source="CLAUDE_CODE_SESSION_ID")
        self.assertEqual(doc["actions"], {"session": 1, "create": 2, "replace": 2})
        self.assertEqual(doc["duplicates"], [{"object": {"type": "view", "database": "sales", "name": "a",
                                                         "kind": "derived view"},
                                              "statements": [1, 3]}])
        self.assertEqual(doc["needs_yes"], [4])

    def test_without_a_session_the_answer_says_so(self):
        doc, code = plan_input(profile(), ["SELECT 1 FROM Dual()"], transport_factory=LiveLikeServer(),
                               database="sales", source=None, ledger=None, session_source=None)
        self.assertEqual(code, 0)
        self.assertIsNone(doc["session"])
        self.assertIn("DENODO_SESSION", doc["session_note"])

    def test_a_server_that_cannot_be_reached(self):
        def broken(profile, database=None):
            raise RuntimeError("connection refused")
        doc, code = plan_input(profile(), ["SELECT 1 FROM Dual()"], transport_factory=broken, database=None,
                               source=None, ledger=None, session_source=None)
        self.assertEqual((code, doc["error"]["kind"]), (1, "connection"))

    def test_the_ledger_lists_and_rechecks(self):
        server = LiveLikeServer()
        run_statements(profile(), ["CREATE OR REPLACE VIEW keep AS SELECT 1 AS a FROM Dual()",
                                   "CREATE OR REPLACE VIEW gone AS SELECT 1 AS a FROM Dual()"],
                       transport_factory=server, max_rows=100, database="sales", ledger=self.ledger, source=None)
        server.elements["sales"].pop(("view", "gone"))       # dropped by someone else
        doc, code = list_ledger(profile(), transport_factory=server, ledger=self.ledger,
                                session_source="CLAUDE_CODE_SESSION_ID")
        self.assertEqual(code, 0)
        states = {o["name"]: o["state"] for o in doc["objects"]}
        self.assertEqual(states, {"keep": "present", "gone": "missing"})
        self.assertNotIn("status", doc["objects"][0])     # one field says where an object stands
        self.assertEqual(doc["states"], {"present": 1, "missing": 1})
        self.assertEqual(doc["session"]["objects"], 2)


class FakeRest:
    def __init__(self, changes):
        self.changes = changes
        self.calls = []

    def __call__(self, profile, server="marketplace"):
        return self

    def call(self, method, path, **kw):
        self.calls.append((method, path))
        half = path.split("/")[-2]
        return HttpResult(200, self.changes.get(half, {}))


class ApiPlanTest(LedgerCase):
    SYNC = "/public/api/element-management/VIEWS/synchronize"

    def setUp(self):
        super().setUp()
        for ref in (ObjectRef("database", None, "mart"), ObjectRef("view", "mart", "v1"),
                    ObjectRef("view", "mart", "old_name")):
            self.ledger.record_created(SERVER, ref, internal_id=None, source=None, statement="", now=NOW)
        self.ledger.record_renamed(SERVER, ObjectRef("view", "mart", "old_name"), "new_name", now=NOW)

    def plan(self, changes, body=None, **kw):
        rest = FakeRest(changes)
        body = body if body is not None else {"proceedWithConflicts": "SERVER_WITH_LOCAL_CHANGES"}
        doc, code = api_call(profile(**kw), "post", self.SYNC, transport_factory=rest, json_body=body,
                             plan=True, ledger=self.ledger)
        return doc, code, rest

    def test_a_radius_of_your_own_objects(self):
        changes = {"DATABASES": {"serverElements": [{"databaseName": "mart"}]},
                   "VIEWS": {"serverElements": [{"databaseName": "mart", "elementName": "v1"},
                                                {"databaseName": "mart", "elementName": "new_name"}],
                             "localElements": [{"databaseName": "mart", "elementName": "old_name"}],
                             "modifiedElements": [{"databaseName": "x", "elementName": "y", "reason": "DESCRIPTION"}]}}
        doc, code, rest = self.plan(changes)
        self.assertEqual(code, 0)
        self.assertFalse(doc["sent"])
        self.assertFalse(doc["needs_yes"])
        self.assertTrue(doc["radius"]["own"])
        self.assertEqual([c[0] for c in rest.calls], ["GET", "GET"])
        self.assertTrue(doc["conditions"])
        self.assertNotIn("yes", doc)

    def test_one_entry_you_did_not_create(self):
        changes = {"VIEWS": {"serverElements": [{"databaseName": "teamdb", "elementName": "wip"}]}}
        doc, _, _ = self.plan(changes)
        self.assertTrue(doc["needs_yes"])
        self.assertIn("not that yes", doc["yes"])
        self.assertEqual(doc["radius"]["not_own"], [{"half": "VIEWS", "list": "serverElements",
                                                     "databaseName": "teamdb", "elementName": "wip"}])

    def test_the_conflict_mode_and_production_decide_too(self):
        empty = {}
        self.assertTrue(self.plan(empty, body={"proceedWithConflicts": "SERVER"})[0]["needs_yes"])
        self.assertTrue(self.plan(empty, production=True)[0]["needs_yes"])

    def test_other_calls(self):
        rest = FakeRest({})
        get, _ = api_call(profile(), "get", "/public/api/tags", transport_factory=rest, plan=True, ledger=None)
        delete, _ = api_call(profile(), "delete", "/public/api/tags/5", transport_factory=rest, plan=True, ledger=None)
        post, _ = api_call(profile(), "post", "/public/api/tags", transport_factory=rest, json_body={"name": "x"},
                           plan=True, ledger=None)
        self.assertEqual((get["needs_yes"], delete["needs_yes"], post["needs_yes"]), (False, True, None))
        self.assertEqual(rest.calls, [])

    def test_an_unassignment_is_not_a_deletion_of_the_object(self):
        rest = FakeRest({})
        for path in ("/public/api/tags/648/views/7757", "/public/api/category-management/categories/365/views/7757",
                     "/public/api/tags/648/views"):
            doc, _ = api_call(profile(), "delete", path, transport_factory=rest, plan=True, ledger=None)
            self.assertTrue(doc["needs_yes"])
            self.assertIn("one assignment", doc["why"])
            self.assertNotIn("everything attached", doc["why"])
        tag, _ = api_call(profile(), "delete", "/public/api/tags/648", transport_factory=rest, plan=True, ledger=None)
        self.assertIn("everything attached", tag["why"])


if __name__ == "__main__":
    unittest.main()
