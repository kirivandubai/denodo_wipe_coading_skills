# Predefined stored procedures

The server ships them; you never create them. `LIST PROCEDURES` returned **128** on a 9.5.1
stand (2026-09-12) against 101 pages in the VQL Guide — the list on your server is the
authority, not this file and not the documentation.

This page answers two questions: how to call any of them, and which family to look in.

## Calling one

```sql
-- verified: 9.5.1 (стенд, 2026-09-12)
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
-- verified: 9.5.1 (стенд, 2026-09-12)
DESC PROCEDURE USED_BY;                               -- name, type, direction (IN/OUT)
SELECT column_name, column_type, column_is_nullable   -- the same, filterable, plus nullable
  FROM GET_PROCEDURE_COLUMNS() WHERE input_procedure_name = 'USED_BY';
```

Through the execution layer: `vql desc --env <env> USED_BY --type procedure`.

## A call that looks like a read and is not

`GENERATE_STATS`, `CREATE_REMOTE_TABLE`, `DROP_REMOTE_TABLE`, `CLEAN_CACHE_DATABASE`,
`DROP_NONACTIVE_CACHE_TABLES`, `CREATE_SCHEMA_ON_SOURCE`, `DROP_SCHEMA_ON_SOURCE`,
`REMOVE_ICEBERG_VIEW_SNAPSHOTS`, `ROLLBACK_ICEBERG_VIEW_TO_SNAPSHOT`,
`UNLOCK_LOCAL_REPOSITORY` — every one of them changes state, and every one of them is
invoked with `SELECT` or `CALL`.

**The tool will not stop you.** `scripts/denodo` classifies VQL by its leading keyword
(`safety.py`), so `SELECT * FROM DROP_REMOTE_TABLE(…)` comes back with
`destructive: null` and runs on a production profile without `--allow-destructive`. The
same trap the marketplace has with its `POST`s (design spec 6.3) exists here in the VQL
channel. Read what a procedure does before calling it, and treat the state-changing ones
like a `DROP`: show the human first.

## Families

Names are grouped by what they answer, not by the guide's alphabet. Each family lists the
ones worth knowing; `LIST PROCEDURES` has the rest.

| Family | Procedures | Note |
|---|---|---|
| Catalog and metadata | `GET_DATABASES`, `GET_ELEMENTS`, `GET_VIEWS`, `GET_VIEW_COLUMNS`, `GET_PROCEDURE_COLUMNS`, `ELEMENT_METADATA`, `CATALOG_VIEWS`, `CATALOG_ELEMENTS`, `CATALOG_METADATA_VIEWS` | the read-backs the other skills use in their Verify sections |
| Keys and relations | `GET_PRIMARY_KEYS`, `GET_FOREIGN_KEYS`, `GET_EXPORTED_KEYS`, `GET_REFERENTIAL_CONSTRAINTS`, `GET_ASSOCIATIONS`, `GET_VIEW_INDEXES` | `GET_ASSOCIATIONS` is the one `/denodo:views` verifies associations with |
| Dependencies and impact | `USED_BY`, `VIEW_DEPENDENCIES`, `COLUMN_DEPENDENCIES`, `QUERY_DEPENDENCIES`, `GET_PUBLIC_VIEW_DEPENDENCIES` | `USED_BY` walks **down** to the dependants of a view, `VIEW_DEPENDENCIES` **up** to what it stands on. Both take a view; neither takes a procedure |
| Source introspection | `PING_DATA_SOURCE`, `GET_JDBC_DATASOURCE_TABLES`, `LIST_JDBC_DATASOURCE_TABLES`, `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW`, `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW_FROM_QUERY`, `GET_SOURCE_COLUMNS`, `GET_SOURCE_TABLE`, `SOURCE_CHANGES`, `REFRESH_BASE_VIEW` | this is a job, not a lookup — `/denodo:datasources` walks it |
| Tags | `GET_VIEW_TAGS`, `CREATE_TAGS_FROM_VIEW`, `CREATE_TAGS_FROM_COLLIBRA`, `GET_GLOBAL_SECURITY_POLICIES_TAGS` | VDP tags, not marketplace tags (`/denodo:catalog`) |
| Statistics | `GENERATE_STATS`, `GENERATE_STATS_FOR_FIELDS`, `GENERATE_SMART_STATS_FOR_FIELDS`, `GET_STATS_FOR_FIELDS`, `GET_AVAILABLE_STATS_MODES`, `COMPUTE_SOURCE_TABLE_STATS` | outside v1 as objects, but the procedures work; the generating ones write |
| Cache | `CACHE_CONTENT`, `GET_CACHE_TABLE`, `GET_CACHE_COLUMNS`, `GET_CACHE_CONFIGURATION`, `CLEAN_CACHE_DATABASE`, `COMPACT_CACHE`, `DROP_NONACTIVE_CACHE_TABLES` | the last three write |
| MPP, lakehouse, Iceberg | `CREATE_REMOTE_TABLE`, `DROP_REMOTE_TABLE`, `REGISTER_EMBEDDED_MPP`, `DISCOVER_OBJECT_STORAGE_MPP_PROCEDURE`, `GET_ICEBERG_VIEW_SNAPSHOTS`, `ROLLBACK_ICEBERG_VIEW_TO_SNAPSHOT`, `OPTIMIZE_LAKEHOUSE_ACCELERATOR_CACHE_TABLES` | performance territory, outside v1 |
| Query diagnostics | `GET_QUERY_EXECUTION_PLAN`, `GET_DELEGATED_SQLSENTENCE`, `GET_SELECT_NAVIGATIONAL_QUERY`, `GET_SESSIONS`, `GET_SERVER_CONNECTIVITY` | `GET_DELEGATED_SQLSENTENCE` is how you see what was actually pushed down to the source |
| Server and logs | `LOGCONTROLLER`, `GET_ACTIVE_LOGGERS`, `WRITELOGINFO`, `WRITELOGERROR`, `GET_PARAMETER`, `WAIT`, `DUAL`, `CHECK_METADATA`, `MAINTAIN_METADATA_TABLES`, `UNLOCK_LOCAL_REPOSITORY` | `DUAL()` is the one-row table every "SELECT a literal" example uses |
| Users and permissions | `GET_USER_ACCOUNTS`, `GET_USERS_WITH_ROLE`, `CATALOG_PERMISSIONS`, `GET_CATALOG_EFFECTIVE_PERMISSIONS`, `PROMPTS_AND_RESTRICTIONS` | security is outside v1, the read-backs still answer |
| OAuth tokens | `GET_OAUTH20_ACCESS_TOKEN_CLIENT_CREDENTIALS`, `GET_OAUTH20_ACCESS_TOKEN_PASSWORD`, `GET_OAUTH20_ACCESS_TOKEN_CODE`, `GET_OAUTH20_AUTHORIZATION_URL`, `GET_OAUTH10A_ACCESS_TOKEN`, `GET_OAUTH10A_TEMPORARY_CREDENTIALS` | for data sources that authenticate with OAuth |
| Web services | `WEBCONTAINER_ELEMENTS`, `WEBCONTAINER_ELEMENT_STATUS`, `WEBCONTAINER_META_INF`, `GET_CATALOG_METADATA_WS` | publication is outside v1 |
| AI assistant | `DENODO_ASSISTANT_*` (14 of them), `VIEWS_SEMANTIC_SEARCH` | they call a configured LLM; nothing works until the assistant is set up on the server |

## Documentation

`vdp/vql/stored_procedures/predefined_stored_procedures/<name in lower case>` under
`https://community.denodo.com/docs/html/accessible/9.5/`, one page per procedure. The
invocation forms are in `vdp/vql/stored_procedures/use_of_stored_procedures/…`.
