---
name: routing-ai-semantic-search
description: Finding the rows closest in meaning to a sentence over stored embeddings is semantic search, and must reach /denodo:ai.
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

Denodo 9.5 reads a PostgreSQL table of help-centre article passages; each row has the passage
text and its embedding (pgvector). Our app should send a customer's question and get back the
five passages closest in meaning. Can Denodo serve that as a view the app queries with the
question?
