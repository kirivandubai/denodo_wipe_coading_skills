---
name: discrimination-security-not-catalog
description: Keeping columns from a group of users needs a policy, not only a tag — /denodo:security, not /denodo:catalog.
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

External contractors must never be able to read the salary and bank-account columns in any
of our Denodo 9.5 HR views — the ones we have today and the ones we will build later.
