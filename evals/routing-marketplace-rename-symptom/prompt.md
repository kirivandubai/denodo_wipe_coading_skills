---
name: routing-marketplace-rename-symptom
description: Tags, a category and an endorsement gone from the Data Marketplace after a view was renamed must reach /denodo:marketplace.
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

Someone renamed one of our views in Denodo 9.5 and then pressed "Sync with VDP" in the Data
Marketplace. The view is there under its new name now, but its tags, its category and the
owner's endorsement are all gone. What happened, and can we get them back?
