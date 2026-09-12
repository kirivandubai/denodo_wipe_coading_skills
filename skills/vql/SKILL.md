---
name: vql
description: Use when doing anything with Denodo — creating or changing a database, folder, tag, data source, wrapper, base view, derived view, interface view, association, or a Data Marketplace object; writing or fixing VQL; deciding where an object lives and what to name it; "build a mart", "connect a source", "vibe-code on Denodo". Start here when the request is ambiguous: this skill holds the working loop, the naming conventions, the safety rule and the map of the other Denodo skills.
---

# Working with Denodo

**VQL goes into a file in the project, and the file is what gets applied.** Objects that
exist only on a server exist in no artifact: nobody can review them, move them to the next
environment, or rebuild them after a rollback.

**Violating the letter of the rules below is violating their spirit.** This plugin gets
installed on production servers.

## The loop

```
intent in words
  → read .denodo/conventions.md if the project has one
  → decide placement: database, layer folder, name
  → write the statements into a .vql file in the project
  → apply the file with /denodo:execute
  → verify: DESC, and SELECT for anything that carries rows
  → the file stays in git
```

**Inline `-e` is for reading only** — `SELECT`, `DESC`, `GET_ELEMENTS()`, `GET_VIEW_TAGS()`.
Every `CREATE`, `ALTER` and `DROP` goes through a file, including the first exploratory one.

**Never create a probe object to test a hypothesis.** A `probe_a` view is an object: it
stays in the catalog, it is not in any file, and removing it needs the human's confirmation
like any other drop. Test the real statement in the real file — re-applying it is safe.

**One file per change, applied whole.** Do not keep a second "cleaned" copy next to it.
Templates are `CREATE OR REPLACE`, so when a statement fails, fix that statement and
re-apply the same file from the top.

Chain order, when several objects are involved: `database → folder → datasource → wrapper
→ base view → derived view → association`. Tags and marketplace objects come last: they
attach to things that must already exist.

## Naming and layout

Defaults below follow the Denodo VDP Naming Conventions. Lowercase with underscores,
singular nouns, no environment name anywhere in an object name (`sales`, never
`sales_dev` — the profile says which server you are on).

| Object | Name |
|---|---|
| Database | the project or domain: `sales_analytics` |
| Data source | `ds_<source system>` — one file source is one file, so a system that arrives as several files gets one per file, named for what is in it: `ds_retail_store`, `ds_retail_store_returns` |
| Wrapper | `wr_<source system>_<entity>` |
| Base view | `bv_<source system>_<entity>` |
| Derived view, integration layer | `iv_<what it does>` |
| Business entity view / interface view | the entity itself: `customer` |
| Association | `a_<principal>_<related>` |
| Summary | `s_<name>` |
| Tag | the concept: `pii`, `gdpr` |

Layers are folders, and every object gets a `FOLDER =`:

| Folder | What lives there |
|---|---|
| `/01 - connectivity` | data sources, wrappers, base views |
| `/02 - integration` | derived views that combine and transform |
| `/03 - business entities` | canonical views and interface views for consumers |
| `/06 - associations` | associations |

Create the layers you actually fill, not the whole table: a mart over two files needs
`/01`, `/02` and `/03`, and an empty `/06` is noise in someone's catalog.

Folder paths are quoted, and a parent must exist before its child:
`Cannot create folder /03 - business entities/sales: parent not found`. Create top-down;
drop bottom-up, because `DROP FOLDER IF EXISTS` will not remove a folder with content.

**A project may override all of this.** Before writing VQL, look for `.denodo/conventions.md`
in the project root (`cat .denodo/conventions.md 2>/dev/null`). It is plain markdown; a
section named after a rule above replaces that rule, anything it does not mention keeps the
default. If the project has one, it wins — do not "improve" its naming with the defaults.

## Idempotency

**`CREATE OR REPLACE` for every object type**, in every file. All twelve VQL object types
of v1 support it, including `DATABASE`.

- `IF NOT EXISTS` does not exist in Denodo. The server answers
  `Syntax error: Exception parsing query near 'IF'` — *verified: 9.5.1 (стенд, 2026-09-09)*.
- `CREATE OR REPLACE DATABASE` **keeps the objects inside the database** — *verified: 9.5.1
  (стенд, 2026-09-09)*. Do not split the database into a separate "bootstrap" file to
  protect it; that guess is wrong and it costs you a re-appliable file.
- `CREATE OR REPLACE VIEW` over a view that others depend on is fine when the change is
  additive — *verified: 9.5.1 (стенд, 2026-09-09)*. Removing or retyping a column that a
  dependent view selects is a breaking change: check dependents first.
- Assigning a tag needs both blocks — `ADD_TO ( ... ) REMOVE_FROM ( VIEWS () COLUMNS () )`
  — or it is a syntax error.
- **Data Marketplace has no `OR REPLACE`.** Every operation goes by numeric id, and an id
  only exists after creation, so idempotency there is a pair: `GET` the object by name,
  then `POST` to create or `PUT` to update. The status of a repeated `DELETE` differs per
  object type (`500`, `200`, `404`) — never rely on it, rely on the lookup.

Templates in the domain skills carry `-- verified: 9.5 (стенд, date)` or
`-- unverified: только по документации 9.5`. An unverified template is still worth using;
it just means the verification is yours to do, with `DESC` and a `SELECT`.

## Safety: you create, the human confirms destruction

| You do it yourself | Only after the human confirms |
|---|---|
| `CREATE` / `CREATE OR REPLACE` of an object | `DROP`, `TRUNCATE`, `DELETE` |
| Read-only `SELECT`, `DESC`, `GET_*`, `env check` — on any profile, production included | `ALTER` of an object that already exists |
| `GET` calls to the marketplace | every destructive marketplace call (below) |
| — | **any change at all on a profile with `production: true`, `CREATE` included** |

The confirmation is a yes in this conversation, after you have shown the exact statements
or calls. Not a yes to the task in general. "Do it on prod" is the task, not the yes.

Reading is always allowed, and on a production profile it is what you do *instead* of
guessing: check `env.production`, `DESC` what is already there, then come back with the
statements you propose to apply.

**For HTTP the rule goes by method and path, not by the verb in the text.** These are as
destructive as a `DROP`, and none of them contains the word:

| Call | What is lost |
|---|---|
| `DELETE /public/api/tags/{id}`, `/tags/delete-multiple` | the tag and every assignment of it |
| `DELETE /public/api/category-management/categories/{id}` | the category **and all its children** |
| `DELETE /public/api/external-tool-servers/{id}` | the server and **every element it imported** |
| `POST /public/api/tags/vdp/synchronize` | every imported VDP tag missing from the list you send |
| `POST /public/api/element-management/all/synchronize` with `proceedWithConflicts:"SERVER"` | local edits in the marketplace |
| `POST /public/api/views/{id}/tags`, `.../categories` | the view's previous assignments — this is "set", not "add" |

Sending a *complete* list to a `synchronize` call is not a substitute for asking: you are
still replacing a set you did not read out to the human.

| Rationalization | Reality |
|---|---|
| "The profile is `dev` and the tool did not refuse" | The tool refuses only on production. Non-refusal is not consent. |
| "They asked me to remove the tags — that *is* the confirmation" | They asked for an outcome. Confirmation is a yes to the listed statements, after you list them. |
| "It's a tag, we can recreate it" | You cannot recreate its assignments to views and columns; and a category takes its children with it. |
| "There's no `DROP` in this call" | The rule is method and path. `POST …/synchronize` deletes. |
| "Cleanup of my own probe objects doesn't count" | It is a `DROP` on a shared server. Same rule. |
| "I'll list what I removed in the summary" | Disclosure after the fact is not consent. |

**Red flags — stop and ask:** you are about to send `DELETE` or a `synchronize`; you are
writing `--allow-destructive`; `env.production` is `true`; you are removing something you
did not create in this session; you are "cleaning up" anything.

## Where to go from here

| Objects | Skill |
|---|---|
| Databases, folders, VDP tags | `/denodo:catalog` |
| Data sources, wrappers, base views (JDBC, DF, JSON) | `/denodo:datasources` |
| Derived views, interface views, associations | `/denodo:views` |
| Marketplace tags, categories, external elements (REST) | `/denodo:marketplace` |
| SELECT, expressions, Denodo dialect | `/denodo:query` |
| Running anything against a live server, reading its errors | `/denodo:execute` |

VDP tags (`CREATE TAG`, VQL, port 9996) and Data Marketplace tags
(`POST /public/api/tags`, REST) are different objects on different servers. "Tag" alone
does not tell you which — ask which one the human means, or look at where the object has
to be visible.
