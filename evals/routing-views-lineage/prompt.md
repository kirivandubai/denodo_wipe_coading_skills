---
name: routing-views-lineage
description: Asking where a field of an existing view comes from must reach /denodo:views.
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

The finance dashboard reads `net_revenue` from the `sales_summary` view in Denodo 9.5. Where
does that field come from — which source table and column, through which views, and is it
calculated anywhere along the way?
