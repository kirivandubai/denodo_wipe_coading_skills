---
name: discrimination-derived-view
description: Building on top of existing base views must reach /denodo:views and must not reach /denodo:datasources.
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

The base views over our CRM are already in place in Denodo 9.5 and return rows. Build the
customer 360 view on top of them.
