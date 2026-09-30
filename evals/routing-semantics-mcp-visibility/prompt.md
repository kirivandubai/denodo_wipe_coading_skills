---
name: routing-semantics-mcp-visibility
description: An AI agent that does not see a view through the Denodo MCP Server must reach /denodo:semantics.
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

We connected an AI agent to Denodo 9.5 through the Denodo MCP Server. It finds most of our
views, but `policy_renewals` is simply not there for it — it says no such view exists.
Why does the agent not see it, and what do we change?
