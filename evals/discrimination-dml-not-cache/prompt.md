---
name: discrimination-dml-not-cache
description: Loading rows from a file into a database table through Denodo is an INSERT … SELECT for /denodo:dml, not a cache load.
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

We received 500 new product records as a CSV, already connected in Denodo 9.5 as the base view `bv_new_products`. Load them into the `product` table of our SQL Server catalog database — Denodo has a base view `bv_catalog_product` over it.
