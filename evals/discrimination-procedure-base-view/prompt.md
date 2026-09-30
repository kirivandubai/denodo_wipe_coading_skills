---
name: discrimination-procedure-base-view
description: A base view over a database's stored function is a data source job — /denodo:datasources, not /denodo:procedures.
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

Our PostgreSQL source `ds_billing` is already connected in Denodo 9.5. The database has a
function `billing.open_balance(customer_id)` that returns a customer's open balance; make it
available in Denodo as a base view.
