---
name: routing-catalog
description: An unambiguous container request (virtual database plus folders) must reach /denodo:catalog.
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

We are starting a new Denodo 9.5 project. I need a virtual database called `sales_core`,
and inside it a folder tree to keep the staging views separate from the published ones.
Walk me through how you would set that up.
