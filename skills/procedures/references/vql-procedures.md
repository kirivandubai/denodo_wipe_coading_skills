# VQL procedures

Denodo's procedural language: variables, branches, loops, cursors, exceptions and DDL, with
no Java and no JAR. **Requires the Denodo Enterprise or Enterprise Plus bundle** (VQL Guide,
*Developing VQL Stored Procedures*) — the syntax is not the thing that fails on a server
without it.

Everything marked `verified` below was created and called on a 9.5.1 stand on 2026-09-12.

## The statement

```sql
-- verified: 9.5.1 (стенд, 2026-09-12)
CREATE [OR REPLACE] VQL PROCEDURE <name>
    [ FOLDER = '<path>' ]
    ( <param> [IN|OUT|IN OUT] <type> [NULLABLE] [, <param> …] )
AS (
    [ <local variable> <type>; ]*
    [ CURSOR <cursor name> IS '<SELECT statement>'; ]*
    [ <exception name> EXCEPTION; ]*
)
BEGIN
    <commands>
[EXCEPTION
    WHEN <exception> THEN <commands>
    [WHEN OTHERS [( <var> )] THEN <commands>] ]
END;
```

`FOLDER =` **before** the parameter list — after it the parser stops at `FOLDER`. This is
the order the server itself writes in `DESC VQL PROCEDURE`, and it is the opposite of the
Java form, where `FOLDER` sits with the other clauses.

The procedure has no `DESCRIPTION` clause. It belongs to the database it was created in;
move it between folders with `ALTER FOLDER '/<target>' MOVE PROCEDURE <name>`
(*verified: 9.5.1 (стенд, 2026-09-12)*), and drop it with `DROP PROCEDURE [IF EXISTS] <name>
[CASCADE]`.

## Parameters and types

| Direction | Meaning |
|---|---|
| `IN` | passed in. **Mandatory unless `NULLABLE`** — without a value the call fails with `View without search methods: The following obligatory fields cannot be removed: <param>` |
| `OUT` | returned through `RETURN ROW` |
| `IN OUT` | both (*unverified: только по документации 9.5*) |

Types: `BIGINT`, `DECIMAL`, `DOUBLE PRECISION`, `FLOAT`, `INT`, `INTEGER`, `NUMBER`,
`NUMERIC`, `REAL`, `SMALLINT`; `CHAR`, `NCHAR`, `NVARCHAR`, `VARCHAR`; `DATE`, `TIMESTAMP`,
`TIMESTAMP WITH TIMEZONE`, `TIMESTAMP WITH LOCAL TIMEZONE`, `INTERVAL YEAR TO MONTH`,
`INTERVAL DAY TO SECOND`; `BOOL`, `ROWTYPE`, `EXCEPTION`.

Local variables are declared in `AS ( … )`, **each closed by its own `;`**. An empty
`AS ( )` is a syntax error near `)`; a procedure that needs no variables still needs the
block with something in it.

## Commands

| Command | Form |
|---|---|
| Assignment | `var := <literal, variable or expression>;` — also `var := SQL%ROWCOUNT;` after an `INSERT`/`UPDATE`/`DELETE` (*unverified*) |
| Branch | `IF <condition> THEN … [ELSE …] END IF;` |
| Branch | `CASE [identifier] WHEN <condition> THEN … [ELSE …] END CASE;` |
| Loop | `LOOP … [EXIT WHEN <condition>] END LOOP;` |
| Loop | `WHILE <condition> LOOP … END LOOP;` |
| Loop | `FOR <var> IN <low> .. <high> LOOP … END LOOP;` |
| Write | `INSERT INTO <view> (cols) VALUES (…);`, `UPDATE <view> SET (cols) = (values) WHERE …;`, `DELETE FROM <view> WHERE …;` (*unverified*) |
| Return | `RETURN ROW (out1, out2) VALUES (v1, v2);` |
| DDL | `EXECUTE '<statement>' [PARAMETERS ( p ) VALUES ( v )] [ON DATABASE <name>];` |

Three things about loops that the documentation does not say and Oracle habits get wrong —
all three *verified: 9.5.1 (стенд, 2026-09-12)*:

- **`FOR` bounds must be literals.** `FOR i IN 1 .. upto LOOP` with a parameter, or even a
  local variable, is `Syntax error: Exception parsing query near 'upto'`.
- **The `FOR` counter is not readable in the body.** The loop runs the right number of
  times, but the counter variable stays null: `acc := acc + i` leaves `acc` null, and
  returning the counter fails the call. Count with your own variable, or use `LOOP` /
  `WHILE`.
- **`EXIT WHEN` goes last in a `LOOP` body.** Put anything after it and the parser stops
  there: `Syntax error … near 'RETURN'`.

`RETURN ROW` may be called repeatedly — that is how a procedure returns many rows (see the
cursor below). A procedure without `RETURN ROW` is legal and returns zero rows.

## EXECUTE: DDL from inside a procedure

```sql
-- verified: 9.5.1 (стенд, 2026-09-12)
CREATE OR REPLACE VQL PROCEDURE p_params (n IN INTEGER, made OUT VARCHAR)
AS (
    tmp VARCHAR;
)
BEGIN
    EXECUTE 'CREATE OR REPLACE VIEW v_param_made AS SELECT :p AS a FROM DUAL()'
        PARAMETERS ( p ) VALUES ( n );
    RETURN ROW (made) VALUES ('v_param_made');
END;
```

The statement is a **literal**, so quotes inside it are doubled. `PARAMETERS ( … ) VALUES
( … )` substitutes `:name` placeholders — the way to build a statement out of the
procedure's inputs without concatenating strings. `ON DATABASE <name>` runs it elsewhere
(the name may be a literal or a variable).

**The body binds late.** A procedure whose `EXECUTE` names a view that does not exist is
stored happily and fails only when called — and the failure the client sees is the bare
`Error executing query. Total time …`. Which is what the next section is for.

## Cursors: walking rows

```sql
-- verified: 9.5.1 (стенд, 2026-09-12)
CREATE OR REPLACE VQL PROCEDURE p_cursor (n OUT INTEGER, label OUT VARCHAR)
AS (
    CURSOR rows_of_v IS 'SELECT n, label FROM v_rows';
    row_of rows_of_v%ROWTYPE;
)
BEGIN
    OPEN rows_of_v;
    LOOP
        FETCH rows_of_v INTO row_of;
        RETURN ROW (n, label) VALUES (row_of.n, row_of.label);
        EXIT WHEN rows_of_v%NOTFOUND;
    END LOOP;
    CLOSE rows_of_v;
END;
```

- The query is a literal and **only `SELECT` is allowed** — no DDL, no `DESC`.
- A parameterised cursor takes `:name` in the query and values at `OPEN`:
  `CURSOR c IS 'SELECT … WHERE x = :p'` … `OPEN c PARAMETERS (p) VALUES ('v')`
  (*unverified: только по документации 9.5*).
- `<cursor>%ROWTYPE` declares a row variable; fields are read as `row_of.<column>`.
- `%NOTFOUND` is true once the cursor is exhausted, which is what ends the loop — and
  `EXIT WHEN` has to be the last command in it, so the row fetched last is returned before
  the test.
- `CLOSE` when done.

## Exceptions

```sql
-- verified: 9.5.1 (стенд, 2026-09-12)
CREATE OR REPLACE VQL PROCEDURE p_others (msg OUT VARCHAR)
AS (
    tmp VARCHAR;
)
BEGIN
    EXECUTE 'SELECT * FROM view_that_is_not_there';
    RETURN ROW (msg) VALUES ('no error');

EXCEPTION
    WHEN OTHERS (e) THEN
        tmp := e.error_message;
        RETURN ROW (msg) VALUES (tmp);
END;
```

Calling this returns `View 'view_that_is_not_there' not found` — **the message the client
never sees**. When a procedure fails with the opaque `Error executing query`, wrapping the
body in `WHEN OTHERS (e)` and returning `e.error_message` is the fastest way to find out
what actually broke.

Own exceptions: declare `<name> EXCEPTION;` in `AS ( … )`, `RAISE <name>;` in the body,
handle it in `WHEN <name> THEN` (*verified: 9.5.1 (стенд, 2026-09-12)* — both the raised
and the unraised path). `THROW <name>;` inside a handler rethrows it
(*unverified: только по документации 9.5*).

## Transactions

`BEGIN_TRANSACTION;`, `COMMIT;`, `ROLLBACK;` inside the body
(*unverified: только по документации 9.5*). The documented pattern is a transaction around
the writes with `EXCEPTION WHEN OTHERS THEN ROLLBACK;`.

## Comments and debugging

Inside a procedure, `--`, `#` and `//` start a line comment and `/** … **/` a block one —
but only inside the declaration block or the body, never before the parameter list. They go
to the server with the rest of the body and **the server does not keep them**:
`DESC VQL PROCEDURE` prints the body normalised, without comments
(*verified: 9.5.1 (стенд, 2026-09-12)*). Comment for the human reading the `.vql` file in
the repository, and do not expect the comment back from the server.

Step-by-step logging, for a procedure that misbehaves in the middle:

```sql
-- unverified: только по документации 9.5
CALL LOGCONTROLLER('com.denodo.vdb.engine.storedprocedure.CommandExecutorVisitorImpl', 'DEBUG');
```

## Documentation

`vdp/developer/developing_extensions/developing_stored_procedures/developing_vql_stored_procedures`
under `https://community.denodo.com/docs/html/accessible/9.5/`.
