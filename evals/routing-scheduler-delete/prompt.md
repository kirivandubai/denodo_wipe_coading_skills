---
name: routing-scheduler-delete
description: Deleting a Denodo Scheduler job must reach /denodo:scheduler.
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

We no longer need the weekly CSV export of `sales_by_region`. Please delete that job from our Denodo 9.5 Scheduler — it's in the project `finance_reports`.
