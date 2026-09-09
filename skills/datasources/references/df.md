# DF data sources and wrappers — full syntax

Delimited text: CSV, TSV, pipe-separated, fixed-width, and anything a Java regular
expression can parse into groups. Source of the grammar: VQL Guide 9.5, *DF Data Sources*
and *DF Wrappers*. Facts marked `verified:` were run on a 9.5.1 server.

## CREATE DATASOURCE DF

```sql
CREATE [ OR REPLACE ] DATASOURCE DF <name>
    [ FOLDER = <literal> ]
    [ IGNOREMATCHINGERRORS = { TRUE | FALSE } ]
    ROUTE <route> [ CHARSET = <literal> ] [ FILTER ( <filter> [, <filter> ]* ) ]
    {   COLUMNDELIMITER = <literal>
      | TUPLEPATTERN = <literal> [ HEADERPATTERN = <literal> ]
      | COLUMNWIDTHS = '<int>[,<int>]' [ PADCHARACTER = <literal> ]
            [ REPLACECHARACTER = <literal> ] [ ALIGNMENT = { LEFT | RIGHT } ]
    }
    [ ENDOFLINEDELIMITER = <literal> ]
    [ BEGINDELIMITER = { <literal> | VAR <variable> } [ ISDATA ] ]
    [ ENDDELIMITER = <literal> [ ISDATA ] ]
    [ HEADER = <boolean> ]
    [ MULTI_CHARACTER_DELIMITER = <boolean> ]
    [ TRANSFER_RATE_FACTOR = <double> ]
    [ DESCRIPTION = <literal> ]
```

`ALTER DATASOURCE DF <name>` takes the same clauses without `FOLDER`; it is a change to an
existing object, so `/denodo:vql` applies — prefer `CREATE OR REPLACE`.

| Clause | Notes |
|---|---|
| `COLUMNDELIMITER` | `\t` for tab. More than one character means *any of them* separates values (`,\|` = comma or pipe) unless `MULTI_CHARACTER_DELIMITER = true`, which makes the whole string one delimiter |
| `ENDOFLINEDELIMITER` | default `\n`; set it for files with `\r\n` that must not be trimmed |
| Quoted values | handled without any clause: a file whose header and values are wrapped in `"` comes back unquoted. *verified: 9.5.1 (стенд, 2026-09-09)* |
| `HEADER` | `TRUE` = first tuple of the data area holds field names. It does **not** make the server introspect the file — you still write `OUTPUTSCHEMA` yourself. *verified: 9.5.1 (стенд, 2026-09-09)* |
| `IGNOREMATCHINGERRORS` | default `TRUE`: rows whose column count does not match the wrapper's schema are skipped **silently** — that is the whole mechanism behind "the base view returns zero rows". `FALSE` makes the same case fail loudly with `[DF ROUTE] [PARSE_ERROR] Invalid line found at data file. Different number of columns`. Put `FALSE` in every source you onboard. *verified: 9.5.1 (стенд, 2026-09-09)* |
| `TUPLEPATTERN` | Java regex matching the **whole** line; capturing groups become the fields. `HEADERPATTERN` only when the header parses differently |
| `COLUMNWIDTHS` | fixed-width files, sizes in bytes; `PADCHARACTER`/`REPLACECHARACTER` escape as Java strings (`á`) |
| `BEGINDELIMITER` / `ENDDELIMITER` | Java regex bounding the data area; `ISDATA` keeps the matched text as data |
| `TRANSFER_RATE_FACTOR` | relative link speed, `1` = 100 Mbps LAN; affects planning only |
| `DESCRIPTION` | last clause |

### Routes

```sql
LOCAL { 'LocalConnection' | 'VariableConnection' } <path> [ FILENAMEPATTERN = <literal> ] [ CHARSET = <literal> ]
HTTP 'http.CommonsHttpClientConnection' { GET | POST } <uri>
     [ POSTBODY <body> [ MIME <type> ] ] [ HEADERS ( <name> = <value>, … ) ]
     [ CHECKCERTIFICATES ] [ <authentication> ] [ <proxy> ]
     [ HTTP_ERROR_CODES_TO_IGNORE ( <int>, … ) ]
FTP 'ftp.FtpClientConnectionAdapter' <uri> <login>
     { <password> [ ENCRYPTED ] | SSH_KEY = <base64> [ ENCRYPTED ] [ SSH_KEY_PASSWORD = <literal> [ ENCRYPTED ] ] }
     [ FILENAMEPATTERN = <literal> ] [ PASSIVE = <boolean> ] [ EXPLICIT = <boolean> ]
HDFS 'hdfs.HdfsConnection' <uri> [ FILENAMEPATTERN = <literal> ] [ <hdfs auth> ]
     [ HADOOP_CUSTOM_PROPERTIES ( <literal> = <literal>, … ) ]
S3   'hdfs.S3Connection'   <uri> [ FILENAMEPATTERN = <literal> ] [ <s3 auth> ]
ABFS 'hdfs.AbfsConnection' <uri> [ FILENAMEPATTERN = <literal> ] [ <azure auth> ]
```

- `LOCAL` paths are **on the Denodo server**. A directory reads every file in it as one
  table; `FILENAMEPATTERN` is a regular expression over file names. All files must share a
  schema. *verified: 9.5.1 (стенд, 2026-09-09) — directory + `FILENAMEPATTERN = '.*\.csv'`*
- `VariableConnection` is for paths built from interpolation variables at query time
  (`@{var}`); the wrapper marks those fields `EXTERN`, and `URIPARAM` when the value is a
  URL query parameter. *unverified: только по документации 9.5*
- `FILENAMEPATTERN` is DF-only — JSON and XML sources do not take it.
- Any password in an FTP or cloud route follows the same rule as JDBC: `ENCRYPTED` only,
  never a literal in a file that goes into git (`references/jdbc.md`).

### Filters

`FILTER ( UNZIP )`, `GUNZIP`, `DECRYPT`, `DECRYPTAES256 PASSWORD = <literal> [ ENCRYPTED ]`,
or `CUSTOM [ JARS … ] CLASSNAME = <literal> <param> = <literal> [ ENCRYPTED ] [ HIDDEN ]`.
Applied to the byte stream before parsing, so a `.csv.gz` needs `FILTER ( GUNZIP )` and
nothing else changes. *unverified: только по документации 9.5*

## CREATE WRAPPER DF

```sql
CREATE [ OR REPLACE ] WRAPPER DF <name>
    [ FOLDER = <literal> ]
    DATASOURCENAME = <name>
    [ TUPLEROOT <literal> ]
    [ OUTPUTSCHEMA ( <field> [, <field> ]* ) ]
    [ SOURCECONFIGURATION ( DATAINORDERFIELDSLIST = { DEFAULT | ( <field> { ASC | DESC }, … ) } ) ]

<field> ::= <name> [ = <mapping:literal> ] [ ( { OBL | OPT } ) ]
            [ ( DEFAULTVALUE <literal> ) ] [ EXTERN ] [ <inline constraint> ]*
<inline constraint> ::= [ NOT ] NULL | [ NOT ] UPDATEABLE
                      | { SORTABLE [ ASC | DESC ] | NOT SORTABLE }
                      | NULLVALUE <literal> | URIPARAM
```

What the 9.5.1 parser actually accepts, against the grammar above:

| Form | Result |
|---|---|
| `cust_id = 'cust_id'` | works — the normal case |
| `email = 'email' NULLVALUE ''` | works; empty strings in that column become `NULL`. Needed **only for text columns**: without it an empty field stays `''`, while an empty numeric or date field is already `NULL` (51 empty descriptions stayed `''`, 45 empty prices came back `NULL`). *verified: 9.5.1 (стенд, 2026-09-09)* |
| `cust_id = 'cust_id' (OPT)` | works |
| `created_dt = 'created_dt' : 'java.util.Date'` | `Syntax error … near '''` — and so does every other spelling of a type (`: java.util.Date`, `: 'date'`, `:date`). **DF wrappers carry no types.** *verified: 9.5.1 (стенд, 2026-09-09)* |
| `OUTPUTSCHEMA` omitted | wrapper is created with an empty schema, a base view over it is created too, and `SELECT` fails with `[NO_CREATED_ACCESS] Unable to create xml raw access`. *verified: 9.5.1 (стенд, 2026-09-09)* |
| a subset of the file's columns | created without complaint, `SELECT` returns **zero rows** (every line fails the column-count check and `IGNOREMATCHINGERRORS` defaults to `TRUE`). *verified: 9.5.1 (стенд, 2026-09-09)* |
| the right number of columns, wrong names | works — **the mapping is positional**. `s_store_id = 's_store_id'` over a header of `"S_STORE_SK","S_STORE_ID",…` returns the *first* column's values under the name `s_store_id`. Names are labels; order is the contract. *verified: 9.5.1 (стенд, 2026-09-09)* |
| the right number of columns, right names, wrong order | rows arrive with values under the wrong names, silently — the same mechanism |

Registers and arrays are not supported in DF output schemas — the documentation says so
and the file format has nowhere to put them.

`ALTER WRAPPER DF <name> [ DATASOURCENAME = … ] [ OUTPUTSCHEMA ( … ) ] [ SOURCECONFIGURATION ( … ) ]`
exists; it is an `ALTER`, so it needs the human's yes. `CREATE OR REPLACE` does not.

## Reading a file as raw lines

`TUPLEPATTERN = '(.*)'` with `HEADER = FALSE` makes every line of the file one text value.
It is the only way to look at a server-side file from VQL, and it works for any text
format — CSV, JSON, XML:

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
CREATE OR REPLACE DATASOURCE DF ds_peek
    FOLDER = '/01 - connectivity'
    ROUTE LOCAL 'LocalConnection' '/data/exports/oms/orders.json'
    CHARSET = 'UTF-8' TUPLEPATTERN = '(.*)' HEADER = FALSE;
CREATE OR REPLACE WRAPPER DF wr_peek
    FOLDER = '/01 - connectivity' DATASOURCENAME = ds_peek
    OUTPUTSCHEMA ( line = 'line' );
```

The base view over it returns one row per line of the file. Give these objects the names
the real source will use and rewrite the same file once you know the schema — the reading
pass then leaves nothing behind. The trick also answers "is the file even there": a wrong
path fails with `[DF ROUTE] [PARSE_ERROR] … Error getting input Stream`.

## Typing a DF source

The wrapper hands text to the base view; the types are declared in `CREATE TABLE`
(`references/base-view.md`). Denodo parses the text into the declared type at query time:

- `created_dt:date` over `2021-04-12` → a real date. *verified: 9.5.1 (стенд, 2026-09-09)*
- a type that does not match returns `NULL` for the whole column, with no error at all —
  `cust_id:int` over `C-10472`. *verified: 9.5.1 (стенд, 2026-09-09)*

Non-ISO formats (`31/12/2026`) do not parse this way. Keep the column `text` in the base
view and convert it in a derived view with `TO_DATE` (`/denodo:views`), so the base view
stays a faithful mirror of the file.

## Optimizing

The Administration Guide's *Optimizing DF Data Sources* covers parallel processing of
large files and `TRANSFER_RATE_FACTOR`. Out of scope for v1: performance work starts after
the source reads correctly.
