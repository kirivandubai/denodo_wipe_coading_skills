"""Transport contract. One channel per object: VQL for Virtual DataPort, REST for
Data Marketplace (design spec, section 7.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..profiles import Profile


@dataclass
class VqlResult:
    statement: str
    columns: list[str] | None      # None when the statement returned no result set
    rows: list[list[Any]] | None

    @property
    def row_count(self) -> int | None:
        return None if self.rows is None else len(self.rows)


class VqlTransport(Protocol):
    """A live session against Virtual DataPort. Errors propagate as exceptions."""

    def __init__(self, profile: Profile, database: str | None = None) -> None: ...

    def execute(self, statement: str) -> VqlResult: ...

    def close(self) -> None: ...


@dataclass
class HttpResult:
    status: int
    body: Any                      # parsed JSON, raw text, or None for an empty body
    headers: dict[str, str] = field(default_factory=dict)
    elapsed_ms: int = 0

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300
