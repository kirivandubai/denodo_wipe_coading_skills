"""``denodo+flightsql`` on port 9994 — structurally reserved, not implemented in v1
(design spec, section 12)."""

from __future__ import annotations


class VqlFlightSqlTransport:
    def __init__(self, profile, database=None):
        raise NotImplementedError(
            "the vql_flightsql transport is not part of v1; use transport = \"vql_psycopg2\""
        )
