---
name: testing
description: Use when a Denodo 9.5 project needs regression tests, or its tests need running or fixing — .denodotest files that the Denodo Testing Tool runs in CI (%EXECUTION, %RESULTS[data|query|csv|exception], configuration.properties, denodo-test.sh) — "add tests for this mart", "a safety net before I rewrite these views", "make sure the dashboards see no difference", "what should CI check on our data products", "prove the mart is right", "CI is red on the Denodo tests", a test that fails on row order, on a column it did not ask for or on a value padded with spaces. Not for checking a new view once, right after creating it — /denodo:views; not for verifying this plugin's own templates — verify in /denodo:execute.
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/denodo *)
---

# Regression tests with the Denodo Testing Tool

The suite is a folder of `.denodotest` files in the project, beside the `.vql` it tests, and
**Denodo's own Testing Tool runs it** — in the team's CI and here. The plugin has no runner of
its own: it writes the tests and starts the tool with `testing run`, which gives the tool its
configuration from the profile. The tool is a download from the Denodo support site (Denodo Connects) that
needs Java 17 or later; when the human has not said where it is, ask — never download or
install it yourself.

The checks themselves are the ones `/denodo:views` makes when it creates a view — a mart's
totals against its input, a unique key, nothing `INVALID`, the contract's columns, a query that
runs in its database — kept in files so that every later change is checked the same way. The
format in full, with every behaviour measured, is `references/format.md`.

**A test is worth what it can catch, and three things make one worthless without a sign:**

1. **A copy of today's output proves only that nothing changed.** If today's output is wrong,
   the copy locks the mistake in, and the suite is green over a broken mart. Tests that prove a
   mart *right* compare it with its input; a copy of its rows comes after those pass.
2. **A test that cannot fail.** Rows compared in an order the query does not fix, a subset of
   nothing, a query that finds no rows because it names the wrong database, a file whose name
   does not end in `.denodotest` — each passes, or is skipped, whatever the views do.
3. **A red test turned green by editing what it expects.** A failure is a finding about the
   views or about the test, and which one is established before anything is edited.

## Where the tests live

```
denodo/sales_analytics/
  00_database.vql
  01_connectivity.vql
  02_views.vql
  tests/
    household_income_by_band_counts_every_household.denodotest
    iv_household_income_key_is_unique.denodotest
    sales_analytics_has_no_invalid_view.denodotest
    household_income_contract.denodotest
    household_income_by_band_rows.denodotest
    expected/                      ← CSV files of expected rows, when inline data is too long
```

A project whose `.vql` files sit directly in `denodo/` keeps them in `denodo/tests/`.

- One check per file, the file named like its `%NAME`, and a `#` line on top that says what the
  check proves — that line is what the human reads when it fails. The `# verified:` line of the
  templates below is this plugin's own mark: leave it out of the project's tests. Any other file
  in the folder (a `README.md`, the expected CSVs) is skipped by the tool.
- `{ds:vdp}` on every `%EXECUTION`, `%RESULTS[query]`, `%SETUP` and `%TEARDOWN`, and view names
  unqualified: the database is the configuration's (`--database` below), so the same files run
  against every environment. Write the database name only where a procedure takes it
  (`GET_VIEWS()`, `GET_VIEW_COLUMNS()`).
- No `configuration.properties`, no wrapper script and no password in the project. The CI
  pipeline writes its own configuration from its secret store (**Running it**, below).

## Templates

`sales_analytics` holds the views of `/denodo:views`: `iv_household_income` joins
`bv_household_demographics` to `bv_income_band`, `household_income_by_band` aggregates it per
band, `household_income` is the interface view in front of it. Each block is one file of the
`tests/` folder.

### The mart counts every input row once

```text
# verified: 9.5.1 (live, 2026-10-06)
# Every household is counted once, in its band: a join that drops or doubles rows fails here.
%NAME household_income_by_band_counts_every_household
%EXECUTION[query] {ds:vdp}
SELECT SUM(household_count) AS household_count
FROM household_income_by_band
%RESULTS[query] {ds:vdp}
SELECT COUNT(*) AS household_count
FROM bv_household_demographics
```

- **This is the test that proves a mart right**, and the first one a mart gets. Both sides are
  queries, so it holds on any environment and after any load; no number is written down. Add a
  measure next to the count (`SUM(amount)` on both sides) when the mart sums one.
- Columns are matched **by name**: both queries give the same aliases, or the test fails on the
  header before any value is compared.
- When rows are dropped on purpose — a filter, an inner join the `DESCRIPTION` explains — the
  `%RESULTS` query applies the same condition, so the test states the decision instead of
  hiding it. When rows are dropped that nothing explains, write two tests: the rows that should
  match (with the condition) and every row (without it). The first is free to catch other
  defects, the second stays red until the human decides.
- **When the mart's grouping key comes from the input itself** (a foreign key of the fact),
  compare per group instead of the grand total — the mart's key and figures against `GROUP BY`
  that key on the input — for the same cost: it also catches a group split in two and rows that
  moved between groups.
- **A label for the rows without a match** (`COALESCE(region_name, '(no region)')` over a `LEFT
  JOIN`) gets a test of its own: no row of the mart carries the label with a key that is not
  `NULL` — a key with no row in the dimension lands there silently (`/denodo:views`). It is the
  first test a new source for the dimension fails.

### The key is unique

```text
# verified: 9.5.1 (live, 2026-10-06)
# Denodo does not enforce a primary key: a duplicated household doubles every figure above it.
%NAME iv_household_income_key_is_unique
%EXECUTION[query] {ds:vdp}
SELECT household_sk, COUNT(*) AS row_count
FROM iv_household_income
GROUP BY household_sk
HAVING COUNT(*) > 1
%RESULTS[data]
household_sk,row_count
```

The same test goes on **every view the mart joins to**, not only on the mart: a dimension that
keeps history has several rows per business key, and a join on that key multiplies every
figure above it.

Expected data with only its header line means "no rows". Such a test passes just as well when
its query finds nothing for a wrong reason, so run it once with `HAVING COUNT(*) > 0` and see it
fail (**Prove that each test can fail**, below).

### Nothing in the database is broken

```text
# verified: 9.5.1 (live, 2026-10-06)
# A view whose column went away underneath turns INVALID with no error anywhere.
%NAME sales_analytics_has_no_invalid_view
%EXECUTION[query] {ds:vdp}
SELECT name
FROM GET_VIEWS()
WHERE input_database_name = 'sales_analytics'
  AND input_retrieve_invalid_views_only = true
%RESULTS[data]
name
```

A view built on an `INVALID` one stays `OK` and fails on `SELECT`: this test names the first
broken view, the other tests of the suite fail on the rest. The same shape checks associations —
`SELECT association_name FROM GET_ASSOCIATIONS() WHERE input_database_name = 'sales_analytics'
AND input_type = 'views' AND valid = false` — *verified: 9.5.1 (live, 2026-10-05)*.

### The contract the consumer reads

```text
# verified: 9.5.1 (live, 2026-10-06)
# What a client of household_income sees: the columns, their order and their types.
%NAME household_income_contract
%EXECUTION[query] {ds:vdp}
SELECT ordinal_position, column_name, column_vdp_type
FROM GET_VIEW_COLUMNS()
WHERE input_database_name = 'sales_analytics'
  AND input_view_name = 'household_income'
ORDER BY ordinal_position
%RESULTS[data]
ordinal_position,column_name,column_vdp_type
1,household_sk,int
2,income_band_sk,int
3,buy_potential,text
4,dependents,int
5,vehicles,int
6,income_lower_bound,int
7,income_upper_bound,int
```

The data tests cannot see a column moved, retyped or added: the tool matches columns by name
and compares numbers by value. One view per test, with `=`: `input_view_name IN ( … )` answers
no rows and no error, which a "no rows" test would read as a pass. This one can, and it is the test a rename or a new column fails
first — on purpose: the contract changed, and the human says whether it should.

### The rows the consumer reads

The expected rows below are what the TPC-DS sample data gives; a suite of yours carries what
your server answers ("Expected values", below).

```text
# verified: 9.5.1 (live, 2026-10-06)
# The mart as the dashboards read it, ordered by its key. Taken after the count test passed.
%NAME household_income_by_band_rows
%EXECUTION[query] {ds:vdp}
SELECT income_band_sk, income_lower_bound, income_upper_bound, household_count, avg_dependents
FROM household_income_by_band
ORDER BY income_band_sk
%RESULTS[data]
income_band_sk,income_lower_bound,income_upper_bound,household_count,avg_dependents
1,0,10000,360,4.5
2,10001,20000,360,4.5
3,20001,30000,360,4.5
4,30001,40000,360,4.5
5,40001,50000,360,4.5
6,50001,60000,360,4.5
7,60001,70000,360,4.5
8,70001,80000,360,4.5
9,80001,90000,360,4.5
10,90001,100000,360,4.5
11,100001,110000,360,4.5
12,110001,120000,360,4.5
13,120001,130000,360,4.5
14,130001,140000,360,4.5
15,140001,150000,360,4.5
16,150001,160000,360,4.5
17,160001,170000,360,4.5
18,170001,180000,360,4.5
19,180001,190000,360,4.5
20,190001,200000,360,4.5
```

- **Name the columns and `ORDER BY` the key.** Inline data is compared in order, so a query
  without `ORDER BY` fails on its first row — or passes today and fails after the next change of
  plan. `SELECT *` fails the day a column is added, with the numbers unchanged. A key with a
  `NULL` row (the group of a `LEFT JOIN`) sorts by `CASE WHEN k IS NULL THEN 1 ELSE 0 END, k`:
  where the sort runs — Denodo, or the database it is delegated to — decides where `NULL`
  lands.
- This test pins **today's data**: it fails after a reload of the sources and on an environment
  with other data. Keep it for the refactor it protects — "the rewrite changes nothing" — and
  say so in its `#` line; the count test is the one that stays true.
- Past a few dozen rows, the expected rows go into a file: `%RESULTS[csv]
  file:expected/<name>.csv`, the same CSV with its header, relative to the test.

### A view over a database runs in the database

```text
# verified: 9.5.1 (live, 2026-10-06)
# The mart is one SQL statement in the warehouse: no expression left in Denodo, no second source.
%NAME household_income_by_band_runs_in_the_database
%EXECUTION[query] {ds:vdp}
SELECT COUNT(*) AS plans_not_delegated
FROM GET_QUERY_EXECUTION_PLAN()
WHERE input_query = 'SELECT * FROM household_income_by_band'
  AND (execution_plan LIKE '%noDelegationCause%'
       OR execution_plan LIKE '%JDBC ROUTE (%JDBC ROUTE (%')
%RESULTS[data]
plans_not_delegated
0
```

For a mart whose base views are JDBC (`/denodo:views`, Silent failure 3): a `MEDIAN` or a cast
the database cannot run, or a second data source, turns the answer to `1` — nothing else
reports it. The query is planned, not run. Quotes inside `input_query` are doubled. `%TRACE`
does not replace this test: against 9.5.1, with the Testing Tool release it was measured with,
it failed every test it was in (`references/format.md`).

## Expected values: from the server, after the checks pass

Never type an expected value from what the data "should" be, and never take one from a view
whose count test has not passed. Run the test's own query — `vql run --env dev --database
sales_analytics -e "<the %EXECUTION query>" --max-rows 500` — and write the rows as the tool
compares them:

| The value | Write it |
|---|---|
| `NULL` | an empty field. The tool cannot tell `NULL` from `''` — select `x IS NULL AS x_is_null` when it matters |
| text | exactly, case and spaces included; a file source may pad text to the column width — `TRIM` in the query rather than quoting padding an editor will strip |
| text with a comma or a quote, starting with `#` or a space | quoted: `"a, b"`, `"#1"`; a `"` inside doubled. **An unquoted line starting with `#` is a comment and its row is gone** |
| `${` | `\${` — in the query too |
| `decimal`, `int`, `long` | as `vql run` prints them; `12.50` equals `12.5` |
| `double` (an `AVG`, a ratio) | round it in the query — `ROUND(AVG(x), 2)` — never its full digits |
| `localdate` | `2024-03-05` |
| `timestamp` | format it in the query, `FORMATDATE('yyyy-MM-dd HH:mm:ss', ts) AS ts`, and write the text: the tool prints a `timestamp` in its own time zone and wants `.SSS` |
| `boolean` | `true`, `false` |

## Prove that each test can fail

Run each new test once **broken on purpose**, on a copy of the folder outside the project, in a
folder of your own with a fresh name — one
expected value changed, `HAVING COUNT(*) > 0` for a "no rows" test,
`input_retrieve_invalid_views_only = false` in the `GET_VIEWS()` test (it then lists the
database's views, which proves the name finds them) — run the copy and see every test fail with
the message you expect (`testing run` on the copy's folder). A test that passes both ways checks
nothing. An edited test that already fails against a regressed view has shown it can fail; see
it pass against the fixed definition (**When a test fails**, below). So does a test that is
red the day it is written: its expected side is proved only by passing against a definition
that is right. Then run the folder itself: `summary.run` must equal `test_files` — a file the tool
did not recognise is skipped without a word.

## Running it

```
${CLAUDE_PLUGIN_ROOT}/scripts/denodo testing run --env dev --database sales_analytics \
    --tool <where the Testing Tool was unzipped> --java-home <Java 17+> denodo/sales_analytics/tests
```

starts **the Denodo Testing Tool itself** on the folder (or one file): the tool parses the tests
and compares the results, the command only launches it. It writes the tool's configuration from
the profile into a temporary file readable by you only, runs the launcher from the tool's
`bin/`, deletes the file, and answers with one JSON document — `exit_code`, `summary` (`run`,
`ok`, `failed`, `zero_tuple`), each test with its `status` and `message`, `test_files` (the
`.denodotest` files it found), and on a failure `output_tail`, the last lines the tool printed.
`--tool` defaults to `DENODO_TESTING_TOOL_HOME`, `--java-home` to the environment's `JAVA_HOME`.

- **`ok: true` (exit `0`) needs the tool's exit code `0` and every test of the summary OK.** A
  run without a summary — a usage message, a Java stack trace — is a failure, and `warning`
  says when fewer tests ran than there are files: a misnamed one was skipped.
- The tests connect to `--database`; the JDBC port is the profile's `jdbc_port`, 9999 when the
  profile names none — not its `port`, which is the ODBC one.
- The tests run as the profile's user — often an administrator, whom no security policy
  restricts: a test of what a restricted person sees impersonates them (`/denodo:security`).
- On a profile marked `production` it refuses until the human's yes (**Safety**, below).

**When the human runs the tool themselves** — their terminal, a scheduled job on their machine —
`testing config --env dev --database sales_analytics` writes the same configuration to a lasting
file beside the profiles file (`<profiles dir>/testing/<env>/<database>.properties`, 0600) and
answers with its `path`, never the password; it refuses a path inside a git work tree the
repository does not ignore. Give them the launcher line, from the tool's own `bin/` — the tool
logs to `../log` of wherever it starts — with absolute paths and `bash`, because the launcher
comes out of the zip without its execute bit:

```
cd "<tool home>/bin" && JAVA_HOME=<java 17+> bash denodo-test.sh file:<path from testing config> file:<absolute path of tests/>
```

Never open that file and never put its path into a command of yours: run the tests with
`testing run`. The launcher exits `0` after printing its usage when an argument is missing, so
whoever runs it reads the summary — `Tests run: N, OK: M (FAILED: K)` — not only the exit code.
`ERROR DriverDataSource … Failed to load class of driverClassName` at its start is noise.

**For CI**, tell the human what the pipeline needs, and write none of it into the repository:
a configuration file with the keys `testing config` writes (`references/format.md`), made by the
pipeline from its own secret store, for a user that may only read the project's database; the
same launcher line; and a failed run when the summary is missing. If the repository already
holds a configuration with a password in it, say so: it has to leave git, and the password has
to change. Leave the file where it is — CI may still read it — and do not print it.

## When a test fails

| The message | What it says | What to do |
|---|---|---|
| `Expected data columns/headers do NOT match … expected [[a, b]] but obtained [[a, b, c]]` | the query returns other columns than the expected data names — a `SELECT *` over a view that gained one, or a renamed column | `SELECT *` in a test is the bug: name the columns. A renamed or removed column is a change of the contract: the human's call |
| `Row 1, col 1 of the obtained result contained [x], but [y] was expected` in a `[data]` or `[csv]` test, and `y` is further down the obtained rows | order, not data | `ORDER BY` the key in the query. In a `[query]` against `[query]` the same message is a row lost or gained — compare the row counts first |
| `Row n, col m … contained [x], but [y] was expected` | a value changed — or, in an unordered `[query]` against `[query]`, a row too many or too few: both sides are sorted and compared row by row | **establish which side is right before touching either** (below) |
| `Obtained n rows, but some of the expected m rows were not found` / `Expected results are only a subset … Obtained n rows, but expected m` | rows appeared or went missing. On a "no rows" test (`… but expected 0`) the check found what it looks for — duplicated keys, broken views | the count test says whether the mart still holds every input row; then as above |
| `Test raised an unexpected java.sql.SQLException: …` | the query itself fails: a view gone, renamed or `INVALID` | `GET_VIEWS(… invalid only)`; the views' own history |
| `… contains variables so context variables cannot be null` | a `${` in the test | `\${` |

**A value changed: which side is right.** Find what changed — `git log -p` of the `.vql`, and
the server against the file (`DESC VQL VIEW <view> ('includeDependencies' = 'no',
'dropElements' = 'no')`), because the view on the server may not be the one in git. Re-run the count test and compare the inputs
yourself. Then:

- the test was wrong (an order it relied on, a padded value, an unrounded double) — fix the
  test, and say what was wrong with it. **Both can be true at once**: a `SELECT *` without an
  `ORDER BY` over a view that also lost a row. Harden the test, and then it must still fail —
  for the real reason only;
- the views changed the answer — a label, a group, a total — **report it, and leave the test
  failing**: whether the new answer is intended is the human's decision. The view's own
  `DESCRIPTION` is evidence: a change that contradicts it is a regression until the human says
  otherwise.
- **Fixing the view is not fixing the test.** Re-applying a view that existed before this
  session changes what every reader of it gets — the dashboard, the report, the other views —
  and a request about tests did not ask for that. Put the fix into the `.vql` file, say what it
  changes, and leave applying it to the human's yes, even when the server would accept it
  without a word. When the fix itself needs a decision the human has not made, describe the
  options in the message instead of choosing one in the file.
- **Show that the fix turns the suite green without applying it**: a copy of the suite outside
  the project, with the view's name replaced by the fixed definition as a subquery — `FROM
  ( SELECT … ) m` — run with `testing run`. It reads only, and it proves the
  definition, not the deployed view; say both in the message.
- **Say what happens if nobody acts**: when the human named a date — a report, a release — the
  message says what that date gets from the server as it is now.

| Rationalization | Reality |
|---|---|
| "The numbers didn't change, the test is just out of date — regenerate the expected rows from today's output" | Regenerating turns any change, intended or not, into the new truth. Find which side moved first. |
| "The human called their change harmless, so the rest of the diff was an accident — I'll restore it on the server and CI is green" | Maybe it was an accident. Restoring it changes what the view's readers get, and nobody asked you to: the fix goes into the file, the yes is theirs. |
| "A snapshot of today's figures is a useful test too — it passes today" | It passes today *because* it copies today's mistakes. Rows are pinned after the count test passes, or the defect is pinned with them. |
| "The human is away and the deadline is close — I'll fix the view so the suite is green" | The finding, the fix in the file and a red suite that says why are the answer. |
| "`type:subset` is enough here" | It passes with any extra rows, fails on unsorted results unless `ordered:false`, and passes against anything with no expected rows. Use it for a known part of a large result, never to quiet a failure. |
| "I need the password for the configuration — I'll load it through the plugin's profile loader, or write a `run-tests.sh` that builds the file from environment variables" | `testing run` gives the tool its configuration from the profile; neither you nor a command line ever holds the password, and the project gets no runner to maintain. |
| "There is no password I may read, so the tests cannot run — I'll leave them unrun" | `testing run` is the way to run them. A suite that never ran has proved nothing, not even that it parses. |
| "The repository already has a configuration with the password, and CI uses it" | Run with `testing run`, and tell the human: the file has to leave git and the password has to change. |

## Safety

The Testing Tool runs whatever a test holds — `%SETUP`, `%TEARDOWN`, an `%EXECUTION[script]` —
on the server of its configuration, **past the classifier every other command of this plugin
applies**. So:

- **A suite reads.** `%EXECUTION[query]` and `%RESULTS[query]` with a `SELECT`, and nothing
  else, is what this skill writes. A test that needs data or objects of its own is a fixture in
  the project's own database, created by a `.vql` file through `/denodo:execute` like any other
  object — not by a `%SETUP`.
- **A suite you did not write is a file of statements**: read every `%SETUP`, `%TEARDOWN` and
  script before running it. Running one that changes state is applying VQL — `/denodo:vql`'s
  table decides who runs it.
- **A failed `%SETUP` statement skips the `%TEARDOWN`** of its test, and so does a failing
  `%RESULTS` query: whatever the setup created stays on the server — *verified: 9.5.1 (live,
  2026-10-05)*.
- On a profile marked `production`, `testing run` and `testing config` refuse without
  `--allow-destructive`.
  Show the human what the suite runs; the flag comes after their yes, as everywhere in this
  plugin (`/denodo:execute`).

**Red flags — stop:** you are about to change an expected value to what the server returns now;
a test passes and you have not seen it fail; a password, a `configuration.properties` or a
script that builds one is about to enter the project; you are reading the profiles file, or
opening or naming in a command the file `testing config` wrote; a suite you are about to run
has a `%SETUP` or a `%TEARDOWN`; `env.production` is `true`.

## Verify

| Question | Read-back |
|---|---|
| Did every test run | `summary.run` equals `test_files`, and there is no `warning` |
| Did they pass | `ok: true` — the tool's exit code `0` **and** every test of the summary OK |
| Did the data tests see data | `summary.zero_tuple` equals the number of "no rows" tests; one more means a data test compared nothing |
| Can each new test fail | the broken run of **Prove that each test can fail**, one per test |
| Is the project clean | `git status`: no configuration file, no `log/` folder, no `#denodo-failed-tests-execution.metafile` |

## Reference

- `references/format.md` — the format in full: files, folders and order, every directive and
  qualifier, parsing traps, the comparison rules measured case by case, expected errors,
  variables and inheritance, `%SETUP`/`%TEARDOWN`, the trace, the launcher's exit codes and
  log, the configuration file and its keys.
