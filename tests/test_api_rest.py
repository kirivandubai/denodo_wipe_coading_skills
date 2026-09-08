import base64
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from denodo_cli.profiles import Profile
from denodo_cli.transports.api_rest import RestTransport

RECEIVED = []


class Handler(BaseHTTPRequestHandler):
    def _respond(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        RECEIVED.append({
            "method": self.command, "path": self.path, "headers": dict(self.headers), "body": body,
        })
        if self.path.startswith("/ctx/empty-409"):
            self.send_response(409)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path.startswith("/ctx/text"):
            payload = b"plain text, not json"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        payload = json.dumps({"echo": self.path, "method": self.command}).encode()
        self.send_response(201 if self.command == "POST" else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", "JSESSIONID=abc; Path=/")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_DELETE = _respond

    def log_message(self, *args):  # keep test output clean
        pass


class RestTransportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/ctx"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        RECEIVED.clear()

    def profile(self, server_id=None):
        return Profile(name="dev", host="h", port=9996, database="admin", user="alice", password="pw:1",
                       production=False, transport="vql_psycopg2", marketplace_url=self.base,
                       marketplace_server_id=server_id)

    def test_basic_auth_on_every_request_and_no_cookie_reuse(self):
        t = RestTransport(self.profile())
        t.call("GET", "/public/api/tags")
        t.call("GET", "/public/api/tags")
        expected = "Basic " + base64.b64encode(b"alice:pw:1").decode()
        for req in RECEIVED:
            self.assertEqual(req["headers"]["Authorization"], expected)
            self.assertNotIn("Cookie", req["headers"])

    def test_server_id_from_profile_is_added_unless_given(self):
        t = RestTransport(self.profile(server_id=7))
        t.call("GET", "/public/api/tags")
        t.call("GET", "/public/api/tags", params={"serverId": 9})
        self.assertEqual(RECEIVED[0]["path"], "/ctx/public/api/tags?serverId=7")
        self.assertEqual(RECEIVED[1]["path"], "/ctx/public/api/tags?serverId=9")

    def test_no_server_id_when_profile_has_none(self):
        RestTransport(self.profile()).call("GET", "/public/api/tags", params={"nameFilter": "a b"})
        self.assertEqual(RECEIVED[0]["path"], "/ctx/public/api/tags?nameFilter=a+b")

    def test_json_body_and_parsed_response(self):
        result = RestTransport(self.profile()).call("POST", "/public/api/tags", json_body={"name": "t"})
        self.assertEqual(result.status, 201)
        self.assertTrue(result.ok)
        self.assertEqual(result.body, {"echo": "/ctx/public/api/tags", "method": "POST"})
        self.assertEqual(RECEIVED[0]["headers"]["Content-Type"], "application/json")
        self.assertEqual(json.loads(RECEIVED[0]["body"]), {"name": "t"})
        self.assertIn("Set-Cookie", result.headers)
        self.assertGreaterEqual(result.elapsed_ms, 0)

    def test_empty_error_body_gives_status_and_none(self):
        result = RestTransport(self.profile()).call("POST", "/empty-409", json_body={})
        self.assertEqual(result.status, 409)
        self.assertFalse(result.ok)
        self.assertIsNone(result.body)

    def test_non_json_body_is_returned_as_text(self):
        result = RestTransport(self.profile()).call("GET", "/text")
        self.assertEqual(result.body, "plain text, not json")

    def test_multipart_request(self):
        parts = {
            "request": (None, json.dumps({"name": "P"}).encode(), "application/json"),
            "icon": ("icon.svg", b"<svg/>", "image/svg+xml"),
        }
        RestTransport(self.profile()).call("POST", "/public/api/external-providers-types", multipart=parts)
        req = RECEIVED[0]
        ctype = req["headers"]["Content-Type"]
        self.assertTrue(ctype.startswith("multipart/form-data; boundary="))
        boundary = ctype.split("boundary=")[1].encode()
        body = req["body"]
        self.assertEqual(body.count(b"--" + boundary), 3)  # two parts + closing
        self.assertIn(b'name="request"\r\nContent-Type: application/json\r\n\r\n{"name": "P"}', body)
        self.assertIn(b'name="icon"; filename="icon.svg"\r\nContent-Type: image/svg+xml\r\n\r\n<svg/>', body)

    def test_path_may_be_given_with_or_without_leading_slash(self):
        t = RestTransport(self.profile())
        t.call("GET", "public/api/tags")
        self.assertEqual(RECEIVED[0]["path"], "/ctx/public/api/tags")

    def test_connection_failure_raises(self):
        dead = Profile(name="dev", host="h", port=9996, database="admin", user="u", password="p",
                       production=False, transport="vql_psycopg2",
                       marketplace_url="http://127.0.0.1:1", marketplace_server_id=None)
        with self.assertRaises(OSError):
            RestTransport(dead).call("GET", "/Ping", timeout=2)

    def test_profile_without_marketplace_url_is_rejected(self):
        p = Profile(name="dev", host="h", port=9996, database="admin", user="u", password="p",
                    production=False, transport="vql_psycopg2", marketplace_url=None, marketplace_server_id=None)
        with self.assertRaises(ValueError) as ctx:
            RestTransport(p)
        self.assertIn("marketplace_url", str(ctx.exception))
