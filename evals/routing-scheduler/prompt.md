---
name: routing-scheduler
description: "A nightly reload of a view's cache by a Denodo Scheduler job is /denodo:scheduler."
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

Set up a Denodo Scheduler job that reloads the full cache of our Denodo 9.5 view `order_line` every night at 03:00, so the dashboard that reads it is fresh in the morning.
