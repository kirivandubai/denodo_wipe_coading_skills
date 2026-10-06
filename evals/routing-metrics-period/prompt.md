---
name: routing-metrics-period
description: A year-over-year or to-date comparison over a metric view must reach /denodo:metrics.
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

We have a Denodo 9.5 metric view `revenue_metrics` with an order date dimension. Finance wants a view with revenue per year and its change against the previous year in percent, plus a month-to-date figure against the same days last year.
