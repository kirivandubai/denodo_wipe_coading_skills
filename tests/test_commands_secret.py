import unittest

from denodo_cli.commands.secret import encrypt_password
from denodo_cli.output import to_json
from denodo_cli.profiles import Profile
from denodo_cli.transports.base import VqlResult

CIPHER = "5jWZgnBTkPVnFZdLGxpCyA=="


def profile(**over):
    base = dict(name="dev", host="h", port=9996, database="admin", user="u", password="p",
                production=False, transport="vql_psycopg2", marketplace_url=None, marketplace_server_id=None)
    base.update(over)
    return Profile(**base)


class FakeTransport:
    """Returns one row with the ciphertext; ``raises`` makes ``execute`` fail instead."""

    instances = []
    raises: Exception | None = None
    result = "rows"

    def __init__(self, profile, database=None):
        self.executed = []
        self.closed = False
        FakeTransport.instances.append(self)

    def execute(self, statement):
        self.executed.append(statement)
        if FakeTransport.raises is not None:
            raise FakeTransport.raises
        if FakeTransport.result == "empty":
            return VqlResult(statement=statement, columns=None, rows=None)
        return VqlResult(statement=statement, columns=["encrypted_password"], rows=[[CIPHER]])

    def close(self):
        self.closed = True


class EncryptPasswordTest(unittest.TestCase):
    def setUp(self):
        FakeTransport.instances.clear()
        FakeTransport.raises = None
        FakeTransport.result = "rows"

    def run_it(self, password, **kw):
        kw.setdefault("transport_factory", FakeTransport)
        return encrypt_password(profile(), password, **kw)

    def test_the_ciphertext_comes_back_in_the_envelope(self):
        doc, code = self.run_it("s3cret")
        self.assertEqual(code, 0)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["command"], "secret encrypt")
        self.assertEqual(doc["env"]["name"], "dev")
        self.assertEqual(doc["encrypted"], CIPHER)

    def test_the_password_is_nowhere_in_the_document(self):
        doc, _ = self.run_it("s3cret")
        self.assertNotIn("s3cret", to_json(doc))
        self.assertNotIn("statement", doc)

    def test_a_quote_in_the_password_is_doubled_in_the_literal(self):
        self.run_it("pa's's")
        self.assertEqual(FakeTransport.instances[0].executed, ["ENCRYPT_PASSWORD 'pa''s''s'"])

    def test_a_server_error_quoting_the_statement_does_not_leak_the_password(self):
        FakeTransport.raises = RuntimeError(
            "ERROR:  Syntax error\nDETAIL:  java.sql.SQLException: near ENCRYPT_PASSWORD 's3cret'\n")
        doc, code = self.run_it("s3cret")
        self.assertEqual(code, 1)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["error"]["kind"], "execution")
        self.assertNotIn("s3cret", to_json(doc))
        self.assertIn("Syntax error", to_json(doc))

    def test_a_result_without_rows_is_an_execution_error(self):
        FakeTransport.result = "empty"
        doc, code = self.run_it("s3cret")
        self.assertEqual(code, 1)
        self.assertEqual(doc["error"]["kind"], "execution")
        self.assertIsNone(doc.get("encrypted"))

    def test_a_connection_failure_is_reported_as_one(self):
        def boom(profile, database=None):
            raise RuntimeError("could not connect to server")
        doc, code = self.run_it("s3cret", transport_factory=boom)
        self.assertEqual(code, 1)
        self.assertEqual(doc["error"]["kind"], "connection")

    def test_the_session_is_closed_on_success_and_on_failure(self):
        self.run_it("s3cret")
        FakeTransport.raises = RuntimeError("ERROR:  boom\n")
        self.run_it("s3cret")
        self.assertEqual([t.closed for t in FakeTransport.instances], [True, True])


if __name__ == "__main__":
    unittest.main()
