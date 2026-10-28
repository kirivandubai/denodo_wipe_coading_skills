"""A workspace's VQL file through denodo_exec: read once, planned, judged, applied, recorded --
denodo_cli faked as the process it is."""

import stat
import tempfile
import unittest
from pathlib import Path

from denodo_exec import files, ledger, vqlfile
from denodo_exec.errors import Refused
from denodo_exec.scope import Scope, Wording
from tests.exec_helpers import AT, DB, FakeCli, Space, client, entry, nothing, space

WORDS = Wording(owner="OWNER: ", unit="demo")


def vql(workspace: Space, name: str, text: str) -> str:
    (workspace.root / "denodo" / name).write_text(text, encoding="utf-8")
    return f"denodo/{name}"


class Swapping(FakeCli):
    """denodo_cli that reads each file it is handed -- and, once the plan is read, the
    workspace's file rewritten under it, as the agent's file tool could between two reads."""

    def __init__(self, workspace: Space, name: str, swap: str, **kwargs):
        super().__init__(**kwargs)
        self.target, self.swap = workspace.root / name, swap
        self.read = {}

    def __call__(self, argv, *, timeout, env=None):
        args = list(argv[3:])
        if args[:2] in (["vql", "plan"], ["vql", "run"]) and args[2] != "-e":
            path = Path(args[2])
            self.read[args[1]] = (str(path), path.read_text("utf-8"),
                                  stat.S_IMODE(path.stat().st_mode))
            if args[1] == "plan":
                self.target.write_text(self.swap, encoding="utf-8")
        return super().__call__(argv, timeout=timeout, env=env)


class VqlFileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.space = space(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def apply(self, cli, name):
        return vqlfile.apply(self.space, client(self.tmp, cli), name, scope=Scope(DB), at=AT,
                             make_rule=lambda: nothing, wording=WORDS)

    def test_apply_refuses_before_anything_runs_and_names_the_owners_word(self):
        name = vql(self.space, "10-replace.vql", "CREATE OR REPLACE VIEW customers AS SELECT 1;")
        cli = FakeCli(plan=[entry(0, "replace", "view", "customers", exists=True)])
        with self.assertRaisesRegex(Refused, "^OWNER: #0"):
            self.apply(cli, name)
        self.assertEqual([call[3:5] for call in cli.calls], [["vql", "plan"]])
        self.assertEqual(ledger.live_objects(self.space.ledger), {})

    def test_apply_runs_and_records_each_object_and_the_files_bytes(self):
        first = vql(self.space, "10-folder.vql", "CREATE FOLDER '/views';")
        second = vql(self.space, "20-view.vql",
                     "CREATE VIEW dv_customers FOLDER = '/views' AS SELECT 1;")
        self.apply(FakeCli(plan=[entry(0, "create", "folder", "/views")]), first)
        done = self.apply(FakeCli(plan=[entry(0, "create", "view", "dv_customers")]), second)
        self.assertIs(done["ok"], True)
        self.assertEqual(sorted(ledger.live_objects(self.space.ledger)),
                         [("folder", DB, "/views"), ("view", DB, "dv_customers")])
        applied = [line for line in files.read_jsonl(self.space.ledger)
                   if line["action"] == "applied"]
        self.assertEqual([line["file"] for line in applied], [first, second])
        self.assertEqual(applied[1]["vql_sha"], files.file_digest(self.space.root / second))

    def test_a_create_over_an_existing_object_of_ones_own_is_recorded_as_a_replace(self):
        self.apply(FakeCli(plan=[entry(0, "create", "view", "dv_a")]),
                   vql(self.space, "10-a.vql", "CREATE VIEW dv_a AS SELECT 1;"))
        self.apply(FakeCli(plan=[entry(0, "create", "view", "dv_a", exists=True)]),
                   vql(self.space, "20-a.vql", "CREATE OR REPLACE VIEW dv_a AS SELECT 2;"))
        actions = [line["action"] for line in files.read_jsonl(self.space.ledger)]
        self.assertEqual(actions, ["create", "applied", "replace", "applied"])

    def test_a_server_error_records_no_object_and_no_applied_line(self):
        name = vql(self.space, "10-view.vql", "CREATE VIEW dv_x AS SELECT 1;")
        done = self.apply(FakeCli(plan=[entry(0, "create", "view", "dv_x")], run_ok=False), name)
        self.assertIs(done["ok"], False)
        self.assertEqual(done["failed_at"], 0)
        self.assertEqual(done["statements"][0]["error"], "Syntax error")
        self.assertEqual(files.read_jsonl(self.space.ledger), [])

    def test_only_a_numbered_file_of_denodo_is_taken(self):
        for bad in ("10-x.vql", "denodo/../request.md", "denodo/x.vql", "denodo/10-X.vql",
                    "denodo/10_x.vql", "denodo/10-none.vql", ""):
            with self.subTest(bad=bad), self.assertRaises(Refused):
                vqlfile.plan(self.space, client(self.tmp, FakeCli()), bad, scope=Scope(DB),
                             wording=WORDS)
        with self.assertRaisesRegex(Refused, "is not a demo VQL file"):
            vqlfile.vql_file(self.space, "x.vql", WORDS)

    def test_a_file_that_is_no_utf8_or_ends_a_line_in_a_lone_return_is_refused(self):
        (self.space.root / "denodo" / "10-a.vql").write_bytes(b"\xff\xfe")
        (self.space.root / "denodo" / "20-b.vql").write_bytes(b"-- x\rDROP VIEW v;")
        for name, said in (("denodo/10-a.vql", "not UTF-8"), ("denodo/20-b.vql", "carriage")):
            with self.subTest(name=name), self.assertRaisesRegex(Refused, said):
                vqlfile.plan(self.space, client(self.tmp, FakeCli()), name, scope=Scope(DB))

    def test_the_file_rewritten_after_it_was_read_does_not_change_what_runs(self):
        text = "CREATE VIEW dv_customers AS SELECT 1;"
        name = vql(self.space, "10-view.vql", text)
        original = files.file_digest(self.space.root / name)
        cli = Swapping(self.space, name, "DROP VIEW customers;",
                       plan=[entry(0, "create", "view", "dv_customers")])
        self.apply(cli, name)
        planned, ran = cli.read["plan"], cli.read["run"]
        # One copy, read once, planned and run: the workspace's file changed, not the copy.
        self.assertEqual(planned[0], ran[0])
        self.assertEqual((planned[1], ran[1]), (text, text))
        self.assertFalse(Path(ran[0]).is_relative_to(self.space.root))
        self.assertEqual(ran[2], 0o600)
        self.assertFalse(Path(ran[0]).exists())
        lines = [line for line in files.read_jsonl(self.space.ledger) if line.get("vql_sha")]
        self.assertTrue(lines)
        self.assertEqual({line["vql_sha"] for line in lines}, {original})

    def test_the_plan_says_what_would_run_and_runs_nothing(self):
        name = vql(self.space, "10-view.vql", "CREATE VIEW dv_x AS SELECT 1;")
        cli = FakeCli(plan=[entry(0, "create", "view", "dv_x")])
        done = vqlfile.plan(self.space, client(self.tmp, cli), name, scope=Scope(DB))
        self.assertEqual((done["file"], done["database"], done["refused"]), (name, DB, None))
        self.assertEqual(done["server"]["name"], "dev")
        self.assertEqual([call[3:5] for call in cli.calls], [["vql", "plan"]])

    def test_a_fresh_rule_is_made_for_every_file(self):
        made = []

        def make():
            made.append(1)
            return nothing

        name = vql(self.space, "10-view.vql", "CREATE VIEW dv_x AS SELECT 1;")
        for _ in range(2):
            vqlfile.plan(self.space, client(self.tmp, FakeCli(plan=[
                entry(0, "create", "view", "dv_x")])), name, scope=Scope(DB), make_rule=make)
        self.assertEqual(made, [1, 1])


class HeldTest(unittest.TestCase):
    def test_a_checks_answer_is_held_to_what_it_expects(self):
        row = {"ok": True, "columns": ["customer_id", "balance"],
               "rows": [["c1", 10], ["c2", 20]], "row_count": 2}
        good = vqlfile.held("schema", "SELECT 1", row, {
            "columns": ["customer_id", "balance"], "min_rows": 2,
            "values": [{"row": 1, "column": "balance", "equals": 20}]})
        self.assertIs(good["ok"], True)
        self.assertEqual(good["failures"], [])
        bad = vqlfile.held("rows", "SELECT 1", row, {
            "min_rows": 5, "columns": ["nope"],
            "values": [{"row": 9, "column": "balance", "equals": 1},
                       {"row": 0, "column": "balance", "equals": 11}]})
        self.assertEqual(bad["failures"], ["columns missing: nope", "2 rows, fewer than 5",
                                           "no row 9 column balance",
                                           "row 0 balance is 10, not 11"])
        refused = vqlfile.held("x", "SELECT 1", {"ok": False, "error": {"message": "no view"}}, {})
        self.assertEqual(refused["failures"], ["the server refused: no view"])

    def test_a_long_answer_keeps_twenty_rows(self):
        row = {"ok": True, "columns": ["n"], "rows": [[i] for i in range(50)], "row_count": 50}
        held = vqlfile.held("n", "SELECT 1", row, {})
        self.assertEqual((len(held["rows"]), held["row_count"]), (20, 50))


if __name__ == "__main__":
    unittest.main()
