---
name: routing-testing-safety-net
description: "A check kept in the repo, before a rewrite, that consumers see no difference after it is a regression suite: /denodo:testing."
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

Next week I'm rewriting the integration views under the Denodo 9.5 view `orders_by_customer`, which our finance dashboard reads. Before I start, I want something in the repo that tells me afterwards — and every time CI runs — whether the dashboard would see any difference. Set it up.
