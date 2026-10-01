---
name: routing-marketplace-rename
description: Renaming a view that is published in the Data Marketplace with tags, a category and an endorsement must reach /denodo:marketplace.
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

We have to rename the view `policy_holders_v2` in database `insurance` to `policy_holders`
in Denodo 9.5. Analysts know it from the Data Marketplace, where it carries our "Certified"
tag, sits in the Policy360 category and has an endorsement from the data owner. How do we
rename it without losing all of that?
