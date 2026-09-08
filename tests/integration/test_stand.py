"""Integration tests against a live Denodo stand.

Skipped unless ``DENODO_TEST_ENV`` names a profile in ``~/.denodo/profiles.toml``
(or ``DENODO_PROFILES``). The profile must not be marked production. Everything is
created in the ``denodo_skills_test`` database with a ``t5_`` prefix and removed.

Run:  DENODO_TEST_ENV=dev uv run --with denodo-sqlalchemy --with psycopg2-binary \
          python -m unittest tests.integration.test_stand -v
"""

from __future__ import annotations

import os
import unittest

from denodo_cli.profiles import load_profile

ENV = os.environ.get("DENODO_TEST_ENV")
TEST_DB = "denodo_skills_test"


def _profile():
    profile = load_profile(ENV)
    if profile.production:
        raise unittest.SkipTest("refusing to run integration tests on a production profile")
    return profile


@unittest.skipUnless(ENV, "DENODO_TEST_ENV not set")
class VqlPsycopg2TransportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from denodo_cli.transports.vql_psycopg2 import VqlPsycopg2Transport

        cls.profile = _profile()
        admin = VqlPsycopg2Transport(cls.profile)
        admin.execute(f"CREATE OR REPLACE DATABASE {TEST_DB} 'T5 integration tests'")
        admin.close()
        cls.transport = VqlPsycopg2Transport(cls.profile, database=TEST_DB)

    @classmethod
    def tearDownClass(cls):
        cls.transport.execute("DROP FOLDER IF EXISTS '/t5'")
        cls.transport.close()

    def test_select_returns_columns_and_rows(self):
        result = self.transport.execute("SELECT 1 AS answer FROM DUAL()")
        self.assertEqual(result.columns, ["answer"])
        self.assertEqual(result.rows, [[1]])

    def test_ddl_returns_no_result_set_and_is_autocommitted(self):
        from denodo_cli.transports.vql_psycopg2 import VqlPsycopg2Transport

        result = self.transport.execute("CREATE OR REPLACE FOLDER '/t5'")
        self.assertIsNone(result.rows)
        other = VqlPsycopg2Transport(self.profile, database=TEST_DB)
        try:
            seen = other.execute(
                f"SELECT name FROM GET_ELEMENTS() WHERE input_database_name = '{TEST_DB}' AND type = 'folder'"
            )
        finally:
            other.close()
        self.assertIn(["t5"], seen.rows)  # GET_ELEMENTS() reports folder names without the leading slash

    def test_percent_sign_in_vql_passes_through(self):
        result = self.transport.execute("SELECT 'New%' AS pattern FROM DUAL() WHERE 'New York' LIKE 'New%'")
        self.assertEqual(result.rows, [["New%"]])

    def test_server_error_surfaces_as_exception_with_server_text(self):
        with self.assertRaises(Exception) as ctx:
            self.transport.execute("SELEKT 1 FROM DUAL()")
        self.assertIn("Syntax error", str(ctx.exception))

    def test_session_survives_an_error(self):
        with self.assertRaises(Exception):
            self.transport.execute("SELEKT 1 FROM DUAL()")
        self.assertEqual(self.transport.execute("SELECT 2 AS n FROM DUAL()").rows, [[2]])
