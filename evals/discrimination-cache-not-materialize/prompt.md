---
name: discrimination-cache-not-materialize
description: Switching on and reloading the full cache of a view is /denodo:cache, not a table of its own.
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

Turn on the full cache for our Denodo 9.5 view `customer_360` so its queries stop hitting the CRM, and give me the statement our scheduler should run every morning to reload it.
