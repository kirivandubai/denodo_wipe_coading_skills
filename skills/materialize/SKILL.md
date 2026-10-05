---
name: materialize
description: Use when the result of a Denodo 9.5 query has to be stored as a table, or a slow federated query should run from data placed next to it — a remote table other tools read ("store this view as a table in our warehouse", "a nightly table for the data science team"), a frozen snapshot ("a frozen copy for the auditors"), a summary that answers aggregate queries without them changing ("the dashboard is slow and we can't change its SQL", "precompute the aggregates"), a data movement ("the join between the file and the database is slow"), a materialized table. Also when "The REFRESH command is only valid for Summaries and Remote Tables", a refreshed table came back empty, a summary answers other numbers than the views, DROP_REMOTE_TABLE fails, or a materialized table refuses an UPDATE. Not for the full cache of a view (/denodo:cache), not for changing rows of an existing table (/denodo:dml).
---

# Results stored as tables, and data placed for a query

Four ways to keep the result of a query somewhere, each with its own owner and its own way
of going wrong:

- **Remote table** — a real table in a database of a JDBC data source, created and loaded from
  a query, with a base view over it; `REFRESH` empties it and loads it again. Other tools read
  it directly.
- **Summary** — the same kind of table, plus a promise to the optimizer: any query it can
  answer from the summary is rewritten to read it, silently, for everyone.
- **Data movement** — the small side of a join copied, per query, into a temporary table in
  the data source of the big side, so the join runs there; nothing stays.
- **Materialized table** — a table in the cache database that Denodo owns, filled by
  `INSERT`; it has no source and no lineage.

**All four write to a database outside Denodo's catalog** — a table appears, is emptied or
is replaced in a system other people and programs use. That is what the rule below is about.

This skill covers creating, loading, refreshing and dropping them, and choosing between them.
The full cache of a view is `/denodo:cache`; inserting, updating or deleting rows of a table
that exists is `/denodo:dml`; the views they are built from are `/denodo:views`; a JDBC data
source is `/denodo:datasources`. **Nothing here schedules anything**: a nightly `REFRESH` is a
Denodo Scheduler job (`/denodo:scheduler`) or the team's own scheduler running a file from this
skill.

## What a stored result does

*verified: 9.5.1 (live, 2026-10-02)* — against SQL Server:

| Fact | Consequence |
|---|---|
| `CREATE_REMOTE_TABLE` creates the table, inserts the query's rows, creates a base view with the query as its `DATA_LOAD_QUERY`, and answers three rows — `inserted_rows` on the second | the count you report comes from that row |
| The `CREATE REMOTE TABLE` **command** creates and loads the table and nothing else: no base view, no count, and the table can neither be refreshed (`The REFRESH command is only valid for Summaries and Remote Tables`) nor dropped by `DROP_REMOTE_TABLE` | use the procedure |
| **`REFRESH` empties the table first.** When the load then fails — a source down, a column added under a `SELECT *` load query — the table **stays empty** until the next run that succeeds | everyone reading it sees 0 rows; the refresh job has to alert, and the load query names its columns |
| `replace_remote_table_if_exist = true` and `CREATE OR REPLACE REMOTE TABLE` drop **whatever table has that name** — another team's included — and the readers of the old one keep their catalog status `OK` until a query asks for a column that is gone | a name that is taken is the human's question |
| A remote table has **no lineage**: `USED_BY` of the view it was loaded from does not list it (a summary is listed) | when that view changes, nothing warns that the table's load will fail |
| **A summary answers from its table until the next `REFRESH`** — after rows changed in the source, and after the definition of a view under it changed (a filter added under it: the old count kept coming back) | every rewritten query returns the old figures, and nothing says they are old |
| **A summary whose load failed is empty and still used**: every query the optimizer sends to it answers 0 rows, or `NULL` and `0` for a total, while the sources are fine | after a failed load, `ALTER SUMMARY VIEW … QUERY REWRITE ENABLED = FALSE` at once — the load job checks and does it |
| A summary is used for its own grain, a coarser one, a filter on its columns, `COUNT(*)` from its count; a `COUNT(DISTINCT)` it computes only at exactly its own grain — and **never** for `AVG` or a column it does not hold | prove it with the plan before promising "faster" |
| A query answered from a summary or a remote table runs in **that database's collation**: through a summary on SQL Server `region = 'DELHI'` found `Delhi`, through the views nothing | an answer can change with the place it runs; check the values the filters compare |
| `DROP VIEW` of a remote table's base view or of a summary leaves the table in the database | `DROP_REMOTE_TABLE` drops both |
| `CREATE OR REPLACE MATERIALIZED TABLE` over one with rows **empties it**, without a word; `UPDATE` and `DELETE` are refused | its rows exist nowhere else: plain `CREATE`, run once |
| Types land as the database's own: a text with a known source size keeps it (`nvarchar(2000)`), any other text becomes `varchar(4000)`, a sum of `decimal(7,2)` becomes `numeric(38,20)`, a `timestamptz` a `datetimeoffset` | a longer text fails the load — after the table was created (below) |
| In a `varchar` column, **characters outside the database's code page become `?`** without an error: `Tokyo 東京` landed as `Tokyo ??` | `CAST(<text> AS nvarchar(<n>))` in the query keeps them |
| **A load that fails after the table was created leaves it there, empty, with no base view**; the next call with `replace_remote_table_if_exist = false` then fails on the name | the empty table is yours to replace — it is from this session — and the cause is fixed first |

## Which one

First find out **why** the query is slow, or **who** reads the table, before choosing:
`/denodo:views`, "delegation", shows whether rows travel between data sources.

| The human wants | Use | Not |
|---|---|---|
| the result as a table that another tool reads directly — a model's training job, an ETL, a BI extract — refreshed or frozen | **remote table** | a cache: its table is Denodo's internal copy, renamed and swapped at will |
| a view's own queries answered from a copy, under the same view name | `/denodo:cache` | |
| aggregate queries over a model faster **without changing them** (BI tools generate the SQL), when figures as of the last load are acceptable | **summary** — the views stay as they are, and any query the summary can answer is sped up | a full cache of each view queried: a 0-row window until its first load, and a change to views others read |
| a federated join faster with **current** data — a small side (a file, another system) joined to a big table in a database | **data movement** of the small side into the big side's data source | a summary or a cache, which answer as of their load |
| rows that exist nowhere else — targets, a mapping someone typed — kept in Denodo, with no database of your own to write to | **materialized table** | |
| rows added to, or corrected in, a table that exists | `/denodo:dml` | |

A temporary table (`CREATE TEMPORARY TABLE`) lives for one session and is invisible to anyone
else — not for anything another person reads.

## The rule: new is yours, existing is the human's

A table that did not exist before this session, created by
a statement that cannot overwrite anything, where the human said it should go, is yours to
create. Anything that replaces, empties or drops a table that existed before this session, or
changes the answers of queries you did not write, waits for the human's yes.

| You do it yourself | Only after the human's yes |
|---|---|
| the reads: is the name free, how many rows, what reads the target, the plan | `replace_remote_table_if_exist = true`, `CREATE OR REPLACE REMOTE TABLE` — whatever the name holds |
| a **new** remote table: `CREATE_REMOTE_TABLE` with `replace_remote_table_if_exist = false`, in the data source and schema the human named, under a name the reads show free, after stating the row count | a remote table in a data source or schema the human did not name |
| `REFRESH` of a remote table you created in this session, and `replace_remote_table_if_exist = true` over one — the empty table a failed load left included | `REFRESH` of any table older than this session — it is emptied first |
| a summary created **unloaded** (`DATA_LOAD_IMMEDIATE = FALSE`) and its plan checked: unloaded, it writes nothing and the optimizer never uses it — the data source and schema it names become part of the yes for its load. When the human named none, propose the data source the big table already lives in and its data-load schema, and say it is a proposal | **every load of a summary** — the first `REFRESH`, a `CREATE` that loads, every reload: from that moment it answers queries you did not write |
| data movement in a view you created in this session | data movement added to a view that existed before this session: every query of it then creates a table in the target database |
| a new materialized table in your project's database, and inserting into one you created in this session | `CREATE OR REPLACE MATERIALIZED TABLE` over one that exists — it empties it |
| writing every file | a new load query for a remote table older than this session (the base view re-declared, "Refresh it") — it decides what the next refresh writes |
| — | `DROP_REMOTE_TABLE`, `DROP VIEW` of any of these — your own included |

The tool flags every statement here `table` or `procedure`, the new table included: it cannot
see whose a table is. On a profile marked production that means every one of them waits for
the yes and `--allow-destructive` (`/denodo:execute`).

Report what you did and ask for the rest in this shape:

```
Created dwh.reporting.household_income (ds_dwh) for the pricing team's models:
7,200 rows (inserted_rows), the same as the query; base view bv_dwh_household_income.
The name was free (GET_JDBC_DATASOURCE_TABLES); the file refuses to overwrite.
Columns land as: household_sk bigint, buy_potential varchar(4000), …
tables/household_income_refresh.vql — REFRESH: empties the table, then loads it.
  If the load fails, the table stays EMPTY until the next good run.
  Nothing schedules it: it belongs in a Scheduler job after the warehouse load, one that alerts.
Waiting for your yes: none.
```

When a step needs the yes and you cannot ask — the human is away, the deadline is close —
the answer is the files and this message, not the step. Then the message opens with what is
**not** there and what that costs by the deadline, then what you found, then each file and
whether it waits for the yes. Name the databases whose readers you could not check.

| Rationalization | Reality |
|---|---|
| "Somebody started it and never finished — I'll just finish it" | The table exists, so replacing it is the yes, however abandoned it looks. A table that looks forgotten is often one another team reads. |
| "They said: do whatever you need on the server" | That is the goal. The yes is to the statements, after the human has seen them. |
| "I'll use another name, then it's new" | The readers read the name they were given. A different name is the human's choice, not a way around the question. (A new period of a snapshot is a new table with its own name — that is the design, not this.) |
| "`CREATE OR REPLACE` keeps the file re-appliable" | For a table in a database it drops whatever has that name; for a snapshot it refills the frozen copy from today's data. The procedure with `replace = false` fails instead of overwriting — that is the point. |
| "A summary only makes queries faster; the answers stay the same" | Only until a row or a view under it changes. Then every rewritten query answers the old figures. |
| "If the refresh fails, yesterday's rows stay" | `REFRESH` empties the table first. A failed load leaves it empty. |
| "I'll refresh with a `DELETE` and an `INSERT … SELECT`" | Two writes, the same empty window, and a base view that no longer says where its data comes from. `REFRESH` is the statement. |

**Red flags — stop:** `replace_remote_table_if_exist = true` or `OR REPLACE` in front of
`REMOTE TABLE`, `SUMMARY VIEW` or `MATERIALIZED TABLE`, on a name you did not create in this
session; a table about to be created or loaded in a schema the human did not name;
a `REFRESH` of a table you did not create; a summary about to be loaded; `SELECT *` in a load
query; `env.production` is `true`.

## Templates

The example database is `sales_analytics`; `ds_dwh` is a JDBC data source over the team's
reporting warehouse (`/denodo:datasources`), with tables going to catalog `dwh`, schema
`reporting`. On a database without catalogs the documentation says `null` for the catalog, and
its own example passes `''` — *unverified: 9.5 documentation only*; the same for a database
without schemas. The blocks build on each other, in this order.

### Before you create: is the name free, and what will land

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

SELECT table_name
FROM GET_JDBC_DATASOURCE_TABLES()
WHERE input_database_name = 'sales_analytics' AND input_datasource_name = 'ds_dwh'
  AND input_catalog_name = 'dwh' AND input_schema_name = 'reporting'
  AND UPPER(table_name) = UPPER('household_income');

SELECT COUNT(*) AS will_load
FROM iv_household_income;
```

- **No row means the name is free.** A row means a table of that name exists — someone's,
  whatever its name suggests: stop and ask (the rule above). `UPPER` on both sides because
  Denodo compares the name exactly and SQL Server does not: `HOUSEHOLD_INCOME` is the same
  table there. The answer's columns are `catalog_name`, `schema_name`, `table_name`, `type`.
- Run these reads **before** the create, as reads: inside a file a `SELECT` that finds a row
  stops nothing — what stops the create is `replace_remote_table_if_exist = false`.
- **Who reads it:** the base views over it. `SELECT database_name, name FROM GET_VIEWS() WHERE
  view_type = 0`, then for each candidate `SELECT source_catalog_name, source_schema_name,
  source_table_name FROM GET_SOURCE_TABLE() WHERE input_database_name = '…' AND input_view_name
  = '…'`; a view in another database is another team's. A database you may not read is a
  reader you could not check — say so in the message. A table nobody made with
  `CREATE_REMOTE_TABLE` (no `DATA_LOAD_QUERY` in its base view's `DESC VQL`) cannot be
  refreshed at all: "finishing" it means replacing it.
- `will_load` is the number `inserted_rows` must equal — and the number you tell the human
  before a big load: every row passes through Denodo unless the query runs entirely in the
  target data source.
- The target the human named is the data source **and** the schema. A data source's default
  target (`DATA_LOAD_CONFIGURATION … TARGET_SCHEMA` in its `DESC VQL`) is not a name the human
  gave.

### A remote table

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

SELECT phase, status, error, inserted_rows, "stored procedure result"
FROM CREATE_REMOTE_TABLE()
WHERE remote_table_name = 'household_income'
  AND replace_remote_table_if_exist = false
  AND query = 'SELECT household_sk, income_band_sk, buy_potential, dependents, vehicles, income_lower_bound, income_upper_bound FROM iv_household_income'
  AND datasource_database_name = 'sales_analytics'
  AND datasource_name = 'ds_dwh'
  AND datasource_catalog = 'dwh'
  AND datasource_schema = 'reporting'
  AND base_view_database_name = 'sales_analytics'
  AND base_view_name = 'bv_dwh_household_income'
  AND base_view_folder = '/01 - connectivity'
  AND replace_base_view_if_exist = false;
```

- **Three rows, `status = 'OK'` in each**, `inserted_rows` on phase 2. A name that exists makes
  the call fail with nothing but `[STORED PROCEDURE] [ERROR]` and touches nothing — that bare
  error is the reason the name check comes first.
- **Name every column in `query`.** The load query is stored as written: a `SELECT *` loads
  whatever the view has at the next `REFRESH`, and a column added to the view then fails the
  load — after the table was emptied. Quotes inside it are doubled: `'… WHERE status = ''open'''`.
- The base view gets the procedure's name for its wrapper too, and no primary key:
  `ALTER TABLE bv_dwh_household_income DESCRIPTION = '…'` and `ALTER TABLE … ADD PRIMARY KEY (
  'household_sk' )` — several columns: `( 'a', 'b' )` — keep its `DATA_LOAD_QUERY`: your own
  new object, no yes needed.
- **A text column that may hold characters beyond Latin** (names, addresses, free text): on SQL
  Server (measured) a text without a source size lands as `varchar`, which turns them into `?`
  without an error, and `CAST(<col> AS nvarchar(<n>))` in `query` keeps them. Other databases
  map the types their own way: read what landed ("Verify") before a reader relies on it.
- **A failure after phase 1** (a value the database refuses — on SQL Server, a text over 4000
  characters into the `varchar(4000)` such a text gets) leaves the table created and empty,
  without a base view. Fix the
  cause, then the same call with `replace_remote_table_if_exist = true`: that table is the one
  you just made — check with the name query that nothing else had the name before you.
- **A frozen snapshot is this call, once**: the period in the table name
  (`household_income_2025q3`), the filter in `query`, and a file that says "do not run again,
  never REFRESH" at the top. A second period is a second table. The procedure still beats the
  command here — the count, a base view to compare the copy with, a clean drop — but its base
  view is a `REFRESH` handle and writable: put "frozen, never REFRESH" in its `DESCRIPTION`,
  and tell the human that only the database's owner can make the table read-only (a `DENY`).
- When the query runs entirely in the target data source, the copy happens inside the database
  (measured once: sixty thousand rows in under a second); otherwise every row passes through
  Denodo.

### Refresh it

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

SELECT COUNT(*) AS will_load
FROM iv_household_income;

REFRESH bv_dwh_household_income;

SELECT COUNT(*) AS loaded
FROM bv_dwh_household_income;
```

- **`REFRESH` answers nothing** — no rows, no count. `loaded` must equal `will_load`; `0` after
  a failed run means the table is empty for everyone right now.
- The first `SELECT` proves the sources answer before the table is emptied — it narrows the
  window, it does not close it. Readers who cannot live with an empty table between a failed
  load and the next good one need a full cache with a status column (`/denodo:cache`) instead.
- **Before a refresh of a table you did not just create, read its load query**: `DESC VQL VIEW
  bv_dwh_household_income ('includeDependencies' = 'no')` ends with `DATA_LOAD_QUERY = '…'`.
  Run that query's `SELECT` and compare its columns with the table's (`DESC VIEW` of both):
  any difference, or a `SELECT *` over a view that has changed, and the refresh empties the
  table and fails. Comparing the query's rows with the table's also tells whether a refresh
  would change anything at all.
- **A wrong load query is changed without touching the table**: take the base view's `DESC VQL`
  from `CREATE TABLE` on, make it `CREATE OR REPLACE TABLE` with the new `DATA_LOAD_QUERY`, apply
  it; the next `REFRESH` loads by the new query. `ALTER TABLE … DATA_LOAD_QUERY` is a syntax
  error. The new query must return the table's columns; on a table older than this session both
  steps wait for the yes.
- **Who runs it:** a Denodo Scheduler job (`/denodo:scheduler`) or the human's own scheduler,
  after the sources are loaded, with an alert on failure — the file and the time go into the
  message. A job that refreshes a table older than this session is that `REFRESH`, every night:
  the same yes.

### A summary — created unloaded, proved by the plan, then loaded

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE SUMMARY VIEW s_household_band
    INTO ds_dwh
    CATALOG = 'dwh'
    SCHEMA = 'reporting'
    RELATIONNAME = 's_household_band'
    IF RELATION EXISTS ERROR
    DATA_LOAD_IMMEDIATE = FALSE
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Households per income band and buy potential, precomputed for aggregate queries over iv_household_income. As of its last REFRESH.'
    AS SELECT income_band_sk, buy_potential,
              COUNT(*) AS households, SUM(dependents) AS dependents, SUM(vehicles) AS vehicles
       FROM iv_household_income
       GROUP BY income_band_sk, buy_potential;

SELECT execution_plan
FROM GET_QUERY_EXECUTION_PLAN()
WHERE input_query = 'SELECT income_band_sk, COUNT(*) AS households FROM iv_household_income GROUP BY income_band_sk CONTEXT (''consider_all_summaries'' = ''on'')';
```

- **Unloaded, it changes no answer**: no table yet, and the optimizer ignores it until its first
  load. That is what lets you prove it before asking. The plan of each query the human cares
  about must show `acceleratedWithSummaries = [sales_analytics.s_household_band]` and
  `optimizationsApplied = [Summary Acceleration]`; plan the dashboards' own queries, not one you
  wrote to match. `consider_all_summaries` makes the planner consider the unloaded summary;
  never *run* a query with it.
- **What it can answer:** sums and counts at its grain or coarser, filters on its columns,
  `COUNT(*)` from its count — so keep `COUNT(*)` in it. A `COUNT(DISTINCT …)` only if the
  summary computes it, and only for a query grouped by exactly the summary's columns — a
  distinct count does not add up, and the optimizer does not try. Not `AVG`, even with a sum
  and a count in it; not a column or a filter it does not hold. Build it over the views the
  queries name; see `references/summaries.md`.
- **`OR REPLACE` with `IF RELATION EXISTS ERROR` and `DATA_LOAD_IMMEDIATE = FALSE`** is
  re-appliable while the summary is unloaded and refuses once a table of that name exists —
  anyone's, the summary's own after its load included. A change to a loaded summary is `… IF
  RELATION EXISTS REPLACE` and a load, both for the human's yes.
- Summaries are created by a server administrator only, on the Enterprise Plus bundle
  (*documentation*).

**Load it — on the human's yes**, and check it against the views themselves:

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

REFRESH s_household_band;

SELECT income_band_sk, COUNT(*) AS households
FROM iv_household_income
GROUP BY income_band_sk
ORDER BY income_band_sk;

SELECT income_band_sk, COUNT(*) AS households
FROM iv_household_income
GROUP BY income_band_sk
ORDER BY income_band_sk
CONTEXT ('summary_rewrite' = 'off');
```

- **The two answers must be equal, row for row.** The first comes from the summary, the second
  from the sources. Run the same pair after every change upstream: a difference is a stale
  summary, and every rewritten query in the meantime returned it. Sums from the summary come
  back with many decimals (`numeric(38,20)`) — compare values, not text.
- **A failed `REFRESH` leaves the summary empty and in use**: every query sent to it answers
  0 rows, a total `NULL` and `0`, while the sources are fine. The job that loads it checks the
  pair above after each run and, when the load failed, runs `ALTER SUMMARY VIEW
  s_household_band QUERY REWRITE ENABLED = FALSE` at once — slow and right instead of fast and
  empty — and alerts. Put that file next to the load file.
- **Its filters run in the summary's database.** On a case-insensitive database a filter that
  matched nothing through the views matches through the summary (`'DELHI'` found `Delhi`).
  Check that no two values the queries filter on differ only by case or trailing spaces.
- A summary goes stale the moment its sources or the views under it change, and nothing marks
  it: it needs a scheduled `REFRESH` like a remote table, and the dashboards show figures as of
  that load. Say both in the message. `ALTER SUMMARY VIEW s_household_band QUERY REWRITE
  ENABLED = FALSE` takes a stale one out of every plan at once — an `ALTER`, for the yes.

### Data movement for a federated join

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW household_band_detail
    FOLDER = '/02 - integration'
    DESCRIPTION = 'Households from the warehouse with the bounds of their income band from the band file. Each query copies the band file into the warehouse and joins there.'
    AS SELECT h.household_sk, h.buy_potential, h.dependents,
              ib.ib_lower_bound AS band_lower_bound, ib.ib_upper_bound AS band_upper_bound
       FROM bv_dwh_household_income AS h
            INNER JOIN bv_income_band AS ib ON h.income_band_sk = ib.ib_income_band_sk
    CONTEXT ( DATAMOVEMENTPLAN = bv_income_band : JDBC ds_dwh );

SELECT execution_plan
FROM GET_QUERY_EXECUTION_PLAN()
WHERE input_query = 'SELECT buy_potential, COUNT(*) AS households FROM household_band_detail GROUP BY buy_potential';
```

- **The small side moves to the big side's data source**: `bv_income_band` (a file) into
  `ds_dwh`, where `bv_dwh_household_income` lives. Moved anywhere else — the cache data source,
  a third database — the plan says `Data Movement` and the join still runs in Denodo.
- The plan must show `optimizationsApplied = [Data Movement …]` and a `JDBC ROUTE` on `ds_dwh`
  whose `SQLSentence` joins a `t_bv_income_band_<id>` table: that is the copy. It is dropped
  when the query ends.
- **Every query of the view creates and drops that table**, in the schema the data source's
  data-load configuration names (`DATA_LOAD_CONFIGURATION … TARGET_SCHEMA` in its `DESC VQL`),
  so its account needs `CREATE TABLE` there, and every query pays for moving the small side: a
  side of millions of rows is not small. Answers stay current — nothing is stored between
  queries.
- The plan goes into the view's own `CONTEXT`, which `CREATE OR REPLACE VIEW` keeps; a query can
  set or switch one off for itself: `CONTEXT ( DATAMOVEMENTPLAN = bv_income_band : OFF )`.

### A materialized table

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

CREATE MATERIALIZED TABLE income_band_target (
        income_band_sk : int,
        target_households : int,
        set_by : text
    )
    FOLDER = '/02 - integration'
    CONSTRAINT 'pk_income_band_target' PRIMARY KEY ( 'income_band_sk' );

INSERT INTO income_band_target (income_band_sk, target_households, set_by)
VALUES (1, 400, 'planning 2025'), (2, 380, 'planning 2025'), (3, 360, 'planning 2025');

SELECT COUNT(*) AS loaded
FROM income_band_target;
```

- **Its rows exist nowhere else.** Never `CREATE OR REPLACE` it: over a filled table that
  empties it, silently. The file runs once; later rows are `INSERT`s in files of their own.
- **Only `INSERT`**: `Update on materialized tables is not allowed`, `Delete on … is not
  allowed`. A correction is a new table, or `DROP VIEW` and a new one — the human's yes.
- The primary key is not enforced: a second `INSERT` of the same key is accepted. Check
  `SELECT key, COUNT(*) … HAVING COUNT(*) > 1` after each load.
- It lives in the cache database (`C_INCOME_BAND_TARGET<digits>`); the cache has to be
  configured for the database (*documentation*). `SELECT … INTO <new name> FROM …` creates one
  from a query; it refuses a name that exists.
- **A `decimal` kept twenty decimals whatever was declared**, with the cache database on SQL
  Server (measured) — `DECIMAL(12,2)` in the SQL form of the column list stored `10.555` as
  `10.55500000000000000000`. Round in the `INSERT`.

### Drop — on the human's yes

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

SELECT used_by_name, depth
FROM USED_BY()
WHERE input_view_database_name = 'sales_analytics' AND input_view_name = 'bv_dwh_household_income';

SELECT "stored procedure result"
FROM DROP_REMOTE_TABLE()
WHERE base_view_database_name = 'sales_analytics' AND base_view_name = 's_household_band'
  AND drop_base_view_on_cascade = false;

SELECT "stored procedure result"
FROM DROP_REMOTE_TABLE()
WHERE base_view_database_name = 'sales_analytics' AND base_view_name = 'bv_dwh_household_income'
  AND drop_base_view_on_cascade = false;
```

- `DROP_REMOTE_TABLE` drops the table in the database and the base view or summary over it.
  With `drop_base_view_on_cascade = false` it refuses while anything reads the view — the
  `USED_BY` above says what — and drops nothing. It refuses a base view the procedure did not
  create, too: a table made by the command or by someone's DDL is dropped by its owner.
- `DROP VIEW` instead leaves the table in the database, orphaned.

## What you need

| Slot | Where it comes from |
|---|---|
| Which of the four | the "Which one" table, after the plan or the readers say why |
| The target data source and schema | **the human** — a data source in the project or the team's shared one; never a default you found |
| The table name | the human, or the warehouse's conventions; the summary's `s_` prefix (`/denodo:vql`) |
| The query | the view the readers need, every column named |
| How often it is refreshed, and by what | the human; a Scheduler job is `/denodo:scheduler`; the file is yours |
| The yes | the human, for everything in the right-hand column of the rule |

## Verify

| Check | How | Expect |
|---|---|---|
| The table holds the query | `inserted_rows`, then `COUNT(*)` of the base view, against `will_load` | equal |
| The types landed as meant | `SELECT creation_vql FROM GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW() WHERE data_source_name = 'ds_dwh' AND catalog_name = 'dwh' AND schema_name = 'reporting' AND table_name = 'household_income' AND base_view_name = 'type_check'` — it only generates text and creates nothing; with `folder = '/'` it fails; read `sourcetypename`, `sourcetypesize` | text widths, `nvarchar` where text is not Latin, the decimals the readers expect |
| A loaded summary answers like the views | the pair in "Load it", after every load | equal; a failed load → rewrite off at once |
| A refresh worked | `COUNT(*)` after `REFRESH` | the new count, not `0` |
| A summary answers what the views answer | the same query with and without `CONTEXT ('summary_rewrite' = 'off')` | equal |
| A summary is used | the plan of the readers' query | `acceleratedWithSummaries = [<db>.<summary>]` |
| A data movement does its job | the plan | one `SQLSentence` in the big side's data source joining `t_<view>_<id>` |
| Nothing old was touched | `GET_JDBC_DATASOURCE_TABLES` of the target schema before and after | one new table, nothing gone |

## Silent failures

Each runs without an error — *verified: 9.5.1 (live, 2026-10-02)*; rows 12, 13 and 15 with the
target database on SQL Server — another database maps types and compares text its own way.

| You did | What happens | Instead |
|---|---|---|
| 1. `REFRESH` while a source was down | the table is emptied and stays empty | check the sources first; the job alerts; readers who cannot see 0 rows need a cache |
| 2. `SELECT *` in the load query, then a column was added to the view | the next `REFRESH` fails after emptying the table | name every column |
| 3. `replace_remote_table_if_exist = true` / `OR REPLACE` on a taken name | another team's table replaced; their views stay `OK` until a query reads a column that is gone | check the name; a taken one is the human's |
| 4. changed the view a remote table is loaded from | no warning — `USED_BY` does not see the table; the next `REFRESH` fails after emptying it | search `DESC VQL DATABASE <db>` for the view's name before changing it |
| 5. loaded a summary, then the sources or the views under it changed | rewritten queries answer the old figures | `REFRESH` on a schedule; compare with `summary_rewrite` off |
| 6. a summary for `AVG` queries, or for `COUNT(DISTINCT)` at another grain than its own | not used; nothing is faster | the plan first; sums and counts in it, a distinct count only at the queried grain |
| 7. data movement into a data source the big side is not in | the plan says `Data Movement`, the join still runs in Denodo | the big side's data source |
| 8. `DROP VIEW` of a remote table's base view or a summary | the table stays in the database | `DROP_REMOTE_TABLE` |
| 9. `CREATE OR REPLACE MATERIALIZED TABLE` over one with rows | 0 rows | plain `CREATE`, once |
| 10. two `INSERT`s of the same key into a materialized table | both kept | check duplicates after each load |
| 11. the `CREATE REMOTE TABLE` command | no base view, no count; later neither `REFRESH` nor `DROP_REMOTE_TABLE` works on it | the procedure |
| 12. a computed or file text into a remote table | it lands as `varchar(4000)`; a longer value fails the load and leaves an empty table | measure `MAX(LEN(…))` first; `CAST(… AS varchar(8000))` in the query makes the column that wide |
| 13. non-Latin text into a `varchar` column | `?` for every character the code page lacks | `CAST(… AS nvarchar(n))` in the query |
| 14. a summary's `REFRESH` failed | the summary is empty and still used: 0 rows, `NULL` totals for every query sent to it | rewrite off at once (`ALTER SUMMARY VIEW … QUERY REWRITE ENABLED = FALSE`), then reload |
| 15. a filter answered through a summary or a remote table | compared in that database's collation — case and trailing spaces may stop counting | check the values; say where the query runs |

## Common mistakes

| You wrote | Server says | Fix |
|---|---|---|
| `CREATE_REMOTE_TABLE` on a name that exists | `CREATE_REMOTE_TABLE [STORED PROCEDURE] [ERROR]`, no reason | the name check; a taken name is the human's |
| the command on a name that exists | `Remote table "dwh"."reporting".household_income already exists` | the same |
| `REFRESH` of a base view the procedure did not create | `The REFRESH command is only valid for Summaries and Remote Tables` | create it with the procedure; a table someone else made is theirs to refresh |
| `REFRESH` after the view gained a column | `Error executing data movement from view _p__… to source ds_dwh` — **table now empty** | name the columns in the load query; recreate it (the human's yes) |
| `DROP_REMOTE_TABLE` on a hand-made base view, or with readers and `cascade = false` | `DROP_REMOTE_TABLE [STORED PROCEDURE] [ERROR]`, no reason; nothing dropped | `USED_BY`; the table's owner |
| `CREATE OR REPLACE SUMMARY VIEW` over an existing one with `IF RELATION EXISTS ERROR` | `Remote table exists. Use clause IF RELATION EXISTS REPLACE to allow its replacement and create the summary.` | a change to a summary is the human's yes, with `REPLACE` |
| `UPDATE` / `DELETE` on a materialized table | `Update on materialized tables is not allowed` / `Delete on materialized tables is not allowed` | a new table, or `INSERT` only |
| `SELECT … INTO` an existing name | `error creating table: invalid view name: already exists` | a new name |
| `DROP MATERIALIZED TABLE x` | `Syntax error: Exception parsing query near 'MATERIALIZED'` | `DROP VIEW x` |
| `CAST(x AS double)` / `CAST(x AS int)` in a load query | `Syntax error … near ')'` | `double precision`, `integer` (`/denodo:vql`, dialect) |

## Reference

- `references/remote-tables.md` — the procedure and the command in full (options, templates,
  indexes), every result and status, types per Denodo type as measured, `REFRESH`, finding the
  readers of a table, materialized and temporary tables.
- `references/summaries.md` — the `CREATE` and `ALTER SUMMARY VIEW` grammar, which queries are
  rewritten (measured), the plan lines, staleness, incremental loads (documentation), the
  switches per server, database and query, and data movement in full.
