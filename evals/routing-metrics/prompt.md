---
name: routing-metrics
description: Asking to define KPIs once in Denodo so every BI tool and AI agent uses the same definition must reach /denodo:metrics.
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

Every dashboard in our company computes revenue, gross margin and order count its own way,
and the numbers never match. In Denodo 9.5 we have the sales fact view and the customer,
product and calendar dimension views. Define these KPIs once in Denodo so Power BI and our AI
agent both use the same definitions, sliceable by customer, product and month.
