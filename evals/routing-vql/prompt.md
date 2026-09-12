---
name: routing-vql
description: An open-ended "where do I start with Denodo" request must reach the entry-point skill /denodo:vql.
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

I have a Denodo 9.5 server and a pile of sources I want to expose to analysts, and I would
like to build it the way you would build code rather than by clicking around the admin
tool. Where do I start, and what are the rules of the road?
