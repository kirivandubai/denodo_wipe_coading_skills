---
name: routing-metrics-query-symptom
description: A metric view that returns the same figure for AVG and SUM, and no rows for SELECT *, must reach /denodo:metrics.
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

In Denodo, `SELECT region, AVG(revenue) FROM sales_kpis GROUP BY region` gives exactly the
same numbers as `SUM(revenue)`, and `SELECT * FROM sales_kpis LIMIT 10` returns no rows at
all, without any error. `sales_kpis` is the metric view the BI team set up. What is going on,
and how should I query it?
