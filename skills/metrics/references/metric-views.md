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

### What an expression may hold

| Where | Accepted | Refused |
|---|---|---|
| dimension | any row-level expression over one or several sources: `TRIM`, `CASE`, `COALESCE`, `CONCAT`, `GETYEAR`, casts, literals | an aggregate — `The following fields cannot be projected: max(…) AS <dim>` |
| metric | `SUM`, `COUNT(<col>)`, `COUNT(DISTINCT <col>)`, `AVG`, `MIN`, `MAX`; `CASE` inside them; arithmetic over aggregates (`SUM(a) / NULLIF(SUM(b), 0)`); `ROUND(AVG(x), 2)`; `SUM(CAST('long', x))` | another metric's name and `COUNT(*)` — `invalid field: missing source schema for field: <metric>`; columns of two views — `There are metric fields referencing different views. Metrics must be built using fields from the same view.` |
| metric without an aggregate (`n AS f.qty`) | **accepted** | — and every query that names it returns no rows |

The Administration Guide says a metric may be "derived by referencing other metrics"
(Average Order Value = Total Revenue / Order Count); in VQL that is the refusal above —
repeat the aggregates. Types follow the dialect: `SUM` over `int` stays `int`, `COUNT` is
`long`, `AVG` over an integer is `double`, `SUM(int) / COUNT(x)` is an integer division.

## Joins: what each association does to the rows

Measured over a fact with `NULL` foreign keys and a calendar dimension whose members mostly
have no facts, every variant built and queried separately — *verified: 9.5.1 (live,
2026-10-01)*.

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
  view's `RIGHT` ran as `INNER`; dropping the extra association brought it back, adding it
  again repeated it. A second association on the same pair of views, or one from the fact
  to an unrelated view, changed nothing. Three associations of different multiplicity
  between the same two base views also made `RIGHT` run as `INNER`.
- `GET_METRIC_VIEWS().associations` gives per pair the join type written: `0` `INNER`, `1`
  `LEFT`, `2` `RIGHT`, `null` none — not the one run.
- The Administration Guide has a table of default join types per pair of cardinalities;
  it names endpoints left and right without saying which is which. Measure with the totals
  check instead of reading it.

## Queries

| Shape | Result |
|---|---|
| `SELECT <dims>, evaluate_metric(<m>) FROM <mv> GROUP BY <dims>` | the metric at that grain |
| `SELECT evaluate_metric(<m>) FROM <mv>` | the grand total (the Data Marketplace page says a query needs a dimension; VQL accepts this) |
| a literal next to metrics only | `For this type of query, the group by fields are mandatory.`; `GROUP BY '<literal>'` works |
| `SELECT <dims> FROM <mv> GROUP BY <dims>` | every member of the dimension views, with or without facts |
| `SELECT *`, or dimensions without `GROUP BY` | **0 rows**; as a view: `Error applying metric transformation.` |
| `SUM`/`AVG`/`MAX`/`COUNT(<metric>)` | the metric's own aggregation, the outer one ignored (*documented*) |
| `COUNT(*)` | the number of fact rows in the group |
| `evaluate_metric(a) * k`, `ROUND(evaluate_metric(a), n)` | `a` unchanged |
| `evaluate_metric(a) / evaluate_metric(b)` | 0 rows |
| `evaluate_metric(<dimension>)` | `There are dimensions fields with function aggregation (…). A dimension field can not be used with an aggregation function.` |
| `evaluate_metric(x)` over any other view | `NULL` |
| `WHERE <dimension> …` | filters the facts before aggregation |
| `WHERE evaluate_metric(m) > …` / `WHERE m > …` | `Aggregate functions are not allowed here` / `Error executing query … [JDBC ROUTE] [ERROR]` |
| `HAVING evaluate_metric(m) > …` | filters groups; **0 rows** when grouped by the key of a dimension view with no declared `PRIMARY KEY` over a file source (plan `INCOMPATIBLE_QUERY_VIEW`, `VOID PLAN`) — declaring the key fixed it; over a view delegated to SQL Server, without a key, it answered |
| `HAVING <dimension> …` | works |
| `HAVING <alias>` / `HAVING <metric>` | `Field not found …` / `Field '<m>' is not a group by field` |
| `GROUP BY <metric>` | `There are metric fields inside the group by fields (<m>). The group by fields can only be dimensions or literals.` |
| `<expr over dims> AS a … GROUP BY a` | grouped by the expression; over sources delegated to a database (SQL Server measured), every `COUNT(DISTINCT …)` metric is dropped from the plan and the result — over file sources it stayed. An expression in the dimension's own definition keeps it |
| `<expr over dims> AS a … GROUP BY <dims>` | grouped by the raw dimensions, `a` repeated |
| `ORDER BY <alias>`, `ORDER BY evaluate_metric(m)`, `LIMIT` | work |
| `ORDER BY <field not selected>` | `Field not found '<f>' in view with schema: …` |
| `<mv> JOIN <view> ON …` with `GROUP BY` | runs until the query timeout: `Error: Time out processing data` (900 s by default; `CONTEXT ('queryTimeout' = '<ms>')` shortens it). `CREATE VIEW` over it is accepted |
| a subquery or view of the shape in the first row, joined to anything | works |

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
- A selection view inherits the description of a dimension it passes through and none of a
  metric (an aggregate inherits nothing — `/denodo:semantics`).
- Totals: a metrics-only selection view (`households_total` in the skill) gives the
  grand total; a `CROSS JOIN` of it with a grouped one gives shares. An average or a distinct
  count is never re-aggregated from the grouped rows.

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
needs every metric of the view in the summary). Summaries are created in Design Studio by
someone with the right licence and privileges — not by this skill.

## Consumers

- **BI tools** through JDBC/ODBC see dimensions and metrics as columns; Power BI marks the
  metrics with Σ and must use DirectQuery so that the aggregation runs in Denodo
  (*documentation*).
- **Data Marketplace** shows a metric view with its own page (summary, schema with
  dimensions and metrics, a query wizard that adds `evaluate_metric` and the `GROUP BY` for
  you, data model, assisted query). Data preparation cannot sample a metric view; it needs
  live data enabled for it (*documentation*).
- **Assisted Query and the AI SDK** receive per field a flag dimension or metric
  (*documentation*) — the field descriptions matter as much as for any view.
- **The MCP Server** shows a metric view like a view, under the same visibility tag
  (`/denodo:semantics`).

## Procedures that describe it

| Procedure | Gives |
|---|---|
| `GET_VIEW_COLUMNS()` | per field `column_organization` (`dimension` / `metric`), `column_dimension` (the group), `column_definition` (the expression), `column_vdp_type`, `column_remarks` (the description); a pattern goes in `input_view_name = 'x%'`, not `LIKE` |
| `GET_METRIC_VIEWS('<db>', '<name pattern>')` | sources, associations with join type, filter, dimensions and metrics as arrays; a `LIKE` pattern works positionally only — `WHERE input_name = 'x%'` returns nothing |
| `GET_VIEWS()` | `view_type = 5` |
| `GET_ELEMENTS()` | `subtype = 'metric'` |
| `DESC VQL VIEW <mv> ('includeDependencies' = 'no', 'dropElements' = 'no')` | `CREATE METRIC VIEW` without `OR REPLACE`, functions lower-cased; a wizard-made one ends with `ALTER VIEW … LAYOUT (…)`, which only places boxes on the canvas. Without the options, `DESC VQL` of a view built on a metric view of another database leaves the metric view out and returns that database's source views unqualified, with their tags |
