---
name: routing-dml
description: Correcting rows in the database behind a Denodo view is a write through the view, and must reach /denodo:dml.
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

Three customers in our Denodo 9.5 view `customer` have the wrong country: ids 12, 48 and 77 should be 'DE', not 'AT'. The view is a base view over our CRM database in SQL Server. Can you fix those three records through Denodo?
