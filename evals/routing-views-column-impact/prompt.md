---
name: routing-views-column-impact
description: Asking whether a column of an existing view can be dropped, and what uses it, must reach /denodo:views.
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

Our source system is about to remove the column `legacy_segment`, and the `customer` view in
Denodo 9.5 still has it. Can I drop it from the view, or will something break? What uses it?
