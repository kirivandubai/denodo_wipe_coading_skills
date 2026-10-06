---
name: routing-datasources-bulk
description: Base views over every table of several schemas at once must reach /denodo:datasources.
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

Our SQL Server warehouse has three schemas, `sales`, `stock` and `hr`, about sixty tables in
all. I need a Denodo 9.5 base view over every one of them in the database `ops_lake`, named
consistently, and some of them were already onboarded by hand last year.
