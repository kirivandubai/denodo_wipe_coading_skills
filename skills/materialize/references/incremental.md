# Incremental loads: only what is new or changed since the last load

A table loaded with `REFRESH` is emptied and reloaded every time. When that takes too long, the
load becomes incremental: each run writes only the rows that are new or changed since the last
one. In VQL that is one statement, an upsert through the table's base view
(`/denodo:dml`, "Rows from another view"), and a Scheduler job runs it (`/denodo:scheduler`).

The example keeps `bv_dwh_orders` — a remote table this session created as a copy of the ERP's
`bv_erp_orders` (`order_id` the key, `updated_at` set on every change) — up to date.

## Before the first run: what it will write

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

-- 1. The watermark, and the source rows on each side of it.
SELECT t.watermark,
       SUM(CASE WHEN e.updated_at > t.watermark THEN 1 ELSE 0 END)  AS after_watermark,
       SUM(CASE WHEN e.updated_at = t.watermark THEN 1 ELSE 0 END)  AS at_watermark,
       SUM(CASE WHEN e.updated_at IS NULL THEN 1 ELSE 0 END)        AS without_updated_at
FROM bv_erp_orders e
     CROSS JOIN ( SELECT MAX(updated_at) AS watermark FROM bv_dwh_orders ) t
GROUP BY t.watermark;

-- 2. Keys the copy has and the source no longer has: an upsert never removes them.
SELECT COUNT(*) AS gone_from_source
FROM bv_dwh_orders d
     LEFT OUTER JOIN bv_erp_orders e ON e.order_id = d.order_id
WHERE e.order_id IS NULL;
```

- **`at_watermark` is why the load reads `>=`, not `>`.** A row committed in the same second as the
  last one loaded, after that load read the source, has the watermark's own time: `>` never loads
  it. With an upsert, reading the last second again rewrites a few rows and harms nothing.
- **`without_updated_at` rows are invisible to any watermark**, however the source is described.
  The load reads them every run (`OR updated_at IS NULL`); say how many, and ask the source's
  owner.
- **`gone_from_source`** is what a full reload removed and an incremental load never will: deleted
  orders stay in the copy. Keeping them, a nightly delete of the keys gone, or a periodic full
  `REFRESH` is the human's choice; say it before the first run, not after.

## The load

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

INSERT INTO bv_dwh_orders ON DUPLICATE KEY ( order_id ) UPDATE
SELECT e.order_id     AS order_id,
       e.customer_id  AS customer_id,
       e.order_amount AS order_amount,
       e.status       AS status,
       e.updated_at   AS updated_at
FROM bv_erp_orders e
WHERE e.updated_at >= ( SELECT COALESCE(MAX(d.updated_at), TIMESTAMP '1900-01-01 00:00:00')
                        FROM bv_dwh_orders d )
   OR e.updated_at IS NULL;
```

- **An upsert, not an `INSERT`.** A changed row is a row whose key is already in the copy: a plain
  `INSERT … WHERE updated_at > <watermark>` added the changed orders a second time — the copy then
  had more rows than keys, no error — and missed the rows at the watermark and without a date
  (measured). A table `CREATE_REMOTE_TABLE` made has no primary key in its database, so nothing
  refuses the duplicate; `ON DUPLICATE KEY ( order_id )` names the key, declared or not.
- **The watermark is the copy's own latest `updated_at`**, read in the same statement: a failed
  run leaves it where it was, and the next one picks up from there. `COALESCE` makes the run over
  an empty copy a full load — `MAX` over no rows is `NULL`, and `>= NULL` loads nothing, without an
  error. Not `@LAST_REFRESH_DATE`: that is the cache's load time, not the data's — and in a
  Scheduler job `@` starts a variable (`\@`, `/denodo:scheduler`).
- **Run twice, the same result**: a second run right after the first rewrites only the rows at the
  watermark and the undated ones, and changes no count — measured with the source and the copy in
  one SQL Server database.
- One statement: a Scheduler job runs exactly one (`/denodo:scheduler`, "Run one statement on a
  schedule"); its data source connects to one database, so name every view with its database
  there — `INSERT INTO sales_analytics.bv_dwh_orders …`.
- The copy's `DATA_LOAD_QUERY` stays the full load: `REFRESH` remains the way to rebuild it, and the
  undo of a bad incremental run.

## After a run

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

-- 1. One row per key: no rows.
SELECT order_id, COUNT(*) AS copies FROM bv_dwh_orders GROUP BY order_id HAVING COUNT(*) > 1;

-- 2. The copy against the source: keys missing from the copy, and rows that differ.
SELECT SUM(CASE WHEN d.order_id IS NULL THEN 1 ELSE 0 END) AS missing_from_copy,
       SUM(CASE WHEN d.order_id IS NOT NULL
                 AND ( e.status <> d.status OR e.order_amount <> d.order_amount
                       OR e.updated_at <> d.updated_at ) THEN 1 ELSE 0 END) AS differing
FROM bv_erp_orders e
     LEFT OUTER JOIN bv_dwh_orders d ON d.order_id = e.order_id;
```

Both `0` after a good run, and `gone_from_source` from the first block unchanged. A Scheduler job
that runs the load reports `COMPLETE` with `extractedDocs: 0` — the report carries no count of
the rows written (measured): these two reads are how the morning after is checked.

## Who runs it

- **The copy you created in this session**: the load, and a job running it, are yours — the same
  table its `REFRESH` already is (`SKILL.md`, the rule). Create the job disabled, read it back,
  run it once now and these checks, then enable it.
- **A table older than this session**: every run writes into it — the yes, to the statement and to
  the job, as for its `REFRESH`.
- **The job that does the full reload today** goes off before the incremental one goes on — a
  `REFRESH` and an upsert at the same hour race each other, and the `REFRESH` empties the table
  under the upsert. That job is its owner's: name it in the message, with the call that disables
  it. Two jobs loading one table is the question of `/denodo:scheduler`, step 4.
- Schedule it after the source's own load, and tell the human that a failed run says nothing by
  itself: mail handlers are the Scheduler administration tool's.

A summary's incremental refresh (`CUSTOM LOAD QUERY` with `LAST_DATE_REFRESH`) is
`references/summaries.md`; an incremental cache load (`'@LAST_REFRESH_DATE'`, `'matching_pk'`)
stays in Design Studio (`/denodo:cache`).
