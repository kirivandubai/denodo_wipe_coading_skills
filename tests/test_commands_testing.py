import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from denodo_cli.commands.testing import properties_value, run_testing_tool, write_testing_config
from denodo_cli.output import to_json
from denodo_cli.profiles import Profile


def profile(**over):
    base = dict(name="dev", host="vdp.example.test", port=9996, database="admin", user="tester",
                password="s3cret", production=False, transport="vql_psycopg2", marketplace_url=None,
                marketplace_server_id=None)
    base.update(over)
    return Profile(**base)


def read_properties(path: Path) -> dict:
    """The key = value lines of a generated file, comments skipped, values left escaped."""
    entries = {}
    for line in path.read_text(encoding="iso-8859-1").splitlines():
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        entries[key] = value
    return entries


class WriteTestingConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "denodo"

    def run_it(self, prof=None, **kw):
        kw.setdefault("config_dir", self.home / "testing")
        return write_testing_config(prof or profile(), **kw)

    def test_the_file_holds_a_vdp_data_source_built_from_the_profile(self):
        doc, code = self.run_it()
        self.assertEqual(code, 0)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["command"], "testing config")
        path = Path(doc["path"])
        self.assertEqual(path, self.home / "testing" / "dev" / "admin.properties")
        entries = read_properties(path)
        self.assertEqual(entries["vdp.driverClassName"], "com.denodo.vdp.jdbc.Driver")
        self.assertEqual(entries["vdp.jdbcUrl"], "jdbc:denodo://vdp.example.test:9999/admin")
        self.assertEqual(entries["vdp.username"], "tester")
        self.assertEqual(entries["vdp.password"], "s3cret")
        self.assertEqual(entries["vdp.dbAdapter"], "denodo-9.0.0")
        self.assertEqual(entries["vdp.connectionTestQuery"], "SELECT * FROM Dual()")
        self.assertEqual(entries["reporter"], "com.denodo.connect.testing.reporter.ConsoleTestReporter")
        self.assertEqual(entries["encoding"], "UTF-8")
        self.assertEqual(entries["maxRowsInMemoryForMatching"], "10000")

    def test_the_password_is_in_the_file_and_nowhere_in_the_answer(self):
        doc, _ = self.run_it()
        self.assertNotIn("s3cret", to_json(doc))
        self.assertEqual(doc["jdbc_url"], "jdbc:denodo://vdp.example.test:9999/admin")
        self.assertEqual(doc["datasource"], "vdp")
        self.assertEqual(doc["user"], "tester")

    def test_only_the_owner_can_read_the_file_or_its_directory(self):
        doc, _ = self.run_it()
        path = Path(doc["path"])
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_regenerating_replaces_the_file_and_keeps_it_private(self):
        first, _ = self.run_it()
        os.chmod(first["path"], 0o644)
        second, code = self.run_it(profile(password="rotated"))
        self.assertEqual(code, 0)
        self.assertEqual(first["path"], second["path"])
        self.assertEqual(read_properties(Path(second["path"]))["vdp.password"], "rotated")
        self.assertEqual(stat.S_IMODE(Path(second["path"]).stat().st_mode), 0o600)

    def test_the_database_names_the_url_the_file_and_the_envelope(self):
        doc, _ = self.run_it(database="sales_analytics")
        self.assertEqual(doc["env"]["database"], "sales_analytics")
        self.assertTrue(doc["path"].endswith(os.path.join("dev", "sales_analytics.properties")))
        self.assertEqual(read_properties(Path(doc["path"]))["vdp.jdbcUrl"],
                         "jdbc:denodo://vdp.example.test:9999/sales_analytics")

    def test_the_jdbc_port_comes_from_the_profile(self):
        doc, _ = self.run_it(profile(jdbc_port=29999))
        self.assertEqual(doc["jdbc_url"], "jdbc:denodo://vdp.example.test:29999/admin")

    def test_another_driver_folder_can_be_named(self):
        doc, _ = self.run_it(db_adapter="denodo-9.3.0")
        self.assertEqual(read_properties(Path(doc["path"]))["vdp.dbAdapter"], "denodo-9.3.0")
        self.assertEqual(doc["db_adapter"], "denodo-9.3.0")

    def test_an_output_path_outside_any_repository_is_used(self):
        target = Path(self.tmp.name) / "elsewhere" / "ci.properties"
        doc, code = self.run_it(output=target)
        self.assertEqual(code, 0)
        self.assertEqual(Path(doc["path"]), target)
        self.assertEqual(read_properties(target)["vdp.password"], "s3cret")

    def test_an_output_path_inside_a_git_work_tree_is_refused(self):
        repo = Path(self.tmp.name) / "project"
        (repo / ".git").mkdir(parents=True)
        target = repo / "tests" / "conf" / "configuration.properties"
        doc, code = self.run_it(output=target)
        self.assertEqual(code, 2)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["error"]["kind"], "usage")
        self.assertIn("git", doc["error"]["message"])
        self.assertFalse(target.exists())

    def test_a_worktree_or_submodule_marker_file_counts_as_git_too(self):
        repo = Path(self.tmp.name) / "linked"
        repo.mkdir()
        (repo / ".git").write_text("gitdir: /somewhere/else\n")
        doc, code = self.run_it(output=repo / "configuration.properties")
        self.assertEqual(code, 2)
        self.assertFalse((repo / "configuration.properties").exists())

    def test_the_default_location_inside_a_repository_is_refused_as_well(self):
        repo = Path(self.tmp.name) / "dotfiles"
        (repo / ".git").mkdir(parents=True)
        doc, code = self.run_it(config_dir=repo / "testing")
        self.assertEqual(code, 2)
        self.assertFalse((repo / "testing").exists())

    @unittest.skipIf(shutil.which("git") is None, "needs git to read ignore rules")
    def test_a_path_the_repository_ignores_is_accepted(self):
        repo = Path(self.tmp.name) / "home"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / ".gitignore").write_text(".denodo/\n")
        doc, code = self.run_it(config_dir=repo / ".denodo" / "testing")
        self.assertEqual(code, 0, doc)
        self.assertTrue(Path(doc["path"]).is_file())

    def test_a_production_profile_is_refused_without_the_flag(self):
        doc, code = self.run_it(profile(production=True))
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "refused")
        self.assertIn("SETUP", doc["error"]["message"])
        self.assertFalse((self.home / "testing").exists())

    def test_a_production_profile_is_written_with_the_flag(self):
        doc, code = self.run_it(profile(production=True), allow_destructive=True)
        self.assertEqual(code, 0)
        self.assertTrue(Path(doc["path"]).is_file())

    def test_a_database_name_that_is_not_a_plain_name_is_refused(self):
        for bad in ("../admin", "a/b", "a\\b", ".hidden", ""):
            doc, code = self.run_it(database=bad)
            self.assertEqual(code, 2, bad)
            self.assertEqual(doc["error"]["kind"], "usage", bad)

    def test_a_password_the_tool_would_read_as_jasypt_ciphertext_is_refused(self):
        doc, code = self.run_it(profile(password="ENC(abc)"))
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "config")
        self.assertNotIn("ENC(abc)", to_json(doc))
        self.assertFalse((self.home / "testing").exists())


class PropertiesValueTest(unittest.TestCase):
    """The tool loads the file with java.util.Properties in ISO-8859-1."""

    def test_plain_text_is_unchanged(self):
        self.assertEqual(properties_value("pa=ss:word#1!"), "pa=ss:word#1!")

    def test_a_backslash_is_doubled(self):
        self.assertEqual(properties_value("a\\b"), "a\\\\b")

    def test_a_leading_space_is_kept_by_escaping_it(self):
        self.assertEqual(properties_value("  x "), "\\  x ")

    def test_control_characters_are_escaped(self):
        self.assertEqual(properties_value("a\tb\nc\rd\fe"), "a\\tb\\nc\\rd\\fe")

    def test_anything_beyond_ascii_becomes_a_unicode_escape(self):
        self.assertEqual(properties_value("pässwörd"), "p\\u00e4ssw\\u00f6rd")

    def test_a_character_outside_the_basic_plane_is_a_surrogate_pair(self):
        self.assertEqual(properties_value("\U0001F511"), "\\ud83d\\udd11")


OK_OUTPUT = """[EXECUTION:START]
--[TEST:END][OK][/p/a.denodotest][a_counts][12ms][1] Test run: a_counts. Test executed OK: Obtained and expected results match. Time elapsed: 12ms.
--[TEST:END][OK][/p/b.denodotest][b_key][9ms][0] Test run: b_key. Test executed OK: Obtained and expected results match. Time elapsed: 9ms.
Results:
Tests run: 2, OK: 2
Total tuples: 1, Zero-tuple tests: 1
"""

FAILED_OUTPUT = """--[TEST:END][FAILED][/p/a.denodotest][a_counts][12ms][1] Test run: a_counts. Test FAILED!: Row 1, col 1 of the obtained result contained [9], but [10] was expected at that position. Time elapsed: 12ms.
--[TEST:END][FAILED][/p/a.denodotest][a_counts][12ms][1] Test run: a_counts. Test FAILED!: Row 1, col 1 of the obtained result contained [9], but [10] was expected at that position. Time elapsed: 12ms.
--[TEST:END][OK][/p/b.denodotest][b_key][9ms][0] Test run: b_key. Test executed OK: Obtained and expected results match. Time elapsed: 9ms.
Tests run: 2, OK: 1 (FAILED: 1)
Total tuples: 1, Zero-tuple tests: 1
"""


class FakeLauncher:
    """Stands in for the process call: records the command and what the configuration held."""

    def __init__(self, returncode=0, output=OK_OUTPUT):
        self.returncode, self.output, self.calls = returncode, output, []

    def __call__(self, command, cwd, env):
        config = Path(command[2][len("file:"):])
        self.calls.append({"command": command, "cwd": cwd, "env": env, "config_path": config,
                           "config": config.read_text(encoding="iso-8859-1"),
                           "mode": stat.S_IMODE(config.stat().st_mode)})
        return self.returncode, self.output


class RunTestingToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.tool = root / "denodo-testing-tool"
        (self.tool / "bin").mkdir(parents=True)
        (self.tool / "bin" / "denodo-test.sh").write_text("#!/bin/bash\n")
        self.tests = root / "project" / "tests"
        (self.tests / "expected").mkdir(parents=True)
        for name in ("a.denodotest", "b.denodotest", "first.denodotest"):
            (self.tests / name).write_text("%NAME x\n")
        (self.tests / "expected" / "rows.csv").write_text("n\n1\n")

    def run_it(self, launcher, prof=None, **kw):
        kw.setdefault("tool", self.tool)
        return run_testing_tool(prof or profile(jdbc_port=29999), tests=self.tests, runner=launcher, **kw)

    def test_the_tool_runs_from_its_bin_with_a_private_temporary_configuration(self):
        launcher = FakeLauncher()
        doc, code = self.run_it(launcher, database="sales")
        self.assertEqual(code, 0, doc)
        call = launcher.calls[0]
        self.assertEqual(call["command"][:2], ["bash", str(self.tool / "bin" / "denodo-test.sh")])
        self.assertEqual(call["command"][3], f"file:{self.tests}")
        self.assertEqual(Path(call["cwd"]), self.tool / "bin")
        self.assertEqual(call["mode"], 0o600)
        self.assertIn("vdp.jdbcUrl=jdbc:denodo://vdp.example.test:29999/sales", call["config"])
        self.assertIn("vdp.password=s3cret", call["config"])
        self.assertFalse(call["config_path"].exists())
        self.assertNotIn("s3cret", to_json(doc))

    def test_a_passing_run_reports_its_summary_and_tests(self):
        doc, code = self.run_it(FakeLauncher())
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["command"], "testing run")
        self.assertEqual(doc["exit_code"], 0)
        self.assertEqual(doc["summary"], {"run": 2, "ok": 2, "failed": 0, "zero_tuple": 1})
        self.assertEqual(doc["test_files"], 2)
        self.assertEqual([t["test"] for t in doc["tests"]], ["a_counts", "b_key"])
        self.assertNotIn("warning", doc)

    def test_a_failed_test_is_exit_one_with_its_message_once(self):
        doc, code = self.run_it(FakeLauncher(returncode=1, output=FAILED_OUTPUT))
        self.assertEqual(code, 1)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["summary"]["failed"], 1)
        failed = [t for t in doc["tests"] if t["status"] == "FAILED"]
        self.assertEqual(len(failed), 1)
        self.assertIn("contained [9], but [10]", failed[0]["message"])

    def test_exit_zero_without_a_summary_is_a_failure(self):
        doc, code = self.run_it(FakeLauncher(returncode=0, output="Required parameters: [config_resource]"))
        self.assertEqual(code, 1)
        self.assertFalse(doc["ok"])
        self.assertIsNone(doc["summary"])
        self.assertIn("Required parameters", doc["output_tail"])

    def test_fewer_tests_run_than_files_is_warned_about(self):
        output = OK_OUTPUT.replace("Tests run: 2, OK: 2", "Tests run: 1, OK: 1")
        doc, code = self.run_it(FakeLauncher(output=output))
        self.assertIn("1 test", doc["warning"])
        self.assertIn("2 .denodotest", doc["warning"])

    def test_java_home_reaches_the_launcher_environment(self):
        launcher = FakeLauncher()
        self.run_it(launcher, java_home=Path("/opt/java17"))
        self.assertEqual(launcher.calls[0]["env"]["JAVA_HOME"], "/opt/java17")

    def test_a_directory_without_the_launcher_is_a_usage_error(self):
        doc, code = self.run_it(FakeLauncher(), tool=self.tool / "nowhere")
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "usage")
        self.assertIn("denodo-test.sh", doc["error"]["message"])

    def test_a_missing_tests_path_is_a_usage_error(self):
        doc, code = run_testing_tool(profile(), tests=self.tests / "nope", tool=self.tool, runner=FakeLauncher())
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "usage")

    def test_production_is_refused_without_the_flag_and_nothing_runs(self):
        launcher = FakeLauncher()
        doc, code = self.run_it(launcher, prof=profile(production=True))
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "refused")
        self.assertEqual(launcher.calls, [])
        doc, code = self.run_it(launcher, prof=profile(production=True), allow_destructive=True)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
