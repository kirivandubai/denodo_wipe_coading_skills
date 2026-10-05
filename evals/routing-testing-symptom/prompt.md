---
name: routing-testing-symptom
description: "A red Denodo Testing Tool run with a header mismatch after a view gained a column is /denodo:testing."
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

Our CI has been failing on a Denodo test since I added a column to the view `customer_ltv`: "Test FAILED!: Expected data columns/headers do NOT match those returned by test after execution". The numbers in the view did not change. How do I fix the test?
