---
name: discrimination-views-not-testing
description: "Checking once that a view just created works is the Verify of /denodo:views, not a regression suite."
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

I just created the derived view `iv_order_lines` in Denodo 9.5 — order headers joined to their lines. Before I build anything on it, check that it actually works: that it reads, and that the join didn't drop or duplicate any lines.
