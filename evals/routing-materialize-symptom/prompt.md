---
name: routing-materialize-symptom
description: A REFRESH that fails on a table made by the CREATE REMOTE TABLE command must reach /denodo:materialize.
tags: [routing]
runs: 3
max_turns: 8
allowed_tools: [Skill]
append_system_prompt: |
  The workspace is an empty scratch directory: there are no project files, no Denodo
  profiles, no credentials and no reachable server, so searching the filesystem will
  find nothing. Answer the request in prose — say what you would create and how —
  rather than trying to create or run anything.
---

In Denodo 9.5, `REFRESH bv_weekly_sales;` fails with "The REFRESH command is only valid for Summaries and Remote Tables". The table behind that base view was created last month with CREATE REMOTE TABLE into our SQL Server reporting schema, and the base view was added by hand afterwards. How do we get it refreshed every week?
