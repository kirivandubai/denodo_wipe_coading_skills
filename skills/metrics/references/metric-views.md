# Metric views — grammar, joins, limits and consumers

Everything below was checked on 9.5.1 unless a line says *documentation*. The public grammar
is in the VQL Guide, "Defining a Metric View"; the query rules in the Administration Guide,
"Creating Metric Views". Both are partial and disagree with each other in places noted here.

## `CREATE METRIC VIEW`

```
CREATE [ OR REPLACE ] METRIC VIEW <name>
    [ FOLDER = '<folder>' ]
    [ DESCRIPTION = '<text>' ]
    [ TAGS ( <tag> [, …] ) ]
    [ ( <field> ( <property> = '<value>' [, …] ) [, …] ) ]
    SOURCES ( <alias> AS [ <database> . ] <view> [, …] )
    [ FILTER ( <condition> ) ]
    [ ASSOCIATIONS ( <alias 1> <alias 2> [ <database> . ] <association> [ INNER | LEFT | RIGHT ] [, …] ) ]
    DIMENSIONS (
        <group> ( <attribute> AS <expression> [, …] ) [, …]
        [, <generic attribute> AS <expression> [, …] ]
    )
    METRICS ( <metric> AS <aggregate expression> [, …] )
    [ CHECK_INDIRECT_ACCESS { ON | OFF } ]
    [ CONTEXT ( … ) ]
```

- `ASSOCIATIONS` is required as soon as there are two sources (`invalid associations: It
  can't be empty`); a single source needs none.
- `<database>.` lets the metric view live in one database and read views and associations
  of another.
- Field properties take the forms of a derived view: `description`, `sourcetypesize`, … and
  `TAGS ( … )` per field.
- `FILTER ( … )` is not in the public grammar; the Design Studio wizard writes it ("Filter
  condition" tab) and `GET_METRIC_VIEWS().filter` returns it. Its place is right after
  `SOURCES` — after `ASSOCIATIONS` it is a syntax error. Measured: over a single source,
  every query fails with `Error applying metric transformation.`; over two sources, grouped
  queries apply it, and a metrics-only query fails when the condition is on a fact column
  and works when it is on a dimension column. Put the condition into the fact view instead
  (an `iv_` derived view with the `WHERE`).
- `CONTEXT ('formatted' = 'yes')` is accepted and not kept: `DESC VQL` re-serialises the
  definition anyway.
- `CHECK_INDIRECT_ACCESS` belongs to the indirect-access privilege (*documentation*;
  Administration Guide, "Limit Indirect Access to Views Shared with Other Development Teams").
- The Administration Guide says a metric may be derived from other metrics; VQL refuses it
  (`invalid field: missing source schema for field`, `SKILL.md`, Common mistakes) — repeat the
  aggregates.

## Joins: what each association does to the rows

*verified: 9.5.1 (live, 2026-10-01)*

| Association's dimension endpoint | Join type written | Unmatched facts (`NULL` or orphan key) | Members without facts |
|---|---|---|---|
| `(0,1)`, with or without `REFERENTIAL CONSTRAINT` | `RIGHT` | kept, one `NULL` group | absent |
| `(0,1)` | `LEFT` | dropped | present, `SUM` → `NULL`, `COUNT` → 0 |
| `(0,1)` | `INNER` | dropped | absent |
| `PRINCIPAL (0,1)`, `REFERENTIAL CONSTRAINT` | none | dropped | present (as `LEFT`) |
| `(1)`, with or without `REFERENTIAL CONSTRAINT` | none, `INNER` or **`RIGHT`** | dropped | absent |
| `(1)` | `LEFT` | dropped | present |

- The order of the two aliases in the pair does not change the result.
- The join of an association is applied only to queries that name an attribute of the
  dimensions behind it; a metrics-only query applies none and always counts every fact row.
- The plan shows the join actually run: `SELECT execution_plan FROM GET_QUERY_EXECUTION_PLAN()
  WHERE input_query = '<the query>'` — `RIGHT OUTER JOIN PLAN`, `LEFT OUTER JOIN PLAN` or
  `INNER JOIN PLAN`.
- **Interference.** With an extra association between the fact and the base view under a
  dimension view (`iv_fact → bv_calendar` next to `iv_fact → iv_calendar`), the metric
  view's `RIGHT` ran as `INNER`; dropping it restored `RIGHT`. A second association on the
  same pair of views, or one from the fact to an unrelated view, changed nothing. Three
  associations of different multiplicity between the same two base views also made `RIGHT`
  run as `INNER`.
- `GET_METRIC_VIEWS().associations` gives per pair the join type written: `0` `INNER`, `1`
  `LEFT`, `2` `RIGHT`, `null` none — not the one run.
- The Administration Guide has a table of default join types per pair of cardinalities;
  it names endpoints left and right without saying which is which. Measure with the totals
  check instead of reading it.

## Queries

Beyond `SKILL.md`, "Query it ad hoc":

- A query of metrics only is accepted and gives the grand total, although the Data Marketplace
  page says a query needs a dimension.
- `WHERE <metric> > …` fails with `Error executing query … [JDBC ROUTE] [ERROR]`.
- A metric view joined in the same `FROM` runs until the server's or the client's query
  timeout; `CONTEXT ('queryTimeout' = '<ms>')` shortens it. `CREATE VIEW` over such a query is
  accepted.

## Over a metric view: selection views

The Administration Guide allows "a join, a union, or any type of subquery, as long as the
subquery accessing the Metric View adheres to the required query structure", and Design
Studio has a wizard for it (metric view → **New** → **Selection**). Keep the metric view in
a `FROM` of its own — the selection view — and build everything else over it.

- A selection view's columns are ordinary columns: arithmetic, `ROUND`, `CASE`, joins and
  `WHERE` on them work. Its metric columns have the metric's type (`long` for a count,
  `double` for an `AVG` over integers, `decimal` for a sum over decimals).
- Re-applying the metric view unchanged keeps its selection views valid; removing a metric
  or dimension a selection view names turns it `INVALID` (its `SELECT` then fails with `The
  following views are in an invalid state`), and putting it back makes it valid again.
  `DROP VIEW <metric view>` without `CASCADE` is refused while selection views exist
  (`There are some elements that depend on this one`). `USED_BY()` lists them.

## What a metric view refuses or ignores

- **Cache**: `ALTER VIEW … CACHE FULL` — `Metric views do not support cache mode`. Cache or
  materialise the source views, or use summaries (below).
- **Row restrictions, masking, custom policies, global security policies** are not applied
  to the metric view itself; they apply when set on its source views (*documentation*). Column
  privileges and `EXECUTE`/`METADATA` work as on any view (*documentation*).
- **Lineage**: a metric view is listed by `USED_BY()` of its sources, and goes `INVALID` when
  a dimension or metric names a column that is gone; one that reaches a column only through
  an association stays `OK` and fails per query — `/denodo:views`,
  `references/dependencies.md`.

## Summaries

A summary built from a metric-view query (`SELECT <dims>, evaluate_metric(…) … GROUP BY
<dims>`) answers that query and any query over a subset of its dimensions (*documentation*,
Administration Guide, "Materialization and Smart Query Acceleration using Summaries"; it
needs every metric of the view in the summary). Summaries are created by a server
administrator with the right licence (`/denodo:materialize`; not verified over a metric view).

## Consumers

- **BI tools** through JDBC/ODBC see dimensions and metrics as columns; Power BI marks the
  metrics with Σ and must use DirectQuery so that the aggregation runs in Denodo
  (*documentation*).
- **Data Marketplace** shows a metric view with its own page (summary, schema with
  dimensions and metrics, a query wizard that adds `evaluate_metric` and the `GROUP BY` for
  you, data model, assisted query). Data preparation cannot sample a metric view; it needs
  live data enabled for it (*documentation*).
- **Assisted Query and the MCP Server** receive per field a flag dimension or metric
  (*documentation*); the MCP Server also labels the view's type `Metric` and applies the same
  visibility tags as to any view (`/denodo:semantics`) — the field descriptions matter as much
  as for any view.

## Procedures that describe it

| Procedure | Gives |
|---|---|
| `GET_VIEW_COLUMNS()` | per field `column_organization` (`dimension` / `metric`), `column_dimension` (the group), `column_definition` (the expression), `column_vdp_type`, `column_remarks` (the description); a pattern goes in `input_view_name = 'x%'`, not `LIKE` |
| `GET_METRIC_VIEWS('<db>', '<name pattern>')` | sources, associations with join type, filter, dimensions and metrics as arrays; a `LIKE` pattern works positionally only — `WHERE input_name = 'x%'` returns nothing |
| `DESC VQL VIEW <mv> ('includeDependencies' = 'no', 'dropElements' = 'no')` | `CREATE METRIC VIEW` without `OR REPLACE`, functions lower-cased; a wizard-made one ends with `ALTER VIEW … LAYOUT (…)`, which only places boxes on the canvas |
