---
name: discrimination-tag-marketplace
description: A tag inside the Data Marketplace must reach /denodo:marketplace and must not reach /denodo:catalog.
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

Put a tag on this view in the Denodo 9.5 Data Marketplace, so that the analysts browsing
the catalog in their browser can filter the view list down to it.
