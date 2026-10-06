# Dependencies in full

Everything `/denodo:views` leaves out of "Before a column changes": the three dependency
procedures, what each one cannot see, how to read a field's lineage, and where any answer
from the server stops.

## The three procedures

| Procedure | Walks | Takes | One row per |
|---|---|---|---|
| `USED_BY()` | down: the views built on this one, at every depth and in every database | `input_view_database_name`, `input_view_name`, optional `input_max_depth` | a view and one of its dependants: `view_database_name`, `view_name` (the view at that depth), `used_by_database_name`, `used_by_name`, `depth` — there is no type column; `depth = 1` names this view in its own definition |
| `VIEW_DEPENDENCIES()` | the other way: what this view stands on, down to the data sources | `input_view_database_name`, `input_view_name` | an element it stands on, repeated at each depth it is reached |
| `COLUMN_DEPENDENCIES()` | the same way, per output column | the two above, plus optional `input_column_name` | an output column and one element its value comes from |

Rules common to all three — *verified: 9.5.1 (live, 2026-09-30)*:

- **The names are exact and case-sensitive.** A name in the wrong case, a pattern (`%`,
  `_`) or a view that does not exist is an error that names nothing — `… USED_BY [STORED
  PROCEDURE] [ERROR] Received exception with` — not an empty result. Take the name as
  `GET_ELEMENTS()` prints it. The catalog procedures are the opposite: in `GET_ELEMENTS()`,
  `GET_VIEWS()` and `GET_VIEW_COLUMNS()` the `input_…name` is a `LIKE` pattern, so
  `input_name = 'store%'` lists every view whose name starts with `store`, and `_` matches any
  one character.
- `USED_BY()` lists dependants in **other databases** too, in `used_by_database_name`.
- **It lists views only.** Associations are `GET_ASSOCIATIONS()`; web services and anything
  outside the catalog — a report, a client, a scheduled job — are not listed anywhere here.
  A metric view is a view and is listed.
- **What you may see decides what you get.** Checked as a user who may read only the top
  view, by impersonation (`CONTEXT ('impersonate_user' = …)`, `/denodo:security`) —
  *verified: 9.5.1 (live, 2026-10-01)*: `COLUMN_DEPENDENCIES()` of that view answered one
  row per column with `dependency_name` empty and `dependency_type = 'No Privileges'`, where
  an administrator got seven named rows down to the data source; `USED_BY()` of a view the
  user may not read failed with a bare `Error executing query`. That a dependant the user
  may not see is left out of `USED_BY()` is documentation only. Neither says it narrowed
  the answer: when the profile's user is not an administrator (`env check` → `vdp.admin`),
  an empty or nameless answer means "nothing this user can see" — say so to the human.

## `COLUMN_DEPENDENCIES()` sees output columns only

Measured over one view `p_sales` and six dependants, each using its `customer_sk` a
different way, before and after `CREATE OR REPLACE VIEW p_sales` without that column, and
over a metric view built on an association that maps the column — *verified: 9.5.1 (live,
2026-09-30)*:

| The dependant uses the column | A row naming it in `COLUMN_DEPENDENCIES()` | After the column is gone |
|---|---|---|
| in its `SELECT` list | yes | `INVALID` |
| inside an expression with other columns | yes: `dependency_column_name = 'customer_sk,store_sk'`, the expression in `expression` | `INVALID` |
| only in a join's `ON` | **none** | `INVALID` |
| only in `WHERE` | **none** | `INVALID` |
| only in `GROUP BY` | **none** | `INVALID` |
| in an interface view's field list | yes | `INVALID` |
| in an association's `ADD MAPPING` | not a view — `GET_ASSOCIATIONS()` | `valid = false` |
| in a metric view's dimension or metric | — | `INVALID`, and every query fails with `View without search methods:` |
| not at all: a metric view that names that association in `ASSOCIATIONS ( … )` | its own rows only | **`OK`**; a metric grouped or filtered by a dimension reached through the association fails with `Error applying metric transformation.`; metrics alone, and that dimension without a metric, still answer |
| in a published REST web service's `FIELDS` | — | the field is dropped from the service's definition, and restoring the column does not bring it back |
| not at all: a view above one of the `INVALID` ones | its own rows only | **`OK`**, and every `SELECT` fails (`Error calculating the join condition for copying the join view …`) |

So **no row is not "unused"**, and "no `INVALID` view" is not "nothing broke". What finds
every use is the definition of each direct dependant: `DESC VQL VIEW <dependant>
('includeDependencies' = 'no', 'dropElements' = 'no')`, searched for the column. Restoring the
column restores every view and association in the table; the web service has to be given its
field back by hand.

A `SELECT` from a view left `INVALID` answers `View without search methods:` — the text
`/denodo:procedures` explains as a missing parameter. Here it means the view underneath lost
a column; `GET_VIEWS(… invalid only)` names the view.

For a whole database at once, `DESC VQL DATABASE <db>` is one text holding every
definition — views, associations, web services — and a text search of it is the most
complete answer the server gives, and the only one that shows a published web service
exposing the view (`RESOURCES ( VIEW <view> FIELDS ( … ) )`). It is large — thousands of
lines on a real database — so save it to a file and search it for the view's name.

## Where a field comes from

```sql
-- verified: 9.5.1 (live, 2026-10-06)
SELECT column_name, dependency_database_name, dependency_name, dependency_column_name,
       dependency_type, expression, depth
  FROM COLUMN_DEPENDENCIES()
 WHERE input_view_database_name = 'sales_analytics'
   AND input_view_name = 'household_income_by_band'
   AND input_column_name = 'avg_vehicles'
   AND view_name = 'household_income_by_band';
```

Without the last filter the answer repeats the chain from the point of view of every view on
the way, each under its own `view_name`. Filtered to the view you asked about, it still names
every element down to the data source — one row per element, nearest first by `depth`:

| Column | Reads |
|---|---|
| `depth` | 1 for what the view names in its own definition, 2 for the next element down, and so on. It is counted from the row's `view_name`, so rows of different views are not comparable |
| `dependency_type` | `Select`, `Inner Any Any Join`, `Interface`, … for views; `Base View`; `Jdbc Datasource`, `Df Datasource`, … for the source. An `Interface` row is a contract: the row one `depth` further is its implementation |
| `dependency_column_name` | the column in that element — a comma-separated list when the value is an expression over several; `*` for `COUNT(*)`; empty on a data source row |
| `expression` | not empty where the value is computed: `round(avg(vehicles), 2)` on the row of the view it is computed from |
| `private_view` (on the other rows) | `true` for `_<view>__<id>_j__<id>`: an internal step of a join of three or more views, created by the server. Read through it |

`expression` shows *that* a value is computed, not the whole computation: the grouping, the
join and the filters of the view are in its definition, `DESC VQL VIEW <view>
('includeDependencies' = 'no', 'dropElements' = 'no')`. Read it when the question is "how is
this number made", not only "where does it come from".

The last hop is a `Base View` row: its `dependency_name` is the base view, its
`dependency_column_name` the base view's column. The table and column in the source database
behind a JDBC base view:

```sql
-- verified: 9.5.1 (live, 2026-10-06)
SELECT column_name, source_catalog_name, source_schema_name, source_table_name, source_column_name
  FROM GET_SOURCE_COLUMNS()
 WHERE input_database_name = '<db>' AND input_view_name = '<jdbc base view>';
```

It takes JDBC base views only — a derived view or a file source is an error; for a file,
`vql desc … <base view> --vql` shows the path. The data source row names the connection; its
`DESC VQL` carries the password ciphertext, so quote the URL from it, not the statement.

## Other ways to ask

- `VIEW_DEPENDENCIES()` answers "what does this view stand on" without columns. It repeats an
  element once per path it is reached by; `SELECT DISTINCT dependency_name, dependency_type`
  is the list.
- `GET_PUBLIC_VIEW_DEPENDENCIES()` gives only the nearest public views and data sources a
  view is built on, skipping the server's private join steps —
  *unverified: 9.5 documentation only*. The dependencies of a view's cache are
  `/denodo:cache`'s; web services are not covered by these skills.
