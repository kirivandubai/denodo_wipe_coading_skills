---
name: routing-views
description: Building a mart on top of views that already exist must reach /denodo:views.
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

The `customer` and `order` base views are already in Denodo 9.5. Build a mart on top of
them that joins the two and aggregates revenue per customer per month, and put it in its
own folder.
