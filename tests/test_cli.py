import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from denodo_cli import cli
from denodo_cli.transports.base import HttpResult, VqlResult

PROFILES = """
[dev]
host = "h"
user = "u"
password = "p"
marketplace_url = "http://mp/ctx"

[prod]
host = "h"
user = "u"
password = "p"
production = true
"""


class FakeVql:
    executed = []

    def __init__(self, profile, database=None):
        pass

    def execute(self, statement):
        FakeVql.executed.append(statement)
        if "BOOM" in statement:
            raise RuntimeError("ERROR:  x\nDETAIL:  java.sql.SQLException: Syntax error near 'BOOM'\n")
        return VqlResult(statement=statement, columns=["n"], rows=[[1]])

    def close(self):
        pass


class FakeRest:
    calls = []

    def __init__(self, profile):
        pass

    def call(self, method, path, **kw):
        FakeRest.calls.append((method, path, kw))
        return HttpResult(status=200, body={"ok": True}, headers={}, elapsed_ms=1)


class CliHarness:
    """Profiles file, fake transports and a ``run_cli`` helper, shared by the CLI suites.

    A mixin rather than a base ``TestCase``: subclassing a ``TestCase`` re-runs every one of
    its tests under the subclass's name too, so a second suite built on it would double-count
    the first suite's coverage instead of adding to it.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "profiles.toml"
        self.path.write_text(PROFILES)
        env = mock.patch.dict(os.environ, {"DENODO_PROFILES": str(self.path)}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("DENODO_ENV", None)
        for p in (mock.patch.object(cli, "resolve_vql_factory", lambda profile: FakeVql),
                  mock.patch.object(cli, "resolve_rest_factory", lambda: FakeRest)):
            p.start()
            self.addCleanup(p.stop)
        FakeVql.executed.clear()
        FakeRest.calls.clear()

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(list(argv))
        return json.loads(out.getvalue()), code


class CliTest(CliHarness, unittest.TestCase):
    def test_env_list(self):
        doc, code = self.run_cli("env", "list")
        self.assertEqual(code, 0)
        self.assertEqual([p["name"] for p in doc["profiles"]], ["dev", "prod"])

    def test_missing_env_is_a_usage_error_in_json(self):
        doc, code = self.run_cli("vql", "run", "-e", "SELECT 1 FROM DUAL()")
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "usage")
        self.assertIn("--env", doc["error"]["message"])

    def test_env_from_environment_variable(self):
        with mock.patch.dict(os.environ, {"DENODO_ENV": "dev"}):
            doc, code = self.run_cli("vql", "run", "-e", "SELECT 1 FROM DUAL()")
        self.assertEqual(code, 0)
        self.assertEqual(doc["env"]["name"], "dev")

    def test_unknown_profile(self):
        doc, code = self.run_cli("vql", "run", "--env", "nope", "-e", "SELECT 1 FROM DUAL()")
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "config")
        self.assertIn("nope", doc["error"]["message"])

    def test_vql_run_inline_statement(self):
        doc, code = self.run_cli("vql", "run", "--env", "dev", "-e", "SELECT 1 FROM DUAL(); SELECT 2 FROM DUAL()")
        self.assertEqual(code, 0)
        self.assertEqual(FakeVql.executed, ["SELECT 1 FROM DUAL()", "SELECT 2 FROM DUAL()"])
        self.assertEqual(doc["executed"], 2)

    def test_vql_run_file(self):
        script = Path(self.tmp.name) / "x.vql"
        script.write_text("-- header\nCREATE OR REPLACE FOLDER '/a';\nSELECT BOOM;\nSELECT 3 FROM DUAL();\n")
        doc, code = self.run_cli("vql", "run", "--env", "dev", str(script))
        self.assertEqual(code, 1)
        self.assertEqual(doc["failed_at"], 1)
        self.assertEqual(doc["source"], str(script))

    def test_vql_run_from_stdin(self):
        with mock.patch("sys.stdin", io.StringIO("SELECT 7 FROM DUAL()")):
            doc, code = self.run_cli("vql", "run", "--env", "dev", "-")
        self.assertEqual(code, 0)
        self.assertEqual(FakeVql.executed, ["SELECT 7 FROM DUAL()"])

    def test_vql_run_requires_exactly_one_input(self):
        doc, code = self.run_cli("vql", "run", "--env", "dev")
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "usage")

    def test_vql_run_missing_file(self):
        doc, code = self.run_cli("vql", "run", "--env", "dev", "/nonexistent/x.vql")
        self.assertEqual(code, 2)
        self.assertIn("/nonexistent/x.vql", doc["error"]["message"])

    def test_vql_run_destructive_on_prod_refused_then_allowed(self):
        doc, code = self.run_cli("vql", "run", "--env", "prod", "-e", "DROP VIEW v")
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "refused")
        doc, code = self.run_cli("vql", "run", "--env", "prod", "--allow-destructive", "-e", "DROP VIEW v")
        self.assertEqual(code, 0)

    def test_vql_desc(self):
        doc, code = self.run_cli("vql", "desc", "--env", "dev", "--type", "datasource df", "--vql", "ds")
        self.assertEqual(code, 0)
        self.assertEqual(FakeVql.executed, ["DESC VQL DATASOURCE DF ds"])

    def test_api_get_with_params(self):
        doc, code = self.run_cli("api", "get", "/public/api/tags", "--env", "dev", "--param", "offset=0")
        self.assertEqual(code, 0)
        method, path, kw = FakeRest.calls[0]
        self.assertEqual((method, path), ("GET", "/public/api/tags"))
        self.assertEqual(kw["params"], {"offset": "0"})
        self.assertEqual(doc["status"], 200)

    def test_api_post_with_json(self):
        self.run_cli("api", "post", "/public/api/tags", "--env", "dev", "--json", '{"name": "t"}')
        self.assertEqual(FakeRest.calls[0][2]["json_body"], {"name": "t"})

    def test_api_post_with_json_file(self):
        body = Path(self.tmp.name) / "body.json"
        body.write_text('{"a": [1, 2]}')
        self.run_cli("api", "post", "/x", "--env", "dev", "--json-file", str(body))
        self.assertEqual(FakeRest.calls[0][2]["json_body"], {"a": [1, 2]})

    def test_api_invalid_json_is_usage_error(self):
        doc, code = self.run_cli("api", "post", "/x", "--env", "dev", "--json", "{not json")
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "usage")

    def test_api_multipart_parts(self):
        icon = Path(self.tmp.name) / "i.svg"
        icon.write_bytes(b"<svg/>")
        self.run_cli("api", "post", "/x", "--env", "dev", "--part", f"icon=@{icon}", "--part", 'request=json:{"n":1}')
        parts = FakeRest.calls[0][2]["multipart"]
        self.assertEqual(parts["icon"][1], b"<svg/>")
        self.assertEqual(parts["request"][2], "application/json")

    def test_api_delete_on_prod_is_refused(self):
        doc, code = self.run_cli("api", "delete", "/public/api/tags/1", "--env", "prod")
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "refused")

    def test_env_check(self):
        doc, code = self.run_cli("env", "check", "--env", "dev")
        self.assertEqual(code, 0)
        self.assertTrue(doc["vdp"]["ok"])
        self.assertTrue(doc["marketplace"]["ok"])

    def test_env_init_refuses_without_a_terminal(self):
        with mock.patch("sys.stdin", io.StringIO("")):
            doc, code = self.run_cli("env", "init")
        self.assertEqual(code, 2)
        self.assertIn("interactive", doc["error"]["message"])

    def test_missing_driver_is_an_environment_error(self):
        def no_driver(profile):
            raise ImportError("No module named 'sqlalchemy'")

        with mock.patch.object(cli, "resolve_vql_factory", no_driver):
            doc, code = self.run_cli("vql", "run", "--env", "dev", "-e", "SELECT 1 FROM DUAL()")
        self.assertEqual(code, 3)
        self.assertEqual(doc["error"]["kind"], "environment")
        self.assertIn("denodo-sqlalchemy", doc["error"]["hint"])

    def test_bad_arguments_produce_json_not_argparse_text(self):
        doc, code = self.run_cli("vql", "frobnicate")
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "usage")


class VerifyCommandTest(CliHarness, unittest.TestCase):
    def test_parser_accepts_the_flags(self):
        args = cli.build_parser().parse_args(["verify", "--env", "lab", "--with-marketplace", "--keep",
                                              "--update-marks", "--allow-destructive",
                                              "--chain", "verification/chain.toml"])
        self.assertEqual(args.group, "verify")
        self.assertTrue(args.with_marketplace)
        self.assertTrue(args.keep)
        self.assertTrue(args.update_marks)
        self.assertTrue(args.allow_destructive)
        self.assertEqual(args.chain, "verification/chain.toml")

    def test_defaults(self):
        args = cli.build_parser().parse_args(["verify", "--env", "lab"])
        self.assertFalse(args.with_marketplace)
        self.assertFalse(args.keep)
        self.assertFalse(args.update_marks)
        self.assertFalse(args.allow_destructive)
        self.assertIsNone(args.chain)

    def test_a_malformed_manifest_is_a_usage_error_in_json(self):
        path = Path(tempfile.mkdtemp()) / "chain.toml"
        path.write_text("[[step]]\nid = 'x'\nkind = 'magic'\nchannel = 'vql'\n", encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["verify", "--env", "dev", "--chain", str(path)])
        doc = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["error"]["kind"], "usage")
        self.assertIn("magic", doc["error"]["message"])

    def test_a_run_time_chain_error_is_a_usage_error_in_json_too(self):
        # _check_cleanup_placeholders raises ChainError from inside run_chain, well after
        # load_chain returned. With a user-supplied --chain that is the likeliest first
        # failure, and it used to escape as a traceback with no JSON document at all.
        path = Path(tempfile.mkdtemp()) / "chain.toml"
        path.write_text("""
[values]
database = "denodo_skills_test"

[cleanup]
vql = ["DROP TAG IF EXISTS {tag_prefix}pii"]

[[step]]
id = "fix"
kind = "fixture"
channel = "vql"
vql = "SELECT 1 FROM DUAL()"
""", encoding="utf-8")
        doc, code = self.run_cli("verify", "--env", "dev", "--chain", str(path))
        self.assertEqual(code, 2)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["error"]["kind"], "usage")
        self.assertIn("tag_prefix", doc["error"]["message"])


class SecretCommandTest(CliHarness, unittest.TestCase):
    """The password reaches the server and nothing else: not a command line, not the output."""

    def stdin(self, text):
        return mock.patch("sys.stdin", io.StringIO(text))

    def test_password_piped_in_is_encrypted(self):
        with self.stdin("hunter2\n"):
            doc, code = self.run_cli("secret", "encrypt", "--env", "dev")
        self.assertEqual(code, 0)
        self.assertEqual(FakeVql.executed, ["ENCRYPT_PASSWORD 'hunter2'"])
        self.assertEqual(doc["command"], "secret encrypt")
        self.assertNotIn("hunter2", json.dumps(doc))

    def test_a_terminal_gets_a_hidden_prompt_instead(self):
        tty = mock.MagicMock()
        tty.isatty.return_value = True
        with mock.patch("sys.stdin", tty), mock.patch.object(cli.getpass, "getpass", return_value="typed"):
            doc, code = self.run_cli("secret", "encrypt", "--env", "dev")
        self.assertEqual(code, 0)
        self.assertEqual(FakeVql.executed, ["ENCRYPT_PASSWORD 'typed'"])
        tty.read.assert_not_called()

    def test_only_the_trailing_newline_is_stripped(self):
        with self.stdin("  spaced pass  \n"):
            self.run_cli("secret", "encrypt", "--env", "dev")
        self.assertEqual(FakeVql.executed, ["ENCRYPT_PASSWORD '  spaced pass  '"])

    def test_a_windows_line_ending_is_stripped_too(self):
        with self.stdin("hunter2\r\n"):
            self.run_cli("secret", "encrypt", "--env", "dev")
        self.assertEqual(FakeVql.executed, ["ENCRYPT_PASSWORD 'hunter2'"])

    def test_an_empty_password_is_a_usage_error(self):
        with self.stdin("\n"):
            doc, code = self.run_cli("secret", "encrypt", "--env", "dev")
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "usage")
        self.assertEqual(FakeVql.executed, [])

    def test_more_than_one_line_is_a_usage_error(self):
        with self.stdin("first\nsecond\n"):
            doc, code = self.run_cli("secret", "encrypt", "--env", "dev")
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "usage")
        self.assertIn("one line", doc["error"]["message"])
        self.assertEqual(FakeVql.executed, [])


if __name__ == "__main__":
    unittest.main()
