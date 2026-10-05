# The `.denodotest` format, as the Testing Tool runs it

Sources: the Denodo Connects manual "Denodo Testing Tool — User Manual" (9.5), the tool's own
sources (`dist/denodo-testing-tool-9-<date>-sources.jar` in the download), and runs of release
`20260428` against Virtual DataPort 9.5.1 on 2026-10-05. A line marked *measured* was run; the
rest is the manual or the sources. The tool is a separate download from the Denodo support site
(Denodo Connects); the plugin does not ship it.

## Files, folders and order

- A test is a file ending in **`.denodotest`**. Anything else in a folder — `.csv`, `.vql`, a
  `.properties` — is skipped without a word, and so is a test whose name is misspelled
  (`checks.denodotests`) — *measured*. Count the tests in the summary against the files.
- A folder runs its files and subfolders in path order, with two exceptions: `first.denodotest`
  runs before everything else in its folder and must hold a `%SETUP`; `last.denodotest` runs after
  everything and must hold a `%TEARDOWN`. A folder holding only those two runs nothing.
- `index.denodoidx` in a folder replaces the path order: one locator per line, relative to the
  index, `#` comments allowed; a listed file that does not exist fails the run.
- A `file:` locator inside a test (`%RESULTS[csv] file:expected/x.csv`, `%SETUP[script]
  file:setup.vql`) is looked up from the tool's working directory first and from the test's own
  folder second. Run the tool from its `bin/` and write locators relative to the test —
  *measured*: `%RESULTS[csv] file:expected/x.csv` found the file beside the test.

## Directives

Each directive starts at a line beginning with `%` and a name in capitals — `%NAME`,
`%DESCRIPTION`, `%CONTEXT`, `%SETUP`, `%EXECUTION`, `%RESULTS`, `%TRACE`, `%TEARDOWN`,
`%EXTENDS` — and runs to the next one. `%Execution` is not `%EXECUTION`: the test then misses a
required directive. `%EXECUTION` and `%RESULTS` are required in every test except `first` and
`last`.

| Directive | Qualifiers | Context (`{…}` after the qualifier) |
|---|---|---|
| `%EXECUTION` | `[query]` one statement; `[script]` a file of statements, the last result set counts; `[ws]` an HTTP GET to a published REST service | `ds:<id>` for query and script, required; `datepattern:…`; `complex_ordered:false` |
| `%RESULTS` | `[data]` inline CSV; `[csv]` a CSV file; `[query]`, `[script]` another statement, on any data source; `[exception]`; `[ws]` | `ds:<id>`; `ordered:true\|false`; `type:full\|subset\|superset`; `datepattern:…`; `complex_ordered:false` |
| `%SETUP`, `%TEARDOWN` | `[query]`, `[script]` | `ds:<id>` |
| `%CONTEXT` | — | — : `key = value` lines, Java properties syntax |
| `%TRACE` | — | MVEL expressions over the execution trace (below) |
| `%NAME`, `%DESCRIPTION`, `%EXTENDS` | — | — |

`ds:` names a data source of the configuration file (`vdp` in what `testing config` writes). A
missing `ds` fails the test with `Missing data source`; an unknown one with `Error creating data
source '<id>'` — *measured*.

**Order inside one test:** SETUP, EXECUTION, RESULTS, TRACE, TEARDOWN, in one pass. Any exception
on the way stops the pass, and the TEARDOWN after it does not run (below).

## Parsing — what silently changes a test

*measured, unless noted*

- **A line starting with `#` is a comment anywhere** — inside a query and inside inline data. An
  expected value beginning with `#` disappears with its whole row, and the test then fails with
  `Obtained 1 rows, but expected 0`. Quote it: `"#1"`.
- **Blank lines are dropped everywhere.** In inline data a blank line is not an empty row.
- **`${name}` is a variable** in every directive. Text that contains `${` without a variable of
  that name fails the test (`… contains variables so context variables cannot be null`); write
  `\${` for a literal one, in the query and in the expected data alike.
- `\uXXXX` escapes are decoded everywhere before anything else (manual).
- Context values are separated by commas: a comma inside one (a date pattern) is `\,` (manual).
- A query may end with `;` or not.

## Comparison — the measured rules

| Case | What the tool does |
|---|---|
| Column names | matched **by name**, case-insensitive, in any order; a name that differs fails with `Expected data columns/headers do NOT match`. `[query]` against `[query]` therefore needs the same aliases on both sides |
| Row order | `[data]` and `[csv]` compare in order by default, `[query]`/`[script]` do not; the comparison is ordered when either side is. A `SELECT` without `ORDER BY` against inline data fails on its first row. Ordered comparison needs an `ORDER BY` on a unique key, or ties come back in any order |
| `type:subset` | checks that the expected rows are among the results. In an ordered comparison it walks both sides as if sorted, and fails with `Row 1 … contained [north], but [east] was expected` when the results are not sorted the same way — add `ordered:false`. **A subset with no expected rows passes against anything** |
| `type:superset` | the opposite: every obtained row must be among the expected ones, which may hold more. Same sorting rule as `subset` |
| Expected data with only the header line | means "no rows": passes on an empty result, fails with `Obtained 1 rows, but expected 0` otherwise |
| Numbers | compared as numbers: `12.5` equals `12.50`, `long` equals `int`. A `double` compares by its exact value: `0.1 + 0.2` is `0.30000000000000004`, not `0.3` — `ROUND` it in the query |
| Text | exact: case, inner and trailing spaces. Text from a file source is often padded to the column width, and an editor strips trailing spaces from the expected line — `TRIM` in the query, or quote the padded value |
| Text that looks like a number | under `ordered:false` the two sides are sorted differently (`'10'` before `'9'` as text, after it as a number) and equal data fails. Compare such columns ordered, with an `ORDER BY` |
| `NULL` | an empty field and the word `NULL` (any case) in expected data both mean `NULL`, and `NULL` equals an empty string. **No test can tell `NULL` from `''`** — compare `x IS NULL` as a column if it matters |
| `localdate` | `2024-03-05` |
| `timestamp` | `2024-03-05 10:11:12.000` — exactly; without the milliseconds, or with a `T`, it fails (the obtained value prints in the tool's own time zone, `2024-03-05T10:11:12+04:00`) |
| `timestamptz` | ISO 8601 with its offset, `2024-03-05T02:11:12-08:00`, compared as an instant |
| `boolean` | `true`, `false` |
| An error in `%EXECUTION` | the test fails with `Test raised an unexpected java.sql.SQLException: <message>` |

The simplest way past the date rules is to compare text: `FORMATDATE('yyyy-MM-dd HH:mm:ss', ts)
AS ts` in the query.

Inline data is CSV (RFC 4180): quote a value that holds a comma or a quote, starts with `#`, or
has leading or trailing spaces; a quote inside a quoted value is doubled. Complex values (arrays,
registers) have a text form of their own — braces for a register, brackets for an array, every
simple element in single quotes — with `complex_ordered:false` to ignore element order (manual).

## Expected errors

```
%RESULTS[exception] not found
```

passes when the execution raises an exception whose message (or a cause's) contains the text,
or whose class (or a cause's) is the one named — `java.sql.SQLException`. *measured*: `SELECT *
FROM no_such_view` passes with `not found`. An execution that raises nothing fails. Useful for a
restriction: a query as a user who must be refused.

## Variables and inheritance

- `%CONTEXT` holds `key = value` lines; `${key}` uses one anywhere in the test — *measured*.
  `#{some.property}` reads a global from the configuration file, the only place an `ENC(…)` value
  is decrypted.
- `key[] = a, b, c` runs the test once per value, every combination when there are several;
  `key[][] = [a, b], [c]` runs the inner lists in parallel threads (manual).
- `%EXTENDS ../base.denodotest` inherits: `NAME`, `DESCRIPTION`, `EXECUTION`, `RESULTS` — the
  child's wins; `CONTEXT` — merged, the child's key wins; `SETUP`, `TEARDOWN`, `TRACE` — the
  parent's run first, then the child's. A parent may have any extension
  (`common.denodocommon`), so it is not run as a test itself.

## SETUP and TEARDOWN

They run statements on the data source they name — VQL on `vdp`, SQL on any other — with no
classifier in between: a `DROP` or an `INSERT` there runs on whatever server the configuration
points at.

- **A failed SETUP statement fails the test and its TEARDOWN does not run**, and neither does
  the TEARDOWN after a `%RESULTS[query]` that fails — *measured*: a folder each such test created
  in its SETUP was still there afterwards. A failed comparison, and an `%EXECUTION` that raises an
  error, still run the TEARDOWN — *measured*. (The directives run in one pass that stops at the
  first exception it does not catch.)
- `[script]` splits a file on `;` outside single quotes; `#` and `--` start a comment, `/* */`
  too; a backslash escapes the next character — a Windows path or a regular expression in a
  string literal breaks the split; a `CREATE [OR REPLACE] VQL PROCEDURE` is kept whole until its
  `END;`.
- A statement that fails inside a SETUP or TEARDOWN script stops that script.

## The trace

`%TRACE` evaluates MVEL expressions such as `EXECUTION PLAN.state == 'OK'` against the trace of
the execution. *measured*: on Virtual DataPort 9.5.1 every test with a `%TRACE` failed with
`Test raised an unexpected java.util.NoSuchElementException: null`, with the 9.0.0 driver the
tool ships and with the server's own 9.5.1 driver alike. Check a plan with a query on
`GET_QUERY_EXECUTION_PLAN()` instead — the template is in the skill.

## Running it

`${CLAUDE_PLUGIN_ROOT}/scripts/denodo testing run --env <profile> --database <db> --tool <dir>
--java-home <java> <tests>` does what follows and reads the result for you. By hand:

```
cd "<tool home>/bin" && JAVA_HOME=<java 17+> bash denodo-test.sh file:<config> file:<tests>
```

*measured*:

- **Exit code `0` only when every test passed; `1` when one failed or the run broke** — a folder
  with no tests in it (`IllegalArgumentException: Testable cannot be null`), a path that does not
  exist (`The file: … does not exist.`), a configuration that cannot be read; those print a Java
  stack trace and no summary.
- **With a missing argument the launcher prints its usage and exits `0`.** A CI step whose
  variables expanded to nothing is green.
- The launcher comes out of the zip without its execute bit: `bash denodo-test.sh`, or
  `chmod +x` once.
- It logs to `../log/testing-tool.log` **relative to the working directory**: started from a
  project root, it creates a `log/` folder next to the project.
- `ERROR DriverDataSource … Failed to load class of driverClassName com.denodo.vdp.jdbc.Driver`
  at the start of every run is noise: the driver is then loaded from `drivers/<dbAdapter>/`.
- The console prints each failed test twice. The last lines are the summary: `Tests run: N, OK:
  M (FAILED: K)`, `Total tuples`, `Zero-tuple tests` — the tests whose comparison saw no row.
- `--failed-resumable` as a third argument reruns only what failed last time, through a
  `#denodo-failed-tests-execution.metafile` the tool writes into the tests folder: keep it out of
  git.

## The configuration file

`testing run` writes it for one run into a temporary file; `${CLAUDE_PLUGIN_ROOT}/scripts/denodo
testing config --env <profile> --database <db>` writes it beside the profiles file, readable by
its owner only, for a human who runs the tool themselves. Both write:

```
encoding=UTF-8
maxRowsInMemoryForMatching=10000
reporter=com.denodo.connect.testing.reporter.ConsoleTestReporter
vdp.driverClassName=com.denodo.vdp.jdbc.Driver
vdp.dbAdapter=denodo-9.0.0
vdp.jdbcUrl=jdbc:denodo://<host>:<jdbc_port>/<database>
vdp.username=<user>
vdp.password=<password>
vdp.connectionTestQuery=SELECT * FROM Dual()
```

- `jdbc_port` comes from the profile, 9999 when it names none; the profile's `port` is the ODBC
  one. `jdbc:denodo://` and the older `jdbc:vdb://` both connect — *measured*. `--db-adapter` names another folder under the tool's `drivers/` — *measured*: the 9.0.0
  driver the tool ships works against a 9.5.1 server, and so does the server's own driver
  (`<DENODO_HOME>/tools/client-drivers/jdbc/denodo-vdp-jdbcdriver.jar`) copied into a folder of
  its own. A driver newer than the server fails (manual).
- The tool reads the file as ISO-8859-1 with `java.util.Properties`; the command escapes the
  values for it. A value of the form `ENC(…)` is decrypted with Jasypt, the key coming from
  `DENODO_TEST_ENCRYPTION_PASSWORD` (environment or system property). There is no substitution
  of environment variables in this file.
- `connectionTestQuery` is required for Virtual DataPort: its driver does not implement
  `Connection.isValid()`.
- More data sources: `<id>.driverClassName`, `<id>.jdbcUrl`, `<id>.username`, `<id>.password`,
  and a driver jar in `drivers/<adapter>/`, in `lib/`, or on `DENODO_TEST_CLASSPATH`.
- Other reporters, for CI: `reporter.<name>=…CSVTestReporter` or `…HTMLTestReporter` with
  `reporter.<name>.pathToOutputFile` and `reporter.<name>.overwriteOutputFileIfExists`; several
  reporters run together when each has a name (`reporter.console=…`, `reporter.html=…`).
