import unittest

from denodo_cli.commands.vql import describe, run_statements
from denodo_cli.profiles import Profile
from denodo_cli.transports.base import VqlResult


def profile(**over):
    base = dict(name="dev", host="h", port=9996, database="admin", user="u", password="p",
                production=False, transport="vql_psycopg2", marketplace_url=None, marketplace_server_id=None)
    base.update(over)
    return Profile(**base)


class FakeTransport:
    """Records statements; a statement containing 'BOOM' raises, SELECT returns rows."""

    instances = []

    def __init__(self, profile, database=None):
        self.profile = profile
        self.database = database
        self.executed = []
        self.closed = False
        FakeTransport.instances.append(self)

    def execute(self, statement):
        self.executed.append(statement)
        if "BOOM" in statement:
            raise RuntimeError("ERROR:  boom\nDETAIL:  java.sql.SQLException: Syntax error near 'BOOM'\n")
        if statement.upper().startswith(("SELECT", "DESC")):
            return VqlResult(statement=statement, columns=["n"], rows=[[1], [2], [3]])
        return VqlResult(statement=statement, columns=None, rows=None)

    def close(self):
        self.closed = True


class RunStatementsTest(unittest.TestCase):
    def setUp(self):
        FakeTransport.instances.clear()

    def run_it(self, statements, **kw):
        kw.setdefault("transport_factory", FakeTransport)
        kw.setdefault("max_rows", 100)
        return run_statements(profile(**kw.pop("profile_over", {})), statements, **kw)

    def test_all_statements_run_and_results_are_reported_in_order(self):
        doc, code = self.run_it(["CREATE OR REPLACE FOLDER '/a'", "SELECT 1 FROM DUAL()"])
        self.assertEqual(code, 0)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["command"], "vql run")
        self.assertEqual([s["index"] for s in doc["statements"]], [0, 1])
        self.assertTrue(all(s["ok"] for s in doc["statements"]))
        self.assertIsNone(doc["statements"][0]["rows"])
        self.assertEqual(doc["statements"][1]["rows"], [[1], [2], [3]])
        self.assertEqual(doc["statements"][1]["columns"], ["n"])
        self.assertIsNone(doc["failed_at"])
        self.assertTrue(FakeTransport.instances[0].closed)

    def test_stops_at_first_error_and_reports_where(self):
        doc, code = self.run_it(["SELECT 1 FROM DUAL()", "SELECT BOOM", "SELECT 3 FROM DUAL()"])
        self.assertEqual(code, 1)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["failed_at"], 1)
        self.assertEqual(len(doc["statements"]), 2)
        self.assertEqual(doc["statements"][1]["error"]["message"], "Syntax error near 'BOOM'")
        self.assertEqual(doc["statements"][1]["statement"], "SELECT BOOM")
        self.assertEqual(FakeTransport.instances[0].executed, ["SELECT 1 FROM DUAL()", "SELECT BOOM"])
        self.assertTrue(FakeTransport.instances[0].closed)

    def test_continue_on_error_runs_everything(self):
        doc, code = self.run_it(["SELECT BOOM", "SELECT 3 FROM DUAL()"], continue_on_error=True)
        self.assertEqual(code, 1)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["failed_at"], 0)
        self.assertEqual(len(doc["statements"]), 2)
        self.assertTrue(doc["statements"][1]["ok"])

    def test_destructive_flag_is_reported(self):
        doc, _ = self.run_it(["DROP VIEW v", "CREATE OR REPLACE VIEW v AS SELECT 1 AS a FROM DUAL()"])
        self.assertEqual(doc["statements"][0]["destructive"], "drop")
        self.assertIsNone(doc["statements"][1]["destructive"])

    def test_destructive_on_production_is_refused_before_anything_runs(self):
        doc, code = self.run_it(["CREATE OR REPLACE FOLDER '/a'", "DROP VIEW v"], profile_over={"production": True})
        self.assertEqual(code, 2)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["error"]["kind"], "refused")
        self.assertEqual(doc["error"]["destructive"], [{"index": 1, "kind": "drop", "statement": "DROP VIEW v"}])
        self.assertIn("--allow-destructive", doc["error"]["message"])
        self.assertEqual(FakeTransport.instances, [])

    def test_destructive_on_production_runs_with_allow_flag(self):
        doc, code = self.run_it(["DROP VIEW v"], profile_over={"production": True}, allow_destructive=True)
        self.assertEqual(code, 0)
        self.assertEqual(FakeTransport.instances[0].executed, ["DROP VIEW v"])

    def test_non_destructive_on_production_runs_without_flag(self):
        _, code = self.run_it(["SELECT 1 FROM DUAL()"], profile_over={"production": True})
        self.assertEqual(code, 0)

    def test_max_rows_truncates(self):
        doc, _ = self.run_it(["SELECT 1 FROM DUAL()"], max_rows=2)
        self.assertEqual(doc["statements"][0]["rows"], [[1], [2]])
        self.assertEqual(doc["statements"][0]["row_count"], 3)
        self.assertTrue(doc["statements"][0]["truncated"])

    def test_database_override_reaches_transport(self):
        self.run_it(["SELECT 1 FROM DUAL()"], database="denodo_skills_test")
        self.assertEqual(FakeTransport.instances[0].database, "denodo_skills_test")

    def test_connection_failure_is_reported_as_connection_error(self):
        def failing_factory(profile, database=None):
            raise OSError("could not connect to server")

        doc, code = self.run_it(["SELECT 1 FROM DUAL()"], transport_factory=failing_factory)
        self.assertEqual(code, 1)
        self.assertEqual(doc["error"]["kind"], "connection")
        self.assertIn("could not connect", doc["error"]["message"])

    def test_empty_input_is_a_usage_error(self):
        doc, code = self.run_it([])
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "usage")


class DescribeTest(unittest.TestCase):
    def setUp(self):
        FakeTransport.instances.clear()

    def test_desc_view_by_default(self):
        doc, code = describe(profile(), "bv_orders", transport_factory=FakeTransport, max_rows=100)
        self.assertEqual(code, 0)
        self.assertEqual(doc["command"], "vql desc")
        self.assertEqual(FakeTransport.instances[0].executed, ["DESC VIEW bv_orders"])
        self.assertEqual(doc["rows"], [[1], [2], [3]])

    def test_desc_vql_with_object_kind(self):
        describe(profile(), "ds_crm", kind="datasource df", vql=True, transport_factory=FakeTransport, max_rows=100)
        self.assertEqual(FakeTransport.instances[0].executed, ["DESC VQL DATASOURCE DF ds_crm"])

    def test_desc_error_is_reported(self):
        doc, code = describe(profile(), "BOOM", transport_factory=FakeTransport, max_rows=100)
        self.assertEqual(code, 1)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["error"]["message"], "Syntax error near 'BOOM'")


if __name__ == "__main__":
    unittest.main()
