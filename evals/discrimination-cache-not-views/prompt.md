---
name: discrimination-cache-not-views
description: Clearing and switching off the cache of an existing view is /denodo:cache, although the statement is an ALTER VIEW.
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

We no longer need the materialized copy of the `sales_by_region` view in Denodo 9.5. Switch
its cache off and clear what is stored for it, so it reads the sources again.
