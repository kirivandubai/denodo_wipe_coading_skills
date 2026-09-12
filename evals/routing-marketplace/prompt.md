---
name: routing-marketplace
description: Making an asset from another tool visible in the Data Marketplace must reach /denodo:marketplace.
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

Our BI dashboards are built in another tool entirely. Anyone browsing the Denodo 9.5 Data
Marketplace has no idea which of them read which views. Make the dashboards show up there
next to the views they consume.
