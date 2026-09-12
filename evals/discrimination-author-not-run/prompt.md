---
name: discrimination-author-not-run
description: Authoring VQL into a file must reach the authoring skills and must not reach /denodo:execute.
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

Draft the VQL for a derived view that joins `orders` and `customers` into a monthly revenue
mart, and leave it in a file in the project. I will review it and apply it to a server
myself later — nothing should be run anywhere for now.
