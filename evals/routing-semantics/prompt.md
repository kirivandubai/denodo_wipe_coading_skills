---
name: routing-semantics
description: Asking to describe the existing views of a database so an AI assistant understands them must reach /denodo:semantics.
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

Our Denodo 9.5 database `claims_analytics` has about forty views that nobody ever documented.
Next month the company's AI assistant will query it. Go through the database and describe
the views and their fields so the assistant understands what they hold.
