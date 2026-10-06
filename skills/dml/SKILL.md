---
name: dml
description: Use when rows have to change in the database behind a Denodo 9.5 view — INSERT, UPDATE or DELETE through a view or base view, INSERT … SELECT from another view or a file, an upsert (ON DUPLICATE KEY UPDATE), RETURNING the generated key, a view an application writes through WITH CHECK OPTION ("correct these records", "set these orders back to open", "load these rows into the table", "delete the test orders", "the app may only create orders for its own region", "give me the new ids"). Also when such a write fails with "Update operation is not allowed", "No update methods ready to be run", "The update condition is non-delegable", "CHECK OPTION failed" or "is not updateable", or a cached view went empty after someone updated rows through it. Not for views that only read (/denodo:views), loading a view's cache (/denodo:cache), or a table made from a query's result (/denodo:materialize).
---

# Writing rows through a view

`INSERT`, `UPDATE` and `DELETE` on a Denodo view change the rows of the table behind it, in
the source database, **at once and for everyone**: the statement is translated into the
source's SQL and sent, and over the tool's connection there is no transaction to roll back.
Everything else in this skill follows from that.

This skill covers: which views take writes and why one does not; the preview and the
before-image that make a write reviewable and undoable; updating, inserting (and getting the
generated key back) and deleting by key; a view an application writes through that accepts
only its own rows; rows copied from another view or a file, including an upsert; and what the
readers of the view see afterwards. Building views that only read is `/denodo:views`; a
view's cache is `/denodo:cache`; base views and data sources are `/denodo:datasources`;
granting `INSERT`, `UPDATE`, `DELETE` on a view is `/denodo:security`; applying files is
`/denodo:execute`. Creating a table in a source, or storing a query's result in one — a
remote table, a summary, a materialized table — is `/denodo:materialize`; so is the refresh of
such a table.

## What a write does

*verified: 9.5.1 (live, 2026-10-02)* — against SQL Server through JDBC base views:

| Fact | Consequence |
|---|---|
| The statement runs in the source as soon as it is sent, one statement at a time | statements before a failed one in the same file stay applied |
| `BEGIN`, `COMMIT`, `ROLLBACK` all answer `ok` — and **`ROLLBACK` undoes nothing** | "try it in a transaction and roll back" changes the data for real. The undo is the before-image you saved (Templates) |
| A write returns no rows; the tool's `affected` is how many rows the source changed | compare it with your preview count before you say anything is done |
| `UPDATE` and `DELETE` through a derived view touch only the rows that view shows — its `WHERE` is added to yours, at every level | a write through the wrong view changes `0` rows without an error |
| An `INSERT` of a row the view would not show, or an `UPDATE` that moves a row out, is accepted unless the view has `WITH CHECK OPTION` — and even then a `NULL` passes | the row lands in the table and is invisible in the view — "A view an application writes through" |
| **A write whose path passes through a view with a full cache empties that cache**: the view, written through directly or through any view above it, returns 0 rows to everyone until its next load. A write below the cache leaves it serving the old rows | write through the base view, and say which cached views now serve old rows |
| `CONTEXT ('impersonate_user' = …)` does not apply to writes: a user with only `EXECUTE` on a view updated it, and a base view they had no privilege on | impersonation proves what a person reads, never what they may write |
| Values are converted by the source: `decimal(12,2)` stores `19.995` as `20.00` | check the value against the column before writing, and compare what reads back |
| A timestamp with a time zone (`NOW()`, `CURRENT_TIMESTAMP`, `TIMESTAMP WITH TIME ZONE '…'`) written to a column without one is stored in the zone of the server process (UTC on the server measured), not the zone your session shows; a `TIMESTAMP '…'` literal and `LOCALTIMESTAMP` are stored as written | `NOW()` landed hours away from the clock the session showed |
| When the source refuses a value (too long, wrong type, a duplicate key), the server cuts its reason short: `… Received exception with message '` and the first characters of the driver's text — from SQL Server, `'com.microsoft.sqlserver.` and nothing more | check lengths, types and keys against the column metadata **before** the write |

## The rule: the human says yes to the statements

**Every `INSERT`, `UPDATE` and `DELETE` waits for the human's yes** — `/denodo:vql`'s safety
table, unchanged: a write lands in a database other people's systems read, and over this
connection it cannot be rolled back. The one exception is an `INSERT` or upsert into a table you
created in this session — a materialized or remote table, its incremental load included
(`/denodo:materialize`); an `UPDATE` or `DELETE` of it waits too, and so does any write whose
query calls an AI function over rows (`/denodo:ai`). The yes is to the exact statements, after you have shown
them with what each will change; "fix these records", "the business signed the file off", "just
get it done" are the task, not the yes.

| You do it yourself | Only after the human's yes |
|---|---|
| reading the view, its definition, its wrapper, its columns and what is built on it | any `INSERT`, `UPDATE`, `DELETE`, `INSERT … SELECT`, upsert — a one-row test write included — but the `INSERT` or upsert into a table you created in this session |
| the preview `SELECT` and the before-image | a second run of a write, a "fix-up" after a surprise, the undo file |
| writing the statements and the undo into files | the load of a cache the write left stale, on a view you did not create in this session (`/denodo:cache`) |
| creating a new view for writers in your project's database — a `CREATE` | the first write through it |

`vql plan` marks every write `needs_yes: true` but one: an `INSERT` or upsert into a
materialized or remote table the session created, with no AI function over rows in its query
(`/denodo:vql`).

Show it in this shape, after the reads and before any write:

```
sales_analytics.bv_orders_db_orders (orders table of the order management database):
cancel 3 orders.
Preview, same WHERE: 3 rows. Before-image: fixes/2026-10-02_cancel_orders_undo.vql.
1. fixes/2026-10-02_cancel_orders.vql
   UPDATE bv_orders_db_orders SET status = 'cancelled'
    WHERE order_id IN (1001, 1002, 1007) AND status = 'open';      -- expects affected = 3
Readers: order_summary has a full cache and keeps showing them as open until its next
load (every day at 06:00); reloading it now is a second statement for your yes.
No transaction: the change is live the moment it runs; the undo file puts the old values back.
Apply 1?
```

When you cannot ask — the human is away, the deadline is close — the answer is the files and
this message, not the write. Say what waiting costs and what applying would have risked; the
change goes live minutes after their yes.

**A write is live when it runs.** "Prices from 18:00" is a file run at 18:00 — by the human, or
by their scheduler — unless the table has a valid-from column the readers honour; nothing here
schedules a statement. Say so instead of writing early.

| Rationalization | Reality |
|---|---|
| "They told me which rows and what to set — that is the yes" | They told you the outcome. The yes comes after the statements, the counts and what the readers will see. |
| "I'll run it inside BEGIN … ROLLBACK to see the count" | `ROLLBACK` answers `ok` and undoes nothing. The preview is a `SELECT` with the same `WHERE`. |
| "It is reversible — I can update it back" | Only from a before-image saved first, and only for what nobody read in between: an invoice sent with a wrong amount stays sent. |
| "One test row, then I'll delete it" | Two writes nobody approved, and a key consumed. A view's rules are tested with values the view rejects — the check fails before any row changes — and those statements are in the message too. |
| "The file was signed off by the business" | The file was. These statements, and the lines of it that do not match the table, were not. |
| "I checked it as the application's user, by impersonation" | Writes ignore impersonation; the write ran with your privileges. |

**Red flags — stop:** a write without a `WHERE`; a `WHERE` that is not on a key or on the
values you previewed; `affected` differs from the preview; a write through a view with a full
cache; `BEGIN` or `ROLLBACK` in your plan; `env.production` is `true`.

## Templates

The example database is `sales_analytics`, with `bv_orders_db_orders` over the `orders` table
of the order management database (`/denodo:datasources`, "Relational database over JDBC"),
generated by introspection. The blocks build on each other, in this order.

### Can this view take the write

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

SELECT column_name, column_vdp_type, column_size, column_decimals, column_is_nullable,
       column_is_primary_key, column_is_autoincrement
FROM GET_VIEW_COLUMNS()
WHERE input_database_name = 'sales_analytics' AND input_view_name = 'bv_orders_db_orders';

SELECT used_by_database_name, used_by_name, depth
FROM USED_BY()
WHERE input_view_database_name = 'sales_analytics' AND input_view_name = 'bv_orders_db_orders';

SELECT name, cache_status
FROM GET_VIEWS()
WHERE input_database_name = 'sales_analytics';
```

- **Write to the view the row belongs to: the base view of the table**, unless the human names
  a view an application writes through. A derived view takes a write only if it reads **one**
  view, without `GROUP BY`, aggregates, joins, unions or `FLATTEN`; its renamed columns are
  written back to the source column, its computed ones never. A base view over a JDBC table
  takes writes; over a file (CSV, JSON, XML), a SQL query or a database procedure it does not.
  Every case, with the error it gives: `references/writable-views.md`.
- `column_size` and `column_decimals` are the source column's (`varchar(40)` → `40`,
  `decimal(12,2)` → `12`, `2`), `column_is_autoincrement` marks the key the database generates
  — **when the base view was generated by introspection**. A hand-written base view, and a
  file's, reports `65536` for every text and no generated key; read the table's definition
  from its owner instead. `input_view_name` is a `LIKE` pattern (`%` and `_` are wildcards,
  documentation); `IN ( … )` answers no rows, without an error. Check every value you will
  write against them — a text's length is `LEN(s)`, spaces counted (delegated to SQL Server,
  `LEN` drops trailing spaces — `/denodo:vql`; `LEN(TRIM(s))` only for padded source text);
  `LENGTH` does not exist: the source's own refusal arrives cut off.
- **A view in `USED_BY` with `cache_status` `3` (full) serves a copy**: after the write it shows
  the old rows until its next load, and a write through it, or through any view above it,
  empties it. A partial cache (`1`, `2`, `4`, `5`) can serve old results until they expire.
  `USED_BY` names readers in every database: run the `GET_VIEWS()` query once per
  `used_by_database_name`. Name them in your message.
- A JDBC wrapper can forbid writes: `DESC VQL WRAPPER JDBC <wrapper> ('includeDependencies' =
  'no', 'dropElements' = 'no')` shows `SOURCECONFIGURATION ( ALLOWDELETE = false … )` or `NOT
  UPDATEABLE` on a field — the options keep the data source, with its encrypted password, out
  of the answer (*verified: 9.5.1 (live, 2026-10-05)*). Nothing to work around — the base
  view's owner decided it.

### Preview, and the before-image

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

SELECT COUNT(*) AS will_change
FROM bv_orders_db_orders
WHERE order_id IN (1001, 1002, 1007) AND status = 'open';

SELECT order_id, status
FROM bv_orders_db_orders
WHERE order_id IN (1001, 1002, 1007) AND status = 'open';
```

- **The same `WHERE`, on the same view, as the write.** `will_change` is the number the write's
  `affected` must equal.
- **The second query is the undo.** Turn its rows into statements that put every changed
  column back, keyed by the primary key, in a file next to the change —
  `UPDATE bv_orders_db_orders SET status = 'open' WHERE order_id = 1001 AND status = 'cancelled';`
  per row for an update, the full `INSERT` for a delete, a `DELETE` by the returned key for an
  insert. Say where it is. It is a write too: it runs on the human's yes — and under a cached
  view the undo leaves the cache as stale as the change did: the load goes with it.
- **Files:** the change, its undo, and a cache load if one follows (`/denodo:cache`, a file of
  its own) — three files, named after the change, each applied whole.
- Never decide from a view with a full cache: read the base view, or add
  `CONTEXT ('cache' = 'off')`.

### Update by key

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

UPDATE bv_orders_db_orders
   SET status = 'cancelled'
 WHERE order_id IN (1001, 1002, 1007) AND status = 'open';
```

- **The key, plus the value you previewed.** `AND status = 'open'` changes only rows still as
  you saw them; someone else's change in between shows as a lower `affected`, not as an
  overwrite. A money column guards the same way: `AND total_amount = 120.50` matched a
  `decimal(12,2)` holding `120.50` — and so did `120.5`; `120.51` matched nothing.
- `affected` must equal `will_change`. Anything else: stop and say so before another write.
- A condition the source cannot evaluate is refused before anything changes — `The update
  condition is non-delegable` (a `REGEXP_LIKE` against SQL Server, for one) — and so is a
  subquery over a view of another data source. Neither is worked around with a broader
  `WHERE`: list the keys (below, "From a file, row by row").

### Insert, and the key the database generated

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

INSERT INTO bv_orders_db_orders (customer_id, order_dt, total_amount, status)
VALUES ('C-1001', TIMESTAMP '2026-10-01 09:30:00', 120.50, 'open')
RETURNING order_id;
```

- **One row per statement when you need the key back.** On SQL Server, `RETURNING` of the
  generated key answers for a single-row `INSERT`. `RETURNING` after a multi-row `VALUES` list
  inserts every row and returns nothing; `RETURNING` of a column with a default returns
  nothing; `RETURNING` of two columns fails before inserting. Other databases answer
  differently (documentation).
- **A failed `INSERT … RETURNING` may have inserted the row.** On a base view without the
  source's type metadata (hand-written, not introspected) it fails with `Cannot parse null
  string` *after* the insert. Read the table before you retry, or you insert it twice.
- **A value that does not fit its column is the human's decision**, not yours to shorten,
  round or drop: put it in the message with the column's size and what fits, and write the
  rows that do fit only if the yes covers them.
- Leave the generated key and the columns with defaults out of the column list; the database
  fills them. A failed insert still consumes a generated key — gaps are normal.
- **Times:** write the value the column means. For a column kept in UTC or any fixed zone,
  convert it yourself and write a `TIMESTAMP '…'` literal: it is stored as written. A
  `TIMESTAMP WITH TIME ZONE '…'`, `NOW()` or `CURRENT_TIMESTAMP` is converted to a zone of the
  server — its process's on the server measured (UTC), not the zone your session shows, which a
  `CAST` in a query also uses — so it fits the column only on a server running in the column's
  zone; read one written row back before relying on it. `LOCALTIMESTAMP` is stored as your
  session's local time.
- Several rows without their keys back: one `VALUES (…), (…), (…)` list; `affected` counts them.

### Delete by key

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

DELETE FROM bv_orders_db_orders
 WHERE order_id IN (1001, 1002, 1007) AND status = 'cancelled';
```

- **Before-image first, with every column** — the undo of a delete is the `INSERT` of those
  rows, and a generated key does not come back as it was.
- **A `DELETE` without `WHERE` empties the table**, with nothing but `affected` to say so.

### A view an application writes through

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW open_order
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Open orders. The order-entry application inserts and amends orders through this view; it can neither close nor cancel one, and every INSERT and UPDATE must send status = ''open''.'
    PRIMARY KEY ( 'order_id' )
    AS SELECT order_id, customer_id, order_dt, total_amount, status
       FROM bv_orders_db_orders
       WHERE status = 'open' AND status IS NOT NULL
    WITH CHECK OPTION;
```

- **`WITH CHECK OPTION` makes the filter a rule for writers.** Without it the view lets the
  application insert a `cancelled` order and close an open one, silently. With it both fail:
  `CHECK OPTION failed: …`, before any row is touched.
- **It checks the values the statement writes, and a `NULL` passes.** A column the statement
  leaves out counts as `NULL`, and `status = 'open'` is neither true nor false for `NULL`: with
  that filter alone, an `INSERT` without `status` and an `UPDATE … SET status = NULL` are
  accepted and the row disappears from the view. `AND status IS NOT NULL` closes both — and
  then **every `UPDATE` must send `status` too**, or it fails. Put that in the description and
  tell the human; the other way is a `NOT NULL` on the source column, its owner's change.
- The check covers the filters of the views below as well (`CASCADED`, the default);
  `WITH LOCAL CHECK OPTION` checks this view's filter alone.
- **Prove the rules with values the view rejects**, after the human's yes to those statements:
  an `INSERT` with `status = 'cancelled'`, an `UPDATE … SET status = 'cancelled' WHERE order_id =
  -1`. Each fails before touching a row; nothing is stored and no key is consumed. Give each
  `INSERT` a second net — a text one character longer than its column, which the source refuses
  too: if the view's check were missing, still nothing is stored, and the error tells which one
  refused. A file of expected refusals runs with `--continue-on-error`; name that in the
  message you ask the yes with. A rule proven by an insert that "should" pass is a real row.
- **Tell the application to treat `affected` other than `1` as a failure**: an `UPDATE` aimed at
  a row outside the view changes nothing and says nothing.
- **A new view for the writers, not a check option on a view others read.** Adding `WITH CHECK
  OPTION` to an existing view changes what its current writers may do — a change to someone
  else's object, for their yes.
- Creating the view is a `CREATE` in your project's database, yours to apply; the first write
  through it is a write. The application writes as its own user, which needs `INSERT` /
  `UPDATE` on this view: `CREATE OR REPLACE ROLE <role> '<description>' GRANT CONNECT ON
  sales_analytics GRANT EXECUTE, INSERT, UPDATE ON sales_analytics.open_order` parses and
  grants exactly that (*verified: 9.5.1 (live, 2026-10-06)*) — a role granting on an existing database, and giving it to anyone, wait
  for the human's yes (`/denodo:security`). Impersonating the application's user proves nothing
  about its writes: they run with your own privileges.

### Rows from another view

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

INSERT INTO bv_orders_db_orders
SELECT customer_id, order_dt, total_amount, status
FROM order_import
WHERE batch_id = 42;

SELECT COUNT(*) AS new_keys
FROM customer_update u
     LEFT OUTER JOIN bv_orders_db_customer c ON c.customer_id = u.customer_id
WHERE c.customer_id IS NULL;

INSERT INTO bv_orders_db_customer ON DUPLICATE KEY ( customer_id ) UPDATE
SELECT customer_id, customer_name, segment
FROM customer_update;
```

- **No column list with a `SELECT`** — `INSERT INTO v (a, b) SELECT …` is a syntax error. The
  `SELECT`'s column names say where each value goes, in any order: alias every expression to
  the target's column name; a name the target does not have fails (`Field name '…' does not
  exist in the view`). Columns left out get the source's default or `NULL`.
- The view you read from may be in another data source — a file included — when the target's
  data source supports data movement (documentation; some need bulk data load enabled);
  `affected` counts the rows inserted.
- **The upsert updates the rows whose key exists and inserts the rest**, with `NULL` in every
  column the `SELECT` does not fill. `new_keys` is how many rows it will insert: a typo in a
  key, or a record not created yet, becomes a new row. Show the number; when the human expects
  `0`, it is a question, not a run.
- **The upsert's key.** On SQL Server, not an identity column: it fails with `Cannot insert
  explicit value for identity column` even when every key exists. On MySQL and PostgreSQL, the
  table's primary key or a unique index (documentation). The target's database must be on the
  documentation's list "Data Sources That Support Merge Data". Without a declared primary key,
  name the key: `ON DUPLICATE KEY ( customer_id )`.
- It never deletes.

**From a file, row by row.** A correction file is usually applied as an `UPDATE` per key:
read the file through its base view, find its keys missing from the table (the `new_keys`
query above — report them, never insert them), check every value against its column (length,
decimals), then write one statement per row into the file. Before asking, prove the file you
wrote says what the source file says: a read that joins the two on the key and counts the rows
whose new value matches — typed statements carry typos. `affected` per statement tells which
rows were not there any more. Lines that cannot go in as written — a key the table does not have,
a value the column would round — stay out of the file and go into the message with what each
needs; whether to apply the rest without them is the human's call, not yours.

## What you need

| Slot | Where it comes from |
|---|---|
| Which rows | the human: keys, or a condition you turn into keys with the preview |
| The new values | the human, or the file they name — checked against the columns |
| The view to write through | the base view of the table, unless the human names a view an application writes through |
| Who reads the view, what is cached on it | `USED_BY`, `GET_VIEWS()` → `cache_status`; consumers outside Denodo — the human |
| The yes | the human, after the message |

## Verify

| Check | How | Expect |
|---|---|---|
| The write changed what you previewed | `affected` of each statement | equal to `will_change` |
| The values read back as written | the preview `SELECT` again, with the new values in the `WHERE` | `will_change` rows, values exactly as written |
| Nothing outside the keys moved | `SELECT <changed column>, COUNT(*) … GROUP BY <changed column>` on the base view, before and after (`COUNT(*)` alone for an insert or a delete) | only the counts the change explains moved |
| Readers | `cache_status` of the views in `USED_BY`; `SELECT expirationdate FROM CACHE_CONTENT('<db>', '<view>')` | a cached reader shows the old rows until its load — say so, or load it after the yes (`/denodo:cache`). A load answers `ok` with no rows; its success is the new `expirationdate` and the same count with `CONTEXT ('cache' = 'off')` |

## Silent failures

Each runs without an error — *verified: 9.5.1 (live, 2026-10-02)*.

| You did | What happens | Instead |
|---|---|---|
| 1. wrote through a view with a full cache, or a view above one | the source changes; the cached view returns **0 rows** to everyone until its next load (`WITH_STATUS` and `NO_STATUS` alike) | write through the base view |
| 2. wrote through the base view under a cached view | the cached view keeps serving the old rows | name it; its load is a statement for the yes |
| 3. `BEGIN` … `ROLLBACK` around a write | everything stays applied | preview with a `SELECT`; undo from the before-image |
| 4. wrote through a filtered view without `WITH CHECK OPTION` | rows the view does not show are inserted, and rows moved out of it | the base view for corrections; `WITH CHECK OPTION` for a view others write through |
| 5. `WITH CHECK OPTION` on `col = 'x'` alone | an `INSERT` without `col`, or `SET col = NULL`, passes; the row vanishes from the view | add `AND col IS NOT NULL`, or `NOT NULL` at the source |
| 6. `UPDATE`/`DELETE` through a filtered view for rows outside its filter | `affected = 0` | the base view, or preview through the same view |
| 7. multi-row `INSERT … RETURNING`, or `RETURNING` a default column (SQL Server) | rows inserted, nothing returned | one row per statement, the generated key only |
| 8. `UPDATE … RETURNING` (SQL Server) | `NULL` instead of the value | you already have the key in the `WHERE` |
| 9. a value with more decimals than the column | rounded by the source (`19.995` → `20.00`) | check `column_decimals`; ask before rounding |
| 10. `NOW()` into a column without a time zone | stored in the server process's zone | write the value the column means |
| 11. upsert with keys the table does not have | new rows with `NULL`s | the `new_keys` count first |
| 12. `DELETE` / `UPDATE` without `WHERE` | every row | a key and the previewed value in every `WHERE` |
| 13. checked a writer's privileges by impersonation | the write ran with your privileges | the writer's own login, by the human |
| 14. a `SELECT DISTINCT` view taking a write (documented as not writable) | the source rows behind it change | write through the base view |

## Common mistakes

| You wrote | Server says | Fix |
|---|---|---|
| a write through a join view | `Error executing sentence: View '<v>'. Update operation is not allowed` | the base view of the table you mean |
| through a `GROUP BY` or `UNION` view | `Error executing sentence: View '<v>'. No update methods ready to be run` | the base view |
| into a file base view, or `INSERT` into a cached view | `View '<v>'. Insert operation is not allowed` (`Delete operation …`) | the base view; a file is changed at its source |
| a computed column | `Error executing sentence: The field '<f>' is not updateable` | the source column it is computed from |
| a field the wrapper marks `NOT UPDATEABLE` | `The field '<f>' is not updateable` / `Cannot insert a value into the non updateable field '<f>'` | leave it out; the base view's owner decided |
| a function the source cannot run, in `WHERE` | `Error executing sentence: The update condition is non-delegable` | a condition on columns and literals, or the keys |
| a subquery over another data source | `The subquery expressions must be delegable to the same datasource of the IDU statement view.` | list the keys |
| a value the view's filter rejects, `WITH CHECK OPTION` | `CHECK OPTION failed: (<field>,eq,[<value>], …)` | a value the view accepts — or the human meant another view |
| `INSERT INTO v (cols) SELECT …` | `Syntax error: Exception parsing query near 'SELECT'` | drop the column list; alias the `SELECT` |
| a `SELECT` column the target lacks | `Field name '<f>' does not exist in the view '<v>'.` | alias it to the target's column |
| an upsert into a view without a primary key | `The view '<v>' has no primary key. You have to use the ON DUPLICATE KEY(field1, field2, ...) clause …` | `ON DUPLICATE KEY ( <key> ) UPDATE` |
| an upsert keyed on an identity column (SQL Server) | `… 'Cannot insert explicit value for identity column in table …` | a key the source does not generate; else update by key |
| `RETURNING a, b` (SQL Server) | `Error in some access … 'The column array is not …` — nothing inserted | `RETURNING <generated key>` |
| `RETURNING` on a hand-written base view | `Error in some access … Cannot parse null string` — **the row was inserted** | read before retrying; regenerate the base view by introspection |
| a value too long, of the wrong type, or a duplicate key | `Error in some access … Received exception with message '` and the start of the driver's text (SQL Server: `'com.microsoft.sqlserver.`) | `column_size`, `column_vdp_type`, the key — `GET_VIEW_COLUMNS()` |

## Reference

- `references/statements.md` — the grammar of `INSERT`, `UPDATE`, `DELETE`, `RETURNING` and
  the upsert, every form as measured, how values land, what `affected` reports, transactions.
- `references/writable-views.md` — which views take which write and the error for each, the
  view's filter on writes, `WITH CHECK OPTION` in full, interface views, the wrapper's write
  switches, writes and the cache, privileges and impersonation.
