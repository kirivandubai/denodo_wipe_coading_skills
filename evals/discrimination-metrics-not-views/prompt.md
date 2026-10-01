---
name: discrimination-metrics-not-views
description: Governed metrics reused at any grain are a metric view (/denodo:metrics), although a view with aggregates is /denodo:views.
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

In our Denodo 9.5 database `finance`, the loan payments view is the fact and borrowers, loan
officers and dates are dimensions around it. Set up total paid, average payment and
number of late payments as governed metrics: analysts will slice them by any combination
of those dimensions from their BI tool, so no fixed grain.
