# Incremental loads: only what is new or changed since the last load

A table loaded with `REFRESH` is emptied and reloaded every time. When that takes too long, the
load becomes incremental: each run writes only the rows that are new or changed since the last
one. In VQL that is one statement, an upsert through the table's base view
(`/denodo:dml`, "Rows from another view"), and a Scheduler job runs it (`/denodo:scheduler`).

The example keeps `bv_dwh_shipments` — a remote table this session created as a copy of the
transport system's `bv_tms_shipments` (`shipment_id` the key, `changed_at` set on every change) —
up to date.

## Before the first run: what it will write

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

-- 1. The watermark, and the source rows on each side of it.
SELECT t.watermark,
       SUM(CASE WHEN e.changed_at > t.watermark THEN 1 ELSE 0 END)  AS after_watermark,
       SUM(CASE WHEN e.changed_at = t.watermark THEN 1 ELSE 0 END)  AS at_watermark,
       SUM(CASE WHEN e.changed_at IS NULL THEN 1 ELSE 0 END)        AS without_changed_at
FROM bv_tms_shipments e
     CROSS JOIN ( SELECT MAX(changed_at) AS watermark FROM bv_dwh_shipments ) t
GROUP BY t.watermark;

-- 2. Keys the copy has and the source no longer has: an upsert never removes them.
SELECT COUNT(*) AS gone_from_source
FROM bv_dwh_shipments d
     LEFT OUTER JOIN bv_tms_shipments e ON e.shipment_id = d.shipment_id
WHERE e.shipment_id IS NULL;

-- 3. Changes under the watermark: rows older than it that differ from the copy. 0 is what makes
--    a watermark safe; any other number is a change the load will never see.
SELECT COUNT(*) AS changed_under_watermark
FROM bv_tms_shipments e
     INNER JOIN bv_dwh_shipments d ON d.shipment_id = e.shipment_id
     CROSS JOIN ( SELECT MAX(changed_at) AS watermark FROM bv_dwh_shipments ) t
WHERE e.changed_at < t.watermark
  AND ( COALESCE(e.shipment_status, '~') <> COALESCE(d.shipment_status, '~')
        OR COALESCE(e.weight_kg, -1) <> COALESCE(d.weight_kg, -1) );
```

- **`at_watermark` is why the load reads `>=`, not `>`.** A row committed in the same second as the
  last one loaded, after that load read the source, has the watermark's own time: `>` never loads
  it. With an upsert, reading the last second again rewrites a few rows and harms nothing.
- **`without_changed_at` rows are invisible to any watermark**, however the source is described.
  The load reads them every run (`OR changed_at IS NULL`); say how many, and ask the source's
  owner.
- **`gone_from_source`** is what a full reload removed and an incremental load never will: deleted
  shipments stay in the copy. Keeping them, a nightly delete of the keys gone, or a periodic full
  `REFRESH` is the human's choice; say it before the first run. The first run removes nothing
  and closes none of the three: when the human cannot answer, run it and put the question first
  in the message.
- **`changed_under_watermark`** above `0` is a source that changes rows without moving their
  `changed_at`: a watermark misses them for ever. Say so; the full `REFRESH` stays the load.
- The first run writes `after_watermark + at_watermark + without_changed_at` rows: that is the
  `affected` to expect.

## The load

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

INSERT INTO bv_dwh_shipments ON DUPLICATE KEY ( shipment_id ) UPDATE
SELECT e.shipment_id     AS shipment_id,
       e.carrier_id      AS carrier_id,
       e.weight_kg       AS weight_kg,
       e.shipment_status AS shipment_status,
       e.changed_at      AS changed_at
FROM bv_tms_shipments e
WHERE e.changed_at >= ( SELECT COALESCE(MAX(d.changed_at), TIMESTAMP '1900-01-01 00:00:00')
                        FROM bv_dwh_shipments d )
   OR e.changed_at IS NULL;
```

- **An upsert, not an `INSERT`.** A changed row is a row whose key is already in the copy: a plain
  `INSERT … WHERE changed_at > <watermark>` added the changed rows a second time — the copy then
  had more rows than keys, no error — and missed the rows at the watermark and without a date
  (measured). A table `CREATE_REMOTE_TABLE` made has no primary key in its database, so nothing
  refuses the duplicate; `ON DUPLICATE KEY ( shipment_id )` names the key, declared or not.
- **The watermark is the copy's own latest `changed_at`**, read in the same statement: a failed
  run leaves it where it was, and the next one picks up from there. `COALESCE` makes the run over
  an empty copy a full load — `MAX` over no rows is `NULL`, and `>= NULL` loads nothing, without an
  error. Not `@LAST_REFRESH_DATE`: that is the cache's load time, not the data's — and in a
  Scheduler job `@` starts a variable (`\@`, `/denodo:scheduler`).
- **Run twice, the same result**: a second run right after the first rewrites only the rows at the
  watermark and the undated ones, and changes no count — measured with the source and the copy in
  one SQL Server database.
- One statement: a Scheduler job runs exactly one (`/denodo:scheduler`, "Run one statement on a
  schedule"); its data source connects to one database, so name every view with its database
  there — `INSERT INTO sales_analytics.bv_dwh_shipments …`.
- The copy's `DATA_LOAD_QUERY` stays the full load: `REFRESH` remains the way to rebuild it, and the
  undo of a bad incremental run.

## After a run

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

-- 1. One row per key: no rows.
SELECT shipment_id, COUNT(*) AS copies FROM bv_dwh_shipments GROUP BY shipment_id HAVING COUNT(*) > 1;

-- 2. The copy against the source: keys missing from the copy, and rows that differ.
SELECT SUM(CASE WHEN d.shipment_id IS NULL THEN 1 ELSE 0 END) AS missing_from_copy,
       SUM(CASE WHEN d.shipment_id IS NOT NULL
                 AND ( COALESCE(e.shipment_status, '~') <> COALESCE(d.shipment_status, '~')
                       OR COALESCE(e.weight_kg, -1) <> COALESCE(d.weight_kg, -1)
                       OR COALESCE(e.changed_at, TIMESTAMP '1900-01-01 00:00:00')
                          <> COALESCE(d.changed_at, TIMESTAMP '1900-01-01 00:00:00') ) THEN 1 ELSE 0 END) AS differing
FROM bv_tms_shipments e
     LEFT OUTER JOIN bv_dwh_shipments d ON d.shipment_id = e.shipment_id;
```

Both `0` after a good run — the `COALESCE`s count a value missing on one side only, which `<>`
alone never does — and `gone_from_source` from the first block unchanged. A Scheduler job
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
  it. Two jobs loading one table is the question of `/denodo:scheduler`, step 4; when you cannot
  see what does the full reload, the incremental job stays disabled and the message says why.
- Whether the upsert runs in the database (a `MERGE`) or through a temporary table is not in any
  plan — `GET_QUERY_EXECUTION_PLAN` refuses an `INSERT`; time the first run.
- Schedule it after the source's own load, and tell the human that a failed run says nothing by
  itself: mail handlers are the Scheduler administration tool's.

A summary's incremental refresh (`CUSTOM LOAD QUERY` with `LAST_DATE_REFRESH`) is
`references/summaries.md`; an incremental cache load (`'@LAST_REFRESH_DATE'`, `'matching_pk'`)
stays in Design Studio (`/denodo:cache`).
