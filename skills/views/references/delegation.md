# Delegation in full

Everything `/denodo:views` leaves out of its delegation check: how to read the plan, what
each outcome looks like, why `GET_DELEGATED_SQLSENTENCE` is not the check, and what to put
in front of the human. Tuning — statistics, the cost-based optimizer, join methods, data
movement — is not covered: that is the execution trace in Design Studio and the
administrator.

## What is at stake

A view over JDBC base views is fast when Denodo hands the whole `SELECT` — joins, filters,
`GROUP BY` — to the database as one SQL statement. When one expression cannot be translated
for that database, the database still runs what lies below it and Denodo runs the rest:
every row below that expression travels to Denodo, which then joins or aggregates them
itself. The rows are the same, nothing reports an error, and the cost grows with the fact
table: the view that answers in a second over test data takes minutes over production data.

## Reading the plan

```sql
-- verified: 9.5.1 (live, 2026-09-30)
SELECT execution_plan
  FROM GET_QUERY_EXECUTION_PLAN()
 WHERE input_query = 'SELECT * FROM store_month_sales';
```

It plans without running the query (`unions.md`, "Seeing the plan"), so the `SELECT` of a
view can be planned inline before the view exists. Plan the top view, not the pieces: the
optimizer works through the `iv_` layer, and what reaches the database is decided for the
whole stack. The text is long; the lines that decide are `noDelegationCause`,
`optimizationsApplied`, `JDBC ROUTE (`, `datasource =` and `SQLSentence =`. Three outcomes:

| In the plan | Means |
|---|---|
| exactly one `SQLSentence = …` line, holding the joins and the `GROUP BY`, and no `noDelegationCause` | delegated whole: the database does all of it |
| `noDelegationCauses = [The aggregate function 'median' cannot be delegated to this database]` near the top, and `noDelegationCause = …` on the node where it stops | one expression stopped it. The `SQLSentence` below that node is what the database still does — typically the joins without the `GROUP BY` — and the nodes above it (`GROUPBY PLAN`, `PROJECTION PLAN`) run in Denodo |
| two or more `JDBC ROUTE (` blocks, each with its own `datasource = …` and `SQLSentence`, under an `INNER JOIN PLAN` (`type = MERGE`, `HASH`, `NESTED`) — **and no cause printed anywhere** | the views come from **different data sources** and Denodo joins them. A check that only searches for `noDelegationCause` passes this one. It holds even when both data sources point at the same database server: the Denodo data source object decides, not the server behind it. What travels is in each `SQLSentence` — see below |

**Two data sources: groups or rows.** Denodo may still split the aggregate: with
`optimizationsApplied = [Aggregation Push-down]` at the top, the fact's `SQLSentence` carries
a `GROUP BY` on the join key (`… sum(…), count_big(*) … GROUP BY …, ss_item_sk`), the database
sends one row per key and month instead of one per line, and Denodo finishes the join and the
aggregate. Without it the fact's `SQLSentence` is a plain `SELECT … ORDER BY <join key>`, and
every line travels. Which one you get is not predictable from the view — the same join
grouped by category alone got no push-down, grouped by category and month through a date
dimension got it (*live, 2026-09-30*) — and an aggregate that cannot be split, such as
`MEDIAN`, always sends every line. Read the `SQLSentence` of the biggest table.

A filter still goes down on its own when an aggregate above it cannot: `WHERE store_sk = 110`
over a mart whose `MEDIAN` stays in Denodo shows up as `WHERE t1.s_store_sk = ?` inside the
`SQLSentence`, so only that store's rows travel.

Measured on 9.5.1 (*live, 2026-09-30*), one query per line, `GROUP BY` over one table:

| Expression | SQL Server | PostgreSQL |
|---|---|---|
| `MEDIAN(x)` | `The aggregate function 'median' cannot be delegated to this database` | delegated, as `PERCENTILE_DISC(0.5)` — a different answer, see `/denodo:vql`, `references/dialect.md` |
| `FIRST(x)`, `LIST(x)` | `The aggregate function '…' cannot be delegated …` | the same |
| `NEST(x)` | `The aggregate function 'nest' cannot be delegated …` | delegated |
| `MAP(x, '<map>')` | `The function 'map' cannot be delegated …` | the same |
| `REGEXP(s, …)`, `SPLIT(…)` | `The function '…' cannot be delegated …` | delegated |
| `CAST(<text column> AS integer)` | delegated | `The parameters of the function 'cast' cannot be delegated to this database. Parameter with type 'text' cannot be cast to 'int'` |
| `TRIM`, `UPPER`, `COALESCE`, `SUBSTR`, `CONCAT`, `CASE`, `ROUND`, `TRUNC(<date>, …)`, `EXTRACT`, `GETYEAR`, `FORMATDATE`, `ADDMONTH`, `TO_LOCALDATE`, `INITCAP`, `LPAD`, `CAST('long', x)`, `COUNT(DISTINCT x)`, `AVG`, `STDEV`, `GROUP_CONCAT`, `ROW_NUMBER() OVER (…)` | delegated | delegated |

The list depends on the adapter the data source was created with — `MEDIAN` goes to one
database and not the other — so it is a sample, not a rule. Read the plan of the view you
built.

## The answer is per query

A column the query does not select is dropped from the plan. Over a mart with a `MEDIAN`
column, `SELECT store_sk, sales_lines, net_paid_total FROM mart` goes to the database whole,
and only a query that reads the median pays for it (*live, 2026-09-30*). So:

- `SELECT * FROM <view>` is the worst case, and the one to check after creating the view;
- a check that never selects the blocking column — `SELECT COUNT(*) FROM mart`, a
  primary-key check — never runs it, and a timing taken that way says nothing about it;
- when the answer is "not delegated", plan the query the consumer will run: a dashboard that
  never reads the blocking column does not pay for it.

## `GET_DELEGATED_SQLSENTENCE` is not the check

```sql
-- verified: 9.5.1 (live, 2026-09-30)
SELECT delegated_query
  FROM GET_DELEGATED_SQLSENTENCE()
 WHERE vdp_query = 'SELECT * FROM store_month_sales';
```

The documentation says it answers only for a query that goes to one JDBC source whole. On
9.5.1 it does not fail when part of the query stays in Denodo: it returns the SQL of the part
that was delegated, and says nothing else. Over a mart whose `MEDIAN` stays in Denodo it
returns the joins with no `GROUP BY` — the missing `GROUP BY` is the only sign. Across two
data sources it fails with an error that names nothing (`… GET_DELEGATED_SQLSENTENCE [STORED
PROCEDURE] [ERROR] Received exception with`). Use it to show the human the SQL of a view the
plan has already shown to be delegated whole.

## What to put in front of the human

"Correct but slow" is their decision. Name what stops the delegation — the function and the
column it computes, or the two data sources — and what it costs: every row below that point
is read into Denodo, and the volume that matters is production's, not the sample's. The
rows that travel can be counted: a `COUNT(*)` over the `SQLSentence`'s own grain — the lines,
or the groups of an aggregation push-down — and what that number grows with (lines per day,
items, months) is the part of the answer the human needs. Then the
options, with the one you would pick. Every one of them is theirs to choose — and when you
cannot ask, build what was asked, as it was asked, and put the cost and the options in your
report:

- **change or drop the measure** — `AVG` is not a median, and a replacement that computes
  something else is a different answer, not an optimisation;
- **a rewrite the database can run** — a median, for instance, from `ROW_NUMBER()` and
  `COUNT(x)` windows, averaging the middle one or two rows. It is a second definition of the
  measure, and it has to match `MEDIAN` over the same rows on everything `MEDIAN` does:
  `NULL`s skipped (`COUNT(*)` and the database's `NULL` ordering break that), rounding half
  up to two places, the scale of the result. It also moves where a consumer's filter lands:
  over the rewrite a `WHERE store_sk = …` stays outside the grouped subquery, so a one-store
  query can get slower than with `MEDIAN`, whose filter reaches the database. Window
  functions also stop working the moment the view is no longer delegated (`Function
  row_number is not executable`);
- **keep it** — when the volume stays small, or the consumer never reads that column;
- **two data sources** — nothing inside the view changes it. Moving the data into one place
  (a cache, a copy in one database) is outside this skill.
