import unittest

from denodo_cli.statements import ObjectRef, parse_statement


def p(text, database="sales"):
    return parse_statement(text, database)


class CreateTest(unittest.TestCase):
    def test_view_in_the_current_database(self):
        s = p("CREATE OR REPLACE VIEW iv_orders FOLDER = '/02 - integration' AS SELECT * FROM bv_orders")
        self.assertEqual(s.action, "create")
        self.assertTrue(s.or_replace)
        self.assertEqual(s.obj, ObjectRef("view", "sales", "iv_orders", "derived view"))

    def test_qualified_name_wins_over_the_current_database(self):
        s = p("CREATE VIEW other.v AS SELECT 1 AS a FROM Dual()")
        self.assertEqual(s.obj.database, "other")
        self.assertFalse(s.or_replace)

    def test_every_view_kind(self):
        cases = {
            "CREATE OR REPLACE TABLE bv_x I18N us_pst (a:int)": "base view",
            "CREATE OR REPLACE INTERFACE VIEW customer (a:int)": "interface view",
            "CREATE OR REPLACE METRIC VIEW sales_metrics AS SELECT 1": "metric view",
            "CREATE OR REPLACE SUMMARY VIEW s_band AS SELECT 1": "summary",
            "CREATE MATERIALIZED TABLE m_x (a:int)": "materialized table",
            "CREATE REMOTE TABLE r_x INTO ds_dwh AS SELECT 1": "remote table",
        }
        for text, kind in cases.items():
            with self.subTest(text=text):
                s = p(text)
                self.assertEqual((s.obj.type, s.obj.kind), ("view", kind))

    def test_data_source_and_wrapper_carry_their_subtype(self):
        s = p("CREATE OR REPLACE DATASOURCE DF ds_crm ROUTE LOCAL 'LocalConnection' '/x.csv'")
        self.assertEqual((s.obj, s.obj.kind), (ObjectRef("datasource", "sales", "ds_crm"), "df"))
        s = p("CREATE OR REPLACE WRAPPER JDBC wr_orders DATASOURCENAME = ds_dwh")
        self.assertEqual((s.obj, s.obj.kind), (ObjectRef("wrapper", "sales", "wr_orders"), "jdbc"))

    def test_folder_is_its_path(self):
        s = p("CREATE OR REPLACE FOLDER '/03 - Business Entities/customer' DESCRIPTION 'c'")
        self.assertEqual(s.obj, ObjectRef("folder", "sales", "/03 - business entities/customer"))

    def test_database_and_global_objects_have_no_database(self):
        self.assertEqual(p("CREATE OR REPLACE DATABASE sales_analytics 'desc'").obj,
                         ObjectRef("database", None, "sales_analytics"))
        self.assertEqual(p("CREATE OR REPLACE TAG pii DESCRIPTION = 'x'").obj, ObjectRef("tag", None, "pii"))
        self.assertEqual(p("CREATE OR REPLACE ROLE analyst 'r' GRANT CONNECT ON sales").obj,
                         ObjectRef("role", None, "analyst"))
        self.assertEqual(p("CREATE USER zq_u EXTERNAL").obj, ObjectRef("user", None, "zq_u"))
        self.assertEqual(p("CREATE OR REPLACE GLOBAL_SECURITY_POLICY masking ENABLED = TRUE").obj,
                         ObjectRef("globalSecurityPolicy", None, "masking"))

    def test_procedures(self):
        s = p("CREATE OR REPLACE VQL PROCEDURE loop_views (n int) AS BEGIN END")
        self.assertEqual(s.obj, ObjectRef("storedProcedure", "sales", "loop_views"))

    def test_association(self):
        s = p("CREATE OR REPLACE ASSOCIATION a_customer_order REFERENTIAL CONSTRAINT ENDPOINT c customer")
        self.assertEqual(s.obj, ObjectRef("association", "sales", "a_customer_order"))

    def test_names_compare_case_insensitively(self):
        self.assertEqual(p('CREATE VIEW "IV_Orders" AS SELECT 1').obj.key(), ("view", "sales", "iv_orders"))

    def test_tags_in_a_column_list_are_assignments_to_the_view(self):
        s = p("CREATE OR REPLACE VIEW iv_h ( buy TAGS ( personal_data ), dep TAGS ( personal_data, pii ) ) "
              "AS SELECT 1 AS buy FROM Dual()")
        self.assertEqual(s.tags_assigned, ["personal_data", "pii"])
        self.assertEqual(s.tag_targets, [("sales", "iv_h")])

    def test_unloaded_summary(self):
        self.assertFalse(p("CREATE SUMMARY VIEW s AS SELECT 1 DATA_LOAD_IMMEDIATE = FALSE").load_immediate)
        self.assertTrue(p("CREATE SUMMARY VIEW s AS SELECT 1").load_immediate)


class AlterDropTest(unittest.TestCase):
    def test_alter_view(self):
        s = p("ALTER VIEW iv_orders CACHE FULL")
        self.assertEqual((s.action, s.obj), ("alter", ObjectRef("view", "sales", "iv_orders")))

    def test_rename(self):
        s = p("ALTER VIEW rpt_top RENAME top_reasons")
        self.assertEqual(s.action, "rename")
        self.assertEqual(s.new_name, "top_reasons")

    def test_alter_table_is_a_view(self):
        self.assertEqual(p("ALTER TABLE bv_x ADD PRIMARY KEY ( 'a' )").obj.type, "view")

    def test_alter_session_is_a_session_setting(self):
        self.assertEqual(p("ALTER SESSION SET 'querytimeout' = '1000'").action, "session")

    def test_alter_tag_assigns_to_views_and_columns(self):
        s = p("ALTER TAG pii ADD_TO ( VIEWS ( sales.v1 ) COLUMNS ( sales.v2.email, v3.phone ) ) "
              "REMOVE_FROM ( VIEWS () COLUMNS () )")
        self.assertEqual(s.obj, ObjectRef("tag", None, "pii"))
        self.assertEqual(s.tags_assigned, ["pii"])
        self.assertEqual(s.tag_targets, [("sales", "v1"), ("sales", "v2"), ("sales", "v3")])

    def test_drop_with_if_exists_and_cascade(self):
        s = p("DROP VIEW IF EXISTS tmp_check CASCADE")
        self.assertEqual((s.action, s.obj), ("drop", ObjectRef("view", "sales", "tmp_check")))
        self.assertEqual(p("DROP DATASOURCE JDBC ds_x").obj, ObjectRef("datasource", "sales", "ds_x", "jdbc"))
        self.assertEqual(p("DROP FOLDER '/x/y'").obj, ObjectRef("folder", "sales", "/x/y"))
        self.assertEqual(p("DROP DATABASE scratch CASCADE").obj, ObjectRef("database", None, "scratch"))


class WebServiceTest(unittest.TestCase):
    """Publishing a view as a web service: outside the plugin, and never "a new object" to the plan."""

    def test_create_names_the_service_not_the_keyword(self):
        cases = {
            "CREATE OR REPLACE REST WEBSERVICE ws_returns CONNECTION ( CHUNKSIZE = 1000 ) RESOURCES ( VIEW mart )":
                ("create", "rest web service", True),
            "create soap webservice ws_returns CONNECTION ( CHUNKSIZE = 1000 ) I18N us_pst":
                ("create", "soap web service", False),
        }
        for text, (action, kind, or_replace) in cases.items():
            with self.subTest(text=text):
                s = p(text)
                self.assertEqual((s.action, s.or_replace), (action, or_replace))
                self.assertEqual((s.obj, s.obj.kind), (ObjectRef("webService", "sales", "ws_returns"), kind))

    def test_alter_and_drop(self):
        s = p("ALTER REST WEBSERVICE ws_returns DROP VIEW IF EXISTS mart")
        self.assertEqual((s.action, s.obj), ("alter", ObjectRef("webService", "sales", "ws_returns")))
        self.assertEqual(p("DROP WEBSERVICE other.ws_returns").obj, ObjectRef("webService", "other", "ws_returns"))

    def test_a_listener_names_itself_not_its_kind(self):
        s = p("CREATE OR REPLACE LISTENER JMS l_orders VENDOR ACTIVEMQ DESTINATION = 'orders' QUEUE OUTPUT = JSON")
        self.assertEqual((s.action, s.obj, s.obj.kind), ("create", ObjectRef("listener", "sales", "l_orders"), "jms"))
        self.assertEqual(p("CREATE LISTENER KAFKA l_events GROUPID = 'g' INPUTTOPIC = 't'").obj.kind, "kafka")

    def test_a_deploy_the_parser_cannot_name_still_publishes(self):
        for text in ("DEPLOY ws_returns", "UNDEPLOY", "REDEPLOY WEBSERVICE"):
            with self.subTest(text=text):
                self.assertEqual(p(text).action, "publish")
        self.assertEqual(p("EXPORT something_else TO 'x'").action, "other")

    def test_deploy_redeploy_undeploy_and_export_publish(self):
        for text in ("DEPLOY WEBSERVICE ws_returns",
                     "REDEPLOY WEBSERVICE ws_returns LOGIN = 'app' PASSWORD = 'x' ENCRYPTED",
                     "UNDEPLOY IF EXISTS WEBSERVICE ws_returns",
                     "EXPORT WAR FROM WEBSERVICE ws_returns NAME = 'r.war' URI = '//h:9999/sales'",
                     "export wsdl from webservice ws_returns NAME = 'r.wsdl'"):
            with self.subTest(text=text):
                s = p(text)
                self.assertEqual((s.action, s.obj), ("publish", ObjectRef("webService", "sales", "ws_returns")))


class OtherStatementsTest(unittest.TestCase):
    def test_reads(self):
        for text in ("SELECT * FROM iv_orders", "DESC VQL VIEW iv_orders", "LIST ROLES",
                     "SELECT name FROM GET_ELEMENTS() WHERE input_database_name = 'sales'"):
            with self.subTest(text=text):
                self.assertEqual(p(text).action, "read")

    def test_connect_moves_the_database(self):
        s = p("CONNECT DATABASE returns_ops")
        self.assertEqual((s.action, s.connect), ("session", "returns_ops"))

    def test_session_and_server_settings(self):
        self.assertEqual(p("SET QUERYTIMEOUT TO 1000").action, "session")
        self.assertEqual(p("SET 'com.denodo.vdb.x' = 'y'").action, "setting")
        self.assertEqual(p("WEBCONTAINER STATUS").action, "read")
        self.assertEqual(p("WEBCONTAINER STOP").action, "setting")

    def test_writes(self):
        self.assertEqual(p("INSERT INTO m_x (a) VALUES (1)").obj, ObjectRef("view", "sales", "m_x"))
        self.assertEqual(p("INSERT INTO m_x (a) VALUES (1)").action, "insert")
        self.assertEqual(p("UPDATE bv_x SET a = 1 WHERE b = 2").action, "update")
        self.assertEqual(p("DELETE FROM bv_x WHERE b = 2").obj, ObjectRef("view", "sales", "bv_x"))

    def test_refresh(self):
        s = p("REFRESH bv_dwh_household_income")
        self.assertEqual((s.action, s.obj), ("refresh", ObjectRef("view", "sales", "bv_dwh_household_income")))

    def test_procedure_call_with_positional_arguments(self):
        s = p("CALL CLEAN_CACHE_DATABASE('sales', 'iv_orders')")
        self.assertEqual((s.action, s.procedure, s.proc_args), ("call", "CLEAN_CACHE_DATABASE", ["sales", "iv_orders"]))

    def test_procedure_select_with_named_arguments(self):
        s = p("SELECT phase FROM CREATE_REMOTE_TABLE() WHERE remote_table_name = 'h' "
              "AND replace_remote_table_if_exist = false AND base_view_name = 'bv_h' "
              "AND base_view_database_name = 'sales' AND query = 'SELECT a FROM v WHERE s = ''x'''")
        self.assertEqual(s.action, "call")
        self.assertEqual(s.procedure, "CREATE_REMOTE_TABLE")
        self.assertEqual(s.proc_named["replace_remote_table_if_exist"], "false")
        self.assertEqual(s.proc_named["base_view_name"], "bv_h")
        self.assertEqual(s.proc_named["query"], "SELECT a FROM v WHERE s = 'x'")

    def test_reading_procedures_stay_reads(self):
        s = p("SELECT used_by_name FROM USED_BY() WHERE input_view_database_name = 'sales'")
        self.assertEqual(s.action, "read")

    def test_cache_load_names_the_view(self):
        s = p("SELECT * FROM iv_orders CONTEXT ('cache_preload' = 'true', 'cache_invalidate' = 'all_rows')")
        self.assertEqual((s.action, s.cache_view), ("cache", ("sales", "iv_orders")))

    def test_ai_over_rows_but_not_over_dual(self):
        self.assertTrue(p("SELECT CLASSIFY_AI(txt, 'a,b') FROM tickets").ai_over_rows)
        self.assertFalse(p("SELECT CLASSIFY_AI('x', 'a,b') FROM Dual()").ai_over_rows)
        self.assertFalse(p("CREATE OR REPLACE VIEW t AS SELECT CLASSIFY_AI(txt, 'a') AS c FROM tickets").ai_over_rows)

    def test_ai_over_rows_in_statements_that_write_them(self):
        # The query runs now, one paid request per row, whatever the rows are written into.
        for text in ("INSERT INTO bv_rt SELECT CLASSIFY_AI(txt, 'a,b') AS c FROM tickets",
                     "INSERT INTO bv_rt ON DUPLICATE KEY ( id ) UPDATE SELECT id, SUMMARIZE_AI(txt) AS s FROM tickets",
                     "UPDATE tickets SET c = CLASSIFY_AI(txt, 'a,b')",
                     "DELETE FROM tickets WHERE CLASSIFY_AI(txt, 'spam,ham') = 'spam'",
                     "CREATE OR REPLACE REMOTE TABLE rt INTO ds AS SELECT EMBED_AI(txt) AS v FROM tickets",
                     "CREATE MATERIALIZED TABLE m AS SELECT CLASSIFY_AI(txt, 'a') AS c FROM tickets",
                     "SELECT * FROM CREATE_REMOTE_TABLE( remote_table_name => 'rt', data_source_name => 'ds', "
                     "query => 'SELECT CLASSIFY_AI(txt, ''a'') AS c FROM tickets', base_view_name => 'bv_rt')"):
            self.assertTrue(p(text).ai_over_rows, text)
        self.assertFalse(p("INSERT INTO bv_rt SELECT id FROM tickets").ai_over_rows)

    def test_security_statement_references(self):
        s = p("CREATE OR REPLACE GLOBAL_SECURITY_POLICY m ENABLED = TRUE AUDIENCE ( ANY ROLES ( sales_analyst ) ) "
              "ELEMENTS ( VIEW_DATABASES ( sales_analytics ) COLUMNS TAGGED ANY ( personal_data ) )")
        for name in ("sales_analyst", "sales_analytics", "personal_data"):
            self.assertIn(name, s.identifiers)
        self.assertNotIn("audience", s.identifiers)
        r = p("CREATE OR REPLACE ROLE r 'x' GRANT EXECUTE ON sales_analytics.household_income")
        self.assertIn("sales_analytics.household_income", r.identifiers)

    def test_unknown_statement(self):
        self.assertEqual(p("FROBNICATE everything").action, "other")


if __name__ == "__main__":
    unittest.main()
