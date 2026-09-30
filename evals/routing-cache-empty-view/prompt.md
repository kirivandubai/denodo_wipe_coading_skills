---
name: routing-cache-empty-view
description: A cached view that suddenly returns no rows, or every row twice, is a cache question — /denodo:cache.
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

Since we switched the `customer` view in Denodo 9.5 to full cache mode it returns 0 rows,
and on the other environment, where someone refreshed it twice, every customer shows up
twice. What is going on and how do I fix it?
