---
name: routing-materialize
description: "A query result wanted as a real table in a warehouse, refreshed nightly, is a remote table: /denodo:materialize."
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

Our data science team wants the result of the Denodo 9.5 view `customer_360` as a real table in the `analytics` schema of our PostgreSQL warehouse, so their notebooks can read it directly without going through Denodo. It should be refreshed every night. We already have a JDBC data source for that warehouse in Denodo. How do we set it up?
