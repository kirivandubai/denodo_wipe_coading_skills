---
name: routing-procedures
description: A request for procedural logic on the server (branching, no Java) must reach /denodo:procedures.
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

We want a small routine to live inside Denodo 9.5 itself: it takes an order amount, decides
which size band the order falls into and hands the band back. Branching logic, nothing that
needs Java. How would you build that?
