# JSON data sources and wrappers — a local file

A JSON file on the Denodo server's own filesystem. Source of the grammar: VQL Guide 9.5,
*JSON Sources* and *JSON Wrappers*. Facts marked `verified:` were run on a 9.5.1 server.

A JSON document behind a URL — a REST API, an OpenAPI document, anything with an HTTP route,
authentication or pagination — is created in Design Studio, not from this grammar
(`SKILL.md`, **What you build, and what goes to Design Studio**).

## CREATE DATASOURCE JSON

```sql
CREATE [ OR REPLACE ] DATASOURCE JSON <name>
    [ FOLDER = <literal> ]
    ROUTE LOCAL 'LocalConnection' <server-side path> [ CHARSET = <literal> ]
    [ DESCRIPTION = <literal> ]
    [ NDJSON ]
```

- `ROUTE LOCAL 'LocalConnection' '<server-side path>' CHARSET = 'UTF-8'` is the file case.
  *verified: 9.5.1 (live, 2026-09-09)*
- `NDJSON` switches the parser to newline-delimited JSON (one document per line).
  *unverified: 9.5 documentation only*
- `FILENAMEPATTERN` is **not** available for JSON — that clause is DF-only. A route to a
  directory reads every file in it, all assumed to share the first file's structure
  (*unverified: 9.5 documentation only*), so the directory must hold only those files.

`ALTER DATASOURCE JSON` takes `ROUTE`, `DESCRIPTION` and `NDJSON`; it is an `ALTER`, so the
human confirms it (`/denodo:vql`). Re-applying `CREATE OR REPLACE` does not need that.

## CREATE WRAPPER JSON

```sql
CREATE [ OR REPLACE ] WRAPPER JSON <name>
    [ FOLDER = <literal> ]
    DATASOURCENAME = <name>
    [ TUPLEROOT <JSON path:literal> ]
    [ OUTPUTSCHEMA ( <field> [, <field> ]* ) ]
    [ SOURCECONFIGURATION ( DATAINORDERFIELDSLIST = { DEFAULT | ( <field> { ASC | DESC }, … ) } ) ]

<field> ::= <name> [ = <mapping:literal> ] [ : <type:literal> ] [ ( { OBL | OPT } ) ]
              [ ( DEFAULTVALUE <literal> ) ] [ <inline constraint> ]*
          | <name> [ = <mapping> ] : ARRAY OF ( <register field> )
          | <register field>

<register field> ::= <name> [ = <mapping> ] : REGISTER OF ( <field> [, <field> ]* )
```

### The shape that works

```sql
-- verified: 9.5.1 (live, 2026-10-07)
TUPLEROOT '/JSONFile/JSONArray'
OUTPUTSCHEMA (jsonfile = 'JSONFile' : REGISTER OF (
    order_id = 'JSONFile.JSONArray.order_id' : 'java.lang.String',
    shipping = 'JSONFile.JSONArray.shipping' : REGISTER OF (
        country = 'country' : 'java.lang.String'
    ),
    lines = 'JSONFile.JSONArray.lines' : ARRAY OF (
        line = 'line' : REGISTER OF ( sku = 'sku' : 'java.lang.String' )
    )
)
);
```

| Question | Answer |
|---|---|
| Is the outer `REGISTER OF` wrapper required? | In practice yes. A flat field list parses and creates, and then the base view returns **the wrong number of rows** — nested arrays multiply them, and with absolute mappings one row comes back all-`NULL`. *verified: 9.5.1 (live, 2026-09-09)* |
| What is `/JSONFile/JSONArray`? | Denodo's own path for "the array at the top level of the document". A document whose root is an object uses `/JSONFile`, and the mappings lose the `JSONArray` segment |
| Absolute or relative mappings? | Top-level fields carry the full path (`JSONFile.JSONArray.x`); fields **inside** a nested `REGISTER OF` or `ARRAY OF` are relative to it (`country`) |
| Does the name inside `ARRAY OF ( … )` matter? | No. `ARRAY OF ( whatever = 'whatever' : REGISTER OF ( … ) )` works the same. *verified: 9.5.1 (live, 2026-09-09)* |
| Can `OUTPUTSCHEMA` be omitted? | It creates, and then `SELECT` fails with `[JSON WRAPPER] [PROCESSING]`. The server does not introspect the document. *verified: 9.5.1 (live, 2026-09-09)* |
| Types | Java class names, as in JDBC wrappers: `java.lang.String`, `java.lang.Integer`, `java.lang.Double`, `java.lang.Boolean` |

## Compound columns need named types

`CREATE TABLE` accepts a type *identifier* for a field, so registers and arrays must exist
as catalog objects first:

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CREATE OR REPLACE TYPE oms_shipping AS REGISTER OF (country:text, city:text, zip:text);
CREATE OR REPLACE TYPE oms_order_line AS REGISTER OF (line_no:int, sku:text, qty:int, price:double);
CREATE OR REPLACE TYPE oms_order_line_array AS ARRAY OF oms_order_line;
```

- Register first, then the array of that register — an array of an inline structure does
  not parse.
- The type is a database-level object: it shows up in `LIST TYPES`, it is dropped with
  `DROP TYPE`, and dropping it while a view uses it needs `CASCADE` (the human's call).
- Keep the type declarations in the same file as the base view; they belong to it.

## Reading the data

- A register field is read with parentheses: `SELECT (shipping).country FROM bv_oms_orders`.
  Without them the parser reads `shipping.country` as *view.column* and answers
  `Field not found 'shipping.country' in view 'shipping'`. *verified: 9.5.1 (live, 2026-09-09)*
- An array is expanded with `FLATTEN` in a derived view: `SELECT … FROM FLATTEN
  bv_oms_orders AS v (v.lines)` — that is `/denodo:views` territory (its
  `references/arrays.md`), but the column names it produces are worth knowing here, because
  they decide what your derived view can select. The array column disappears and **its
  register's subfields appear unprefixed**, next to the top-level columns; a register column
  that is not flattened stays as one register value:

  ```
  SELECT * FROM FLATTEN bv_oms_orders AS v (v.lines)
  → order_id, customer_id, order_dt, status, total_amount, shipping,
    line_no, sku, qty, price          -- 3 orders, 4 lines → 4 rows
  ```
  *verified: 9.5.1 (live, 2026-09-09)*. A subfield that shares a name with a top-level
  column is renamed by the server, `<array>_<subfield>` — a line's `status` comes out as
  `lines_status` — and an order whose array is empty or missing comes out as one row with
  the subfields `NULL` — *verified: 9.5.1 (live, 2026-09-30)*.
- **Filters need the base view's `CONSTRAINTS`.** A JSON base view created without
  `ADD <field> NOS ZERO ()` for every column and every register subfield ignores every
  `WHERE` on it — the server passes the condition to the JSON wrapper, which drops it.
  `SKILL.md`, **JSON file**, has the block; `SELECT COUNT(*) … WHERE <key> = '<one value>'`
  returning more than one row is the symptom — *verified: 9.5.1 (live, 2026-09-30)*.
  Re-applying the base view with the block fixes every view above it. A base view that is not
  yours is its owner's to fix; `/denodo:views` (`references/arrays.md`) has what to do in the
  meantime.
- Base views over JSON keep the document's own types; converting `order_dt` from an ISO
  string to a timestamp belongs in the derived layer, not in the base view.
