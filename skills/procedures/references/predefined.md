# Predefined stored procedures

The server ships them; you never create them. Which ones a server has depends on its
features (the Lakehouse Accelerator, MPP, the AI assistant): `LIST PROCEDURES` on your server is
the authority, not this file and not the documentation.

This page answers two questions: how to call any of them, and which family to look in.

## Calling one

```sql
-- verified: 9.5.1 (live, 2026-09-12)
SELECT column_name, column_vdp_type, column_type
  FROM GET_PROCEDURE_COLUMNS()
 WHERE input_procedure_name = 'GENERATE_STATS';
```

| Rule | Detail |
|---|---|
| Parameters live in `WHERE`, named `input_…` | they are passed into the procedure, not applied to its output |
| The result schema carries the inputs too | `SELECT *` echoes every `input_…` column back; name the columns you want |
| Mandatory parameters announce themselves | `No search methods ready to be run. The following fields are obligatory: input_view_database_name, input_view_name` |
| Positional arguments are not universal | `SELECT status FROM PING_DATA_SOURCE('db', 'JDBC', 'ds')` answers a bare `Error executing query. Total time 0.035 seconds.` — no hint that the form is the problem |
| `CALL` is the other form | positional, `null` for the ones you skip: `CALL USED_BY('sales_analytics', 'customer', null)`. It cannot be joined with anything |
| A procedure can be joined like a view | that is the reason to prefer the `SELECT` form |

Two ways to read a signature, both on the server:

```sql
-- verified: 9.5.1 (live, 2026-09-12)
DESC PROCEDURE USED_BY;                               -- name, type, direction (IN/OUT)
SELECT column_name, column_type, column_is_nullable   -- the same, filterable, plus nullable
  FROM GET_PROCEDURE_COLUMNS() WHERE input_procedure_name = 'USED_BY';
```

Through the execution layer: `vql desc --env dev USED_BY --type procedure`.

## A call that looks like a read and is not

Every one of these changes state, and every one of them is invoked with `SELECT` or
`CALL`. Treat a call like a `DROP`: show the human first.

| Procedure | What it changes |
|---|---|
| `GENERATE_STATS` | overwrites the stored statistics of a view. Deprecated in 9.5, still shipped, still writes; its parameters are the old-style `viewname`, `databasename` — no `input_` prefix — *verified: 9.5.1 (live, 2026-09-17)* |
| `GENERATE_STATS_FOR_FIELDS` | the same for the fields named: gathers and **stores** their statistics. Deprecated; `GET_STATS_FOR_FIELDS` only reads |
| `GENERATE_SMART_STATS_FOR_FIELDS` | the same, from the source's system tables where it can |
| `COMPUTE_SOURCE_TABLE_STATS` | runs the commands that make **the source database** compute the statistics of a base view's table |
| `CREATE_REMOTE_TABLE` | creates a table **in the JDBC source**, fills it with a query's rows, and creates a base view over it; with `replace_remote_table_if_exist = true`, drops whatever table had that name first. A new table where the human named, with `false`, is the agent's own (`/denodo:materialize`) |
| `DROP_REMOTE_TABLE` | drops the base view or summary and the table **in the source** behind it; with cascade, the dependants too (`/denodo:materialize`) |
| `CLEAN_CACHE_DATABASE` | runs the cache maintenance task: deletes expired and invalidated cached rows of a database, or of one view |
| `DROP_NONACTIVE_CACHE_TABLES` | drops cache tables no cached view references any more (its preview mode only lists them, and is flagged all the same) |
| `COMPACT_CACHE` | deletes outdated control rows and the tables of expired temporary tables in the **whole cache data source** — every database that caches there, not only the one named — and can put the server in single-user mode |
| `REFRESH_BASE_VIEW` | rewrites a base view's columns, types, key and descriptions from the source, and with `propagate_views` the views above it |
| `CREATE_TAGS_FROM_VIEW` | with `input_action = 'CREATE'`, creates and assigns VDP tags — and with `input_unassign_tags_mode = 'ALL'` takes every earlier assignment off. `'READ'` only reads, and is flagged all the same |
| `CREATE_TAGS_FROM_COLLIBRA` | the same, from Collibra |
| `LOGCONTROLLER` | the log level of a category **for the whole server**, until it is set back or the server restarts; `DEBUG` and `TRACE` can write query results into the log |
| `MAINTAIN_METADATA_TABLES` | maintenance of the database that stores the server's own metadata |
| `CREATE_SCHEMA_ON_SOURCE` | DDL in the source (Lakehouse Accelerator and PrestoDB data sources) |
| `DROP_SCHEMA_ON_SOURCE` | DDL in the source: removes a schema |
| `REMOVE_ICEBERG_VIEW_SNAPSHOTS` ¹ | expires snapshots of the Iceberg table behind a view; what they held cannot be rolled back to |
| `ROLLBACK_ICEBERG_VIEW_TO_SNAPSHOT` ¹ | replaces the current data of the table with an older snapshot |

¹ documented for 9.5, but absent from a 9.5.1 server without the Lakehouse Accelerator —
`LIST PROCEDURES` decides what your server has.

**The tool stops on these.** `scripts/denodo` matches the procedure name in
`SELECT … FROM name(…)` and `CALL name(…)` against this list and reports
`destructive: "procedure"`; on a profile with `production: true` the call is refused
until a human has confirmed and `--allow-destructive` is passed — the same gate as a
`DROP` (`/denodo:execute`, *Destructive operations*). `DROP_REMOTE_TABLE()` gets no
free pass for being spelled `SELECT`.

The list above is the list the tool checks: it is kept once here and once in the tool's
code (`safety.py`), and a unit test fails when the two differ. Adding a procedure means
adding a row here and a name there, in the same change.

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
| Catalog and metadata | `GET_DATABASES`, `GET_ELEMENTS`, `GET_VIEWS`, `GET_VIEW_COLUMNS`, `GET_PROCEDURE_COLUMNS`, `ELEMENT_METADATA`, `CATALOG_VIEWS`, `CATALOG_ELEMENTS`, `CATALOG_METADATA_VIEWS` | the read-backs the other skills use in their Verify sections. `GET_VIEW_COLUMNS` returns `column_name`, `column_vdp_type`, `column_sql_type`, `column_size`, `column_decimals`, `column_is_primary_key`, `column_is_nullable`, `column_remarks`, `ordinal_position` among others — there is no `column_type` |
| Keys and relations | `GET_PRIMARY_KEYS`, `GET_FOREIGN_KEYS`, `GET_EXPORTED_KEYS`, `GET_REFERENTIAL_CONSTRAINTS`, `GET_ASSOCIATIONS`, `GET_VIEW_INDEXES` | `GET_ASSOCIATIONS` is the one `/denodo:views` verifies associations with |
| Dependencies and impact | `USED_BY`, `VIEW_DEPENDENCIES`, `COLUMN_DEPENDENCIES`, `QUERY_DEPENDENCIES`, `GET_PUBLIC_VIEW_DEPENDENCIES` | `USED_BY` lists the dependants of a view (what is built on it), `VIEW_DEPENDENCIES` what it stands on. Both take a view; neither takes a procedure. `COLUMN_DEPENDENCIES` traces output columns only — a column used only in a join or a filter has no row, so it cannot tell whether a column is safe to drop; `/denodo:views` has the recipe that can |
| Source introspection | `PING_DATA_SOURCE`, `GET_JDBC_DATASOURCE_TABLES`, `LIST_JDBC_DATASOURCE_TABLES`, `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW`, `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW_FROM_QUERY`, `GET_SOURCE_COLUMNS`, `GET_SOURCE_TABLE`, `SOURCE_CHANGES`, `REFRESH_BASE_VIEW` | this is a job, not a lookup — `/denodo:datasources` walks it |
| Tags | `GET_VIEW_TAGS`, `CREATE_TAGS_FROM_VIEW`, `CREATE_TAGS_FROM_COLLIBRA`, `GET_GLOBAL_SECURITY_POLICIES_TAGS` | VDP tags, not marketplace tags (`/denodo:catalog`); the two `CREATE_TAGS_FROM_*` write — the list above |
| Statistics | `GENERATE_STATS`, `GENERATE_STATS_FOR_FIELDS`, `GENERATE_SMART_STATS_FOR_FIELDS`, `GET_STATS_FOR_FIELDS`, `GET_AVAILABLE_STATS_MODES`, `COMPUTE_SOURCE_TABLE_STATS` | the generating ones and `COMPUTE_SOURCE_TABLE_STATS` write — the list above |
| Cache | `CACHE_CONTENT`, `GET_CACHE_TABLE`, `GET_CACHE_COLUMNS`, `GET_CACHE_CONFIGURATION`, `CLEAN_CACHE_DATABASE`, `COMPACT_CACHE`, `DROP_NONACTIVE_CACHE_TABLES` | the last three write — the list above. Reading and clearing the cache of one view is `/denodo:cache` |
| MPP, lakehouse, Iceberg | `CREATE_REMOTE_TABLE`, `DROP_REMOTE_TABLE`, `REGISTER_EMBEDDED_MPP`, `DISCOVER_OBJECT_STORAGE_MPP_PROCEDURE`, `GET_ICEBERG_VIEW_SNAPSHOTS`, `ROLLBACK_ICEBERG_VIEW_TO_SNAPSHOT`, `OPTIMIZE_LAKEHOUSE_ACCELERATOR_CACHE_TABLES` | remote tables and summaries are `/denodo:materialize`; the rest belongs to the Lakehouse Accelerator and MPP, which these skills do not set up |
| Query diagnostics | `GET_QUERY_EXECUTION_PLAN`, `GET_DELEGATED_SQLSENTENCE`, `GET_SELECT_NAVIGATIONAL_QUERY`, `GET_SESSIONS`, `GET_SERVER_CONNECTIVITY` | `GET_DELEGATED_SQLSENTENCE` returns the SQL of whatever part of a query is pushed down — without an error even when the aggregate stays in Denodo, so it does not tell you *whether* the query was delegated; the plan does (`/denodo:views`, `references/delegation.md`). `SELECT execution_plan FROM GET_QUERY_EXECUTION_PLAN() WHERE input_query = '<query, quotes doubled>'` is the plan as text, without running the query — the only plan that comes back through the tool (`DESC QUERYPLAN` and `TRACE` return nothing there); *verified: 9.5.1 (live, 2026-09-30)* |
| Server and logs | `LOGCONTROLLER`, `GET_ACTIVE_LOGGERS`, `WRITELOGINFO`, `WRITELOGERROR`, `GET_PARAMETER`, `WAIT`, `DUAL`, `CHECK_METADATA`, `MAINTAIN_METADATA_TABLES` | `DUAL()` is the one-row table every "SELECT a literal" example uses; `LOGCONTROLLER` and `MAINTAIN_METADATA_TABLES` change the whole server — the list above |
| Users and permissions | `GET_USER_ACCOUNTS`, `GET_USERS_WITH_ROLE`, `CATALOG_PERMISSIONS`, `GET_CATALOG_EFFECTIVE_PERMISSIONS`, `PROMPTS_AND_RESTRICTIONS` | the read-backs of `/denodo:security` |
| OAuth tokens | `GET_OAUTH20_ACCESS_TOKEN_CLIENT_CREDENTIALS`, `GET_OAUTH20_ACCESS_TOKEN_PASSWORD`, `GET_OAUTH20_ACCESS_TOKEN_CODE`, `GET_OAUTH20_AUTHORIZATION_URL`, `GET_OAUTH10A_ACCESS_TOKEN`, `GET_OAUTH10A_TEMPORARY_CREDENTIALS` | for data sources that authenticate with OAuth |
| Web services | `WEBCONTAINER_ELEMENTS`, `WEBCONTAINER_ELEMENT_STATUS`, `WEBCONTAINER_META_INF`, `GET_CATALOG_METADATA_WS` | publishing web services is not covered by these skills |
| AI assistant | `DENODO_ASSISTANT_*`, `VIEWS_SEMANTIC_SEARCH` | they call a configured LLM; nothing works until the assistant is set up on the server |

## Documentation

`vdp/vql/stored_procedures/predefined_stored_procedures/<name in lower case>` under
`https://community.denodo.com/docs/html/accessible/9.5/`, one page per procedure. The
invocation forms are in `vdp/vql/stored_procedures/use_of_stored_procedures/…`.
