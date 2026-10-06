# The Scheduler REST API, as this skill uses it

The administration tool of Denodo Scheduler serves the API at
`<web container>/webadmin/denodo-scheduler-admin/public/api/…`, and its own description at
`…/denodo-scheduler-admin/v3/api-docs` (OpenAPI, readable without logging in). Every call needs the `uri` query parameter — the Scheduler server as the
administration tool reaches it, `//<host>:8000` by default — and HTTP Basic with a Virtual
DataPort account; `api --server scheduler` adds both from the profile (`scheduler_url`,
`scheduler_uri`; without them the origin of `marketplace_url` and `//<host>:8000`). The tool
refuses a path with a `..` segment. *Everything below: verified: 9.5.1 (live, 2026-10-05),
unless it says documentation.*

## Calls

| Call | What it does | Notes |
|---|---|---|
| `GET /public/api/me` | the user, its Scheduler roles and permissions, the server version and mode | `env check` reads it |
| `GET /public/api/dataSources` | every data source of every project | `type`, `id`, `projectName`, `login`, `connectionURI`; the password is write-only |
| `GET /public/api/projects` | every project, a list | `--param expand=job,dataSource` adds them |
| `GET /public/api/projects?name=<p>` | that project, **one object** | `404 There is no instance of the resource with identifier '<p>'` |
| `POST /public/api/projects` | creates a project | body `{"name": …, "description": …}`; answers `201` with `id` |
| `DELETE /public/api/projects/{p}` | deletes the project, its jobs and their reports | `204` |
| `GET /public/api/projects/{p}/jobs` | the jobs of a project | `?type=VDP` / `VDPCache` filters |
| `POST /public/api/projects/{p}/jobs` | creates a job | answers `201` with the job and its `id`; same name in the project → `422` |
| `GET /public/api/projects/{p}/jobs/{j}` | the job as the server keeps it | the read-back |
| `PUT /public/api/projects/{p}/jobs/{j}` | **replaces** the job | needs `id`, `handlerSection` and, on a VDP job, `exportationSection`; a section left out is emptied |
| `DELETE /public/api/projects/{p}/jobs/{j}` | deletes the job and its reports | `204`. The documentation: a job that depended on it is disabled |
| `PUT /public/api/projects/{p}/jobs/{j}/status` | `{"action": "start" \| "stop" \| "enable" \| "disable" \| "start_with_state" \| "start_with_dependencies"}` | `204`; `start` of a disabled job → `500` |
| `PUT /public/api/projects/{p}/jobs/status` | the same for `{"action": …, "IDs": "1,2"}` | |
| `GET /public/api/projects/{p}/jobs/{j}/status` | `state`, `result`, `previousExecution`, `nextExecution` (UTC), counts | no `result` while it runs |
| `GET /public/api/jobs/status` | the same for every job | `?jobIDs=1,2` |
| `GET /public/api/projects/jobs/status?projectName=<p>&jobName=<j>` | one job's status by names | |
| `GET /public/api/jobs` | every job of every project | a `?projectId=` parameter is ignored |
| `GET /public/api/jobs/vdpcache_data?viewName=<db>.<view>` | the cache jobs that load that view | exact `<db>.<view>`; the bare name answers `[]` |
| `GET /public/api/projects/{p}/jobs/{j}/reports?start=0&count=5` | the runs, newest first | `start` and `count` required; `{list, hasMore, total}` |
| `GET /public/api/projects/{p}/jobs/{j}/reports/summary` | the runs with their counts | |
| `POST /public/api/projects/jobs/validateCronExpressions` | body: a JSON list of expressions | one string each, `""` = valid |
| `GET /public/api/meta/defaultConfig/job/VDPCache`, `…/job/VDP`, `…/exporter/CSV` | the defaults a new element gets | the source of the defaults below |

Left to the administration tool: data sources (`…/dataSources`, `…/csvDataSources`, keytab and
cloud sources — they take passwords and key files), `draftJobs`, Data Load, DAG and indexer
jobs, `configuration/*`, `tool-configuration/*`, `roles`, `drivers`, `plugins`,
`serverMetadata/export|import` (an import replaces every project, job and data source), the
deletion of reports. The plugin's tool classifies them anyway: `PUT` of configuration and
`POST` of drivers and plugins as `setting`, roles and passwords as `security`, the metadata
import as `replace`, report deletions as `delete`.

## A cache job (`VDPCache`, *Simple Cache Management*)

| Field | Default (`defaultConfig`) | Meaning |
|---|---|---|
| `extractionSection.dataSourceID` | — | a VDP data source of any project |
| `extractionSection.jobConcurrencyLevel` | — | load processes run at once |
| `loadprocesses[].viewName` | — | `<db>.<view>` |
| `loadprocesses[].loadProcessName` | — | required by the run; unique in the job |
| `loadprocesses[].parameterizedQuery` | — | the load query, `select * from <db>.<view>` (+ ` where …`); the administration tool builds it from the view and the conditions; `""` is dropped |
| `loadprocesses[].cacheInvalidationMode` | **`NONE`** | `NONE` appends, `ALL_ROWS` replaces everything, `MATCHING_ROWS` the rows the query returns (without a condition: everything), `MATCHING_PK` updates by primary key and inserts the rest — offered only for a view with a key |
| `loadprocesses[].cacheAtomicOperation` | `true` in the defaults, **`false` when a create leaves it out** | invalidation and load in one transaction |
| `loadprocesses[].cacheLoadOnError` | `false` | keep the rows of a load that failed |
| `loadprocesses[].cacheContextOpts` | — | more `CONTEXT` parameters, not the six the job sets itself |
| `loadprocesses[].incrementalFieldName`, `incrementalFieldSource` | `VDP` in the defaults, `SCHEDULER` when a create leaves it out | an incremental load on a "modified since `@LAST_REFRESH_DATE`" field — administration tool |
| `loadprocesses[].sourcesNotChange` | `true` in the defaults, `false` when a create leaves it out | for parameterized load queries |

The query a run sends: `select * from <db>.<view> CONTEXT('cache_preload'='true',
'cache_wait_for_load'='true', 'cache_return_query_results'='false', 'cache_invalidate'='all_rows',
'cache_atomic_operation'='true') TRACE`. Measured on a three-row view: with `NONE`, 3 cached rows
after the first run and 6 after the second, both runs `COMPLETE` with `cachedDocs: 3`; with
`ALL_ROWS`, 3 and 3; with `MATCHING_ROWS` after a row was deleted from the source, 2 — the
deleted row went too. Over a view without a cache the run is `WARNING`, `extractedDocs: 2`,
`cachedDocs: 0`, `The cache is not configured for the selected view and no tuples have been
cached in its subviews`. Its report's virtual exporter is `CacheLoader`.

## A VDP job (`VDP`, *Individual Query*)

| Field | Meaning |
|---|---|
| `extractionSection.dataSourceID` | a VDP data source; the statement runs in the database of its `connectionURI`, as its `login` |
| `extractionSection.extractionData.parameterizedQuery` | one VQL statement; `@name` and `@{name}` are variables, `\@ \\ \^ \{ \}` the literal characters |
| `extractionData.fields`, `maxIterations`, `concurrencyLevel` | values for the variables from a CSV, a list or a query — administration tool |
| `exportationSection.exporters[]` | what is done with the rows; empty for a statement whose rows nobody needs |
| `exportationSection.transactionality` | `NONE`, `EXPORTATION`, `EXTRACTION_AND_EXPORTATION` — for JDBC exporters |

The rows carry, besides the query's columns, `_$job_project`, `_$job_name`, `_$job`,
`_$job_start_time`, `_$job_retry_start_time`, `_$job_retry_count` — exported only with
`exportInternalFields: true` (documentation). A `CALL` and a `SELECT` over a procedure run;
`ALTER VIEW <db>.<view>` does not parse; `REFRESH <db>.<table>` parses.

## The CSV exporter

| Field | Default (`defaultConfig`) | Measured |
|---|---|---|
| `fileName` | `@{projectName}_@{jobName}_@{jobID}_CSVExporter#@{exporterID}.csv` | relative → `<DENODO_HOME>/work/scheduler/data/csv/` on the Scheduler host; absolute → that path |
| `createNewFile` | `true` | the start time of the run is added to the name: a new file every run |
| `overwriteFile` | `false` | `true` with `createNewFile: false`: one file, replaced by each run |
| `appendFile` | `false` | |
| `allowEmptyFile` | `false` | `false` + no rows: the file the previous run wrote is **deleted**; `true`: a header-only file |
| `includeHeader` | `false` | no header line |
| `exportInternalFields` | `false` | |
| `separator` | `,` | `;` for a file Excel opens directly (documentation) |
| `encoding` | `UTF-8` | BOM variants exist |
| `quoteFieldsOption` | `WHEN_REQUIRED` (RFC 4180) | |
| `filter` | `NONE` | required: `400 Validation error` without it |
| `i18n`, `mappings`, `exportOnlyMappings` | — | date and number format; renaming columns |

A run's report: `exportedDocs: {"CSVExporter0": n}` and `exporterResources: {"CSVExporter0":
["<full path>"]}`; the index is the exporter's position.

## Status and reports

Status: `state` — `NOT_RUNNING`, `RUNNING`, `DISABLED`, `WAITING` (for a dependency), `DRAFT`,
`POLLING` (a trigger condition); `result` of the last run — `COMPLETE`, `WARNING`, `ERROR`,
`STOPPED`, `NEVER_EXECUTED`, `MISFIRED` (it was due while the server was down); `nextExecution`
in UTC, absent when disabled or without a trigger.

A job created without `reportSection` stores `{}`; the run's own report exists either way, and
a `PUT` may come back with `reportConfig` filled in (`maxIndividualReports: 100`,
`reportOnlyErrors: true`).

A run's report: `startTime`, `endTime` (UTC), `result`, `extractedDocs`, `cachedDocs`,
`exportedDocs`, `exporterResources`, `extractorErrors`, `extractorWarnings`,
`initializationErrors` (the job's own configuration), `generalErrors`, `exporterErrors`,
`handlerErrors`, `triggerConditionErrors`, `sourcesErrors`, `query`, and `reports[]` with one
entry per load process or query. The report exists only once the run has ended. The
`timestamp` of an error answer is in a 12-hour format without AM/PM — never read a time from it.

## Deleting a job

```bash
# verified: 9.5.1 (live, 2026-10-06)
# 1. the project, then the job by its exact name inside it
api --server scheduler get /public/api/projects --param name=sales_analytics --env dev
api --server scheduler get /public/api/projects/<project_id>/jobs --env dev
# 2. what goes with it, kept in the project's folder: the job as the server has it, and its runs
api --server scheduler get /public/api/projects/<project_id>/jobs/<job_id> --env dev
api --server scheduler get /public/api/projects/<project_id>/jobs/<job_id>/reports --param start=0 --param count=100 --env dev
# 3. after the yes
api --server scheduler delete /public/api/projects/<project_id>/jobs/<job_id> --env dev
# 4. the project's jobs without it
api --server scheduler get /public/api/projects/<project_id>/jobs --env dev
```

- **The job by its exact name inside the named project.** A name is unique only in its project:
  the same name in another project is another team's job, and a name that only starts the same
  (`…_v2`) is another job — take the `id` of the exact match, and check it again right before
  the `DELETE`.
- **What goes**: the job and every report of it — the only history of its runs. Step 2's answers,
  saved as `scheduler/<project>/<job>.json` and `<job>.reports.json`, are what is left; the job's
  `GET` re-creates it, under a new id and without its history.
- **What stays**: the file an export wrote on the Scheduler host — still there after the delete
  (measured); the cache the job loaded and the table it refreshed. A job that waited on this one
  is disabled (documentation). Say each in the message.
- A job `RUNNING` in `status` is stopped first (`stop`, the skill's "Stop, enable, disable").
  `disable` keeps the job and its reports and is undone by `enable`: offer it beside the delete
  when the human may want the job back.
- Deleting a job is always the human's yes, a job of this session included: the message names the
  job, its project and id, what each run does, its next run, and what goes and what stays. The
  `DELETE` answers `204`; the job's `GET` then answers `404`, which the tool reports as `ok:
  false` — the answer wanted here.

## Triggers

`triggerSection.triggers[]`: `{"type": "cron", "cronExpression": …, "startTime", "endTime",
"dependencyInfo"}` — no time zone. The cron is Quartz (six fields and an optional year, `?` in
one of the two day fields; `L`, `W`, `#` as in Quartz) and fires on the Scheduler server's
clock. `startTime` and `endTime` bound the period the trigger is active in. Several triggers
fire the job at each of their times.

Dependencies (documentation; left to the administration tool): a trigger with
`dependencyInfo.jobIDs` waits for those jobs to finish successfully, unless
`executeAnyway`; the dependent job has to **start first** — if the job it waits for starts
earlier, the dependent waits for its next run.
