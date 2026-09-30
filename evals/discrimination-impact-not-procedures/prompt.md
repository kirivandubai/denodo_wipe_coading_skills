---
name: discrimination-impact-not-procedures
description: Asking what uses a view is answered by predefined procedures, but it is a question about changing a view — /denodo:views, not /denodo:procedures.
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

Before I change the `orders` view in Denodo 9.5, I need to know what uses this view — every
view built on it, and whether any of them would break if I renamed its `order_ts` column.
