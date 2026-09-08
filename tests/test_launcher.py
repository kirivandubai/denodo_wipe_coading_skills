import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
LAUNCHER = REPO / "scripts" / "denodo"
ENTRY = REPO / "scripts" / "denodo_cli" / "__main__.py"


def load_launcher():
    loader = importlib.machinery.SourceFileLoader("denodo_launcher", str(LAUNCHER))
    spec = importlib.util.spec_from_loader("denodo_launcher", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class InlineMetadataTest(unittest.TestCase):
    def test_dependencies_come_from_the_entry_point_block(self):
        launcher = load_launcher()
        deps = launcher.read_inline_dependencies(ENTRY)
        self.assertEqual(deps, ["denodo-sqlalchemy>=2.0.5", "psycopg2-binary>=2.9.6"])

    def test_launcher_imports_only_the_standard_library(self):
        source = LAUNCHER.read_text()
        for forbidden in ("sqlalchemy", "psycopg2", "tomllib", "requests"):
            self.assertNotIn(f"import {forbidden}", source)


class DataDirTest(unittest.TestCase):
    def test_explicit_home_wins(self):
        launcher = load_launcher()
        with mock.patch.dict(os.environ, {"DENODO_CLI_HOME": "/x/home", "CLAUDE_PLUGIN_DATA": "/y/denodo"}):
            self.assertEqual(launcher.data_dir(), Path("/x/home"))

    def test_plugin_data_dir_is_used_when_it_belongs_to_this_plugin(self):
        launcher = load_launcher()
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": "/p/denodo-skills-denodo"}, clear=True):
            self.assertEqual(launcher.data_dir(), Path("/p/denodo-skills-denodo"))

    def test_foreign_plugin_data_dir_is_ignored(self):
        launcher = load_launcher()
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": "/p/other-plugin"}, clear=True):
            self.assertEqual(launcher.data_dir(), Path("~/.claude/plugins/data/denodo").expanduser())


class StrategyTest(unittest.TestCase):
    def test_explicit_python_first(self):
        launcher = load_launcher()
        with mock.patch.dict(os.environ, {"DENODO_CLI_PYTHON": "/opt/py/bin/python"}):
            cmd = launcher.build_command(["env", "list"])
        self.assertEqual(cmd[:3], ["/opt/py/bin/python", "-m", "denodo_cli"])

    def test_uv_when_available(self):
        launcher = load_launcher()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None):
            cmd = launcher.build_command(["env", "list"])
        self.assertEqual(cmd[:5], ["/usr/bin/uv", "run", "-q", "--script", str(ENTRY)])
        self.assertEqual(cmd[5:], ["env", "list"])

    def test_venv_fallback_uses_data_dir(self):
        launcher = load_launcher()
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.dict(os.environ, {"DENODO_CLI_HOME": tmp}, clear=True), \
             mock.patch("shutil.which", lambda name: None), \
             mock.patch.object(launcher, "ensure_venv", lambda deps: Path(tmp) / "venv" / "bin" / "python"):
            cmd = launcher.build_command(["env", "list"])
        self.assertEqual(cmd[:3], [str(Path(tmp) / "venv" / "bin" / "python"), "-m", "denodo_cli"])


class EndToEndTest(unittest.TestCase):
    def run_launcher(self, *args, env_extra=None):
        env = {k: v for k, v in os.environ.items() if k not in ("DENODO_CLI_PYTHON", "DENODO_ENV")}
        env.update(env_extra or {})
        return subprocess.run([sys.executable, str(LAUNCHER), *args], capture_output=True, text=True, env=env)

    def test_explicit_python_runs_the_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            profiles = Path(tmp) / "profiles.toml"
            profiles.write_text('[dev]\nhost="h"\nuser="u"\npassword="p"\n')
            proc = self.run_launcher("env", "list", env_extra={"DENODO_CLI_PYTHON": sys.executable,
                                                                "DENODO_PROFILES": str(profiles)})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertEqual(doc["profiles"][0]["name"], "dev")

    def test_exit_code_is_propagated(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_launcher("vql", "run", "-e", "SELECT 1", env_extra={
                "DENODO_CLI_PYTHON": sys.executable, "DENODO_PROFILES": str(Path(tmp) / "none.toml")})
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["error"]["kind"], "usage")

    def test_broken_interpreter_reports_environment_error(self):
        proc = self.run_launcher("env", "list", env_extra={"DENODO_CLI_PYTHON": "/nonexistent/python"})
        self.assertEqual(proc.returncode, 3)
        doc = json.loads(proc.stdout)
        self.assertEqual(doc["error"]["kind"], "environment")
        self.assertIn("pip install", doc["error"]["hint"])

    @unittest.skipUnless(shutil.which("uv"), "uv not installed")
    def test_uv_path_runs_with_real_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            profiles = Path(tmp) / "profiles.toml"
            profiles.write_text('[dev]\nhost="127.0.0.1"\nport=1\nuser="u"\npassword="p"\n')
            proc = self.run_launcher("env", "check", "--env", "dev", env_extra={"DENODO_PROFILES": str(profiles)})
        self.assertEqual(proc.returncode, 1, proc.stderr)  # driver loaded, connection refused
        doc = json.loads(proc.stdout)
        self.assertFalse(doc["vdp"]["ok"])
        self.assertNotEqual(doc["vdp"]["error"]["type"], "ImportError")


class UvFailureTest(unittest.TestCase):
    def test_uv_that_cannot_build_the_environment_yields_json_error(self):
        launcher = load_launcher()
        with tempfile.TemporaryDirectory() as tmp:
            fake_uv = Path(tmp) / "uv"
            fake_uv.write_text("#!/bin/sh\necho 'error: Failed to download distributions' >&2\nexit 2\n")
            fake_uv.chmod(0o755)
            import io
            from contextlib import redirect_stdout
            out = io.StringIO()
            with mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch("shutil.which", lambda name: str(fake_uv) if name == "uv" else None), \
                 redirect_stdout(out):
                code = launcher.main(["env", "list"])
        self.assertEqual(code, 3)
        doc = json.loads(out.getvalue())
        self.assertEqual(doc["error"]["kind"], "environment")
        self.assertIn("Failed to download", doc["error"]["message"])

    def test_uv_output_and_exit_code_pass_through_when_the_cli_ran(self):
        launcher = load_launcher()
        with tempfile.TemporaryDirectory() as tmp:
            fake_uv = Path(tmp) / "uv"
            fake_uv.write_text('#!/bin/sh\nprintf \'{"ok": false}\'\nexit 1\n')
            fake_uv.chmod(0o755)
            import io
            from contextlib import redirect_stdout
            out = io.StringIO()
            with mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch("shutil.which", lambda name: str(fake_uv) if name == "uv" else None), \
                 redirect_stdout(out):
                code = launcher.main(["env", "list"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue()), {"ok": False})
