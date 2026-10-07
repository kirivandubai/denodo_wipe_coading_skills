# Periods: year over year, to date, running totals

A comparison of periods is built like everything else over a metric view: selections — the
metric view alone in its `FROM` — and the arithmetic in a view above them (`SKILL.md`, "The rule").
What is particular to periods is where they come from, what a partial period does to a change,
what "today" is, and which totals can be added up.

The examples are a metric view of store returns over a calendar: `bv_retail_store_returns` (the
fact, one row per return line, `sr_returned_date_sk` empty on some) and `bv_date_dim` (the TPC-DS
calendar, one row per day, `d_date_sk` its key), in `sales_analytics`.

## The periods are dimensions

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE ASSOCIATION a_return_date REFERENTIAL CONSTRAINT
    FOLDER = '/06 - associations'
    ENDPOINT return_date   bv_retail_store_returns (0,*)
    ENDPOINT store_returns bv_date_dim PRINCIPAL (0,1)
    ADD MAPPING sr_returned_date_sk = d_date_sk;

CREATE OR REPLACE METRIC VIEW store_return_metrics
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Store return KPIs by calendar period. A return line without a date is in the NULL period of every level.'
    SOURCES (
        returns AS bv_retail_store_returns,
        dates   AS bv_date_dim
    )
    ASSOCIATIONS (
        returns dates a_return_date RIGHT
    )
    DIMENSIONS (
        return_date (
            return_year  AS dates.d_year,
            return_month AS dates.d_moy,
            return_day   AS dates.d_date
        )
    )
    METRICS (
        return_amount       AS SUM(returns.sr_return_amt),
        return_lines        AS COUNT(returns.sr_ticket_number),
        returning_customers AS COUNT(DISTINCT returns.sr_customer_sk)
    );
```

- **Every period a consumer compares is a dimension** — year, quarter (`d_qoy`), month, day, from
  the calendar's own columns. `(0,1)` with `RIGHT` keeps the undated lines, in a `NULL` period
  (`SKILL.md`, section 1). Without a calendar view the fact's own date serves: one source, no
  `ASSOCIATIONS` clause, and each period an expression in its dimension's definition —
  `<year> AS GETYEAR(f.<date>)`, a quarter as a `CASE` over `GETMONTH(f.<date>)`. There they are
  safe; the same expressions written in a query are not (the last point).
- **A coarser period cannot be added up later for every metric.** Sums and counts roll up from a
  finer selection; a `COUNT(DISTINCT …)` does not — the months of a year summed counted a customer
  once per month they returned something, a higher figure than the year's own — and neither do
  averages and ratios. When the metric view has only a date, the year of a distinct count or an
  average is a dimension its owner adds — or your own metric view over the same sources. When
  nothing may be created, a finer dimension filtered to one coarser period at a time answers
  exactly: `WHERE <month> IN (1, 2, 3) GROUP BY <year>` is the first quarter of every year.
- **Not grouped by an expression over the date in the query.** Grouped by `GETYEAR(<date>)` — by
  the expression or by its alias — a metric view over a database drops every `COUNT(DISTINCT …)`
  metric from the result, with no error (`SKILL.md`, Silent failures, 13) —
  *verified: 9.5.1 (live, 2026-10-06)*, SQL Server.

## Year over year

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW store_returns_by_year
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Store returns per calendar year, from the metrics of store_return_metrics. One row per year with returns; first_day and last_day are the first and last dates of the year that have returns. Undated return lines are in no year.'
    PRIMARY KEY ( 'return_year' )
    AS SELECT y.return_year, y.return_amount, y.return_lines, y.returning_customers,
              d.first_day, d.last_day
       FROM ( SELECT return_year,
                     evaluate_metric(return_amount)       AS return_amount,
                     evaluate_metric(return_lines)        AS return_lines,
                     evaluate_metric(returning_customers) AS returning_customers
              FROM store_return_metrics
              WHERE return_year IS NOT NULL
              GROUP BY return_year ) y
            INNER JOIN ( SELECT return_year, MIN(return_day) AS first_day, MAX(return_day) AS last_day
                         FROM ( SELECT return_year, return_day,
                                       evaluate_metric(return_lines) AS return_lines
                                FROM store_return_metrics
                                GROUP BY return_year, return_day ) days
                         WHERE return_lines > 0
                         GROUP BY return_year ) d
            ON d.return_year = y.return_year
    CONTEXT ('formatted' = 'yes');

CREATE OR REPLACE VIEW store_returns_yoy
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Store returns per calendar year with the change against the year before, in percent. NULL when there is no year before or its figure is 0. A year whose first_day is not 1 January or whose last_day is not 31 December is partial, and so is a change from it or to it: the previous year''s coverage is on the row too.'
    PRIMARY KEY ( 'return_year' )
    AS SELECT c.return_year,
              c.return_amount,
              CAST(ROUND(100 * (c.return_amount - p.return_amount) / NULLIF(p.return_amount, 0), 2) AS decimal(9,2)) AS return_amount_change_pct,
              c.returning_customers,
              CAST(ROUND(100.0 * (c.returning_customers - p.returning_customers) / NULLIF(p.returning_customers, 0), 2) AS decimal(9,2)) AS returning_customers_change_pct,
              c.first_day,
              c.last_day,
              p.first_day AS previous_first_day,
              p.last_day  AS previous_last_day
       FROM store_returns_by_year c
            LEFT OUTER JOIN store_returns_by_year p
            ON p.return_year = c.return_year - 1
    CONTEXT ('formatted' = 'yes');
```

- **The year before is a join on `return_year - 1`, not `LAG`.** `LAG` reads the previous row, so a
  year with no rows compares two years apart; and over a source that cannot run windows it fails
  unless the server moves the data to an MPP or the cache. The quarter or month before crosses
  the year: number the periods — `<year> * 4 + <quarter>`, `<year> * 12 + <month>`
  (`GETQUARTER(<date>)` gives the quarter) — and join on that number minus one.
- **A partial period makes its change meaningless**, and every total check still passes. Data
  that starts in the middle of a year or stops in the middle of a month gives a first and a last
  period shorter than the others, compared with full ones. The coverage of both years is on every
  row — a full year compared with a partial one looks clean on its own dates. Put the coverage you
  measured in the `DESCRIPTION` and in the answer; the like-for-like figure is the next template,
  the same days of both years, as of the last date with data.
- **The coverage query reads the metric** (`WHERE return_lines > 0`). A query over a selection that
  uses none of its metric columns — a `MIN` of the date, a `COUNT(*)` — runs as a query of
  dimensions only and lists every member of the dimension view: the coverage came back as the
  calendar's, 1 January to 31 December of every year — *verified: 9.5.1 (live, 2026-10-06)*. The
  same holds for a consumer's query of a view like `store_returns_by_year` that names only its
  date columns; the coverage subquery is safe because its own `WHERE` reads the metric. A date
  dimension taken from the fact itself has no members without facts, and lists only those. A metric
  view of your own can carry the coverage as metrics — `MIN(<fact>.<date>)`, `MAX(…)` — read per
  period like any other.
- **`ROUND` keeps the scale the server gave the decimal** — over a database a sum came back with
  twenty decimals and a percentage over it with six: `21.24` printed `21.240000`, a zero `0E-20` in
  some clients. `CAST(ROUND(x, 2) AS decimal(9,2))` for a figure a person reads: `ROUND` first,
  then the cast; a `100.0 *` for a count divided by a count (`SKILL.md`, the dialect rules).
- `WHERE return_year IS NOT NULL` keeps the undated lines out of every year; how many there are is
  the `NULL` row of the same selection without the filter — say it in the `DESCRIPTION`.

## To date, against the same days of last year

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW store_returns_ytd
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Store returns from 1 January to yesterday, against the same days of the year before (29 February compared with 28 February). One row; the amounts are 0 when no return falls in a window. last_return_day is the last day up to as_of with a return: earlier than as_of means the data is not loaded that far.'
    AS SELECT ADDDAY(CURRENT_DATE, -1) AS as_of,
              d.last_return_day,
              COALESCE(t.return_amount, 0) AS return_amount_ytd,
              COALESCE(l.return_amount, 0) AS return_amount_last_ytd,
              CAST(ROUND(100 * (COALESCE(t.return_amount, 0) - l.return_amount) / NULLIF(l.return_amount, 0), 2) AS decimal(9,2)) AS return_amount_change_pct
       FROM ( SELECT evaluate_metric(return_amount) AS return_amount
              FROM store_return_metrics
              WHERE return_year = GETYEAR(ADDDAY(CURRENT_DATE, -1))
                AND return_day <= ADDDAY(CURRENT_DATE, -1) ) t
            CROSS JOIN ( SELECT evaluate_metric(return_amount) AS return_amount
                         FROM store_return_metrics
                         WHERE return_year = GETYEAR(ADDDAY(CURRENT_DATE, -1)) - 1
                           AND return_day <= ADDYEAR(ADDDAY(CURRENT_DATE, -1), -1) ) l
            CROSS JOIN ( SELECT MAX(return_day) AS last_return_day
                         FROM ( SELECT return_day, evaluate_metric(return_lines) AS return_lines
                                FROM store_return_metrics
                                WHERE return_day <= ADDDAY(CURRENT_DATE, -1)
                                GROUP BY return_day ) days
                         WHERE return_lines > 0 ) d
    CONTEXT ('formatted' = 'yes');
```

- **"Today" is the server's clock, not the data's.** Over data whose last loaded day is weeks old,
  this view answers `0` against last year's figure — a fall of 100 %, with no error; a feed a few
  days late shows as a fall of that many days. `last_return_day` puts the last date with data on
  the row: say in the answer when it is older than the as-of date. A comparison of the data as it
  stands puts that date, as a literal, where the template has `ADDDAY(CURRENT_DATE, -1)`.
  `CURRENT_DATE` is the Denodo server's date, sent as a value where the condition is delegated
  (SQL Server and PostgreSQL measured); a database that evaluates it itself may read its own clock
  (VQL Guide, Datetime Functions; `/denodo:vql`, `references/dialect.md`, time zones).
- **Check it at dates you choose**: the view's `SELECT` with `CURRENT_DATE` replaced by a literal —
  the last day with data, a 31st, 29 February, 1 January — against plain SQL over the fact for the
  same windows. Through the view itself only today can be read.
- **A query of metrics only always returns one row**, so a `CROSS JOIN` of windows never loses the
  row: over no rows a count is `0` and a sum is `NULL` — hence the `COALESCE` outside the metric,
  in the view (inside it is dropped) — *verified: 9.5.1 (live, 2026-10-06)*.
- "So far" — up to yesterday or including today's partial day — is the human's choice; a morning
  report usually means yesterday — the server's yesterday: a job firing at 08:00 in a zone ahead
  of the server's reads the day before that. `as_of` on the row shows which day it read. `ADDYEAR` and `ADDMONTH` clamp to the last day of a shorter
  month: `2016-02-29` minus a year is `2015-02-28`, `2017-03-31` minus a month is `2017-02-28`.
- Month to date is the same view with `return_month` added to both windows' conditions; the
  same days of last month, `ADDMONTH(…, -1)` — and its month and year, which differ in January.
  Over a metric view with only a date, a range on it is each window and January needs nothing:
  `<date> >= FIRSTDAYOFMONTH(ADDDAY(CURRENT_DATE, -1)) AND <date> <= ADDDAY(CURRENT_DATE, -1)`.
  "The same days of last month" at a month's end is literal — the 30th of April against the 1st
  to the 30th of March: say it, the human may want the whole month.

## Running total within a year

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW store_returns_by_month
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Store returns per month, from the metrics of store_return_metrics. One row per month with returns.'
    PRIMARY KEY ( 'return_year', 'return_month' )
    AS SELECT return_year, return_month, evaluate_metric(return_amount) AS return_amount
       FROM store_return_metrics
       WHERE return_year IS NOT NULL
       GROUP BY return_year, return_month
    CONTEXT ('formatted' = 'yes');

CREATE OR REPLACE VIEW store_returns_running
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Store returns per month with the running total from January of the same year. One row per month with returns.'
    PRIMARY KEY ( 'return_year', 'return_month' )
    AS SELECT c.return_year, c.return_month, c.return_amount,
              SUM(p.return_amount) AS return_amount_ytd
       FROM store_returns_by_month c
            INNER JOIN store_returns_by_month p
            ON p.return_year = c.return_year AND p.return_month <= c.return_month
       GROUP BY c.return_year, c.return_month, c.return_amount
    CONTEXT ('formatted' = 'yes');
```

- **A running total of a sum or a count adds the periods up**; of a distinct count it does not —
  "customers so far this year" is the metric over the window from 1 January, as in the previous
  template, not a sum of months.
- The join runs over any source. Over a metric view whose sources are in one database the window
  form runs there too — `SUM(return_amount) OVER (PARTITION BY return_year ORDER BY return_month)`
  over the selection, the whole query one `SQLSentence` — but order it by a number or a date: by a
  text label (`FORMATDATE('yyyy-MM', …)`) SQL Server refuses it, `ORDER BY list of RANGE window
  frame …`, unless the frame is `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` — *verified:
  9.5.1 (live, 2026-10-06)*, SQL Server. Over files, on a server not set up to move the data to an
  MPP or the cache, it was `Function sum is not executable`.
- A month with no returns has no row, so the running total of a chart skips it; when the human
  wants every month, take the months from the calendar view and `LEFT OUTER JOIN` the totals.

## Checks

- **Coverage before any change is read**: `first_day` / `last_day` per period, against the full
  period.
- **The totals of the comparison add up to the metric**: the sum of `return_amount` over
  `store_returns_by_year` plus the `NULL` period equals the metric with no dimension (`SKILL.md`,
  the totals check); a distinct count does not add up, by definition.
- **Each change against plain SQL** over the fact for the same two periods — one `FULL OUTER
  JOIN`, keeping the rows that differ beyond a tolerance; then the same comparison with one
  figure deliberately altered must return rows, or the comparison is not looking at anything.
