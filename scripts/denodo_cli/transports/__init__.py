"""Transport registry: profile ``transport`` name → class. Imports are lazy so that the
registry, and everything that only needs profiles or parsing, works without the driver
stack installed."""

from __future__ import annotations

import importlib

_VQL_TRANSPORTS = {
    "vql_psycopg2": ("denodo_cli.transports.vql_psycopg2", "VqlPsycopg2Transport"),
    "vql_flightsql": ("denodo_cli.transports.vql_flightsql", "VqlFlightSqlTransport"),
}


def vql_transport_names() -> list[str]:
    return list(_VQL_TRANSPORTS)


def get_vql_transport(name: str) -> type:
    try:
        module_name, class_name = _VQL_TRANSPORTS[name]
    except KeyError:
        raise KeyError(f"unknown VQL transport {name!r}; known: {', '.join(_VQL_TRANSPORTS)}") from None
    return getattr(importlib.import_module(module_name), class_name)


def get_rest_transport() -> type:
    return importlib.import_module("denodo_cli.transports.api_rest").RestTransport
