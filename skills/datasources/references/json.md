# JSON data sources and wrappers — full syntax

Source of the grammar: VQL Guide 9.5, *JSON Sources* and *JSON Wrappers*. Facts marked
`verified:` were run on a 9.5.1 server.

## CREATE DATASOURCE JSON

```sql
CREATE [ OR REPLACE ] DATASOURCE JSON <name>
    [ ID = <literal> ]
    [ FOLDER = <literal> ]
    {   ROUTE <route> [ CHARSET = <literal> ] [ FILTER ( <filter> [, … ] ) ]
      | OPENAPI3 (
            DOCUMENT_ACCESS_CONFIGURATION ( <openapi route> )
            DEFAULT_CONFIGURATION_FOR_BASE_VIEWS ( ROUTE <route> [ CHARSET = <literal> ] [ FILTER ( … ) ] )
        )
    }
    [ TRANSFER_RATE_FACTOR = <double> ]
    [ DESCRIPTION = <literal> ]
    [ NDJSON ]
```

- `ROUTE LOCAL 'LocalConnection' '<server-side path>' CHARSET = 'UTF-8'` is the file case.
  *verified: 9.5.1 (стенд, 2026-09-09)*
- `NDJSON` switches the parser to newline-delimited JSON (one document per line).
- `FILENAMEPATTERN` is **not** available for JSON — that clause is DF-only. A directory of
  JSON files needs one source per file, or a DF-style ingestion.
- The other route types (HTTP, FTP, HDFS, S3, ABFS) share the grammar with DF —
  `references/df.md`.
- OpenAPI 3: Denodo reads the document and offers one base view per operation. The
  document route and the runtime route are configured separately.
  *unverified: только по документации 9.5*

`ALTER DATASOURCE JSON` takes `ROUTE`, `OPENAPI3`, `TRANSFER_RATE_FACTOR`, `DESCRIPTION`,
`NDJSON`.

## CREATE WRAPPER JSON

```sql
CREATE [ OR REPLACE ] WRAPPER JSON <name>
    [ FOLDER = <literal> ]
    DATASOURCENAME = <name>
    [ TUPLEROOT <JSON path:literal> ]
    [ ROUTE <route> [ CHARSET = <literal> ] [ FILTER ( … ) ] ]
    [ OUTPUTSCHEMA ( <field> [, <field> ]* ) ]
    [ SOURCECONFIGURATION ( DATAINORDERFIELDSLIST = { DEFAULT | ( <field> { ASC | DESC }, … ) } ) ]

<field> ::= <name> [ = <mapping:literal> ] [ : <type:literal> ] [ ( { OBL | OPT } ) ]
              [ ( DEFAULTVALUE <literal> ) ] [ EXTERN ] [ <inline constraint> ]*
          | <name> [ = <mapping> ] : ARRAY OF ( <register field> )
          | <register field>

<register field> ::= <name> [ = <mapping> ] : REGISTER OF ( <field> [, <field> ]* )
```

### The shape that works

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
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
| Is the outer `REGISTER OF` wrapper required? | In practice yes. A flat field list parses and creates, and then the base view returns **the wrong number of rows** — nested arrays multiply them, and with absolute mappings one row comes back all-`NULL`. *verified: 9.5.1 (стенд, 2026-09-09)* |
| What is `/JSONFile/JSONArray`? | Denodo's own path for "the array at the top level of the document". A document whose root is an object uses `/JSONFile`, and the mappings lose the `JSONArray` segment |
| Absolute or relative mappings? | Top-level fields carry the full path (`JSONFile.JSONArray.x`); fields **inside** a nested `REGISTER OF` or `ARRAY OF` are relative to it (`country`) |
| Does the name inside `ARRAY OF ( … )` matter? | No. `ARRAY OF ( whatever = 'whatever' : REGISTER OF ( … ) )` works the same. *verified: 9.5.1 (стенд, 2026-09-09)* |
| Can `OUTPUTSCHEMA` be omitted? | It creates, and then `SELECT` fails with `[JSON WRAPPER] [PROCESSING]`. The server does not introspect the document. *verified: 9.5.1 (стенд, 2026-09-09)* |
| Types | Java class names, as in JDBC wrappers: `java.lang.String`, `java.lang.Integer`, `java.lang.Double`, `java.lang.Boolean` |

### Wrapper-level route

A JSON **data source** can hold a base URI and each wrapper its own relative path:
`ROUTE HTTP 'http.CommonsHttpClientConnection' GET '/books'` on the wrapper is
concatenated to the source's URI. That is how one REST API becomes many base views.
*unverified: только по документации 9.5*

```sql
ROUTE HTTP 'http.CommonsHttpClientConnection' { GET | POST } <uri>
    [ POSTBODY <body> [ MIME <type> ] ]
    [ HEADERS ( <name> = <value> [, … ] ) ]
    [ PAGINATION_SETTINGS ( <settings> ) ]
    [ CHARSET = <literal> ]
```

Pagination comes in four shapes, all inside `PAGINATION_SETTINGS`:

| Shape | Keys |
|---|---|
| page number | `PAGE_SIZE_PARAMETER`, `PAGE_SIZE`, `PAGE_NUMBER_PARAMETER`, `FIRST_PAGE_INDEX`, `OFFSET_FOR_NEXT_REQUESTS`, `MAX_NUMBER_OF_REQUESTS` |
| token in a parameter | `PAGE_SIZE_PARAMETER`, `PAGE_SIZE`, `NEXT_TOKEN_PARAMETER`, `NEXT_TOKEN_PATH`, `[ MAX_NUMBER_OF_REQUESTS ]` |
| token in the body | `PAGE_SIZE_PARAMETER`, `PAGE_SIZE`, `NEXT_TOKEN_PATH`, `[ MAX_NUMBER_OF_REQUESTS ]` |
| next-page URL in a header | `HEADER_WITH_NEXT_PAGE_URL`, `[ MAX_NUMBER_OF_REQUESTS ]` |

Route filters on a wrapper: `DECRYPTAES256 PASSWORD = <literal> [ ENCRYPTED ]`,
`DECRYPT`, `UNZIP`, `GUNZIP`, `CUSTOM [ JARS … ] CLASSNAME = <literal> <param> = <literal>
[ ENCRYPTED ] [ HIDDEN ]`.

## Compound columns need named types

`CREATE TABLE` accepts a type *identifier* for a field, so registers and arrays must exist
as catalog objects first:

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
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
  `Field not found 'shipping.country' in view 'shipping'`. *verified: 9.5.1 (стенд, 2026-09-09)*
- An array is expanded with `FLATTEN` in a derived view: `SELECT … FROM FLATTEN
  bv_oms_orders AS v (v.lines)` — that is `/denodo:views` territory, but the column names
  it produces are worth knowing here, because they decide what your derived view can
  select. The array column disappears and **its register's subfields appear unprefixed**,
  next to the top-level columns; a register column that is not flattened stays as one
  register value:

  ```
  SELECT * FROM FLATTEN bv_oms_orders AS v (v.lines)
  → order_id, customer_id, order_dt, status, total_amount, shipping,
    line_no, sku, qty, price          -- 3 orders, 4 lines → 4 rows
  ```
  *verified: 9.5.1 (стенд, 2026-09-09)*. Names collide if a subfield shares a name with a
  top-level column — alias them in the projection.
- Base views over JSON keep the document's own types; converting `order_dt` from an ISO
  string to a timestamp belongs in the derived layer, not in the base view.
