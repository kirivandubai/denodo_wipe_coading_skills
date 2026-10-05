---
name: metrics
description: Use when business metrics or KPIs have to be defined once in Denodo 9.5 and reused by BI tools and AI agents — a metric view over a fact view and its dimension views — and whenever a metric view is queried or built on: EVALUATE_METRIC, a view over a metric view, metrics of two metric views side by side, a percent of total or a ratio of two metrics. Also for "a semantic layer of KPIs", "governed metrics", "one definition of revenue for every tool", and for the symptoms — AVG or SUM over a metric returns the metric's own value, SELECT * from a metric view returns no rows, a query joining a metric view runs until it times out, the totals by a dimension do not add up to the grand total, "Error applying metric transformation". Not for a mart of fixed grain that one consumer reads — /denodo:views; not for descriptions, keys and tags of views that already exist — /denodo:semantics.
---

# Metric views: KPIs defined once, sliced by any dimension

A **metric view** (new in 9.5) declares a model instead of a query: one **fact view** that
holds the measures, the **dimension views** around it, the **associations** that join them,
the **dimensions** a consumer may group and filter by, and the **metrics** — aggregations
over the fact view. A query names the dimensions it wants, and Denodo builds the joins and
the aggregation for exactly those, so "revenue" is the same number in every tool at every
grain. BI tools, the Data Marketplace, Assisted Query and the MCP Server read it like any
view, telling dimensions from metrics.

The model does not know this object, and most of what goes wrong with it returns a number,
not an error. Associations and the join rules for any two views are `/denodo:views`; the
descriptions consumers read are `/denodo:semantics`. Applying files is `/denodo:execute`;
the working loop, the naming defaults and the safety rule are `/denodo:vql`. A **mart** —
one aggregate of fixed grain for one consumer — is still a `CREATE VIEW … GROUP BY` in
`/denodo:views`; a metric view is for figures many consumers slice their own way.

## The rule: a metric view stands alone in its `FROM`

The only thing built directly on a metric view is a **selection view** — the metric view
alone in its `FROM`, dimensions in `SELECT` and `GROUP BY`, each metric as
`evaluate_metric(<metric>)`, a filter on dimensions in `WHERE`. Everything else — another
dimension view, another fact, a second metric view, arithmetic over metrics, a total — is
done over selection views. Measured on 9.5.1, each without an error message:

- a metric view joined to another view in the same `FROM` runs until the query timeout
  (`Error: Time out processing data`) — over a few thousand rows too;
- `evaluate_metric(a) * 100`, `ROUND(evaluate_metric(a), 2)` return `a` unchanged, and
  `evaluate_metric(a) / evaluate_metric(b)` returns no rows — ad hoc and inside a `CREATE
  VIEW` alike;
- `evaluate_metric(x)` over a column of any other view returns `NULL`;
- `SUM`, `AVG`, `MAX` or `COUNT` around a metric is ignored: the metric's own aggregation
  runs, so `AVG(revenue)` returns the sum.

Over a selection view — a view or a subquery — joins, `ROUND`, ratios and `CASE` work as in
any view.

## 1. The model, before the statement

| Part | What it must be | Check |
|---|---|---|
| **Fact view** | the one view every metric reads — metrics over two views are refused | its grain: `SELECT COUNT(*), COUNT(DISTINCT <key>) FROM <fact>` |
| **Dimension views** | one row per key, and that key declared as the view's `PRIMARY KEY` — a duplicated key multiplies every metric under it; an undeclared one empties every `HAVING` grouped by it (Silent failures, 12) | `SELECT COUNT(*), COUNT(DISTINCT <key>) FROM <dimension>` — equal; `column_is_primary_key` in `GET_VIEW_COLUMNS()` |
| **Associations** | one per dimension, from the fact (or from the dimension a snowflake hangs on), a tree with no second path | `SELECT association_name, mappings, valid FROM GET_ASSOCIATIONS() WHERE input_database_name = '<db>' AND input_type = 'views' AND input_name = '<fact>'` |
| **Fact rows without a dimension row** | decide: kept in a `NULL` group, or dropped | `SELECT COUNT(*), COUNT(<fk>) FROM <fact>`, and orphans: `… LEFT OUTER JOIN <dimension> … WHERE <fk> IS NOT NULL AND <dimension key> IS NULL` |

The checks in the table — *verified: 9.5.1 (live, 2026-10-05)*.

**Which fact rows survive is decided by the association, not by the query** — *verified:
9.5.1 (live, 2026-10-01)*:

| In `ASSOCIATIONS` | Rows of the fact without a match | Dimension members without facts |
|---|---|---|
| `RIGHT`, dimension endpoint `(0,1)` or `PRINCIPAL (0,1)` | kept, in a `NULL` group of that dimension | absent |
| `LEFT` | **dropped** | present, metrics `NULL` (`COUNT` 0) |
| `INNER`, or any type over a `(1)` endpoint | **dropped** | absent |
| nothing | from the association: dimension endpoint `(1)` → as `INNER`; `PRINCIPAL (0,1)` → as `LEFT` | |

- **`RIGHT` keeps the fact's rows only when the dimension endpoint of the association is
  `(0,1)`.** With `(1)` — "every fact row has exactly one" — the server runs `INNER`
  whatever you write, and the facts without a match vanish from every grouped query. The
  association template in `/denodo:views` declares `(1)`: right when the check above finds
  no `NULL` key and no orphan, wrong otherwise — then the association says `(0,1)`:
  `ENDPOINT <role> <fact view> (0,*)` and `ENDPOINT <role> <dimension view> PRINCIPAL (0,1)`,
  the rest of the template unchanged.
- The order of the two aliases does not matter; the type is read against the fact.
- A query without any dimension of a group applies no join for it: the grand total always
  counts every fact row, which is why a model that drops rows still shows the right total.
- **Another association between the fact and the view under a dimension view** (the base
  view a dimension `iv_` selects from) turned `RIGHT` into `INNER` — measured, reproduced by
  adding and dropping it. Before you add an association near a metric view, run Verify.
- Creating an association between views you did not create makes it a dependant of both:
  propose it to their owner (`/denodo:semantics`). Over someone else's base views, build your
  own `iv_` views for the fact and each dimension (`/denodo:views`) — with the key declared,
  text trimmed — and put the associations between those: everything the model needs is then
  yours, and no association lands next to theirs. The metric view can also live in your own
  database and name views of another (`<db>.<view>` in `SOURCES`).

## 2. Templates

Each template is one file, applied whole. `CREATE OR REPLACE METRIC VIEW` re-applies safely;
views built on it stay valid while the metrics and dimensions they name stay.

### The metric view

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE METRIC VIEW household_metrics
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Household KPIs by income band and buying potential. Query: SELECT <dimensions>, evaluate_metric(<metric>) FROM household_metrics GROUP BY <dimensions>.'
    (
        buy_potential   ( description = 'Buying potential band of the household, as in the source (for example ''0-500'').' ),
        household_count ( description = 'Number of households.' ),
        avg_dependents  ( description = 'Average number of dependents per household.' )
    )
    SOURCES (
        households AS bv_household_demographics,
        bands      AS bv_income_band
    )
    ASSOCIATIONS (
        households bands a_income_band_household RIGHT
    )
    DIMENSIONS (
        income_band (
            income_band_sk     AS bands.ib_income_band_sk,
            income_lower_bound AS bands.ib_lower_bound,
            income_upper_bound AS bands.ib_upper_bound
        ),
        household (
            buy_potential AS TRIM(households.hd_buy_potential)
        )
    )
    METRICS (
        household_count AS COUNT(households.hd_demo_sk),
        dependents      AS SUM(CAST('long', households.hd_dep_count)),
        avg_dependents  AS AVG(households.hd_dep_count)
    );
```

Clause order: `FOLDER` → `DESCRIPTION` → `TAGS` → `( field properties )` → `SOURCES` →
`ASSOCIATIONS` → `DIMENSIONS` → `METRICS`. Each alias in `SOURCES` is how dimensions and
metrics name that view. `a_income_band_household` is the association template of
`/denodo:views`; its `(1)` endpoint makes this `RIGHT` run as `INNER`, which is right here
because every household has its band. `bv_income_band` declares `PRIMARY KEY (
'ib_income_band_sk' )` in its own file — over a file source, a dimension view without its key
declared answers every `HAVING` grouped by that key with no rows.

- **A dimension** is any expression over the sources without an aggregate: `TRIM`, `CASE`,
  `COALESCE(<dim>.<label>, '(not specified)')` to name the `NULL` group, `GETYEAR(<date>)`, a
  `CONCAT` over two views. Labels and buckets belong here, in the definition — the same
  expression written in a query and grouped by its alias can lose every `COUNT(DISTINCT …)`
  metric from the result (Silent failures, 13). Groups (`income_band ( … )`) are how
  consumers see them; an attribute after the last group, `, <name> AS <expr>`, is a generic
  one.
- **A metric** is an aggregate over fact columns: `SUM`, `COUNT(<column>)`, `COUNT(DISTINCT
  …)`, `AVG`, `MIN`, `MAX`, with `CASE` inside (`SUM(CASE WHEN … THEN amount ELSE 0 END)`) and
  arithmetic over aggregates (`SUM(fee) / NULLIF(SUM(amount), 0)`). It cannot name another
  metric or use `COUNT(*)` — both are `invalid field: missing source schema for field:
  <metric>`; repeat the aggregates instead.
- **The dialect rules hold inside a metric** (`/denodo:vql`): `SUM` over an `int` column
  stays `int`, hence `CAST('long', …)` above; an `int` divided by an `int` is an integer
  division, so a share written `SUM(CASE … 1 ELSE 0 END) / COUNT(x)` is `0` — write
  `1.0 * SUM(…) / COUNT(x)`. `AVG` over an integer is a `double` with noise in the last
  digits; `AVG` over a `decimal` and a ratio of `decimal` sums come back as `decimal` with a
  scale the server picks (a dozen digits and more). `ROUND` goes inside the metric
  (`ROUND(AVG(x), 2)`) or over a selection view's column — around `evaluate_metric` it is
  dropped.
- **`AVG` and `COUNT(<column>)` skip `NULL`s**: over a fact with missing measures, "average
  per return" is the sum over the rows that have one. Decide which the KPI means —
  `AVG(x)`, or `SUM(x) / COUNT(<key>)` for "missing counts as zero" — and say it in the
  metric's description.
- **A filter that every metric obeys goes into the fact view** — an `iv_` derived view with
  the `WHERE`, named in `SOURCES`. The `FILTER ( … )` clause the Design Studio wizard writes
  after `SOURCES` fails on some queries with `Error applying metric transformation.` —
  details in `references/metric-views.md`.
- Field descriptions go in the field properties above or by `ALTER VIEW <metric view> (
  ALTER COLUMN … ADD ( DESCRIPTION = '…' ) )`. A selection view inherits the description of
  a dimension it passes through, never that of a metric: describe `evaluate_metric` columns
  in the selection view (`/denodo:semantics`).
- `DESC VQL` gives the definition back as `CREATE METRIC VIEW` — without `OR REPLACE`,
  functions lower-cased, `CONTEXT` dropped — so it is a reference, not your file. A metric
  view takes no cache: `ALTER VIEW … CACHE FULL` is `Metric views do not support cache mode`.

### Selection views, a total and a share

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW households_by_band
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Households per income band, from the metrics of household_metrics. One row per income band.'
    AS SELECT income_band_sk,
              evaluate_metric(household_count) AS household_count,
              evaluate_metric(avg_dependents)  AS avg_dependents
       FROM household_metrics
       GROUP BY income_band_sk
    CONTEXT ('formatted' = 'yes');

CREATE OR REPLACE VIEW households_total
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'All households, from the metrics of household_metrics. One row.'
    AS SELECT evaluate_metric(household_count) AS household_count,
              evaluate_metric(avg_dependents)  AS avg_dependents
       FROM household_metrics
    CONTEXT ('formatted' = 'yes');

CREATE OR REPLACE VIEW household_share_by_band
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Each income band''s share of all households, in percent. One row per income band.'
    AS SELECT b.income_band_sk,
              b.household_count,
              ROUND(100.0 * b.household_count / t.household_count, 2) AS household_share_pct,
              ROUND(b.avg_dependents, 2)                              AS avg_dependents
       FROM households_by_band b
            CROSS JOIN households_total t
    CONTEXT ('formatted' = 'yes');
```

- **A total comes from the metric, never from adding up rows.** `households_total` asks the
  metric view with no dimension at all — allowed when the `SELECT` holds metrics only; a
  literal next to them needs a `GROUP BY` (`For this type of query, the group by fields are
  mandatory.`). Summing the rows of `households_by_band` is right for a sum or a count and
  wrong for an average (an average of averages) and for a `COUNT(DISTINCT …)` (a customer in
  two bands counts twice).
- **A view or fact from outside the model** joins to a selection view grouped by the join
  key — `GROUP BY <key>` in the selection, then `JOIN <other view> ON s.<key> = …`. **Two
  metric views side by side**: one selection view each, at the same dimensions — aliased to
  one name when the two metric views call it differently — joined on them; a `FULL OUTER
  JOIN` keeps a member only one of them has, and the key column is then `COALESCE(a.<key>,
  b.<key>)`.
- Arithmetic over metrics — a ratio, a percent, rounding — is a column of the view over the
  selections, as `household_share_pct` above.
- Do not `GROUP BY` a selection view again to a coarser grain unless every metric in it is a
  sum or a count; ask the metric view at that grain instead.
- **An average per member** — per customer, per store — is a selection grouped by the
  member, averaged in the view above: `SELECT type, AVG(m.total) FROM (SELECT type,
  customer_id, evaluate_metric(revenue) AS total … GROUP BY type, customer_id) m GROUP BY
  type` — *verified: 9.5.1 (live, 2026-10-05)*. Its denominator is the members that have facts; members without any are absent
  under `RIGHT`. When they must count as zero, take the members from a dimensions-only query
  (it lists every one) and `LEFT OUTER JOIN` the totals to it.
- **When nothing may be created** — a question to answer, not a view to build — the same
  views are subqueries: `SELECT … FROM (<selection>) b CROSS JOIN (<total>) t`.

### Query it ad hoc

```sql
-- verified: 9.5.1 (live, 2026-10-06)
SELECT income_band_sk, buy_potential,
       evaluate_metric(household_count) AS household_count
  FROM household_metrics
 WHERE buy_potential = '>10000'
 GROUP BY income_band_sk, buy_potential
HAVING evaluate_metric(household_count) > 50
 ORDER BY household_count DESC;
```

| Works | Does not |
|---|---|
| `WHERE` on dimensions | `WHERE evaluate_metric(m) > …` — `Aggregate functions are not allowed here`; `WHERE <metric> > …` — an `Error executing query` from the route |
| `HAVING evaluate_metric(m) > …`, `HAVING <dimension> …` | `HAVING <alias>` — `Field not found`; `HAVING <metric>` — `is not a group by field` |
| `ORDER BY <alias>` or `ORDER BY evaluate_metric(m)` | `ORDER BY` a field not in the `SELECT` — `Field not found '<f>' in view with schema` |
| an expression over a dimension in `SELECT`, grouped by the **raw dimension** — one row per raw value, every metric kept | the same expression grouped by its **alias**: regrouped, but a `COUNT(DISTINCT …)` metric can go missing from the result (Silent failures, 13) — put the expression in the dimension's definition |
| `COUNT(*)` — the fact rows of the group | `GROUP BY <metric>` — `The group by fields can only be dimensions or literals` |
| `LIMIT` | no `GROUP BY` with a dimension in `SELECT`, or `SELECT *` — **0 rows, no error** |

A query of dimensions only lists every member of the dimension view — every year of a
calendar — not the members that have facts. Ask with a metric to see what has data.

## 3. Read what exists

```sql
-- verified: 9.5.1 (live, 2026-10-06)
SELECT column_name, column_organization, column_dimension, column_definition, column_vdp_type
  FROM GET_VIEW_COLUMNS()
 WHERE input_database_name = 'sales_analytics' AND input_view_name = 'household_metrics';

SELECT name, sources, associations, filter
  FROM GET_METRIC_VIEWS('sales_analytics', 'household_metrics');
```

The first lists every dimension and metric with its expression — what a query may name;
add `column_remarks` for the descriptions.
The second gives the sources and, per association, the join type: `0` `INNER`, `1` `LEFT`,
`2` `RIGHT`, `null` none written. `GET_METRIC_VIEWS` takes a `LIKE` pattern only as a
positional argument; `WHERE input_name = '<pattern>'` returns nothing. These two are the way
to read a metric view. `vql desc … --vql` of a metric view, or of a view built on one,
rebuilds its sources down to the data sources — `ENCRYPTED` passwords included, into your
transcript — and when the metric view is in another database, it leaves the metric view out
and gives back that database's source views unqualified, as if they were yours. A metric view
is
`subtype = 'metric'` in `GET_ELEMENTS()` and `view_type = 5` in `GET_VIEWS()`. The
description of a metric view written by someone else may show a query with `SUM(<metric>)`:
it runs only because the outer `SUM` is ignored.

## Who applies what

A new metric view and the views over it, created in this session, are yours to apply and
verify. Changing a metric view you did not create in this session — `CREATE OR REPLACE METRIC
VIEW` over it, even to add one metric — rewrites what every dashboard on it reads: show the
file and get a yes (`/denodo:vql`). A missing dimension or metric in another team's metric
view is a proposal to them; until they add it, your own metric view over the same sources
answers the question without touching theirs.

## Verify — the totals check

The one check that catches the silent failures of the model: the same figure three ways.

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

-- 1. The fact itself.
SELECT COUNT(hd_demo_sk) AS fact_total FROM bv_household_demographics;

-- 2. The metric with no dimension: no join is applied.
SELECT evaluate_metric(household_count) AS metric_total FROM household_metrics;

-- 3. Once per dimension group: its slices add up to the same total.
SELECT SUM(s.household_count) AS slices_total, COUNT(*) AS slices
  FROM (SELECT income_band_sk, evaluate_metric(household_count) AS household_count
          FROM household_metrics
         GROUP BY income_band_sk) s;
```

| You see | It means |
|---|---|
| 1 = 2 = 3 | every fact row is in every slicing |
| 3 lower than 2 | fact rows dropped under that dimension: `NULL` or orphan keys with `INNER`, `LEFT`, no type, or a `(1)` endpoint (section 1) |
| 3 higher than 2 | a key duplicated in that dimension view: those facts are counted twice |
| 2 differs from 1 | the metric reads a different column or a `FILTER`; read its definition (section 3) |

**On a metric view you did not build** the same three queries tell you what its
associations do with the rows: you cannot read the join from its definition alone.

Run step 3 for one attribute of each dimension group — each association is applied only
when a query names its dimensions. Use a sum or a count for it; then compare every other
metric with plain SQL over the fact and the dimension — one `FULL OUTER JOIN` of the
selection and the plain `GROUP BY` on the dimensions, keeping the rows where any figure
differs, checks every slice at once. Compare averages with a tolerance: an `AVG` over an
integer is a `double` in the metric and a `decimal` in hand-written SQL over a decimal
column, and a `ROUND` inside the metric can then differ in the last digit. Also: `SELECT
name, view_status FROM GET_VIEWS() WHERE input_database_name = '<db>' AND
input_retrieve_invalid_views_only = true` is empty, and every selection view returns rows —
*verified: 9.5.1 (live, 2026-10-05)*.

## Silent failures

Each runs without an error — *verified: 9.5.1 (live, 2026-10-01)*.

| You wrote | What you get | Instead |
|---|---|---|
| 1. `AVG(<sum metric>)`, `SUM(<avg metric>)`, `MAX(…)` | the metric's own aggregation | `evaluate_metric`; another aggregation is another metric, or a view over a selection |
| 2. `evaluate_metric(a) * 100`, `ROUND(evaluate_metric(a), 2)` | `a`, unchanged | the expression over the selection view's column |
| 3. `evaluate_metric(a) / evaluate_metric(b)` | no rows | a ratio metric `SUM(x) / NULLIF(SUM(y), 0)`, or the division over a selection |
| 4. `SELECT * FROM <metric view>`, a dimension without `GROUP BY` | no rows | dimensions in `GROUP BY`, metrics in `evaluate_metric` |
| 5. `RIGHT` over an association with a `(1)` dimension endpoint | facts without a match dropped from every grouped query; the grand total still right | `(0,1)` on the association; the totals check |
| 6. `LEFT`, or no type over a `PRINCIPAL (0,1)` endpoint | every dimension member, with empty metrics, and the unmatched facts dropped | `RIGHT` |
| 7. a dimension view with a duplicated key | every metric of that key multiplied | one row per key in the dimension view |
| 8. a metric without an aggregate (`n AS f.qty`) | accepted; every query with it returns no rows | an aggregate |
| 9. the sum of a selection's rows as a total | an average of averages; distinct counts counted twice | the metric with no dimension |
| 10. `evaluate_metric(x)` over a selection view | `NULL` | `x` — `evaluate_metric` belongs to the metric view only |
| 11. a share as `SUM(CASE … 1 ELSE 0 END) / COUNT(x)` | `0` — integer division | `1.0 * SUM(…) / COUNT(x)` |
| 12. `HAVING evaluate_metric(m) > …` grouped by the key of a dimension view that declares no `PRIMARY KEY`, over a file source | no rows: the plan is `INCOMPATIBLE_QUERY_VIEW`, `VOID PLAN` (the same query delegated to a database answered) | declare the key in the dimension view's file; or filter the selection view's column in a view above |
| 13. `COALESCE(<dim>, '…') AS d`, `UPPER(<dim>) AS d` or a `CASE` in a query, `GROUP BY d`, over sources in a database | every `COUNT(DISTINCT …)` metric missing from the result — the plan already projects without it; sums, counts and averages stay (over file sources it stayed) | the expression in the dimension's definition, or `GROUP BY <dim>` and the label in the view above |

## Common mistakes

| You wrote | Server says | Fix |
|---|---|---|
| a metric view joined to a view in one `FROM` | nothing, then `Error: Time out processing data` | a selection view, then the join |
| `per AS total / cnt` — a metric over metrics; `COUNT(*)` | `invalid field: missing source schema for field: per` | repeat the aggregates; `COUNT(<fact column>)` |
| `MAX(…)` in a dimension | `The following fields cannot be projected: max(…) AS <dim>` | aggregates go in `METRICS` |
| metrics over two source views | `There are metric fields referencing different views. Metrics must be built using fields from the same view.` | one fact view; the other figure is a second metric view |
| two `SOURCES`, no `ASSOCIATIONS` | `invalid associations: It can't be empty` | name the association |
| `evaluate_metric(<dimension>)` | `There are dimensions fields with function aggregation …` | dimensions go in `GROUP BY` |
| a literal next to metrics, no `GROUP BY` | `For this type of query, the group by fields are mandatory.` | `GROUP BY '<literal>'`, or the literal in the view above |
| a view `AS SELECT * FROM <metric view>` | created; its queries fail with `Error applying metric transformation.` | a selection view |
| a metric removed while a selection view names it | the selection view turns `INVALID` | put the metric back, or change the selection first (`/denodo:views`, "Before a column changes") |

## Reference

- `references/metric-views.md` — the full `CREATE METRIC VIEW` grammar, the join types
  measured case by case, the `FILTER` clause, what a metric view refuses (cache, row
  restrictions), how consumers read it, summaries, and the procedures that describe it.
