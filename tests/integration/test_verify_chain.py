# tests/integration/test_verify_chain.py
"""The v1 chain against a live stand.

Skipped unless ``DENODO_TEST_ENV`` names a non-production profile. Creates and drops
``denodo_skills_test`` and the two ``verify_`` tags — nothing else.

Run:  DENODO_TEST_ENV=lab PYTHONPATH=scripts uv run --with denodo-sqlalchemy \
          --with psycopg2-binary python -m unittest tests.integration.test_verify_chain -v
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from denodo_cli.commands.verify import load_chain, run_chain
from denodo_cli.profiles import load_profile
from denodo_cli.transports import get_vql_transport

ENV = os.environ.get("DENODO_TEST_ENV")
REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(ENV, "DENODO_TEST_ENV not set")
class VerifyChainTest(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile(ENV)
        if self.profile.production:
            self.skipTest("refusing to run the chain on a production profile")
        self.chain = load_chain(REPO / "verification" / "chain.toml")

    def test_the_whole_chain_passes_and_cleans_up(self):
        doc, code = run_chain(self.profile, self.chain, root=REPO,
                              vql_factory=get_vql_transport(self.profile.transport))
        self.assertEqual(code, 0, [s for s in doc["steps"] if not s["ok"]])
        self.assertGreaterEqual(doc["summary"]["verified"], 6)
        self.assertEqual(doc["summary"]["failed"], 0)
        self.assertTrue(doc["cleanup"]["ran"])
        self.assertTrue(all(s["ok"] for s in doc["cleanup"]["statements"]))

    def test_the_test_database_is_gone_afterwards(self):
        transport = get_vql_transport(self.profile.transport)(self.profile)
        try:
            result = transport.execute(
                "SELECT db_name FROM GET_DATABASES() WHERE db_name = 'denodo_skills_test'")
        finally:
            transport.close()
        self.assertEqual(result.rows, [])

    def test_a_second_run_is_green_too(self):
        doc, code = run_chain(self.profile, self.chain, root=REPO,
                              vql_factory=get_vql_transport(self.profile.transport))
        self.assertEqual(code, 0, [s for s in doc["steps"] if not s["ok"]])
