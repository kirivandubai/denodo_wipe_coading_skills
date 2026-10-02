---
name: routing-ai-cost-symptom
description: A view with an LLM column that makes a dashboard slow and the provider's bill grow is a cost diagnosis of the LLM functions, and must reach /denodo:ai.
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

Last week someone added a sentiment column to one of our Denodo 9.5 views using the AI
functions. Since then the dashboard on top of it takes minutes to refresh, the bill from our
LLM provider has tripled, and some users get an error about privileges to execute a function.
What is going on, and what should we change?
