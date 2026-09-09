---
name: datasources
description: Use when connecting a source to Denodo 9.5 and turning it into base views — a delimited file or CSV (CREATE DATASOURCE DF), a JSON file or REST payload (CREATE DATASOURCE JSON), a relational database over JDBC (CREATE DATASOURCE JDBC), the wrapper over any of them, and the base view itself (CREATE TABLE … ADD SEARCHMETHOD). Also for "connect Oracle/Postgres", "onboard this CSV", "read that JSON export", "make base views over the source", introspecting a source's tables, and for a base view that was created fine but returns no rows or wrong values. Not for derived views over base views that already exist — that is /denodo:views.
---

# Data sources, wrappers and base views

Three objects, always in this order: **data source → wrapper → base view**. The data
source says where the data lives and how to reach it, the wrapper says what one record
looks like, the base view is the object the rest of Denodo queries. Skipping a level is
not possible; putting all three in one file per source is the norm.

Databases and folders are `/denodo:catalog`, everything built *on top of* a base view is
`/denodo:views`, applying files is `/denodo:execute`, and the working loop, naming and the
safety rule are `/denodo:vql`.

**The dangerous part of this skill is not syntax — it is silent success.** Every template
below has a way to be accepted by the server and still deliver nothing, or the wrong
thing, with no error anywhere. The Verify section is not optional.

## Templates

Each template is one file, applied whole. `CREATE OR REPLACE` throughout, so re-applying
after a fix is safe — with one exception, the JDBC password, called out below.

### Delimited file (CSV) — DF

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE DATASOURCE DF ds_crm
    FOLDER = '/01 - connectivity'
    IGNOREMATCHINGERRORS = FALSE
    ROUTE LOCAL 'LocalConnection' '/data/exports/crm/customers.csv'
    CHARSET = 'UTF-8'
    COLUMNDELIMITER = ','
    HEADER = TRUE
    DESCRIPTION = 'CRM customer export, refreshed nightly';

CREATE OR REPLACE WRAPPER DF wr_crm_customers
    FOLDER = '/01 - connectivity'
    DATASOURCENAME = ds_crm
    OUTPUTSCHEMA (
        cust_id = 'cust_id',
        first_name = 'first_name',
        last_name = 'last_name',
        email = 'email' NULLVALUE '',
        country = 'country',
        city = 'city',
        created_dt = 'created_dt',
        segment_cd = 'segment_cd'
    );

CREATE OR REPLACE TABLE bv_crm_customers I18N us_pst (
        cust_id:text,
        first_name:text,
        last_name:text,
        email:text,
        country:text,
        city:text,
        created_dt:date,
        segment_cd:text
    )
    FOLDER = '/01 - connectivity'
    CACHE OFF
    TIMETOLIVEINCACHE DEFAULT
    ADD SEARCHMETHOD wr_crm_customers (
        OUTPUTLIST ( cust_id, first_name, last_name, email, country, city, created_dt, segment_cd )
        WRAPPER (df wr_crm_customers)
    );
```

- **`OUTPUTSCHEMA` lists every column of the file, in file order** — not the columns the
  human asked for. The mapping is **positional**: the names are labels, and Denodo does not
  match them against the header. Two consequences, both silent:
  a wrapper with three of eight columns returns **zero rows**, and a wrapper with the right
  count in the wrong order returns rows with **values in the wrong columns**
  (`s_store_id` holding `1`, `s_city` holding `13-MAR-12`). Narrow the columns in the base
  view's field list or in a derived view, never in the wrapper.
- **`IGNOREMATCHINGERRORS = FALSE` is what turns that silence into a message.** The server
  default is `TRUE`: lines whose column count does not match the schema are dropped without
  a word, which is exactly the zero-row case above. With `FALSE` the same wrapper answers
  `[DF ROUTE] [PARSE_ERROR] Invalid line found at data file. Different number of columns` —
  put it in every file source you onboard, and leave it in unless the human wants malformed
  rows skipped in production.
- The wrapper carries **names only**. A type there (`created_dt = 'created_dt' :
  'java.util.Date'`) is `Syntax error … near '''` in any spelling — DF wrappers do not
  take types. Types are declared in `CREATE TABLE`, and Denodo parses the text into them:
  `created_dt:date` over `2021-04-12` works.
- `NULLVALUE ''` is for **text** columns only, and it is a decision, not boilerplate:
  without it an empty field stays an empty string, with it becomes `NULL`. Numeric and date
  columns need nothing — an empty field is already `NULL` there.
  *verified: 9.5.1 (стенд, 2026-09-09)*
- **The base view may list fewer columns than the wrapper** — that is where you narrow.
  The wrapper mirrors the file, the base view exposes what the human asked for (four of
  twenty-nine columns is fine, in the field list and in `OUTPUTLIST` together).
  *verified: 9.5.1 (стенд, 2026-09-09)*
- `TIMETOLIVEINCACHE DEFAULT` is required between `CACHE OFF` and `ADD SEARCHMETHOD`.
- The `CONSTRAINTS ( … )` block that the server prints in `DESC VQL` is optional; so is
  `I18N` inside `ADD SEARCHMETHOD`. `I18N <map>` after the view name is not
  (`LIST MAPS I18N` shows the 76 available; `us_pst` is the usual default).
- The path is **on the Denodo server**, not on your machine. If it points to a directory,
  every file in it is read as one table — add `FILENAMEPATTERN = '.*\.csv'` and keep the
  files' schema identical.
- `FOLDER = '…'` does **not** create the folder: a missing one is
  `Error creating data source: destination folder '/x' not found`. Folders come first, and
  they are `/denodo:catalog`.

### JSON file or endpoint

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE DATASOURCE JSON ds_oms
    FOLDER = '/01 - connectivity'
    ROUTE LOCAL 'LocalConnection' '/data/exports/oms/orders.json'
    CHARSET = 'UTF-8';

CREATE OR REPLACE WRAPPER JSON wr_oms_orders
    FOLDER = '/01 - connectivity'
    DATASOURCENAME = ds_oms
    TUPLEROOT '/JSONFile/JSONArray'
    OUTPUTSCHEMA (jsonfile = 'JSONFile' : REGISTER OF (
        order_id = 'JSONFile.JSONArray.order_id' : 'java.lang.String',
        customer_id = 'JSONFile.JSONArray.customer_id' : 'java.lang.String',
        order_dt = 'JSONFile.JSONArray.order_dt' : 'java.lang.String',
        status = 'JSONFile.JSONArray.status' : 'java.lang.String',
        total_amount = 'JSONFile.JSONArray.total_amount' : 'java.lang.Double',
        shipping = 'JSONFile.JSONArray.shipping' : REGISTER OF (
            country = 'country' : 'java.lang.String',
            city = 'city' : 'java.lang.String',
            zip = 'zip' : 'java.lang.String'
        ),
        lines = 'JSONFile.JSONArray.lines' : ARRAY OF (
            line = 'line' : REGISTER OF (
                line_no = 'line_no' : 'java.lang.Integer',
                sku = 'sku' : 'java.lang.String',
                qty = 'qty' : 'java.lang.Integer',
                price = 'price' : 'java.lang.Double'
            )
        )
    )
    );

CREATE OR REPLACE TYPE oms_shipping AS REGISTER OF (country:text, city:text, zip:text);
CREATE OR REPLACE TYPE oms_order_line AS REGISTER OF (line_no:int, sku:text, qty:int, price:double);
CREATE OR REPLACE TYPE oms_order_line_array AS ARRAY OF oms_order_line;

CREATE OR REPLACE TABLE bv_oms_orders I18N us_pst (
        order_id:text,
        customer_id:text,
        order_dt:text,
        status:text,
        total_amount:double,
        shipping:oms_shipping,
        lines:oms_order_line_array
    )
    FOLDER = '/01 - connectivity'
    CACHE OFF
    TIMETOLIVEINCACHE DEFAULT
    ADD SEARCHMETHOD wr_oms_orders (
        OUTPUTLIST ( order_id, customer_id, order_dt, status, total_amount, shipping, lines )
        WRAPPER (json wr_oms_orders)
    );
```

- **The whole record sits inside one `REGISTER OF` wrapper field.** `jsonfile = 'JSONFile'
  : REGISTER OF ( … )` is not decoration: a flat `OUTPUTSCHEMA` is accepted and then
  **multiplies rows by the nested arrays** — a three-order file came back as four rows,
  one of them all-`NULL`. There is no error to catch this; only counting rows catches it.
- `TUPLEROOT '/JSONFile/JSONArray'` for a file whose top level is an array. Mappings of
  top-level fields are the full path (`JSONFile.JSONArray.x`); inside a nested `REGISTER`
  or `ARRAY` they are relative (`country`). The name of the element inside `ARRAY OF ( … )`
  is arbitrary — only its shape matters.
- **A compound column needs a named type.** `CREATE TABLE` takes a type identifier, so a
  register or array column must be declared first with `CREATE OR REPLACE TYPE`
  (register first, then the array of it). Inline structures do not parse.
- A JSON payload over HTTP swaps the `ROUTE` for
  `ROUTE HTTP 'http.CommonsHttpClientConnection' GET '<uri>'` plus authentication and
  pagination — `references/json.md`.
- Reading a register field in `SELECT` needs parentheses: `(shipping).country`. Plain
  `shipping.country` is read as *view.column* and fails with `Field not found
  'shipping.country' in view 'shipping'`. Flattening arrays is `/denodo:views`.

### Relational database over JDBC

**Ask for the parts, build the URI yourself.** Nobody has a JDBC URL lying around; they
have a host, a port and the name of a database. Ask for those, in one message, with the
defaults already filled in, then assemble the string from the table below.

| Source | `DRIVERCLASSNAME` | `DATABASEURI` | `CLASSPATH` | `DATABASENAME` |
|---|---|---|---|---|
| PostgreSQL | `org.postgresql.Driver` | `jdbc:postgresql://<host>:5432/<database>` | `postgresql-16` | `postgresql` |
| Oracle, service name | `oracle.jdbc.OracleDriver` | `jdbc:oracle:thin:@<host>:1521/<service>` | `oracle-21c` | `oracle` |
| Oracle, SID | `oracle.jdbc.OracleDriver` | `jdbc:oracle:thin:@<host>:1521:<sid>` | `oracle-21c` | `oracle` |
| SQL Server | `com.microsoft.sqlserver.jdbc.SQLServerDriver` | `jdbc:sqlserver://<host>:1433;databaseName=<database>` | `mssql-jdbc` | `sqlserver` |
| MySQL / MariaDB | `org.mariadb.jdbc.Driver` | `jdbc:mariadb://<host>:3306/<database>` | `mariadb` | `mysql` |
| Snowflake | `net.snowflake.client.jdbc.SnowflakeDriver` | `jdbc:snowflake://<account>.snowflakecomputing.com/?db=<db>&warehouse=<wh>` | `snowflake-1.x` | `snowflake` |
| Databricks | `com.databricks.client.jdbc.Driver` | `jdbc:databricks://<host>:443/default;httpPath=<path>` | `databricks-3` | `databricks` |
| Another Denodo server | `com.denodo.vdp.jdbc.Driver` | `jdbc:vdb://<host>:9999/<database>` | `vdp-9` | `denodo` |

*verified: 9.5.1 (стенд, 2026-09-09) — PostgreSQL, Oracle (service name) and SQL Server;
the rest of the rows come from the driver directories the server ships and are unverified.*
`DATABASEVERSION` is the source's own version as a string (`'16'`, `'19c'`, `'2022'`) —
ask for it, do not assume the newest. The full driver list is in `references/jdbc.md`.

Certificate and TLS options ride in the URI, not in a separate clause — SQL Server on a
self-signed certificate needs `;trustServerCertificate=true` appended, and that is a
question for the human, not a default you add silently.

```sql
-- verified: 9.5.1 (стенд, 2026-09-09) — created and queried against a live Oracle
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE DATASOURCE JDBC ds_orders_db
    FOLDER = '/01 - connectivity'
    DRIVERCLASSNAME = 'oracle.jdbc.OracleDriver'
    DATABASEURI = 'jdbc:oracle:thin:@oracle-edw.internal:1521/XEPDB1'
    USERNAME = 'appuser'
    USERPASSWORD = '<ciphertext — see Passwords below; fill it in before applying>' ENCRYPTED
    CLASSPATH = 'oracle-21c'
    DATABASENAME = 'oracle'
    DATABASEVERSION = '19c'
    DESCRIPTION = 'Order management database, read-only account';
```

**Then stop writing VQL and ask the server.** Once the data source is up, it introspects
the database for you — you never ask the human for column names or types:

```sql
-- verified: 9.5.1 (стенд, 2026-09-09) — against live Oracle, SQL Server and PostgreSQL
SELECT status, down_cause FROM PING_DATA_SOURCE()
 WHERE database_name = 'sales_analytics' AND data_source_type = 'JDBC'
   AND data_source_name = 'ds_orders_db';

-- Oracle: no catalog. On SQL Server add AND input_catalog_name = '<database>'
SELECT catalog_name, schema_name, table_name, type FROM GET_JDBC_DATASOURCE_TABLES()
 WHERE input_datasource_name = 'ds_orders_db'
   AND input_schema_name = 'RETAIL';

SELECT creation_vql FROM GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW()
 WHERE data_source_name = 'ds_orders_db'
   AND schema_name = 'RETAIL' AND table_name = 'CUSTOMER'
   AND base_view_name = 'bv_orders_db_customer'
   AND folder = '/01 - connectivity';
```

`GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW` returns **two rows**: the `CREATE OR REPLACE
WRAPPER JDBC` with every column, its Java type and the source's own type metadata, and the
matching `CREATE OR REPLACE TABLE`. Paste both into the file under the data source, and
mind two things: the wrapper is given the *base view's* name, so rename it to `wr_…` if
the project's conventions say so (rename it in both statements), and the generated
`DATASOURCENAME` is database-qualified. The generated `CREATE TABLE` ends with
`CONTEXT('SIMULATE' = 'NO')` — an execution hint, not part of the definition; keep it or
drop it, the object is the same.

- `PING_DATA_SOURCE` before introspecting: a `DOWN` answer names the cause —
  `UnknownHostException` (network), `ClassNotFoundException` (wrong `CLASSPATH`), an
  authentication error (credentials).
- Two listing procedures exist and they are not equivalent.
  `GET_JDBC_DATASOURCE_TABLES` takes `input_catalog_name` / `input_schema_name` /
  `input_table_name` as **input** and is the one to use.
  `LIST_JDBC_DATASOURCE_TABLES` takes only the data source and walks everything: fine on
  Oracle and PostgreSQL, but on SQL Server it fails outright — filtering it in `WHERE`
  does not help, because the walk happens first.
- A demo or dev database is full of Denodo's own cache tables (`C_…`); the real tables sit
  in the business schemas. Show the human the schema list before picking.

When the database is unreachable from here (a different network zone, credentials not
issued yet), introspection is not available and you write the wrapper by hand from the
schema the human gives you — the DDL still parses and the objects still get created; only
`SELECT` fails, on the connection. A JDBC wrapper may list **a subset of the table's
columns** and works fine — that is the opposite of DF, where a subset returns zero rows:

```sql
-- verified: 9.5.1 (стенд, 2026-09-09) — created against an unreachable host
CREATE OR REPLACE WRAPPER JDBC wr_orders_db_orders
    FOLDER = '/01 - connectivity'
    DATASOURCENAME = ds_orders_db
    SCHEMANAME = 'public'
    RELATIONNAME = 'orders'
    OUTPUTSCHEMA (
        order_id = 'order_id' :'java.lang.Long' (OPT) SORTABLE,
        customer_id = 'customer_id' :'java.lang.String' (OPT) SORTABLE,
        order_dt = 'order_dt' :'java.sql.Timestamp' (OPT) SORTABLE,
        total_amount = 'total_amount' :'java.math.BigDecimal' (OPT) SORTABLE,
        status = 'status' :'java.lang.String' (OPT) SORTABLE
    );

CREATE OR REPLACE TABLE bv_orders_db_orders I18N us_pst (
        order_id:long,
        customer_id:text,
        order_dt:timestamp,
        total_amount:decimal,
        status:text
    )
    FOLDER = '/01 - connectivity'
    CACHE OFF
    TIMETOLIVEINCACHE DEFAULT
    ADD SEARCHMETHOD wr_orders_db_orders (
        OUTPUTLIST ( order_id, customer_id, order_dt, total_amount, status )
        WRAPPER (jdbc wr_orders_db_orders)
    );
```

- JDBC wrappers **do** take types, and they are **Java** class names
  (`java.lang.Long`, `java.sql.Timestamp`, `java.math.BigDecimal`) — the base view above
  them uses VQL types (`long`, `timestamp`, `decimal`). Introspection also records the
  source's own type (`sourcetypename='NUMBER'`, sizes, decimals); those properties are
  informative, and a hand-written wrapper without them works.
- The clause order of `CREATE DATASOURCE JDBC` is fixed, and the parser reports the token
  where it gave up, not the one that is out of place. Keep the order of the template.
  Everything the server prints back beyond it — `VALIDATIONQUERY`, `INITIALSIZE`,
  `MAXACTIVE`, the rest of the pool — is default and belongs in the file only when the
  human asked for a specific pool.
- `CLASSPATH` is the **name of a driver directory shipped with Denodo**, not a path to a
  jar (the table above; the server's full list is `references/jdbc.md`).
  `DATABASENAME`/`DATABASEVERSION` **without** `CLASSPATH` fail at creation with
  `error creating new data source: Cannot invoke "java.util.List.size()"` — a message
  that says nothing about the missing clause.
- The version is **not validated**: `DATABASEVERSION = '99'` is created happily. A wrong
  adapter silently changes what gets delegated to the source; confirm it with the human.

## When you cannot see the file

A file source needs the header verbatim, and the file lives on the server, where you have
no shell. Three ways to get it, in order of preference:

1. **Ask the human for `head -1`** (or the first 20 lines of the JSON). Cheapest and most
   accurate; they usually have access even when you do not.
2. **Read an existing wrapper over the same file.** Find candidates and compare paths:
   ```sql
   SELECT database_name, name, subtype FROM GET_ELEMENTS() WHERE type = 'datasource';
   ```
   then `vql desc --env <env> --database <db> <ds> --type "datasource df" --vql` to see the
   `ROUTE`, and the same on the wrapper for the column list. Reading other databases is
   allowed anywhere; changing them is not.
3. **Let the server read the file for you, as one column per line.** A DF source whose
   `TUPLEPATTERN` captures the whole line returns the raw text of the file — header
   included, and it works for JSON too:
   ```sql
   -- verified: 9.5.1 (стенд, 2026-09-09)
   CREATE OR REPLACE DATASOURCE DF ds_crm
       FOLDER = '/01 - connectivity'
       ROUTE LOCAL 'LocalConnection' '/data/exports/crm/customers.csv'
       CHARSET = 'UTF-8' TUPLEPATTERN = '(.*)' HEADER = FALSE;
   CREATE OR REPLACE WRAPPER DF wr_crm_customers
       FOLDER = '/01 - connectivity' DATASOURCENAME = ds_crm
       OUTPUTSCHEMA ( line = 'line' );
   CREATE OR REPLACE TABLE bv_crm_customers I18N us_pst ( line:text )
       FOLDER = '/01 - connectivity' CACHE OFF TIMETOLIVEINCACHE DEFAULT
       ADD SEARCHMETHOD wr_crm_customers ( OUTPUTLIST ( line ) WRAPPER (df wr_crm_customers) );
   ```
   `SELECT line FROM bv_crm_customers` with `--max-rows 5` shows the header, then you
   **rewrite the same three statements in the same file** with the real schema and apply it
   again. Use the names the objects will keep — that way the reading pass leaves no probe
   object behind, it is just the first version of the file (`/denodo:vql`: no probe objects,
   one file applied whole).

## Passwords: the human hands you one, the file only ever holds the ciphertext

`USERPASSWORD` is the only secret in these templates, and a `.vql` file lives in git. You
do not need a vault, a server login, or a manual step from the human — encrypt it yourself
through the same tool, and keep the plaintext out of both the repository and the command
line:

```bash
# verified: 9.5.1 (стенд, 2026-09-09)
# 1. write the statement into a temp file OUTSIDE the repository — never `-e "…'<password>'"`,
#    because command arguments are kept in the session transcript
printf "ENCRYPT_PASSWORD '<password>';\n" > "$SCRATCH/enc.vql"

# 2. one row comes back: the encrypted string
${CLAUDE_PLUGIN_ROOT}/scripts/denodo vql run --env <env> "$SCRATCH/enc.vql"

# 3. delete the temp file
rm "$SCRATCH/enc.vql"
```

The project file then carries `USERPASSWORD = '<the string from step 2>' ENCRYPTED`, and
the server accepts it — a wrong password encrypted this way fails with the source's own
`password authentication failed`, which is proof the ciphertext was read.

- **The ciphertext is server-specific.** Encrypt on the server the file will be applied to;
  moving a data source to another environment means repeating step 1–3 there.
- **A source to the same database may already exist — then you need no password at all.**
  `vql desc --env <env> --database <db> <existing_ds> --type "datasource jdbc" --vql`
  prints `USERNAME` and `USERPASSWORD '…' ENCRYPTED`, and both work verbatim in your own
  data source. The donor may live in **any database on that server** — look for it with
  `SELECT database_name, name FROM GET_ELEMENTS() WHERE type = 'datasource' AND subtype = 'jdbc'`
  and compare `DATABASEURI`. Reading another database is allowed; changing it is not.
  *verified: 9.5.1 (стенд, 2026-09-09)* — this is the first thing to try when the human
  says the password is not theirs to give.
- **A plaintext password is accepted too** (the server stores it encrypted regardless), so
  a `.vql` with a plaintext password *works* — which is exactly why it is easy to commit
  one by accident. Encrypt before writing the file, not after.
- If the human typed a production password into the chat, say so plainly once and suggest
  rotating it; the transcript keeps it.
- `CREDENTIALS_VAULT` / `FROM_VAULT` is the clean answer where a vault is configured —
  `references/jdbc.md`. Development servers rarely have one, hence the flow above.

**`CREATE OR REPLACE DATASOURCE` rewrites the credentials every time the file is applied,
and omitting the clause erases them.** Re-applying the same data source without
`USERPASSWORD` leaves it with no password at all — the next query fails with the source's
`no password was provided`. *verified: 9.5.1 (стенд, 2026-09-09)* A placeholder does the
same thing, more quietly. So: if you do not have the real value, do not run that statement
— say so, and leave the data source alone rather than replacing a working one.

## What you need before filling a template

"Connect our Oracle" is a complete request and an incomplete specification. Ask for what
is missing **in one message, with the defaults already proposed**, then build everything
else yourself. Three or four lines, not an interview:

> To connect it I need: the host (port 1521 unless you say otherwise), the service name or
> SID, the Oracle version, and the login and password of the account Denodo should read
> with. The password goes no further than this session — I encrypt it before it reaches
> any file.

| Slot | Where it comes from |
|---|---|
| JDBC host, port, database / service / SID | **the human** — then you assemble `DATABASEURI` from the table above; never ask for a JDBC URL |
| JDBC product and version | **the human** — it picks `DRIVERCLASSNAME`, `CLASSPATH` and the adapter; a wrong adapter changes what gets pushed down and the server will not complain |
| JDBC login | **the human**; it goes into the file |
| Any password | the human gives it to you in whatever form suits them; **you** encrypt it and only the ciphertext reaches the file (above). Ask for it last, after everything else is settled, so it spends as little time in the conversation as possible |
| JDBC schema, tables, columns, types | **the server** — `GET_JDBC_DATASOURCE_TABLES` and `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW` after the source is up. Ask only which tables the human wants, and only if the schema has more than a handful |
| File path / URI | **the human** — and it is **server-side**: the file must be readable by the Denodo server, not by you |
| Delimiter, header, charset | the human, or a sample of the file; `,` + `HEADER = TRUE` + `UTF-8` is the common case |
| **Every column name of a file, in order** | the file header, verbatim and complete — the server does **not** introspect files. Three ways to get it, including one that needs nobody: **When you cannot see the file** above. Never infer it from the columns the human wants |
| JSON shape | a sample of the document — nesting decides `REGISTER OF` / `ARRAY OF`, and you cannot guess it. Same three ways |
| Object names | the conventions in `/denodo:vql` — unless the human asked for something specific in this request (a prefix, a naming scheme). An explicit instruction wins over the convention; keep the type marker inside it (`green1_ds_store`, not `green1_store`) |
| Column types of a file source | your decision in `CREATE TABLE`: text unless the format is unambiguous; a wrong type costs `NULL`s, not an error |
| Database, folder | `/denodo:catalog` and the conventions in `/denodo:vql`: `/01 - connectivity`, `ds_<source>`, `wr_<source>_<entity>`, `bv_<source>_<entity>` |

Do not ask about caching, pooling, statistics or delegation options. They have defaults,
and they are in the references when the human raises them.
Do not ask a question whose answer is one read away: what exists (`LIST DATASOURCES <type>`),
how a similar object is written here (`vql desc … --vql`), whether the source answers
(`PING_DATA_SOURCE`).

## Reference

- `references/df.md` — full `CREATE DATASOURCE DF` / `WRAPPER DF`: route types (LOCAL,
  HTTP, FTP, HDFS, S3, ABFS), filters, fixed-width and regex-parsed files, `NULLVALUE`,
  interpolation variables.
- `references/json.md` — full `CREATE DATASOURCE JSON` / `WRAPPER JSON`: HTTP routes,
  authentication, pagination, NDJSON, OpenAPI 3, `CREATE TYPE`.
- `references/jdbc.md` — full `CREATE DATASOURCE JDBC` / `WRAPPER JDBC`: the driver
  directory names on the server, adapters, Kerberos / OAuth / vault / pass-through
  credentials, connection pool, `SQLSENTENCE` and stored-procedure wrappers, introspection
  procedures.
- `references/base-view.md` — full `CREATE TABLE`: search methods and constraints, cache
  clauses, primary keys, tags, indexes, `ONSCHEMACHANGE`, VQL types.

## Verify

`ok: true` on the `CREATE` statements proves the parser was happy and nothing else. Read
the data back, every time:

| Check | How | What a failure looks like |
|---|---|---|
| Rows arrive | `vql run --env dev --database <db> -e "SELECT COUNT(*) FROM <bv>"` | `0` — a DF wrapper missing columns, or an empty/unreachable file |
| The count is *right* | compare with what the human expects the source to hold | a JSON wrapper without the `REGISTER OF` wrapper inflates rows through nested arrays |
| Values are values | `SELECT * FROM <bv>` with `--max-rows 5`, look at every column | a whole column of `NULL` = the type in `CREATE TABLE` does not match the data (`cust_id:int` over `C-10472`) |
| Schema is what you wrote | `vql desc --env dev --database <db> <bv>` | missing or extra columns |
| A JDBC source can be reached | `SELECT status, down_cause FROM PING_DATA_SOURCE() WHERE database_name='<db>' AND data_source_type='JDBC' AND data_source_name='<ds>'` | `DOWN` with `UnknownHostException` (network/host), `ClassNotFoundException` (wrong `CLASSPATH`), authentication errors (credentials) |
| The folder exists before you use it | `SELECT name, folder FROM GET_ELEMENTS() WHERE input_database_name = '<db>' AND type = 'folder'` — `LIST FOLDERS` does not exist |  `Syntax error … near 'FOLDERS'`; and a missing folder fails the `CREATE` itself |
| The base view is in the catalog | `SELECT name, subtype, folder FROM GET_ELEMENTS() WHERE input_database_name = '<db>' AND type = 'view'` | **not** `LIST VIEWS`: it lists derived views only and answers an empty set for a database full of base views — *verified: 9.5.1 (стенд, 2026-09-09)*. `LIST TABLES` does not exist |
| What already exists | `LIST DATASOURCES DF` / `JSON` / `JDBC`, `LIST WRAPPERS DF`, `LIST TYPES` — the **type is mandatory** on `LIST DATASOURCES` | `Syntax error … near 'DATASOURCES'` when you leave it out |

`GET_ELEMENTS()` takes its filters as `input_database_name` / `input_type` and returns
`database_name`, `name`, `type`, `subtype`, `folder` — the input columns carry the `input_`
prefix, the output ones do not.

**When a template does not cover your case, ask the server, not your memory.**
`vql desc --env dev --database <db> <object> --type "datasource json" --vql` prints the
server's own `CREATE` statement for any existing object of that type — the exact 9.5.1
syntax, including the parts no documentation shows. An existing source over the same file
is also where the true column list comes from. This is read-only and allowed anywhere,
production included.

## Common mistakes

| You wrote | What happens | Fix |
|---|---|---|
| DF `OUTPUTSCHEMA` with the columns the human asked for | `CREATE` succeeds, `SELECT` returns **0 rows** | list every column of the file; narrow in the base view |
| DF `OUTPUTSCHEMA` with the right count but the wrong order | rows arrive with values under the wrong names | the mapping is positional — reorder to match the header |
| DF source without `IGNOREMATCHINGERRORS = FALSE` | schema mismatches are dropped row by row, silently | add it; the mismatch becomes `[DF ROUTE] [PARSE_ERROR] Invalid line found at data file` |
| `FOLDER = '/x'` where `/x` does not exist | `Error creating data source: destination folder '/x' not found` | create the folder first (`/denodo:catalog`) |
| DF `OUTPUTSCHEMA` with types (`: 'java.util.Date'`) | `Syntax error … near '''` | DF wrappers take `name = 'mapping'` only, plus `(OPT)` / `NULLVALUE` |
| Wrapper with no `OUTPUTSCHEMA` at all | creates, then `SELECT` fails: DF `[NO_CREATED_ACCESS] Unable to create xml raw access`, JSON `[JSON WRAPPER] [PROCESSING]` | the server does not introspect files — write the schema |
| JSON `OUTPUTSCHEMA` as a flat field list | `CREATE` succeeds, row count is wrong (arrays multiply rows) | wrap the fields in `<name> = 'JSONFile' : REGISTER OF ( … )` |
| `CREATE TABLE … ( lines:ARRAY OF (…) )` | `Syntax error` | declare `CREATE OR REPLACE TYPE` first, use its name |
| `CACHE OFF ADD SEARCHMETHOD` | `Syntax error … near 'ADD'` | `CACHE OFF TIMETOLIVEINCACHE DEFAULT ADD SEARCHMETHOD` |
| `cust_id:int` over text keys | column comes back all `NULL`, no error | fix the type in `CREATE TABLE`, re-apply |
| `DATABASENAME`/`DATABASEVERSION` without `CLASSPATH` | `error creating new data source: Cannot invoke "java.util.List.size()"` | add `CLASSPATH = '<driver directory>'` |
| JDBC clauses in a different order | `Syntax error` naming a clause that is fine | restore the template's order; the named token is where the parser stopped |
| `SELECT shipping.country` | `Field not found 'shipping.country' in view 'shipping'` | `(shipping).country` |
| `LIST DATASOURCES` | `Syntax error … near 'DATASOURCES'` | the type is mandatory: `LIST DATASOURCES DF` |
| `SELECT` from a JDBC base view whose source is unreachable | `[JDBC ROUTE] [CONNECTION_ERROR]` | expected without the database; the objects are still correct — verify with `PING_DATA_SOURCE` |
| Relative path in `ROUTE LOCAL` | `[DF ROUTE] [PARSE_ERROR] … Error getting input Stream` | absolute path, on the server's filesystem |

Dropping a source takes its wrappers and base views with it (`CASCADE`), and that is the
human's call — `/denodo:vql`. Replacing a working source with `CREATE OR REPLACE` is
cheap and safe; the one thing it destroys is the stored password.
