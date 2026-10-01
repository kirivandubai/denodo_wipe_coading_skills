# Denodo 9.5 skills roadmap: what to build after v1

**Date:** 2026-09-29
**Status:** reviewed by the owner item by item (section 11); section 10 is the build order that follows from it
**Basis:** a full read of the Denodo 9.5 documentation; complements the
[design spec](2026-09-04-denodo-skills-design.md) and the [v1 scope](2026-09-04-denodo-v1-scope.md)

---

## 1. How this list was produced

**Corpus.** All sixteen guides of the Denodo 9.5 documentation (1260 pages: VQL Guide, Virtual
DataPort Administration and Developer guides, Data Marketplace, Diagnostic & Monitoring Tool,
Scheduler, Solution Manager, Platform installation/upgrade/new features/administration,
Lakehouse Accelerator, Agora) and the 40 Denodo Connects manuals (dbt adapter, MCP Server,
AI SDK, Testing Tool, VQL Generation stored procedures, custom wrappers, governance bridges and
others). The corpus was read in nine partitions; each partition produced a report of candidate
skills with page references.

**Each topic was rated on four axes:**

- **Frequency** in vibe coding: daily / weekly / episodic / rare / one-off setup.
- **Necessity:** blocker (a typical scenario cannot be finished without it) / important /
  nice to have / out of scope (infrastructure, operations, UI only).
- **Delta:** how often and how confidently a model gets it wrong when it writes from memory or by
  analogy with PostgreSQL or Oracle. A skill is worth writing where this delta is large.
- **Channel:** VQL over the existing transport, REST (existing or a new transport profile), or
  no channel (Design Studio UI, scripts on the server host, server config files).

**Priorities:**

| Priority | Meaning |
|---|---|
| P0 | Without it, vibe coding on the platform is broken or unsafe |
| P1 | Frequent developer action with a large delta |
| P2 | Episodic or narrow |
| P3 | Rare, administrative, or almost no delta |

**Caveat.** Everything below comes from the documentation. Nothing was run against a live
server for this document. The reading found about twenty places where the documentation
contradicts itself or known server behaviour (examples in section 8), so every grammar quoted
here is a hypothesis until a template carries a `verified:` mark.

---

## 2. Gaps in the core — no P0 left after the review

These are not new skills but gaps in `execute` and `vql`. The owner review took none of them
as P0: 2.1 became a narrowed P1, the rest were dropped or attached to later skills.

### 2.1 The safety classifier misses state-changing statements

**Owner review: P1, narrowed (see section 11).** The refusal acts only on a profile with
`production = true`; on a development profile `destructive` is informational. A text
classifier can never be complete — a wrapper with side effects is invisible in the statement —
and most of the list below is emitted only after a skill teaches it. So:

- **Now:** the server-wide `SET '<property>' = …` (quoted form only; the unquoted session form
  stays harmless) and `INSERT` / `UPDATE` / `MERGE` — what an agent writes from memory without
  any skill.
- **Rule for everything else:** a skill that teaches a state-changing statement or procedure
  extends the classifier in the same PR.
- **Criterion for "destructive"** (closes the open question in `docs/TASKS.md`): the statement
  changes state outside the agent's own project — server settings, data in sources, objects
  of other databases, global objects. `CREATE` in the agent's own database is not destructive.

The original finding follows.

`scripts/denodo_cli/safety.py` classifies VQL by its leading keyword (`DROP`, `ALTER`,
`DELETE`, `TRUNCATE`) and by nine procedure names (T20). The documentation describes many more
operations that change state while looking harmless:

- **Server-wide configuration:** `SET '<property>' = '<value>'` (quoted property name) changes a
  setting of the whole server, some take effect immediately and propagate to the cluster, some
  need a restart; this includes JVM options (`SET 'java.env.DENODO_OPTS_START' = …`). Also
  `WEBCONTAINER SET | STOP | START`. The unquoted form (`SET QUERYTIMEOUT TO …`) is
  session-scoped and harmless. Reading settings is safe through `GET_PARAMETER()`.
- **SELECT with side effects:**
  `SELECT … CONTEXT('cache_preload' = 'true', 'cache_invalidate' = 'all_rows')` rewrites or
  wipes the cache of a view; `CONTEXT('DATAMOVEMENTPLAN' = …)` creates tables in another data
  source; `SELECT … INTO`.
- **Writes to sources:** `INSERT`, `UPDATE` (write through a view into the source), `REFRESH`
  of a remote table (truncates it), `CREATE OR REPLACE REMOTE TABLE` (drops and recreates the
  table in the source), `UNDEPLOY WEBSERVICE`.
- **About twenty writing procedures outside the deny list**, among them `CHECK_METADATA` with
  `remove_broken_references` (drops views in cascade), `REFRESH_BASE_VIEW` (changes the schema
  of a base view even with default parameters), `MIGRATE_DATE_TYPES` (with a `NULL` database it
  rewrites types across the whole server), `COMPACT_CACHE`, `GET_STATS_FOR_FIELDS` with
  `input_save = true`, `CREATE_TAGS_FROM_VIEW` with `DROP_UNASSIGNED_CASCADE` (also drops global
  security policies that use the tags), `LOGCONTROLLER`, the Lakehouse Accelerator maintenance
  procedures. The open question in `docs/TASKS.md` about the criterion for "destructive" is the
  prerequisite here.
- **Views over custom wrappers with side effects** (Denodo Connects): a `SELECT` over the SSH
  wrapper runs a command on a remote machine; the Kafka wrapper in incremental mode moves the
  consumer offset on every query; the Distributed File System wrapper with "Delete after
  reading" deletes files; the FileSystem wrapper in read-write mode writes files on the server
  disk. The danger is determined by the wrapper class (`DESC VQL` → `CLASSNAME`), not by the
  statement keyword.
- **Global objects:** users, roles, global security policies, VDP tags, JARs, i18n maps and the
  web container belong to the server, not to a database. Creating them puts the server into
  single-user mode for a moment.

### 2.2 `DESC VQL` without options emits destructive VQL

**Owner review: dropped (see section 11).** The skills already say "read it, do not apply it" (`execute/SKILL.md`, `views/references/derived.md`), and agents use `DESC VQL` as a syntax reference, which relies on the default `includeDependencies`. Safe export options matter only when the output is applied elsewhere — that belongs to `deploy` (item 10), if it stays. The original finding follows.

`vql desc --vql` sends `DESC VQL <KIND> <name>` without options
(`scripts/denodo_cli/commands/vql.py`). The documented defaults are
`'dropElements' = 'yes'` (a `DROP … CASCADE` before every `CREATE`),
`'replaceExistingElements' = 'no'` and `'includeDependencies' = 'yes'`. Applying such output
drops the object and everything that depends on it, including data sources. Since 9.0 the output
may also include objects of other databases. The safe form is
`('dropElements' = 'no', 'replaceExistingElements' = 'yes', 'includeDependencies' = 'no')`;
what each object type actually prints must be checked live.
Source: `vdp/vql/describing_catalog_elements/describing_catalog_elements`,
`vdp/vql/describing_catalog_elements/exporting_metadata/exporting_metadata`.

### 2.3 Transactions are ignored on the transport

**Owner review: dropped (see section 11).** The transport runs in autocommit, and `execute/SKILL.md` already states that statements before `failed_at` stay applied and nothing is rolled back. The original finding follows.

Port 9996 is the ODBC interface of Virtual DataPort. By default it ignores `BEGIN`, `COMMIT`,
`ROLLBACK`, `SAVEPOINT` and `RELEASE`, so a batch of DDL applied through psycopg2 is not atomic
and a rollback undoes nothing. Enabling transactions is a server-wide `SET` that affects every
ODBC client. This belongs in the core skill as a stated fact.
Source: `vdp/developer/access_through_odbc/integration_with_third-party_applications/disabling_transactions`.

### 2.4 Secrets appear in more statements than data sources

**Owner review: no separate item (see section 11).** Every statement listed below arrives with a skill that does not exist yet (HTTP sources, `security`, `publish`). The first skill that teaches a secret without an `ENCRYPTED` form brings the `@{secret:<name>}` substitution in the same scope — the same rule as for the classifier in 2.1. Substitution protects git, not the transcript: the tool echoes executed statements and `DESC VQL` prints headers back, so output redaction is part of that scope. The original finding follows.

Passwords and keys also appear in `CREATE/ALTER USER`, `CONNECT USER … PASSWORD`,
`DEPLOY WEBSERVICE … PASSWORD`, `AUTHENTICATION BASIC`, `CREATE DATABASE … VCS … PASSWORD`,
listeners, `REGISTER_EMBEDDED_MPP`, the VQL Generation procedures and custom wrapper
`PARAMETERS`. HTTP `HEADERS` values (API keys) have no `ENCRYPTED` form at all, so today they
would land in git in clear text. A general secret placeholder resolved at apply time (the
`@{secret:<name>}` idea already listed in `docs/TASKS.md`) becomes necessary rather than
optional. Credentials vault clauses (`VAULT_SECRET`, `FROM_VAULT`, `CREDENTIALS_VAULT(...)`) are
the platform-native alternative where a vault is configured.

### 2.5 Smaller core additions

**Owner review (see section 11):** `HELP` — kept if a live check shows it answers over the transport, then one line in `vql` next to the `DESC VQL` rule (checked in T23: it answers with no rows, so dropped); the admin flag in `env check` — decided together with `security` (item 13); identifier conventions — dropped, rows go to `execute/references/errors.md` when an agent actually trips on them; feature renames — a convention in `CONTRIBUTING.md` (done), not a task. The original list follows.

- `HELP <command>` returns the server's own syntax for a statement — a better source than memory
  when a template is missing.
- `env check` should report whether the profile user is an administrator: many procedures are
  admin-only, and security features do not apply to administrators (see `security`).
- Identifier conventions: lowercase `[a-z0-9_]`, at most 100 characters; a quoted name with an
  uppercase letter becomes case-sensitive forever; common column names are reserved words
  (`user`, `read`, `base`, `row`, `hash`, `table`, `view`, `offset`, `limit`, `context`,
  `trace`) and must be quoted.
- Feature renames in 9.x that must appear in skill descriptions under both names: Data Catalog →
  Data Marketplace, Cache → Materialization, Embedded MPP → Lakehouse Accelerator, VDPCache job →
  Simple Cache Management, Reference Lineage → 360 Graph.

---

## 3. Ranked list

| # | Skill | Kind | Priority | Frequency | Necessity | Channel |
|---|---|---|---|---|---|---|
| 1 | `dialect` → `vql/references/dialect.md` | reference, not a skill | P1 | daily | blocker (silent wrong data) | VQL |
| 2 | `views` (unions, partitioned unions, `FLATTEN`/`NEST`) | extension | P1 | daily | important | VQL |
| 3 | `lineage` → additions to `views` | extension, not a skill | P2 | daily–weekly | important | VQL, read only |
| 4 | `datasources`: route non-v1 sources to Design Studio | change of an existing skill | P1 | weekly | important | none — UI for the human |
| 5 | `performance` → delegation check in `views` | extension, not a skill | P1 | weekly | important | VQL |
| 6 | `cache` (FULL only for now) | new | P1 | weekly | important | VQL |
| 7 | `semantics` (VDP half: audit and fill) | new | P1 | weekly | important (AI consumers) | VQL |
| 8 | `marketplace` (safe sync) | extension | P1 | weekly | important | Marketplace REST |
| 9 | `testing` (`.denodotest` + Testing Tool) | new | P2 | weekly | important | local Testing Tool over JDBC |
| 10 | ~~`deploy`~~ — dropped | — | — | — | — | — |
| 11 | ~~`publish`~~ — dropped | — | — | — | — | — |
| 12 | `scheduler` — later, separate skill | new | later | weekly | — | new Scheduler REST profile |
| 13 | `security` (basic actions) | new | P2, this round | episodic | important for production | VQL |
| 14 | `metrics` | new | P2 | episodic, growing | nice → important | VQL |
| 15 | `materialize` | new | P2 | episodic | important | VQL |
| 16 | ~~`connectors`~~ — dropped, Design Studio (item 4) | — | — | — | — | — |
| 17 | ~~`datasources` (files)~~ — dropped, Design Studio (item 4) | — | — | — | — | — |
| 18 | ~~`lakehouse`~~ — dropped | — | — | — | — | — |
| 19 | ~~`dbt`~~ — dropped | — | — | — | — | — |
| 20 | ~~`deploy` (Solution Manager)~~ — dropped with item 10 | — | — | — | — | — |
| 21 | `ai` | new | P2, this round | episodic | nice | VQL |
| 22 | `dml` | new | P2, this round | episodic | nice | VQL |
| 23 | ~~`marketplace` (governance)~~ — dropped | — | — | — | — | — |
| 24 | ~~`listeners`~~ — dropped | — | — | — | — | — |
| 25 | ~~`sap`~~ — dropped, Design Studio (item 4) | — | — | — | — | — |
| 26 | ~~`extensions`~~ — dropped | — | — | — | — | — |
| 27 | ~~`clients`~~ — dropped | — | — | — | — | — |
| 28 | ~~`vcs`~~ — dropped with item 10 | — | — | — | — | — |

---

## 4. P1 skills

### 4.1 `dialect` (new) — VQL expressions versus standard SQL

**Owner review: P1, a reference, not a skill (see section 11).** A skill triggers on the user's phrase, and nobody says "mind the VQL dialect": the user asks for a mart, `views` fires, and a separate `dialect` would load only through a cross-reference — which makes it a reference file anyway, while its description would compete with `views`. Shape: `vql/references/dialect.md` with every delta verified by `SELECT … FROM Dual()`, plus a short table of the 8–10 most dangerous silent deltas in the body of `vql` or `views` (dates, substrings, NULL in aggregates, `CAST`, the `SUM` overflow); the two rows now in `views/SKILL.md` move there. The original proposal follows; its "Shape" paragraph is superseded.

**Scope.** Functions and operators where VQL differs from what a model guesses from PostgreSQL
or Oracle: text, dates and intervals, NULL handling, aggregates and window functions, compound
types (register, array), JSON, `CONTEXT`, and what changed between Denodo 5.x and 9.5.

**Why it reverses the T13 conclusion.** T13 closed without a `query` skill because the
acceptance scenarios never hit a server error on expressions. The documentation shows about
thirty deltas, of which about twelve return **wrong data without an error**, so the absence of
errors in T13 is not evidence. `SELECT` is also written outside `views`: verification queries in
every skill, VQL procedure bodies, ad-hoc questions without creating a view. Denodo itself ships
an agent skill `denodo-vql-generation` with the MCP Server, stating that LLMs write incorrect VQL
without it.

**Silent deltas (examples):**

- `SUBSTRING(x, start, end)` is 0-based and takes an end index, not a length;
  `SUBSTR(x, s, l)` / `SUBSTRING(x FROM s FOR l)` follow SQL-92.
- `INSTR` is 0-based and returns -1 when not found; `POSITION` is 1-based and returns 0.
- The default escape character of `LIKE` is `$`.
- `datetime - datetime` returns whole days as a long, not an interval.
- `TO_LOCALDATE`, `TO_TIMESTAMP`, `FORMATDATE` take the pattern first, in Java
  `SimpleDateFormat` syntax.
- The first day of the week depends on the i18n of the view and, when delegated, on the source.
- Text comparison is case-sensitive, unless delegated to a case-insensitive source.
- Scalar `MAX`/`MIN` return NULL if any argument is NULL; `SUM(a, b)` is addition, not an
  aggregate.
- `CAST(x AS VARCHAR(n))` truncates silently.
- `GROUP_CONCAT` drops the whole row when any field is NULL; `STRING_AGG(field, sep)` exists.
- Window functions over sources that cannot run them (CSV, JSON, REST) abort the query unless
  the Lakehouse Accelerator or the cache can take over.

**Version deltas the model reproduces from old examples:** `UNION` removes duplicates since 8.0
(older examples behave as `UNION ALL`); the `date` type and `TO_DATE` are deprecated in favour of
`localdate`/`timestamp`/`timestamptz`; `contains`/`containsand`/`containsor`/`iscontained`
operators are removed; identifiers use double quotes only and a single quote is escaped by
doubling it; `CATALOG_*` procedures are deprecated in favour of `GET_*`; `LIMIT`/`OFFSET` are
allowed in `CREATE VIEW` in 9.5.

**Shape.** A table of the 10–12 silent deltas in the core `vql` skill (about 25 lines), plus a
narrow `dialect` skill with references: dates, text, aggregates and windows, compound types and
JSON, legacy VQL. The description will compete with `views` and must go through the eval suite.

**Verification.** Almost every delta is checkable with `SELECT … FROM Dual()` on an empty
database — no external source needed. Only the delegation-dependent ones need a live JDBC source.

**Docs.** `vdp/vql/functions/{text_functions,datetime_functions,numeric_functions,aggregation_functions,window_functions,json_functions,conversion_functions,other_functions}`,
`vdp/vql/language_for_defining_and_processing_data_vql/data_types/data_types_for_dates_timestamps_and_intervals`,
`vdp/vql/language_for_defining_and_processing_data_vql/comparison_operators/comparison_operators`,
`vdp/vql/language_for_defining_and_processing_data_vql/syntax_conventions/syntax_conventions`,
`platform/upgrade/backward_compatibility/*`, `platform/upgrade/features_deprecated`.

### 4.2 `views` (extension)

**Done in T25 (2026-09-30):** union and array templates in the body of `views`, the details in `views/references/unions.md` and `arrays.md`, `CONTEXT ('formatted' = 'yes')` on every `CREATE VIEW`; the JSON base view template of `datasources` gained the `CONSTRAINTS … NOS ZERO ()` block without which every `WHERE` on it was ignored. `docs/TASKS.md` has what was measured.

**Owner review: P1, kept whole except `INTERSECT`/`MINUS` (see section 11).** Scope to add: both union semantics, partitioned unions with branch pruning, `FLATTEN` and `NEST` (a real gap inside v1: `datasources` already builds a JSON base view with an `ARRAY OF` field and nothing shows how to turn it into rows), `CONTEXT('formatted' = 'yes')`. Already in `views` and not to be redone: primary key and description on every view, `USING PARAMETERS`, and the dependants check (`USED_BY()` before, `GET_VIEWS(… invalid only)` after — "Silent failure 1"). The original proposal follows.

**Scope added:** the two union semantics (SQL `UNION` versus Denodo's extended union that
matches by name and pads with NULL), partitioned unions and branch pruning, flatten and `NEST`,
`INTERSECT`/`MINUS` (by name; there is no `EXCEPT`), view parameters, primary keys and
descriptions on every view, `CONTEXT('formatted' = 'yes')` so that the stored definition matches
the project file.

**Key pitfall.** When a view changes, Design Studio's "Views affected by modification" dialog
propagates new fields to dependent views and web service operations. `CREATE OR REPLACE` over VQL
does not — the agent has to find and update dependents itself (see `lineage`).

**Docs.** `vdp/vql/queries_select_statement/union_clause/union_clause`,
`vdp/vql/queries_select_statement/from_clause/flatten_view_flattening_data_structures`,
`vdp/administration/creating_derived_views/*`,
`vdp/administration/optimizing_queries/automatic_simplification_of_queries/removing_redundant_branches_of_queries_partitioned_unions`.

### 4.3 `lineage` (new) — impact analysis before a change

**Done in T26 (2026-09-30):** `views` has "Before a column changes" and
`references/dependencies.md`. Checked live, two of the pitfalls below changed: the dependency
procedures take **exact, case-sensitive names** and answer a pattern with an error, not with a
wider result — the `LIKE` matching is real only in the catalog procedures (`GET_ELEMENTS`,
`GET_VIEWS`, `GET_VIEW_COLUMNS`); and the bigger trap is one nobody listed —
`COLUMN_DEPENDENCIES` traces output columns only, so a column used in a join or a filter looks
unused. The privilege narrowing stays documentation-only until a second, non-administrator
profile exists (T31).

**Owner review: P2, no skill — additions to `views` (see section 11).** `views` already runs `USED_BY()` before a change and `GET_VIEWS(… invalid only)` after, and `procedures` documents the whole dependency family; a separate skill would compete with both for the same phrases. To add to `views`: column level (`COLUMN_DEPENDENCIES`) next to `USED_BY`, the privilege and `LIKE` pitfalls after a live check, and the phrases "what uses this view / can I drop this column / where does this field come from" in its description (eval suite). Web service and cache dependants are added by the skill that introduces them. The original proposal follows.

**Scope.** Read-only: `USED_BY`, `VIEW_DEPENDENCIES`, `COLUMN_DEPENDENCIES`,
`GET_PUBLIC_VIEW_DEPENDENCIES`, which web services publish a view, which cache loads depend on
it. Triggered by "what uses this view", "can I drop this column", and implicitly before any
`ALTER` or `DROP`.

**Pitfalls.** Procedures do not fail without privileges — they silently narrow the result, so an
empty answer does not mean "safe to drop". `input_name` parameters are matched with `LIKE`, so
`_` is a wildcard. Filtering on an output column instead of the `input_…` parameter scans the
whole server or returns nothing. The `input_` prefix is not universal.

**Why P1.** Cheap (read only, no new transport), frequent, and it is the safety net for the
dependency propagation gap in `views`.

**Docs.** `vdp/vql/stored_procedures/predefined_stored_procedures/{used_by,view_dependencies,column_dependencies,get_public_view_dependencies,get_cache_load_view_dependencies}`.

### 4.4 `datasources` (extension) — HTTP sources, JDBC depth, schema drift

**Owner review: none of the extensions; the skill routes to Design Studio instead (see section 11).** The rule for `datasources`:

1. The verified v1 templates — delimited file, JSON file, JDBC table — stay: the agent creates those over VQL.
2. Everything beyond them — REST APIs, a base view from a SQL query or a database procedure, schema drift, Excel, XML, Salesforce, custom wrappers and every other source type — the skill recommends creating in Design Studio; the agent then reads what was created (`DESC VQL`) and continues from there.
3. Base views: the agent creates them where it works; when creation does not succeed straight away, it stops iterating and sends the human to Design Studio.

What became of the `unverified` HTTP, `SQLSENTENCE` and credential sections in the references was decided in T23 with the owner: the grammar of everything beyond the three templates was removed from `references/json.md`, `references/df.md` and `references/jdbc.md` — the verified `SQLSENTENCE` included, since a base view over a query goes to Design Studio too — and each reference now names the Design Studio rule instead. Kept grammar would read as "an unverified template is still worth using" (`vql`), which is the opposite of the routing. Objects created in Design Studio are not copied into the project's files. The same decision drops items 16 (`connectors`), 17 (`datasources` files) and 25 (`sap`). The original proposal follows.

**Scope added:**

- **REST APIs as a source:** the wrapper `ROUTE` is concatenated with the data source `ROUTE`;
  `@{var}`, `EXTERN` and URI parameters become mandatory search-method fields; four pagination
  styles; OAuth2; OpenAPI import. HTTP `HEADERS` cannot be encrypted (see 2.4).
- **JDBC beyond "table → base view":** base views from a SQL query (`SQLSENTENCE` with
  `@WHEREEXPRESSION`, `^ExecuteIfIsNotNull`), base views over database procedures, pass-through,
  and the work the Design Studio wizard does implicitly (associations from foreign keys, schema
  prefixes).
- **Search methods and `ALTER TABLE`:** mandatory/optional/unsupported field tuples; Design
  Studio cannot edit search methods at all.
- **Schema drift:** `GET_SOURCE_CHANGES`, `REFRESH_BASE_VIEW` (which itself changes the view —
  see 2.1).
- **Adapter change** only through `CREATE OR REPLACE` with new `CLASSPATH`/`DATABASENAME`/
  `DATABASEVERSION` — `DROP` removes the base views. Several adapters are deprecated in 9.5
  (PostgreSQL 8–13, Oracle before 18c, the old Simba Databricks driver, Athena 2.x) and a model
  tends to pick exactly those.
- **Credentials vault** clauses instead of an encrypted password in git.

**Pitfalls.** Credential keywords differ by source type: JDBC `USERNAME … USERPASSWORD …`,
WS/HTTP `USER … PASSWORD …`, Salesforce `USER_IDENTIFIER`.

**Verification.** The server's own RESTful web service is a live, paginated JSON API with Basic
authentication and can serve as a fixture for HTTP sources without internet access.

**Docs.** `vdp/administration/creating_data_sources_and_base_views/path_types_in_virtual_dataport/http_path`,
`vdp/vql/generating_wrappers_and_data_sources/creating_data_sources/jdbc_data_sources`,
`vdp/vql/creating_a_base_view/query_capabilities_search_methods_and_wrappers/*`,
`vdp/vql/stored_procedures/predefined_stored_procedures/{get_source_changes,refresh_base_view}`,
`platform/administration/credentials_vault/credentials_vault`.

### 4.5 `performance` (new) — why is this query slow

**Done in T26 (2026-09-30):** a Verify row and Silent failure 3 in `views`, and
`references/delegation.md`. Over the transport the plan comes from
`GET_QUERY_EXECUTION_PLAN()` (`noDelegationCauses` names the function); `DESC QUERYPLAN` is
empty, and `GET_DELEGATED_SQLSENTENCE` answers — but returns the delegated part without an
error even when the aggregate stays in Denodo, so it is not the check. Views over two data
sources print no cause at all.

**Owner review: P1, narrowed to a delegation check in `views` (see section 11).** The vibe-coding risk is a mart over a JDBC source that silently stops being delegated because of one function the source cannot run: correct rows, minutes instead of seconds in production. Today neither `views` nor `datasources` checks delegation. To add: one row in the `views` verification table — for a view over JDBC read `GET_DELEGATED_SQLSENTENCE` or `DESC QUERYPLAN`, confirm the join and the aggregate reached the source whole, and name the blocking function to the human when they did not; first confirm live that both answer over the transport. Tuning — statistics, the cost-based optimizer, join hints, data movement — is dropped: expert work with an execution trace in Design Studio, partly server-wide `SET`, and a wrong flag returns wrong data. The original proposal follows.

**Scope.** `DESC QUERYPLAN`, `GET_DELEGATED_SQLSENTENCE`, reasons for non-delegation, join
methods and hints, statistics and the cost-based optimizer, partitioned-union pruning, data
movement, the Lakehouse Accelerator as an execution engine for what the source cannot run.

**Pitfalls.** The cost-based optimizer is off by default and silently does nothing when any base
view of the query lacks statistics. The name of the statistics procedure is inconsistent across
pages (`GET_STATS_FOR_FIELDS` versus `GENERATE_SMART_STATS_FOR_FIELDS`; `GENERATE_STATS_FOR_FIELDS`
is deprecated). A wrong association with a referential constraint breaks GROUP BY push-down.
Setting "supports binary ORDER BY collation" to yes on a source that defaults to no returns wrong
results. The execution trace (`TRACE`) may be available only in Design Studio — to check over
the transport.

**Docs.** `vdp/administration/optimizing_queries/*`,
`vdp/administration/creating_derived_views/querying_views/execution_trace_of_a_statement`,
`vdp/administration/appendix/execution_trace_information/execution_trace_information`,
`vdp/vql/defining_the_statistics_of_a_view/defining_the_statistics_of_a_view`.

### 4.6 `cache` (new)

**Owner review: P1, a separate skill from the start, FULL cache only (see section 11).** The skill exists now so that it can grow later without moving text between skills. First scope: turn a FULL cache on and off for a view, fill it with what the human says (the whole view or a filter they chose — the `WHERE` of a preload is a decision, not a default), and clear the cache tables. PARTIAL, time to live, incremental loads, indexes and scheduled refresh are out for now. The silent pitfalls below that apply to FULL are the core of the skill; `cache_invalidate` goes into the classifier in the same PR (rule from 2.1). Working assumption for verification: the cache of the agent's own views counts as its own objects (section 9, decision 2). The original proposal follows.

**Scope.** `ALTER VIEW | TABLE … CACHE PARTIAL [EXACT] [PRELOAD] | FULL | OFF`, time to live,
preload and invalidation through `CONTEXT`, incremental loads (`@LAST_REFRESH_DATE`), cache
indexes, `GET_CACHE_*` and `CACHE_CONTENT` for inspection.

**Built in T27** (`skills/cache/`). Checked on 9.5.1 against the list below: the first,
second, third and last pitfalls hold; the fourth holds only for an explicit
`'cache_wait_for_load' = 'false'` — left out, the load waits and reports the failure; PARTIAL
and the UI labels are Design Studio's. New ones, in the skill: `NO_STATUS` breaks the views
above on every full reload, `CACHE OFF` keeps the rows and serves them again on the next
`CACHE FULL`, re-applying the view without its `ALTER` switches the cache off.

**Silent pitfalls:**

- A FULL cache without a preload returns 0 rows.
- A preload with a `WHERE` clause truncates the view permanently.
- A preload without `cache_invalidate` duplicates rows.
- Without `'cache_wait_for_load' = 'true'` a failed load is not reported to the client
  (the parameter is marked deprecated yet used in the official recipe — to check).
- PARTIAL on a cache database such as Athena, BigQuery or Presto is a silent no-op.
- UI labels ("Query results", "Explicit", "Match exact") differ from VQL keywords.
- Without `'cache_return_query_results' = 'false'` a preload streams every row to the client.

**Constraint.** The cache engine of the server is enabled in the UI; the skill starts from a
configured cache. Cache writes go to an external database — see section 9, decision 2.

**Docs.** `vdp/administration/cache_module/*`,
`vdp/vql/advanced_characteristics/using_the_cache/*`.

### 4.7 `semantics` (new) — make views understandable to people and AI

**Owner review: P1, a separate skill, VDP half only (see section 11).** New views already get a description and a primary key from `views`; the gap is an audit of what already exists. Scope: walk a database, find views without a description, field descriptions, primary key, associations or the MCP visibility tag, and fill them in. Descriptions are derived from the data (a profile of the values), never invented from a column name, and the human approves them before they are written. Triggers: "describe these views", "prepare for AI / MCP", "why does the agent not see this view". The marketplace half (logical names, property groups, sync pitfalls) comes later as a `marketplace` extension. The original proposal follows.

**Built in T28** (`skills/semantics/`). Checked on 9.5.1: descriptions of views, fields,
associations and tags, primary keys and tag assignments are all written with `ALTER`, which
keeps the cache, the dependants and the privileges; re-applying a view's own `CREATE OR
REPLACE` without them removes every one, the MCP tag included; a field description is
inherited live through plain column references and stops at any expression; a declared key
marks its columns `NOT NULL`, and `ADD PRIMARY KEY` replaces an existing key without an error.
The MCP Server, Assisted Query and the AI SDK were not queried — what they read is taken from
their manuals. The marketplace pitfalls below stay with the later `marketplace` extension.

**Scope.** View and field descriptions, primary keys, associations, the VDP tag that controls
MCP Server visibility, Data Marketplace logical names and property groups with the
"Include in AI context" flag, and synchronisation with the marketplace so the metadata reaches it.

**Why P1.** The consumers that read this metadata are the 9.5 direction of the platform:
Assisted Query in the Data Marketplace, the MCP Server, the AI SDK. They build prompts from view
and field descriptions, primary keys, NOT NULL flags, tags and first-level associations. Joins
are built only from associations. With the MCP Server's sample configuration
(`mcp.visibility.tags=mcp`) a view without the tag is invisible to agents. Primary keys and
associations are also required by OData navigation, and descriptions surface in JDBC `REMARKS`.

**Pitfalls.** A description edited in the marketplace stays in the marketplace and is not written
back to VDP. The `LOCAL` sync mode ignores new descriptions from VDP. Logical names exist only in
the marketplace. Property groups are assigned as a group, not per property; turning off HTML or
deleting a language in the marketplace personalisation destroys existing values.

**Alternative.** Split into a convention in `views` (VDP half) and a `marketplace` extension
(marketplace half). A separate skill is proposed because the trigger phrases ("describe these
views", "prepare for AI", "why does the assistant not see this view") belong to neither.

**Docs.** `vdp/vql/language_for_defining_and_processing_data_vql/object_descriptions/object_descriptions`,
`vdp/data_catalog/views/assisted_query`,
`vdp/data_catalog/administration/property_groups_management/property_groups_management`,
`vdp/data_catalog/administration/synchronize/synchronize`, Denodo Connects "Denodo MCP Server"
and "Denodo AI SDK" manuals.

### 4.8 `marketplace` (extension) — safe synchronisation

**Owner review: P1, as proposed (see section 11).** The agent carries the metadata of a renamed or recreated view over to its new element through REST. Starts with a spike on the server's OpenAPI: find how elements are matched during synchronisation. If the API has no such call, fall back to a warning in `views` before the rename and a pointer to the synchronisation dialog of the marketplace UI — and bring that back to the owner. Today `marketplace` already stops on a non-empty `localElements`, so the loss is not silent, but the human is not told that the "removed" element is the same view under its old name. The original proposal follows.

**Scope.** Renaming or recreating a view that already exists in the marketplace. Synchronisation
sees a rename as a deletion plus a new element; tags, categories, descriptions, custom properties
and endorsements of the old element are lost unless the elements are matched (in the UI this is a
drag-and-drop dialog; whether the REST API exposes it must be read from the server's OpenAPI).
Deleting an external tool server irreversibly removes its elements with their metadata.

**Cross-reference.** `views` and `vql` should route "rename / recreate a view that is in the
marketplace" to `marketplace` first.

**Docs.** `vdp/data_catalog/administration/synchronize/synchronize`.

### 4.9 `testing` (new) — regression tests for data products

**Owner review: P2, Denodo's format run by the real Testing Tool (see section 11).** The skill writes `.denodotest` files next to the project's `.vql` and runs them with the Denodo Testing Tool itself; no runner of our own in `scripts/`. The checks `views` already makes at creation time are the natural first tests. `configuration.properties` holds credentials, so it is generated outside the repository — how exactly (from the environment profile, without the password entering a command line) is part of the task. The original proposal follows; its lightweight-runner option is not taken.

**Scope.** Tests in the Denodo Testing Tool format (`.denodotest`: `%EXECUTION[query]`,
`%RESULTS[data|csv|query|exception]`, `%CONTEXT`, `%SETUP`/`%TEARDOWN`), kept in the project next
to the `.vql` files. Two execution options: the Testing Tool itself (a local Java CLI over JDBC),
or a lightweight runner `scripts/denodo test` that understands a subset of the format and uses the
existing transport — no credentials in a properties file, no new transport.

**Pitfalls.** `ordered` defaults to `false` for `[query]`/`[script]` but `true` for
`[csv]`/`[data]`, so inline expectations without `ORDER BY` fail on row order. Six kinds of
escaping. The VDP driver needs `connectionTestQuery`. Credentials sit in
`configuration.properties` (plain or Jasypt-encrypted) — they must be generated outside the
repository. The manual's teardown example uses `REMOVE FROM`, which is not VQL.

**Why P1.** Vibe coding rewrites views in bulk; this is where a safety net pays off, and the
model does not know the format at all.

**Docs.** Denodo Connects "Denodo Testing Tool" manual.

### 4.10 `deploy` (new) — move a data product between environments

**Owner review: dropped entirely (see section 11).** Not taken in any form — neither promotion between environments nor exporting objects made in Design Studio into the project. The same decision drops item 20 (Solution Manager branch) and item 28 (`vcs`), and with them the safe export options left over from 2.2. The original proposal follows.

**Scope.** Export with safe options (section 2.2) and `'includeProperties' = 'yes'`,
environment properties files (`databases.<db>.datasources.jdbc.<ds>.DATABASEURI` and similar),
`ENCRYPT_PASSWORD … FOR_PROPERTIES_FILE`, applying the result through another profile. Also
onboarding an existing server into git and backups.

**Pitfalls.** Encrypted passwords are bound to the installation key: VQL with an `ENCRYPTED`
password applies on another server but the connection does not work, unless both servers share
the key or the export used a custom key. `includeCreateDatabase` adds `DROP DATABASE IF EXISTS`.
The automatic retry of deferred statements exists only in Design Studio and the import script,
not over the transport. Since 9.0 the export can include objects of other databases.

**Conventions it implies.** Data sources written without literal environment values, so that an
export with properties is possible — worth stating in `vql` and `datasources` now.

**Docs.** `vdp/vql/describing_catalog_elements/exporting_metadata/exporting_metadata`,
`vdp/administration/exporting_and_importing_the_server_metadata/exporting_and_importing_elements_across_different_environments/*`.

### 4.11 `publish` (new) — serve data to applications

**Owner review: dropped (see section 11).** Neither custom web services nor pointing consumers at the always-on RESTful, OData and GraphQL services. The original proposal follows.

**Scope.** `CREATE REST WEBSERVICE` (and SOAP as a second path), authentication, CORS,
`DEPLOY`/`REDEPLOY`/`UNDEPLOY`, `WEBCONTAINER_ELEMENT_STATUS`; readiness of views for the
always-on OData 4, GraphQL and RESTful services (primary keys, associations, names, privileges);
an HTTP check that the service answers.

**Pitfalls.** `CREATE` does not publish — `DEPLOY` does. `DEPLOY` without `LOGIN`/`PASSWORD` runs
the service with the credentials of whoever deployed it, i.e. the agent's profile, often an
administrator; the safe default is HTTP Basic with VDP and a non-empty list of accepted users.
`VERBOSEERRORS` defaults to true. Published names must be `[a-z0-9_]`: spaces and dots break OData
and XML; RESTful URLs are case-sensitive.

**New transport.** An HTTP profile to the web container for the verification step.

**Docs.** `vdp/vql/publication_of_web_services/*`,
`vdp/administration/publication_of_web_services/*`, `vdp/administration/restful_architecture/*`.

### 4.12 `scheduler` (new) — scheduled work

**Owner review: not now; a separate skill later (see section 11).** Nothing is taken in this round — no spike, no transport, no pointer from `cache`. When it comes back it is a skill of its own, and the notes below are its starting point.

**Scope.** Jobs: Simple and DAG Cache Management ("refresh the cache every night"), Data Loader,
Individual Query with CSV, Excel or JDBC exporters ("export this mart"), time-based triggers,
dependencies, mail handlers, retries, enable/disable, execution reports; projects and the VDP data
source of the Scheduler.

**Channel.** The REST API lives on the web container
(`…/webadmin/denodo-scheduler-admin/public/api/…`) and every call needs the `uri` query
parameter pointing at the Scheduler server itself. Authentication is HTTP Basic with a VDP user.
The guide documents only the projects endpoint — the rest must be taken from the server's
Swagger, so a spike comes first (the same way T11 did it for the marketplace). The RMI Java API
and the CLI scripts need a local Denodo installation and take the password as an argument.

**Pitfalls.** Cron expressions are Quartz: seconds first and `?` required in day-of-month or
day-of-week (`0 0 2 * * ?`, not `0 2 * * *`). `@` in a job query is a variable; `@ \ ^ { }` in
literals are escaped with a backslash. Dependencies run the "wrong way round": the dependent job
must start before the one it depends on. Exporters write files on the Scheduler host, not to the
user; in a cluster with fail-over the files may be duplicated. A DAG cache job over a whole server
or database reloads other teams' caches. 9.5 has no ARN or JDBC job types.

**Docs.** `scheduler/administration/creating_and_scheduling_jobs/*`,
`scheduler/administration/developer_api/rest_api/rest_api`.

---

## 5. P2 skills

### 5.1 `security` (new)

**Owner review: a basic skill in this round, details later (see section 11).** Not much more than the basic actions to start with: put a tag on an element, assign a role, create a global security policy. The exact scope is set when the task is taken. It brings forward two decisions from section 9 — global objects under the "own objects only" rule, and a second, non-admin profile to verify that a policy actually restricts — and the admin flag in `env check` from 2.5. A precedent for the first already exists: the verification chain creates server-level objects under the `verify_` prefix and removes them by id. The original proposal follows.

Roles and users, privileges, row and column restrictions with masking, global security policies
by tag, `CHOWN`, verification through `CONNECT USER`.
**Pitfalls:** there is no standalone `GRANT … TO` statement — privileges are clauses of
`CREATE/ALTER USER | ROLE | DATABASE`, with `TO` in one form and `ON` in another; there is no
`SELECT` privilege, it is `EXECUTE`; element privileges are ignored when the user has `EXECUTE`
on the whole database; a row restriction with a non-empty column list and without `ANY` returns
all rows when the query does not project all listed columns; roles combine privileges rather than
intersect; `DROP TAG … CASCADE` deletes the global security policies that use the tag;
restrictions do not apply to administrators, so read-back procedures prove nothing — only a
`SELECT` under a non-admin user does.
**Why P2, not P1:** episodic for a developer, every object is global, and verification needs a
second, non-admin profile. It rises to P1 if the audience includes data-product owners.
**Docs.** `vdp/vql/creating_databases_users_roles_and_access_privileges/*`,
`vdp/vql/global_security_policies/global_security_policies`,
`vdp/administration/databases_users_and_access_rights_in_virtual_dataport/*`.

### 5.2 `metrics` (new)

**Owner review: P2, a separate skill (see section 11).** Not a reference inside `views` and not part of `semantics`. Its description must go through the eval suite against `views` and `semantics`, which will compete for "define a metric" and "semantic layer".

**Owner's rule for the skill:** the only thing built on top of a metric view is a selection view; facts and dimensions are joined to that selection view, never to the metric view itself. To be confirmed live like every other rule before it carries a `verified:` mark.

**Built in T29** (`skills/metrics/`). The owner's rule is confirmed on 9.5.1 and is the core of
the skill: a metric view joined to another view in the same `FROM` runs until the query
timeout, over a few thousand rows too, while the same join over a selection view
answers at once; `evaluate_metric(a) * k` and `ROUND(evaluate_metric(a), n)` silently return
`a`, `evaluate_metric(a) / evaluate_metric(b)` returns no rows, `evaluate_metric` over any other
view returns `NULL`. Against the pitfalls listed below: a query without any dimension is
accepted and gives the grand total (the Data Marketplace page says otherwise); conditions on
metrics do go to `HAVING` and sorting does need projected fields; metric views do have lineage —
`USED_BY()` lists them. Not in the documentation at all: which fact rows survive is decided by
the association — `RIGHT` keeps facts without a dimension row only when the dimension endpoint
is `(0,1)`, `LEFT` keeps dimension members and drops those facts, and with a `(1)` endpoint
every type runs as `INNER`; a `HAVING` grouped by the key of a dimension view with no declared
primary key returns no rows; a `FILTER ( … )` clause exists (written by the wizard) and breaks
some queries.

Metric views, new in 9.5: `CREATE METRIC VIEW`, `EVALUATE_METRIC`, dimensions and metrics,
associations and cardinalities as prerequisites. At least one dimension is required; conditions
on metrics go to `HAVING` and on dimensions to `WHERE`; sorting only by projected fields; no data
lineage. The model does not know this object at all. Could fold into `semantics` later.
**Docs.** `vdp/vql/defining_a_derived_view/defining_a_metric_view/defining_a_metric_view`,
`vdp/administration/creating_derived_views/creating_metric_views/creating_metric_views`,
`vdp/data_catalog/metric_views/*`.

### 5.3 `materialize` (new)

**Owner review: P2, a separate skill, scope as proposed (see section 11).** Remote tables write to a source database with `DROP` and `TRUNCATE` inside, so the skill needs the second half of section 9, decision 2 — writes to external databases — and brings `CREATE [OR REPLACE] REMOTE TABLE` and remote-table `REFRESH` into the classifier (rule from 2.1).

Remote tables (`CREATE REMOTE TABLE` does not create a base view, unlike the wizard; editing is a
drop; `REFRESH` truncates), materialized tables, summaries (Enterprise Plus, server admin;
`summary_rewrite`; `LAST_DATE_REFRESH` versus the cache's `@LAST_REFRESH_DATE`), data movement.
All of it writes to an external database.
**Docs.** `vdp/vql/{remote_tables,materialized_tables,summary_views}/*`,
`vdp/administration/optimizing_queries/{summary_views,data_movement}/*`.

### 5.4 `connectors` (new)

**Owner review: dropped — created in Design Studio (item 4, section 11).**

Non-JDBC, non-file sources in one skill with a reference per type:

- **Native:** Salesforce (OAuth only; Bulk API only through VQL), MongoDB/DocumentDB, SOAP
  (WSDL at creation time, `$n`/`$$` mappings), OData v2/v4 (custom wrappers under the hood), LDAP.
- **Denodo Connects custom wrappers:** Kafka, Google Sheets, GraphQL, Distributed File System,
  FileSystem, DynamoDB, Couchbase, Azure AI Search. One pattern for all: the extension JAR on the
  server → `CREATE DATASOURCE CUSTOM … CLASSNAME … JARS '<extension name>' PARAMETERS (…)` →
  `CREATE WRAPPER CUSTOM` → base view.

**Pitfalls.** Custom wrapper parameters are named by their UI labels in quotes, with ` *` for
mandatory ones (`'Connection String *'`). `JARS` takes the extension name, not the file name.
Class names differ between sections of the same manual and across versions — a template is
valid only after a live check against the installed JAR, and the mark should carry the connector
version. `CREATE JAR <name> '<base64>'` may be a remote upload path, while
`skills/procedures/references/java-procedures.md` currently says a JAR needs a file on the server
— to check. Kafka listener (runs VQL from a topic) and Kafka custom wrapper (reads a topic as a
table) are different objects.
**Docs.** `vdp/vql/generating_wrappers_and_data_sources/creating_data_sources/{salesforce,mongodb,ldap,custom}_data_sources`,
`vdp/vql/generating_wrappers_and_data_sources/creating_data_sources/data_sources_for_web_services`,
`vdp/vql/defining_other_elements_of_the_catalog/defining_jar_extensions/defining_jar_extensions`,
the Denodo Connects custom wrapper manuals.

### 5.5 `datasources` (extension) — files

**Owner review: dropped — created in Design Studio (item 4, section 11).**

XML (XPath `TUPLEROOT`), Excel (a custom source internally; no grammar in the documentation —
take the template from `DESC VQL` of a sample), compressed and encrypted files, SFTP, fixed width,
S3/ADLS/HDFS/GCS routes.
**Docs.** `vdp/vql/generating_wrappers_and_data_sources/creating_data_sources/xml_data_sources`,
`vdp/administration/creating_data_sources_and_base_views/{excel_sources,delimited_file_sources,path_types_in_virtual_dataport}/*`.

### 5.6 `lakehouse` (new)

**Owner review: dropped (see section 11).**

Parquet, Iceberg and Delta Lake through the Lakehouse Accelerator (Embedded MPP): a JDBC data
source of type `EMBEDDED_MPP`, `DISCOVER_OBJECT_STORAGE_MPP_PROCEDURE`, statistics, partitions,
Iceberg snapshots and maintenance. Delta Lake is read-only; Iceberg UPDATE/MERGE needs format v2
and merge-on-read; bulk load into discovered views is not possible. `REGISTER_EMBEDDED_MPP`
creates a database, a user and a data source — not something to run on a shared server.
Enterprise Plus only; without an MPP cluster and object storage the templates stay `unverified`.
**Docs.** `vdp/administration/creating_data_sources_and_base_views/parquet_sources/*`,
`vdp/administration/embedded_parallel_processing/*`, `mpp/*`.

### 5.7 `dbt` (new)

**Owner review: dropped (see section 11).**

The Denodo dbt adapter (Denodo 9.4+, over the same port 9996) as an alternative authoring path:
`view` → view, `table` → view with full cache, `incremental` → full cache with append/merge
(requires a cache database, not transactional), `materialized_view` → materialized table.
`is_incremental()` is not supported — the incremental condition uses `incremental_condition`
with `@LAST_REFRESH_DATE`; `insert_overwrite`, `delete_insert` and `microbatch` are not supported.
**Docs.** Denodo Connects "DBT Denodo Adapter" manual.

### 5.8 `deploy` — Solution Manager branch

**Owner review: dropped with item 10 (section 11).**

Solution Manager REST (port 10090, stateless, Basic): `POST /revisions/loadFromVQL` →
`POST /revisions/{id}/validate` → `POST /deployments` → poll `GET /deployments/{id}/progress`,
with `vdpProperties`/`schProperties`. Revisions "from selected elements" (with Scheduler jobs)
exist only in the UI; creating revisions from VQL needs the promotion admin role or
`DEPLOY_ADMIN`; the VQL must not carry a BOM when sent as base64; `POST /deployments` reports
missing properties in the response body, not as an HTTP error; a deployment waits for running
queries and queues new ones — downtime on a single-node production. Default of the skill: stop at
`validate`, deploy only on explicit confirmation.
**Docs.** `solution_manager/administration/promotions/*`,
`solution_manager/administration/appendix/rest_api/rest_api`.

---

## 6. P3 skills

- **`ai`** — LLM functions (`CLASSIFY_AI`, `SUMMARIZE_AI`, `TRANSLATE_AI` …), the `vector` type,
  `EMBED_AI`, `VECTOR_DISTANCE`, `DENODO_ASSISTANT_GENERATE_*` procedures. Enterprise Plus; every
  row costs money; LLM configuration is UI only. Could live as a reference inside `dialect`.
  **Owner review: taken in this round, a skill of its own.** First check whether the server has
  an LLM configured; the skill never runs an AI function over a table without a `LIMIT` the
  human agreed to, because every row is a paid call.
- **`dml`** — `INSERT`/`UPDATE`/`DELETE` through views, `RETURNING`, `WITH CHECK OPTION`. Writes
  to sources; rarely a developer task.
  **Owner review: taken in this round, a skill of its own.** The safety side (writes to source
  databases, section 9 decision 2) is settled later; the classifier already flags
  `INSERT`/`UPDATE` by decision 2.1.
- **`marketplace` (governance)** — deprecation, warnings, endorsements, workflow requests, saved
  queries, metadata search, marketplace metadata export/import between environments.
  **Owner review: dropped.**
- **`listeners`** — JMS and Kafka listeners; client JARs on the host; a listener executes any VQL
  arriving from the queue.
  **Owner review: dropped.**
- **`sap`** — BAPI, BW/BI, Essbase, OLAP; needs SAP JCo installed on the server host.
  **Owner review: dropped with item 4 (Design Studio).**
- **`extensions`** — Java custom functions, wrappers, input filters, view policies; local build
  plus JAR upload.
  **Owner review: dropped.**
- **`clients`** — connecting applications: JDBC (`jdbc:denodo://`, the `jdbc:vdb://` form is
  deprecated), ODBC, Arrow Flight SQL, SQLAlchemy, Spark, Hibernate, Power BI.
  **Owner review: dropped.**
- **`vcs`** — a fork inside `deploy`. Denodo explicitly discourages running the VCS commands
  manually or from CI/CD; workspaces (9.2) are the relevant new feature.
  **Owner review: dropped with item 10.**
- **Instructions for a human, not automation:** SaaS wizards (Marketo, GA4, Dynamics BC,
  SharePoint — mostly OAuth authorization-code flows in a browser) and governance bridges
  (Collibra, Purview, OpenLineage, IGC — separate services configured on their own host).
  **Owner review: covered by item 4** — source wizards are Design Studio's job.

---

## 7. Out of scope

No channel for the agent, or operations rather than development: installation and upgrade,
JVM and memory, server configuration, server authentication (Kerberos, SSO, OAuth), clusters and
backups, monitoring (JMX, Denodo Monitor, logs), the Diagnostic & Monitoring Tool (UI without an
API), licences and metering, the Agora console, Lakehouse Accelerator deployment on Kubernetes,
Denodo Dashboard, Adoption Report, LLM and vector database configuration for the Denodo
Assistant, Solution Manager environment modelling.

---

## 8. Cross-cutting findings

- **Documentation is a hypothesis.** Examples found: the DF wrapper grammar allows a field type
  that the server rejects; type conversion tables are outdated; `PASSOWORD_GRANT` typo;
  `ADDYEAR` syntax printed as `ADDWEEK`; `PERCENTILE_DIST` instead of `PERCENTILE_DISC`; the
  `COUNT(field)` semantics without GROUP BY contradict each other; `USING VIEW PARAMETERS` versus
  `USING PARAMETERS`; Denodo Connects examples with `i18` instead of `i18n`, a stray `;` in
  `CREATE PROCEDURE … JARS`, `REMOVE FROM` instead of `DELETE FROM`. Rule for new skills: take a
  grammar from the guide, confirm it with `DESC VQL` of a sample or a live run.
- **Excel, OData and custom sources have no VQL grammar in the guide.** The general technique:
  create a sample, read `DESC VQL`, turn it into a template.
- **Licensing bundles.** Data Marketplace and the Diagnostic & Monitoring Tool are absent in
  Standard and Professional; summaries, global security policies, the Lakehouse Accelerator, LLM
  features and Assisted Query need Enterprise Plus; VDP tag import into the marketplace needs the
  Semantics feature pack. Skills should tell a licence error from a syntax error; an edition flag
  in the environment profile would help.
- **Agora changes the rules:** users and roles are managed in the Agora console, the `FILE`
  privilege is disabled, bulk load to several databases is off, there is no Solution Manager REST
  API.
- **Every DDL, `LIST` or `DESC` briefly locks the database**, and global objects trigger
  single-user mode — relevant for a shared development server.
- **Transport identity.** Connections of the agent appear with access interface `ODBC`. Whether
  `application_name` can tag sessions for the Resource Manager and audit is unknown — to check.
- **Several new capabilities need new REST profiles:** the web container (published services),
  the Scheduler (two addresses: web admin URL and the `uri` of the server), the Solution Manager.
  The design spec (section 7.3) already anticipates this as "one transport plus one skill".

---

## 9. Decisions needed from the owner

1. ~~**Bring the dialect skill back.**~~ **Decided:** no skill; a verified reference in `vql`
   plus a short table of silent deltas (section 4.1, section 11).
2. **Extend the "write only to your own database" invariant.** Split by the review into three
   parts, each settled inside the task that needs it:
   - *the cache of the agent's own views* — counted as its own objects; working assumption
     taken with `cache` (item 6);
   - *global objects* (roles, users, global security policies, VDP tags) — settled in the
     `security` task (item 13); the verification chain's `verify_` prefix plus removal by id is
     the existing precedent;
   - *writes to external databases* (remote tables, materialized tables, writes through views)
     — settled with `materialize` (item 15) and `dml` (item 22); the owner put the safety of
     `dml` after the skill itself.
   `publish` no longer needs it — dropped.
3. **A second, non-admin profile in the transport** — settled in the `security` task (item 13),
   together with the admin flag in `env check` (2.5).

---

## 10. Build order after the owner review

| Wave | Content | Why this order |
|---|---|---|
| 0 | Classifier: server `SET '…'` and `INSERT`/`UPDATE`/`MERGE` (2.1); `datasources` routes non-v1 sources to Design Studio (item 4); `vql/references/dialect.md` with a live `HELP` check (item 1, 2.5) | changes to existing skills and the core that every later skill relies on |
| 1 | `views`: union semantics, partitioned unions, `FLATTEN`/`NEST` (item 2); `views` checks: delegation (item 5) and column-level dependencies (item 3) | one existing skill, VQL only, file fixtures on the current server |
| 2 | New VQL skills: `cache`, FULL only (item 6); `semantics`, VDP half (item 7); `metrics` (item 14) | VQL only; `metrics` stands on the associations `views` already builds |
| 3 | `marketplace`: carry metadata of a renamed view over (item 8), spike on the OpenAPI first | REST on the existing marketplace transport |
| 4 | `security`, basic actions (item 13); `ai` (item 21); `dml` (item 22); `materialize` (item 15); `testing` with the Testing Tool (item 9) | each needs a decision or an installation first: global objects and a second profile, an LLM on the server, writes to external databases, the Testing Tool |
| later | `scheduler` as a separate skill (item 12) | not in this round |

Dropped: 2.2, 2.3, items 10, 11, 16–20, 23–28; 2.4 has no item of its own. Every new skill or
description change goes through the eval suite (`evals/`); the pairs most likely to compete are
`semantics` versus `views` and `marketplace`, `metrics` versus `views` and `semantics`, `cache`
versus `views`, and `dml` versus `views`.

---

## 11. Owner review log

The owner went through this roadmap item by item, starting 2026-09-29. One line per decision;
the sections above are edited to match, and section 10 (build order) was rebuilt from the result.

| Item | Decision | Reason |
|---|---|---|
| 2.1 safety classifier | P0 → P1, narrowed | The guard refuses only on production profiles, and a text classifier is never complete. Now only what an agent writes without any skill (server `SET '…'`, `INSERT`/`UPDATE`/`MERGE`); every later skill extends the classifier with what it teaches |
| 2.2 `DESC VQL` options | dropped | Already covered by "read it, do not apply it" in `execute` and `views`; changing the defaults would break `DESC VQL` as a syntax reference. Safe export options go with `deploy`, if it stays |
| 2.3 transactions | dropped | `execute` already says nothing is rolled back after `failed_at`; the transport is autocommit anyway |
| 2.4 secrets | no separate item | Each case comes with a skill not yet written; the first skill that needs a secret without `ENCRYPTED` brings the substitution (and output redaction) with it |
| 2.5 `HELP` | dropped after a live check | Useful only if it answers over ODBC. Checked on 9.5.1 (2026-09-30): `HELP`, `HELP CREATE VIEW` and `HELP CREATE DATASOURCE JSON` answer `ok` with no columns and no rows over the transport, so there is nothing to put in `vql` |
| 2.5 admin flag in `env check` | moved to `security` | Matters only for admin-only procedures and security restrictions |
| 2.5 identifier conventions | dropped | Mostly covered by `vql` naming and `errors.md`; the rest is a loud error the agent fixes itself |
| 2.5 feature renames | convention, done | One sentence in `CONTRIBUTING.md` on descriptions |
| 1 `dialect` (and decision 9.1) | P1, reference in `vql` instead of a skill | Nobody triggers a dialect skill by phrase; it would load only by cross-reference and compete with `views`. The silent deltas are real (T13 `SUM` overflow, T19 `decimal`), so they are kept — verified on `Dual()` |
| 2 `views` extension | P1, whole scope minus `INTERSECT`/`MINUS` | Union semantics, partitioned unions and `FLATTEN`/`NEST` are wanted; set operations are not. PK, descriptions, parameters and the dependants check are already in `views` |
| 3 `lineage` | P2, additions to `views` instead of a skill | View-level impact is already in `views` and the procedure family in `procedures`; only column level and two pitfalls are missing |
| 4 `datasources` extension | dropped; the skill routes non-v1 sources to Design Studio | The verified v1 templates stay with the agent; everything beyond them is faster and safer in the Design Studio wizard. Base views: the agent where it works, Design Studio when it does not work straight away |
| 16 `connectors`, 17 files, 25 `sap` | dropped | Consequence of item 4: every data source type beyond v1 goes to Design Studio |
| 5 `performance` | P1, delegation check in `views` only | Silent loss of push-down is the real risk of a generated mart; tuning is expert work for Design Studio and the administrator |
| 6 `cache` | P1, separate skill now, FULL cache only | A skill of its own so it can grow; first scope is on/off, fill with what the human names, clear the cache tables. Other cache settings wait |
| 7 `semantics` | P1, separate skill, VDP half only | Existing databases need an audit the per-view rules in `views` never run; descriptions come from the data and are approved by the human. Marketplace half later |
| 8 `marketplace` safe sync | P1, as proposed | Carry tags, categories and descriptions of a renamed view over through REST; spike on the OpenAPI first, fallback to a warning plus the UI dialog only if the API cannot do it |
| 9 `testing` | P2, Denodo format run by the real Testing Tool | Tests stay compatible with the tool teams run in CI; no runner of our own to maintain |
| 10 `deploy`, 20 Solution Manager, 28 `vcs` | dropped | Moving between environments and bringing objects into git are not part of the plugin |
| 11 `publish` | dropped | Serving data to applications is not part of the plugin, in either form |
| 12 `scheduler` | later, a separate skill | Not in this round at all; when it returns it is its own skill, starting from section 4.12 |
| 13 `security` | basic skill in this round, scope set when taken | Tag an element, assign a role, create a global security policy — little more than that at first; details later |
| 14 `metrics` | P2, separate skill | A metric view is a new object the model does not know at all; its own skill rather than a reference in `views` |
| 14 `metrics` (addition) | rule recorded | Only selection views are built on a metric view; other facts and dimensions are joined to the selection view |
| 15 `materialize` | P2, separate skill | Remote tables, materialized tables, summaries and data movement in one skill of their own, not folded into `cache` |
| 18 `lakehouse` | dropped | Enterprise Plus with an MPP cluster, nothing to verify it on, and connecting the source is Design Studio's job after item 4 |
| 19 `dbt` | dropped | A competing authoring path to the plugin's own `.vql` loop, useful only to dbt teams |
| 21 `ai` | this round, separate skill | Taken at once; check the server's LLM configuration first, never an unbounded AI call over a table |
| 22 `dml` | this round, separate skill | Taken at once; the safety of writes to sources is settled later |
| 23, 24, 26, 27 | dropped | Marketplace governance, listeners, Java extensions and client code are not part of the plugin |
| Section 6, instructions for a human | covered by item 4 | SaaS source wizards and governance bridges are Design Studio or their own hosts |
