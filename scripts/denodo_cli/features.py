"""What a server has (T40): its bundle, its cache database, its LLM and optimizer switches.

``env check`` reports these and ``verify`` reads them before its first step: a step that needs
a feature the server lacks is skipped with the reason instead of failing the chain, and the
values that belong to the installation — the embedding model, the cache data source, the
Scheduler's data source — come from here instead of from the manifest.

Every call is read-only, and every failure leaves its feature unknown (``None``): a
non-administrator cannot read server settings, and that is an answer, not an error.
``GET_PARAMETER`` can read any server setting, secrets included, so it is only ever asked for
the properties of ``PARAMETERS``.
"""

from __future__ import annotations

from typing import Any

# Short name -> server setting. Nothing that holds a secret: names, switches and models only.
PARAMETERS: dict[str, str] = {
    "llm_enabled": "com.denodo.vdb.llm.integration.enabled",
    "llm_provider": "com.denodo.vdb.llm.integration.apiType",
    "llm_model": "com.denodo.vdb.llm.integration.modelName",
    "embedding_provider": "com.denodo.vdb.vector.integration.embeddingModelConfiguration.embeddingModelProvider",
    "embedding_model": "com.denodo.vdb.vector.integration.embeddingModelConfiguration.modelName",
    "embedding_disabled": ("com.denodo.vdb.vector.integration.embeddingModelConfiguration"
                           ".vectorizationFeatures.disabled"),
    "summary_rewrite": "com.denodo.vdb.interpreter.execution.SelectAction.summaryRewrite",
    "data_movement": "com.denodo.vdb.interpreter.execution.SelectAction.dataMovement",
}

# The names a step may require (`requires` in verification/chain.toml).
FEATURE_NAMES = ("enterprise_plus", "llm", "embedding", "cache", "summary_rewrite", "data_movement",
                 "impersonation")

# Why a step needing the feature cannot run without it — the second half of a skip reason.
FEATURE_REASONS: dict[str, str] = {
    "enterprise_plus": ("the license is not Enterprise Plus (VALIDATE_MPP_LICENSE answers max_processors = -1); "
                        "tags, global security policies and the AI functions need that bundle"),
    "llm": "no LLM is configured (Server configuration > Denodo Assistant)",
    "embedding": "no embedding model is configured, or vectorization is disabled",
    "cache": "the cache is off on this server (GET_CACHE_CONFIGURATION status OFF)",
    "summary_rewrite": "summary rewriting is switched off in the server settings",
    "data_movement": "data movement is switched off in the server settings",
    "impersonation": ("the profile's user may not impersonate (it lacks the impersonator role), so a check "
                      "cannot read as another user"),
}


def _rows(transport, statement: str) -> list[dict[str, Any]] | None:
    try:
        result = transport.execute(statement)
    except Exception:  # noqa: BLE001 — a refusal is an unknown, not a failed probe
        return None
    columns = result.columns or []
    return [dict(zip(columns, row)) for row in (result.rows or [])]


def _flag(value: Any) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return True if text == "true" else False if text == "false" else None


def _license(transport) -> tuple[bool | None, dict | None]:
    rows = _rows(transport, "SELECT max_processors, current_processors, status, details FROM VALIDATE_MPP_LICENSE()")
    if not rows or "max_processors" not in rows[0]:
        return None, None
    row = rows[0]
    try:
        enterprise_plus = int(row["max_processors"]) != -1   # documented: -1 unless Enterprise Plus
    except (TypeError, ValueError):
        enterprise_plus = None
    return enterprise_plus, {"status": row.get("status"), "details": row.get("details")}


def _cache(transport) -> dict | None:
    rows = _rows(transport, "SELECT database_datasource_name, datasource_name, adapter_database_name, "
                            "adapter_database_version, status, target_catalog, target_schema "
                            "FROM GET_CACHE_CONFIGURATION() WHERE database_name IS NULL")
    if not rows or "status" not in rows[0]:
        return None
    row = rows[0]
    return {"on": str(row.get("status") or "").upper() == "ON",
            "data_source_database": row.get("database_datasource_name"),
            "data_source": row.get("datasource_name"),
            "adapter": row.get("adapter_database_name"),
            "adapter_version": row.get("adapter_database_version"),
            "catalog": row.get("target_catalog"),
            "schema": row.get("target_schema")}


def _parameters(transport) -> dict[str, Any] | None:
    """Every property of ``PARAMETERS`` in one statement; ``None`` when the server refuses it."""
    statement = " UNION ALL ".join(
        f"SELECT '{name}' AS name, property_value FROM GET_PARAMETER() WHERE input_property_name = '{prop}'"
        for name, prop in PARAMETERS.items())
    rows = _rows(transport, statement)
    if rows is None or (rows and "property_value" not in rows[0]):
        return None
    return {row.get("name"): row.get("property_value") for row in rows}


def read_features(transport) -> dict:
    """The server's features, from an open VQL session. Unknown is ``None``, never a guess."""
    enterprise_plus, mpp = _license(transport)
    params = _parameters(transport)
    llm = embedding = summary_rewrite = data_movement = None
    if params is not None:
        llm = {"on": bool(_flag(params.get("llm_enabled")) and params.get("llm_model")),
               "provider": params.get("llm_provider"), "model": params.get("llm_model")}
        embedding = {"on": bool(params.get("embedding_model")) and _flag(params.get("embedding_disabled")) is not True,
                     "provider": params.get("embedding_provider"), "model": params.get("embedding_model")}
        summary_rewrite = _flag(params.get("summary_rewrite"))
        data_movement = _flag(params.get("data_movement"))
    return {"enterprise_plus": enterprise_plus, "mpp": mpp, "cache": _cache(transport), "llm": llm,
            "embedding": embedding, "summary_rewrite": summary_rewrite, "data_movement": data_movement}


def feature_state(features: dict, name: str) -> bool | None:
    """Whether the server has ``name`` (one of ``FEATURE_NAMES``): ``None`` when it did not say."""
    value = features.get(name)
    if isinstance(value, dict):
        return value.get("on")
    return value


def server_values(features: dict) -> dict[str, str]:
    """The chain's ``@server`` values the server answered; one it did not answer is left out."""
    cache = features.get("cache") or {}
    embedding = features.get("embedding") or {}
    candidates = {
        "embedding_model": embedding.get("model"),
        "write_datasource_database": cache.get("data_source_database"),
        "write_datasource_name": cache.get("data_source"),
        "write_catalog": cache.get("catalog"),
        "write_schema": cache.get("schema"),
        "write_dialect": cache.get("adapter"),
    }
    return {name: str(value) for name, value in candidates.items() if value not in (None, "")}


def scheduler_data_source(rest, user: str) -> tuple[str | None, list[dict]]:
    """The VDP data source of the Scheduler a job of the chain runs through, as the profile's user.

    The one VDP data source whose ``login`` is ``user``; with none or several the chain cannot
    choose, and the candidates go into the reason of the skip.
    """
    try:
        result = rest.call("GET", "/public/api/dataSources", timeout=30)
    except Exception:  # noqa: BLE001
        return None, []
    if not result.ok:
        return None, []
    body = result.body
    if isinstance(body, dict):
        body = body.get("dataSources") or body.get("list") or []
    sources = [s for s in body or [] if isinstance(s, dict) and str(s.get("type", "")).upper() == "VDP"]
    candidates = [{"id": s.get("id"), "projectName": s.get("projectName"), "login": s.get("login"),
                   "connectionURI": s.get("connectionURI")} for s in sources]
    mine = [c for c in candidates if c["login"] == user]
    return (str(mine[0]["id"]) if len(mine) == 1 else None), (mine or candidates)
