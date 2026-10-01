---
name: discrimination-mart-not-metrics
description: A mart of one fixed grain for one report is a derived view (/denodo:views), not a metric view.
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

In Denodo 9.5, build me a mart for the monthly returns report: returned amount and number of
returns per store and month, from the store returns base view and the store base view. One
row per store and month; the report reads nothing else.
