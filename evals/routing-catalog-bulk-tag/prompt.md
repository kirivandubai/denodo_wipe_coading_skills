---
name: routing-catalog-bulk-tag
description: One VDP tag on every matching column of a large database must reach /denodo:catalog and must not reach /denodo:marketplace.
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

The `crm` database in Denodo 9.5 has a few hundred views. Every column in it that holds an
email address or a phone number has to carry our Virtual DataPort tag `contact`, so that a
`GET_VIEW_TAGS` report shows where contact details live. Some of the views are mine, some
are other teams'.
