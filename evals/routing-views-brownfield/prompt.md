---
name: routing-views-brownfield
description: Changing a view built in Design Studio that has no file in the project must reach /denodo:views, which starts the file from the server.
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

The BI team built `customer_360` in Design Studio, and our repository has no file for it. It
needs one more column, the customer's signup channel from `bv_crm_customer`. Make the change in
Denodo 9.5.
