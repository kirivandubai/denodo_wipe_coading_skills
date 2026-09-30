---
name: discrimination-semantics-not-marketplace
description: Preparing VDP views for AI consumers is /denodo:semantics, although the Data Marketplace is one of those consumers.
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

We are about to switch on Assisted Query in the Denodo 9.5 Data Marketplace and connect the
MCP Server to our `retail_sales` database. What metadata do the views need so the AI
understands them and can join them, and what is missing today?
