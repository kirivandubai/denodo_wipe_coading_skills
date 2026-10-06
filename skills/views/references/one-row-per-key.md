# One row per key: the current row, the latest version, a feed loaded twice

"The last known address of each patient", "the current version of each store", "the
feed arrives twice — de-duplicate it": each is a choice of one row per key among several. What
decides the statement is what the data carries and where the view runs:

| The data has | Write | Runs over |
|---|---|---|
| a validity column — the current row has no end date | `WHERE <end> IS NULL` (the first template) | any source |
| an order between versions — a date, a load number | `ROW_NUMBER()` in a subquery, `WHERE <rank> = 1` outside (the second) | a view over one database |
| the same order, over a file or over two data sources | the anti-join: keep the row nothing newer replaces (the third) | any source |

**The current row and the latest version are different answers.** A key whose last version was
closed — a store shut, a contract ended — has a latest version and no current row. Say which one
the view gives in its `DESCRIPTION`, and count the keys that differ (Checks, 4). When the rows of
a key are not versions of one thing but several things at once — a customer's subscriptions, an
account's cards — "current" can also mean the latest one in a given state: that condition goes
**inside** the subquery, before the rank, and it is a different view. Name the reading you built,
count the keys where the other one differs, and say both in the answer.

**A key with no row at all is not in any of these views.** "Every customer" — those without a
subscription too — starts from the view of the keys and `LEFT OUTER JOIN`s the chosen rows to it;
count the keys left without one and say it.

The examples are integration views (`iv_`, `/02 - integration`) for a business view to build on.
When the consumer reads the result directly, it is the `/03 - business entities` view with the
bare name (`SKILL.md`, Naming).

The examples read `bv_store`, a base view over the TPC-DS store dimension (`/denodo:datasources`):
one row per version of a store, `s_store_id` the business key, `s_store_sk` the surrogate key of
the version, `s_rec_start_date` and `s_rec_end_date` its validity, `localdate`.

## The current row of a history

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW iv_store_current
    FOLDER = '/02 - integration'
    DESCRIPTION = 'The current version of each store: the version of bv_store whose validity has no end. A closed store has no row. One row per store_id.'
    PRIMARY KEY ( 'store_id' )
    AS SELECT s_store_id         AS store_id,
              s_store_sk         AS store_sk,
              TRIM(s_store_name) AS store_name,
              s_rec_start_date   AS valid_from
       FROM bv_store
       WHERE s_rec_end_date IS NULL
    CONTEXT ('formatted' = 'yes');
```

- **The filter is the whole recipe, and the key check is the whole proof**: two open versions of
  one key are a defect of the source, and the view passes them on with no error. Checks 1 before
  you publish it.
- In a file the empty end date is an empty field; a `localdate` column reads it as `NULL`. A text
  column reads it as `''` — `WHERE s_rec_end_date IS NULL` then finds nothing. Read the type off
  `vql desc` of the base view.

## The latest version, in the database

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW iv_store_latest
    FOLDER = '/02 - integration'
    DESCRIPTION = 'The latest version of each store, closed stores included: the latest s_rec_start_date, a version without one ranked last, and on the same start date the higher s_store_sk. One row per store_id.'
    PRIMARY KEY ( 'store_id' )
    AS SELECT store_id, store_sk, store_name, valid_from, valid_to
       FROM ( SELECT s_store_id         AS store_id,
                     s_store_sk         AS store_sk,
                     TRIM(s_store_name) AS store_name,
                     s_rec_start_date   AS valid_from,
                     s_rec_end_date     AS valid_to,
                     ROW_NUMBER() OVER ( PARTITION BY s_store_id
                                         ORDER BY CASE WHEN s_rec_start_date IS NULL THEN 1 ELSE 0 END,
                                                  s_rec_start_date DESC,
                                                  s_store_sk DESC ) AS version_rank
              FROM bv_store ) ranked
       WHERE version_rank = 1
    CONTEXT ('formatted' = 'yes');
```

Over a base view of a database (JDBC): the window, the filter and everything above go to the
database as one `SQLSentence` — *verified: 9.5.1 (live, 2026-10-06)*, SQL Server.

- **The rank is filtered outside, around a subquery.** `QUALIFY` is a syntax error (`near
  'ROW_NUMBER'`), and a `WHERE` cannot name an alias of its own `SELECT`.
- **The `ORDER BY` ends with a column unique per row** — the surrogate key, the line's id. Without
  it the database picks among versions with the same date, and the pick can change between runs.
  `RANK()`, or a `MAX(<date>)` joined back, keeps both tied rows: two rows for the key, no error.
  A time read from text orders only as a `timestamp`: `TO_LOCALDATE('yyyy-MM-dd HH:mm:ss', s)`
  returns the date alone, and every change of one day becomes a tie — `TO_TIMESTAMP`, or the
  `timestamp` type in the base view (*verified: 9.5.1 (live, 2026-10-06)*).
- **A `NULL` in the ordering column sorts where the database puts it**: on `DESC`, PostgreSQL puts
  it first — the undated version wins — and SQL Server last. `NULLS FIRST` / `NULLS LAST` is
  accepted after `ASC` or `DESC` and does nothing: it is left out of the SQL sent to the
  database, and a file sorted by Denodo ignores it too (without `ASC`/`DESC` it is a syntax
  error) — *verified: 9.5.1 (live, 2026-10-06)*, PostgreSQL and SQL Server. The `CASE` flag in
  the template is what decides; keep it even over a column with no `NULL`s today.
- **A consumer's filter stays above the window**: a `WHERE` on any column over such a view gives
  the keys whose latest version matches it — not the latest of the matching versions. The plan
  shows the filter on the outer query of the `SQLSentence` and the window inside.
- **Where it runs.** Over one data source, in its database. Over a join of two data sources, only
  when Denodo can put the window on one side — partitioned by the join key and ordered by that
  side's columns: the plan then says `optimizationsApplied = [Analytic Functions Push-down]`.
  Anywhere else — over a file, over `Dual()` — unless the server sends window functions to an MPP
  engine or moves the data for them (documentation), the view is created, `GET_VIEWS()` says
  `OK`, and every `SELECT` fails with `Function row_number is not executable`. The next
  template runs everywhere.

## The latest version, from a file

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW iv_store_latest
    FOLDER = '/02 - integration'
    DESCRIPTION = 'The latest version of each store, closed stores included: the latest s_rec_start_date, a version without one ranked last, and on the same start date the higher s_store_sk. One row per store_id.'
    PRIMARY KEY ( 'store_id' )
    AS SELECT v.s_store_id         AS store_id,
              v.s_store_sk         AS store_sk,
              TRIM(v.s_store_name) AS store_name,
              v.s_rec_start_date   AS valid_from,
              v.s_rec_end_date     AS valid_to
       FROM bv_store v
            LEFT OUTER JOIN bv_store newer
            ON newer.s_store_id = v.s_store_id
               AND ( COALESCE(newer.s_rec_start_date, DATE '0001-01-01') > COALESCE(v.s_rec_start_date, DATE '0001-01-01')
                     OR ( COALESCE(newer.s_rec_start_date, DATE '0001-01-01') = COALESCE(v.s_rec_start_date, DATE '0001-01-01')
                          AND newer.s_store_sk > v.s_store_sk ) )
       WHERE newer.s_store_id IS NULL
    CONTEXT ('formatted' = 'yes');
```

A version is kept when no version of the same key is newer: a later date, or the same date and a
higher tie-breaker. It needs no window, so it runs over anything, and it is the same view as the
second template — same rows, same columns.

- **`COALESCE` to a date before any real one** — `TIMESTAMP '0001-01-01 00:00:00'` for a
  `timestamp` — ranks an undated version last and keeps a key whose versions are all undated. Without it every comparison with a `NULL` date is unknown: an undated
  version is never replaced, and stays beside the latest one.
- **The tie-breaker must be unique per row.** A file whose loads can be delivered twice holds
  identical lines; read it through a `SELECT DISTINCT <every column> FROM <base view>` view first
  (an `iv_` view with the key and the tie-breaker as its `PRIMARY KEY`, proved by Checks 1 on it),
  and join that view to itself — identical copies are otherwise each "not older" than the other
  and both stay. When nothing in the line is unique, the human decides what tells two versions
  apart; a line number the file does not carry does not exist.
- **Two orders — the time of the change and the number of the load — can disagree** when a load
  brings an older change late. Count the keys where they pick different rows: none, and the
  `DESCRIPTION` says the order and that both agree today; some, and which one wins is the human's.
- **The usual shortcut fails twice, quietly.** `MAX(<date>)` per key joined back on the date keeps
  both rows of a tie, and drops a key whose versions are all undated (`MAX` is `NULL`, and `NULL =
  NULL` is not true). Over data with both, the two errors cancel in `COUNT(*)`: measured on such a
  feed, the view had exactly as many rows as the input had keys, and fewer distinct keys. Checks 2
  compares three numbers for that reason.
- A rank key built as text — the date formatted, then the tie-breaker padded — orders correctly
  only when every part has a fixed width and the empty date maps below every real one (a `|`
  separator sorts after the digits). The anti-join needs neither.
- The file is read twice per query, and the join compares the versions within each key. A large
  feed is a question for `/denodo:cache` or `/denodo:materialize`, once the view is right.

## Checks

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

-- 1. One row per key: no rows.
SELECT store_id, COUNT(*) AS versions
FROM iv_store_latest
GROUP BY store_id
HAVING COUNT(*) > 1;

-- 2. Every key of the input is there, once: the three numbers are equal.
SELECT i.keys_in, o.rows_out, o.keys_out
FROM ( SELECT COUNT(DISTINCT s_store_id) AS keys_in FROM bv_store ) i
     CROSS JOIN ( SELECT COUNT(*) AS rows_out, COUNT(DISTINCT store_id) AS keys_out FROM iv_store_latest ) o;

-- 3. Nothing newer than what the view gives: 0.
SELECT COUNT(*) AS newer_versions
FROM iv_store_latest l
     INNER JOIN bv_store s ON s.s_store_id = l.store_id
WHERE s.s_rec_start_date > l.valid_from
   OR ( s.s_rec_start_date = l.valid_from AND s.s_store_sk > l.store_sk );

-- 4. Keys with a latest version and no current row: the closed ones.
SELECT l.store_id, l.valid_to
FROM iv_store_latest l
     LEFT OUTER JOIN iv_store_current c ON c.store_id = l.store_id
WHERE c.store_id IS NULL;
```

- 1 catches a doubled key, 2 also a lost one — a key check alone passes a view that lost keys.
- 3 is the check of the order itself, independent of how the view chose: over a database the
  same three numbers come from the anti-join run as a query, compared with the window's rows.
  When the ordering column has `NULL`s, add the cases 3 cannot see: `l.valid_from IS NULL AND
  s.s_rec_start_date IS NOT NULL`, and two undated versions, `l.valid_from IS NULL AND
  s.s_rec_start_date IS NULL AND s.s_store_sk > l.store_sk`.
- 4 lists what the two answers disagree on; its count goes into the `DESCRIPTION` of the view
  the consumer reads, with the date you measured it.
- The views stay valid only while `bv_store` keeps these columns ("Before a column changes" in
  `SKILL.md`), and a view built on another team's view is now among its dependants.
