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

The clause order is fixed. Everything below is optional except `DRIVERCLASSNAME` and
`DATABASEURI`; the parser names the token where it stopped, not the clause that is out of
place, so when it complains about a clause that is obviously fine, look at what precedes
it.

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

`ALTER DATASOURCE JDBC` mirrors it without `FOLDER`. It is an `ALTER` — the human confirms
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

The ciphertext comes from `scripts/denodo secret encrypt --env dev` — never write the
underlying `ENCRYPT_PASSWORD '<password>'` yourself, because the plaintext would land in a
Bash argument and stay in the transcript (`/denodo:execute`, "A password for a data
source"). Encrypt on the server the data source will live on: the ciphertext is
server-specific, and it is salted, so the same password encrypts to a different string
every time. A ciphertext produced this way is accepted as a real credential — with a
deliberately wrong password the source answers `The username or password is incorrect`,
not a format error. *verified: 9.5.1 (live, 2026-09-12)*

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
(`File > Extensions management`), not VQL. Which drivers a server has is in that dialog;
there is no VQL that lists them, and you have no shell on the server.

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

All of them need the source to be reachable. Verified against live Oracle, SQL Server and
PostgreSQL on 9.5.1 (live, 2026-09-09).

| Procedure | Call | Notes |
|---|---|---|
| `PING_DATA_SOURCE` | `SELECT status, down_cause FROM PING_DATA_SOURCE() WHERE database_name='<db>' AND data_source_type='JDBC' AND data_source_name='<ds>'` | `UP` / `DOWN` plus the Java exception. Positional arguments do **not** work — pass the parameters in `WHERE` |
| `GET_JDBC_DATASOURCE_TABLES` | `… WHERE input_datasource_name='<ds>' [ AND input_catalog_name='<cat>' ] [ AND input_schema_name='<schema>' ] [ AND input_table_name='<t>' ] [ AND input_type='TABLE' ]` | the reliable one: the filters are input parameters, so the server asks the source only about what you want |
| `LIST_JDBC_DATASOURCE_TABLES` | `… WHERE data_source_name='<ds>'` | walks every catalog and schema. Fine on Oracle and PostgreSQL; **fails on SQL Server**, and filtering in `WHERE` does not help — the walk happens first |
| `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW` | `SELECT creation_vql FROM …() WHERE data_source_name='<ds>' [ AND catalog_name='<cat>' ] AND schema_name='<s>' AND table_name='<t>' AND base_view_name='<bv>' AND folder='<path>'` | returns **two rows**: the wrapper and the `CREATE TABLE`. `catalog_name` is required where the product has catalogs (SQL Server), omitted for Oracle |
| `GET_SOURCE_TABLE`, `GET_SOURCE_COLUMNS` | `… WHERE input_database_name='<db>' AND input_view_name='<view>'` | the other direction: which source table and columns an existing base view sits on — the way to answer "where does this column come from" |

What generated VQL looks like, and what to change in it:

- the wrapper is named after `base_view_name`, not `wr_…` — rename it in both statements
  if the project's conventions ask for a prefix;
- `DATASOURCENAME` comes back database-qualified (`<db>.<ds>`);
- the `CREATE TABLE` ends with `CONTEXT('SIMULATE' = 'NO')`, which is harmless to keep;
- types are chosen by the adapter: Oracle `NUMBER(10)` → `long`, `NVARCHAR2` → `text`,
  PostgreSQL `date` → `localdate`, SQL Server `bigint` → `long`.

## Data movement and MPP

`DATA_LOAD_CONFIGURATION ( USE_FOR_QUERY_OPTIMIZATION = DATA_MOVEMENT … )`,
`EMBEDDED_MPP`, `PROCESSING_UNITS`, external tables and bulk-load settings belong to
performance work, which these skills leave to Design Studio. The clauses exist in the grammar above; the
Administration Guide documents what they do. A data movement written into a view, a remote
table or a summary created in this data source's database is `/denodo:materialize`; the
temporary tables of a data movement go to its `TARGET_CATALOG` and `TARGET_SCHEMA`.
