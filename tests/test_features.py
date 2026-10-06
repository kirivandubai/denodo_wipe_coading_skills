"""What the server says about itself (T40): its bundle, cache, LLM and optimizer switches.

Every answer below is the shape Denodo 9.5.1 gave on a live server; a call that fails leaves
its feature unknown (``None``) rather than failing the probe — a non-administrator cannot read
server settings, and that is an answer, not an error.
"""

from __future__ import annotations

import unittest

from denodo_cli.features import (FEATURE_NAMES, FEATURE_REASONS, PARAMETERS, feature_state, read_features,
                                 scheduler_data_source, server_values)
from denodo_cli.transports.base import HttpResult, VqlResult

MPP_ENTERPRISE_PLUS = VqlResult(
    statement="", columns=["max_processors", "current_processors", "status", "details"],
    rows=[[2147483647, -1, -5, "The validation was not successful because it could not connect"]])
MPP_ENTERPRISE = VqlResult(statement="", columns=["max_processors", "current_processors", "status", "details"],
                           rows=[[-1, -1, -3, "no MPP configured"]])
CACHE_SQLSERVER = VqlResult(
    statement="", columns=["database_datasource_name", "datasource_name", "adapter_database_name",
                           "adapter_database_version", "status", "target_catalog", "target_schema"],
    rows=[["admin", "vdpcachedatasource", "sqlserver", "2025", "ON", "enterprise_data", "dbo"]])


def parameters(**answers):
    rows = [[name, answers.get(name)] for name in PARAMETERS]
    return VqlResult(statement="", columns=["name", "property_value"], rows=rows)


class Scripted:
    """Answers by the procedure a statement reads; an Exception answer is raised."""

    def __init__(self, answers):
        self.answers, self.sent = answers, []

    def execute(self, statement):
        self.sent.append(statement)
        for key, answer in self.answers.items():
            if key in statement:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise RuntimeError(f"unexpected statement {statement}")


ALL_ON = {
    "VALIDATE_MPP_LICENSE": MPP_ENTERPRISE_PLUS,
    "GET_CACHE_CONFIGURATION": CACHE_SQLSERVER,
    "GET_PARAMETER": parameters(llm_enabled="true", llm_provider="OPEN_AI", llm_model="gpt-5.1",
                                embedding_provider="OPEN_AI", embedding_model="text-embedding-3-large",
                                embedding_disabled="false", summary_rewrite="true", data_movement="true"),
}


class ReadFeaturesTest(unittest.TestCase):
    def test_a_server_with_everything(self):
        features = read_features(Scripted(ALL_ON))
        self.assertIs(features["enterprise_plus"], True)
        self.assertEqual(features["mpp"], {"status": -5, "details": MPP_ENTERPRISE_PLUS.rows[0][3]})
        self.assertEqual(features["cache"], {
            "on": True, "data_source_database": "admin", "data_source": "vdpcachedatasource",
            "adapter": "sqlserver", "adapter_version": "2025", "catalog": "enterprise_data", "schema": "dbo"})
        self.assertEqual(features["llm"], {"on": True, "provider": "OPEN_AI", "model": "gpt-5.1"})
        self.assertEqual(features["embedding"],
                         {"on": True, "provider": "OPEN_AI", "model": "text-embedding-3-large"})
        self.assertIs(features["summary_rewrite"], True)
        self.assertIs(features["data_movement"], True)

    def test_minus_one_processors_means_not_enterprise_plus(self):
        features = read_features(Scripted({**ALL_ON, "VALIDATE_MPP_LICENSE": MPP_ENTERPRISE}))
        self.assertIs(features["enterprise_plus"], False)

    def test_a_non_administrator_cannot_read_settings_and_that_is_unknown(self):
        features = read_features(Scripted({**ALL_ON, "GET_PARAMETER": RuntimeError("Error executing query.")}))
        for name in ("llm", "embedding", "summary_rewrite", "data_movement"):
            self.assertIsNone(features[name], name)
        self.assertIs(features["enterprise_plus"], True)
        self.assertTrue(features["cache"]["on"])

    def test_every_call_failing_leaves_everything_unknown(self):
        features = read_features(Scripted({}))
        self.assertEqual({k: v for k, v in features.items() if v is not None}, {})

    def test_llm_off_and_embedding_disabled(self):
        answers = {**ALL_ON, "GET_PARAMETER": parameters(llm_enabled="false", llm_model="gpt-5.1",
                                                          embedding_model="text-embedding-3-large",
                                                          embedding_disabled="true")}
        features = read_features(Scripted(answers))
        self.assertIs(features["llm"]["on"], False)
        self.assertIs(features["embedding"]["on"], False)
        self.assertIsNone(features["summary_rewrite"])     # not set in the file: unknown

    def test_no_model_means_off(self):
        features = read_features(Scripted({**ALL_ON, "GET_PARAMETER": parameters(llm_enabled="true")}))
        self.assertIs(features["llm"]["on"], False)
        self.assertIs(features["embedding"]["on"], False)

    def test_cache_off(self):
        rows = [CACHE_SQLSERVER.rows[0][:4] + ["OFF"] + CACHE_SQLSERVER.rows[0][5:]]
        cache = VqlResult(statement="", columns=CACHE_SQLSERVER.columns, rows=rows)
        self.assertIs(read_features(Scripted({**ALL_ON, "GET_CACHE_CONFIGURATION": cache}))["cache"]["on"], False)

    def test_only_the_listed_properties_are_ever_asked_for(self):
        transport = Scripted(ALL_ON)
        read_features(transport)
        sent = " ".join(s for s in transport.sent if "GET_PARAMETER" in s)
        asked = {part.split("'")[0] for part in sent.split("input_property_name = '")[1:]}
        self.assertEqual(asked, set(PARAMETERS.values()))
        for prop in asked:
            self.assertNotRegex(prop.lower(), "secret|key|password|token|header|organization")


class ServerValuesTest(unittest.TestCase):
    def test_the_values_the_server_answers(self):
        values = server_values(read_features(Scripted(ALL_ON)))
        self.assertEqual(values, {
            "embedding_model": "text-embedding-3-large", "write_datasource_database": "admin",
            "write_datasource_name": "vdpcachedatasource", "write_catalog": "enterprise_data",
            "write_schema": "dbo", "write_dialect": "sqlserver"})

    def test_a_null_is_left_out(self):
        row = CACHE_SQLSERVER.rows[0][:5] + [None, "zq_cache"]
        cache = VqlResult(statement="", columns=CACHE_SQLSERVER.columns, rows=[row])
        values = server_values(read_features(Scripted({**ALL_ON, "GET_CACHE_CONFIGURATION": cache})))
        self.assertNotIn("write_catalog", values)
        self.assertEqual(values["write_schema"], "zq_cache")

    def test_unknown_features_give_no_values(self):
        self.assertEqual(server_values(read_features(Scripted({}))), {})


class FeatureStateTest(unittest.TestCase):
    def test_each_name_reads_its_feature(self):
        features = read_features(Scripted(ALL_ON))
        features.update(impersonation=False)
        self.assertEqual({name: feature_state(features, name) for name in FEATURE_NAMES}, {
            "enterprise_plus": True, "llm": True, "embedding": True, "cache": True,
            "summary_rewrite": True, "data_movement": True, "impersonation": False})

    def test_unknown_stays_unknown(self):
        features = read_features(Scripted({}))
        self.assertTrue(all(feature_state(features, name) is None for name in FEATURE_NAMES))

    def test_every_feature_has_a_reason(self):
        self.assertEqual(set(FEATURE_REASONS), set(FEATURE_NAMES))


class Rest:
    def __init__(self, body, status=200):
        self.body, self.status, self.calls = body, status, []

    def call(self, method, path, **kw):
        self.calls.append((method, path))
        return HttpResult(status=self.status, body=self.body)


SOURCES = [
    # As 9.5.1 answers: the index data source has a login too, so the type decides.
    {"id": 1, "type": "Scheduler-Index", "projectName": "default", "login": "admin", "host": "localhost"},
    {"id": 2, "type": "VDP", "projectName": "default", "login": "admin", "connectionURI": "//localhost:9999/admin"},
]


class SchedulerDataSourceTest(unittest.TestCase):
    def test_the_one_vdp_source_of_the_profile_s_user(self):
        rest = Rest(SOURCES)
        found, candidates = scheduler_data_source(rest, "admin")
        self.assertEqual(found, "2")
        self.assertEqual(rest.calls, [("GET", "/public/api/dataSources")])
        self.assertEqual([c["id"] for c in candidates], [2])

    def test_none_for_another_user(self):
        found, candidates = scheduler_data_source(Rest(SOURCES), "mlee")
        self.assertIsNone(found)
        self.assertEqual([c["login"] for c in candidates], ["admin"])

    def test_none_when_two_match(self):
        two = SOURCES + [{**SOURCES[1], "id": 9, "projectName": "ops"}]
        found, candidates = scheduler_data_source(Rest(two), "admin")
        self.assertIsNone(found)
        self.assertEqual(len(candidates), 2)

    def test_none_when_the_scheduler_does_not_answer(self):
        self.assertEqual(scheduler_data_source(Rest(None, status=500), "admin"), (None, []))

    def test_a_wrapped_list_is_read_too(self):
        found, _ = scheduler_data_source(Rest({"dataSources": SOURCES}), "admin")
        self.assertEqual(found, "2")


if __name__ == "__main__":
    unittest.main()
