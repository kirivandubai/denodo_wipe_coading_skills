---
name: routing-semantics-bulk
description: Descriptions for hundreds of views, approved in batches, must reach /denodo:semantics.
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

The Denodo 9.5 database `finance_dw` has about three hundred views and not one description,
and the MCP assistant on top of it is guessing. Write descriptions for all of them — I want
to approve them in batches of thirty or so, not all at once.
