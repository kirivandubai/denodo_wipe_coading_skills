---
name: routing-security
description: Masking columns for one role is a global security policy over tagged columns, and must reach /denodo:security.
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

In our Denodo 9.5 database `crm`, people with the analyst role must not see customers'
e-mail addresses and phone numbers — they should get them masked — while customer support
keeps seeing the real values. How do we set that up?
