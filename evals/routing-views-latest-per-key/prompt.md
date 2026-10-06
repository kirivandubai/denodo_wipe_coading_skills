---
name: routing-views-latest-per-key
description: The latest row per key, or de-duplicating a feed, must reach /denodo:views.
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

Our Denodo 9.5 base view `bv_customer_changes` gets a new row every time a customer record changes, and some loads arrive twice. I need a derived view with exactly one row per customer — their most recent record.
