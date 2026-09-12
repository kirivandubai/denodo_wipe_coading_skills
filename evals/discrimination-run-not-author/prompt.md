---
name: discrimination-run-not-author
description: Interpreting a failed tool call must reach /denodo:execute and must not reach the object skills.
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

I ran the Denodo tool and instead of doing anything it printed
`{"ok": false, "error": {"kind": "connection", "message": "..."}}` and exited non-zero.
What is that telling me, and what do I do about it?
