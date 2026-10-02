---
name: routing-materialize-summary
description: "Aggregate queries that cannot be changed, answered from precomputed figures, are a summary: /denodo:materialize."
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

Our BI dashboards aggregate sales by region and month over the Denodo 9.5 view `sales`, which joins a billion-row fact table in Snowflake with three dimensions from other systems. Every panel takes 20 seconds. The BI tool generates the SQL, so we cannot change the queries, and figures as of last night are fine for these dashboards. What can Denodo do?
