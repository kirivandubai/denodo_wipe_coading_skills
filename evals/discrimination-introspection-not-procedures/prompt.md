---
name: discrimination-introspection-not-procedures
description: Listing a JDBC source's tables runs through predefined procedures but is a data source job — /denodo:datasources, not /denodo:procedures.
tags: [discrimination]
runs: 3
max_turns: 8
allowed_tools: [Skill]
append_system_prompt: |
  The workspace is an empty scratch directory: there are no project files, no Denodo
  profiles, no credentials and no reachable server, so searching the filesystem will
  find nothing. Answer the request in prose — say what you would create and how —
  rather than trying to create or run anything.
---

The Oracle source `ds_orders_db` is already set up in Denodo 9.5 and reachable. Show me what
tables it has in the `RETAIL` schema, then turn two of them into base views.
