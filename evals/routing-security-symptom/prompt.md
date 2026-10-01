---
name: routing-security-symptom
description: A user who sees rows a restriction should hide is a policy diagnosis, and must reach /denodo:security.
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

In Denodo 9.5 our West-region analysts are supposed to see only California customers, and
that worked when we set it up. Now one of them sees customers from every state in the
`customer` view. What could have happened, and how do we find out?
