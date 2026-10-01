import re
import unittest
from pathlib import Path

from denodo_cli.safety import STATE_CHANGING_PROCEDURES, classify_http, classify_vql

PREDEFINED_MD = Path(__file__).resolve().parents[1] / "skills" / "procedures" / "references" / "predefined.md"


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


class ServerSettingTest(unittest.TestCase):
    """``SET '<property>' = …`` writes VDBConfiguration.properties of the whole server
    (propagated to servers sharing an external metadata database); ``WEBCONTAINER`` does
    the same for the embedded web container, or stops and reloads it."""

    def test_quoted_property_is_a_server_setting(self):
        self.assertEqual(
            classify_vql("SET 'com.denodo.vdb.server.xmlFunctions.allowedProtocols' = 'http,https'"),
            "setting",
        )

    def test_jvm_options_are_a_server_setting(self):
        self.assertEqual(classify_vql("SET 'java.env.DENODO_OPTS_START' = '-server -Xms8g -Xmx8g'"), "setting")

    def test_removing_a_property_is_a_server_setting(self):
        # = NULL without quotes deletes the property from the configuration file
        self.assertEqual(classify_vql("SET 'com.denodo.restfulws.vdbUri' = NULL"), "setting")

    def test_lowercase_and_no_spaces(self):
        self.assertEqual(classify_vql("set 'com.denodo.restfulws.vdbUri'='//localhost:9999/admin'"), "setting")

    def test_leading_comment_is_skipped(self):
        self.assertEqual(classify_vql("-- raise the limit\nSET 'x.y' = '1'"), "setting")

    def test_set_the_tool_does_not_recognise_counts_as_a_server_setting(self):
        # only the documented session form passes; anything else errs on the side of refusing
        self.assertEqual(classify_vql('SET "x.y" = \'1\''), "setting")

    def test_web_container_changes_are_server_settings(self):
        self.assertEqual(classify_vql("WEBCONTAINER SET 'java.env.DENODO_OPTS_START' = '-Xmx2g'"), "setting")
        self.assertEqual(classify_vql("WEBCONTAINER STOP"), "setting")
        self.assertEqual(classify_vql("webcontainer start 'denodo-restfulws'"), "setting")
        self.assertEqual(classify_vql("WEBCONTAINER RELOAD 'denodo-restfulws'"), "setting")

    def test_web_container_status_is_a_read(self):
        self.assertIsNone(classify_vql("WEBCONTAINER STATUS"))

    def test_set_inside_a_string_does_not_count(self):
        self.assertIsNone(classify_vql("SELECT 'SET ''x'' = 1' AS s FROM DUAL()"))


class SessionSettingTest(unittest.TestCase):
    """Session settings last until the connection closes and touch nothing else, so they
    pass on any profile (checked live on 9.5.1: ``ALTER SESSION SET 'querytimeout'`` shows
    in ``GETSESSION`` on the same connection and is gone on the next one)."""

    def test_odbc_connection_settings(self):
        self.assertIsNone(classify_vql("SET QUERYTIMEOUT TO 3600000"))
        self.assertIsNone(classify_vql("SET I18N TO us_pst"))
        self.assertIsNone(classify_vql("set force_decimal_properties to true"))

    def test_alter_session(self):
        self.assertIsNone(classify_vql("ALTER SESSION SET 'querytimeout' = '10000'"))
        self.assertIsNone(classify_vql("alter session set 'querytimeout' = NULL"))

    def test_alter_of_an_object_named_session_is_still_alter(self):
        self.assertEqual(classify_vql("ALTER VIEW session ADD COLUMN x:text"), "alter")


class SourceWriteTest(unittest.TestCase):
    """``INSERT`` and ``UPDATE`` through a view change the data in the source behind it.
    VQL has no ``MERGE`` (the 9.5.1 parser rejects it); its merge is
    ``INSERT … ON DUPLICATE KEY UPDATE``."""

    def test_insert_is_a_write(self):
        self.assertEqual(classify_vql("INSERT INTO customer (id, name) VALUES (1, 'a')"), "write")

    def test_insert_select_is_a_write(self):
        self.assertEqual(classify_vql("insert into all_sales SELECT * FROM online_sales"), "write")

    def test_merge_form_of_insert_is_a_write(self):
        self.assertEqual(
            classify_vql("INSERT INTO all_sales ON DUPLICATE KEY(sale_id) UPDATE SELECT * FROM online_sales"),
            "write",
        )

    def test_update_is_a_write(self):
        self.assertEqual(
            classify_vql("UPDATE internet_inc SET specific_field1 = '10' WHERE iinc_id = 6"), "write"
        )

    def test_insert_inside_a_string_does_not_count(self):
        self.assertIsNone(classify_vql("SELECT 'INSERT INTO t' AS s FROM DUAL()"))


class CacheWriteTest(unittest.TestCase):
    """A query whose CONTEXT loads or invalidates a view's cache is a write, although it
    starts with SELECT: ``'cache_invalidate'`` deletes cached rows before the load, and a
    ``'cache_preload' = 'true'`` without it appends a second copy of the rows (T27)."""

    def test_preload_that_replaces_the_cache(self):
        self.assertEqual(
            classify_vql(
                "SELECT * FROM web_return_line CONTEXT ('cache_preload' = 'true', "
                "'cache_invalidate' = 'all_rows', 'cache_wait_for_load' = 'true', "
                "'cache_return_query_results' = 'false')"
            ),
            "cache",
        )

    def test_preload_without_invalidation_appends(self):
        self.assertEqual(
            classify_vql("SELECT * FROM v WHERE id > 0 CONTEXT ('cache_preload' = 'true')"), "cache"
        )

    def test_invalidation_without_preload(self):
        self.assertEqual(
            classify_vql("SELECT * FROM v WHERE a = 1 CONTEXT ('cache_invalidate' = 'matching_rows')"), "cache"
        )

    def test_case_and_spacing(self):
        self.assertEqual(classify_vql("select * from v context('CACHE_PRELOAD'='TRUE')"), "cache")

    def test_leading_comment_is_skipped(self):
        self.assertEqual(
            classify_vql("-- nightly\nSELECT * FROM v CONTEXT ('cache_invalidate' = 'all_rows', 'cache_preload' = 'true')"),
            "cache",
        )

    def test_reading_around_the_cache_is_not_a_write(self):
        # 'cache' = 'off' reads the source instead of the cache: the check a preload is compared with
        self.assertIsNone(classify_vql("SELECT COUNT(*) FROM v CONTEXT ('cache' = 'off')"))
        self.assertIsNone(classify_vql("SELECT * FROM v CONTEXT ('cache_preload' = 'false')"))
        self.assertIsNone(classify_vql("SELECT * FROM v CONTEXT ('cache_wait_for_load' = 'true')"))
        self.assertIsNone(classify_vql("SELECT * FROM CACHE_CONTENT('d', 'v')"))

    def test_parameter_names_inside_a_string_do_not_count(self):
        # doubled quotes inside a literal are not a CONTEXT parameter
        self.assertIsNone(
            classify_vql("SELECT 'CONTEXT (''cache_preload'' = ''true'')' AS how FROM DUAL()")
        )

    def test_alter_view_cache_stays_alter(self):
        self.assertEqual(classify_vql("ALTER VIEW v CACHE INVALIDATE"), "alter")
        self.assertEqual(classify_vql("ALTER VIEW v CACHE FULL"), "alter")


class StateChangingProcedureTest(unittest.TestCase):
    """Predefined procedures that change state are invoked with SELECT or CALL, so the
    leading keyword says nothing; the name does (T20)."""

    def test_select_from_state_changing_procedure(self):
        self.assertEqual(
            classify_vql("SELECT * FROM DROP_REMOTE_TABLE() WHERE input_base_view_database_name = 'd' AND input_base_view_name = 'v'"),
            "procedure",
        )

    def test_call_form(self):
        self.assertEqual(classify_vql("CALL CLEAN_CACHE_DATABASE('sales_analytics')"), "procedure")

    def test_name_is_matched_case_insensitively(self):
        self.assertEqual(classify_vql("select 1 from generate_stats() where input_database_name = 'd'"), "procedure")

    def test_database_qualified_name(self):
        self.assertEqual(classify_vql("SELECT * FROM admin.DROP_NONACTIVE_CACHE_TABLES()"), "procedure")

    def test_every_listed_procedure_is_caught_in_both_forms(self):
        for name in STATE_CHANGING_PROCEDURES:
            self.assertEqual(classify_vql(f"SELECT * FROM {name}()"), "procedure", name)
            self.assertEqual(classify_vql(f"CALL {name}(null)"), "procedure", name)

    def test_reading_procedures_are_not_flagged(self):
        self.assertIsNone(classify_vql("SELECT name FROM GET_ELEMENTS() WHERE input_database_name = 'd'"))
        self.assertIsNone(classify_vql("SELECT 1 AS a FROM DUAL()"))
        self.assertIsNone(classify_vql("CALL USED_BY('d', 'v', null)"))
        self.assertIsNone(classify_vql("SELECT * FROM GET_CACHE_TABLE() WHERE input_database_name = 'd'"))

    def test_prefix_of_a_listed_name_is_not_flagged(self):
        # GENERATE_STATS is listed; a view or procedure merely starting with it is not
        self.assertIsNone(classify_vql("SELECT * FROM GENERATE_STATS_REPORT()"))

    def test_plain_view_named_like_a_procedure_is_not_flagged(self):
        # no parenthesis, no call: a view called drop_remote_table is just a view
        self.assertIsNone(classify_vql("SELECT * FROM drop_remote_table"))

    def test_view_defined_over_a_state_changing_procedure_is_flagged(self):
        # every query of such a view would run the procedure again
        self.assertEqual(
            classify_vql("CREATE OR REPLACE VIEW v AS SELECT * FROM CLEAN_CACHE_DATABASE('d')"),
            "procedure",
        )

    def test_drop_keyword_wins_over_procedure_name(self):
        self.assertEqual(classify_vql("DROP VIEW generate_stats_wrapper"), "drop")

    def test_list_matches_the_procedures_skill_reference(self):
        """The list is kept twice on purpose — in code (the tool must not read skill files
        at run time) and in the skill (which must stay self-contained) — and this test is
        what keeps the two copies from drifting apart silently."""
        text = PREDEFINED_MD.read_text(encoding="utf-8")
        section = re.search(r"^## A call that looks like a read and is not\n(.*?)^## ", text, re.S | re.M)
        self.assertIsNotNone(section, "section heading changed in predefined.md")
        rows = [line for line in section.group(1).splitlines() if line.startswith("| `")]
        listed = {re.match(r"\| `([A-Z0-9_]+)`", line).group(1) for line in rows}
        self.assertEqual(listed, set(STATE_CHANGING_PROCEDURES))


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

    def test_view_property_groups_set_replaces_them(self):
        # T30, live on 9.5.1: assigning [211] to a view that had [212] dropped 212 and the
        # values of its properties. Reading the groups back is not a POST at all (405).
        self.assertEqual(classify_http("POST", "/public/api/property-management/views/7452/groups"), "replace")
        self.assertIsNone(classify_http("PUT", "/public/api/views/property-values"))

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
