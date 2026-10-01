---
name: routing-security-grant
description: Giving a user a role, or a role read access to views, must reach /denodo:security.
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

Priya joined the finance team. In Denodo 9.5 she needs to query the views of the `finance`
database the same way the rest of the team does — give her that access.
