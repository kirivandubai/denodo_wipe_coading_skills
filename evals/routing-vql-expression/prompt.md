---
name: routing-vql-expression
description: Writing the expressions of a query over a Denodo view — substrings, date labels, time differences — must reach /denodo:vql, which holds the table of silent dialect deltas.
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

I'm writing a SELECT against a view `orders` in Denodo. I need the first three characters
of `order_code`, the order month formatted like 2024-03 from `order_date`, and the number of
hours between `created_at` and `shipped_at`. How do I write those three expressions?
