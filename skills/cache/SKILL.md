---
name: cache
description: Use when a Denodo 9.5 view should be answered from a stored copy instead of its sources, or when that copy misbehaves — putting a full cache (materialization) on a view or a base view (ALTER VIEW … CACHE FULL), loading or refreshing it with a preload query, caching only some rows, clearing it, switching it off, "the view is slow, cache it", "materialize this view", "give me the statement that loads the cache", a cached view that returns 0 rows, old rows, every row twice, or fails because its cache table is missing ("Invalid object name" on SQL Server). Also for any other cache setting — partial or query-results cache, time to live, incremental loads, cache indexes. Not for building or changing what the view computes — /denodo:views; not for refreshing it on a schedule — /denodo:scheduler; not for a table of its own that other tools read — /denodo:materialize.
---

# Full cache of a view

A view with a **full cache** never reads its sources: every query — the view's own and every
view built on it — reads a table the cache engine keeps in the cache database, and that
table holds exactly what the last load put there. Design Studio calls it *Full
materialization*; `CACHE FULL` in VQL.

**This skill covers the full cache only:** switch it on or off for a view, load it with the
rows the human names, clear it. The other settings — partial (*Query results*) cache, time
to live, incremental loads, cache indexes, a custom table name, schema-evolution options, a
scheduled refresh — are set in Design Studio (view → **Options** → *Materialization*); say
so and stop. A refresh on a schedule is a Scheduler cache job, `/denodo:scheduler`: it runs
the load statement below. Whether the server has a cache at all is the administrator's
setting, not yours.

Building or changing the view itself is `/denodo:views`; base views are
`/denodo:datasources`. A view whose columns call the server's LLM (`CLASSIFY_AI` …) is
cached so that readers stop paying for it, and **every load of it is a paid run of every
row** — the number of rows is the human's (`/denodo:ai`); a column of the vector type
cannot be cached at all. Applying files is `/denodo:execute`. The working loop and the safety
rule are `/denodo:vql`.

**Everything here changes what every reader of the view gets, and does it silently.** The
statements succeed; the view then returns 0 rows, a filtered subset, yesterday's rows or
every row twice, and so does every view built on it. That is why each statement below comes
with a check, and why the human sees the consequences before you apply them.

## Before you touch a cache

1. **Is the cache on for the database?**
   `SELECT status, adapter_database_name, maintenance, maintainer_period FROM GET_CACHE_CONFIGURATION() WHERE database_name = '<db>'`.
   `OFF` → stop: `ALTER VIEW … CACHE FULL` is still accepted, but the view keeps reading its
   sources and every load fails with `Operation not allowed because the cache is disabled or
   not correctly configured` — *verified: 9.5.1 (live, 2026-09-30)*. Enabling it is the
   administrator's job in Design Studio. `adapter_database_name` is the cache data source's
   adapter — the kind of database the cached queries will run in.
2. **Who reads the view?** `SELECT used_by_database_name, used_by_name, depth FROM USED_BY() WHERE input_view_database_name = '<db>' AND input_view_name = '<view>'`
   — every view built on it reads the cache too, and runs its own `GROUP BY` and joins in the
   cache database. (`view_name` in that answer is the view you asked about, not a reader.)
   It lists only the dependants the profile's user may see: when that user is not an
   administrator (`env check` → `vdp.admin`), tell the human the list may be incomplete.
   Consumers outside Denodo (a dashboard, a report) are the human's to name.
3. **What is loaded now, and how?** `SELECT expirationdate FROM CACHE_CONTENT('<db>', '<view>')`:
   for a full cache it is the time of the last successful load; `NULL` means nothing is
   loaded; no row means the cache was never on. `vql desc --env dev --database <db> <view>
   --vql` ends with `ALTER VIEW … CACHE FULL …` when the cache is on, and has no such line
   when it is off. It names `WITH_STATUS` or `NO_STATUS` only if the file did; for a bare
   `CACHE FULL`, the plan tells: `SELECT execution_plan FROM GET_QUERY_EXECUTION_PLAN() WHERE
   input_query = 'SELECT COUNT(*) FROM <view>'` — `rowStatus = ?` in its SQL is `WITH_STATUS`.
   A bare `CACHE FULL` in a file that is not yours is a change to propose, not to make.

## Who applies it

| The view | You apply yourself | Only after the human's yes |
|---|---|---|
| created by you in this session, read by nothing but your own views of this session | on, load, clear, off | — |
| any other view | the reads above | on, load, reload, clear, off |

Whether the view was created in this session, and whether anything else reads it, is what
`vql plan` reports for the file's `ALTER VIEW … CACHE` and load (`own`, `needs_yes`) — not
your memory (`/denodo:vql`).

On a view other people read, switching the cache on empties it until the load finishes, a
load replaces its rows with a snapshot, a `WHERE` in the load becomes its content, and
clearing empties it. The yes is to the statements, shown in this shape:

```
View sales_analytics.iv_household_income — read by household_income_by_band,
household_income (USED_BY), and <consumers the human named>.
1. model/sales.vql:  ALTER VIEW iv_household_income CACHE FULL WITH_STATUS;
   From here until step 2 finishes, the view and everything on it return 0 rows.
2. cache/iv_household_income_load.vql: <the load statement>
   Loads 7,200 rows (the source has 7,200 now). A snapshot: nothing refreshes it
   until this file runs again.
After: its queries run in <adapter_database_name> — text comparisons follow that database.
Apply both?
```

For a view in the right-hand column, when you cannot ask — the human is away, the deadline
is close — the answer is the files written and this message, not the statements applied.
Those files are then ahead of the server: say in the message which runs first, and what
applying one alone does — the view's file with a new `CACHE FULL` line empties the view until
the load runs; the view's file without its old line switches the cache off and leaves the
loaded rows to come back stale. `CACHE OFF` is not an undo: the rows people already read
were empty or partial, and the loaded copy stays behind (Silent failures, 4).

| Rationalization | Reality |
|---|---|
| "They named the view and the mode — that is the yes" | They named the outcome. The yes is to the statements and the zero-row window, after you show them. |
| "It is dev, and it is the team's own database" | Your own objects are the ones you created in this session. The team's view has readers you do not know. |
| "It is reversible with `CACHE OFF`" | The readers already got 0 rows; `OFF` keeps the loaded copy, and the next `CACHE FULL` serves it again, however old. |
| "There is a deadline" | A report that shows 0 rows or a subset is worse than a slow one, and nobody is told. |
| "I'll run a second reload to test it" | Every reload is a write to what people read. Test on the view you are building in this session's file — never on a probe object (`/denodo:vql`). |

## Templates

### Switch it on — in the view's own file

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

ALTER VIEW iv_household_income CACHE FULL WITH_STATUS;
```

- **The line goes into the file that creates the view, right after its `CREATE OR REPLACE
  VIEW`.** Re-applying a `CREATE OR REPLACE VIEW` without it switches the cache off
  silently — `DESC VQL` loses the line, the view reads its sources again. `CREATE VIEW` has
  no `CACHE` clause; `ALTER VIEW` is the only way for a derived view.
- **Always `WITH_STATUS`.** With `NO_STATUS` every load with `'all_rows'` builds a new cache
  table and drops the old one, and every view above that had already been queried keeps
  reading the dropped table — `Invalid object name '<catalog>.<schema>.C_<VIEW>…'` on a SQL
  Server cache database (measured; the documentation says a database that can rename tables
  keeps the name) — until its own `CREATE OR REPLACE VIEW` is re-applied — not after
  minutes, not after the next load. With `WITH_STATUS` the table stays and loads are
  atomic. A bare `CACHE FULL` is `WITH_STATUS` on some servers and `NO_STATUS` on others (the documentation says the latter
  is the default since 9.4) — write it out. *verified: 9.5.1 (live, 2026-09-30)*
- From this statement until a load finishes, the view returns **0 rows** to everyone.
- **A base view** carries it in its own `CREATE OR REPLACE TABLE`: `CACHE FULL WITH_STATUS`
  in place of `CACHE OFF`, keeping `TIMETOLIVEINCACHE DEFAULT` after it
  (`/denodo:datasources`). Re-applying that file with `CACHE OFF` switches the cache off.
  `ALTER VIEW` on a base view fails: `the view : 'bv_x' is a base view`; `ALTER TABLE bv_x
  CACHE FULL WITH_STATUS` works — *verified: 9.5.1 (live, 2026-09-30)*.
- The tool marks the line `destructive: alter` on every apply; on a production profile each
  apply of the file needs the human's yes.

### Load it — a file of its own

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

SELECT * FROM iv_household_income
CONTEXT ('cache_preload' = 'true',
         'cache_invalidate' = 'all_rows',
         'cache_wait_for_load' = 'true',
         'cache_return_query_results' = 'false');
```

The file is what a refresh job runs, and what you run again after the view's columns change.
Keep it out of the view's file: that one is applied on every change, a load only when the
data should move. The tool marks it `destructive: cache`. In a Scheduler *Simple Cache
Management* job the same choice is its *Invalidate* option, `cacheInvalidationMode`:
`ALL_ROWS`. Its default is `NONE`, whatever the documentation says — every scheduled run appends, the first row of the table
below, every night — *verified: 9.5.1 (live, 2026-10-05)* (`/denodo:scheduler`).

Each of the four parameters prevents a silent failure:

| Leave it out | What happens |
|---|---|
| `'cache_invalidate' = 'all_rows'` | the rows are **added** to what is cached: after a second load every row is there twice, primary key or not, and every aggregate on top doubles |
| `'cache_preload' = 'true'` | an ordinary query; nothing is loaded |
| `'cache_wait_for_load' = 'true'` | the default already waits and reports a failed load; `'false'` answers `ok` while the load fails. Write it out: the documentation disagrees with itself about the default |
| `'cache_return_query_results' = 'false'` | every row of the view is streamed back to you as the result |

- `SELECT *` and the cached view itself. Fewer columns fail loudly (`All view fields should
  be projected with cache full mode`). The same statement over **another** view — one built
  on the cached one — answers `ok` and loads nothing.
- A load that fails keeps the previous content and its date: the view goes on serving the
  last good load.
- A `WHERE` here is a decision, never a default — next section.

### Load only some rows

When the human did not name a filter, the load has no `WHERE`. Do not add one to keep the
cache small or to match one dashboard.

When the human names one, the rows the load leaves out are gone from the view **for every
reader** — nothing falls back to the source. Put two options in front of them, with the
numbers:

- **a `WHERE` in the load of this view** — `SELECT * FROM v WHERE <filter> CONTEXT (…)`,
  the same four parameters. The view, and every view on it, then holds `<n>` rows of
  `<total>`; name the dependants from `USED_BY`. The refresh job runs the same statement
  with the same `WHERE` and `'all_rows'`.
- **a new view with that filter, cached itself** — `CREATE OR REPLACE VIEW v_<subset> AS
  SELECT * FROM v WHERE <filter>` (`/denodo:views`), `CACHE FULL WITH_STATUS` on it, and its
  own load with no `WHERE`. The original view stays whole. The right choice whenever the
  view has other readers. Two consequences to name: the consumers who wanted the subset
  move to the new view; and if the original keeps a full cache, the new view is loaded from
  that cache — so the original is either still loaded in full, or switched off (Clear it,
  below) before the cache gets any smaller.

`'cache_invalidate' = 'matching_rows'` replaces only the rows that match the `WHERE` and
keeps the rest: a way to reload one slice, not a way to shrink the cache. Nor does a
smaller load shrink the table at once: the rows it replaced are marked, and stay until they
are cleaned (Clear it, below).

### Clear it, switch it off

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

ALTER VIEW iv_household_income CACHE INVALIDATE;
CALL CLEAN_CACHE_DATABASE('sales_analytics', 'iv_household_income');
ALTER VIEW iv_household_income CACHE OFF;
```

- **This order — each step works only while the cache is on.** `INVALIDATE` empties it: the
  view returns 0 rows and `CACHE_CONTENT.expirationdate` becomes `NULL`; the rows are
  marked, not deleted (on a `NO_STATUS` table they are deleted at once — documentation).
  `CLEAN_CACHE_DATABASE` deletes the marked rows of that one view now (its answer has a
  row for the view with `deleted_tuples`). `OFF` then makes the view read
  its sources. After `OFF`, both are accepted and do nothing: `INVALIDATE` leaves the loaded
  rows valid, to be served again by the next `CACHE FULL`, and `CLEAN_CACHE_DATABASE`
  answers without a row for the view.
- `CLEAN_CACHE_DATABASE` takes **both arguments**: without the view it cleans the whole
  database. Leave it out when space does not matter and `maintenance` is `true`
  (`GET_CACHE_CONFIGURATION`, step 1): the cache maintenance task deletes marked rows every
  `maintainer_period` seconds. With it `false` — the documentation's advice for production —
  only a `CLEAN_CACHE_DATABASE` run does. It is a state-changing procedure for
  administrators (`/denodo:procedures`).
- Only clearing, the cache staying on: `INVALIDATE` alone. The view returns 0 rows until the
  next load.
- Switching off for good: also delete the `ALTER VIEW … CACHE FULL` line from the view's
  file, or its next apply switches the cache back on; and stop the refresh job
  (`/denodo:scheduler`) — a load of a
  view whose cache is off answers `ok` and does nothing, every night. Readers get the
  sources' answers back, with the sources' rules (Silent failures, 9, in reverse).
- The empty table itself stays in the cache database until the view is dropped
  (documentation only). Dropping and re-creating the view removes it, and takes with it
  the views built on it (`CASCADE`), their privileges and tags — the human's decision.
  `DROP_NONACTIVE_CACHE_TABLES` removes such tables for **every database that shares the
  cache data source** — the administrator's call, never yours.

## What you need

| Slot | Where it comes from |
|---|---|
| View and database | the human; the view must exist (`/denodo:views`, `/denodo:datasources`) |
| Whole view or a subset | the human. Not said → the whole view |
| Its readers | `USED_BY()` and the human (dashboards, reports) |
| When it is refreshed | the human; the Scheduler job that does it is `/denodo:scheduler` |
| Rows now | `SELECT COUNT(*) FROM <view> CONTEXT ('cache' = 'off')` — the source, whatever the cache holds |

## Verify

After switching on, loading or clearing — every row of this table, not the first:

| Check | Query | Expect |
|---|---|---|
| The cache is on | `SELECT cache_table_name FROM GET_CACHE_TABLE('<db>', '<view>')` | one row; `GET_CACHE_TABLE [STORED PROCEDURE] [ERROR]` means the view's cache is off — the expected answer after switching off |
| Loaded, and when | `SELECT expirationdate FROM CACHE_CONTENT('<db>', '<view>')` | the time of the load you just ran; `NULL` = nothing loaded |
| Complete | `SELECT COUNT(*) FROM <view>` and `SELECT COUNT(*) FROM <view> CONTEXT ('cache' = 'off')` (with the load's `WHERE`, if it had one) | equal |
| No duplicates | `SELECT COUNT(*) FROM (SELECT <pk> FROM <view> GROUP BY <pk> HAVING COUNT(*) > 1) d` | `0` |
| Readers still answer | `SELECT COUNT(*) FROM <each view from USED_BY>` | a number, not `Invalid object name` |
| Served from the cache | `SELECT execution_plan FROM GET_QUERY_EXECUTION_PLAN() WHERE input_query = 'SELECT COUNT(*) FROM <view>'` | the SQL names a `C_<VIEW>…` table |

`CONTEXT ('cache' = 'off')` reads the sources for one query without touching the cache — the
comparison for every check above, a read allowed on any profile, but only on a view you hold
WRITE on or with the `disable_cache_query` role: otherwise the server ignores it and reads the
cache (documentation), so say the comparison could not be made. `CONTEXT` closes the query:
after `ORDER BY` and `LIMIT`, never before them.

## Silent failures

Each runs without an error — *verified: 9.5.1 (live, 2026-09-30)*.

| You did | What readers get | Instead |
|---|---|---|
| 1. `CACHE FULL`, no load yet | 0 rows, from the view and every view on it | apply the load right after, and say so beforehand |
| 2. a second load without `'cache_invalidate'` | every row twice; the primary key is not enforced | `'all_rows'` in every load, including the job's |
| 3. a load with a `WHERE` | only those rows, for everyone, permanently | "Load only some rows" above |
| 4. `CACHE OFF`, later `CACHE FULL` again | the rows of the old load, immediately, with no load | `INVALIDATE` before `OFF` |
| 5. re-applied the view's file with a column added, removed or retyped | 0 rows, `expirationdate` `NULL`: the cache table was rebuilt empty | run the load file after every such apply |
| 6. re-applied a `CREATE OR REPLACE VIEW` without the `ALTER VIEW … CACHE` line | the sources again, slowly; the loaded rows wait to come back stale | the line stays in the view's file |
| 7. the load over a view built on the cached one | nothing loaded, `ok` | the load names the cached view itself |
| 8. `'cache_wait_for_load' = 'false'` | the old content, while the load reported `ok` | `'true'` |
| 9. switched a view on | its queries, and the filters, `GROUP BY`, `DISTINCT`, joins and `ORDER BY` of every view on it, now run in the cache database with that database's rules: its collation, trailing spaces, `NULL` ordering, numeric scale. On a SQL Server cache database (measured): a case-insensitive collation made `= 'did not fit'` match `'Did not fit'` (rows the sources did not return), trailing spaces stopped counting, `NULL`s sorted first, and `decimal` came back with 20 decimal places. Switching off reverses all of it | before switching: `SELECT UPPER(TRIM(<col>)), COUNT(DISTINCT <col>) FROM <view> GROUP BY UPPER(TRIM(<col>)) HAVING COUNT(DISTINCT <col>) > 1` finds the values a case-insensitive database would merge; after: the readers' filters against `CONTEXT ('cache' = 'off')`. `CAST(<expression> AS decimal(12,2))` around the final value in the view that reads it gives the scale back (an `AVG` over a cast column does not). Tell the human what differs — the adapter's name does not say the collation |
| 10. a load over a view whose cache is off — a refresh job left running | nothing loaded, `ok` | stop the job when you switch the cache off |

## Common mistakes

| You wrote | Server says | Fix |
|---|---|---|
| `ALTER VIEW bv_x CACHE FULL` on a base view | `the view : 'bv_x' is a base view` | `CACHE FULL WITH_STATUS` in its `CREATE OR REPLACE TABLE` |
| `SELECT a, b FROM v CONTEXT ('cache_preload' = 'true', …)` | `All view fields should be projected with cache full mode` | `SELECT *` |
| a load while the database's cache is off | `Operation not allowed because the cache is disabled or not correctly configured` | the administrator enables it; stop |
| a text value longer than the cache column (4000 on SQL Server) | `Error loading cache: …` — on SQL Server, `String or binary data would be truncated` | the previous content is still served; show the human the value |
| a view on a `NO_STATUS` cache, after a load | its cache table is gone — on SQL Server `Invalid object name '<catalog>.<schema>.C_<VIEW>…'` | `ALTER VIEW <cached view> CACHE FULL WITH_STATUS;` (keeps the rows), then re-apply the failing view's file |
| `ALTER VIEW <metric view> CACHE FULL` | `Metric views do not support cache mode` | cache its source views (`/denodo:metrics`), or a summary over them (`/denodo:materialize`) |
| `ALTER VIEW v CACHE RECREATE` to clear | nothing: the view is empty, but `CACHE_CONTENT` keeps the old load's date | `CACHE INVALIDATE` |

## Reference

- `references/full-cache.md` — every `CONTEXT` parameter of a load and what was measured,
  the `ALTER VIEW … CACHE` forms and what each does to the rows and the table, what survives
  re-applying a file, the Design Studio labels, and where each setting outside this skill
  lives.
