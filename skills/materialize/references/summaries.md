# Summaries and data movement

Grammar from the VQL Guide 9.5 ("Summaries", "Data Movement") and the Administration Guide
("Smart Query Acceleration Using Summaries", "Managing Summaries", "Summary Rewrite
Optimization", "Data Movement"); behaviour marked *measured* was observed on 9.5.1 against SQL
Server, 2026-10-02. Everything else is documentation only.

## CREATE SUMMARY VIEW

```
CREATE [ OR REPLACE ] SUMMARY VIEW <name>
    [ ID = '<id>' ]
    INTO <data source>                      -- JDBC; database-qualified works: admin.ds
    [ CATALOG = '<catalog>' ]               -- at least one of CATALOG and SCHEMA
    [ SCHEMA = '<schema>' ]
    [ RELATIONNAME = '<table>' ]            -- default: the summary's name
    [ IF RELATION EXISTS { REPLACE | ERROR } ]   -- default ERROR
    [ DATA_LOAD_IMMEDIATE = { TRUE | FALSE } ]   -- default TRUE
    [ FOLDER = '<folder>' ]
    [ DESCRIPTION = '<text>' ]
    [ <primary key> ]
    [ QUERY REWRITE ENABLED = { TRUE | FALSE } ] -- default TRUE
    [ CUSTOM LOAD QUERY '<select>' ]
    [ CREATE_TABLE_TEMPLATE ( '<template>' [ DEFAULT ( … ) ] ) ]
    [ OPTIONS ( … ) ]                        -- as CREATE REMOTE TABLE
    AS [ WITH … ] <select> [ ORDER BY … ] [ OFFSET … ] [ LIMIT … ]
    [ CONTEXT ( … ) ] [ TRACE ]
```

- Only server administrators create, change and drop summaries; the feature is off outside the
  Enterprise Plus bundle; the server needs *Data Movement* and *Automatic simplification of
  queries* enabled (documentation).
- *Measured*: it answers no rows. `DESC VQL` shows it as a JDBC wrapper plus `CREATE SUMMARY
  VIEW <name> ( <typed fields> ) … AS SELECT <aliases> FROM ( <your query> )` — the server wraps
  the query in an outer `SELECT` that aliases every column (alias them yourself and it reads as
  written). `GET_VIEWS()` reports `view_type = 4`; no column there says whether it is loaded.
- *Measured*: `DATA_LOAD_IMMEDIATE = FALSE` creates no table, and the optimizer does not use the
  summary until a `REFRESH` succeeds.
- *Measured*: `IF RELATION EXISTS ERROR` refuses a table of that name even when it is the
  summary's own: re-applying `CREATE OR REPLACE SUMMARY VIEW … IF RELATION EXISTS ERROR` over a
  loaded summary fails with `Remote table exists. Use clause IF RELATION EXISTS REPLACE to allow
  its replacement and create the summary.` With `REPLACE` and `DATA_LOAD_IMMEDIATE = FALSE` the
  table was kept and the summary stayed in use. `REPLACE` with a load drops and recreates the
  table — and any table of that name.

## ALTER SUMMARY VIEW

```
ALTER SUMMARY VIEW <name>
    [ RENAME TO <new name> ]
    [ DROP PRIMARY KEY ] [ ADD PRIMARY KEY ( … ) ]
    [ DESCRIPTION = '<text>' ]
    [ QUERY REWRITE ENABLED = { TRUE | FALSE } ]
    [ CUSTOM LOAD QUERY '<select>' ]
    [ CREATE_TABLE_TEMPLATE ( … ) ]
    [ OPTIONS ( … ) ]
```

*Measured*: `QUERY REWRITE ENABLED = FALSE` takes the summary out of every plan at once — the way
to stop a stale one without dropping it. Changing the query is `CREATE OR REPLACE`.

## Which queries are rewritten (measured)

Over a summary `SELECT channel, order_year, order_month, SUM(amount) AS amount, COUNT(*) AS
lines FROM orders GROUP BY channel, order_year, order_month`:

| Query over `orders` | Rewritten |
|---|---|
| the same grouping and sums | yes |
| a coarser grouping (`GROUP BY channel`), or a grand total | yes — `sum( t0.amount)` over the summary |
| `COUNT(*)` | yes — `sum( t0.lines)` |
| a filter on a summary column (`WHERE order_month = 3`) | yes |
| `AVG(amount)` | **no**, although the sum and the count are there |
| `COUNT(DISTINCT order_number)`, the summary holding none | **no** |
| `COUNT(DISTINCT …)` that the summary computes, the query grouped by exactly its columns | yes — the column is read as it is |
| the same distinct count grouped by fewer columns (`channel` alone, or `channel, order_month`) | **no** — the query goes to the views, and the answer stays right |
| a column or a filter the summary does not hold (`country`, `customer_name = …`) | **no** |

The documentation adds: build it over the top views the queries name — over a stack of
projections and selections the optimizer matches the views the query joins and aggregates —
always include `COUNT(*)`, avoid
`HAVING`, declare primary keys and referential constraints of the views it joins, gather
statistics when cost-based optimization is on.

**The plan says it** (*measured*): `GET_QUERY_EXECUTION_PLAN()` of the query shows
`acceleratedWithSummaries = [<db>.<summary>]`, `optimizationsApplied = [Summary Acceleration]`,
`summaryAccess = true`, and a `JDBC ROUTE` whose `SQLSentence` reads the summary's table. An
unloaded summary is considered only with `CONTEXT ('consider_all_summaries' = 'on')` in the
planned query.

**Switches** (documentation): server-wide in *Server configuration → Queries optimization*;
per database `CREATE OR REPLACE DATABASE … SUMMARY REWRITE { ON | OFF | DEFAULT }` (`/denodo:catalog`);
per query `CONTEXT ('summary_rewrite' = 'off')` (*measured*: the query then reads the views).

## Staleness (measured)

A summary is a copy as of its last load, and nothing marks it old:

- a row inserted into the fact table under it: the rewritten query answered the old sum and
  count, the same query with `summary_rewrite` off the new ones, one row more;
- the view under it re-declared with an extra column, and then with a new filter
  (`WHERE amount > 100`): still rewritten, still the old figures — more rows than the view now
  returns. The documentation says a summary is invalidated when the definition of a view under
  it changes; on 9.5.1 neither change did it;
- `REFRESH <summary>` brought both back in line.

Sums read from the summary's table come back as `numeric(38,20)`: `1234.50000000000000000000`.

**A failed load** (*measured*): with the file under a view of the summary gone, `REFRESH` failed
with the view's error — and the summary stayed in every plan, now empty: the queries it answers
returned no rows, a grand total `NULL` and a count `0`, also after the file was back. `REFRESH`
again, or `QUERY REWRITE ENABLED = FALSE`, ends it. A loading job checks the result and switches
rewriting off when the load failed.

**Collation** (*measured*): a query answered from the summary runs in its database — on SQL Server
a filter `= 'DELHI'` matched rows holding `Delhi`, and the same query with `summary_rewrite` off
matched nothing.

## Loading and incremental loads

`REFRESH <summary>` truncates the table and runs the summary's query (*measured*). A `CUSTOM LOAD
QUERY` turns a refresh into an incremental load: a query that returns only the new rows,
filtered on a timestamp against `LAST_DATE_REFRESH` — `CUSTOM LOAD QUERY 'SELECT <the summary's
columns, named> FROM sales WHERE sale_date >= LAST_DATE_REFRESH'`.
*unverified: 9.5 documentation only* It is not the cache's
`@LAST_REFRESH_DATE`. Rows can also be added with `INSERT` into the summary (documentation).
After a promotion to another environment a summary is unused until its first `REFRESH`.

## Dropping

`DROP_REMOTE_TABLE` with the summary's name drops the summary and its table (*measured*, also
when the table never existed). `DROP VIEW <summary>` keeps the table (documentation, and the same
as for a remote table's base view, measured).

## Data movement

The small side of a join or set operation is copied into a table in the data source of the
other side for one query, so the operation runs there.

```
CREATE OR REPLACE VIEW <view> … AS SELECT …
    CONTEXT ( DATAMOVEMENTPLAN = <view to move> : JDBC <target data source>
                                 [ <another view> : JDBC <target> ]* );

SELECT … FROM <view> CONTEXT ( DATAMOVEMENTPLAN = <view to move> : OFF );    -- one query, off

ALTER VIEW <view> DATAMOVEMENTPLAN = { <view to move>: () (JDBC <target>) };   -- unverified: 9.5 documentation only
```

- *Measured*: the plan is kept in the view's `CONTEXT` and printed by `DESC VQL`. A query plans as
  `optimizationsApplied = [Data Movement …]`, a `DATA_MOVEMENT PLAN (` node, and a `JDBC ROUTE` on
  the target whose `SQLSentence` joins `<schema>.t_<moved view>_<uuid>`; the table was gone after
  the query. A data source given database-qualified (`admin.ds`) works.
- *Measured*: moved into a data source the other side is not in, the plan still says `Data
  Movement` and the join stays in Denodo. Measured once, moving a dimension of a few thousand rows
  next to a fact of a million made an aggregate with `COUNT(DISTINCT)` about five times faster.
- The target is a JDBC data source the view already uses, or the cache data source, with an
  adapter the cache engine supports and a connection URI that names the database
  (documentation). The tables go to its data-load target schema; its account needs to create
  and drop tables there.
- CONTEXT options of the query (documentation): `'data_movement_bulk_load' = 'off'` — plain
  `INSERT`s instead of the bulk API; `'data_movement_clean_resources' = 'false'` — keep the
  table and files (they pile up; for debugging only); `'data_movement_clean_resources_on_error'
  = 'false'` — keep them only when it fails.
- Not movable: a view with a subquery in its `WHERE`; the views under an interface view, from a
  view over the interface (documentation).
- A database can forbid the optimizer to move its data elsewhere (*Optimizer data movement
  control*: all, none, same database, listed databases) — set by the administrator in Design
  Studio (documentation).
