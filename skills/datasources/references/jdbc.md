# JDBC data sources and wrappers — tables

Source of the grammar: VQL Guide 9.5, *JDBC Data Sources* and *JDBC Wrappers*; the driver
list and the introspection procedures come from a live 9.5.1 server. Facts marked
`verified:` were run there.

This is the grammar for a base view over a **table or view**, on a data source that logs in
with a user name and password. A base view over a SQL query or a stored procedure, and a
data source that logs in any other way, are created in Design Studio (`SKILL.md`, **What you
build, and what goes to Design Studio**); the base views over the tables of such a source
are yours again once it answers.

## CREATE DATASOURCE JDBC

The clause order is fixed. Everything below is optional except `DRIVERCLASSNAME`,
`DATABASEURI` and `USERNAME` — the documentation makes the credentials optional, but the 9.5.1
parser refused the statement without `USERNAME` (measured; without `USERPASSWORD` alone it was
accepted). The parser names the token where it stopped, not the clause that is out of place,
so when it complains about a clause that is obviously fine, look at what precedes it.

```sql
CREATE [ OR REPLACE ] DATASOURCE JDBC <name> [ EMBEDDED_MPP ]
    [ ID = <literal> ]
    [ FOLDER = <literal> ]
    DRIVERCLASSNAME = <literal>
    DATABASEURI = <literal>
    [ USERNAME = <literal> USERPASSWORD = <literal> [ ENCRYPTED ] ]
    [ CLASSPATH = <literal> ]
    [ DATABASENAME = <literal> DATABASEVERSION = <literal> ]
    [ ISOLATIONLEVEL = { TRANSACTION_NONE | TRANSACTION_READ_COMMITTED
                       | TRANSACTION_READ_UNCOMMITTED | TRANSACTION_REPEATABLE_READ
                       | TRANSACTION_SERIALIZABLE } ]
    [ IGNORETRAILINGSPACES = { TRUE | FALSE } ]
    [ FETCHSIZE = <integer> ]
    [ <data load configuration> ]
    [ <pool configuration> ]
    [ <external data configuration> ]
    [ PROPERTIES ( <literal> = <literal> [ VAR ] [, … ] ) ]
    [ TRANSFER_RATE_FACTOR = <double> ]
    [ PROCESSING_UNITS = <integer> ] [ CPUS_PER_PROCESSING_UNIT = <integer> ]
    [ INTERNAL_TRANSFER_RATE = <double> ]
    [ <data infrastructure> ]
    [ DESCRIPTION = <literal> ]
    [ SOURCECONFIGURATION ( <property> [, <property> ]* ) ]
```

`ALTER DATASOURCE JDBC` takes the same clauses but `EMBEDDED_MPP`, `ID` and `FOLDER`: the
documented grammar lists the last two, and a 9.5.1 server answered them, when measured,
with `Syntax error … near 'FOLDER'` / `'ID'`. It is an `ALTER` — the human confirms
(`/denodo:vql`); `CREATE OR REPLACE` does not need that.

**The pool clauses are defaults.** `VALIDATIONQUERY`, `INITIALSIZE`, `MAXIDLE`, `MINIDLE`,
`MAXACTIVE`, `EXHAUSTEDACTION`, `TESTONBORROW`, `TESTONRETURN`, `TESTWHILEIDLE`,
`TIMEBETWEENEVICTION`, `NUMTESTPEREVICTION`, `MINEVICTABLETIME`, `POOLPREPAREDSTATEMENTS`,
`MAXOPENPREPAREDSTATEMENTS` are all printed by `DESC VQL` because the server fills them in;
a data source created without them behaves identically. Put them in a file only when the
human asked for a specific pool. *verified: 9.5.1 (live, 2026-09-09)*

## Credentials

```sql
USERNAME = <literal> USERPASSWORD = <literal> [ ENCRYPTED ]
```

| Mechanism | Syntax | Status |
|---|---|---|
| Password, encrypted | `USERPASSWORD = '<string>' ENCRYPTED`, string from `ENCRYPT_PASSWORD '<password>'` | *verified: 9.5.1 (live, 2026-09-09)* — and the encrypted string can be copied between data sources **on the same server**, which is how you reuse an existing source's credentials without ever seeing the password |
| Password, plain | `USERPASSWORD = '<password>'` | works, and the server stores it encrypted anyway — but the file keeps the clear text, so never in git |

A credentials vault, Kerberos, OAuth, AWS IAM, GCP service accounts and pass-through session
credentials are set up in the Design Studio wizard, not here.

The ciphertext comes from `${CLAUDE_PLUGIN_ROOT}/scripts/denodo secret encrypt --env <env>` —
never write the underlying `ENCRYPT_PASSWORD '<password>'` yourself, because the plaintext
would land in a Bash argument and stay in the transcript (`/denodo:execute`, "A password for
a data source"). Encrypt on the environment the data source will live on: the ciphertext is
tied to the installation's encryption key, and it is salted, so the same password encrypts
to a different string every time. A ciphertext produced this way is accepted as a real
credential — with a deliberately wrong password the source answers `The username or
password is incorrect`, not a format error. *verified: 9.5.1 (live, 2026-09-12)*

Credentials are **replaced, never merged**: re-applying `CREATE OR REPLACE DATASOURCE`
without the `USERPASSWORD` clause leaves the source with no password, and the next query
answers `no password was provided`. *verified: 9.5.1 (live, 2026-09-09)*

## Driver directories (`CLASSPATH`)

`CLASSPATH` names a directory under `<DENODO_HOME>/lib/extensions/jdbc-drivers`, not a jar
path. `DATABASENAME` + `DATABASEVERSION` without `CLASSPATH` fail with
`error creating new data source: Cannot invoke "java.util.List.size()"`.
*verified: 9.5.1 (live, 2026-09-09)*

What a 9.5.1 server ships with:

```
amazon-athena-1.0 amazon-athena-3.0 amazon-redshift-2.x cassandra-1.0 clickhouse
databricks-2 databricks-3 denodo-jdbc-odbc denodo-jtds-1.3.1 derby-10
elasticsearch-6.4 elasticsearch-6.7 elasticsearch-8 elasticsearch-9 exasol-7.1
jdbc-odbc jtds-1.2.5 jtds-1.2.8 jtds-1.3.1 mariadb mariadb-2.7 maxcompute
mssql-jdbc mssql-jdbc-6.x mssql-jdbc-7.x mssql-jdbc-9.x mssql-jdbc-10.x mssql-jdbc-12.x
oracle oracle-9i oracle-10g oracle-11g oracle-12c oracle-18c oracle-19c oracle-21c
postgresql postgresql-8 … postgresql-17 postgresql-13gcp presto-0.1x prestosql-3xx
snowflake-1.x spanner sqreamdb trino-4xx vdp-8.0 vdp-9 vertica-7 vertica-9
```

Drivers Denodo may not redistribute (MySQL, IBM DB2, Teradata, BigQuery, Hive, Impala)
have to be installed on the server first — an administrator's job in Design Studio
(`File > Extensions management`), not VQL. Whether one was is a read, as measured on a
9.5.1 server: `LIST RESOURCES JDBC VERSION = '<name>'` lists the jars imported under that
name (`mysql-8`), empty when none were; `LIST RESOURCES JDBC` alone lists every name a
driver can be imported under, not the ones that were.

`DATABASENAME` / `DATABASEVERSION` select the **adapter**: the dialect, the delegation
rules and the ping query. The value is not validated — `DATABASEVERSION = '99'` is created
without a word — and a wrong adapter silently changes what Denodo pushes down.
*verified: 9.5.1 (live, 2026-09-09)*

## CREATE WRAPPER JDBC

```sql
CREATE [ OR REPLACE ] WRAPPER JDBC <name>
    [ FOLDER = <literal> ]
    [ DESCRIPTION = <literal> ]
    DATASOURCENAME = <name>
    [ CATALOGNAME = <literal> ] [ SCHEMANAME = <literal> ] RELATIONNAME = <literal>
    [ OUTPUTSCHEMA ( <field> [, <field> ]* ) ]
    [ ALIASES ( <literal> = <literal> [, … ] ) ]
    [ SOURCECONFIGURATION ( <property> [, … ] ) ]
    [ [ CONSTRAINT <literal> ] PRIMARY KEY ( <literal> [, … ] ) ]
    [ <foreign key> ]* [ <index> ]*

<field> ::= <name> [ = <mapping:literal> ] : <type:literal>
              [ ( { OBL | OPT } ) ]
              [ ( <field property> = <literal> [, … ] ) ]
              [ <inline constraint> ]*
          | <name> [ = <mapping> ] : ARRAY OF ( <register field> ) …
          | <register field>

<field property>  ::= DEFAULTVALUE | SOURCETYPENAME | SOURCETYPEID | SOURCETYPESIZE
                    | SOURCETYPEDECIMALS | SOURCETYPERADIX
<inline constraint> ::= [ NOT ] NULL | [ NOT ] UPDATEABLE
                    | { SORTABLE [ ASC | DESC ] | NOT SORTABLE }
                    | ESCAPE | IS_AUTOINCREMENT | MAXLEN = <integer>
```

- Field types are **Java class names**: `java.lang.Long`, `java.lang.Integer`,
  `java.lang.String`, `java.lang.Double`, `java.math.BigDecimal`, `java.sql.Timestamp`,
  `java.sql.Date`, `java.lang.Boolean`. *verified: 9.5.1 (live, 2026-09-09)*
- The `sourcetype*` properties record what the column is in the source (`'NUMBER'`,
  `'bigint'`, sizes, decimals). Introspection writes them; a hand-written wrapper without
  them queries fine. *verified: 9.5.1 (live, 2026-09-09)*
- **A subset of the table's columns is fine** — unlike DF, a JDBC wrapper that lists three
  of eighteen columns returns rows normally. *verified: 9.5.1 (live, 2026-09-09)*
- `SOURCECONFIGURATION` here controls delegation and write support:
  `ALLOWDELETE`, `ALLOWINSERT`, `ALLOWUPDATE`, `DELEGATESQLSELECTION`,
  `DELEGATESQLSENTENCEASSUBQUERY`, `DATAINORDERFIELDSLIST`,
  `SUPPORTSDISTRIBUTEDTRANSACTIONS`.

## Introspection procedures

`PING_DATA_SOURCE` and the listing and generating procedures need the source to be
reachable; `GET_SOURCE_TABLE` / `GET_SOURCE_COLUMNS` read the base view's own metadata and
answer without it. Run against Oracle, SQL Server and PostgreSQL —
*verified: 9.5.1 (live, 2026-09-09)*.

| Procedure | Call | Notes |
|---|---|---|
| `PING_DATA_SOURCE` | `SELECT status, down_cause FROM PING_DATA_SOURCE() WHERE database_name='<db>' AND data_source_type='JDBC' AND data_source_name='<ds>'` | `UP` / `DOWN` plus the Java exception. Positional arguments work too; a bare `Error executing query. Total time …` comes, for one, from a database or data source that does not exist |
| `GET_JDBC_DATASOURCE_TABLES` | `… WHERE input_datasource_name='<ds>' [ AND input_catalog_name='<cat>' ] [ AND input_schema_name='<schema>' ] [ AND input_table_name='<t>' ] [ AND input_type='TABLE' ]` | the reliable one: the filters are input parameters, so the server asks the source only about what you want |
| `LIST_JDBC_DATASOURCE_TABLES` | `… WHERE data_source_name='<ds>'` | Deprecated (documentation); walks every catalog and schema the login can list. It failed on the SQL Server measured, and a `WHERE` does not help because the walk happens first. Use `GET_JDBC_DATASOURCE_TABLES` |
| `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW` | `SELECT creation_vql FROM …() WHERE data_source_name='<ds>' [ AND catalog_name='<cat>' ] AND schema_name='<s>' AND table_name='<t>' AND base_view_name='<bv>' AND folder='<path>'` | with `folder`, returns **three rows**: a `CREATE OR REPLACE FOLDER` of that folder with no description, the wrapper and the `CREATE TABLE` — *verified: 9.5.1 (live, 2026-10-06)*. `catalog_name` is required where the product has catalogs (SQL Server), omitted for Oracle |
| `GET_SOURCE_TABLE`, `GET_SOURCE_COLUMNS` | `… WHERE input_database_name='<db>' AND input_view_name='<view>'` | the other direction: which source table and columns an existing base view sits on — the way to answer "where does this column come from" |

What generated VQL looks like, and what to change in it:

- the wrapper is named after `base_view_name`, not `wr_…` — rename it in both statements
  if the project's conventions ask for a prefix;
- `DATASOURCENAME` comes back database-qualified (`<db>.<ds>`);
- the `CREATE TABLE` ends with `CONTEXT('SIMULATE' = 'NO')`, which is harmless to keep;
- types are chosen by the adapter: Oracle `NUMBER(10)` → `long`, `NVARCHAR2` → `text`,
  PostgreSQL `date` → `localdate`, SQL Server `bigint` → `long`;
- the first row, `CREATE OR REPLACE FOLDER`, is not part of the base view: leave it out. Over a
  folder that exists it clears the folder's description, and over a folder you did not create
  in this session it is a re-declaration that waits for the human's yes.

## Every table of a schema

For a request that names a set of tables — every table of one or more schemas — the list, the
statements and the check each come from one read (`/denodo:vql`, **Many objects at once**).

**What is already there**, by the table it reads rather than by its name — a colleague's
`bv_crm_customer` over `crm.customers` is the same table as your `bv_crm_customers` would be:

```sql
-- verified: 9.5.1 (live, 2026-10-06)
SELECT e.name, s.source_catalog_name, s.source_schema_name, s.source_table_name
  FROM GET_ELEMENTS() AS e
       INNER JOIN GET_SOURCE_TABLE() AS s
       ON (s.input_database_name = e.database_name AND s.input_view_name = e.name)
 WHERE e.input_database_name = 'sales_analytics' AND e.input_type = 'views'
   AND e.subtype = 'base' AND e.base_view_type = 'jdbc';
```

`base_view_type = 'jdbc'` is not a nicety: one base view of another kind in the database — a
delimited file, a JSON document — and `GET_SOURCE_TABLE` fails the whole query with `GET_SOURCE_TABLE
[STORED_PROCEDURE] [ERROR]`.

**Every statement, in one query** — here over `ds_erp`, a SQL Server data source. The
introspection procedures join: the list of tables feeds the generator, the base view's name is
an expression, and the wrapper gets its `wr_` name in both statements. The constant inputs of the generator go in `WHERE` — in `ON` they fail with `The
following obligatory fields cannot be removed`:

```sql
-- verified: 9.5.1 (live, 2026-10-06) — SQL Server, several schemas in one query
SELECT t.schema_name, t.table_name,
       CASE WHEN g.creation_vql LIKE 'CREATE OR REPLACE WRAPPER%' THEN 1 ELSE 2 END AS step,
       REPLACE(REPLACE(g.creation_vql, 'WRAPPER JDBC bv_', 'WRAPPER JDBC wr_'),
               'WRAPPER (jdbc bv_', 'WRAPPER (jdbc wr_') AS creation_vql
  FROM GET_JDBC_DATASOURCE_TABLES() AS t
       INNER JOIN GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW() AS g
       ON (g.catalog_name = t.catalog_name AND g.schema_name = t.schema_name
           AND g.table_name = t.table_name
           AND g.base_view_name = CONCAT('bv_erp_', t.schema_name, '_', t.table_name))
 WHERE t.input_database_name = 'sales_analytics' AND t.input_datasource_name = 'ds_erp'
   AND t.input_catalog_name = 'erp' AND t.schema_name IN ('sales', 'billing')
   AND t.type = 'TABLE'
   AND g.database_name = 'sales_analytics' AND g.data_source_name = 'ds_erp'
   AND g.folder = '/01 - connectivity'
   AND g.creation_vql NOT LIKE 'CREATE OR REPLACE FOLDER%'
 ORDER BY schema_name, table_name, step;
```

- Run it with `--max-rows 5000` — two rows per table — and check `truncated` before writing
  the rows into the file, in their order: each wrapper before its table.
- `input_schema_name` narrows the walk to one schema; for several, `t.schema_name IN (…)`
  filters a walk of the whole catalog (on SQL Server give `input_catalog_name`).
- `t.input_database_name` and `g.database_name` are the **data source's** database. When the
  views go into another one, the statements still create them wherever the file is applied,
  and `DATASOURCENAME` comes back qualified with the source's database (`shared.ds_erp`).
- The name rule is one for every table and mechanical — the table's name as it is, not
  singularised by hand table by table. When the same table name exists in two schemas of the
  list, the schema goes into every name, as above — not only into the two that collide. Base
  views someone made earlier under another rule keep their names: renaming them is their
  owner's yes.
- Keep out of the file what is not the human's data — views (`t.type`); the server's own `C_…`
  and `vdb_cache_…` tables, in a database that doubles as Denodo's cache store — and the rows of
  every table that already has a base view (the query above): those are plan rows, not statements.

**The check, one read per view** — a file of `SELECT COUNT(*) AS row_count FROM <bv>;`, one line
per base view, run with `--continue-on-error`: an entry with `ok: false` is that table's failure
(a permission on one table, a type the adapter cannot read), and the others still answer. Then
the reads of **Verify** in `SKILL.md` that look at values, the same way — one statement per view,
generated from `GET_VIEW_COLUMNS()`: `SELECT COUNT(<c1>) AS <c1>, COUNT(<c2>) AS <c2>, … FROM <bv>`
finds a column that is `NULL` throughout, and a few sample rows show what the values end with.
When the request names who will query the views, whether they can is part of the check — the
grants on the database (`/denodo:security`, its first read); granting is the human's yes.

## Data movement and MPP

`DATA_LOAD_CONFIGURATION ( USE_FOR_QUERY_OPTIMIZATION = DATA_MOVEMENT … )`,
`EMBEDDED_MPP`, `PROCESSING_UNITS`, external tables and bulk-load settings belong to
performance work, which these skills leave to Design Studio. The clauses exist in the grammar above; the
Administration Guide documents what they do. A data movement written into a view, a remote
table or a summary created in this data source's database is `/denodo:materialize`; the
temporary tables of a data movement go to its `TARGET_CATALOG` and `TARGET_SCHEMA`.
