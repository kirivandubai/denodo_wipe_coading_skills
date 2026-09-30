---
name: routing-views-delegation
description: Asking whether a mart over a database actually runs in that database must reach /denodo:views.
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

I built a mart in Denodo 9.5 that joins and aggregates three of our Oracle tables. It returns
the right numbers, but how do I know the join and the aggregation really run in Oracle, and
Denodo is not pulling every row across?
