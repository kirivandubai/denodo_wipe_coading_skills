---
name: routing-dml-app-view
description: A view an application inserts through, limited to its own rows and returning the generated key, is a writable view — /denodo:dml.
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

Our order-entry web app will insert orders through Denodo 9.5 instead of connecting to the database directly. It must only be able to create and change orders of its own sales region, and after each insert it needs the order number the database generated. What should we give it to write to?
