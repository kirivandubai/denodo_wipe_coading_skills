import datetime as dt
import decimal
import json
import unittest

from denodo_cli.output import envelope, rows_payload, to_json
from denodo_cli.profiles import Profile


def profile(**over):
    base = dict(name="dev", host="h", port=9996, database="admin", user="u", password="secret",
                production=False, transport="vql_psycopg2", marketplace_url=None, marketplace_server_id=None)
    base.update(over)
    return Profile(**base)


class EnvelopeTest(unittest.TestCase):
    def test_envelope_carries_env_facts_but_not_password(self):
        doc = envelope(True, profile(production=True), "vql run", statements=[])
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["command"], "vql run")
        self.assertEqual(doc["env"], {"name": "dev", "production": True, "transport": "vql_psycopg2", "database": "admin"})
        self.assertNotIn("secret", to_json(doc))
        self.assertEqual(doc["statements"], [])

    def test_env_database_follows_the_override(self):
        # agents are told to read env to know where they are connected; --database changes that
        doc = envelope(True, profile(), "vql run", database="sales_analytics", statements=[])
        self.assertEqual(doc["env"]["database"], "sales_analytics")

    def test_env_database_falls_back_to_the_profile(self):
        doc = envelope(True, profile(), "vql run", database=None, statements=[])
        self.assertEqual(doc["env"]["database"], "admin")

    def test_envelope_without_profile(self):
        doc = envelope(False, None, "env list", error={"kind": "config", "message": "x"})
        self.assertIsNone(doc["env"])
        self.assertEqual(doc["error"]["kind"], "config")


class RowsPayloadTest(unittest.TestCase):
    def test_rows_are_truncated_to_max_rows(self):
        payload = rows_payload(["n"], [[1], [2], [3]], max_rows=2)
        self.assertEqual(payload["rows"], [[1], [2]])
        self.assertEqual(payload["row_count"], 3)
        self.assertTrue(payload["truncated"])
        self.assertEqual(payload["columns"], ["n"])

    def test_small_result_is_not_truncated(self):
        payload = rows_payload(["n"], [[1]], max_rows=10)
        self.assertFalse(payload["truncated"])
        self.assertEqual(payload["row_count"], 1)

    def test_no_result_set(self):
        payload = rows_payload(None, None, max_rows=10)
        self.assertEqual(payload, {"columns": None, "rows": None, "row_count": None, "truncated": False})

    def test_non_json_values_become_strings(self):
        rows = [[decimal.Decimal("1.50"), dt.datetime(2026, 9, 8, 10, 0), b"\x00\x01", None]]
        payload = rows_payload(["d", "t", "b", "n"], rows, max_rows=5)
        encoded = json.loads(to_json(payload))
        self.assertEqual(encoded["rows"][0], ["1.50", "2026-09-08T10:00:00", "0001", None])
