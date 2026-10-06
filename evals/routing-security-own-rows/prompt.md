---
name: routing-security-own-rows
description: Each person seeing only their own rows must reach /denodo:security.
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

In Denodo 9.5, our `opportunities` view has an `owner_login` column. Each sales rep should only ever see the opportunities they own, while sales leadership keeps seeing all of them. How do I set that up?
