---
name: routing-ai
description: Labelling every row of a text column with the LLM configured on the server is the LLM functions, and must reach /denodo:ai.
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

We keep customer product reviews in a Denodo 9.5 view, `product_review`, one row per review
with the text in `review_text`. Our Denodo server is connected to an LLM. I'd like each review
to get a topic — quality, delivery, price or something else — and a sentiment, so the
merchandising team can filter on them.
