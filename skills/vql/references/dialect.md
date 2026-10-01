# VQL expressions versus the SQL you know

VQL reads like PostgreSQL and is not. Most differences are loud — a function that does not
exist, a clause the parser refuses — and cost one attempt. This file is mostly about the
other kind: **the statement runs, and the value is wrong, or `NULL`, with no error and no
warning.** A mart built on one of those reads like real data.

Every row below was run on the server, `SELECT … FROM Dual()` unless it names a view —
*verified: 9.5.1 (live, 2026-09-30)*. Rows marked *delegated* were run against views over
JDBC sources, because there the answer changes.

## Check an expression before it goes into a view

An expression you have not used in VQL before — a substring, a date pattern, a cast, a
division — gets one run on `Dual()` with an input whose answer you already know:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/denodo vql run --env dev -e "SELECT SUBSTR('abcdef', 1, 3) AS want_abc, TO_LOCALDATE('yyyy-MM-dd', '2024-03-15') AS want_mar_15 FROM Dual()"
```

That is a read, so it goes inline. Name each column after the answer you expect, and choose
the input so that the wrong reading gives a different answer: `'abcdef'` and `1, 3` tell 0-based from 1-based and length from end index at
once; `2024-12-30` tells a calendar year from a week year; `2.9` tells truncation from
rounding. After a parse or a cast over real rows, count the `NULL`s it produced — a
`NULL` is how most of the failures below report themselves.

## Text

| You write | Denodo does | Write instead |
|---|---|---|
| `SUBSTRING(s, 1, 3)` for the first three characters | the comma form is **0-based and takes an end index**, not a length: `'abcdef'` → `'bc'`; `SUBSTRING(s, 1, 1)` → `''` | `SUBSTR(s, 1, 3)`, `SUBSTRING(s FROM 1 FOR 3)` (SQL-92, 1-based, length) or `LEFT(s, 3)` → `'abc'` |
| `SUBSTRING(s, POSITION('@' IN s) + 1)` for what follows `@` | `POSITION` is 1-based, the comma `SUBSTRING` 0-based: `'a.b@example.org'` → `'xample.org'`. The opposite mix, `SUBSTR(s, INSTR(s, '@') + 1)`, keeps the `@` → `'@example.org'` | one family per expression: `SUBSTR` with `POSITION` (1-based), or `SUBSTRING` with `INSTR` (0-based) → `'example.org'`. Guard the separator: with no `@`, `POSITION` is `0` and `SUBSTR(s, 1)` returns the whole string — add `WHERE POSITION('@' IN s) > 0` |
| `INSTR(s, x)` | **0-based, `-1` when absent**: `INSTR('abcabc', 'c')` → `2`. `POSITION('c' IN 'abcabc')` and `STRPOS('abc', 'c')` are 1-based, `0` when absent | test for presence with `POSITION(x IN s) > 0` |
| `s = 'abc'`, `GROUP BY s` | exact: case **and trailing spaces** count, in comparisons, `GROUP BY` and `DISTINCT` alike. `'abc' = 'abc  '` is false; a file source that pads its fields to a fixed width matches nothing, and a piece cut from a padded field keeps a different amount of padding on every row, so grouping on it splits every group | `TRIM` first, then cut: `SUBSTR(TRIM(s), …)`. `UPPER(TRIM(s)) = 'ABC'` or `GROUP BY LOWER(…)` when case must not matter (e-mail domains). `LIKE 'abc%'` survives the padding |
| `number_col > '9'`, `text_col > 900` | a comparison that mixes text and a number compares **as text**, in both directions: `day_of_month > '9'` returns no rows at all, because `'10'` to `'31'` sort below `'9'` as text; a text column of street numbers `> 900` counts `'95'` above 900 and `'1000'` below it. `=` and `IN` still convert | compare numbers as numbers: a number literal, or `CAST(text_col AS integer)` after checking the text |
| `s LIKE 'US$%'` | **`$` is the default escape character**: `$%` means a literal `%`, so `'US$5' LIKE 'US$%'` is false | add `ESCAPE '!'` (any character not in the pattern) to every pattern that contains `$` |
| `s LIKE 'a\_b'` | backslash is an ordinary character — the PostgreSQL escape matches nothing | `LIKE 'a$_b'`, or `ESCAPE` |
| `ILIKE` | does not exist | `UPPER(s) LIKE 'ABC%'`, or `s REGEXP_ILIKE 'abc.*'` |
| `LEN(s)` / `LENGTH(s)` | `LENGTH` does not exist; `LEN` counts trailing spaces: `LEN('abc  ')` → `5` | `LEN(TRIM(s))`; `CHAR_LENGTH` also exists |
| `REPLACE(s, '.', '-')` | literal, as expected. `REGEXP(s, '.', '-')` is the regex one — `'a.b.c'` → `'-----'` | pick by intent; escape regex metacharacters in `REGEXP`, `SPLIT` and `REGEXP_LIKE` |
| `SPLIT_PART(s, ',', 2)` | does not exist. `SPLIT(',', s)` takes the **regex first** and returns an array, indexed from **0** | parse with `SUBSTR` and `POSITION`, or see `/denodo:views` for arrays |
| `TRIM(BOTH 'xy' FROM s)` | only the **first** character of the trim set is used: `'xxabcyy'` → `'abcyy'` | a regex, below |
| `CONCAT('abc', NULL)`, and the operator form below | `NULL` — as in PostgreSQL, unlike Oracle | `COALESCE(x, '')` around each nullable part |
| `'' IS NULL`, `COUNT(s)` to find missing values | `''` is a value, unlike Oracle. A file source writes a missing field as `''`, padded to the column width, so `COUNT(s)` counts it as a value, and a `NULL` count reports nothing missing | `COUNT(NULLIF(TRIM(s), ''))` counts the values actually there |
| `ORDER BY name` | by Unicode code point: `A, B, a, b` | `ORDER BY UPPER(name)` when people read the order |

`'abc' || NULL` is `NULL`, like `CONCAT`. A set of trim characters needs a regex:
`REGEXP(s, '^[xy]+|[xy]+$', '')` → `'abc'`.
`UPPER('straße')` → `'STRASSE'` and `INITCAP('hello WORLD')` → `'Hello World'` behave as
Java does.

## Numbers and casts

| You write | Denodo does | Write instead |
|---|---|---|
| `CAST(x AS integer)` to round | **truncates** when Denodo computes it: `2.9` → `2`, `-2.9` → `-2`. The same `CAST` **delegated** to PostgreSQL rounds: `2.75` → `3`. One view, two answers, depending on where the expression runs | `ROUND(x)`, `FLOOR(x)`, `TRUNC(x)` — whichever you mean, explicitly |
| `CAST(text AS integer)` | garbage is not an error: `'12abc'` → `12`, `'2.9'` → `2`, `'abc'` → `NULL`, `' 12 '` → `12` | check the text first: `WHERE TRIM(s) REGEXP_LIKE '^-?[0-9]+$'` — without `TRIM` a padded value never matches — and count what does not match. `LIKE` and `REGEXP_LIKE` are not columns: `SELECT s REGEXP_LIKE … AS ok` is a syntax error (a comparison or `IS NULL` projects fine); project `CASE WHEN … THEN 1 ELSE 0 END` |
| `CAST(3000000000 AS integer)` | **wraps around**: `-1294967296` | `CAST(x AS bigint)`; `integer` holds ±2 147 483 647 |
| `a + b` on `int` values past the range | **`NULL`** — no error: `2147483647 + 1`, a literal or a column. Multiplication past the range fails instead, with a bare `Error executing query` that names nothing | widen first: `CAST(a AS bigint) + b`, `CAST(a AS bigint) * b` |
| `a / 0` | **`NULL`**, for integers and doubles alike — a broken denominator disappears into the result | `CASE WHEN b = 0 THEN … END` stating what zero means, and count those rows |
| `7 / 2`, `COUNT(x) * 100 / COUNT(*)` | integer division, `3` and a truncated percentage — as in PostgreSQL, unlike Oracle | `100.0 * COUNT(x) / COUNT(*)` |
| `price * 1.1`, `0.1 + 0.2` | a literal with a decimal point is a **`double`**: `0.1 + 0.2` → `0.30000000000000004`, and `0.1 + 0.2 = 0.3` is false | `CAST(0.1 AS decimal)` next to money; `decimal` arithmetic is exact (`0.3`) |
| `CAST(a AS decimal) / b` | `decimal` division keeps six decimals when the inputs have fewer: `10.00 / 3.00` → `3.333333` | `ROUND` to what you publish, and do not chain divisions on the rounded value |
| `CAST(2.565 AS decimal(10,2))` | rounds half up → `2.57`, while `CAST(… AS integer)` truncates; a value too wide for the precision is an error | say which rounding the column carries |
| `ROUND(2.5)` | half away from zero: `3`, `-3`; also for `double` | — |
| `LOG(8, 2)` | **value first, base second** → `3` (log₂ 8). PostgreSQL and Oracle take the base first | `LOG(value, base)`; `LOG(x)` is base 10, `LN(x)` natural |
| `GREATEST(a, b)`, `LEAST` | do not exist. Their substitute, the scalar `MAX(a, b)` / `MIN(a, b)`, returns **`NULL` when any argument is `NULL`** | `MAX(COALESCE(a, b), COALESCE(b, a))` |
| `CAST('yes' AS boolean)` | `false`; `'true'` and `'1'` are true | map the source's values with `CASE` |
| `CAST(x AS double)`, `CAST(x AS int)`, `CAST(x AS long)` | syntax errors — a `CAST` takes SQL type names | `CAST(x AS double precision)`, `CAST(x AS integer)`, or the VQL names in the two-argument form: `CAST('double', x)` |

### Aggregates

- **`SUM` over an `int` column stays `int` and overflows silently** — past 2 147 483 647 it
  returns `NULL` or a wrong number that looks real: three rows of 2 000 000 000 summed to
  `2000000000`; on a 68 636-row fact column `1140298269` instead of `168668968269`
  (*verified: 9.5.1 (live, 2026-09-12)*). Cast the input: `SUM(CAST('long', x))`.
  **Never over `decimal`**: the same cast truncates every row before the sum — `183734747`
  against a true `183801994.51` on a 144 067-row money column (*verified: 9.5.1 (live,
  2026-09-12)*). `decimal` and `double` measures need no cast. `AVG` over `int` does not
  overflow and returns `double`.
- `COUNT(x)` skips `NULL`; `AVG(x)` divides by `COUNT(x)`, not by `COUNT(*)`. When the two
  differ, say in the answer which denominator the average is over — a "per line" average over
  a measure with `NULL`s has two defensible values.
- `AVG` over a `decimal` column returns a `decimal` that is exact to about twelve significant
  digits and noise after: `721.88727540500000001458…` where the true mean is
  `721.8872754050073…`. Harmless once rounded — `ROUND(AVG(x), 2)` — but not an exact figure
  to compare or to divide further.
- `GROUP_CONCAT(sep1, sep2, a, b)` **drops the whole row when any of the fields is `NULL`**;
  `GROUP_CONCAT(false, sep1, sep2, a, b)` keeps it with `NULL` as empty. `STRING_AGG(x, ',')`
  and single-field `GROUP_CONCAT(x)` skip `NULL` values only.
- **`MEDIAN(x)` computed by Denodo returns a `decimal` rounded half up to two places**, whatever
  the input's scale: `{0.001, 0.002}` → `0.00`, `{1.0001, 1.0004, 1.0007}` → `1.00`, a
  `double` `0.123456` → `0.12`. An even count gives the mean of the two middle values,
  rounded the same way (`{1, 2}` → `1.50`); `NULL`s are skipped (*verified: 9.5.1 (live,
  2026-09-30)*). Delegated, it is another function — see "Delegation changes the answer".
- Empty input: `SUM`, `AVG` → `NULL`, `COUNT(*)` → `0`, as in standard SQL.
- The documentation says `COUNT(field)` needs a `GROUP BY`; it does not — `COUNT(x)` over the
  whole view works.

## Dates and times

**Patterns are Java `SimpleDateFormat`, and the pattern comes first:**
`TO_LOCALDATE('yyyy-MM-dd', s)`, `TO_TIMESTAMP('yyyy-MM-dd HH:mm:ss', s)`,
`FORMATDATE('yyyy-MM', d)`. Case is meaning, and **a wrong pattern returns a wrong date or
`NULL`, never an error**:

| Pattern letter | Means | Wrong guess and what it does |
|---|---|---|
| `yyyy` | calendar year | `YYYY` is the **week year**: `FORMATDATE('YYYY-MM', DATE '2015-12-30')` → `'2016-12'`. A monthly report labelled this way puts the last days of December under the next year — measured on a real fact: 774 lines under `2015-12`, 120 under `2016-12` |
| `MM` | month | `mm` is minutes: `TO_LOCALDATE('yyyy-mm-dd', '2024-03-15')` → `2024-01-15`; `FORMATDATE('yyyy-mm-dd', …)` → `'2024-00-15'` |
| `dd` | day of month | `DD` is day of year: `FORMATDATE('yyyy-MM-DD', DATE '2024-03-15')` → `'2024-03-75'`; `TO_LOCALDATE('YYYY-MM-DD', …)` → `NULL` |
| `HH` | hour 0–23 | `hh` is 1–12: `'13:45'` parsed with `hh:mm` → `NULL` |
| `yy` | two-digit year | lands in **2000–2099**: `'15.03.70'` → `2070-03-15`. A source that writes `02-JAN-00`, parsed with `'dd-MMM-yy'`, loses its century — a date dimension spanning 1900–2100 folds onto 2000–2099, two rows per date, while its own year column still says 1900 |
| `MMM`, `EEE` | month and day names | read and written **in the language of the i18n**: `TO_LOCALDATE('dd-MMM-yyyy', '02-JAN-2000')` is `NULL` under a Spanish i18n, which expects `ene`; `FORMATDATE('dd MMM yyyy', …)` writes `'02 ene 2000'`. A view that parses English month names returns nothing but `NULL` dates when it is queried from a database with another i18n. Pass the language: `TO_LOCALDATE('dd-MMM-yyyy', s, 'en')` |
| Oracle / PostgreSQL masks (`YYYY-MM-DD`, `HH24:MI:SS`) | — | `NULL` |

| You write | Denodo does | Write instead |
|---|---|---|
| `TO_DATE('2024-03-15', 'YYYY-MM-DD')` (Oracle order) | `NULL`. `TO_DATE` is also deprecated and returns the deprecated `date` type | `TO_LOCALDATE('yyyy-MM-dd', s)`, `TO_TIMESTAMP(…)`, or the literals `DATE '2024-03-15'`, `TIMESTAMP '2024-03-15 10:20:30'` |
| a parse over text that may be malformed | `TO_LOCALDATE` returns `NULL` for anything that does not match, including `'2024-02-30'`, a leading space or a trailing time | count the `NULL`s against the non-empty inputs |
| `CAST('2024-02-30' AS date)` | **corrected, not refused**: `2024-02-29`; `'2024-04-31'` → `2024-04-30`; `'2023-02-29'` → `2023-02-28`. Month `13` or another layout → `NULL`. The literal `DATE '2024-04-31'` is `NULL` too | `TO_LOCALDATE` when invalid dates must stay visible as `NULL` |
| `date_col > '2024-03-01'` | works; by the documentation, the text is read with the date pattern of the query's i18n | `date_col > DATE '2024-03-01'` |
| `TO_CHAR(d, 'YYYY-MM')` | does not exist | `FORMATDATE('yyyy-MM', d)` |
| `DATE_TRUNC('month', d)` | does not exist | `TRUNC(d, 'MM')` or `FIRSTDAYOFMONTH(d)` — over a timestamp `FIRSTDAYOFMONTH` **keeps the time of day**: `TIMESTAMP '2024-12-30 10:20:30'` → `2024-12-01T10:20:30`, so two rows of one month group apart (*verified: 9.5.1 (live, 2026-09-30)*). Over a timestamp, `TRUNC(d, 'MM')` or `CAST(FIRSTDAYOFMONTH(d) AS date)` |
| `TRUNC(d, 'month')` | Oracle masks, **uppercase only**: `'MONTH'`, `'MM'`, `'Q'`, `'YYYY'` work; `'month'`, `'Mon'`, `'yyyy'` or a typo return **`d` unchanged** — every day stays its own group | uppercase masks; check one row. The first day of the quarter as a label: `FORMATDATE('yyyy-MM-dd', TRUNC(d, 'Q'))` |
| `d + 1` | error | `d + INTERVAL '1' DAY`, `ADDDAY(d, 1)`, `ADDMONTH(d, 1)` (31 Jan + 1 month → 29 Feb) |
| `d2 - d1` on dates | whole days as `long` — as in PostgreSQL | — |
| `ts2 - ts1` on timestamps, for hours | **whole 24-hour periods, hours discarded**: 23:00 → 01:00 next day is `0`, 46 hours is `1`. `GETDAYSBETWEEN(ts1, ts2)` counts calendar days instead (`1` for the same pair) | hours: `(GETTIMEINMILLIS(ts2) - GETTIMEINMILLIS(ts1)) / 3600000.0` |
| `GETDAYSBETWEEN(a, b)`, `GETMONTHSBETWEEN(a, b)` | positive when `a` is the earlier date — the reverse of `a - b` | earlier first |
| `DATEADD`, `DATEDIFF`, `AGE`, `GETYEARSBETWEEN`, `ADD_MONTHS`, `MONTHS_BETWEEN`, `LAST_DAY`, `SYSDATE`, `GETDATE()`, `EXTRACT(EPOCH …)` | do not exist | `ADDDAY`/`ADDMONTH`/`+ INTERVAL`, `GETDAYSBETWEEN`, `GETMONTHSBETWEEN`, `LASTDAYOFMONTH`, `CURRENT_DATE`/`LOCALTIMESTAMP`, `GETTIMEINMILLIS(ts) / 1000` |
| `YEAR(d)`, `MONTH(d)`, `DAY(d)` | `Function 'year' with arity 1 not found` (*verified: 9.5.1 (live, 2026-09-30)*) | `GETYEAR(d)`, `GETMONTH(d)`, `GETDAY(d)`, or `EXTRACT(YEAR FROM d)` |
| `TIME '10:00' - TIME '08:30'` | milliseconds: `5400000` | divide explicitly |

Two recipes that come up with every customer table, both checked:

- **A date from three integer columns:**
  `TO_LOCALDATE('yyyy-M-d', CAST(y AS varchar) || '-' || CAST(m AS varchar) || '-' || CAST(d AS varchar))`
  — single `M` and `d`, because the cast gives no leading zeros; an impossible date such as
  `1937-2-29` comes back `NULL`, so count them.
- **Age in completed years:** `FLOOR(GETMONTHSBETWEEN(birth_date, DATE '2026-09-30') / 12)` —
  `GETMONTHSBETWEEN` counts completed months, so the day before the birthday still gives the
  lower age. There is no `GETYEARSBETWEEN` and no `AGE`.

**The day of the week depends on the i18n — every function that returns it.** The i18n in
effect is the one of the database you are connected to (`GETSESSION('i18n')`), or a
`CONTEXT('i18n' = …)` at the end of the query; a `CONTEXT` inside the definition of the view
you read from did not change it. So the same query answers differently in two databases,
and nothing says so:

| Expression | Sunday, US i18n (`us_pst`) | Sunday, European i18n (`es_euro`, `gb`) |
|---|---|---|
| `GETDAYOFWEEK(d)` | `1` | `7` |
| `EXTRACT(DOW FROM d)` — the documentation says Sunday is always `0` | `0` | `6` |
| `FORMATDATE('EEEE', d)` | `'Sunday'` | `'domingo'` |
| `FORMATDATE('EEEE', d, 'us_pst')` | `'Sunday'` | `'Sunday'` — the third argument fixes the language |
| `MOD(GETDAYSBETWEEN(DATE '1900-01-07', d), 7)` | `0` | `0` — days since a known Sunday, for any `d` from 1900 on |

Use one of the last two when the result must not depend on where the query runs. Delegated to
a database, the database's own rule applies. `FIRSTDAYOFWEEK` / `LASTDAYOFWEEK` follow the
i18n the same way (Sunday or Monday). `EXTRACT(WEEK …)` and `GETWEEK` are ISO weeks while
`EXTRACT(YEAR …)` is the calendar year: `2024-12-30` is week `1` of year `2024`.

**Time zones.** `timestamp` and `localdate` carry none; `timestamptz` and the deprecated
`date` do. Casting a `timestamptz` to `timestamp` moves it into the **server's** zone
(`23:30 +00:00` → `16:30` on a server at `-07:00`); `CURRENT_DATE`, `LOCALTIMESTAMP` and `NOW()`
are the server's clock too. **Formatting a `timestamptz` renders it in the time zone of the
i18n**, so the day can change with the database you are connected to: `FORMATDATE('yyyy-MM-dd
HH:mm', …)` of `2024-03-15 23:30 +00:00` is `'2024-03-15 16:30'` under `us_pst` and
`'2024-03-16 00:30'` under `es_euro`. A monthly label over a `timestamptz` moves the last hours
of a month into the next one.

## `NULL`, ordering and the shape of a query

| You write | Denodo does | Write instead |
|---|---|---|
| `ORDER BY x DESC` | `NULL`s last **in both directions** — PostgreSQL and Oracle put them first on `DESC`. `NULLS FIRST/LAST` is a syntax error | `ORDER BY CASE WHEN x IS NULL THEN 0 ELSE 1 END, x DESC` |
| `LIMIT 10 OFFSET 20` | syntax error | `OFFSET 20 LIMIT 10`, or `OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY` |
| `TOP 10`, `DISTINCT ON (…)`, `IS DISTINCT FROM` | syntax errors | `LIMIT`; a window function (below) or a `GROUP BY`; spell the `NULL` case out |
| `NVL(a, b)`, `IFNULL(a, b)` | do not exist | `COALESCE(a, b)` |
| `x NOT IN (1, NULL)`, `x = NULL` | never true — standard SQL | `IS NULL`; keep `NULL` out of `NOT IN` lists |
| `GROUP BY 1`, `ORDER BY 1`, `WITH t AS (…)` | work as in PostgreSQL | — |
| `UNION` | removes duplicates (since 8.0; older examples behave as `UNION ALL`) | `UNION ALL` unless you mean it |
| `SELECT a, b … UNION ALL SELECT b, a …` | matched by **position**, and the names of the result can come from either branch: queries over it then disagree about which value is `a` — no error | the same columns, in the same order, under the same aliases in every branch (`/denodo:views`, `references/unions.md`) |
| `ROW_NUMBER() OVER (…)` and every other window function | runs only when delegated to a database that has it; over a file source or `Dual()` — and by the documentation any source that cannot run it — `Function row_number is not executable` | window functions over JDBC views; otherwise aggregate and join back |
| `"abc"` for a string | an identifier: `Field not found 'abc'` | single quotes; a quote inside is doubled: `'it''s'` |
| `x contains 'a'` (old examples) | the `contains` family is removed | `LIKE`, `REGEXP_LIKE` |

## JSON

| You write | Denodo does | Write instead |
|---|---|---|
| `doc ->> 'a'`, `JSON_VALUE`, `JSON_EXTRACT` | do not exist | `JSONPATH(doc, '$.a.b')` |
| `JSONPATH(doc, path)` | returns **text** (`'5'`), `NULL` for a missing path **and** for a document that is not JSON; `JSONPATH(doc, path, true)` keeps quotes on strings | cast the result, and count `NULL`s against non-empty documents |

## Delegation changes the answer

Denodo pushes expressions down to the source when it can, and the source then decides. The
same view can return different values depending on what runs where — after a join to a file
source, a cache, or a change of source, the query plan and the answer move together.

| Expression | Denodo computes it | Delegated |
|---|---|---|
| `category = 'household'` against `'Household'` | no match — exact | SQL Server: 667 matches, case and trailing spaces ignored (*delegated*) |
| `CAST(2.75 AS integer)` | `2` | PostgreSQL: `3` (*delegated*) |
| `GETDAYOFWEEK`, `EXTRACT(DOW …)`, `FIRSTDAYOFWEEK` | the i18n of the connection | the database's own rule |
| `SUBSTRING(s, 1, 3)` | `'bc'` | PostgreSQL: `'bc'` too — Denodo translates it (*delegated*) |
| window functions | not executable | the database runs them (*delegated*) |
| `MEDIAN(x)` | the mean of the two middle values, rounded to two places | PostgreSQL: `PERCENTILE_DISC(0.5)`, full precision and no mean — `107.5242857…` where Denodo says `107.53` over the same 62 874 rows (*delegated*); SQL Server does not take it at all |

Whether an expression was delegated at all is in the query plan — `/denodo:views`,
`references/delegation.md`.

When a figure must not depend on the plan, write the expression that means the same everywhere:
`UPPER(TRIM(…))` on both sides, `ROUND` instead of a `CAST`, days since a known Sunday
instead of a weekday number.

## Legacy VQL in old examples

- The `date` type and `TO_DATE` are deprecated: `localdate`, `timestamp`, `timestamptz` and
  `TO_LOCALDATE` / `TO_TIMESTAMP` / `TO_TIMESTAMPTZ` replace them. In a `CAST`, the SQL name
  `DATE` means `localdate`: `CAST('2024-03-15' AS date)` → `2024-03-15`.
- `CATALOG_ELEMENTS`, `CATALOG_VIEWS` and the other `CATALOG_*` procedures are deprecated:
  `GET_ELEMENTS`, `GET_VIEWS`, `GET_PRIMARY_KEYS`, `GET_FOREIGN_KEYS`.
- Before 8.0, `UNION` kept duplicates.
- Type names in declarations and in `CAST` differ (`int` / `integer`, `long` / `bigint`,
  `text` / `varchar`, `double` / `double precision`: `CAST(x AS double)` is a syntax error) —
  the table is in `/denodo:views`.
