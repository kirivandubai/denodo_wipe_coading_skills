---
name: discrimination-materialize-not-dml
description: Creating a new table from a view's result is a remote table for /denodo:materialize, not an INSERT for /denodo:dml.
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

Create a new table `region_month_snapshot` in the `reporting` schema of our SQL Server database, holding what the Denodo 9.5 view `region_month_sales` returns today. It must not change afterwards: the auditors compare it with their own extract. Denodo already has a JDBC data source for that database.
