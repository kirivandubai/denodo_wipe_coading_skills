import unittest

from denodo_cli.catalog import Catalog
from denodo_cli.statements import ObjectRef
from denodo_cli.transports.base import VqlResult

ELEMENT_COLUMNS = ["name", "type", "subtype", "folder", "internal_id"]


class FakeServer:
    """Answers the catalog reads from a dict; records every statement."""

    def __init__(self, databases=("sales",), elements=None, globals_=(), roles=(), users=(), used_by=None,
                 policies=None, fail=()):
        self.databases = list(databases)
        self.elements = elements or {}
        self.globals = list(globals_)
        self.roles, self.users = list(roles), list(users)
        self.used = used_by or {}
        self.policies = policies or {}
        self.fail = fail
        self.executed = []

    def execute(self, statement):
        self.executed.append(statement)
        for marker in self.fail:
            if marker in statement:
                raise RuntimeError(f"ERROR: {marker} failed")
        if "GET_DATABASES" in statement:
            return VqlResult(statement, ["db_name"], [[d] for d in self.databases])
        if "GET_ELEMENTS" in statement and "input_database_name" in statement:
            db = statement.split("input_database_name = '")[1].split("'")[0]
            return VqlResult(statement, ELEMENT_COLUMNS, self.elements.get(db, []))
        if "GET_ELEMENTS" in statement:
            return VqlResult(statement, ELEMENT_COLUMNS, self.globals)
        if statement.startswith("LIST ROLES"):
            return VqlResult(statement, ["name", "description", "roles"], [[r, None, None] for r in self.roles])
        if statement.startswith("LIST USERS"):
            return VqlResult(statement, ["name", "description", "admin"], [[u, None, False] for u in self.users])
        if "USED_BY" in statement:
            view = statement.split("input_view_name = '")[1].split("'")[0]
            return VqlResult(statement, ["used_by_database_name", "used_by_name", "depth"], self.used.get(view, []))
        if statement.startswith("DESC VQL GLOBAL_SECURITY_POLICY"):
            name = statement.split()[-1]
            return VqlResult(statement, ["result"], [[self.policies[name]]])
        raise AssertionError(f"unexpected statement {statement}")


def rows(*elements):
    return [list(e) for e in elements]


class CatalogTest(unittest.TestCase):
    def test_an_element_is_found_with_its_id_and_subtype(self):
        server = FakeServer(elements={"sales": rows(("iv_orders", "view", "derived", "/02", "_a1"))})
        catalog = Catalog(server)
        found = catalog.lookup(ObjectRef("view", "sales", "IV_ORDERS"))
        self.assertEqual((found.exists, found.internal_id, found.subtype), (True, "_a1", "derived"))
        self.assertFalse(catalog.lookup(ObjectRef("view", "sales", "nope")).exists)

    def test_each_database_is_read_once(self):
        server = FakeServer(elements={"sales": rows(("a", "view", "derived", "/", "_1"))})
        catalog = Catalog(server)
        catalog.lookup(ObjectRef("view", "sales", "a"))
        catalog.lookup(ObjectRef("view", "sales", "b"))
        self.assertEqual(sum("input_database_name" in s for s in server.executed), 1)

    def test_a_missing_database_has_no_elements_and_is_not_queried(self):
        server = FakeServer(databases=["sales"])
        catalog = Catalog(server)
        self.assertFalse(catalog.lookup(ObjectRef("view", "newdb", "v")).exists)
        self.assertFalse(catalog.lookup(ObjectRef("database", None, "newdb")).exists)
        self.assertTrue(catalog.lookup(ObjectRef("database", None, "SALES")).exists)
        self.assertFalse(any("newdb" in s for s in server.executed))

    def test_folders_are_found_by_path(self):
        server = FakeServer(elements={"sales": rows(("02 - integration", "folder", "", "/", "17"),
                                                    ("customer", "folder", "", "/03 - business entities", "18"))})
        catalog = Catalog(server)
        self.assertTrue(catalog.lookup(ObjectRef("folder", "sales", "/02 - integration")).exists)
        self.assertTrue(catalog.lookup(ObjectRef("folder", "sales", "/03 - business entities/customer")).exists)

    def test_tags_policies_roles_and_users(self):
        server = FakeServer(globals_=rows(("pii", "tag", "", None, "pii_1"), ("m", "globalSecurityPolicy", "", None, "m_1")),
                            roles=["analyst"], users=["mlee"])
        catalog = Catalog(server)
        self.assertEqual(catalog.lookup(ObjectRef("tag", None, "PII")).internal_id, "pii_1")
        self.assertTrue(catalog.lookup(ObjectRef("globalSecurityPolicy", None, "m")).exists)
        self.assertTrue(catalog.lookup(ObjectRef("role", None, "Analyst")).exists)
        self.assertTrue(catalog.lookup(ObjectRef("user", None, "mlee")).exists)
        self.assertFalse(catalog.lookup(ObjectRef("role", None, "nobody")).exists)

    def test_a_failed_read_is_unknown_not_absent(self):
        server = FakeServer(fail=("GET_ELEMENTS",))
        catalog = Catalog(server)
        self.assertIsNone(catalog.lookup(ObjectRef("view", "sales", "v")).exists)
        self.assertTrue(catalog.errors)

    def test_used_by(self):
        server = FakeServer(used_by={"iv_orders": [["sales", "dashboard", 1], ["other", "report", 2]]})
        self.assertEqual(Catalog(server).used_by("sales", "iv_orders"), [("sales", "dashboard"), ("other", "report")])

    def test_a_tag_a_policy_names(self):
        server = FakeServer(globals_=rows(("p1", "globalSecurityPolicy", "", None, "p1_1")),
                            policies={"p1": "CREATE GLOBAL_SECURITY_POLICY p1 ELEMENTS ( COLUMNS TAGGED ANY ( pii ) )"})
        catalog = Catalog(server)
        self.assertEqual(catalog.policies_naming("pii"), ["p1"])
        self.assertEqual(catalog.policies_naming("pii_other"), [])

    def test_a_quote_in_a_name_does_not_break_the_query(self):
        server = FakeServer(databases=["o'brien"])
        Catalog(server).lookup(ObjectRef("view", "o'brien", "v"))
        self.assertIn("'o''brien'", server.executed[-1])


if __name__ == "__main__":
    unittest.main()
