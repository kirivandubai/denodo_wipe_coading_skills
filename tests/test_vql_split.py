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


class ProcedureBodyTest(unittest.TestCase):
    """A VQL procedure carries semicolons inside its own body (design spec, section 8:
    the skill's template is what the agent copies, and it is a single statement)."""

    PROCEDURE = (
        "CREATE OR REPLACE VQL PROCEDURE greet (in_name IN VARCHAR, greeting OUT VARCHAR)\n"
        "AS (\n"
        "    tmp VARCHAR;\n"
        ")\n"
        "BEGIN\n"
        "    tmp := 'hello ' || in_name;\n"
        "    RETURN ROW (greeting) VALUES (tmp);\n"
        "END"
    )

    def test_procedure_body_is_one_statement(self):
        self.assertEqual(split_statements(self.PROCEDURE + ";"), [self.PROCEDURE])

    def test_statement_after_the_procedure_is_separate(self):
        text = self.PROCEDURE + ";\nSELECT greeting FROM greet() WHERE in_name = 'world';"
        self.assertEqual(
            split_statements(text),
            [self.PROCEDURE, "SELECT greeting FROM greet() WHERE in_name = 'world'"],
        )

    def test_end_if_does_not_close_the_body(self):
        body = (
            "CREATE OR REPLACE VQL PROCEDURE p (n IN INTEGER, out_n OUT INTEGER)\n"
            "AS (\n"
            "    tmp INTEGER;\n"
            ")\n"
            "BEGIN\n"
            "    IF n > 0 THEN\n"
            "        tmp := n;\n"
            "    ELSE\n"
            "        tmp := 0;\n"
            "    END IF;\n"
            "    RETURN ROW (out_n) VALUES (tmp);\n"
            "END"
        )
        self.assertEqual(split_statements(body + ";"), [body])

    def test_end_loop_does_not_close_the_body(self):
        body = (
            "CREATE OR REPLACE VQL PROCEDURE p (out_n OUT INTEGER)\n"
            "AS (\n"
            "    tmp INTEGER;\n"
            ")\n"
            "BEGIN\n"
            "    tmp := 0;\n"
            "    FOR i IN 1 .. 3 LOOP\n"
            "        tmp := tmp + i;\n"
            "    END LOOP;\n"
            "    RETURN ROW (out_n) VALUES (tmp);\n"
            "END"
        )
        self.assertEqual(split_statements(body + ";"), [body])

    def test_end_case_does_not_close_the_body(self):
        body = (
            "CREATE OR REPLACE VQL PROCEDURE p (n IN INTEGER, out_n OUT INTEGER)\n"
            "AS (\n"
            "    tmp INTEGER;\n"
            ")\n"
            "BEGIN\n"
            "    CASE\n"
            "        WHEN n > 0 THEN tmp := 1;\n"
            "        ELSE tmp := 0;\n"
            "    END CASE;\n"
            "    RETURN ROW (out_n) VALUES (tmp);\n"
            "END"
        )
        self.assertEqual(split_statements(body + ";"), [body])

    def test_procedure_without_or_replace(self):
        body = "CREATE VQL PROCEDURE p (out_n OUT INTEGER)\nAS (\n    tmp INTEGER;\n)\nBEGIN\n    tmp := 1;\n    RETURN ROW (out_n) VALUES (tmp);\nEND"
        self.assertEqual(split_statements(body + ";"), [body])

    def test_lowercase_header_is_recognised(self):
        body = "create or replace vql procedure p (out_n out integer)\nas (\n    tmp integer;\n)\nbegin\n    tmp := 1;\n    return row (out_n) values (tmp);\nend"
        self.assertEqual(split_statements(body + ";"), [body])

    def test_comment_inside_the_body_does_not_split_it(self):
        text = (
            "CREATE OR REPLACE VQL PROCEDURE p (out_n OUT INTEGER)\n"
            "AS (\n"
            "    tmp INTEGER;\n"
            ")\n"
            "BEGIN\n"
            "    -- one; two\n"
            "    tmp := 1;\n"
            "    RETURN ROW (out_n) VALUES (tmp);\n"
            "END;"
        )
        self.assertEqual(len(split_statements(text)), 1)

    def test_a_view_named_procedure_is_not_a_procedure(self):
        """Only the CREATE ... VQL PROCEDURE header opens a body; the word alone does not."""
        text = "CREATE OR REPLACE VIEW procedure_log AS SELECT 1 AS a FROM DUAL();\nSELECT 2 FROM DUAL();"
        self.assertEqual(len(split_statements(text)), 2)

if __name__ == "__main__":
    unittest.main()
