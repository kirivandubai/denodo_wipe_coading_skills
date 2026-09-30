---
name: routing-views-union
description: Combining several views of one entity into a single view, with a query for one source reading only that source, must reach /denodo:views.
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

In Denodo 9.5 we have two base views, `bv_store_returns` and `bv_web_returns`, whose columns
are named differently. Combine them into one view of all returns, with a column that says
which channel each row came from, so that a query for web returns reads only the web source.
