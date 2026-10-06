# A verification chain any server can run (T40)

**Status:** design for T40 ([TASKS.md](../../TASKS.md)); once implemented, the decisions are
folded into the [design spec](2026-09-04-denodo-skills-design.md), section 11.1. This file keeps
the detail: where each value comes from, what the server is asked, which data the fixtures read,
which blocks run and which do not, and how the two configurations were run.

## Why

`scripts/denodo verify` proves the templates against a live server, and until now only against
one kind of server: the Denodo demo image. The fixtures read the image's CSV files
(`/opt/denodo/demos/csv`), the write steps create their tables with SQL Server DDL, the AI steps
name one embedding model, the Scheduler steps one data source id, and the chain stops at the first
step a server cannot run — on a server without the Enterprise Plus bundle that is the step that
creates a tag. A user cannot learn which templates hold on their server, and the SQL Server
assumptions found in section A of the [review](2026-10-05-skills-review.md) cannot show on ours,
whose cache database is SQL Server: they would show on the first server whose cache database is
PostgreSQL.

And the chain runs only `SKILL.md` blocks. The 76 marked blocks of `references/` were each
verified once by hand; nothing re-runs them.

T40 makes "run `verify` on your server" a new user's first step: the chain reads what it needs
from the server or from a local file, its fixtures reach any server, it says which tail the
server lacks instead of failing on it, and every marked block either runs or is listed as not run
with the reason.

## Values: the manifest, the server, a local file

`[values]` in `verification/chain.toml` keeps only what belongs to the chain itself — the test
database, the prefix, the fixture route, the expected row counts. A value that belongs to an
installation is a **marker** the run fills in:

| Marker | Filled from |
|---|---|
| `@encrypt-throwaway` | a random password encrypted on the server (existing, spec 11.1) |
| `@server` | what the server says — the probe below |
| `@dialect` | the `[dialects.<write_dialect>]` table of the manifest |

Then **the local values file** overrides any of them. It lives beside the profiles file —
`<directory of the profiles file>/verify.toml`, so `DENODO_PROFILES` moves both — with one table
per profile:

```toml
[dev]
scheduler_data_source_id = "7"
fixture_route = "LOCAL 'LocalConnection'"
fixture_base = "/srv/denodo/verify-data"
```

`--values <file>` reads another file. Precedence: values file, then server, then the manifest.
A key the manifest does not declare (in `[values]` or a dialect table) is a usage error naming
the file and the known keys: a typo would otherwise change nothing and say nothing. The values
file holds no secret and needs none — a password never reaches the chain (the throwaway is made
on the server).

**A value nobody filled in** — the server did not say (a profile that is not an administrator
cannot read server settings), the file did not set it — is *unresolved*. A step whose texts name
an unresolved value (its body, its substitutions, its check, its files) is **skipped** with the
reason: which value, what the server answered, and the line to add to which table of which file.
So is a `[cleanup] writes` statement that names one. A run never sends a text with a placeholder
in it.

The report carries `values` as before, plus `values_from`: for each value, `manifest`, `server`,
`dialect`, `file` or `unresolved`, and `values_file` with the path read.

### What `@server` reads

| Value | Source | Notes |
|---|---|---|
| `embedding_model` | `GET_PARAMETER('com.denodo.vdb.vector.integration.embeddingModelConfiguration.modelName')` | administrators only |
| `write_datasource_database`, `write_datasource_name`, `write_catalog`, `write_schema` | the global row of `GET_CACHE_CONFIGURATION()`: `database_datasource_name`, `datasource_name`, `target_catalog`, `target_schema` | any user; a `NULL` catalog or schema stays unresolved |
| `write_dialect` | the same row's `adapter_database_name` (`sqlserver`, `postgresql`, …) | picks the dialect table |
| `scheduler_data_source_id` | `GET /public/api/dataSources` of the Scheduler: the one VDP data source whose `login` is the profile's user | none or several — unresolved, the reason lists the candidates |

`GET_PARAMETER` can read every server setting, secrets included. The probe asks for a fixed list
of non-secret properties only; nothing else is ever passed to it.

## The server's features

`env check` gains `features`, read with the same calls `verify` makes before its first step:

| Feature | Read from | Meaning |
|---|---|---|
| `enterprise_plus` | `VALIDATE_MPP_LICENSE()`: `max_processors` is `-1` unless the license is Enterprise Plus (documented) | tags, global security policies, LLM and embedding functions, embedded MPP |
| `mpp` | the same row's `status` and `details` | reported only; no step needs it |
| `cache` | the global row of `GET_CACHE_CONFIGURATION()`: `status`, data source, adapter and version, target catalog and schema | `on` is `status = 'ON'` |
| `llm` | `GET_PARAMETER` of `com.denodo.vdb.llm.integration.enabled`, `.apiType`, `.modelName` | on when enabled and a model is named |
| `embedding` | `GET_PARAMETER` of `…embeddingModelConfiguration.embeddingModelProvider`, `.modelName`, `.vectorizationFeatures.disabled` | on when a model is named and the features are not disabled |
| `summary_rewrite`, `data_movement` | `GET_PARAMETER` of `com.denodo.vdb.interpreter.execution.SelectAction.summaryRewrite`, `.dataMovement` | `NULL` (not set in the file) is unknown |
| `admin`, `impersonation` | the existing `vdp` checks | |

The bundle table of the documentation (*Denodo Platform - Subscription Bundles*) also puts VQL
stored procedures, summaries and the Data Marketplace in Enterprise and above. No read-only call
tells Enterprise from the bundles below it, so those stay unknown.

A step names what it needs: `requires = ["enterprise_plus", "impersonation"]`. Before running a
step, `verify` skips it when a feature it requires is known to be missing — `false`, never
`null` — with the reason: the feature, what the server answered, what needs it. Unknown runs:
the step's own failure is then the answer, and `features` in the report says it was unknown.
Gates and requirements combine: an `ai` step runs only with `--with-ai` **and** when `llm` is
not known to be off.

The vocabulary is closed (`enterprise_plus`, `llm`, `embedding`, `cache`, `summary_rewrite`,
`data_movement`, `impersonation`); an unknown name in `requires` is a manifest error.

## Fixture data: synthetic files under the TPC-DS names

The fixtures no longer read the demo image. `verification/data/` holds the five files they read —
`income_band.csv`, `household_demographics.csv`, `reason.csv`, `store_returns.csv`,
`web_returns.csv` — in the layout of the TPC-DS files (the header quoted, text columns padded to
their `CHAR` width), written by `verification/data/generate.py`: deterministic, standard library
only, run again only when the data has to change.

- `income_band` and `household_demographics` follow the TPC-DS definitions — twenty bands of
  10,000; 7,200 households as the cross product of band, buy potential, dependants and vehicles —
  so every count the checks and the `testing` templates state still holds (20 bands, 7,200
  households).
- `reason`, `store_returns` and `web_returns` are invented rows under the TPC-DS column names:
  35 reasons, a few thousand returns with `NULL`s in the reason and date keys, as the templates
  over them expect. No check reads their exact contents.

Where the server reads them from is two values: `fixture_route`, the route clause, and
`fixture_base`, the folder. By default the server reads them over HTTP from the public repository
(`ROUTE HTTP 'http.ApacheHttpClientConnection,120000' GET
'https://raw.githubusercontent.com/<repository>/main/verification/data/<file>'`) — measured on
9.5.1: a DF source over that route reads a file of the repository. A server that does not reach
GitHub gets the folder copied to it and `fixture_route = "LOCAL 'LocalConnection'"` with the
folder's path in its values file. A branch that changes the data points `fixture_base` at its own
raw URL.

Rejected: rows written through the cache data source — a default run would then write into a
source database, which only `--with-writes` may do; views over `Dual()` — the fixtures would stop
being base views over files, and the templates over them (`CACHE`, data movement, plans that read
a file) would test something else.

## Writes on any cache database

The write steps create their tables in the cache data source with a `CREATE_TABLE_TEMPLATE`, and
the identity key is product syntax. The template takes two values, `write_identity` and
`write_timestamp`, both `@dialect`; the manifest carries `[dialects.sqlserver]` and
`[dialects.postgresql]`, the two products the chain was run against. Another product: the reason
of the skip names the two values to set in the values file (and `write_dialect` when the write
data source is not the cache's).

## Every marked block runs, or says why not

A block of `skills/` carries a `verified:` mark (inside it, or in the paragraph right above or
below — the lint's rule) because it was run once on a live server. From T40 the chain re-runs it,
or lists it:

```toml
[not_run]
"skills/datasources/SKILL.md#Relational database over JDBC[1]" = "introspection answers only from a database that is up, with a real credential"
```

A unit test holds both directions: every marked block is the address of a step (or of a step's
`files`) or a key of `[not_run]`; every key of `[not_run]` resolves to a marked block that no step
runs. Adding a marked block to a skill without a step or a line there fails CI, the same ratchet
as the lint's lists.

What goes to `[not_run]`: grammar (`[ … ]`, `<…>` alternatives — not a statement), a fragment
that is not a statement and cannot be made one by substitution, a block that needs what the chain
cannot have (a source that answers, a JAR, a VCS), a call that would change something shared
beyond the run's prefix. Everything else becomes a step. A fragment of a statement becomes one
when a substitution completes it (`AS SELECT …` gets its `CREATE OR REPLACE VIEW <name>`, `<first
key of the live period>` a key of the fixture data) — the block's text still runs, and what the
step adds is in the manifest beside it.

The prose marks (a fact in a sentence or a table cell, with no block) stay outside, as spec 11.1
already says: the flag never rewrites them, and a claim in prose is not a statement the chain can
send.

The report's summary gains `not_run`, the number of keys of `[not_run]`.

## Two configurations

Done when the chain passes unchanged on both:

1. **The demo image as it is** — SQL Server cache database, the fixtures over HTTP from the
   repository, every tail (`--with-marketplace --with-ai --with-writes --with-scheduler
   --testing-tool`).
2. **The same server with its cache database on PostgreSQL** — a schema of the demo PostgreSQL the
   cache account owns, a JDBC data source of its own database pointed at it, the server's
   `com.denodo.vdb.cache.jdbc.serverCacheDataSource` set to that source and Virtual DataPort
   restarted (the documentation: changing the cache DBMS needs a restart); the fixtures from a
   local folder copied into the server (the no-internet route); every tail. Afterwards the setting
   goes back, the server restarts, the schema and the database are dropped. The owner said yes to
   this on 2026-10-06; the AI tails of the task are capped at 200 paid requests.

Each run's values come from the profile's table in the values file and from the server; nothing
in the repository changes between them. Whatever the PostgreSQL run finds wrong in a template is
fixed in the skill, not worked around in the manifest.

## Not in T40

- Telling Enterprise from Standard or Professional: no read-only call does; VQL procedures and
  summaries stay unknown below Enterprise Plus.
- A verification run on a server without an administrator account: the probe reports the
  features it cannot read as unknown; the steps that need them run and fail with the server's
  answer.
- Prose marks; the marketplace's own Enterprise check (the tail already needs the marketplace to
  answer).
