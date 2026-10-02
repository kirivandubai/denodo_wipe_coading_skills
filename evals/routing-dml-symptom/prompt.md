---
name: routing-dml-symptom
description: Updates through a view failing with 'Update operation is not allowed' or 'No update methods ready to be run' are a write question — /denodo:dml.
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

In Denodo 9.5, UPDATE statements through our view `customer_orders` fail with "View 'customer_orders'. Update operation is not allowed", and through `orders_by_month` with "No update methods ready to be run". Through the base view the same update works. Why, and how should these updates be done?
