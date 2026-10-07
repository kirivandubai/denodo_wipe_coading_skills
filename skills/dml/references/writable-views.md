# Which views take a write, and what the view does to it

Everything `/denodo:dml` leaves out of "Can this view take the write": the rules by view type
with the error each case gives, how the view's own filter shapes a write, `WITH CHECK OPTION`,
interface views, the wrapper's switches, and privileges.

## By view type

*verified: 9.5.1 (live, 2026-10-02)* unless marked — a JDBC base view over a SQL Server table,
and derived views over it:

| The view | `INSERT` / `UPDATE` / `DELETE` | Server says |
|---|---|---|
| base view over a JDBC table | all three | — |
| base view over a file — CSV (DF), JSON, XML | none | `View '<v>'. Insert operation is not allowed` (`Delete operation …`, `Update operation …`) |
| base view over a SQL query, a database procedure; a Denodo stored procedure anywhere below | none (documentation) | — |
| derived view over **one** view: a selection and a projection, renamed columns | all three, renamed columns written to the source column | — |
| … with a computed column | the other columns; the computed one never | `Error executing sentence: The field '<f>' is not updateable` |
| … with a filter | rows the filter shows; see "The view's filter" | — |
| join view | none | `Error executing sentence: View '<v>'. Update operation is not allowed` |
| `GROUP BY` / aggregate view, `UNION` view | none | `Error executing sentence: View '<v>'. No update methods ready to be run` |
| `SELECT DISTINCT` view | **accepted** — the documentation lists it as not writable; an `UPDATE` changed the source row | — |
| `FLATTEN` view | none (documentation) | — |
| partitioned union, when a write's `WHERE` leaves one branch and that branch is writable | `UPDATE`, `DELETE` (documentation; needs query simplification on) | — |
| view with parameters | `UPDATE` / `DELETE` whose `WHERE` gives every parameter (documentation) | — |
| interface view | whatever its implementation takes, through the implementation's filter | — |
| view with a full cache | `UPDATE`, `DELETE` — and the cache is emptied; `INSERT` refused | `View '<v>'. Insert operation is not allowed` |
| a derived view over any view above that does not take writes | none | — |

Salesforce, MongoDB, ODBC and custom-wrapper base views can take writes too
(documentation); this skill's templates are JDBC only.

## The view's filter on writes

Measured with query simplification on (the default; `GET_DATABASES()` → `query_simplification`):

| The write | Without `WITH CHECK OPTION` | With it |
|---|---|---|
| `UPDATE` / `DELETE` of rows the view does not show | `affected = 0` — the view's `WHERE` is added | the same |
| `UPDATE` that moves a row out of the view (`SET status = 'shipped'` through `WHERE status = 'open'`) | accepted | `Error executing sentence: CHECK OPTION failed: (status,eq,['open'], <i18n>)` |
| the same `UPDATE` with a `WHERE` no row matches | `affected = 0` | **the same failure** — the check runs on the statement's values, before any row is read |
| `INSERT` of a row the view would not show | accepted, invisible | `CHECK OPTION failed: …` |
| `INSERT` that leaves the filtered column out | accepted, `NULL` stored, invisible | **accepted, `NULL` stored, invisible** |
| `UPDATE … SET status = NULL` | accepted, the row leaves the view | **accepted, the row leaves the view** |
| a view on a view on the base view | every level's filter is added to `UPDATE` / `DELETE` | the filters below are checked too, unless `LOCAL` |

The documentation says the server treats every derived view as `WITH CHECK OPTION` when query
simplification is on; measured, that holds for which rows `UPDATE` and `DELETE` reach, not for
what an `INSERT` or a `SET` may write.

## `WITH CHECK OPTION`

```sql
CREATE OR REPLACE VIEW <name> AS SELECT … FROM <one view> WHERE <filter>
    [ WITH [ CASCADED | LOCAL ] CHECK OPTION ];
```

- The check reads only the statement's values, and an unknown condition passes (the table
  above). `AND status IS NOT NULL` closes it and fails every `UPDATE` whose `SET` does not name
  `status`: `CHECK OPTION failed: ((status,eq,['open'], <i18n>) AND (status,isnotnull,[], <i18n>))`.
- Without a keyword it is `CASCADED`: an `INSERT` through a view over `WHERE status = 'open'`,
  with its own filter on another column, was refused for `status = 'closed'`. `LOCAL` checked
  only its own filter and let the row in.
- Placed after the `SELECT` and its `ORDER BY` / `OFFSET` / `LIMIT`, before the view's
  `CONTEXT` clause (documentation).

## The wrapper's switches

A JDBC wrapper can forbid each kind of write, and mark single fields read-only:

```sql
CREATE OR REPLACE WRAPPER JDBC <name> …
    OUTPUTSCHEMA ( …, customer_code = 'customer_code' :'java.lang.String' (OPT) SORTABLE NOT UPDATEABLE, … )
    SOURCECONFIGURATION ( ALLOWDELETE = false )
    …;
```

| Switch | A write that hits it |
|---|---|
| `ALLOWDELETE = false` | `Error executing sentence: View '<v>'. Delete operation is not allowed` |
| `ALLOWINSERT = false`, `ALLOWUPDATE = false` | the same for `Insert` / `Update` (documentation) |
| `NOT UPDATEABLE` on a field | `UPDATE`: `The field '<f>' is not updateable`; `INSERT`: `Cannot insert a value into the non updateable field '<f>'` |

`DEFAULT` (or no `SOURCECONFIGURATION`) takes a default that depends on the source
(documentation); over SQL Server it allowed all three. `DESC VQL WRAPPER JDBC <wrapper>
('includeDependencies' = 'no', 'dropElements' = 'no')` shows what is set, without the data
source and its encrypted password (*verified: 9.5.1 (live, 2026-10-05)*); the wrapper's name
is in the base view's `WRAPPER ( jdbc … )`. Changing a wrapper someone else owns to make a
write pass is not a fix — it is a change to their object, for their yes.

## Privileges and impersonation

Writing needs `INSERT`, `UPDATE` or `DELETE` on the view, besides `CONNECT` on its database;
`EXECUTE` alone reads. Row restrictions defined for a role apply to its `UPDATE` and `DELETE`
too — the rows it may not see are not changed (documentation). Granting is
`/denodo:security`. An administrator writes through every restriction.

**Impersonation does not reach writes** (`impersonate_user` and `impersonate_roles` alike): what
a writer may write is checked only by that writer's own login; leave that check to the human
(`/denodo:security`, **Check it as the people it is for**).
