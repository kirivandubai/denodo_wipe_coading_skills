import unittest

from denodo_cli.vql_split import split_statements


class SplitStatementsTest(unittest.TestCase):
    def test_two_statements_separated_by_semicolon(self):
        text = "CREATE OR REPLACE FOLDER '/a';\nCREATE OR REPLACE FOLDER '/b';"
        self.assertEqual(
            split_statements(text),
            ["CREATE OR REPLACE FOLDER '/a'", "CREATE OR REPLACE FOLDER '/b'"],
        )

    def test_statement_without_trailing_semicolon(self):
        self.assertEqual(split_statements("SELECT 1 FROM DUAL()"), ["SELECT 1 FROM DUAL()"])

    def test_semicolon_inside_single_quoted_string_is_kept(self):
        text = "SELECT 'a;b' AS x FROM DUAL(); SELECT 2 FROM DUAL()"
        self.assertEqual(
            split_statements(text),
            ["SELECT 'a;b' AS x FROM DUAL()", "SELECT 2 FROM DUAL()"],
        )

    def test_escaped_quote_inside_string(self):
        text = "SELECT 'it''s; fine' FROM DUAL();"
        self.assertEqual(split_statements(text), ["SELECT 'it''s; fine' FROM DUAL()"])

    def test_semicolon_inside_double_quoted_identifier(self):
        text = 'SELECT "we;ird" FROM v;'
        self.assertEqual(split_statements(text), ['SELECT "we;ird" FROM v'])

    def test_line_comments_are_removed(self):
        text = (
            "-- header; with semicolon\n"
            "# Generated with Denodo Platform 9.5.1; ignore\n"
            "SELECT 1 FROM DUAL(); -- trailing; comment\n"
            "SELECT 2 FROM DUAL();"
        )
        self.assertEqual(split_statements(text), ["SELECT 1 FROM DUAL()", "SELECT 2 FROM DUAL()"])

    def test_block_comment_with_semicolon_is_removed(self):
        text = "/* one; two */ SELECT 1 FROM DUAL(); /* ; */ SELECT 2 FROM DUAL()"
        self.assertEqual(split_statements(text), ["SELECT 1 FROM DUAL()", "SELECT 2 FROM DUAL()"])

    def test_empty_and_whitespace_only_chunks_are_dropped(self):
        self.assertEqual(split_statements(";;  \n ; SELECT 1 FROM DUAL(); \n\n"), ["SELECT 1 FROM DUAL()"])

    def test_multiline_statement_keeps_inner_newlines(self):
        text = "CREATE OR REPLACE VIEW v\n    FOLDER = '/x'\n    AS SELECT 1 AS a FROM DUAL();"
        self.assertEqual(
            split_statements(text),
            ["CREATE OR REPLACE VIEW v\n    FOLDER = '/x'\n    AS SELECT 1 AS a FROM DUAL()"],
        )

    def test_hash_inside_string_is_not_a_comment(self):
        text = "SELECT '#1; x' FROM DUAL()"
        self.assertEqual(split_statements(text), ["SELECT '#1; x' FROM DUAL()"])


if __name__ == "__main__":
    unittest.main()
