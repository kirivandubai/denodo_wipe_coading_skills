---
name: routing-datasources
description: Connecting a relational source and producing base views must reach /denodo:datasources.
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

Our orders live in a PostgreSQL database. Get that database into Denodo 9.5 and give me
base views over the tables in its `public` schema.
