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

from denodo_cli.commands.secret import quote_literal
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

    def test_a_password_survives_quoting_into_a_vql_literal(self):
        """What ``secret encrypt`` puts around a password has to reach the server intact.

        The server is the only authority on the escaping rule, so the check is a round trip
        through its parser: doubling the single quote is enough, and a backslash is literal.
        Drop the doubling in ``quote_literal`` and the first case is a syntax error.
        """
        for password in ("pa'ss", "back\\slash", "per%cent", 'a"b', "zwei'wörter \\ 100%", "  spaced  "):
            with self.subTest(password=password):
                result = self.transport.execute(f"SELECT {quote_literal(password)} AS p FROM DUAL()")
                self.assertEqual(result.rows, [[password]])

    def test_encrypt_password_is_salted(self):
        """Two runs on one password differ — so a ciphertext can never be compared, only used."""
        ciphers = {self.transport.execute("ENCRYPT_PASSWORD 'hunter2'").rows[0][0] for _ in range(2)}
        self.assertEqual(len(ciphers), 2)


@unittest.skipUnless(ENV, "DENODO_TEST_ENV not set")
class RestTransportStandTest(unittest.TestCase):
    """Needs ``marketplace_url`` in the profile; creates and removes a ``t5_`` tag."""

    @classmethod
    def setUpClass(cls):
        from denodo_cli.transports.api_rest import RestTransport

        cls.profile = _profile()
        if not cls.profile.marketplace_url:
            raise unittest.SkipTest("profile has no marketplace_url")
        cls.rest = RestTransport(cls.profile)
        for tag in cls.rest.call("GET", "/public/api/tags").body or []:
            if tag.get("name") == "t5_it_tag":
                cls.rest.call("DELETE", f"/public/api/tags/{tag['id']}")

    def test_basic_auth_is_accepted(self):
        result = self.rest.call("GET", "/public/api/tags/count")
        self.assertEqual(result.status, 200)
        self.assertIsInstance(result.body, int)

    def test_wrong_server_id_is_401_with_code(self):
        result = self.rest.call("GET", "/public/api/tags/count", params={"serverId": 999999})
        self.assertEqual(result.status, 401)
        self.assertEqual(result.body["code"], "AUTHENTICATION_SERVER_NOT_FOUND")

    def test_create_duplicate_and_delete_tag(self):
        body = {"name": "t5_it_tag", "description": "T5 integration test", "descriptionType": "TEXT"}
        created = self.rest.call("POST", "/public/api/tags", json_body=body)
        self.assertEqual(created.status, 200, created.body)
        tag_id = created.body["id"]
        try:
            duplicate = self.rest.call("POST", "/public/api/tags", json_body=body)
            self.assertEqual(duplicate.status, 409)
            self.assertIsNone(duplicate.body)  # empty body: status must be reported on its own
        finally:
            deleted = self.rest.call("DELETE", f"/public/api/tags/{tag_id}")
        self.assertEqual(deleted.status, 200)


@unittest.skipUnless(ENV, "DENODO_TEST_ENV not set")
class LedgerAndPlanStandTest(unittest.TestCase):
    """T39: the ledger against a live catalog. Two sessions in a temporary directory — "mine" and a
    colleague's — over views of a ``t39_`` folder in ``denodo_skills_test``, removed at the end."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        from pathlib import Path

        from denodo_cli.ledger import Ledger
        from denodo_cli.transports.vql_psycopg2 import VqlPsycopg2Transport

        cls.profile = _profile()
        cls.factory = VqlPsycopg2Transport
        cls.tmp = tempfile.TemporaryDirectory()
        cls.mine = Ledger(Path(cls.tmp.name), "t39-mine")
        cls.colleague = Ledger(Path(cls.tmp.name), "t39-colleague")
        admin = VqlPsycopg2Transport(cls.profile)
        admin.execute(f"CREATE OR REPLACE DATABASE {TEST_DB} 'T5 integration tests'")
        admin.close()

    @classmethod
    def tearDownClass(cls):
        transport = cls.factory(cls.profile, database=TEST_DB)
        for statement in ("DROP VIEW IF EXISTS t39_report", "DROP VIEW IF EXISTS t39_theirs",
                          "DROP VIEW IF EXISTS t39_mine2", "DROP VIEW IF EXISTS t39_mine",
                          "DROP FOLDER IF EXISTS '/t39'"):
            transport.execute(statement)
        transport.close()
        cls.tmp.cleanup()

    def run_as(self, ledger, *statements):
        from denodo_cli.commands.vql import run_statements

        doc, code = run_statements(self.profile, list(statements), transport_factory=self.factory, max_rows=10,
                                   database=TEST_DB, ledger=ledger, source="it.vql")
        self.assertEqual(code, 0, doc)
        return doc

    def plan(self, *statements):
        from denodo_cli.commands.plan import plan_input

        doc, code = plan_input(self.profile, list(statements), transport_factory=self.factory, database=TEST_DB,
                               source=None, ledger=self.mine, session_source="DENODO_SESSION")
        self.assertEqual(code, 0, doc)
        return doc["statements"]

    def test_own_and_colleague_objects(self):
        mine = self.run_as(self.mine, "CREATE OR REPLACE FOLDER '/t39'",
                           "CREATE OR REPLACE VIEW t39_mine FOLDER = '/t39' AS SELECT 1 AS a FROM Dual()")
        # the folder may already be this session's from the other test: it is recorded once, when new
        self.assertIn(f"{TEST_DB}.t39_mine", mine["ledger"]["recorded"])
        self.run_as(self.colleague,
                    "CREATE OR REPLACE VIEW t39_theirs FOLDER = '/t39' AS SELECT 2 AS b FROM Dual()",
                    "CREATE OR REPLACE VIEW t39_report FOLDER = '/t39' AS SELECT a FROM t39_mine")
        entries = self.plan("CREATE OR REPLACE VIEW t39_mine FOLDER = '/t39' AS SELECT 1 AS a, 2 AS c FROM Dual()",
                            "CREATE OR REPLACE VIEW t39_theirs FOLDER = '/t39' AS SELECT 3 AS b FROM Dual()",
                            "ALTER VIEW t39_mine CACHE FULL",
                            "DROP VIEW t39_theirs")
        self.assertEqual([e["own"] for e in entries], [True, False, True, False])
        self.assertEqual([e["needs_yes"] for e in entries], [False, True, True, True])
        self.assertIn("t39_report", entries[2]["why"])   # the colleague's view reads it

    def test_identity_survives_a_rename_and_not_a_recreate(self):
        self.run_as(self.mine, "CREATE OR REPLACE FOLDER '/t39'",
                    "CREATE OR REPLACE VIEW t39_mine2 FOLDER = '/t39' AS SELECT 1 AS a FROM Dual()")
        self.run_as(self.mine, "ALTER VIEW t39_mine2 RENAME t39_mine2b")
        self.assertTrue(self.plan("ALTER VIEW t39_mine2b CACHE OFF")[0]["own"])
        self.run_as(self.colleague, "DROP VIEW t39_mine2b",
                    "CREATE VIEW t39_mine2b FOLDER = '/t39' AS SELECT 9 AS a FROM Dual()")
        self.assertFalse(self.plan("ALTER VIEW t39_mine2b CACHE OFF")[0]["own"])
        self.run_as(self.colleague, "DROP VIEW t39_mine2b")
