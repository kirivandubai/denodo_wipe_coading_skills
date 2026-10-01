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


def scripted(answers, seen=None):
    """A VQL transport that answers by the start of the statement (or a substring for
    ``CONTEXT``): a VqlResult is returned, an exception raised; anything else is OkVql."""
    class Scripted(OkVql):
        def execute(self, statement):
            if seen is not None:
                seen.append(statement)
            for key, answer in answers.items():
                if statement.startswith(key) or (key == "CONTEXT" and "CONTEXT" in statement):
                    if isinstance(answer, Exception):
                        raise answer
                    return answer
            return super().execute(statement)
    return Scripted


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

    def test_admin_and_impersonation_are_reported(self):
        doc, code = check_environment(profile(), vql_factory=scripted({
            "DESC USER u": VqlResult("", ["name", "description", "admin", "adminglobal"],
                                     [["u", None, "true", "true"]]),
        }), rest_factory=OkRest)
        self.assertEqual(code, 0)
        self.assertIs(doc["vdp"]["admin"], True)
        self.assertIs(doc["vdp"]["impersonation"], True)

    def test_standard_user_without_the_impersonator_role(self):
        doc, code = check_environment(profile(), vql_factory=scripted({
            "DESC USER u": VqlResult("", ["name", "description", "admin", "adminglobal"],
                                     [["u", "analyst", "false", "false"]]),
            "CONTEXT": RuntimeError("This user cannot impersonate. Only users with role "
                                    "'impersonator' can impersonate."),
        }), rest_factory=OkRest)
        self.assertEqual(code, 0)
        self.assertTrue(doc["ok"])
        self.assertIs(doc["vdp"]["admin"], False)
        self.assertIs(doc["vdp"]["impersonation"], False)

    def test_unknown_when_the_server_does_not_say(self):
        # a user known only to LDAP or an identity provider has no DESC USER; any other refusal
        # of the impersonated read says nothing about the role either
        doc, code = check_environment(profile(), vql_factory=scripted({
            "DESC USER u": RuntimeError("Error loading user 'u'"),
            "CONTEXT": RuntimeError("The user 'u' does not exist."),
        }), rest_factory=OkRest)
        self.assertEqual(code, 0)
        self.assertTrue(doc["vdp"]["ok"])
        self.assertIsNone(doc["vdp"]["admin"])
        self.assertIsNone(doc["vdp"]["impersonation"])

    def test_user_name_is_quoted_as_an_identifier_and_as_a_literal(self):
        seen = []
        check_environment(profile(user="o'neil.ops"), vql_factory=scripted({}, seen=seen), rest_factory=OkRest)
        self.assertIn('DESC USER "o\'neil.ops"', seen)
        self.assertTrue(any("'impersonate_user' = 'o''neil.ops'" in s for s in seen), seen)

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
