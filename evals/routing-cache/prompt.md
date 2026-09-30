---
name: routing-cache
description: Asking to put a full cache on a view and load it must reach /denodo:cache.
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

Our dashboard reads the `order_line` view in Denodo 9.5 and every refresh goes back to the
source database, which is slow. Put a full cache on `order_line` and load it, so the
dashboard reads from the cache instead.
