# JDBC data sources and wrappers — full syntax

Source of the grammar: VQL Guide 9.5, *JDBC Data Sources* and *JDBC Wrappers*; the driver
list and the introspection procedures come from a live 9.5.1 server. Facts marked
`verified:` were run there.

## CREATE DATASOURCE JDBC

The clause order is fixed. Everything below is optional except `DRIVERCLASSNAME` and
`DATABASEURI`; the parser names the token where it stopped, not the clause that is out of
place, so when it complains about a clause that is obviously fine, look at what precedes
it.

```sql
CREATE [ OR REPLACE ] DATASOURCE JDBC <name> [ EMBEDDED_MPP ]
    [ ID = <literal> ]
    [ FOLDER = <literal> ]
    [ VAULT_SECRET = <literal> ]
    DRIVERCLASSNAME = <literal>
    DATABASEURI = <literal>
    [ <credentials> | <kerberos> | <oauth> | <aws iam> | <gcp> | <pass-through> ]
    [ WITH PROXY_CONNECTIONS ]
    [ CLASSPATH = <literal> ]
    [ DATABASENAME = <literal> DATABASEVERSION = <literal> ]
    [ ISOLATIONLEVEL = { TRANSACTION_NONE | TRANSACTION_READ_COMMITTED
                       | TRANSACTION_READ_UNCOMMITTED | TRANSACTION_REPEATABLE_READ
                       | TRANSACTION_SERIALIZABLE } ]
    [ IGNORETRAILINGSPACES = { TRUE | FALSE } ]
    [ FETCHSIZE = <integer> ]
    [ <data load configuration> ]
    [ CREDENTIALS_VAULT ( STATUS { ON | DEFAULT } [ PROVIDER CYBERARK ( … ) ] ) ]
    [ <pool configuration> ]
    [ <external data configuration> ]
    [ PROPERTIES ( <literal> = <literal> [ VAR ] [, … ] ) ]
    [ KERBEROSPROPERTIES ( <literal> = <literal> [, … ] ) ]
    [ OAUTHPROPERTIES ( <literal> = <literal> [, … ] ) ]
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
human asked for a specific pool. *verified: 9.5.1 (стенд, 2026-09-09)*

## Credentials

```sql
<credentials> ::= USERNAME = <literal> USERPASSWORD = <literal> [ ENCRYPTED ]
                | USERNAME = <literal> FROM_VAULT
                | USERNAME = <literal> FROM_VAULT ( VAULT_SECRET = <literal>, FIELD_AT_SECRET = DEFAULT )
```

| Mechanism | Syntax | Status |
|---|---|---|
| Password, encrypted | `USERPASSWORD = '<string>' ENCRYPTED`, string from `ENCRYPT_PASSWORD '<password>'` | *verified: 9.5.1 (стенд, 2026-09-09)* — and the encrypted string can be copied between data sources **on the same server**, which is how you reuse an existing source's credentials without ever seeing the password |
| Password, plain | `USERPASSWORD = '<password>'` | works, and the server stores it encrypted anyway — but the file keeps the clear text, so never in git |
| Credentials vault | `VAULT_SECRET = '<secret>'` at the top, `FROM_VAULT` instead of the password, `CREDENTIALS_VAULT ( STATUS ON … )` | *unverified: только по документации 9.5* — the vault must be configured on the server first |
| Kerberos | `USE_KERBEROS ( KRB_USERNAME = … { KRB_USERPASSWORD = … [ ENCRYPTED ] \| KRB_KEYTAB = … } )`, or `USE_KERBEROS_AT_RUNTIME` / `USE_KERBEROS_AT_INTROSPECTION` next to `<credentials>` | *unverified: только по документации 9.5* |
| OAuth | `USE_OAUTH ( TOKEN_ENDPOINTURL … CLIENT_IDENTIFIER … CLIENT_SECRET … [ ENCRYPTED ] OAUTH_USER … OAUTH_PASSWORD … SCOPE … )` | *unverified: только по документации 9.5* |
| AWS IAM | `USE_AWS_IAM_CREDENTIALS ( AWS_ACCESS_KEY_ID … AWS_SECRET_ACCESS_KEY … [ ENCRYPTED ] [ AWS_IAM_ROLE_ARN … ] [ AWS_REGION … ] )` | *unverified: только по документации 9.5* |
| GCP | `GCP ( OAUTH_TYPE … PRIVATE_KEY … [ ENCRYPTED ] PROJECT_ID … SERVICE_ACCOUNT_EMAIL … )` | *unverified: только по документации 9.5* |
| Pass-through session credentials | `WITH PASS-THROUGH SESSION CREDENTIALS ( <options> )` — the querying user's own credentials go to the source | *unverified*: the empty form `( )` is a syntax error on 9.5.1, so the options are not optional in practice |

The ciphertext comes from `scripts/denodo secret encrypt --env <env>` — never write the
underlying `ENCRYPT_PASSWORD '<password>'` yourself, because the plaintext would land in a
Bash argument and stay in the transcript (`/denodo:execute`, "A password for a data
source"). Encrypt on the server the data source will live on: the ciphertext is
server-specific, and it is salted, so the same password encrypts to a different string
every time. A ciphertext produced this way is accepted as a real credential — with a
deliberately wrong password the source answers `The username or password is incorrect`,
not a format error. *verified: 9.5.1 (стенд, 2026-09-12)*

Credentials are **replaced, never merged**: re-applying `CREATE OR REPLACE DATASOURCE`
without the `USERPASSWORD` clause leaves the source with no password, and the next query
answers `no password was provided`. *verified: 9.5.1 (стенд, 2026-09-09)*

## Driver directories (`CLASSPATH`)

`CLASSPATH` names a directory under `<DENODO_HOME>/lib/extensions/jdbc-drivers`, not a jar
path. `DATABASENAME` + `DATABASEVERSION` without `CLASSPATH` fail with
`error creating new data source: Cannot invoke "java.util.List.size()"`.
*verified: 9.5.1 (стенд, 2026-09-09)*

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
have to be installed on the server first — that is an administrator's job, not VQL.
The current list on any server: `ls <DENODO_HOME>/lib/extensions/jdbc-drivers`.

`DATABASENAME` / `DATABASEVERSION` select the **adapter**: the dialect, the delegation
rules and the ping query. The value is not validated — `DATABASEVERSION = '99'` is created
without a word — and a wrong adapter silently changes what Denodo pushes down.
*verified: 9.5.1 (стенд, 2026-09-09)*

## CREATE WRAPPER JDBC

```sql
CREATE [ OR REPLACE ] WRAPPER JDBC <name>
    [ FOLDER = <literal> ]
    [ DESCRIPTION = <literal> ]
    DATASOURCENAME = <name>
    {   [ CATALOGNAME = <literal> ] [ SCHEMANAME = <literal> ] RELATIONNAME = <literal>
      | [ CATALOGNAME = <literal> ] [ SCHEMANAME = <literal> ] [ PACKAGENAME = <literal> ]
        PROCEDURENAME = <literal>
      | SQLSENTENCE = <literal>
    }
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
                    | ESCAPE | EXTERN | EXTERNWHEREEXPRESSION | IS_AUTOINCREMENT
                    | ISCURSOR | ISPARAMETER | ISTABLE | MAXLEN = <integer>
                    | PARAMINDEX = <integer> | SQLFRAGMENT
```

- Field types are **Java class names**: `java.lang.Long`, `java.lang.Integer`,
  `java.lang.String`, `java.lang.Double`, `java.math.BigDecimal`, `java.sql.Timestamp`,
  `java.sql.Date`, `java.lang.Boolean`. *verified: 9.5.1 (стенд, 2026-09-09)*
- The `sourcetype*` properties record what the column is in the source (`'NUMBER'`,
  `'bigint'`, sizes, decimals). Introspection writes them; a hand-written wrapper without
  them queries fine. *verified: 9.5.1 (стенд, 2026-09-09)*
- **A subset of the table's columns is fine** — unlike DF, a JDBC wrapper that lists three
  of eighteen columns returns rows normally. *verified: 9.5.1 (стенд, 2026-09-09)*
- `SQLSENTENCE = 'SELECT …'` builds a wrapper over a query instead of a table — the query
  runs **in the source's own dialect**, so an aggregate pushed down this way is computed
  there. The output schema is written by hand or generated
  (`GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW_FROM_QUERY`); the mapping names must match the
  column labels the query returns, uppercased where the source uppercases them.
  *verified: 9.5.1 (стенд, 2026-09-09) — a `GROUP BY` over Oracle returned its 20 rows*
- `PROCEDURENAME` wraps a stored procedure; parameters are the fields marked `ISPARAMETER`
  with `PARAMINDEX`. *unverified: только по документации 9.5*
- `SOURCECONFIGURATION` here controls delegation and write support:
  `ALLOWDELETE`, `ALLOWINSERT`, `ALLOWUPDATE`, `DELEGATESQLSELECTION`,
  `DELEGATESQLSENTENCEASSUBQUERY`, `DATAINORDERFIELDSLIST`,
  `SUPPORTSDISTRIBUTEDTRANSACTIONS`.

## Introspection procedures

All of them need the source to be reachable. Verified against live Oracle, SQL Server and
PostgreSQL on 9.5.1 (стенд, 2026-09-09).

| Procedure | Call | Notes |
|---|---|---|
| `PING_DATA_SOURCE` | `SELECT status, down_cause FROM PING_DATA_SOURCE() WHERE database_name='<db>' AND data_source_type='JDBC' AND data_source_name='<ds>'` | `UP` / `DOWN` plus the Java exception. Positional arguments do **not** work — pass the parameters in `WHERE` |
| `GET_JDBC_DATASOURCE_TABLES` | `… WHERE input_datasource_name='<ds>' [ AND input_catalog_name='<cat>' ] [ AND input_schema_name='<schema>' ] [ AND input_table_name='<t>' ] [ AND input_type='TABLE' ]` | the reliable one: the filters are input parameters, so the server asks the source only about what you want |
| `LIST_JDBC_DATASOURCE_TABLES` | `… WHERE data_source_name='<ds>'` | walks every catalog and schema. Fine on Oracle and PostgreSQL; **fails on SQL Server**, and filtering in `WHERE` does not help — the walk happens first |
| `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW` | `SELECT creation_vql FROM …() WHERE data_source_name='<ds>' [ AND catalog_name='<cat>' ] AND schema_name='<s>' AND table_name='<t>' AND base_view_name='<bv>' AND folder='<path>'` | returns **two rows**: the wrapper and the `CREATE TABLE`. `catalog_name` is required where the product has catalogs (SQL Server), omitted for Oracle |
| `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW_FROM_QUERY` | same, with the query instead of the table | *unverified: только по документации 9.5* |
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
performance work, which is outside v1. The clauses exist in the grammar above; the
Administration Guide documents what they do.
