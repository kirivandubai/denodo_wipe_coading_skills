---
name: discrimination-views-not-dml
description: A filtered view people only read is a derived view for /denodo:views; nothing is written through it.
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

In Denodo 9.5, build a view of the open orders only — status 'open' — over our `bv_orders` base view, for the operations dashboard to read.
