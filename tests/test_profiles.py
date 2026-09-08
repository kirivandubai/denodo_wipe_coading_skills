import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from denodo_cli.profiles import (
    Profile,
    ProfileError,
    list_profiles,
    load_profile,
    profiles_path,
    write_profile,
)

MINIMAL = """
[dev]
host = "vdp.example.test"
user = "alice"
password = "s3cret"
"""

FULL = """
[prod]
host = "vdp.example.test"
port = 9997
database = "corp"
user = "bob"
password_env = "DENODO_PROD_PASSWORD"
production = true
transport = "vql_psycopg2"
marketplace_url = "http://mp.example.test:9090/denodo-data-catalog/"
marketplace_server_id = 2
"""


class ProfilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "profiles.toml"

    def write(self, text):
        self.path.write_text(text)

    def test_minimal_profile_gets_defaults(self):
        self.write(MINIMAL)
        p = load_profile("dev", self.path)
        self.assertEqual(p.name, "dev")
        self.assertEqual(p.port, 9996)
        self.assertEqual(p.database, "admin")
        self.assertFalse(p.production)
        self.assertEqual(p.transport, "vql_psycopg2")
        self.assertIsNone(p.marketplace_url)
        self.assertIsNone(p.marketplace_server_id)
        self.assertEqual(p.password, "s3cret")

    def test_full_profile_and_password_from_environment(self):
        self.write(FULL)
        with mock.patch.dict(os.environ, {"DENODO_PROD_PASSWORD": "from-env"}):
            p = load_profile("prod", self.path)
        self.assertEqual(p.password, "from-env")
        self.assertTrue(p.production)
        self.assertEqual(p.port, 9997)
        self.assertEqual(p.marketplace_url, "http://mp.example.test:9090/denodo-data-catalog")
        self.assertEqual(p.marketplace_server_id, 2)

    def test_password_env_missing_variable_is_an_error(self):
        self.write(FULL)
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProfileError) as ctx:
                load_profile("prod", self.path)
        self.assertIn("DENODO_PROD_PASSWORD", str(ctx.exception))

    def test_missing_file(self):
        with self.assertRaises(ProfileError) as ctx:
            load_profile("dev", self.path)
        self.assertIn(str(self.path), str(ctx.exception))
        self.assertIn("env init", str(ctx.exception))

    def test_unknown_profile_lists_available(self):
        self.write(MINIMAL)
        with self.assertRaises(ProfileError) as ctx:
            load_profile("staging", self.path)
        self.assertIn("staging", str(ctx.exception))
        self.assertIn("dev", str(ctx.exception))

    def test_missing_required_field(self):
        self.write('[dev]\nhost = "h"\nuser = "u"\n')
        with self.assertRaises(ProfileError) as ctx:
            load_profile("dev", self.path)
        self.assertIn("password", str(ctx.exception))

    def test_unknown_transport_is_rejected(self):
        self.write(MINIMAL.replace('password = "s3cret"', 'password = "x"\ntransport = "carrier_pigeon"'))
        with self.assertRaises(ProfileError):
            load_profile("dev", self.path)

    def test_env_var_overrides_default_path(self):
        with mock.patch.dict(os.environ, {"DENODO_PROFILES": str(self.path)}):
            self.assertEqual(profiles_path(), self.path)

    def test_default_path_is_under_home(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(profiles_path(), Path.home() / ".denodo" / "profiles.toml")

    def test_list_profiles_never_exposes_password(self):
        self.write(MINIMAL + FULL)
        listed = list_profiles(self.path)
        self.assertEqual([p["name"] for p in listed], ["dev", "prod"])
        for entry in listed:
            self.assertNotIn("password", entry)
            self.assertNotIn("s3cret", repr(entry))
        self.assertTrue(listed[1]["production"])
        self.assertEqual(listed[0]["host"], "vdp.example.test")

    def test_list_profiles_without_file_is_empty(self):
        self.assertEqual(list_profiles(self.path), [])

    def test_write_profile_appends_section_and_restricts_permissions(self):
        self.write(MINIMAL)
        write_profile(
            self.path,
            Profile(name="qa", host="qa.example.test", port=9996, database="admin", user="carol",
                    password="p'w", production=False, transport="vql_psycopg2",
                    marketplace_url="http://qa:9090/denodo-data-catalog", marketplace_server_id=None),
        )
        self.assertEqual(load_profile("dev", self.path).password, "s3cret")
        qa = load_profile("qa", self.path)
        self.assertEqual(qa.password, "p'w")
        self.assertEqual(qa.marketplace_url, "http://qa:9090/denodo-data-catalog")
        mode = stat.S_IMODE(self.path.stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_write_profile_creates_parent_directory(self):
        nested = Path(self.tmp.name) / "deep" / "profiles.toml"
        write_profile(nested, Profile(name="dev", host="h", port=1, database="admin", user="u",
                                      password="p", production=True, transport="vql_psycopg2",
                                      marketplace_url=None, marketplace_server_id=None))
        self.assertTrue(load_profile("dev", nested).production)

    def test_write_profile_refuses_duplicate_name(self):
        self.write(MINIMAL)
        with self.assertRaises(ProfileError):
            write_profile(self.path, Profile(name="dev", host="h", port=1, database="admin", user="u",
                                             password="p", production=False, transport="vql_psycopg2",
                                             marketplace_url=None, marketplace_server_id=None))


if __name__ == "__main__":
    unittest.main()
