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
        # the category endpoint lives under category-management; /public/api/views/{id}/categories
        # is not a path the 9.5.1 API serves at all (T8d, checked against the server's OpenAPI)
        self.assertEqual(classify_http("POST", "/public/api/views/42/tags"), "replace")
        self.assertEqual(classify_http("POST", "/public/api/category-management/views/42/categories"), "replace")

    def test_per_type_catalog_synchronize_is_destructive_too(self):
        # it removes from the marketplace whatever VDP no longer has, exactly like the "all" form
        for element_type in ("DATABASES", "VIEWS", "WEBSERVICES", "EXTERNAL_ELEMENTS"):
            self.assertEqual(
                classify_http("POST", f"/public/api/element-management/{element_type}/synchronize?serverId=306"),
                "replace",
            )

    def test_external_tool_server_synchronize_deletes_missing_elements(self):
        self.assertEqual(classify_http("POST", "/public/api/external-tool-servers/synchronize"), "replace")
        self.assertEqual(classify_http("POST", "/public/api/external-tool-servers/synchronize-all"), "replace")
        self.assertEqual(classify_http("POST", "/public/api/external-tool-servers/217/synchronize"), "replace")

    def test_reading_the_synchronize_radius_is_not_destructive(self):
        self.assertIsNone(classify_http("GET", "/public/api/element-management/VIEWS/changes?serverId=306"))
        self.assertIsNone(classify_http("GET", "/public/api/tags/vdp/local"))

    def test_adding_a_tag_to_views_is_additive(self):
        self.assertIsNone(classify_http("POST", "/public/api/tags/42/views"))
        self.assertIsNone(classify_http("POST", "/public/api/category-management/categories/7/views"))
        self.assertIsNone(classify_http("POST", "/public/api/category-management/add/views/42/categories"))

    def test_plain_create_and_reads_are_not_flagged(self):
        self.assertIsNone(classify_http("POST", "/public/api/tags"))
        self.assertIsNone(classify_http("GET", "/public/api/tags/vdp/synchronize"))
        self.assertIsNone(classify_http("PUT", "/public/api/tags"))

    def test_delete_multiple_endpoint(self):
        self.assertEqual(classify_http("DELETE", "/public/api/tags/delete-multiple?tagIds=1"), "delete")


if __name__ == "__main__":
    unittest.main()
