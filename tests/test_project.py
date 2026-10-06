import datetime as dt
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from denodo_cli.project import declarations_before, normalize
from denodo_cli.statements import ObjectRef

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]


def commit(repo: Path, message: str, when: dt.datetime) -> None:
    env = dict(os.environ, GIT_AUTHOR_DATE=when.isoformat(), GIT_COMMITTER_DATE=when.isoformat())
    subprocess.run(GIT + ["add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(GIT + ["commit", "-q", "-m", message], cwd=repo, check=True, capture_output=True, env=env)


class DeclarationsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        (self.repo / "model").mkdir()
        self.yesterday = dt.datetime(2026, 10, 5, 9, 0, tzinfo=dt.timezone.utc)
        self.started = dt.datetime(2026, 10, 6, 9, 0, tzinfo=dt.timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def test_objects_declared_in_a_commit_before_the_session(self):
        (self.repo / "model" / "views.vql").write_text(
            "CONNECT DATABASE sales;\nCREATE OR REPLACE VIEW iv_orders AS SELECT 1 AS a FROM Dual();\n"
            "CREATE OR REPLACE FOLDER '/02 - integration';\n")
        commit(self.repo, "views", self.yesterday)
        found = declarations_before(self.repo / "model" / "new.vql", self.started, default_database="admin")
        self.assertEqual(found.root, self.repo.resolve())
        decl = found.get(ObjectRef("view", "sales", "IV_ORDERS"))
        self.assertEqual(decl.path, "model/views.vql")
        self.assertIn("iv_orders", decl.text)
        self.assertIsNotNone(found.get(ObjectRef("folder", "sales", "/02 - integration")))

    def test_a_commit_made_during_the_session_vouches_for_nothing(self):
        (self.repo / "model" / "views.vql").write_text("CREATE OR REPLACE VIEW old_one AS SELECT 1 AS a FROM Dual();\n")
        commit(self.repo, "before", self.yesterday)
        (self.repo / "model" / "views.vql").write_text(
            "CREATE OR REPLACE VIEW old_one AS SELECT 1 AS a FROM Dual();\n"
            "CREATE OR REPLACE VIEW colleague_view AS SELECT 2 AS b FROM Dual();\n")
        commit(self.repo, "during", self.started + dt.timedelta(minutes=30))
        found = declarations_before(self.repo / "model" / "views.vql", self.started, default_database="sales")
        self.assertIsNotNone(found.get(ObjectRef("view", "sales", "old_one")))
        self.assertIsNone(found.get(ObjectRef("view", "sales", "colleague_view")))

    def test_without_a_file_database_the_default_one_is_assumed(self):
        (self.repo / "a.vql").write_text("CREATE OR REPLACE VIEW v AS SELECT 1 AS a FROM Dual();\n")
        commit(self.repo, "a", self.yesterday)
        found = declarations_before(self.repo / "a.vql", self.started, default_database="sales")
        self.assertIsNotNone(found.get(ObjectRef("view", "sales", "v")))
        self.assertIsNone(found.get(ObjectRef("view", "other", "v")))

    def test_no_commit_before_the_session(self):
        (self.repo / "a.vql").write_text("CREATE OR REPLACE VIEW v AS SELECT 1 AS a FROM Dual();\n")
        commit(self.repo, "a", self.started + dt.timedelta(hours=1))
        found = declarations_before(self.repo / "a.vql", self.started, default_database="sales")
        self.assertIsNone(found.base)
        self.assertIsNone(found.get(ObjectRef("view", "sales", "v")))

    def test_outside_git(self):
        with tempfile.TemporaryDirectory() as plain:
            found = declarations_before(Path(plain) / "x.vql", self.started, default_database="sales")
            self.assertIsNone(found.root)

    def test_normalize_ignores_whitespace_and_case_of_keywords_only_in_spacing(self):
        self.assertEqual(normalize("CREATE  OR REPLACE\n VIEW v AS SELECT 1"), normalize("CREATE OR REPLACE VIEW v AS SELECT 1"))
        self.assertNotEqual(normalize("SELECT 'a b'"), normalize("SELECT 'a  b'"))


if __name__ == "__main__":
    unittest.main()
