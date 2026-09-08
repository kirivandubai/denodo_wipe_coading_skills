import tempfile
import unittest
from pathlib import Path

from denodo_cli.commands.env import check_environment, init_environment, list_environments
from denodo_cli.profiles import Profile, load_profile
from denodo_cli.transports.base import HttpResult, VqlResult


def profile(**over):
    base = dict(name="dev", host="h", port=9996, database="admin", user="u", password="p",
                production=False, transport="vql_psycopg2", marketplace_url=None, marketplace_server_id=None)
    base.update(over)
    return Profile(**base)


class OkVql:
    def __init__(self, profile, database=None):
        pass

    def execute(self, statement):
        return VqlResult(statement=statement, columns=["v"], rows=[["# Generated with Denodo Platform 9.5.1."]])

    def close(self):
        pass


class OkRest:
    calls = []

    def __init__(self, profile):
        pass

    def call(self, method, path, **kw):
        OkRest.calls.append(path)
        return HttpResult(status=200, body={"count": 3}, headers={}, elapsed_ms=1)


class ListTest(unittest.TestCase):
    def test_list_reports_profiles_without_passwords(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profiles.toml"
            path.write_text('[dev]\nhost="h"\nuser="u"\npassword="s3cret"\n')
            doc, code = list_environments(path)
        self.assertEqual(code, 0)
        self.assertEqual(doc["command"], "env list")
        self.assertEqual(doc["profiles"][0]["name"], "dev")
        self.assertNotIn("s3cret", str(doc))
        self.assertEqual(doc["path"], str(path))


class CheckTest(unittest.TestCase):
    def setUp(self):
        OkRest.calls.clear()

    def test_vdp_only_when_no_marketplace_url(self):
        doc, code = check_environment(profile(), vql_factory=OkVql, rest_factory=OkRest)
        self.assertEqual(code, 0)
        self.assertTrue(doc["ok"])
        self.assertTrue(doc["vdp"]["ok"])
        self.assertEqual(doc["vdp"]["server_version"], "9.5.1")
        self.assertIsNone(doc["marketplace"])
        self.assertEqual(OkRest.calls, [])

    def test_marketplace_is_checked_when_configured(self):
        doc, code = check_environment(profile(marketplace_url="http://mp/ctx"), vql_factory=OkVql, rest_factory=OkRest)
        self.assertEqual(code, 0)
        self.assertTrue(doc["marketplace"]["ok"])
        self.assertEqual(doc["marketplace"]["status"], 200)
        self.assertIn("/public/api/tags/count", OkRest.calls)

    def test_vdp_failure_is_reported_and_marketplace_still_checked(self):
        class BadVql(OkVql):
            def __init__(self, profile, database=None):
                raise OSError("connection refused")

        doc, code = check_environment(profile(marketplace_url="http://mp/ctx"), vql_factory=BadVql, rest_factory=OkRest)
        self.assertEqual(code, 1)
        self.assertFalse(doc["ok"])
        self.assertFalse(doc["vdp"]["ok"])
        self.assertIn("connection refused", doc["vdp"]["error"]["message"])
        self.assertTrue(doc["marketplace"]["ok"])

    def test_marketplace_401_is_a_failure(self):
        class Unauthorized(OkRest):
            def call(self, method, path, **kw):
                return HttpResult(status=401, body=None, headers={}, elapsed_ms=1)

        doc, code = check_environment(profile(marketplace_url="http://mp/ctx"), vql_factory=OkVql, rest_factory=Unauthorized)
        self.assertEqual(code, 1)
        self.assertFalse(doc["marketplace"]["ok"])
        self.assertEqual(doc["marketplace"]["status"], 401)


class InitTest(unittest.TestCase):
    def test_interactive_init_writes_profile_and_never_echoes_password(self):
        answers = iter(["qa", "vdp.example.test", "", "", "carol", "y", "http://mp.example.test/denodo-data-catalog", ""])
        secrets = iter(["hunter2"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profiles.toml"
            doc, code = init_environment(path, ask=lambda prompt, default="": next(answers) or default,
                                         ask_secret=lambda prompt: next(secrets))
            self.assertEqual(code, 0)
            self.assertNotIn("hunter2", str(doc))
            written = load_profile("qa", path)
        self.assertEqual(written.password, "hunter2")
        self.assertEqual(written.port, 9996)
        self.assertEqual(written.database, "admin")
        self.assertTrue(written.production)
        self.assertEqual(written.marketplace_url, "http://mp.example.test/denodo-data-catalog")
        self.assertIsNone(written.marketplace_server_id)
        self.assertEqual(doc["connection"]["name"], "qa")
        self.assertEqual(doc["path"], str(path))

    def test_init_rejects_empty_password(self):
        answers = iter(["qa", "h", "", "", "u", "n", "", ""])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profiles.toml"
            doc, code = init_environment(path, ask=lambda prompt, default="": next(answers) or default,
                                         ask_secret=lambda prompt: "")
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "usage")
