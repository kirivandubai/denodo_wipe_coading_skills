"""``denodo+psycopg2`` on port 9996 — the default VQL transport.

Three facts from spike T2 (section 3) shape this file:

* autocommit cannot be requested through SQLAlchemy (the Denodo dialect has no
  ``set_isolation_level``); it is switched on at the DBAPI connection via the
  ``connect`` event;
* VQL goes through a raw psycopg2 cursor with no parameters, otherwise a ``%`` in
  the user's VQL is interpolated and the statement breaks;
* a ``CONNECT DATABASE`` switches the session, so one object holds exactly one
  connection for its whole life — a pooled second connection would be in the wrong
  database.
"""

from __future__ import annotations

import sqlalchemy as sa

from ..profiles import Profile
from .base import VqlResult


class VqlPsycopg2Transport:
    def __init__(self, profile: Profile, database: str | None = None) -> None:
        url = sa.URL.create(
            "denodo+psycopg2",
            username=profile.user,
            password=profile.password,
            host=profile.host,
            port=profile.port,
            database=database or profile.database,
        )
        self._engine = sa.create_engine(url, poolclass=sa.pool.StaticPool)

        @sa.event.listens_for(self._engine, "connect")
        def _autocommit(dbapi_conn, _record):
            dbapi_conn.autocommit = True

        self._connection = self._engine.connect()

    def execute(self, statement: str) -> VqlResult:
        cursor = self._connection.connection.cursor()
        try:
            cursor.execute(statement)
            if cursor.description is None:
                return VqlResult(statement=statement, columns=None, rows=None)
            columns = [col[0] for col in cursor.description]
            rows = [list(row) for row in cursor.fetchall()]
            return VqlResult(statement=statement, columns=columns, rows=rows)
        finally:
            cursor.close()

    def close(self) -> None:
        self._connection.close()
        self._engine.dispose()
