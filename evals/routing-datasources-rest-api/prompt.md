---
name: routing-datasources-rest-api
description: A REST API as a source must reach /denodo:datasources, which routes it to Design Studio.
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

Our order service exposes a paginated REST API with bearer-token authentication. Bring its
orders into Denodo 9.5 as a base view the analysts can query.
