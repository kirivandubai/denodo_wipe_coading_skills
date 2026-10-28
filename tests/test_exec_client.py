"""denodo_exec's profile copy, scrub and denodo_cli client -- denodo_cli faked as the process it
is."""

import json
import os
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from denodo_exec import profile as profiles
from denodo_exec.client import Denodo, Ran
from denodo_exec.errors import Refused, Unavailable
from denodo_exec.scrub import SECRET_MARK, scrub
from tests.exec_helpers import DB, PASSWORD, PROFILES, FakeCli, client, profile_and_file


def floats_in(value):
    if isinstance(value, float):
        return [value]
    if isinstance(value, dict):
        return [found for item in value.values() for found in floats_in(item)]
    if isinstance(value, (list, tuple)):
        return [found for item in value for found in floats_in(item)]
    return []


class Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def source(self) -> Path:
        path = self.tmp / "profiles.toml"
        path.write_text(PROFILES, encoding="utf-8")
        return path


class ProfileTest(Tmp):
    def test_the_copy_holds_one_profile_on_the_host_the_container_reaches(self):
        profile, path = profile_and_file(self.tmp)
        self.assertEqual((profile.host, profile.port, profile.user, profile.database),
                         ("host.docker.internal", 9996, "admin", "admin"))
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("[dev]\n"))
        self.assertNotIn("[prod]", text)
        self.assertIn('marketplace_url = "http://host.docker.internal:9090/denodo-data-catalog"', text)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertNotIn(PASSWORD, repr(profile))

    def test_a_production_profile_is_never_opened(self):
        with self.assertRaisesRegex(Refused, "production = true: the tool server never opens"):
            profiles.derive_profile(self.source(), "prod", "h", self.tmp / "run", who="the tool server")
        self.assertFalse((self.tmp / "run" / "profiles.toml").exists())

    def test_a_missing_file_or_profile_is_unavailable_with_a_sentence(self):
        with self.assertRaisesRegex(Unavailable, "no Denodo profiles at .*: mount it"):
            profiles.derive_profile(self.tmp / "none.toml", "dev", "h", self.tmp / "run",
                                    hint=": mount it")
        with self.assertRaisesRegex(Unavailable, "no profile 'test'"):
            profiles.derive_profile(self.source(), "test", "h", self.tmp / "run")
        (self.tmp / "bad.toml").write_text("[dev\npassword = 'x'", encoding="utf-8")
        with self.assertRaisesRegex(Unavailable, "is not valid TOML") as caught:
            profiles.derive_profile(self.tmp / "bad.toml", "dev", "h", self.tmp / "run")
        self.assertNotIn("password", str(caught.exception))

    def test_a_password_from_the_environment_is_resolved_or_refused(self):
        source = self.tmp / "profiles.toml"
        source.write_text('[dev]\nhost = "localhost"\nuser = "u"\npassword_env = "DEV_PW"\n',
                          encoding="utf-8")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEV_PW", None)
            with self.assertRaisesRegex(Unavailable, "DEV_PW, which the server is not given"):
                profiles.derive_profile(source, "dev", "h", self.tmp / "run")
        with mock.patch.dict(os.environ, {"DEV_PW": 'with "quotes"'}):
            profile, path = profiles.derive_profile(source, "dev", "h", self.tmp / "run")
        self.assertEqual(profile.password, 'with "quotes"')
        self.assertIn('password = "with \\"quotes\\""', path.read_text(encoding="utf-8"))

    def test_a_profile_without_host_user_or_password_is_unavailable(self):
        source = self.tmp / "profiles.toml"
        source.write_text('[dev]\nhost = "localhost"\nuser = "u"\n', encoding="utf-8")
        with self.assertRaisesRegex(Unavailable, "lacks host, user or password"):
            profiles.derive_profile(source, "dev", "h", self.tmp / "run")

    def test_an_old_copy_of_the_profile_is_made_private(self):
        run = self.tmp / "run"
        run.mkdir()
        (run / "profiles.toml").write_text("old", encoding="utf-8")
        (run / "profiles.toml").chmod(0o644)
        _, path = profile_and_file(self.tmp)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(sorted(p.name for p in run.iterdir()), ["profiles.toml"])

    def test_a_reader_never_meets_an_empty_copy_while_it_is_rewritten(self):
        # The copy is replaced by a rename: a call of denodo_cli that opens it meanwhile reads
        # the old profile or the new one, never a file truncated under it.
        profile_and_file(self.tmp)
        path = self.tmp / "run" / "profiles.toml"
        seen, done = [], threading.Event()

        def read():
            while not done.is_set():
                seen.append(path.read_text(encoding="utf-8"))

        reader = threading.Thread(target=read)
        reader.start()
        try:
            for _ in range(200):
                profile_and_file(self.tmp)
        finally:
            done.set()
            reader.join()
        self.assertTrue(seen)
        self.assertTrue(all(text.startswith("[dev]\n") for text in seen))


class ScrubTest(unittest.TestCase):
    def test_every_string_of_an_answer_is_scrubbed(self):
        doc = {"a": [f"x {PASSWORD} y", {"b": PASSWORD}], "n": 1}
        self.assertEqual(scrub(doc, PASSWORD),
                         {"a": [f"x {SECRET_MARK} y", {"b": SECRET_MARK}], "n": 1})

    def test_a_short_password_is_a_word_and_is_not_scrubbed(self):
        self.assertEqual(scrub({"database": "admin"}, "admin"), {"database": "admin"})
        self.assertEqual(scrub("x", ""), "x")


class ClientTest(Tmp):
    def test_the_cli_runs_the_installed_module_on_the_copy_with_no_session(self):
        cli = FakeCli()
        client(self.tmp, cli).check_env()
        self.assertEqual(cli.calls, [["/app/.venv/bin/python", "-m", "denodo_cli", "env", "check",
                                      "--env", "dev"]])
        [seen] = cli.envs
        self.assertEqual(seen["DENODO_PROFILES"], str(self.tmp / "run" / "profiles.toml"))
        self.assertEqual(seen["HOME"], str(self.tmp / "run"))
        for name in ("PYTHONPATH", "DENODO_SESSION", "CLAUDE_CODE_SESSION_ID"):
            self.assertNotIn(name, seen)

    def test_the_commands_and_their_arguments(self):
        cli = FakeCli()
        denodo = client(self.tmp, cli)
        denodo.plan(Path("/f.vql"), DB)
        denodo.plan_text("SELECT 1", DB)
        denodo.plan_texts(["SELECT 1", "SELECT 2"], DB)
        denodo.run_file(Path("/f.vql"), DB)
        denodo.run_text("SELECT 1", DB, max_rows=5)
        denodo.run_texts(["SELECT 1", "SELECT 2"], DB)
        self.assertEqual([call[3:-2] for call in cli.calls], [
            ["vql", "plan", "/f.vql", "--database", DB],
            ["vql", "plan", "-e", "SELECT 1", "--database", DB],
            ["vql", "plan", "-e", "SELECT 1", "-e", "SELECT 2", "--database", DB],
            ["vql", "run", "/f.vql", "--database", DB, "--max-rows", "100"],
            ["vql", "run", "-e", "SELECT 1", "--database", DB, "--max-rows", "5"],
            ["vql", "run", "-e", "SELECT 1", "-e", "SELECT 2", "--database", DB, "--max-rows",
             "100", "--continue-on-error"]])

    def test_the_timeout_is_the_callers(self):
        seen = []

        def timed(argv, *, timeout, env=None):
            seen.append(timeout)
            return Ran(0, json.dumps({"ok": True}), "")

        profile, path = profile_and_file(self.tmp)
        Denodo(profile, path, timed, python="p").check_env()
        Denodo(profile, path, timed, python="p", timeout_s=7).check_env()
        self.assertEqual(seen, [300, 7])

    def test_the_password_never_leaves_in_an_answer(self):
        def leaky(argv, *, timeout, env=None):
            return Ran(1, json.dumps({"ok": False, "statements": [
                {"index": 0, "ok": False, "error": {"message": f"bad password {PASSWORD}"}}]}), "")

        profile, path = profile_and_file(self.tmp)
        doc = Denodo(profile, path, leaky, python="p").run_text("SELECT 1", DB)
        self.assertNotIn(PASSWORD, json.dumps(doc))
        self.assertIn(SECRET_MARK, json.dumps(doc))

    def test_a_password_across_the_cut_leaves_no_fragment(self):
        profile, path = profile_and_file(self.tmp)
        ran = Ran(1, "Traceback", "x" * 290 + PASSWORD + "y" * 5)
        with self.assertRaises(Unavailable) as caught:
            Denodo(profile, path, lambda argv, **k: ran, python="p").check_env()
        self.assertNotIn(PASSWORD[:6], str(caught.exception))
        self.assertNotIn(PASSWORD[-6:], str(caught.exception))

    def test_a_server_that_does_not_answer_is_unavailable(self):
        def down(argv, *, timeout, env=None):
            return Ran(1, json.dumps({"ok": False, "error": {"kind": "connection",
                                                             "message": "connection refused"}}), "")

        profile, path = profile_and_file(self.tmp)
        with self.assertRaisesRegex(Unavailable, "host.docker.internal:9996"):
            Denodo(profile, path, down, python="p").check_env()

    def test_no_json_a_missing_driver_and_json_that_is_no_object_are_unavailable(self):
        profile, path = profile_and_file(self.tmp)
        for ran, said in ((Ran(1, "Traceback", f"boom {PASSWORD}"), "no JSON"),
                          (Ran(3, json.dumps({"ok": False, "error": {
                              "kind": "environment", "message": "no psycopg2"}}), ""), "driver"),
                          (Ran(0, "[1]", ""), "no object")):
            with self.subTest(said=said), self.assertRaisesRegex(Unavailable, said) as caught:
                Denodo(profile, path, lambda argv, ran=ran, **k: ran, python="p").check_env()
            self.assertNotIn(PASSWORD, str(caught.exception))

    def test_a_usage_or_config_error_is_refused(self):
        profile, path = profile_and_file(self.tmp)
        ran = Ran(2, json.dumps({"ok": False, "error": {"kind": "usage", "message": "bad flag"}}), "")
        with self.assertRaisesRegex(Refused, "denodo_cli refused: bad flag"):
            Denodo(profile, path, lambda argv, **k: ran, python="p").check_env()

    def test_floats_from_the_server_become_decimal_strings(self):
        cli = FakeCli(rows=[[1.5, "x"]], columns=["amount", "name"])
        doc = client(self.tmp, cli).run_text("SELECT 1", DB)
        self.assertEqual(floats_in(doc), [])
        self.assertEqual(doc["statements"][0]["rows"], [["1.5", "x"]])

    def test_a_held_copy_is_private_and_beside_the_profile(self):
        denodo = client(self.tmp, FakeCli())
        held = denodo.hold(b"SELECT 1;")
        self.assertEqual(held.parent, self.tmp / "run")
        self.assertEqual(stat.S_IMODE(held.stat().st_mode), 0o600)
        self.assertEqual(held.read_bytes(), b"SELECT 1;")


if __name__ == "__main__":
    unittest.main()
