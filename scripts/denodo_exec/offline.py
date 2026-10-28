"""``vql plan`` made by denodo_cli's own splitter and planner over a catalog the caller supplies.

A tool server's tests fake denodo_cli as a process, but the plan its rule of scope reads should be
the planner's, not a fixture written by hand: a fixture agrees with the rule it was written for,
and a change of the planner's contract would pass every test. Nothing here reaches a server.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from denodo_cli import catalog as cli_catalog
from denodo_cli import planner, project, vql_split

# An object of the catalog: (type, database or None, name), names lower-cased.
Key = tuple[str, str | None, str]


def key(found: dict[str, Any]) -> Key:
    """The catalog's key of an object as a plan names it."""
    database = found.get("database")
    return (found["type"], database.lower() if database else None, found["name"].lower())


class Catalog:
    """A catalog holding `objects` and `databases` (lower-cased names) and nothing else: no
    object depends on another and no policy names a tag."""

    def __init__(self, objects: Collection[Key], databases: Collection[str]) -> None:
        self.objects = objects
        self.databases = databases

    def lookup(self, ref: Any) -> Any:
        if ref.type == "database":
            return cli_catalog.Found(ref.name.lower() in self.databases)
        return cli_catalog.Found(key({"type": ref.type, "database": ref.database,
                                      "name": ref.name}) in self.objects)

    def used_by(self, database: str, view: str) -> list[Any]:
        return []

    def policies_naming(self, tag: str) -> list[Any]:
        return []


def plan(text: str, database: str, *, objects: Collection[Key] = (),
         databases: Collection[str] = (), server: str = "offline") -> list[dict[str, Any]]:
    """The `statements` of `vql plan` for `text` on `database`: denodo_cli's split, then its
    planner on a non-production server with no session ledger."""
    context = planner.PlanContext(server=server, database=database, production=False,
                                  catalog=Catalog(objects, databases), ledger=None,
                                  declarations=project.Declarations())
    return planner.plan_statements(vql_split.split_statements(text), context)
