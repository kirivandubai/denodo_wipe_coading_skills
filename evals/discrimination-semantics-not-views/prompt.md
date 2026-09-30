---
name: discrimination-semantics-not-views
description: Adding descriptions and a primary key to views that already exist is /denodo:semantics, although views are /denodo:views.
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

The views in our Denodo 9.5 database `hr_reporting` were built in Design Studio years ago:
none has a description, the field descriptions are empty and there are no primary keys.
Fill that metadata in — the views themselves stay as they are.
