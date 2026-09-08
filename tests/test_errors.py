import unittest

from denodo_cli.errors import normalize_error

PSYCOPG2_TEXT = (
    "ERROR:  Syntax error: Exception parsing query near 'ADD'\n"
    "DETAIL:  java.sql.SQLException: Syntax error: Exception parsing query near 'ADD'\n"
)


class NormalizeErrorTest(unittest.TestCase):
    def test_server_message_is_extracted_from_detail_line(self):
        info = normalize_error(RuntimeError(PSYCOPG2_TEXT))
        self.assertEqual(info["message"], "Syntax error: Exception parsing query near 'ADD'")
        self.assertEqual(info["type"], "RuntimeError")
        self.assertIn("DETAIL", info["raw"])

    def test_error_line_without_detail(self):
        info = normalize_error(RuntimeError("ERROR:  error removing view: The database does not contain the specified view: x\n"))
        self.assertEqual(info["message"], "error removing view: The database does not contain the specified view: x")

    def test_plain_exception_text_is_kept(self):
        info = normalize_error(ConnectionRefusedError("connection refused"))
        self.assertEqual(info["message"], "connection refused")
        self.assertEqual(info["raw"], "connection refused")

    def test_whitespace_is_collapsed(self):
        info = normalize_error(RuntimeError("  multi\n   line \t text  "))
        self.assertEqual(info["message"], "multi line text")
