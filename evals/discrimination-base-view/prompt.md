---
name: discrimination-base-view
description: Onboarding a file as a queryable view must reach /denodo:datasources and must not reach /denodo:views.
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

Finance sent over `suppliers.csv`, a semicolon-delimited export with a header row. Get it
into Denodo 9.5 so the rest of the platform can query it as a view.
