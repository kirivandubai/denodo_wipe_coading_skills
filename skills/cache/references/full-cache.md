# Full cache: what each statement does

Everything marked *live* was measured on 9.5.1 (2026-09-30) against a SQL Server cache
database, on a derived view over delimited files with a view built on top of it. The rest is
the 9.5 documentation, and says so — where the two disagree, the measurement wins.

## The load query

`SELECT * FROM <cached view> [WHERE …] CONTEXT ( … )`

| Parameter | Values | What it does |
|---|---|---|
| `'cache_preload'` | `'true'` | stores the result in the cache. Without it the query is an ordinary read. *live* |
| `'cache_invalidate'` | `'all_rows'` | everything cached is replaced by the result, atomically on a `WITH_STATUS` table: readers see the old rows until the new ones are in. *live* |
| | `'matching_rows'` | only the cached rows matching the `WHERE` are replaced; the rest stay. Without a `WHERE` it is `'all_rows'` (documentation). *live*: 143,526 rows (every row twice) became 132,761 after reloading the 10,765 rows of a slice — both copies of the slice went, one came back |
| | `'matching_pk'` | replaces rows by primary key — an incremental load: Design Studio, not this skill |
| | *(left out)* | the result is **added** to what is cached. A second full load gives every row twice; the declared primary key is not enforced. *live* |
| `'cache_wait_for_load'` | `'true'` | the query ends when the rows are stored, and a failed store is its error. *live*: a load that failed on a too-long text value answered `Error loading cache: There was an error during a batch insertion: String or binary data would be truncated …` |
| | `'false'` | the query ends when the rows are read; a failed store is not reported. *live*: the same failing load answered `ok`, and the cache still held the previous content |
| | *(left out)* | *live*: waits, like `'true'`. The documentation gives the default as `'false'` in the grammar and as `'true'` for a full cache in the text |
| `'cache_return_query_results'` | `'false'` | the result is not sent back: `ok` with no rows. *live* |
| | *(left out)* | every row of the view comes back as the query's result (71,763 rows for a 71,763-row load). *live* |
| `'cache'` | `'off'` | this one query reads the sources, ignoring every cache on the way. Not a load; the comparison for checking one. *live* |

Rules of the load itself:

- It projects every column — `SELECT *`. Fewer columns: `Invalid query to load data in
  cache : All view fields should be projected with cache full mode`. *live*
- It runs over the cached view itself. Over a view built on it, it answers `ok`, returns
  nothing and loads nothing — `CACHE_CONTENT` keeps the old date. *live*
- No `GROUP BY`, `HAVING`, or subquery in the `WHERE` (documentation).
- A failed load keeps what was cached before and the date of that load. *live*
- `'cache_invalidate'` without `'cache_preload'` changes nothing on a full cache. *live*
- Over a view whose cache is off, it answers `ok` and loads nothing: switching the cache on
  afterwards gives 0 rows. A refresh job left running after `CACHE OFF` fails silently. *live*
- A Scheduler cache job builds this query from its options; its *Invalidate* option
  (`cacheInvalidationMode`) defaults to `NONE` for a new job — in the API and in the 9.5.1
  administration tool, against the documentation's *Matching rows* — so every run appends. Set
  `ALL_ROWS` (`/denodo:scheduler`). *live*

## `ALTER VIEW … CACHE` (`ALTER TABLE … CACHE` for a base view)

| Statement | Rows | Cache table | `CACHE_CONTENT.expirationdate` |
|---|---|---|---|
| `CACHE FULL WITH_STATUS` on a view never cached | 0 until a load | created, with a `rowStatus` column | row with `NULL` |
| `CACHE FULL NO_STATUS` | 0 until a load | created without it; **every `'all_rows'` load creates a new table and drops the old one** *live* | |
| `CACHE FULL` (bare) | as one of the two above — the server decides. On 9.5.1 *live* it was `WITH_STATUS`; the documentation names `NO_STATUS` as the default since 9.4 | | |
| `CACHE FULL WITH_STATUS` on a `NO_STATUS` cache | kept | kept, stops moving on loads *live* | kept |
| `CACHE INVALIDATE` (cache on) | 0 | kept; rows marked, deleted by maintenance | `NULL` |
| `CACHE INVALIDATE WHERE <condition>` | the matching rows go | kept | kept (documentation) |
| `CACHE INVALIDATE` (cache off) | accepted, **no effect** — the next `CACHE FULL` serves the old rows *live* | | |
| `CACHE OFF` | the sources | kept, rows still valid *live* — the maintenance-task page says they are marked invalid; the `CACHE_CONTENT` page and the server say otherwise | kept |
| `CACHE FULL` again after `OFF` | **the old rows, at once** — no load *live* | same | the old date |
| `CACHE RECREATE` | 0 | dropped and created again (documentation); *live* same name | **the old date**, although nothing is cached |
| `CACHE INVALIDATE ON CASCADE` | not for a full cache: a full cache cannot be invalidated on cascade, and a cascade from above skips the full caches below (documentation) | | |

The status column is the Design Studio option **Include control columns (legacy)**. The
documentation recommends leaving it out; on 9.5.1, leaving it out breaks every view above the
cache on every full reload *(live)*:

```
view above, queried once → load with 'all_rows' → view above:
Error executing query. … QUERY [CACHE] [ERROR] … Invalid object name '<catalog>.<schema>.C_<VIEW>…'
```

It stayed broken for as long as it was polled (minutes), through further loads, until its own
`CREATE OR REPLACE VIEW` was re-applied — and broke again on the next load. A view created
after the load worked until the load after that. The cached view itself kept answering.

## What survives re-applying a file

| Re-applied | Cache mode | Rows |
|---|---|---|
| `CREATE OR REPLACE VIEW`, unchanged, followed by the `ALTER VIEW … CACHE FULL WITH_STATUS` line | kept | kept *live* |
| the whole file — database, sources, wrappers, base views and the view, all unchanged, with the `ALTER` line | kept | kept, same load date *live* |
| the view with only its `DESCRIPTION` changed | kept | kept, same table and load date *live* |
| the same **without** the `ALTER` line | **off** — `DESC VQL` loses it | kept in the table, served again stale if the cache is switched back on *live* |
| `CREATE OR REPLACE VIEW` with a column added (and the `ALTER` line) | on | **0**: the table is rebuilt empty, `expirationdate` `NULL`, aggregates above return `NULL` *live*. The documentation's default for a schema change is *Recreate schema*; the other options are Design Studio's |
| `CREATE OR REPLACE TABLE` of a base view with `CACHE FULL WITH_STATUS`, unchanged | kept | kept *live* |
| the same with `CACHE OFF` | off | kept *live* |

## Reading the state

| Question | Query |
|---|---|
| Is the cache enabled for the database, in which database do cached queries run, how often maintenance runs | `SELECT status, adapter_database_name, time_to_live, maintenance, maintainer_period FROM GET_CACHE_CONFIGURATION() WHERE database_name = '<db>'` — the row with `database_name` `NULL` is the server's |
| Is the view's cache on, and its table | `SELECT cache_catalog_name, cache_schema_name, cache_table_name FROM GET_CACHE_TABLE('<db>', '<view>')` — when the view's cache is off: `Error executing query. … GET_CACHE_TABLE [STORED PROCEDURE] [ERROR] Received exception with message …` *live* |
| `WITH_STATUS` or `NO_STATUS` | `DESC VQL` names it only when the statement did; otherwise the plan below: `rowStatus = ?` is `WITH_STATUS` *live* |
| The table's columns and their types in the cache database | `SELECT column_name, cache_column_type_name, cache_column_type_size FROM GET_CACHE_COLUMNS() WHERE input_database_name = '<db>' AND input_view_name = '<view>'` — the control column is not listed. *live*: `text` became `VARCHAR(4000)` and `decimal` `NUMERIC(38,20)` on SQL Server |
| Last successful load | `SELECT expirationdate, status FROM CACHE_CONTENT('<db>', '<view>')` — `status` is `preload` for a full cache. No row: never cached |
| Every cached view of a database | `CACHE_CONTENT('<db>', NULL)` — also lists views whose cache is off but whose rows are still there |
| Whether a query reads the cache | `SELECT execution_plan FROM GET_QUERY_EXECUTION_PLAN() WHERE input_query = '<query>'` — the cache's SQL names the `C_<VIEW>…` table and, with the status column, `WHERE rowStatus = ?` |

`CACHE_CONTENT` and `CLEAN_CACHE_DATABASE` need an administrator or a local administrator of
the database; `GET_CACHE_TABLE` needs the Metadata privilege on the view (documentation).

## Freeing the space

- Invalidated rows stay in the table until the **cache maintenance task** deletes them —
  every `maintainer_period` seconds when `maintenance` is on. *live*: after `CACHE
  INVALIDATE`, with the cache still on, `CALL CLEAN_CACHE_DATABASE('<db>', '<view>')`
  returned a row for that view with `deleted_tuples = 71763`, and nothing for any other.
  After `CACHE OFF` the same call returned no row for the view and deleted nothing; the
  rows were deleted once the cache was switched on again and the call repeated. *live*
- `CLEAN_CACHE_DATABASE('<db>')` without a view runs the task over the whole database.
- The table stays after `CACHE OFF`; it is deleted when the view is dropped (documentation).
- `DROP_NONACTIVE_CACHE_TABLES` drops every cache table no cached view references, across
  every database whose cache is in the data sources it is given — by default all of them. A
  global administrator's procedure, even in preview mode.

## Design Studio labels

| Design Studio (view → Options → Materialization) | VQL |
|---|---|
| Virtual | `CACHE OFF` |
| Full | `CACHE FULL` |
| Query results | `CACHE PARTIAL` (with *explicit loads*: `PRELOAD`; *match exact*: `EXACT`) |
| Include control columns (legacy) | `WITH_STATUS` |
| Delete stored results → Invalidate all / partially | `CACHE INVALIDATE [WHERE …]` |
| Store results in cache + Invalidate existing results | `'cache_preload' = 'true'` + `'cache_invalidate'` |

## Outside this skill

| Setting | Where |
|---|---|
| Partial / *Query results* cache, `EXACT`, `PRELOAD` | Design Studio |
| Time to live (`TIMETOLIVEINCACHE`) | Design Studio; a full cache is invalidated by loads, not by time |
| Incremental loads (`'@LAST_REFRESH_DATE'`, `'matching_pk'`, `CACHE FULL INCREMENTAL`) | Design Studio |
| Cache indexes (`DECLARE CACHE INDEX`), custom table name, table templates, schema evolution (`ONSCHEMACHANGE`), batch size | Design Studio |
| Refresh on a schedule | a Scheduler cache job, `/denodo:scheduler`; its load query is this statement. DAG Cache Management jobs: the Scheduler administration tool |
| Enabling the cache for the server or a database, choosing the cache data source | the administrator, Design Studio |
| Remote tables, materialized tables, summaries | not a cache — `/denodo:materialize` |
