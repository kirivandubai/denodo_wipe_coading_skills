import sys
import unittest

from denodo_cli import transports
from denodo_cli.transports.base import HttpResult, VqlResult


class RegistryTest(unittest.TestCase):
    def test_known_names(self):
        self.assertEqual(transports.vql_transport_names(), ["vql_psycopg2", "vql_flightsql"])

    def test_unknown_name_lists_known_ones(self):
        with self.assertRaises(KeyError) as ctx:
            transports.get_vql_transport("carrier_pigeon")
        self.assertIn("vql_psycopg2", str(ctx.exception))

    def test_lookup_is_lazy_sqlalchemy_not_imported_by_registry(self):
        # The registry itself must be importable without the driver stack installed.
        self.assertNotIn("sqlalchemy", sys.modules)

    def test_flightsql_is_not_part_of_v1(self):
        cls = transports.get_vql_transport("vql_flightsql")
        with self.assertRaises(NotImplementedError) as ctx:
            cls(profile=None)
        self.assertIn("v1", str(ctx.exception))


class ResultTypesTest(unittest.TestCase):
    def test_vql_result_fields(self):
        r = VqlResult(statement="SELECT 1", columns=["1"], rows=[[1]])
        self.assertEqual(r.row_count, 1)
        self.assertIsNone(VqlResult(statement="CREATE X", columns=None, rows=None).row_count)

    def test_http_result_ok_follows_status(self):
        self.assertTrue(HttpResult(status=201, body=None, headers={}, elapsed_ms=1).ok)
        self.assertFalse(HttpResult(status=409, body=None, headers={}, elapsed_ms=1).ok)
