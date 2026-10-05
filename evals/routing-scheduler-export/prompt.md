---
name: routing-scheduler-export
description: "A CSV export of a view at a set time, run by the platform itself, is /denodo:scheduler — the phrase names no Scheduler."
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

Every Monday at 07:00 the finance team needs the rows of our Denodo 9.5 view `weekly_sales` as a CSV file on the Denodo server, with a header line, replacing last week's file. Make Denodo produce it on its own every week.
