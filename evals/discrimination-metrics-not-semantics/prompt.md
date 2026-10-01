---
name: discrimination-metrics-not-semantics
description: A semantic layer of KPIs for an AI agent is a metric view (/denodo:metrics), not the description audit of /denodo:semantics.
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

We are building a semantic layer in Denodo 9.5 for our AI agent. The agent should never
compute revenue or churn rate itself: define those two KPIs once over the subscriptions fact
view and its customer and plan dimensions, so the agent only picks the dimensions and gets
the governed numbers.
