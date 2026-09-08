import unittest

from denodo_cli.safety import classify_http, classify_vql


class ClassifyVqlTest(unittest.TestCase):
    def test_drop_is_destructive(self):
        self.assertEqual(classify_vql("DROP VIEW spike_dv"), "drop")

    def test_drop_if_exists_is_still_destructive(self):
        self.assertEqual(classify_vql("drop folder if exists '/spike'"), "drop")

    def test_alter_existing_object(self):
        self.assertEqual(classify_vql("ALTER VIEW v ADD COLUMN x:text"), "alter")

    def test_alter_tag_assignment_is_alter(self):
        self.assertEqual(
            classify_vql("ALTER TAG t ADD_TO ( VIEWS (db.v) COLUMNS () ) REMOVE_FROM ( VIEWS () COLUMNS () )"),
            "alter",
        )

    def test_create_or_replace_is_not_flagged(self):
        self.assertIsNone(classify_vql("CREATE OR REPLACE VIEW v AS SELECT 1 AS a FROM DUAL()"))

    def test_select_and_desc_are_not_flagged(self):
        self.assertIsNone(classify_vql("SELECT * FROM v"))
        self.assertIsNone(classify_vql("DESC VQL VIEW v"))

    def test_leading_comments_and_whitespace_are_skipped(self):
        self.assertEqual(classify_vql("-- verified: 9.5\n  /* x */ DROP TAG IF EXISTS t"), "drop")

    def test_drop_inside_string_does_not_count(self):
        self.assertIsNone(classify_vql("SELECT 'DROP VIEW x' AS s FROM DUAL()"))

    def test_delete_and_truncate_are_destructive(self):
        self.assertEqual(classify_vql("DELETE FROM cache_table"), "delete")
        self.assertEqual(classify_vql("TRUNCATE TABLE t"), "delete")


class ClassifyHttpTest(unittest.TestCase):
    def test_delete_method(self):
        self.assertEqual(classify_http("DELETE", "/public/api/tags/17"), "delete")
        self.assertEqual(classify_http("delete", "/public/api/category-management/categories/3?serverId=1"), "delete")

    def test_vdp_tag_synchronize_replaces_imported_set(self):
        self.assertEqual(classify_http("POST", "/public/api/tags/vdp/synchronize"), "replace")

    def test_catalog_synchronize(self):
        self.assertEqual(classify_http("POST", "/public/api/element-management/all/synchronize?serverId=1"), "replace")

    def test_view_tag_and_category_set_replace_assignments(self):
        self.assertEqual(classify_http("POST", "/public/api/views/42/tags"), "replace")
        self.assertEqual(classify_http("POST", "/public/api/views/42/categories"), "replace")

    def test_adding_a_tag_to_views_is_additive(self):
        self.assertIsNone(classify_http("POST", "/public/api/tags/42/views"))

    def test_plain_create_and_reads_are_not_flagged(self):
        self.assertIsNone(classify_http("POST", "/public/api/tags"))
        self.assertIsNone(classify_http("GET", "/public/api/tags/vdp/synchronize"))
        self.assertIsNone(classify_http("PUT", "/public/api/tags"))

    def test_delete_multiple_endpoint(self):
        self.assertEqual(classify_http("DELETE", "/public/api/tags/delete-multiple?tagIds=1"), "delete")


if __name__ == "__main__":
    unittest.main()
