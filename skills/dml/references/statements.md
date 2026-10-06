# The write statements in full

Everything `/denodo:dml` leaves out of its templates: the grammar of each statement, the forms
that were measured and what they returned, `RETURNING` per form, `INSERT … SELECT` and the
upsert, how values land, what the tool reports, and transactions.

*verified: 9.5.1 (live, 2026-10-02)* unless marked — against SQL Server 2022 through a JDBC base
view. A source of another kind translates the same statement into its own SQL; where it
answers differently is documentation only.

## `INSERT`

```sql
INSERT INTO <view> ( <field> [, <field> ]* ) VALUES ( <value> [, <value> ]* ) [, ( … ) ]*
    [ RETURNING <field> [, <field> ]* ];

INSERT INTO <view> SET <field> = <value> [, <field> = <value> ]* [ RETURNING … ];

INSERT INTO <view> <select>;

INSERT INTO <view> ON DUPLICATE KEY [ ( <field> [, <field> ]* ) ] UPDATE <select>;
```

| Form | Measured |
|---|---|
| one row, column list, `VALUES` | `affected = 1` |
| several rows in one `VALUES` list | `affected` = the rows |
| `SET` form | as `VALUES` |
| `VALUES` without a column list | every column in the view's order (documentation) |
| a column the list leaves out | the source's default, or `NULL` |
| `INSERT INTO v (a, b) SELECT …` | `Syntax error: Exception parsing query near 'SELECT'` — no column list with a `SELECT` |
| `INSERT INTO v SELECT 'S1' AS status, 'C9' AS customer_id …` | each value lands in the column its alias names — matched **by name**, in any order |
| a `SELECT` column the target does not have | `Field name 'cust' does not exist in the view 'v'.` |
| `INSERT INTO v SELECT …` over a view of the **same** data source | `affected` = the rows (delegated as one `INSERT … SELECT`, documentation) |
| `INSERT INTO v SELECT …` over a file or another data source | `affected` = the rows (read by Denodo, then inserted) |

## `UPDATE`

```sql
UPDATE <view> SET <field> = <value or expression> [, … ] [ WHERE <condition> ] [ RETURNING … ];
UPDATE <view> SET ( <field> [, … ] ) = ( <value> [, … ] ) [ WHERE … ];
UPDATE <view> SET ( <field> [, … ] ) = ( <select returning one row> ) [ WHERE … ];
```

| Form | Measured |
|---|---|
| `SET col = 'literal' WHERE <key>` | `affected` = rows matched |
| `SET col = col + 1`, `CONCAT('x', other_col)` | evaluated by the source |
| `SET col = FORMATDATE(…)` | translated into the source's own function, which failed (`format(…)`) — try an expression new to you on one row first |
| a `WHERE` the source cannot evaluate (`REGEXP_LIKE` on SQL Server) | `Error executing sentence: The update condition is non-delegable` — nothing changed |
| a `WHERE … IN (SELECT …)` over a view of the same data source | `affected` as expected |
| the same over a file or another data source | `Error executing sentence: The subquery expressions must be delegable to the same datasource of the IDU statement view.` |
| no `WHERE` | every row |

## `DELETE`

```sql
DELETE FROM <view> [ WHERE <condition> ];
```

The `WHERE` follows the `UPDATE` rules above (non-delegable condition, subquery from another
source). No `WHERE`: every row of the table. No `RETURNING`.

## `RETURNING`

The documentation: "for views whose data comes from a JDBC database"; Denodo passes the fields
to the database, which may refuse or ignore them. Measured on SQL Server:

| Statement | Result |
|---|---|
| one-row `INSERT … RETURNING <generated key>` | the new key |
| `INSERT … SET … RETURNING <generated key>` | the new key |
| several rows in `VALUES` with `RETURNING <key>` | rows inserted, **no result set** |
| `RETURNING` of a column with a default (`created_at`) | row inserted, **no result set** |
| `RETURNING <key>, <other>` | `Error in some access … 'The column array is not …` — **nothing inserted** |
| `UPDATE … WHERE <key> RETURNING <key>` | row updated, **`NULL`** returned |
| `UPDATE … RETURNING` of two columns | the same error, nothing updated |
| one-row `INSERT … RETURNING <key>` through a derived view over the base view (a filtered one `WITH CHECK OPTION`) | the new key |
| `INSERT … RETURNING <key>` on a base view written by hand, without the source's type metadata (`sourcetypeid`) | `Error in some access … Error executing view: Cannot parse null string` — **after the row was inserted**; two retries made two more rows. Regenerated with the metadata, the same statement returned the key |

On another database each line can differ; when a key matters, check the returned value by
reading the row back.

## The upsert

`INSERT INTO <view> ON DUPLICATE KEY [ ( <key fields> ) ] UPDATE <select>`:

- rows whose key exists are updated with the `SELECT`'s values, the others inserted —
  `affected` counts both;
- the key is the view's primary key, or the fields in parentheses; with neither: `The view
  '<v>' has no primary key. You have to use the ON DUPLICATE KEY(field1, field2, ...) clause to
  specify the fields used to detect the duplicate rows.`;
- delegated to the source as a `MERGE` when the `SELECT` runs there; otherwise through a
  temporary table in the cache database (documentation);
- `'@LAST_REFRESH_DATE'` in the `SELECT`'s `WHERE` is replaced by the time of the last
  successful insert into the view (documentation) — a load's time, not the data's, and in a
  Scheduler job `@` starts a variable: an incremental load reads its watermark from the table
  (`/denodo:materialize`, `references/incremental.md`);
- **it never deletes**, and a key that is not in the table becomes a new row;
- **keyed on an identity column it fails** on SQL Server — `Cannot insert explicit value for
  identity column in table …` — even when every key in the `SELECT` exists already. Keyed on a
  natural key (a code the table does not generate) it updated the existing rows and inserted
  the new ones.

## How values land

| You write | Stored (SQL Server) |
|---|---|
| `10.555` or `'10.555'` into `decimal(12,2)` | `10.56` |
| text longer than `varchar(n)` | refused: `… Received exception with message 'com.microsoft.sqlserver.` (cut) |
| `'abc'` into a number | refused, same cut message |
| `''` | `''` — not `NULL` |
| `NULL` | `NULL` |
| `TIMESTAMP '2026-01-15 10:00:00'`, `'2026-01-15 10:00:00'` into `datetime2` | `10:00:00` |
| `DATE '2026-01-15'` into `datetime2` | `00:00:00` |
| `TIMESTAMP WITH TIME ZONE '2026-01-15 10:00:00 +02:00'` | `08:00:00` — converted to UTC |
| `NOW()`, `CURRENT_TIMESTAMP`, `CAST(NOW() AS timestamp)` | the UTC time, while the session shows the same moment at `-07:00` |
| `LOCALTIMESTAMP` | the session's local time |

The source's refusal is cut by the server at a fixed length, and `TRACE` does not bring the
rest back: the reason is in the column's metadata (`GET_VIEW_COLUMNS()` → `column_size`,
`column_vdp_type`, `column_decimals`, `column_is_nullable`, the primary key), so check there
before writing.

## What the tool reports

`vql run` gives every statement `affected`: the number of rows the source reports changed by
an `INSERT`, `UPDATE` or `DELETE` (`0` when nothing matched), `null` for a read, a `CREATE` or
a failed statement — and `null` for a write whose `RETURNING` answered: there the returned rows
are the trace, and a read-back confirms them. Nothing else says what a write did.

## Transactions

Over the tool's connection (the server's ODBC interface) `BEGIN`, `COMMIT`, `ROLLBACK` are
accepted and ignored — measured: an `UPDATE` between `BEGIN` and `ROLLBACK` stayed applied.
Enabling them is a server-wide setting that changes every ODBC client
(`SET 'com.denodo.vdb.vdbinterface.server.odbc.ignoreTransactions' = 'false'`, an
administrator's decision, documentation). Even then Virtual DataPort runs them as distributed
transactions with two-phase commit, with a 30-minute limit and rolled back after 30 idle
seconds (documentation). So a change of several statements is not atomic here: order them so
that stopping after any one leaves the data consistent, and keep the undo file.
