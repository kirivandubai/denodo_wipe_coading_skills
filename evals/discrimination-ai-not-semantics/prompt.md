---
name: discrimination-ai-not-semantics
description: Writing descriptions for undocumented views, even with the Denodo Assistant, is metadata work for /denodo:semantics, not the LLM functions of /denodo:ai.
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

Most views in our Denodo 9.5 database `finance` have no description at all, and the AI
assistant our analysts use cannot make sense of them. Can the Denodo Assistant draft the view
and field descriptions for us, so we only review them?
