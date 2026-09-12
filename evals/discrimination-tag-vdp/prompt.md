---
name: discrimination-tag-vdp
description: A tag inside Virtual DataPort must reach /denodo:catalog and must not reach /denodo:marketplace.
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

Mark the `customer_email` column as PII in Virtual DataPort, so that the marking is part of
the view definition itself and travels with it when we promote the database.
