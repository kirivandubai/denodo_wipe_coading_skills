---
name: procedures
description: Use when a Denodo 9.5 stored procedure is in play — calling one the server already ships (SELECT … FROM GET_VIEWS() / USED_BY() … WHERE input_… = …, the CALL statement, finding which predefined procedure answers a question and what parameters it takes), writing your own procedural logic in VQL (CREATE OR REPLACE VQL PROCEDURE … BEGIN … END, local variables, IF/LOOP/CASE, cursors, exceptions, EXECUTE of DDL), or importing a Java one from a JAR (CREATE PROCEDURE … CLASSNAME … JARS). Also for "run the stats procedure", "loop over rows and create views", "call that procedure from a view". Not for introspecting a JDBC source into base views — that is /denodo:datasources.
---

# Stored procedures

Three kinds live under one name in Virtual DataPort, and the first thing to settle is
which one the request is about:

| Kind | Statement | When |
|---|---|---|
| **Predefined** | none — you only call it | the server ships them — `LIST PROCEDURES` shows which yours has; metadata, dependencies, statistics, cache |
| **VQL procedure** | `CREATE OR REPLACE VQL PROCEDURE` | procedural logic — variables, branches, loops, cursors — without Java |
| **Java procedure** | `CREATE OR REPLACE PROCEDURE … CLASSNAME` | a compiled class from a JAR already imported into the server |

`CREATE PROCEDURE` and `CREATE VQL PROCEDURE` are **different statements for different
objects**. Drop the word `VQL` from a procedure that has a body and the parser stops at the
parameter list: `Syntax error: Exception parsing query near '('`.

Everything here is VQL, sent over the profile's ODBC (PostgreSQL-protocol) port of Virtual
DataPort (9996 by default).
Introspecting a JDBC source into base views also runs through predefined procedures
(`PING_DATA_SOURCE`, `GET_JDBC_DATASOURCE_TABLES`, `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW`),
but that is a step of a different job and lives in `/denodo:datasources`. Databases, folders
and VDP tags are `/denodo:catalog`; derived views are `/denodo:views`; the working loop,
naming and the safety rule are `/denodo:vql`; apply the file with `/denodo:execute`.

## Templates

### Call a predefined procedure

```sql
-- verified: 9.5.1 (live, 2026-10-06)
SELECT view_name, depth FROM USED_BY()
 WHERE input_view_database_name = 'sales_analytics'
   AND input_view_name = 'customer';
```

**Input parameters go in the `WHERE` clause, under the procedure's own parameter names** —
`input_…` for many catalog procedures (`USED_BY`, `GET_ELEMENTS`), plain names for many others
(`PING_DATA_SOURCE`: `database_name`, `data_source_type`, `data_source_name`;
`DROP_REMOTE_TABLE`: `base_view_database_name`, `base_view_name`); `DESC PROCEDURE <name>`
lists them. They are parameters, not filters: the server passes them into the procedure
instead of filtering its output, and a procedure that requires one refuses the call without it —
`No search methods ready to be run. The following fields are obligatory: input_view_database_name, input_view_name`.
That message is also the cheapest way to learn which parameters are mandatory.

The result schema holds **both** the input and the output parameters, so `SELECT *` shows
the input columns echoed back. Name the columns you want, as above.

`CALL` is the other form and takes the values **positionally**, `null` for every optional
one you skip: `CALL USED_BY('sales_analytics', 'customer', null)`. Prefer the `SELECT`
form — it names its parameters and it lets you join the result with a view.

**Some predefined procedures change state, and they are called exactly like a read.**
`GET_STATS_FOR_FIELDS` with `input_save = true` overwrites a view's statistics,
`CLEAN_CACHE_DATABASE` deletes cached rows, `DROP_REMOTE_TABLE` drops a table in the source,
`LOGCONTROLLER` changes logging for the whole server — the list the tool checks, with what each
one changes, is `references/predefined.md`, "A call that looks like a read and is not". It is
not every writer: read the page of any other procedure before calling it. Show the human the
call and wait for the yes, as for a `DROP` (`/denodo:vql`); "run the stats procedure" is the
task, not that yes. The tool flags each one `destructive: "procedure"`. Two exceptions belong
to other skills, each on objects you created in this session: a new remote table
(`/denodo:materialize`) and clearing the cache of your own view (`/denodo:cache`).

### VQL procedure

```sql
-- verified: 9.5.1 (live, 2026-10-06)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VQL PROCEDURE order_size_band
    FOLDER = '/02 - integration'
    (amount IN DECIMAL, band OUT VARCHAR)
AS (
    result VARCHAR;
)
BEGIN
    IF amount >= 10000 THEN
        result := 'large';
    ELSE
        result := 'standard';
    END IF;
    RETURN ROW (band) VALUES (result);
END;
```

- **`FOLDER =` comes before the parameter list**, not after it — the one place where this
  object differs from every other `CREATE` in the set. The other way round is
  `Syntax error: Exception parsing query near 'FOLDER'`. (`DESC VQL PROCEDURE` prints it
  this way too, which is how you confirm it on any server.)
- `AS ( … )` declares the local variables, **each closed by its own `;`**. The block is
  required even when you declare nothing useful — an empty `AS ( )` is a syntax error.
- `BEGIN … END` is the body; `:=` assigns, `RETURN ROW (out1, out2) VALUES (v1, v2)`
  returns a row through the `OUT` parameters. A procedure with no `RETURN ROW` is legal: it
  runs, does its work and returns zero rows.
- An `IN` parameter is **mandatory** unless declared `NULLABLE`. Calling without it is
  `View without search methods: The following obligatory fields cannot be removed: amount`;
  with `amount IN DECIMAL NULLABLE` the same call runs and the variable is `null`.
- Invoke it exactly like a predefined one: `SELECT band FROM order_size_band() WHERE
  amount = 12000`, or from inside a view — `CREATE OR REPLACE VIEW v … AS SELECT band FROM
  order_size_band() WHERE amount = 25000` (the view is `/denodo:views`, the procedure is
  here).
- **VQL procedures need the Denodo Enterprise or Enterprise Plus bundle.** On a server
  without it the statement does not run; there is nothing about this in the VQL itself, so
  if `CREATE VQL PROCEDURE` is refused on a server where the syntax is right, check the
  bundle before rewriting the procedure.

### Java procedure from a JAR

```sql
-- unverified: 9.5 documentation only
CREATE OR REPLACE PROCEDURE order_enrichment
    CLASSNAME 'com.acme.denodo.OrderEnrichment'
    JARS 'acme-denodo-extensions'
    FOLDER = '/02 - integration'
    DESCRIPTION = 'Enriches orders from the pricing service';
```

The JAR is imported into the server first (Administration Guide, *Importing Extensions*);
`JARS` then names it, and the class must be inside it — otherwise the statement fails with
`error storing procedure: Unable to find class 'com.acme.denodo.OrderEnrichment'`. The
`CLASSPATH` clause is the alternative and the documentation recommends against it: it ties
the procedure to a path on one machine. Here `FOLDER =` sits with the other clauses, after
`CLASSNAME` — unlike the VQL form above.

## What you need before filling the template

| Slot | Where it comes from |
|---|---|
| Which kind of procedure | the request: calling something → predefined; "loop / branch / for each" → VQL; "we have a JAR" → Java |
| Which predefined procedure | the server, not memory: `LIST PROCEDURES` and `references/predefined.md` for the families |
| Its parameters and their direction | `DESC PROCEDURE <name>` → `name, type, direction`; or `SELECT … FROM GET_PROCEDURE_COLUMNS() WHERE input_procedure_name = '<NAME>'`, which adds `column_is_nullable` |
| Parameters and types of your own procedure | the human — what goes in, what comes back; types are the VQL types (`references/vql-procedures.md`) |
| Folder | the layer the procedure serves, `/02 - integration` for logic over integrated views; project conventions win (`.denodo/conventions.md`) |
| Database | the procedure lives in one — `CONNECT DATABASE` at the top of the file, or `--database` on the command |
| Java class name and JAR | the human, plus the server: the JAR has to be imported before the statement is applied |

Do not ask for a folder tree, cache or statistics settings — a procedure has none of them.

## Reference

- `references/predefined.md` — what the predefined procedures cover, family by family, the
  ones that change state, and the rules that apply to calling any of them.
- `references/vql-procedures.md` — the full procedural language: types, `IN/OUT/IN OUT`,
  `NULLABLE`, `IF`/`CASE`/`LOOP`/`WHILE`/`FOR`, cursors, exceptions, `EXECUTE` of DDL,
  transactions, comments, debug logging.
- `references/java-procedures.md` — `CREATE PROCEDURE`, `ALTER PROCEDURE`, the JAR, and
  what it costs compared with the VQL form.

## Verify

| Question | Read-back |
|---|---|
| Does the procedure exist, and where | `SELECT name, subtype, folder FROM GET_ELEMENTS() WHERE input_database_name = '<db>' AND type = 'storedProcedure'` — `subtype` is `user defined - vql` for the VQL form |
| What does it take and return | `vql desc --env dev --database <db> <name> --type procedure` → `name, type, direction` — *verified: 9.5.1 (live, 2026-10-05)* |
| What is its definition | `vql desc --env dev --database <db> <name> --type procedure --vql` → the `CREATE VQL PROCEDURE` the server itself would write |
| Does it work | call it: `SELECT <out column> FROM <name>() WHERE <input> = <value>` — the only check that proves the body, not the parse |
| Which predefined procedure is available here | `LIST PROCEDURES` |
| Which views stand on this procedure | `SELECT dependency_name, dependency_type, depth FROM VIEW_DEPENDENCIES() WHERE input_view_database_name = '<db>' AND input_view_name = '<view>'` — asked per view; a procedure shows up as `dependency_type = 'Storedprocedure Vql'` |

**Creating the procedure is not the same as it working.** The body binds when it runs, not
when it is stored: a procedure whose `EXECUTE` names a view that does not exist is stored
without a complaint and fails on the first call — with `Error executing query. Total time
…` and nothing about the missing view. Always end with a call.

## Common mistakes

| You wrote | Server says | Fix |
|---|---|---|
| `CREATE OR REPLACE PROCEDURE p (a IN INT, b OUT VARCHAR) AS ( … ) BEGIN … END` | `Syntax error … near '('` | `CREATE OR REPLACE VQL PROCEDURE` — without `VQL` it is the Java statement |
| `CREATE OR REPLACE VQL PROCEDURE p (a IN INT) FOLDER = '/x' AS …` | `Syntax error … near 'FOLDER'` | `FOLDER =` goes before the parameter list |
| `CREATE OR REPLACE VQL PROCEDURE p (…) AS ( ) BEGIN … END` | `Syntax error … near ')'` | declare at least one local variable (a placeholder such as `tmp VARCHAR;`); the `AS ( … )` block itself is required |
| `SELECT * FROM USED_BY()` | `No search methods ready to be run. The following fields are obligatory: …` | pass the mandatory `input_…` parameters in `WHERE` |
| `SELECT status FROM PING_DATA_SOURCE() WHERE input_database_name = 'db' …` | `Error in select view conditions: Field not found 'input_database_name' …` | its parameters have no prefix: `WHERE database_name = 'db' AND data_source_type = 'JDBC' AND data_source_name = 'ds'`. A bare `Error executing query. Total time …` from it means no such database or data source |
| `SELECT band FROM order_size_band()` | `View without search methods: The following obligatory fields cannot be removed: amount` | pass the parameter, or declare it `NULLABLE` |
| `CALL no_such_procedure()` | `error invoking stored procedure: 'no_such_procedure' not found` | `LIST PROCEDURES`, and check you are in the right database |
| `DROP PROCEDURE p` where there is none | `error removing stored procedure: The database does not contains the specified stored procedure` | `DROP PROCEDURE IF EXISTS p` |
| `DROP PROCEDURE p` that a view calls | `error removing stored procedure: There are some elements that depend on this one` | show the human what depends on it, then `DROP PROCEDURE p CASCADE` — it drops those views too |
| `CREATE OR REPLACE PROCEDURE p CLASSNAME 'com.acme.X'` with no JAR imported | `error storing procedure: Unable to find class 'com.acme.X'` | import the JAR into the server first, then name it in `JARS` |

Dropping is the human's call — `/denodo:vql`. A procedure something else uses refuses to go
(`error removing stored procedure: There are some elements that depend on this one`), and
`DROP PROCEDURE … CASCADE` takes those views with it. `USED_BY()` will not tell you which
ones — it takes a view and answers `This view does not exist` for a procedure. The question
is asked from the other side: `VIEW_DEPENDENCIES()` on a view lists what it stands on, and a
procedure appears there as `dependency_name` with `dependency_type = 'Storedprocedure Vql'`.
