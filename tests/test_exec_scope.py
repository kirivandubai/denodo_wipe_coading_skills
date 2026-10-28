"""The shared tests of the rule of scope: denodo_exec's own splitter held to denodo_cli's on a
corpus, and `judge` on plans written by hand and on plans denodo_cli's planner makes."""

import re
import unittest
from pathlib import Path

from denodo_cli.vql_split import split_statements
from denodo_exec import offline
from denodo_exec.errors import Refused
from denodo_exec.scope import Scope, Wording, judge, refusal, why_not
from denodo_exec.vql import split_vql
from tests.exec_helpers import DB, entry, nothing

REPO = Path(__file__).resolve().parents[1]
FENCE = re.compile(r"^```(?:sql|vql)\s*$(.*?)^```\s*$", re.M | re.S)
PROCEDURE = re.compile(r"\bVQL\s+PROCEDURE\b", re.I)

# What a splitter is easy to get wrong: quotes doubled and left open, comments of every kind
# holding a semicolon, a comment marker inside a literal, empty statements.
TRICKY = [
    "SELECT 'a;b' AS x FROM dual(); SELECT 2 FROM dual()",
    "SELECT 'it''s; fine' FROM dual();",
    'SELECT "we;ird", "q""uote;d" FROM v;',
    "-- head; er\n# Generated; by\nSELECT 1 FROM dual(); -- tail;\nSELECT 2;",
    "/* a; block */ CREATE VIEW v AS SELECT 1; /* open; comment",
    "SELECT '-- not a comment;' FROM dual(); SELECT '/* nor; this */' FROM dual();",
    "SELECT '# nor; this' FROM dual();;;\n;\nSELECT 3",
    "SELECT 'left open; to the end",
    "CREATE VIEW a AS SELECT ';' AS s FROM b; -- x;\n/* c; */ DROP VIEW \"q;\";\n",
    "SELECT 1 -- a comment at the end, no newline",
    "SELECT a-b, c/d, e*f FROM g; SELECT '/' FROM h",
]


def corpus() -> list[str]:
    """Every VQL block of the skills, but a procedure's, and the tricky texts."""
    found = []
    for path in sorted((REPO / "skills").rglob("*.md")):
        for block in FENCE.findall(path.read_text(encoding="utf-8")):
            if not PROCEDURE.search(block):
                found.append(block)
    return found + TRICKY


class SplitTest(unittest.TestCase):
    def test_the_splitter_ignores_semicolons_in_quotes_and_comments(self):
        text = ("# header; comment\nCREATE VIEW a AS SELECT ';' AS s FROM b; -- x;\n"
                "/* c; */ DROP VIEW \"q;\";\n")
        self.assertEqual(split_vql(text), ["CREATE VIEW a AS SELECT ';' AS s FROM b",
                                           'DROP VIEW "q;"'])

    def test_the_two_splitters_find_the_same_statements_on_the_corpus(self):
        # The plan's alignment check compares the two: they must agree wherever a workspace's
        # file can stand, or a legal file is refused -- and they must stay two, or the check
        # compares a splitter with itself.
        texts = corpus()
        self.assertGreater(len(texts), 100)
        for text in texts:
            with self.subTest(text=text[:80]):
                self.assertEqual(split_vql(text), split_statements(text))

    def test_a_procedure_splits_apart_and_its_file_is_refused(self):
        text = ("CREATE OR REPLACE VQL PROCEDURE p () AS (\n  n INT;\n) BEGIN\n"
                "  n := 1;\nEND;\nSELECT 1 FROM dual();")
        self.assertEqual(len(split_statements(text)), 2)
        self.assertGreater(len(split_vql(text)), 2)
        plan = {"statements": offline.plan(text, DB, databases=[DB])}
        with self.assertRaisesRegex(Refused, "no VQL procedure"):
            judge(plan, text, scope=Scope(DB), live={})

    def test_the_layer_does_not_borrow_denodo_cli_s_splitter(self):
        source = (REPO / "scripts" / "denodo_exec" / "vql.py").read_text(encoding="utf-8")
        imports = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
        self.assertEqual(imports, ["from __future__ import annotations"])


WORDS = Wording(owner="OWNER: ", unit="demo", ledger="its ledger")
# (plan entry, statement, a fragment of why -- None when allowed), on a scope of a database alone.
DATABASE_ONLY = [
    (entry(0, "create", "view", "dv_customers"), "CREATE VIEW dv_customers AS SELECT 1", None),
    (entry(0, "create", "view", "dv_x", database="admin"),
     "CREATE VIEW admin.dv_x AS SELECT 1", "outside the demo's database"),
    (entry(0, "replace", "view", "customers", exists=True),
     "CREATE OR REPLACE VIEW customers AS SELECT 1", "not this demo's"),
    (entry(0, "create", "view", "customers", exists=True),
     "CREATE OR REPLACE VIEW customers AS SELECT 1", "exists and is not this demo's"),
    (entry(0, "drop", "view", "customers", exists=True), "DROP VIEW customers",
     "not this demo's: it is in no line of its ledger"),
    (entry(0, "drop", "view", "dv_gone", exists=False), "DROP VIEW IF EXISTS dv_gone", None),
    (entry(0, "drop", "database", "sales", exists=True), "DROP DATABASE sales",
     "database is the owner's"),
    (entry(0, "create", "user", "bob", destructive="security"), "CREATE USER bob 'x'",
     "users, roles"),
    (entry(0, "create", "folder", "/views"), "CREATE FOLDER '/views'", None),
    (entry(0, "read", None, None), "SELECT * FROM customers", None),
    ({**entry(0, "read", None, None), "destructive": "cache"}, "SELECT 1 FROM v", "a cache load"),
    ({**entry(0, "read", None, None), "destructive": "write"}, "SELECT 1 FROM v",
     "a write into a source"),
    (entry(0, "insert", "view", "dv_x"), "INSERT INTO dv_x VALUES (1)", "owner's to run"),
    (entry(0, "create", "view", "dv_foo", exists=None), "CREATE OR REPLACE VIEW dv_foo AS ...",
     "could not say whether it exists"),
    (entry(0, "drop", "view", "dv_a", exists=True), "DROP VIEW dv_a CASCADE", "CASCADE would drop"),
]
FOLDERED = Scope(DB, folder="/app", prefix="app_")
# The same rule with a folder and a prefix.
IN_FOLDER = [
    (entry(0, "create", "view", "app_a"), "CREATE VIEW app_a FOLDER = '/app/x' AS SELECT 1", None),
    (entry(0, "create", "view", "dv_a"), "CREATE VIEW dv_a FOLDER = '/app' AS SELECT 1",
     "lacks the demo's prefix app_"),
    (entry(0, "create", "view", "app_a"), "CREATE VIEW app_a AS SELECT 1",
     "has no FOLDER = '/app/...'"),
    (entry(0, "create", "view", "app_a"), "CREATE VIEW app_a FOLDER = '/apps' AS SELECT 1",
     "folder /apps is outside the demo's folder /app"),
    (entry(0, "create", "folder", "/app/sub"), "CREATE FOLDER '/app/sub'", None),
    (entry(0, "create", "folder", "/other"), "CREATE FOLDER '/other'",
     "folder /other is outside the demo's folder /app"),
    (entry(0, "replace", "view", "app_old", exists=True),
     "CREATE OR REPLACE VIEW app_old FOLDER = '/elsewhere' AS SELECT 1",
     "folder /elsewhere is outside"),
]


class JudgeTest(unittest.TestCase):
    def check(self, cases, scope):
        for planned, statement, why in cases:
            with self.subTest(statement=statement):
                [judged] = judge({"statements": [planned]}, statement + ";", scope=scope,
                                 live={}, rule=nothing, wording=WORDS)
                self.assertIs(judged["allowed"], why is None, judged["why"])
                if why:
                    self.assertIn(why, judged["why"])

    def test_the_rule_of_scope_on_a_database(self):
        self.check(DATABASE_ONLY, Scope(DB))

    def test_the_rule_of_scope_on_a_folder_and_a_prefix(self):
        self.check(IN_FOLDER, FOLDERED)

    def test_a_folder_and_a_prefix_only_narrow_the_scope_of_a_database(self):
        # One rule for both kinds of workspace: a folder and a prefix add refusals of their own
        # and never lift or reword a refusal of the database's rule.
        narrowing = ("lacks the demo's prefix", "has no FOLDER =", "is outside the demo's folder")
        for planned, statement, _ in DATABASE_ONLY:
            with self.subTest(statement=statement):
                wide = why_not(planned, statement, Scope(DB), {}, WORDS)
                narrow = why_not(planned, statement, FOLDERED, {}, WORDS)
                if wide is not None:
                    self.assertEqual(narrow, wide)
                elif narrow is not None:
                    self.assertTrue(any(word in narrow for word in narrowing), narrow)
        # Both branches are taken: the table holds allowed and refused cases, and the folder
        # refuses at least one statement the database alone allows.
        self.assertTrue(any(why_not(p, s, Scope(DB), {}, WORDS) is None
                            and why_not(p, s, FOLDERED, {}, WORDS) is not None
                            for p, s, _ in DATABASE_ONLY))

    def test_an_object_of_the_ledger_may_be_replaced_and_dropped(self):
        live = {("view", DB, "dv_customers"): {}}
        for planned, statement in ((entry(0, "replace", "view", "DV_Customers", exists=True),
                                    "CREATE OR REPLACE VIEW DV_Customers AS ..."),
                                   (entry(0, "drop", "view", "dv_customers", exists=True),
                                    "DROP VIEW dv_customers")):
            [judged] = judge({"statements": [planned]}, statement, scope=Scope(DB), live=live)
            self.assertTrue(judged["allowed"], judged["why"])

    def test_cascade_is_refused_on_a_drop_even_of_ones_own(self):
        live = {("view", DB, "dv_a"): {}}
        for statement in ("DROP VIEW dv_a CASCADE", "drop view dv_a cascade"):
            [judged] = judge({"statements": [entry(0, "drop", "view", "dv_a", exists=True,
                                                   database=DB)]}, statement, scope=Scope(DB),
                             live=live)
            self.assertFalse(judged["allowed"])
            self.assertIn("CASCADE", judged["why"])

    def test_a_plan_that_does_not_align_with_the_file_is_refused(self):
        with self.assertRaisesRegex(Refused, "^OWNER: the file splits into 2 statements"):
            judge({"statements": [entry(0, "read", None, None)]}, "SELECT 1; SELECT 2",
                  scope=Scope(DB), live={}, wording=WORDS)

    def test_the_agents_rule_is_asked_for_every_statement_and_its_refusal_kept(self):
        asked = []

        def refusing(planned, statement):
            asked.append(statement)
            return "a road out"

        plan = {"statements": [entry(0, "create", "view", "dv_x"),
                               entry(1, "drop", "database", "sales", exists=True)]}
        judged = judge(plan, "CREATE VIEW dv_x AS SELECT 1; DROP DATABASE sales",
                       scope=Scope(DB), live={}, rule=refusing, wording=WORDS)
        self.assertEqual(asked, ["CREATE VIEW dv_x AS SELECT 1", "DROP DATABASE sales"])
        # The rule of scope speaks first; the agent's rule where the scope has nothing to say.
        self.assertEqual([row["why"] for row in judged],
                         ["a road out", "a database is the owner's to change"])
        self.assertEqual(refusal(judged, WORDS), "OWNER: #0 ... -- a road out; "
                         "#1 ... -- a database is the owner's to change")
        self.assertIsNone(refusal([], WORDS))

    def test_the_default_wording_is_english_and_generic(self):
        [judged] = judge({"statements": [entry(0, "drop", "view", "v", exists=True)]},
                         "DROP VIEW v", scope=Scope(DB), live={})
        self.assertEqual(judged["why"], "view v is not this workspace's: it is in no line of "
                                        "its ledger")
        self.assertTrue(refusal([judged]).startswith("needs the owner's word: #0"))


class PlannedTest(unittest.TestCase):
    """Plans denodo_cli's own planner makes: what the rule reads is the planner's contract."""

    def judged(self, text, *, objects=(), live=None, scope=None):
        plan = {"statements": offline.plan(text, DB, objects=objects, databases=[DB, "admin"])}
        return judge(plan, text, scope=scope or Scope(DB), live=live or {}, wording=WORDS)

    def test_a_new_view_and_folder_are_the_workspaces_to_make(self):
        rows = self.judged("CREATE FOLDER '/views';\n"
                           "CREATE VIEW dv_a FOLDER = '/views' AS SELECT 1 AS n FROM dual();")
        self.assertEqual([row["allowed"] for row in rows], [True, True], rows)

    def test_someone_elses_existing_view_is_not_replaced(self):
        [row] = self.judged("CREATE OR REPLACE VIEW customers AS SELECT 1 AS n FROM dual();",
                            objects={("view", DB, "customers")})
        self.assertFalse(row["allowed"])
        self.assertIn("exists and is not this demo's", row["why"])

    def test_ones_own_view_is_replaced_and_dropped(self):
        live = {("view", DB, "dv_a"): {}}
        rows = self.judged("CREATE OR REPLACE VIEW dv_a AS SELECT 1 AS n FROM dual();\n"
                           "DROP VIEW dv_a;", objects={("view", DB, "dv_a")}, live=live)
        self.assertEqual([row["allowed"] for row in rows], [True, True], rows)

    def test_another_database_users_and_a_database_are_the_owners(self):
        rows = self.judged("CREATE VIEW admin.dv_b AS SELECT 1 AS n FROM dual();\n"
                           "CREATE USER bob 'x';\nDROP DATABASE admin;")
        self.assertEqual([row["allowed"] for row in rows], [False, False, False], rows)

    def test_a_read_is_free_and_a_cache_load_is_not(self):
        rows = self.judged("SELECT * FROM customers;\n"
                           "SELECT * FROM customers CONTEXT ('cache_preload' = 'true');")
        self.assertTrue(rows[0]["allowed"], rows)
        self.assertFalse(rows[1]["allowed"], rows)

    def test_a_folder_scope_holds_on_planned_statements(self):
        rows = self.judged("CREATE VIEW app_a FOLDER = '/app' AS SELECT 1 AS n FROM dual();\n"
                           "CREATE VIEW app_b AS SELECT 1 AS n FROM dual();", scope=FOLDERED)
        self.assertEqual([row["allowed"] for row in rows], [True, False], rows)


if __name__ == "__main__":
    unittest.main()
