---
name: routing-execute
description: Applying a .vql file to a live server and running a test SELECT must reach /denodo:execute.
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

`sales_core.vql` is finished and reviewed. Apply it to the server behind the `lab` profile,
then run a test SELECT against the view it creates so we know it returns rows.
