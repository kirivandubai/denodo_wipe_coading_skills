---
name: vql
description: Use when doing anything with Denodo — creating or changing a database, folder, tag, data source, wrapper, base, derived, interface or metric view, association, cache, role or security policy, remote table or summary, a Data Marketplace object, a regression test or a Scheduler job; writing or fixing VQL, or an expression in a SELECT — text, dates, casts; deciding where an object lives and what to name it; "where do I start", "build a mart", "connect a source", "vibe-code on Denodo". Start here when the request is ambiguous or names no single object.
---

# Working with Denodo

**VQL goes into a file in the project, and the file is what gets applied.** Objects that
exist only on a server exist in no artifact: nobody can review them, move them to the next
environment, or rebuild them after a rollback.

**Violating the letter of the rules below is violating their spirit.** This plugin gets
installed on production servers.

## The loop

```
intent in words
  → read .denodo/conventions.md if the project has one
  → decide placement: database, layer folder, name
  → write the statements into a .vql file in the project
  → plan it: vql plan says, per statement, whether it is yours or waits for the human's yes
  → apply the file with /denodo:execute
  → verify: DESC, and SELECT for anything that carries rows — a view whose columns call
    the server's LLM is read from its cache, or with a LIMIT the human agreed to (/denodo:ai)
  → the file stays in git
```

**When there is no project** — an empty directory, a server and nothing else — the file is
still written: put it in the working directory and say in the summary where it is and that
it is outside version control. What the rule protects is the artifact, not the repository:
an object living only on a server is the failure mode whether or not there is a git to
commit the file to.

**Inline `-e` is for reading only** — `SELECT`, `DESC`, `GET_ELEMENTS()`, `GET_VIEW_TAGS()`.
Every `CREATE`, `ALTER` and `DROP` goes through a file, including the first exploratory one.

**Never create a probe object to test a hypothesis.** A `probe_a` view is an object: it
stays in the catalog, it is not in any file, and removing it needs the human's confirmation
like any other drop. Test the real statement in the real file — re-applying it is safe.

**One file per change, applied whole.** Do not keep a second "cleaned" copy next to it.
Templates are `CREATE OR REPLACE`, so when a statement fails, fix that statement and
re-apply the same file from the top.

**A request for a set** — every table of a schema, every column that holds an email, every
view of a database — runs the same loop over a list, with a plan file: **Many objects at
once**, below.

Chain order, when several objects are involved: `database → folder → datasource → wrapper
→ base view → derived view → association → metric view → the views over it`. A view's cache
line goes in the view's own file, right after its `CREATE`, and the load after that; remote
tables, summaries and Scheduler jobs come after the views they read. Tags and marketplace
objects come last: they attach to things that must already exist — except a tag that a view's
own file names (`TAGS`), which is created before that view.

## Naming and layout

Defaults below follow the Denodo VDP Naming Conventions. Lowercase with underscores,
singular nouns, no environment name anywhere in an object name (`sales`, never
`sales_dev` — the profile says which server you are on).

| Object | Name |
|---|---|
| Database | the project or domain: `sales_analytics` |
| Data source | `ds_<source system>` — one file source is one file, so a system that arrives as several files gets one per file, named for what is in it: `ds_retail_store`, `ds_retail_store_returns` |
| Wrapper | `wr_<source system>_<entity>` |
| Base view | `bv_<source system>_<entity>` |
| Derived view, integration layer | `iv_<what it does>` |
| Business entity view / interface view | the entity itself: `customer` |
| Metric view | the subject and `_metrics`: `sales_metrics`; the selection views over it say what they hold, `sales_by_region` |
| Association | `a_<principal>_<related>` |
| Summary | `s_<name>` |
| Tag | the concept: `pii`, `gdpr` |

Layers are folders, and every object gets a `FOLDER =`:

| Folder | What lives there |
|---|---|
| `/01 - connectivity` | data sources, wrappers, base views |
| `/02 - integration` | derived views that combine and transform |
| `/03 - business entities` | canonical views, interface views, metric views and the views over them — what consumers read |
| `/06 - associations` | associations |

Create the layers you actually fill, not the whole table: a mart over two files needs
`/01`, `/02` and `/03`, and an empty `/06` is noise in someone's catalog.

Folder paths are quoted, and a parent must exist before its child:
`Cannot create folder /03 - business entities/sales: parent not found`. Create top-down;
drop bottom-up, because `DROP FOLDER IF EXISTS` will not remove a folder with content.

**A project may override all of this.** Before writing VQL, look for `.denodo/conventions.md`
in the project root (`cat .denodo/conventions.md 2>/dev/null`). It is plain markdown; a
section named after a rule above replaces that rule, anything it does not mention keeps the
default. If the project has one, it wins — do not "improve" its naming with the defaults.

## Idempotency

**`CREATE OR REPLACE` for every object type**, in every file — `DATABASE` included. The
exception is a table that holds rows: over a remote table, a summary or a materialized table
`OR REPLACE` drops or empties what is there (`/denodo:materialize`).

- `IF NOT EXISTS` does not exist in Denodo. The server answers
  `Syntax error: Exception parsing query near 'IF'` — *verified: 9.5.1 (live, 2026-09-09)*.
- `CREATE OR REPLACE DATABASE` **keeps the objects inside the database** — *verified: 9.5.1
  (live, 2026-09-09)*. Do not split the database into a separate "bootstrap" file to
  protect it; that guess is wrong and it costs you a re-appliable file.
- `CREATE OR REPLACE VIEW` over a view that others depend on is fine when the change is
  additive — *verified: 9.5.1 (live, 2026-09-09)*. Removing or retyping a column that a
  dependent view uses — selects, joins on, filters or groups by — is a breaking change:
  check dependents first (`/denodo:views`, "Before a column changes").
- Assigning a tag needs both blocks — `ADD_TO ( ... ) REMOVE_FROM ( VIEWS () COLUMNS () )`
  — or it is a syntax error — *verified: 9.5.1 (live, 2026-10-06)*.
- **Data Marketplace has no `OR REPLACE`.** Every operation goes by numeric id, and an id
  only exists after creation, so idempotency there is a pair: `GET` the object by name,
  then `POST` to create or `PUT` to update. The status of a repeated `DELETE` differs per
  object type (`500`, `200`, `404`) — never rely on it, rely on the lookup.

Templates in the domain skills carry `-- verified: 9.5.1 (live, <date>)` — the release and the
day it ran — or `-- unverified: 9.5 documentation only`. An unverified template is still worth using;
it just means the verification is yours to do, with `DESC` and a `SELECT`.

## Safety: you create, the human confirms destruction

**Plan a file before you apply it, and again after you change it.** `vql plan --env dev
<file>` reads it against the server and against the session's ledger — every `vql run`
records the objects it created — and executes nothing. Per statement: `exists`; `own` —
created in this session, by the ledger with the server's id checked, or by an earlier
statement of the same file; `needs_yes`, with `why` (the row below that decides) and
`conditions` (what that row also needs and the tool cannot see). `true`: show those
statements and wait for the yes. `false`: yours, once its `conditions` hold. `null`: the
plan does not recognise the statement, and this table decides. On a production profile every
change is `true`. "Created in this session" in the table means what `own` says, not what you
remember: after a compacted context, in a subagent, or beside an object of the same name, the
ledger knows and you do not. `vql ledger --env dev` lists what the session created.

| You do it yourself | Only after the human confirms |
|---|---|
| `CREATE` / `CREATE OR REPLACE` of an object — a new one, or one a file of your project declared before this session (the plan's `declared_in`; a file you have just written vouches for nothing) | `DROP`, `TRUNCATE`, `DELETE` |
| Read-only `SELECT`, `DESC`, `GET_*`, `env check` — on any profile, production included | `ALTER` of an object that existed before this session, or that something you did not create already reads. Your own new view takes the `ALTER VIEW … CACHE` line of its file without a yes; a `DROP`, even of your own object, does not |
| Session settings: `SET QUERYTIMEOUT TO …`, `ALTER SESSION SET 'querytimeout' = …` | `INSERT`, `UPDATE` — the rows land in the source behind the view, at once: over this connection `ROLLBACK` undoes nothing (`/denodo:dml`). The `INSERT`s that are yours: into a materialized or remote table you created in this session — an incremental load of it included (`/denodo:materialize`) |
| A **new** table in a source database: `CREATE_REMOTE_TABLE` with `replace_remote_table_if_exist = false`, in the data source and schema the human named, under a name you checked is free; its `REFRESH` while it is yours from this session; a summary created unloaded; a new materialized table in your project's database (`/denodo:materialize`) | replacing, emptying or dropping a table in a source database that existed before this session — `replace … = true`, `OR REPLACE` before `REMOTE TABLE`, `SUMMARY VIEW` or `MATERIALIZED TABLE`, `REFRESH`, `DROP_REMOTE_TABLE` — and **every load of a summary**: from then on the optimizer answers other people's queries from it (`/denodo:materialize`) |
| — | `SET '<property>' = …`, `WEBCONTAINER SET / STOP / START / RELOAD` — the whole server's configuration, not your session |
| — | `CREATE OR REPLACE` of an existing view that drops or renames a column other objects use — the server accepts it and breaks them without an error (`/denodo:views`, "Before a column changes") |
| — | `CREATE OR REPLACE` of an existing object no file of your project declares — made in Design Studio, or another team's: your text replaces its whole configuration, a data source's stored password and a view's cache settings included (`/denodo:datasources`) |
| — | loading, reloading or clearing the cache of a view you did not create in this session — `SELECT … CONTEXT ('cache_preload' = 'true', …)`, `ALTER VIEW … CACHE` (`/denodo:cache`) |
| — | `CREATE OR REPLACE METRIC VIEW` over a metric view you did not create in this session — a changed join type, filter or metric changes every figure built on it, with no column dropped (`/denodo:metrics`) |
| — | the description, field descriptions, primary key or tags of a view you did not create in this session — by `ALTER VIEW`, `ALTER TAG`, or by re-declaring the view with `CREATE OR REPLACE`: the human approves the texts; naming a view to be made visible to an agent is the yes for its tag. An association that names a view you did not create counts too: it becomes that view's dependant (`/denodo:semantics`) |
| — | who may read what: a role, a user or a global security policy, created or changed, a grant of a role or a privilege to a person, or a tag that a policy names put on or taken off a column — unless every object it touches was created by you in this session. A `CREATE` counts: a new policy restricts people who exist, and `CREATE OR REPLACE` of an existing role adds to it (`/denodo:security`) |
| `…_AI` calls on `Dual()` — to see that the server answers, or to try an expression on up to three texts — and a search whose text is embedded once | an AI function — `CLASSIFY_AI`, `SENTIMENT_AI` and the rest, or an embedding computed per row — evaluated on the rows of a view, a cache load of a view with such a column included: every row is a paid request to an outside provider, and its text goes with it. The human agrees to the number of requests, or names a ceiling (`/denodo:ai`) |
| — | a predefined procedure that changes state, however it is spelled: `SELECT * FROM DROP_REMOTE_TABLE(…)`, `CALL CLEAN_CACHE_DATABASE(…)`, `GENERATE_STATS(…)`, `LOGCONTROLLER(…)` — the list is in `/denodo:procedures`. Two exceptions, both on what you created in this session: `CREATE_REMOTE_TABLE` of a new table, above, and `CLEAN_CACHE_DATABASE` of the cache of your own view (`/denodo:cache`) |
| a Scheduler job created disabled — it runs nothing — and one whose runs touch only what you created in this session; every Scheduler `GET` (`/denodo:scheduler`) | enabling, starting or changing a Scheduler job whose runs reload a cache, refresh a table or write a file that existed before this session — the job is that statement, every time it fires — and anything on a job that existed before this session (`/denodo:scheduler`) |
| `GET` calls to the marketplace; a catalog `synchronize` whose radius is yours (below) | every other destructive marketplace call (below) |
| — | **any change at all on a profile with `production: true`, `CREATE` included** |

Destruction, for this rule, is anything that destroys or overwrites what exists, or changes
state outside your own project: server settings, data in sources, objects of other
databases, global objects. One kind of change outside it is yours: a new table in a source
database, where the human said it should go, by a statement that cannot overwrite one.

The confirmation is a yes in this conversation, after you have shown the exact statements
or calls. Not a yes to the task in general. "Do it on prod" is the task, not the yes.

Reading is always allowed, and on a production profile it is what you do *instead* of
guessing: check `env.production`, `DESC` what is already there, then come back with the
statements you propose to apply.

**For HTTP the rule goes by method and path, not by the verb in the text.** These are as
destructive as a `DROP`, and none of them contains the word:

| Call | What is lost |
|---|---|
| `DELETE /public/api/tags/{id}`, `/tags/delete-multiple` | the tag and every assignment of it |
| `DELETE /public/api/category-management/categories/{id}` | the category **and all its children** |
| `DELETE /public/api/external-tool-servers/{id}` | the server and **every element it imported** |
| `POST /public/api/tags/vdp/synchronize` | every imported VDP tag missing from the list you send |
| `POST /public/api/element-management/{all,DATABASES,VIEWS,…}/synchronize` | everything the marketplace holds that VDP no longer has — `changes.localElements` is that list, and it goes whatever `proceedWithConflicts` says; `"SERVER"` additionally overwrites descriptions edited in the marketplace. A view renamed in VDP is on that list under its old name, with everything people attached to it, unless the pair is matched in the call (`/denodo:marketplace`) |
| `POST /public/api/views/{id}/tags`, `.../categories`, `/public/api/property-management/views/{id}/groups` | the view's previous assignments — this is "set", not "add"; a property group left out takes its values with it |

Sending a *complete* list to `tags/vdp/synchronize` is not a substitute for asking: you are
still replacing a set you did not read out to the human.

| Rationalization | Reality |
|---|---|
| "The profile is `dev` and the tool did not refuse" | The tool refuses only on production. Non-refusal is not consent. |
| "They asked me to remove the tags — that *is* the confirmation" | They asked for an outcome. Confirmation is a yes to the listed statements, after you list them. |
| "It's a tag, we can recreate it" | You cannot recreate its assignments to views and columns; and a category takes its children with it. |
| "There's no `DROP` in this call" | The rule is method and path. `POST …/synchronize` deletes. |
| "Cleanup of my own probe objects doesn't count" | It is a `DROP` on a shared server. Same rule. |
| "I'll list what I removed in the summary" | Disclosure after the fact is not consent. |
| "Nothing gets removed — the rest of the radius only adds" | Clean is not the test; whose is. Another team's new database or view under `serverElements` lands in the catalog everybody browses before its owner chose to publish it. One entry you did not create in this session, and the body goes in a file with what waiting risks; the human sends it or says yes. |
| "The pair is matched, so the rename costs nothing" | A view that existed before this session is someone's: the rename and its matched `synchronize` wait for one yes, shown together. |
| "My file declares it — the table says that is mine" | A file declares whatever you put in it. Your project's file is one that declared the object before this session — the plan's `declared_in`. A name that `exists` and is not `own` waits for the yes. |
| "The context was compacted and I cannot tell which objects are mine, so everything waits" | `vql plan` and `vql ledger` know: the tool recorded every object this session created. Asking the human about your own work costs their time; guessing costs their objects. |

**Two named exceptions, and only these.** On a `production` profile neither applies: the tool
refuses every `synchronize` there regardless (`/denodo:marketplace`).

1. **A catalog `synchronize` whose radius is yours** — `api post … --plan` reads both
   `changes` against the ledger and says so (`radius.own`, `needs_yes`). `VIEWS/synchronize` — preceded by
   `DATABASES/synchronize` when the database is new — with `proceedWithConflicts:
   "SERVER_WITH_LOCAL_CHANGES"`, when both `…/changes`, `DATABASES` and `VIEWS`, read right
   before the call, hold only what you created in this session: every
   `serverElements` entry a database or view you created, every `localElements` entry the
   element of a view you created — your own view renamed, with the pair matched in the call,
   included. `modifiedElements` do not change this: that mode keeps every description edited
   in the marketplace. After the call, read `removed` and `inserted` against the radius you
   read, then both `changes` again — `removed` can be empty while elements went
   (`/denodo:marketplace`) — and tell the human at once about anything you did not expect. Any other entry — a database
   or view you did not create in this session, an orphan you did not make — and the call waits
   for the yes.
2. The first `POST /public/api/external-tool-servers/synchronize` on an external tool server
   you created in this same session imports elements and can delete none, because that server
   has imported none yet. Every later import on it is back under the rule.

Nothing else about a `synchronize` is exempt.

**Red flags — stop and ask:** you are applying a file the plan has not read since its last
change; you are about to send `DELETE`; a `synchronize` whose radius
you have not read just now, or that holds anything you did not create in this session; you
are writing `--allow-destructive`; `env.production` is `true`; you are removing something you
did not create in this session; you are "cleaning up" anything.

## Many objects at once

When the request names a set, what goes wrong is the list: an object missing from it, two
that end up under one name, a check that read three of thirty, a report that says "all done".
The loop is the same; the list becomes a file, and every step answers per object.

1. **The list comes from the server, whole.** One read returns every candidate — the tables of
   a schema (`/denodo:datasources`), the columns of a database and where each one's value comes
   from (`/denodo:catalog`), the views and their metadata (`/denodo:semantics`). Run it with
   `--max-rows 5000`: the tool keeps 100 rows by default, and `truncated: true` means the list
   is not whole — narrow the read and run it again, never work from what came back. What
   already exists is on the list too, found by what it reads, not by its name.
2. **The plan file**, `<change>.plan.md` beside the statements: one row per candidate, and the
   decision in the row — the object, what it comes from, the action (or none, and why: it
   exists and is not yours, it is not what was asked, a question for the human), whose it is,
   the file that carries its statement, and a status. Names come from one rule, unique across
   the list; when two sources would get one name, the rule changes for all of them.
3. **One statement file per yes.** Generate the statements from the list — a query that
   returns them, or a script — never by hand. `vql plan` the file: `actions` counts what it
   does, and `duplicates` lists two statements of the file declaring one object differently —
   the later silently replaces the earlier. What is yours goes into the file you apply; what waits for the
   human goes into a file of its own, all of it. When the human has to read every object — texts,
   tags on views you did not create — split that file into batches one sitting reads (tens of
   objects, grouped by schema, folder or subject), a file and a yes each.
4. **Apply** each file as always. An object that fails and cannot be fixed now leaves the file
   and becomes a `failed` row with the server's message; the rest goes on. Taking a failed
   statement out of a file the human said yes to only narrows what they approved.
5. **Check every object, then write the result into the plan file.** A catalog read compared
   with the list row for row — `GET_ELEMENTS()`, `GET_VIEW_TAGS()`, `GET_VIEW_COLUMNS()`: a
   missing row is a failure that raised no error. For rows, a file of reads, one `SELECT` per
   view, run with `--continue-on-error` — `statements[i]` is that view's answer. Every row gets
   its status: done and what the check saw, failed and the message, waiting and its file,
   skipped and why.

```
# Base views over ds_erp, schemas sales and billing — 14 tables (GET_JDBC_DATASOURCE_TABLES, not truncated)
| object | from | action | whose | file | status |
|---|---|---|---|---|---|
| bv_erp_sales_customer | sales.customer | create | new | model/erp_base_views.vql | done — 48,210 rows |
| bv_erp_billing_customer | billing.customer | create | new | model/erp_base_views.vql | failed — permission denied on the table |
| bv_erp_invoice | billing.invoice | none — exists | not yours, no project file declares it | — | left as it is |
| bv_erp_sales_audit_log | sales.audit_log | none | — | — | question: wanted? |
```

The message to the human gives the count per status, names the plan file and the files that
wait, and lists every row that is not done. Those files are what you showed: the yes to them
covers each file as it was when shown — a file changed after the yes in any other way than a
failed statement taken out is planned and shown again.

## Expressions: VQL is not PostgreSQL

Most of a `SELECT` is the SQL you know; the expressions are where it is not. Every row
below **runs without an error and returns a wrong value or `NULL`**, and a view or a report
built on it reads like real data. The loud differences, the functions that do not exist and
what replaces them, and the rest of the silent ones are in `references/dialect.md` — read
it before writing a text, date or cast expression you have not written in VQL before.

**An expression new to you gets one run on `Dual()` with an input whose answer you know**,
before it goes into a view or a report:
`vql run --env dev -e "SELECT SUBSTR('abcdef', 1, 3) AS want_abc FROM Dual()"`. Choose
the input so the wrong reading shows: `'abcdef'` for a substring, `2024-12-30` for a year,
`2.9` for a cast. After a parse or a cast over real rows, count the `NULL`s it produced.

*verified: 9.5.1 (live, 2026-09-30)*

| You write | Denodo gives | Write instead |
|---|---|---|
| `SUBSTRING(s, 1, 3)` | `'bc'` — the comma form is 0-based and its third argument is an end index. `INSTR` is 0-based (`-1` when absent), `POSITION` 1-based | `SUBSTR(s, 1, 3)` or `LEFT(s, 3)`; never mix the 0-based and 1-based functions in one expression |
| `s = 'abc'`, `num_col > '9'` | exact: case and trailing spaces count, and a file source may pad text to the column width (`LEN` shows it). A comparison mixing text and a number compares as text — `day > '9'` finds nothing. Delegated to SQL Server, case and spaces are ignored instead | `UPPER(TRIM(s)) = 'ABC'`; numbers compared as numbers |
| `CAST(x AS integer)` | truncates, `2.9` → `2` — yet rounds when the cast runs in PostgreSQL. `'12abc'` → `12`; past the range it wraps around | `ROUND`, `FLOOR` or `TRUNC`, whichever you mean; check text with `TRIM(s) REGEXP_LIKE '^-?[0-9]+$'` before casting it |
| `a / 0`, `int + int` past 2 147 483 647 | `NULL`, no error | guard the denominator; `CAST(a AS bigint)` before adding |
| `SUM(int_col)` | stays `int`: past 2 147 483 647 it returns `NULL` or a wrong number that looks real | `SUM(CAST('long', x))` — for `int` only: over a `decimal` the same cast truncates every row. `decimal` and `double` need nothing |
| `MAX(a, b)` (there is no `GREATEST`), `CONCAT(a, b)`, `GROUP_CONCAT(';', ':', a, b)` | `NULL` when any argument is `NULL`; `GROUP_CONCAT` drops the whole row | `COALESCE` each argument |
| `TO_LOCALDATE('YYYY-MM-DD', s)`, `FORMATDATE('YYYY-MM', d)` | Java patterns, pattern first. `YYYY` is the week year (30 Dec → next year), `DD` day of year, `mm` minutes, `hh` 1–12, `yy` 2000–2099; `MMM` month names are read in the language of the i18n. A wrong letter gives a wrong date or `NULL` | `yyyy-MM-dd HH:mm:ss`; a language argument for names: `TO_LOCALDATE('dd-MMM-yyyy', s, 'en')` |
| a date parsed from text | malformed → `NULL`; but `CAST('2024-02-30' AS date)` → `2024-02-29`, silently corrected | `TO_LOCALDATE`, then count the `NULL`s against the non-empty inputs |
| `TRUNC(d, 'month')`, `ts2 - ts1` | Oracle masks, uppercase only: `'month'` returns `d` unchanged. A timestamp minus a timestamp is whole days: the hours are dropped | `TRUNC(d, 'MM')`; hours from `GETTIMEINMILLIS(ts2) - GETTIMEINMILLIS(ts1)` |
| `GETDAYOFWEEK(d)`, `EXTRACT(DOW FROM d)` | Sunday is `1` or `7`, `0` or `6`, by the i18n of the database you are connected to — the documentation's "Sunday is always 0" is wrong | `FORMATDATE('EEEE', d, 'us_pst') = 'Sunday'`, or `MOD(GETDAYSBETWEEN(DATE '1900-01-07', d), 7)`: `0` is Sunday |

Also silent, and in the reference: `LIKE` treats `$` as its escape character; `1.1` is a
`double`; `LOG(value, base)` takes the base second; `NULL`s sort last on `DESC` too; a
`timestamptz` formats to a different day under another i18n; and the same view can return
different figures depending on what Denodo pushes down to the source.

## Where to go from here

| Objects | Skill |
|---|---|
| Databases, folders, VDP tags | `/denodo:catalog` |
| Data sources, wrappers, base views — JDBC tables, DF and JSON files; every other source type it hands to Design Studio | `/denodo:datasources` |
| Derived views — joins, aggregates, unions, `FLATTEN` / `NEST` of arrays — interface views, associations | `/denodo:views` |
| Marketplace tags, categories, external elements (REST) | `/denodo:marketplace` |
| Stored procedures — calling one, or writing one | `/denodo:procedures` |
| The full cache of a view — switching it on or off, loading it, clearing it; where every other cache setting lives | `/denodo:cache` |
| KPIs defined once for every tool — metric views (`CREATE METRIC VIEW`), `evaluate_metric`, the views built on them | `/denodo:metrics` |
| Who may read what — a role and its grants, giving it to a user, masking columns or filtering rows with a global security policy over tagged columns, checking what a given user gets | `/denodo:security` |
| The LLM or the embedding model in a query — classifying, scoring, translating, summarising or extracting from a text column (`CLASSIFY_AI` …), a view that keeps those answers, semantic search over stored vectors (`VECTOR_DISTANCE`, `EMBED_AI`) | `/denodo:ai` |
| Changing rows in the database behind a view — `INSERT`, `UPDATE`, `DELETE`, `INSERT … SELECT`, an upsert, the generated key back, a view an application writes through (`WITH CHECK OPTION`) | `/denodo:dml` |
| The result of a query stored as a table — a remote table other tools read and its `REFRESH`, a frozen snapshot, a summary the optimizer answers aggregates from, a data movement for a slow federated join, a materialized table | `/denodo:materialize` |
| What people and AI consumers read about existing views — descriptions, primary keys, associations, the tag the MCP Server shows views by; "why does the agent not see this view" | `/denodo:semantics` |
| Regression tests a CI runs — `.denodotest` files for the Denodo Testing Tool beside the `.vql`, the tool's configuration from a profile, a red suite after a change | `/denodo:testing` |
| Work on a schedule — a nightly cache refresh, a `REFRESH` or a CSV export at a set time, running, pausing or reading a Denodo Scheduler job (REST) | `/denodo:scheduler` |
| Running anything against a live server, reading its errors | `/denodo:execute` |

There is no skill for the `SELECT` itself — an ad-hoc question, a report, the body of a
view: it is the SQL you know, with the expression deltas above and in
`references/dialect.md`. The server's own error texts are in `/denodo:execute`.

VDP tags (`CREATE TAG`, VQL, Virtual DataPort) and Data Marketplace tags
(`POST /public/api/tags`, REST) are different objects on different servers. "Tag" alone
does not tell you which — ask which one the human means, or look at where the object has
to be visible.
