---
name: scheduler
description: Use when something in Denodo 9.5 has to happen on a schedule, or a scheduled run misbehaves — refreshing the cache of a view every night or every hour, running REFRESH of a remote table or a procedure at a set time, exporting a view to a CSV file every week or month, running a Denodo Scheduler job now, stopping, pausing or enabling it, reading what last night's run did or why it failed, "the cache doubles after every refresh", "the job fires at the wrong hour", "the export file is missing or has no header". Denodo Scheduler projects, jobs, cron triggers and reports, through the REST API of the Scheduler administration tool. Not for switching a cache on or loading it once (/denodo:cache), not for creating the remote table or summary itself (/denodo:materialize).
---

# Scheduled work: Denodo Scheduler jobs

**A job does its work with nobody watching.** It runs at 01:30 for months, and every decision
in it — which rows, which mode, which hour, which file — is made the day you create it. A
mistake there does not fail: the run reports `COMPLETE` while the cache doubles, the file
loses its header or the refresh fires four hours early.

Denodo Scheduler is a server of its own. Its channel is the REST API of its administration
tool, through the plugin's tool: `api --server scheduler <method> <path> --env dev`. The tool
signs every call with the profile's account and adds the `uri` parameter that names the
Scheduler server; `env check --env dev` shows under `scheduler` whether it answers and with
which roles. There is no VQL for Scheduler objects. Applying calls and reading their errors is
`/denodo:execute`; the working loop and the safety rule are `/denodo:vql`.

**Violating the letter of the rules below is violating their spirit.**

## What this skill covers

- **A cache job** (*Simple Cache Management*, `VDPCache`): reloads the full cache of named
  views on a schedule. The cache itself — on, off, a one-off load — is `/denodo:cache`.
- **A VDP job** (*Individual Query*, `VDP`): runs **one** VQL statement on a schedule —
  `REFRESH` of a remote table (`/denodo:materialize`), a `CALL`, or a `SELECT` whose rows a
  CSV exporter writes to a file on the Scheduler host.
- Running a job now, stopping, enabling and disabling it; its status and its reports; the jobs
  that already touch a view.

Everything else is set up by the human in the administration tool
(`<web container>/webadmin/denodo-scheduler-admin`): data sources — they hold a password —,
the other job types (Data Load, DAG cache load, indexer), exporters other than CSV (JDBC,
Excel, Elasticsearch, cloud storage), mail handlers, retries, trigger conditions, a query fed
with parameters from a source, dependencies between jobs, the server's configuration, roles,
import and export. Say so and stop.

## Before you create a job

All of these are reads:

1. **The Scheduler answers.** `env check --env dev` → `scheduler.ok: true`, and `roles`
   names a Scheduler role that may create jobs. `scheduler: null` means the profile names
   neither `scheduler_url` nor `marketplace_url` and the check was not tried:
   `api --server scheduler get /public/api/me --env dev` asks the default address.
2. **The VDP data source the job runs through.**
   `api --server scheduler get /public/api/dataSources --env dev` — every data source of every
   project; take those with `"type": "VDP"` and read `id`, `projectName`, `login` and
   `connectionURI`. **The job runs as `login`**, with that user's privileges, and its statement
   runs in the database at the end of `connectionURI`. A job may use a data source of another
   project — *verified: 9.5.1 (live, 2026-10-05)*. Which one is the human's choice when there
   are several; with one, use it and name its `login` in the message — `admin` means every run
   is an administrator's, with no privilege check. None, or none they accept → they create one
   in the administration tool (*Data sources → New → VDP*); it needs a password: never write one
   into a file or a call. One data source of a known project:
   `GET /public/api/projects/<project_id>/dataSources/<id>`.
3. **The project.** `api --server scheduler get /public/api/projects --param name=<project>
   --env dev` answers the project — one object, not a list — or `404`. Use the one the human
   names; when they name none, create one named after the VDP database (below).
4. **What already runs on the view.**
   `api --server scheduler get /public/api/jobs/vdpcache_data --param viewName=<db>.<view> --env dev`
   lists the cache jobs that load it — the name exactly as `<database>.<view>`; the bare view
   name answers `[]`. `api --server scheduler get /public/api/jobs --env dev` lists every job
   (one project: `GET /public/api/projects/<project_id>/jobs?type=VDP`): a VDP job naming the
   view is in its `extractionSection.extractionData.parameterizedQuery`, a job writing the same
   file in `exportationSection.exporters[].fileName`. A second job loading the same cache, or
   writing the same file, is a question for the human.
5. **The clock.** A trigger has no time zone: the cron fires on the clock of the Scheduler
   server, and `nextExecution` comes back in UTC (`…Z`). What shows that clock is an enabled
   job: its cron's hour against the hour of its `nextExecution`. An enabled job already on the
   server; or your own while its runs change nothing — a VDP job created **without** its
   exporter, enabled, its `nextExecution` read, disabled again before the exporter goes in by
   `PUT`; or your job the moment it is enabled after the yes. Otherwise the zone is the
   administrator's to tell, or your assumption, said as such in the message. An hourly cron does
   not care, unless the server is off by half an hour. Times in VQL results follow the session's
   i18n and say nothing about the Scheduler's clock.

## Who applies it

**A job is its statement, run every time it fires.** Whatever running that statement now would
need, enabling the job needs: reloading the cache of a view somebody reads is the yes of
`/denodo:cache`, `REFRESH` of a table older than this session the yes of
`/denodo:materialize`, writing over a file you did not create the human's word. A job created
**disabled** runs nothing, so creating it is yours — and it is how the server shows you the
job before anyone agrees to it.

| You do it yourself | Only after the human's yes |
|---|---|
| every `GET`; `POST …/validateCronExpressions` | — |
| a new project for the jobs of the request | deleting a project — its jobs and their reports go with it |
| **a new job created with `"disabled": true`**, read back, and changed while it is yours | **enabling it** — or creating it enabled — when its runs change anything that existed before this session: the cache of a view, a table, a file; the yes is to that job as the server read it back, its user and its hour |
| a new job created enabled, and run now, when everything its runs change was created by you in this session | **starting** any job whose run changes what existed before this session: the run is that load, that `REFRESH`, that write, now, for everyone who reads it |
| enabling, disabling, stopping or changing a job you created in this session, within the two rows above | **anything on a job that existed before this session** — `PUT`, `start`, `stop`, `enable`, `disable`, `DELETE` |
| — | deleting a job, yours included |
| — | **anything at all on a profile with `production: true`** |

What a job's statement changes, and whether you created it in this session, is what `vql plan
-e "<its statement>"` says (`own`, `needs_yes`); the ledger records no Scheduler job, so a job
you created is the one your `POST` returned. A file on the Scheduler host counts as existing unless you created it in this session: the API
cannot tell you whether it is there. A job of yours is judged by what its runs would change at
that moment: enabled while it only reads, it has to be disabled before a `PUT` gives it an
exporter that writes over such a file — then the yes enables it.

**The yes, asked for in this shape** — after the read-back, never before:

```
Job iv_household_income_cache, project sales_analytics — created disabled, read back.
Each run reloads the full cache of sales_analytics.iv_household_income (ALL_ROWS, one
transaction); readers: household_income_by_band (USED_BY) and <consumers the human named>.
Runs as: admin (VDP data source "VDP", //host:9999/admin).
Fires: 0 30 1 * * ? on a server in UTC → every night 01:30 UTC = <that time in the human's zone, named>.
File: scheduler/sales_analytics/iv_household_income_cache.json
Enable it?
```

For an export, the middle lines say what each run writes and replaces: the full path on the
Scheduler host, that a file of that name is overwritten whoever wrote it, the header line, what
an empty run leaves, and how many rows the query returns today.

**For a job in the right-hand column, when you cannot ask** — the human is away, a run is
due — the answer is the files, the job created disabled if it is new, and that message; never
the call that enables, starts or changes it. Say what not enabling means (no refresh tonight).
For a job that existed before the session, the message says what is wrong and how you know;
when its next run is, in UTC and in the human's time, and what that run will do; the exact
calls that would fix it (`PUT` with the file, then `start` if a reload is needed); and the
smallest step that stops it getting worse (`disable`) — for the human or the job's owner to
choose. Deleting a job is never that step: its reports go with it. A wrong job you only
happen to see — another project, another view — goes into the message the same way, untouched.

| Rationalization | Reality |
|---|---|
| "They asked for the nightly refresh — that is the yes" | They asked for the outcome. The yes is to this job — what it reloads, as which user, at which hour — after you show it. Create it disabled and ask. |
| "They are offline until tomorrow — just get it done" | Then the job waits, disabled, and the message says so. A wrong job running at night is found in the morning by its readers. |
| "They asked for the outcome — fix it by 11 — and cannot answer" | The outcome is theirs. A change to another team's job and a reload of what others read are the yes. Files and a message. |
| "The task names this database and this Scheduler project" | Naming where the problem is is not the yes to change it. |
| "The cache is `WITH_STATUS`: the load is atomic, no 0-row window" | Atomic is how the numbers change, not whether you may change them. |
| "It is exactly what the job does every night anyway" | A run at its hour is what its owner set up. A run now is yours. |
| "Doing nothing is not neutral — the next run makes it worse" | Then the message says when, and names the call that prevents it. The human or the owner decides. |
| "Readers already see wrong numbers" | A second change nobody approved does not become one by being well meant. |
| "I can't reach the Scheduler — I'll load the profile's password myself / try `../` in the path" | The tool is the only channel (`api --server scheduler`). A path with `..` is refused; reading the profile is reading a credential. |

**Red flags — stop:** you are about to enable, start, stop, change or delete a job whose runs
touch what you did not create in this session; you are writing your own HTTP client or reading
the profile; a cron with five fields; a cache job without `cacheInvalidationMode`; a `PUT`
built from part of a job; `env.production` is `true`.

## The job file

A job is a JSON file in the project — `scheduler/<project>/<job>.json` — created with
`--json-file`, so it is reviewed and kept like the `.vql` beside it. Two things in it belong
to one Scheduler, not to the project: `dataSourceID` (step 2 above) and, once created, the
job's `id`. Another environment means other ids. `--json-file` reads a path relative to the
directory the command runs in — an absolute path when that is not the project. A fix you propose for a job that is not yours goes into the
repository of the request too, under `scheduler/<its project>/`, as the job's `GET` with your
change — the body its owner sends with the `PUT`.

A name is unique inside its project: a second `POST` with the same name answers `422 There is
already an instance of the resource '<name> already exists in the project.'` — look the job up
by name, and change it (below) when it exists.

## Templates

### The project

```bash
# verified: 9.5.1 (live, 2026-10-05)
api --server scheduler get /public/api/projects --param name=sales_analytics --env dev
api --server scheduler post /public/api/projects --json '{"name": "sales_analytics", "description": "Jobs of the sales_analytics database"}' --env dev
```

The first call answers the project or `404 There is no instance of the resource with
identifier 'sales_analytics'`; only then the second, whose answer carries the new `id`.

### Refresh the cache of a view on a schedule

The job file, `scheduler/sales_analytics/iv_household_income_cache.json` — the mark of the
calls below covers it:

```json
{
  "type": "VDPCache",
  "name": "iv_household_income_cache",
  "description": "Reloads the full cache of sales_analytics.iv_household_income every night at 01:30 UTC.",
  "disabled": true,
  "extractionSection": {
    "type": "VDPCache",
    "dataSourceID": <data_source_id>,
    "loadprocesses": [
      {
        "viewName": "sales_analytics.iv_household_income",
        "loadProcessName": "iv_household_income",
        "parameterizedQuery": "select * from sales_analytics.iv_household_income",
        "cacheInvalidationMode": "ALL_ROWS",
        "cacheAtomicOperation": true,
        "cacheLoadOnError": false
      }
    ]
  },
  "handlerSection": {},
  "triggerSection": {"triggers": [{"type": "cron", "cronExpression": "0 30 1 * * ?"}]}
}
```

```bash
# verified: 9.5.1 (live, 2026-10-06)
api --server scheduler post /public/api/projects/<project_id>/jobs --json-file scheduler/sales_analytics/iv_household_income_cache.json --env dev
api --server scheduler get /public/api/projects/<project_id>/jobs/<job_id>/status --env dev
api --server scheduler get /public/api/projects/<project_id>/jobs/<job_id> --env dev
```

The first call answers the job with its `id`; the second its `state` — `DISABLED`, with no
`nextExecution` until it is enabled; the third is the job as the server keeps it — the
read-back. Then the yes, and `enable` (below); `nextExecution` appears.

Every field of a load process prevents a silent failure — *verified: 9.5.1 (live, 2026-10-05)*:

| Field | Left out, or left at its default |
|---|---|
| `"cacheInvalidationMode": "ALL_ROWS"` | the default is **`NONE`** — in the API and in the 9.5.1 administration tool alike, whatever the documentation says (*Matching rows*): every run **adds** the rows to the cache, both reports say `COMPLETE`, and after the second night every row is there twice. `MATCHING_ROWS` without a condition replaces everything too, but says less about what you mean |
| `"cacheAtomicOperation": true` | stored as `false` when left out (the tool's form defaults to `true`): invalidation and load in separate transactions |
| `"loadProcessName"` | the job is created, and every run fails: `Missing configuration parameter: 'loadProcessName'` |
| `"parameterizedQuery": "select * from <db>.<view>"` | `""` is dropped and every run fails: `Missing configuration parameter: 'parameterizedQuery'`. It is the load query — `select *` over the cached view itself, the database named, nothing else; a `where` here loads only those rows, for every reader (`/denodo:cache`, "Load only some rows") |
| `"viewName": "<db>.<view>"` | the view the load is for; the same `<db>.<view>` is what `jobs/vdpcache_data` finds it by |
| `"cacheLoadOnError": false` | `true` keeps the rows of a load that failed half-way |
| `"handlerSection": {}` | creating works without it; a later `PUT` without it fails with `500` |

The view's cache has to be on: over a view without one, every run answers `WARNING` — `The
cache is not configured for the selected view and no tuples have been cached in its subviews` —
and loads nothing. The run sends `select * from <view> CONTEXT('cache_preload'='true',
'cache_wait_for_load'='true', 'cache_return_query_results'='false',
'cache_invalidate'='all_rows', 'cache_atomic_operation'='true') TRACE` — the load statement of
`/denodo:cache`. Several views go into one job as several load processes, each named.

### Export a view to a CSV file on a schedule

`scheduler/sales_analytics/household_income_by_band_csv.json` — the mark of the calls below
covers it:

```json
{
  "type": "VDP",
  "name": "household_income_by_band_csv",
  "description": "Writes household_income_by_band.csv on the 1st of every month at 01:00 UTC.",
  "disabled": true,
  "extractionSection": {
    "type": "VDP",
    "dataSourceID": <data_source_id>,
    "extractionData": {
      "parameterizedQuery": "SELECT income_band_sk, household_count FROM sales_analytics.household_income_by_band ORDER BY income_band_sk"
    }
  },
  "exportationSection": {
    "exporters": [
      {
        "type": "CSV",
        "fileName": "household_income_by_band.csv",
        "overwriteFile": true,
        "createNewFile": false,
        "appendFile": false,
        "allowEmptyFile": true,
        "includeHeader": true,
        "exportInternalFields": false,
        "separator": ",",
        "encoding": "UTF-8",
        "quoteFieldsOption": "WHEN_REQUIRED",
        "filter": "NONE"
      }
    ]
  },
  "handlerSection": {},
  "triggerSection": {"triggers": [{"type": "cron", "cronExpression": "0 0 1 1 * ?"}]}
}
```

```bash
# verified: 9.5.1 (live, 2026-10-06)
api --server scheduler post /public/api/projects/<project_id>/jobs --json-file scheduler/sales_analytics/household_income_by_band_csv.json --env dev
api --server scheduler get /public/api/projects/<project_id>/jobs/<job_id>/status --env dev
api --server scheduler get /public/api/projects/<project_id>/jobs/<job_id> --env dev
```

**The file is written on the Scheduler host**, not on the human's machine: a relative
`fileName` lands in `<DENODO_HOME>/work/scheduler/data/csv/`, an absolute one where it says.
The report of each run names the full path (`exporterResources`). The exporter's defaults each
break a reader without an error — *verified: 9.5.1 (live, 2026-10-05)*:

| Field | Its default does |
|---|---|
| `"includeHeader": true` | no header line: a reader that finds columns by name finds none |
| `"overwriteFile": true`, `"createNewFile": false` | the default name is `@{projectName}_@{jobName}_@{jobID}_CSVExporter#@{exporterID}.csv` plus the start time of each run: a new file every run, piling up, never the name the reader opens |
| `"allowEmptyFile": true` | with `false`, a run that returns no rows **deletes the file the last run wrote** and reports `COMPLETE`, 0 rows; with `true` it leaves a file with only the header |
| `"exportInternalFields": false` | `true` adds the job's own columns (`_$job_project`, `_$job_name`, …) |
| `"filter": "NONE"` | required: without it `400 Validation error` — `exportationSection.exporters[0].filter must not be null` |

The query names its columns and sorts: a renamed column then fails the run instead of shifting
the file, and the rows come in the same order each time. Over a view with a full cache it reads
the cache — as fresh as its last load (`/denodo:cache`); `CONTEXT ('cache' = 'off')` at the end
reads the sources instead.

### Run one statement on a schedule

The same file as the export, without exporters (`"exportationSection": {}`) and with the
statement as `parameterizedQuery` — `REFRESH sales_analytics.rt_household_income`, `CALL
<procedure>(…)`:

- **One statement per job.** Two separated by `;` fail every run: `Syntax error: Exception
  parsing query near 'SELECT'`.
- **It runs in the database of the data source's `connectionURI`**, as its `login`. Name the
  database in the statement where VQL allows it — `REFRESH <db>.<table>`, `<db>.<view>` in a
  `FROM`; a statement that cannot name it (`ALTER VIEW <db>.<view> …` → `Syntax error … near
  '.'`) needs a data source connected to that database.
- **`@`, `\`, `^`, `{`, `}` in a literal are written `\@`, `\\`, `\^`, `\{`, `\}`.** An `@`
  starts a variable: `'ops@example.com'` is accepted when the job is created and fails every
  run with `No configuration found for the following parameters of the query: [example.com]`.
- A statement on a view that is not there is accepted too, and fails at the run: `View '<v>'
  not found`. Run the statement — or, for a write, a `SELECT` of what it reads — before the job
  is created.
- What the statement does every night is classified as if you ran it now: the tool flags a job
  with `REFRESH` as `table`, with `DROP` as `drop`, and so on, and refuses it on a production
  profile.

### Run it now, and wait for the report

```bash
# verified: 9.5.1 (live, 2026-10-06)
api --server scheduler put /public/api/projects/<project_id>/jobs/<job_id>/status --json '{"action": "start"}' --env dev
api --server scheduler get /public/api/projects/<project_id>/jobs/<job_id>/reports --param start=0 --param count=1 --env dev
```

`start` answers `204` and the run goes on by itself. **The report appears only when the run
ends**: while it runs, `total` stays where it was and the status has no `result`. Repeat the
second call every few seconds until `total` is one more than before, then read `list[0]`:
`result` (`COMPLETE`, `WARNING`, `ERROR`), `extractedDocs`, `cachedDocs` for a cache job,
`exportedDocs` and `exporterResources` for an export, and the error lists — `extractorErrors`,
`initializationErrors`, `generalErrors`, `exporterErrors`, and `reports[]`, one entry per load
process or query, where a warning's text is. A cache job's `query` shows the `CONTEXT` it sent:
without `'cache_invalidate'` it ran with `NONE` and appended. `start` on a disabled job fails
with `500 Internal error` — enable it first. Who may start which job is the table above.

When a job loads the view, its `start` — after the job is right — is the reload: the same
statement as the load file of `/denodo:cache`, with a report. The load file is still worth
writing, for a reload without the Scheduler.

### Stop, enable, disable

```bash
# verified: 9.5.1 (live, 2026-10-06)
api --server scheduler put /public/api/projects/<project_id>/jobs/<job_id>/status --json '{"action": "disable"}' --env dev
api --server scheduler put /public/api/projects/<project_id>/jobs/<job_id>/status --json '{"action": "enable"}' --env dev
api --server scheduler get /public/api/projects/<project_id>/jobs/<job_id>/status --env dev
```

`disable` → `state: DISABLED` and no `nextExecution`: the job keeps its definition and does not
fire. `enable` brings `nextExecution` back. `stop` ends a run in progress (on a job that is not
running it answers `204` and does nothing). The tool flags each of these `destructive: job`.
**After enabling, set `"disabled": false` in the job's file**: the file is what a `PUT` or a
re-creation sends, and one that still says `true` switches the job off again without a word.

### Change a job

```bash
# verified: 9.5.1 (live, 2026-10-06)
api --server scheduler get /public/api/projects/<project_id>/jobs/<job_id> --env dev
api --server scheduler put /public/api/projects/<project_id>/jobs/<job_id> --json-file scheduler/sales_analytics/iv_household_income_cache.json --env dev
```

**A `PUT` replaces the whole job.** Its body is the job's file with `"id": <job_id>` added, or
the job exactly as the `GET` returned it with your change — its `projectId`, `projectName` and
the other fields the server added may stay: a section left out is emptied —
without `triggerSection` the job answers `200` and has **no schedule any more** — and without
`handlerSection` (or, on a VDP job, `exportationSection`) it fails with `500 Internal error`;
without `id`, `400 Illegal argument`. A failed `PUT` changes nothing. Read the job back after
it.

### What ran, and what failed

```bash
# verified: 9.5.1 (live, 2026-10-06)
api --server scheduler get /public/api/jobs/status --env dev
api --server scheduler get /public/api/projects/<project_id>/jobs/<job_id>/reports/summary --env dev
api --server scheduler get /public/api/projects/<project_id>/jobs/<job_id>/reports --param start=0 --param count=5 --env dev
```

`jobs/status` is every job's `state` (`NOT_RUNNING`, `RUNNING`, `DISABLED`, `WAITING`, …),
`result` of its last run (`NEVER_EXECUTED` until one), `previousExecution` and `nextExecution`.
The summary lists the runs with their counts; `reports` with `start` and `count` (both
required) has each run, newest first — `reports[]` inside a run holds the detail of its load
processes or queries when there is any (`hasIndividualDetails` in the summary). Deleting a job
deletes its reports.

### A cache that doubles, a job that does nothing

Figures on a cached view that double, then triple, every morning:

1. `SELECT COUNT(*) FROM <view>` against the same with `CONTEXT ('cache' = 'off')` — more rows
   in the cache than in the sources, every key or group twice.
2. `GET /public/api/jobs/vdpcache_data?viewName=<db>.<view>` — the jobs that load it.
3. Each job's `extractionSection.loadprocesses[].cacheInvalidationMode`, and the `query` of its
   last reports: `NONE`, no `'cache_invalidate'` — every run appended. Two jobs loading the
   view are the other cause.
4. The job's `nextExecution` — when it gets worse — and who owns it. The fix is the job's `PUT`
   and a reload: the human's, or the owner's (Who applies it).

A job that runs and changes nothing: its reports say `WARNING` (the view's cache is off) or
`COMPLETE` with `cachedDocs: 0`; a job that never runs: `state: DISABLED`, or no
`triggerSection` after a `PUT`.

## Cron: Quartz, on the server's clock

Six fields and an optional seventh: **seconds** minutes hours day-of-month month
day-of-week [year]. One of day-of-month and day-of-week must be `?`.

| The human says — the last three for a human in UTC+3, as an example | Cron, on a server in UTC |
|---|---|
| every night at 01:30 UTC | `0 30 1 * * ?` |
| every hour, on the hour | `0 0 * * * ?` |
| weekdays at 18:00 UTC | `0 0 18 ? * MON-FRI` |
| at 05:00 their time | `0 0 2 * * ?` |
| Mondays at 01:00 their time | `0 0 22 ? * SUN` — the day moves with the hour |
| the 1st of the month at 01:00 their time | `0 0 22 L * ?` — the last day of the previous month |

`POST /public/api/projects/jobs/validateCronExpressions` with a JSON list of expressions
answers one string per expression, `""` when it is valid — every expression in the table above
and the refusal of `0 0 2 * * *` below, *verified: 9.5.1 (live, 2026-10-05)*:
`api --server scheduler post /public/api/projects/jobs/validateCronExpressions --json '["0 0 2 * * ?"]' --env dev`.
Validate before creating: a five-field cron makes the create call fail with nothing but
`500 Internal error`; `0 0 2 * * *` is invalid too (`Day-of-Month and Day-of-Week can not both
be a specific value`).
A zone with daylight saving time moves against a UTC server twice a year; say so, and name the
hour it becomes.

## What you need

| Slot | Where it comes from |
|---|---|
| What runs: the view, the statement, the query and the file | the human; the view must exist and, for a cache job, have its cache on (`/denodo:cache`) |
| When | the human, in their own words and time zone; the cron is yours to work out |
| Project | the human; none named → a new one named after the VDP database |
| VDP data source, so the user the job runs as | the human's choice among `GET /public/api/dataSources`; none → the human creates one in the administration tool |
| Where the file goes | the human; it is a path on the Scheduler host |

## Verify

After creating or changing a job — every row:

| Check | Call | Expect |
|---|---|---|
| The job is what the file says | `GET …/jobs/<job_id>` | for a cache job `cacheInvalidationMode: ALL_ROWS`, `cacheAtomicOperation: true`, a `loadProcessName` and a `parameterizedQuery`; for an export `includeHeader`, `overwriteFile` and the `fileName` you wrote; `triggerSection` with your cron |
| It fires when the human asked — once enabled | `GET …/jobs/<job_id>/status` | `state: NOT_RUNNING`, and `nextExecution` (UTC) is the human's hour in their zone — convert it back and say both in the report; before the yes it is `DISABLED`, and the hour is your computation, said as such |
| Its statement works | `vql run` of the statement as a read — the export's `SELECT … LIMIT 5`, `SELECT COUNT(*)` of the cached view | rows, the columns the reader expects |
| Nothing else does the same | `GET /public/api/jobs/vdpcache_data?viewName=<db>.<view>`; for an export, `exportationSection.exporters[].fileName` across `GET /public/api/jobs` | only your job |

After a run you were allowed to start, and the morning after the first scheduled run:

| Check | Where | Expect |
|---|---|---|
| The run | `list[0]` of the reports | `COMPLETE`; `cachedDocs` or `exportedDocs` equal to `extractedDocs` |
| A cache job loaded once, not twice | `SELECT COUNT(*) FROM <view>` and `SELECT COUNT(*) FROM <view> CONTEXT ('cache' = 'off')` | equal (`/denodo:cache`, Verify) |
| The file | `exporterResources` of the report | the path the reader opens |

## Silent failures

Each runs without an error — *verified: 9.5.1 (live, 2026-10-05)*:

| You did | What happens | Instead |
|---|---|---|
| a cache job with the default `cacheInvalidationMode` | every run adds the rows again; `COMPLETE` each night, every figure on the view doubles, then triples | `ALL_ROWS` in the file, and the read-back |
| the human's hour as the cron's hour on a server in another zone | it fires hours early or late; on a day boundary, on the wrong day | the cron for the server's zone; check `nextExecution` |
| a `PUT` of only the part you changed | the job loses its trigger, or the `PUT` fails | the whole job, then the read-back |
| an export with the exporter's defaults | no header; a new file with a timestamp every run | the export template |
| an export that returned no rows, `allowEmptyFile: false` | the previous file is deleted | `allowEmptyFile: true`, and a reader that checks the row count |
| an `@` in a literal | accepted when created, every run fails | `\@` |
| a job over a view whose cache was switched off | `WARNING` every run, nothing loaded | stop or delete the job when the cache goes off (`/denodo:cache`) |

## Common errors

| Answer | Cause | Fix |
|---|---|---|
| `500 Internal error` on create | a cron of five fields, or with both days specific | `validateCronExpressions` |
| `500 Internal error` on `start` | the job is disabled | `enable` first |
| `500 Internal error` on `PUT` | the body lacks `handlerSection` or `exportationSection` | the whole job |
| `400 Illegal argument` on `PUT` | the body lacks `id` | add `"id": <job_id>` |
| `400 Validation error`, `…exporters[0].filter must not be null` | an exporter without `filter` | `"filter": "NONE"` |
| `422 There is already an instance of the resource '<name> already exists in the project.'` | the name is taken in the project | look it up; change that job, or another name |
| `404 There is no instance of the resource with identifier '<name>'` | no project of that name | create it |
| `401` | the tool reached the server without the profile's account | `api --server scheduler`, never a call of your own |
| run `ERROR`: `Missing configuration parameter: 'loadProcessName'` / `'parameterizedQuery'` | a load process without them | the cache template |
| run `ERROR`: `No configuration found for the following parameters of the query: [x]` | an unescaped `@` | `\@` |
| run `ERROR`: `Syntax error: Exception parsing query near 'SELECT'` | two statements in one job | one job each |
| run `WARNING`: `The cache is not configured for the selected view…` | the view's cache is off | `/denodo:cache`, or stop the job |

## Reference

- `references/rest-api.md` — the calls this skill uses and the ones it leaves to the
  administration tool, every field of the two job types and of the CSV exporter with its
  default, the report fields, and what was measured about each.
