# Remote tables, materialized tables, temporary tables

Grammar from the VQL Guide 9.5 ("Remote Tables", "CREATE_REMOTE_TABLE", "DROP_REMOTE_TABLE",
"Refreshing Views", "Materialized Tables", "Temporary Tables"); behaviour marked *measured* was
observed on 9.5.1 against SQL Server, 2026-10-02. Everything else is documentation only.

## The procedure

```
CREATE_REMOTE_TABLE(
      remote_table_name : text                 -- A–Z first, then letters, digits, _ ; not a reserved word
    , replace_remote_table_if_exist : boolean  -- default false: fail if the table exists
    , query : text                             -- runs in Denodo; quotes doubled
    , datasource_database_name : text          -- null: the current database
    , datasource_name : text                   -- a JDBC data source whose adapter the cache engine supports
    , datasource_catalog : text                -- mandatory; null where the database has no catalogs ('' in the documentation's own example)
    , datasource_schema : text                 -- mandatory; null where the database has no schemas
    , base_view_database_name : text           -- null: the current database
    , base_view_name : text                    -- null: the table's name
    , base_view_folder : text                  -- created if missing; null: the root
    , replace_base_view_if_exist : boolean     -- default false
    , options : text                           -- 'batch_insert_size=…, location=…, parquet_row_group_size=…'
    , create_table_template : text
    , create_table_template_parameters : text
)
```

Called as a read — `SELECT … FROM CREATE_REMOTE_TABLE() WHERE <param> = <value> AND …` —
*verified: 9.5.1 (live, 2026-10-05)*. Or positionally, with `CALL CREATE_REMOTE_TABLE('name',
false, 'SELECT …', …)` — *unverified: 9.5 documentation only*.

**Result** (*measured*): three rows, one per phase — `phase`, `status`, `error`,
`remote_table`, `base_view`, `base_view_database`, `inserted_rows` (phase 2 only),
`stored procedure result` (`Step 2 of 3: Inserted <n> rows into remote table '…'.`). The
documented statuses (`REMOTE_TABLE_ALREADY_EXISTS`, `VIEW_ALREADY_EXISTS`, `INVALID_SCHEMA`, …)
did not appear as rows: a name that exists failed the whole call with
`CREATE_REMOTE_TABLE [STORED PROCEDURE] [ERROR]` and no reason, and left the table as it was.

**What it leaves when it fails** (*measured*): a failure before the table is created — a query
the engine cannot run (a window function over a join with a file source) — leaves nothing. A
failure after it — a value the database refuses (5,000 characters into `varchar(4000)`), or any
`create_table_template` (below) — leaves the table created and empty, and no base view. The
next call with `replace_remote_table_if_exist = false` fails on the name.

**The base view it creates** (*measured*): a wrapper of the same name as the base view, the
source's type metadata on every column, no primary key, and the load query as
`DATA_LOAD_QUERY = '…'` at the end of its `DESC VQL`. `ALTER TABLE <view> DESCRIPTION = '…'` and
`ALTER TABLE <view> ADD PRIMARY KEY ( '…' )` keep the load query.

**Speed** (*measured*): a query that runs entirely in the target data source is copied inside
the database — sixty thousand rows in under a second; anything else passes through Denodo in batches of
the data source's `BATCHINSERTSIZE`, or through the database's bulk-load tool when the data
source enables it.

**Privileges** (documentation): `CONNECT` on the data source's database and `EXECUTE` on the data
source, `CONNECT` and `CREATE VIEW` on the base view's database (`CREATE FOLDER` for a new
folder), `EXECUTE` on the views in the query; `WRITE` on the data source for a custom template.
The data source's database account must be able to create tables in the schema.

## The command

```
CREATE [ OR REPLACE ] REMOTE TABLE <name>
     INTO <data source>
     [ CATALOG = '<catalog>' ]
     [ SCHEMA = '<schema>' ]
     [ CREATE INDEX <index> [ UNIQUE ] ON ( <field> [ ASC | DESC ] [, …] ) ]*
     [ CREATE_TABLE_TEMPLATE ( '<template>' [ DEFAULT ( '<param>' = '<value>' [, …] ) ] ) ]
     [ OPTIONS ( 'batch_insert_size' = '…' | 'location' = '…' | 'parquet_row_group_size' = '…' ) ]
     AS <select>
```

*Measured*: it answers no rows and no `affected`; it creates no base view, so the table cannot
be refreshed (`The REFRESH command is only valid for Summaries and Remote Tables`) or dropped by
`DROP_REMOTE_TABLE` (it refuses base views the procedure did not make). Without `OR REPLACE` a
name that exists fails with `Remote table "<catalog>"."<schema>".<name> already exists`. With
`OR REPLACE` the existing table is dropped and recreated with the new columns: a base view
another database had over it kept `view_status = OK` and `COUNT(*)` worked, and a query of a
column that was gone failed at run time with `Invalid column name '<column>'`. A table made this
way is taken over for dropping with `CREATE_REMOTE_TABLE` and `replace_remote_table_if_exist =
true`, then `DROP_REMOTE_TABLE` — a replacement, so the human's yes when it is not yours.

**Table creation templates.** `@{internal_parameter_table_name}`, `@{internal_parameter_columns}`
and `@{internal_parameter_restrictions}` are filled by the server; anything else is a parameter
with a `DEFAULT`. On the command a template that declares extra columns next to
`@{internal_parameter_columns}` worked (an identity key, measured on SQL Server); on the procedure, a template holding only the placeholders failed with a bare
error and left an empty table (*measured*, twice). Widen a text column with
`CAST(<text> AS varchar(<n>))` in the query instead (*measured*: `varchar(8000)` held 5,000
characters).

## Types (measured, SQL Server)

| Denodo type in the query | Column created |
|---|---|
| `text` with a source size (a JDBC column) | the source's type and size (`nvarchar(2000)`) |
| `text` without one (a file, an expression) | `varchar(4000)`; `CAST(… AS varchar(8000))` gives `varchar(8000)`. Characters outside the database's code page become `?` (`Tokyo 東京` → `Tokyo ??`); `CAST(… AS nvarchar(100))` gives `nvarchar(100)` and keeps them |
| `int` | `int` |
| `long` | `bigint` |
| `decimal` from a `numeric(7,2)` column | `numeric(7,2)` |
| `SUM` of a `decimal` | `numeric(38,20)` |
| `double` | `float` |
| `boolean` | `bit` |
| `localdate` | `date` |
| `timestamp` | `datetime2(7)` |
| `timestamptz` | `datetimeoffset` |

A field name that is a reserved word of the database becomes `field_0`, `field_1`, …
(documentation). In a load query, `CAST` takes SQL type names: `integer`, `bigint`,
`double precision`, `varchar(n)`, `decimal(p,s)`.

## REFRESH

```
REFRESH <base view made by CREATE_REMOTE_TABLE | summary>
    [ OPTIONS ( <as the command> ) ]
    [ CONTEXT ( … ) ]
    [ TRACE ]
```

*Measured*: no rows, no `affected`; the base view's count shows the result. It truncates the
table, runs `DATA_LOAD_QUERY`, inserts. When the load fails the table is left empty: with the
source file missing (`… [DF ROUTE] [PARSE_ERROR] …`), and with a column added to the view a
`SELECT *` load query reads (`Error executing data movement from view _p__… to source <ds>`).
If the table does not exist, `REFRESH` creates it (documentation). A base view the procedure
did not make: `The REFRESH command is only valid for Summaries and Remote Tables`.

**Changing the load query** (*measured*): `ALTER TABLE <view> DATA_LOAD_QUERY = '…'` is a syntax
error. Re-declaring the base view works — its `DESC VQL ('includeDependencies' = 'no',
'dropElements' = 'no')` from `CREATE TABLE` on, as `CREATE OR REPLACE TABLE`, with the new
`DATA_LOAD_QUERY = '…'` at its end — and leaves the table as it is; the next `REFRESH` loads by
the new query. `ALTER TABLE … ADD PRIMARY KEY ( 'a', 'b' )` keeps the load query too.

**Incremental loads** are not `REFRESH`: they are an upsert through the base view, `INSERT INTO
<base view> ON DUPLICATE KEY ( <key> ) UPDATE SELECT … WHERE <newer than the last load>` — the
watermark, the rows it cannot see and the checks are `references/incremental.md`.

## Who reads a table, and what a view feeds

- Whether a name is taken: `GET_JDBC_DATASOURCE_TABLES()` answers `catalog_name`,
  `schema_name`, `table_name`, `type` (`TABLE`, `VIEW`); its `table_name` filter is exact —
  `'HOUSEHOLD_INCOME'` does not find `household_income` — while SQL Server names are not, so compare `UPPER` of both
  (*measured*).
- A table's readers: the base views whose wrapper points at it. `GET_SOURCE_TABLE()` answers
  `source_catalog_name`, `source_schema_name`, `source_table_name` (and `sqlsentence` for a base
  view over a query) for one JDBC base view (`input_database_name`, `input_view_name`, both
  mandatory); `DESC VQL VIEW <v> ('includeDependencies' = 'no')` shows `RELATIONNAME` and
  the data source. List the base views of the databases you can read (`GET_VIEWS()`,
  `view_type = 0`) and check the candidates.
- A view's remote tables: **not in `USED_BY`** (*measured*; its summaries are). The load query
  is text in the base view's `DATA_LOAD_QUERY`: search `DESC VQL DATABASE <db>` for the view's
  name.

## DROP_REMOTE_TABLE

```
DROP_REMOTE_TABLE( base_view_database_name : text, base_view_name : text,
                   drop_base_view_on_cascade : boolean )   -- default false
```

*Measured*: drops the table and the base view or summary, answering one row per step
(`Step 1 of 2: Remote table '…' dropped successfully.`; for a summary whose table was never
loaded, `The remote table '…' did not exist.`). With readers and `cascade = false`, and on a base
view the procedure did not create, it fails with a bare `[STORED PROCEDURE] [ERROR]` and drops
nothing. `DROP VIEW` of the base view leaves the table in the database.

## Materialized tables

```
CREATE [ OR REPLACE ] MATERIALIZED TABLE [<db>.]<name>
    ( <field> : <vdp type> [, …] | <field> <SQL type> [, …] )
    [ FOLDER = '<folder>' ]
    [ [ CONSTRAINT '<name>' ] PRIMARY KEY ( '<field>' [, …] ) ]

CREATE [ OR REPLACE ] MATERIALIZED TABLE [<db>.]<name> AS <select>

SELECT <expressions> INTO <new name> FROM … [ WHERE … ] [ GROUP BY … ]
```

*Measured*: `GET_VIEWS()` reports `view_type = 3`; the rows are in the cache database as
`C_<NAME><digits>`, removed with the table by `DROP VIEW <name>` (`DROP MATERIALIZED TABLE` is a
syntax error). `INSERT … VALUES (…), (…)` and `INSERT INTO <t> ( <select> )` (columns in the
table's order) work; `UPDATE` → `Update on materialized tables is not allowed`, `DELETE` →
`Delete on materialized tables is not allowed`. The primary key is not enforced. A `decimal`
keeps twenty decimals, `DECIMAL(12,2)` declared or not. `CREATE OR REPLACE` over a table with
rows leaves 0 rows (the typed form) or the new query's rows (`AS SELECT`). `SELECT … INTO` a
name that exists: `error creating table: invalid view name: already exists`. The `AS SELECT`
and `INTO` forms keep the database in single-user mode until the query ends; `CREATE` then
`INSERT … SELECT` does not (documentation). The cache must be enabled for the database
(documentation).

## Temporary tables

`CREATE TEMPORARY TABLE <name> ( … ) | AS <select>` — same column grammar; visible only to the
session that made it, deleted when it closes (and after 48 hours regardless), insert-only, no
derived views over it. Needs `CREATE` or `CREATE_VIEW` on the database or the
`create_temporary_table` role. Documentation only.
