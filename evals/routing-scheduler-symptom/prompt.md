---
name: routing-scheduler-symptom
description: "A cache that grows after every scheduled refresh while the job reports COMPLETE reaches /denodo:scheduler."
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

Since we set up the nightly refresh job for the cache of a Denodo 9.5 view, the figures on the dashboard grow every morning: yesterday twice the real number, today three times. The job's report says COMPLETE every night. What is going on, and how do we fix the job?
