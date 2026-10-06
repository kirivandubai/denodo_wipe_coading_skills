# Predefined stored procedures

The server ships them; you never create them. Which ones a server has depends on its
features (the Lakehouse Accelerator, formerly Embedded MPP, and the Denodo Assistant):
`LIST PROCEDURES` on your server is the authority, not this file and not the documentation.

This page answers two questions: how to call any of them, and which family to look in.

## Calling one

```sql
-- verified: 9.5.1 (live, 2026-10-07)
SELECT column_name, column_vdp_type, column_type
  FROM GET_PROCEDURE_COLUMNS()
 WHERE input_procedure_name = 'GENERATE_STATS';
```

| Rule | Detail |
|---|---|
| Parameters live in `WHERE`, under their own names | `input_…` for many, plain for others (`DESC PROCEDURE` shows which); they are passed into the procedure, not applied to its output |
| The result schema carries the inputs too | `SELECT *` echoes every input column back; name the columns you want |
| Mandatory parameters announce themselves | `No search methods ready to be run. The following fields are obligatory: input_view_database_name, input_view_name` |
| A missing name can fail bare | `PING_DATA_SOURCE` answers `Error executing query. Total time …`, with nothing about the cause, for example over a data source that does not exist (named or positional) or a database that does not exist — *verified: 9.5.1 (live, 2026-10-07)* |
| `CALL` is the other form | positional, `null` for the ones you skip: `CALL USED_BY('sales_analytics', 'customer', null)`. It cannot be joined with anything |
| A procedure can be joined like a view | that is the reason to prefer the `SELECT` form |

Two ways to read a signature, both on the server:

```sql
-- verified: 9.5.1 (live, 2026-10-07)
DESC PROCEDURE USED_BY;                               -- name, type, direction (IN/OUT)
SELECT column_name, column_type, column_is_nullable   -- the same, filterable, plus nullable
  FROM GET_PROCEDURE_COLUMNS() WHERE input_procedure_name = 'USED_BY';
```

Through the execution layer: `vql desc --env dev USED_BY --type procedure`.

## A call that looks like a read and is not

Every one of these can change state, and every one of them is invoked with `SELECT` or
`CALL`. Treat a call like a `DROP`: show the human first.

| Procedure | What it changes |
|---|---|
| `GENERATE_STATS` | overwrites the stored statistics of a view. Deprecated in 9.5, still shipped, still writes; its parameters are `viewname`, `databasename` — *verified: 9.5.1 (live, 2026-09-17)* |
| `GENERATE_STATS_FOR_FIELDS` | the same for the fields named: gathers and **stores** their statistics. Deprecated |
| `GENERATE_SMART_STATS_FOR_FIELDS` | Deprecated; the same, from the source's system tables where it can |
| `GET_STATS_FOR_FIELDS` | the documented replacement of the three above: with `input_save = true` it **stores** the statistics it gathers (its page's description says "not stores"; the parameter says it does). `input_save = false` only returns them, and is flagged all the same |
| `COMPUTE_SOURCE_TABLE_STATS` | runs the commands that make **the source database** compute the statistics of a base view's table |
| `CREATE_REMOTE_TABLE` | creates a table **in the JDBC source**, fills it with a query's rows, and creates a base view over it; with `replace_remote_table_if_exist = true`, drops whatever table had that name first. A new table where the human named, with `false`, is the agent's own (`/denodo:materialize`) |
| `DROP_REMOTE_TABLE` | drops the base view or summary and the table **in the source** behind it; with cascade, the dependants too (`/denodo:materialize`) |
| `CLEAN_CACHE_DATABASE` | runs the cache maintenance task: deletes expired and invalidated cached rows of a database, or of one view |
| `DROP_NONACTIVE_CACHE_TABLES` | drops cache tables no cached view references any more (its preview mode only lists them, and is flagged all the same) |
| `COMPACT_CACHE` | deletes outdated control rows and the tables of expired temporary tables in the **whole cache data source** — every database that caches there, not only the one named — and can put the server in single-user mode |
| `CHECK_CACHE_NAMES` | with `fix_cache_names_mappings = true`, deletes and rewrites the name mappings of the **whole cache data source**, and can put the server in single-user mode. `false` only lists them, and is flagged all the same |
| `REFRESH_BASE_VIEW` | rewrites a base view's columns, types, key and descriptions from the source, and with `propagate_views` the views above it |
| `MIGRATE_DATE_TYPES` | retypes the `date` columns of base views, interface views and types; the change can spread to other databases, and with `input_database_name` null it covers the whole server. It has no listing mode |
| `CREATE_TAGS_FROM_VIEW` | with `input_action = 'CREATE'`, creates and assigns VDP tags — and with `input_unassign_tags_mode = 'ALL'` takes every earlier assignment off. `'READ'` only reads, and is flagged all the same |
| `CREATE_TAGS_FROM_COLLIBRA` | the same, from Collibra |
| `LOGCONTROLLER` | the log level of a category **for the whole server**, until it is set back or the server restarts; `DEBUG` and `TRACE` can write query results into the log |
| `MAINTAIN_METADATA_TABLES` | maintenance of the database that stores the server's own metadata |
| `CHECK_METADATA` | with `input_remove_broken_references = true`, fixes the metadata and puts the server in single-user mode; with `input_remove_broken_views_on_cascade = true` also removes views and procedures, in databases it was not given too. Listing (the default) only reads, and is flagged all the same |
| `CREATE_SCHEMA_ON_SOURCE` | DDL in the source (Lakehouse Accelerator and PrestoDB data sources) |
| `DROP_SCHEMA_ON_SOURCE` | DDL in the source: removes a schema |
| `REMOVE_ICEBERG_VIEW_SNAPSHOTS` ¹ | expires snapshots of the Iceberg table behind a view; what they held cannot be rolled back to |
| `ROLLBACK_ICEBERG_VIEW_TO_SNAPSHOT` ¹ | replaces the current data of the table with an older snapshot |
| `OPTIMIZE_LAKEHOUSE_ACCELERATOR_CACHE_TABLES` | with its defaults (no arguments), deletes orphan files older than 3 days and snapshots older than 5 days of the Lakehouse Accelerator's cache control tables, and rewrites their data files and manifests. `remove_orphan_files = false` and `remove_snapshots = false` keep both, and are flagged all the same |

¹ documented for 9.5, but absent from a 9.5.1 server without the Lakehouse Accelerator —
`LIST PROCEDURES` decides what your server has.

**The tool stops on these.** `scripts/denodo` matches the procedure name in
`SELECT … FROM name(…)` and `CALL name(…)` against this list and reports
`destructive: "procedure"`; on a profile with `production: true` the call is refused
until a human has confirmed and `--allow-destructive` is passed — the same gate as a
`DROP` (`/denodo:execute`, *Destructive operations*). `DROP_REMOTE_TABLE()` gets no
free pass for being spelled `SELECT`.

**What the name check cannot see:** a VQL procedure of your own that runs DDL through
`EXECUTE` inside its body. The tool sees `CALL my_cleanup()` and knows nothing about the
`DROP` inside; the same goes for any predefined procedure not in this list. The rule is
unchanged for those — read what the procedure does before calling it — the tool just
cannot back it up.

## Families

Names are grouped by what they answer, not by the guide's alphabet. Each family lists the
ones worth knowing; `LIST PROCEDURES` has the rest.

| Family | Procedures | Note |
|---|---|---|
| Catalog and metadata | `GET_DATABASES`, `GET_ELEMENTS`, `GET_VIEWS`, `GET_VIEW_COLUMNS`, `GET_PROCEDURE_COLUMNS`, `ELEMENT_METADATA`, `CATALOG_METADATA_VIEWS` | the read-backs the other skills use in their Verify sections. `GET_VIEW_COLUMNS` returns `column_name`, `column_vdp_type`, `column_sql_type`, `column_size`, `column_decimals`, `column_is_primary_key`, `column_is_nullable`, `column_remarks`, `ordinal_position` among others — there is no `column_type` |
| Keys and relations | `GET_PRIMARY_KEYS`, `GET_FOREIGN_KEYS`, `GET_EXPORTED_KEYS`, `GET_REFERENTIAL_CONSTRAINTS` ², `GET_ASSOCIATIONS`, `GET_VIEW_INDEXES` | `GET_ASSOCIATIONS` is the one `/denodo:views` verifies associations with |
| Dependencies and impact | `USED_BY`, `VIEW_DEPENDENCIES`, `COLUMN_DEPENDENCIES`, `QUERY_DEPENDENCIES` ², `GET_PUBLIC_VIEW_DEPENDENCIES` | `USED_BY` lists the dependants of a view (what is built on it), `VIEW_DEPENDENCIES` what it stands on. Both take a view; neither takes a procedure. `COLUMN_DEPENDENCIES` traces output columns only — a column used only in a join or a filter has no row, so it cannot tell whether a column is safe to drop; `/denodo:views` has the recipe that can |
| Source introspection | `PING_DATA_SOURCE`, `GET_JDBC_DATASOURCE_TABLES`, `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW`, `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW_FROM_QUERY`, `GET_SOURCE_COLUMNS`, `GET_SOURCE_TABLE`, `GET_SOURCE_CHANGES`, `REFRESH_BASE_VIEW` | this is a job, not a lookup — `/denodo:datasources` walks it |
| Tags | `GET_VIEW_TAGS`, `CREATE_TAGS_FROM_VIEW`, `CREATE_TAGS_FROM_COLLIBRA`, `GET_GLOBAL_SECURITY_POLICIES_TAGS` | VDP tags, not marketplace tags (`/denodo:catalog`); the two `CREATE_TAGS_FROM_*` write — the list above |
| Statistics | `GENERATE_STATS`, `GENERATE_STATS_FOR_FIELDS`, `GENERATE_SMART_STATS_FOR_FIELDS`, `GET_STATS_FOR_FIELDS`, `GET_AVAILABLE_STATS_MODES`, `COMPUTE_SOURCE_TABLE_STATS` | the generating ones, `GET_STATS_FOR_FIELDS` and `COMPUTE_SOURCE_TABLE_STATS` write — the list above |
| Cache | `CACHE_CONTENT`, `GET_CACHE_TABLE`, `GET_CACHE_COLUMNS`, `GET_CACHE_CONFIGURATION`, `CLEAN_CACHE_DATABASE`, `COMPACT_CACHE`, `DROP_NONACTIVE_CACHE_TABLES` | the last three write — the list above. Reading and clearing the cache of one view is `/denodo:cache` |
| MPP, lakehouse, Iceberg | `CREATE_REMOTE_TABLE`, `DROP_REMOTE_TABLE`, `REGISTER_EMBEDDED_MPP`, `DISCOVER_OBJECT_STORAGE_MPP_PROCEDURE`, `GET_ICEBERG_VIEW_SNAPSHOTS`, `ROLLBACK_ICEBERG_VIEW_TO_SNAPSHOT`, `OPTIMIZE_LAKEHOUSE_ACCELERATOR_CACHE_TABLES` | remote tables and summaries are `/denodo:materialize`; the rest belongs to the Lakehouse Accelerator (formerly Embedded MPP), which these skills do not set up |
| Query diagnostics | `GET_QUERY_EXECUTION_PLAN`, `GET_DELEGATED_SQLSENTENCE`, `GET_SELECT_NAVIGATIONAL_QUERY` ², `GET_SESSIONS`, `GET_SERVER_CONNECTIVITY` | `GET_DELEGATED_SQLSENTENCE` returns the SQL of whatever part of a query is pushed down — without an error even when the aggregate stays in Denodo, so it does not tell you *whether* the query was delegated; the plan does (`/denodo:views`, `references/delegation.md`). `SELECT execution_plan FROM GET_QUERY_EXECUTION_PLAN() WHERE input_query = '<query, quotes doubled>'` is the plan as text, without running the query — the only plan that comes back through the tool (`DESC QUERYPLAN` and `TRACE` return nothing there); *verified: 9.5.1 (live, 2026-09-30)* |
| Server and logs | `LOGCONTROLLER`, `GET_ACTIVE_LOGGERS`, `WRITELOGINFO`, `WRITELOGERROR`, `GET_PARAMETER`, `WAIT`, `DUAL`, `CHECK_METADATA`, `MAINTAIN_METADATA_TABLES` | `DUAL()` is the one-row table every "SELECT a literal" example uses; `LOGCONTROLLER`, `MAINTAIN_METADATA_TABLES` and `CHECK_METADATA` in fix mode change the whole server — the list above |
| Users and permissions | `GET_USER_ACCOUNTS`, `GET_USERS_WITH_ROLE`, `CATALOG_PERMISSIONS`, `GET_CATALOG_EFFECTIVE_PERMISSIONS`, `PROMPTS_AND_RESTRICTIONS` ² | `GET_USERS_WITH_ROLE`, `CATALOG_PERMISSIONS` and `GET_CATALOG_EFFECTIVE_PERMISSIONS` are the read-backs of `/denodo:security` |
| Web services | `WEBCONTAINER_ELEMENT_STATUS`, `WEBCONTAINER_META_INF`, `GET_CATALOG_METADATA_WS` | publishing web services is not covered by these skills |
| Denodo Assistant | `DENODO_ASSISTANT_*`, `VIEWS_SEMANTIC_SEARCH` ² | `DENODO_ASSISTANT_*` call the configured LLM; nothing works until the Denodo Assistant is set up on the server |

² listed by `LIST PROCEDURES` on a 9.5.1 server, on no page of the documentation — read its
signature with `DESC PROCEDURE` before calling it.

## Documentation

`vdp/vql/stored_procedures/predefined_stored_procedures/<name in lower case>` under
`https://community.denodo.com/docs/html/accessible/9.5/`, one page per procedure, with three
exceptions (`GET_USERS_WITH_ROLE` is `get_users`, `WEBCONTAINER_ELEMENT_STATUS` is
`webcontainer_elements_status`, `GET_GLOBAL_SECURITY_POLICIES_TAGS` is
`get_global_security_policies_tags_procedure`); the index page
`…/predefined_stored_procedures/predefined_stored_procedures` links them all. The
invocation forms are in `vdp/vql/stored_procedures/use_of_stored_procedures/…`.
