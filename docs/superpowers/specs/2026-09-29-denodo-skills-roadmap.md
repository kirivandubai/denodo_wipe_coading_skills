# Denodo 9.5 skills roadmap: what to build after v1

**Date:** 2026-09-29
**Status:** proposal — priorities are a recommendation, the decisions in section 9 are open
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

## 2. P0 — fix the core before adding skills

These are not new skills but gaps in `execute` and `vql`. Every new domain skill widens the
set of statements the agent emits, so these should be closed first.

### 2.1 The safety classifier misses state-changing statements

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

Port 9996 is the ODBC interface of Virtual DataPort. By default it ignores `BEGIN`, `COMMIT`,
`ROLLBACK`, `SAVEPOINT` and `RELEASE`, so a batch of DDL applied through psycopg2 is not atomic
and a rollback undoes nothing. Enabling transactions is a server-wide `SET` that affects every
ODBC client. This belongs in the core skill as a stated fact.
Source: `vdp/developer/access_through_odbc/integration_with_third-party_applications/disabling_transactions`.

### 2.4 Secrets appear in more statements than data sources

Passwords and keys also appear in `CREATE/ALTER USER`, `CONNECT USER … PASSWORD`,
`DEPLOY WEBSERVICE … PASSWORD`, `AUTHENTICATION BASIC`, `CREATE DATABASE … VCS … PASSWORD`,
listeners, `REGISTER_EMBEDDED_MPP`, the VQL Generation procedures and custom wrapper
`PARAMETERS`. HTTP `HEADERS` values (API keys) have no `ENCRYPTED` form at all, so today they
would land in git in clear text. A general secret placeholder resolved at apply time (the
`@{secret:<name>}` idea already listed in `docs/TASKS.md`) becomes necessary rather than
optional. Credentials vault clauses (`VAULT_SECRET`, `FROM_VAULT`, `CREDENTIALS_VAULT(...)`) are
the platform-native alternative where a vault is configured.

### 2.5 Smaller core additions

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
| 1 | `dialect` | new | P1 | daily | blocker (silent wrong data) | VQL |
| 2 | `views` | extension | P1 | daily | important | VQL |
| 3 | `lineage` | new | P1 | daily–weekly | important | VQL, read only |
| 4 | `datasources` (HTTP, JDBC depth, drift) | extension | P1 | weekly | blocker for REST sources | VQL |
| 5 | `performance` | new | P1 | weekly | important | VQL |
| 6 | `cache` | new | P1 | weekly | important | VQL |
| 7 | `semantics` | new | P1 | weekly | important (AI consumers) | VQL + Marketplace REST |
| 8 | `marketplace` (safe sync) | extension | P1 | weekly | important | Marketplace REST |
| 9 | `testing` | new | P1 | weekly | important | VQL (new `scripts/denodo test`) |
| 10 | `deploy` | new | P1 | weekly / per release | important | VQL |
| 11 | `publish` | new | P1 | weekly–episodic | blocker for serving apps | VQL + new HTTP profile |
| 12 | `scheduler` | new | P1 | weekly | blocker for scheduled work | new Scheduler REST profile |
| 13 | `security` | new | P2 | episodic | important for production | VQL |
| 14 | `metrics` | new | P2 | episodic, growing | nice → important | VQL |
| 15 | `materialize` | new | P2 | episodic | important | VQL |
| 16 | `connectors` | new | P2 | episodic | important per project | VQL (+ JAR upload) |
| 17 | `datasources` (files) | extension | P2 | episodic | important per project | VQL |
| 18 | `lakehouse` | new | P2 | episodic | important on Enterprise Plus | VQL |
| 19 | `dbt` | new | P2 | daily for dbt teams, else never | important for dbt teams | local `dbt` over the same port |
| 20 | `deploy` (Solution Manager) | extension | P2 | per release | important where SM is used | new Solution Manager REST profile |
| 21 | `ai` | new | P3 | episodic | nice | VQL |
| 22 | `dml` | new | P3 | episodic | nice | VQL |
| 23 | `marketplace` (governance) | extension | P3 | episodic | nice | Marketplace REST |
| 24 | `listeners` | new | P3 | rare | nice | VQL + broker |
| 25 | `sap` | new | P3 | rare | important for SAP shops | VQL + host install |
| 26 | `extensions` | new | P3 | rare | nice | local Java build + JAR |
| 27 | `clients` | new | P3 | episodic | nice | client code only |
| 28 | `vcs` | fork inside `deploy` | P3 | weekly where used | nice | VQL, discouraged by Denodo |

---

## 4. P1 skills

### 4.1 `dialect` (new) — VQL expressions versus standard SQL

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

**Scope.** `ALTER VIEW | TABLE … CACHE PARTIAL [EXACT] [PRELOAD] | FULL | OFF`, time to live,
preload and invalidation through `CONTEXT`, incremental loads (`@LAST_REFRESH_DATE`), cache
indexes, `GET_CACHE_*` and `CACHE_CONTENT` for inspection.

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

**Scope.** Renaming or recreating a view that already exists in the marketplace. Synchronisation
sees a rename as a deletion plus a new element; tags, categories, descriptions, custom properties
and endorsements of the old element are lost unless the elements are matched (in the UI this is a
drag-and-drop dialog; whether the REST API exposes it must be read from the server's OpenAPI).
Deleting an external tool server irreversibly removes its elements with their metadata.

**Cross-reference.** `views` and `vql` should route "rename / recreate a view that is in the
marketplace" to `marketplace` first.

**Docs.** `vdp/data_catalog/administration/synchronize/synchronize`.

### 4.9 `testing` (new) — regression tests for data products

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

Metric views, new in 9.5: `CREATE METRIC VIEW`, `EVALUATE_METRIC`, dimensions and metrics,
associations and cardinalities as prerequisites. At least one dimension is required; conditions
on metrics go to `HAVING` and on dimensions to `WHERE`; sorting only by projected fields; no data
lineage. The model does not know this object at all. Could fold into `semantics` later.
**Docs.** `vdp/vql/defining_a_derived_view/defining_a_metric_view/defining_a_metric_view`,
`vdp/administration/creating_derived_views/creating_metric_views/creating_metric_views`,
`vdp/data_catalog/metric_views/*`.

### 5.3 `materialize` (new)

Remote tables (`CREATE REMOTE TABLE` does not create a base view, unlike the wizard; editing is a
drop; `REFRESH` truncates), materialized tables, summaries (Enterprise Plus, server admin;
`summary_rewrite`; `LAST_DATE_REFRESH` versus the cache's `@LAST_REFRESH_DATE`), data movement.
All of it writes to an external database.
**Docs.** `vdp/vql/{remote_tables,materialized_tables,summary_views}/*`,
`vdp/administration/optimizing_queries/{summary_views,data_movement}/*`.

### 5.4 `connectors` (new)

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

XML (XPath `TUPLEROOT`), Excel (a custom source internally; no grammar in the documentation —
take the template from `DESC VQL` of a sample), compressed and encrypted files, SFTP, fixed width,
S3/ADLS/HDFS/GCS routes.
**Docs.** `vdp/vql/generating_wrappers_and_data_sources/creating_data_sources/xml_data_sources`,
`vdp/administration/creating_data_sources_and_base_views/{excel_sources,delimited_file_sources,path_types_in_virtual_dataport}/*`.

### 5.6 `lakehouse` (new)

Parquet, Iceberg and Delta Lake through the Lakehouse Accelerator (Embedded MPP): a JDBC data
source of type `EMBEDDED_MPP`, `DISCOVER_OBJECT_STORAGE_MPP_PROCEDURE`, statistics, partitions,
Iceberg snapshots and maintenance. Delta Lake is read-only; Iceberg UPDATE/MERGE needs format v2
and merge-on-read; bulk load into discovered views is not possible. `REGISTER_EMBEDDED_MPP`
creates a database, a user and a data source — not something to run on a shared server.
Enterprise Plus only; without an MPP cluster and object storage the templates stay `unverified`.
**Docs.** `vdp/administration/creating_data_sources_and_base_views/parquet_sources/*`,
`vdp/administration/embedded_parallel_processing/*`, `mpp/*`.

### 5.7 `dbt` (new)

The Denodo dbt adapter (Denodo 9.4+, over the same port 9996) as an alternative authoring path:
`view` → view, `table` → view with full cache, `incremental` → full cache with append/merge
(requires a cache database, not transactional), `materialized_view` → materialized table.
`is_incremental()` is not supported — the incremental condition uses `incremental_condition`
with `@LAST_REFRESH_DATE`; `insert_overwrite`, `delete_insert` and `microbatch` are not supported.
**Docs.** Denodo Connects "DBT Denodo Adapter" manual.

### 5.8 `deploy` — Solution Manager branch

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
- **`dml`** — `INSERT`/`UPDATE`/`DELETE` through views, `RETURNING`, `WITH CHECK OPTION`. Writes
  to sources; rarely a developer task.
- **`marketplace` (governance)** — deprecation, warnings, endorsements, workflow requests, saved
  queries, metadata search, marketplace metadata export/import between environments.
- **`listeners`** — JMS and Kafka listeners; client JARs on the host; a listener executes any VQL
  arriving from the queue.
- **`sap`** — BAPI, BW/BI, Essbase, OLAP; needs SAP JCo installed on the server host.
- **`extensions`** — Java custom functions, wrappers, input filters, view policies; local build
  plus JAR upload.
- **`clients`** — connecting applications: JDBC (`jdbc:denodo://`, the `jdbc:vdb://` form is
  deprecated), ODBC, Arrow Flight SQL, SQLAlchemy, Spark, Hibernate, Power BI.
- **`vcs`** — a fork inside `deploy`. Denodo explicitly discourages running the VCS commands
  manually or from CI/CD; workspaces (9.2) are the relevant new feature.
- **Instructions for a human, not automation:** SaaS wizards (Marketo, GA4, Dynamics BC,
  SharePoint — mostly OAuth authorization-code flows in a browser) and governance bridges
  (Collibra, Purview, OpenLineage, IGC — separate services configured on their own host).

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

1. **Bring the dialect skill back.** This reverses the T13 conclusion that `query` is not needed
   (section 4.1 gives the reasons). Name to choose: `dialect`, `sql` or the original `query`.
2. **Extend the "write only to your own database" invariant.** It does not cover global objects
   (users, roles, global security policies, VDP tags, JARs, maps, server `SET`) or writes to
   external databases (cache, remote tables, summaries, data movement). Without an extension,
   `security`, `publish`, `cache` and `materialize` cannot be verified on a shared server.
   Options: a reserved prefix for test objects plus mandatory cleanup, a dedicated server, or
   9.2 workspaces if the transport accepts the `workspace` connection parameter (to check).
3. **A second, non-admin profile in the transport**, required to verify `security` and any
   privilege-dependent behaviour honestly.

---

## 10. Suggested build order

| Wave | Content | Why this order |
|---|---|---|
| 0 | Section 2: safety classifier, safe `DESC VQL`, transactions note, secret placeholders | every later skill emits more statements |
| 1 | `dialect`, `views` extension, `lineage`, `datasources` extension, `performance`, `cache` | VQL only, verifiable on the current server with file fixtures |
| 2 | `semantics` + marketplace safe sync, `testing`, `deploy`, `publish` | one new HTTP profile; `testing` protects later waves |
| 3 | `scheduler` (spike first), `security` (non-admin profile), `metrics` | new transport and new invariant decisions |
| 4 | remaining P2 by demand, then P3 | narrow audiences, harder verification |

Each new skill or description change goes through the eval suite (`evals/`): at least `dialect`
versus `views`, `connectors` versus `datasources`, and `semantics` versus `marketplace` will
compete for the same phrases.
