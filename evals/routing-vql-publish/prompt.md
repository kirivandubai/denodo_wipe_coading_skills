---
name: routing-vql-publish
description: Publishing a view as a REST API for an application is outside the plugin and creates nothing — /denodo:vql says so, and names the built-in RESTful web service.
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

The ops app needs to read our `returns_by_reason` view in Denodo 9.5 as a REST API that returns
JSON. Can you publish it as a web service for them?
