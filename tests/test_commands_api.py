import json
import tempfile
import unittest
from pathlib import Path

from denodo_cli.commands.api import api_call, parse_multipart_specs, parse_params
from denodo_cli.profiles import Profile
from denodo_cli.transports.base import HttpResult


def profile(**over):
    base = dict(name="dev", host="h", port=9996, database="admin", user="u", password="p",
                production=False, transport="vql_psycopg2",
                marketplace_url="http://mp.example.test/denodo-data-catalog", marketplace_server_id=None)
    base.update(over)
    return Profile(**base)


class FakeRest:
    calls = []
    status = 200
    body = {"id": 1}

    def __init__(self, profile):
        if not profile.marketplace_url:
            raise ValueError("profile has no marketplace_url")

    def call(self, method, path, **kw):
        FakeRest.calls.append((method, path, kw))
        return HttpResult(status=FakeRest.status, body=FakeRest.body, headers={"Content-Type": "application/json"}, elapsed_ms=12)


class ApiCallTest(unittest.TestCase):
    def setUp(self):
        FakeRest.calls.clear()
        FakeRest.status, FakeRest.body = 200, {"id": 1}

    def call(self, method="GET", path="/public/api/tags", **kw):
        kw.setdefault("transport_factory", FakeRest)
        return api_call(profile(**kw.pop("profile_over", {})), method, path, **kw)

    def test_successful_call_reports_status_and_body(self):
        doc, code = self.call()
        self.assertEqual(code, 0)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["command"], "api")
        self.assertEqual(doc["method"], "GET")
        self.assertEqual(doc["path"], "/public/api/tags")
        self.assertEqual(doc["status"], 200)
        self.assertEqual(doc["body"], {"id": 1})
        self.assertEqual(doc["elapsed_ms"], 12)
        self.assertIsNone(doc["destructive"])

    def test_non_2xx_is_not_ok_and_keeps_body_separate(self):
        FakeRest.status, FakeRest.body = 409, None
        doc, code = self.call("POST", "/public/api/tags", json_body={"name": "t"})
        self.assertEqual(code, 1)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["status"], 409)
        self.assertIsNone(doc["body"])

    def test_arguments_reach_the_transport(self):
        self.call("POST", "/public/api/tags", json_body={"a": 1}, params={"serverId": 2}, timeout=7)
        method, path, kw = FakeRest.calls[0]
        self.assertEqual((method, path), ("POST", "/public/api/tags"))
        self.assertEqual(kw["json_body"], {"a": 1})
        self.assertEqual(kw["params"], {"serverId": 2})
        self.assertEqual(kw["timeout"], 7)

    def test_destructive_call_is_flagged(self):
        doc, _ = self.call("DELETE", "/public/api/tags/5")
        self.assertEqual(doc["destructive"], "delete")

    def test_destructive_on_production_is_refused(self):
        doc, code = self.call("POST", "/public/api/tags/vdp/synchronize", profile_over={"production": True})
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "refused")
        self.assertIn("--allow-destructive", doc["error"]["message"])
        self.assertEqual(FakeRest.calls, [])

    def test_destructive_on_production_with_flag(self):
        _, code = self.call("DELETE", "/public/api/tags/5", profile_over={"production": True}, allow_destructive=True)
        self.assertEqual(code, 0)
        self.assertEqual(len(FakeRest.calls), 1)

    def test_missing_marketplace_url_is_a_config_error(self):
        doc, code = self.call(profile_over={"marketplace_url": None})
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["kind"], "config")
        self.assertIn("marketplace_url", doc["error"]["message"])

    def test_network_failure_is_a_connection_error(self):
        class Dead(FakeRest):
            def call(self, *a, **kw):
                raise OSError("connection refused")

        doc, code = self.call(transport_factory=Dead)
        self.assertEqual(code, 1)
        self.assertEqual(doc["error"]["kind"], "connection")


class ArgumentParsingTest(unittest.TestCase):
    def test_params(self):
        self.assertEqual(parse_params(["offset=0", "nameFilter=a=b"]), {"offset": "0", "nameFilter": "a=b"})

    def test_param_without_equals_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_params(["offset"])

    def test_multipart_file_and_inline_json_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "icon.svg"
            icon.write_bytes(b"<svg/>")
            parts = parse_multipart_specs([f"icon=@{icon}", 'request=json:{"name": "P"}'])
        self.assertEqual(parts["icon"], ("icon.svg", b"<svg/>", "image/svg+xml"))
        self.assertEqual(parts["request"][0], None)
        self.assertEqual(json.loads(parts["request"][1]), {"name": "P"})
        self.assertEqual(parts["request"][2], "application/json")

    def test_multipart_file_with_explicit_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            blob = Path(tmp) / "icon.bin"
            blob.write_bytes(b"x")
            parts = parse_multipart_specs([f"icon=@{blob};image/png"])
        self.assertEqual(parts["icon"], ("icon.bin", b"x", "image/png"))

    def test_multipart_plain_text_part(self):
        self.assertEqual(parse_multipart_specs(["name=hello"])["name"], (None, b"hello", "text/plain"))

    def test_multipart_missing_file(self):
        with self.assertRaises(ValueError):
            parse_multipart_specs(["icon=@/nonexistent/icon.svg"])
