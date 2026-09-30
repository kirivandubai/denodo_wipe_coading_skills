---
name: discrimination-json-array
description: Turning the array of an existing JSON base view into rows must reach /denodo:views and must not reach /denodo:datasources.
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

Our JSON orders export is already connected in Denodo 9.5: the base view `bv_orders` returns
one row per order, and `lines` is an array column. Give me a view with one row per order line,
with the order id and the customer next to each line.
