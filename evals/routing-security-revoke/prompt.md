---
name: routing-security-revoke
description: Taking a person's access away must reach /denodo:security.
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

Marco left the analytics team yesterday. In our Denodo 9.5 server he should no longer be able to read anything in the `sales_marts` database — make sure his access is gone.
