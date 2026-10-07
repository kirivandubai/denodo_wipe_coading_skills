---
name: datasources
description: Use when connecting any source to Denodo 9.5 and turning it into base views — a delimited file or CSV (CREATE DATASOURCE DF), a JSON file (CREATE DATASOURCE JSON), a relational database over JDBC (CREATE DATASOURCE JDBC), the wrapper and the base view (CREATE TABLE … ADD SEARCHMETHOD) — and equally for a REST or HTTP API, Excel, XML, Parquet, Salesforce, SAP, OData, SOAP, MongoDB, a SaaS application, a base view over a SQL query or a database's stored procedure or function, or a base view whose source schema changed. Also for "connect Oracle/Postgres", "onboard this CSV", "make base views over the source", introspecting a source's tables, and a base view that was created fine but returns no rows or wrong values. Not for derived views over base views that already exist — that is /denodo:views.
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

## What you build, and what goes to Design Studio

Three kinds of source have verified templates here, and those you build yourself:

| Source | Template |
|---|---|
| A delimited file (CSV, TSV, pipe-separated) on the Denodo server's own filesystem | DF, below |
| A JSON file on the Denodo server's own filesystem | JSON, below |
| A table or view of a relational database, with a user name and password | JDBC, with introspection, below |

**Everything else the human creates in Design Studio, and you continue from what they
created.** Denodo's own guide says creating data sources in VQL "is prone to errors so we
suggest you do it graphically": the wizard introspects the source, previews the rows and
writes the search methods, pagination and credentials itself. Hand-written VQL for these
guesses at clauses nothing here has verified, and the server accepts most guesses at
creation and fails later, at query time. That covers:

- a REST or HTTP API — JSON or XML behind a URL, an OpenAPI document — even when the
  payload is "just JSON";
- a file anywhere other than the server's own disk (S3, ADLS, HDFS, FTP/SFTP, a URL), a
  compressed or encrypted file, Excel, XML, fixed-width, Parquet, Delta, Iceberg;
- a delimited file whose records run over more than one line — a line break inside quoted
  values (a delimiter inside them is fine, `references/df.md`); the raw lines (**When you
  cannot see the file**) show it before you write anything;
- Salesforce, SAP, OData, SOAP, MongoDB, LDAP, a SaaS wizard, a custom wrapper;
- a base view over a SQL query, or over a stored procedure or function, instead of a table;
- a JDBC data source that logs in by Kerberos, OAuth, cloud IAM, a credentials vault or
  pass-through, or needs a driver the server does not ship — **the data source only**: once
  it answers `PING_DATA_SOURCE`, the base views over its tables are yours again;
- an existing base view whose source changed under it — columns added, dropped, retyped.

A request that mixes the two is split, not refused: build your part now and hand over the
rest in the same message.

### Handing it over

The database and the folder are yours, not the wizard's: create them first if they do not
exist yet (`/denodo:catalog`), and check that the names you are about to propose are free
(`GET_ELEMENTS()`, below). Then one message, with these parts in this order:

1. What goes to Design Studio, in one line, and why.
2. Where to click, from the table below.
3. What to enter so the result fits the project: the database, the folder
   (`/01 - connectivity`), and the names the conventions give (`ds_…`, `bv_…` —
   `/denodo:vql`).
4. When the source needs a secret — a password, token, client secret, key: it is typed into
   the wizard. Do not ask for it and do not offer to encrypt it; nothing of yours will use
   it.
5. What to tell you when it is done (the base view names), and what you will do then.

| To create | In Design Studio |
|---|---|
| A data source of any type | `File > New > Data source`, then the type: a REST API is **REST API → JSON**, a delimited file **FILES → Delimited file (CSV)** |
| The base views over it | open the data source → **Create base view** |
| A base view over a SQL query | the JDBC data source → **Create base view** → **Create from query** |
| A base view over a stored procedure or function | the JDBC data source → **Create base view**: the same dialog lists the stored procedures |
| Folder and description | the **Metadata** tab of the same dialog |
| A change to an existing data source or base view | double-click it in the Server Explorer → **Edit** |
| A base view out of date with its source | open the base view → **Edit** → **Source Refresh**: it shows the differences and propagates them to the views that depend on it |

*unverified: 9.5 documentation only* — the menu paths come from the Administration Guide,
*Creating Data Sources and Base Views*.

### When the human says it is done

- Find what was created: `SELECT name, subtype, folder FROM GET_ELEMENTS() WHERE
  input_database_name = '<db>' AND type = 'view'`, and read each base view with
  `vql desc --env dev "<db>.<bv>" --vql`. Read it; never apply it (`/denodo:execute`).
- Run the **Verify** table below on it. A wizard-made base view fails silently in the same
  ways yours does — a wrong row count, a column of `NULL`s, padded text. For an API, the
  count to expect is the total the API itself reports.
- If `SELECT` answers that some fields are obligatory, the base view has mandatory inputs (a
  view over a procedure does): ask the human for one value they know the answer for, and
  query with it in `WHERE`.
- **Do not copy it into your files.** Your `.vql` holds only the objects you create, and a
  comment at its top names the objects made in Design Studio that belong with them. The
  `DESC VQL` output opens with `DROP … CASCADE`, and even without that line, re-applying a
  copy overwrites the wizard's configuration and credentials with your transcription of
  them. If you created nothing yourself, there is no file. Either way, your summary names
  the objects that exist on the server only.
- A change to such an object goes back to Design Studio too — not an `ALTER`, and not a
  `CREATE OR REPLACE` from your file.
- **Source Refresh on a base view that your own file declares** changes the server, not
  the file, and your next apply would undo it. Bring the wrapper's `OUTPUTSCHEMA` and the
  base view's field list in your file into line with `DESC VQL` after the refresh.

### When a template does not work straight away

The budget is this: apply the template, and for each failure make the one fix this skill
names for that error or symptom — **Common mistakes**, **Verify**, the notes under each
template — and re-apply. Stop at the first of:

- an error or a wrong result this skill does not name;
- a named error whose fix has nothing to change — what it tells you to check is already
  right;
- the same failure again after its named fix.

Stopping means no clause of your own to try, no second reading pass to test a theory, and
never `IGNOREMATCHINGERRORS = TRUE` to make the count come out. Hand the source over as
above, and add what you learned: the header or sample you read, the exact error, what the
named fix changed. Your objects already exist — say so, and let the human choose between
opening your data source in Design Studio and fixing it against the wizard's preview, or
having you drop them first (a drop is theirs to confirm). Take their statements out of your
file as soon as the human takes the objects over — from then on a re-apply would undo the
wizard's work. If the wizard cannot read the source either, the fix is in the export, and a
cleaned file fits your template as it is.

| Thought | Reality |
|---|---|
| "The human said try whatever it takes" | That is the outcome they want, not permission to experiment on their server. Design Studio's preview tests a setting in a click; you test it in an apply and a `SELECT` |
| "One more clause might do it" | A clause this skill does not name is a guess, and the parser accepts most guesses |
| "It is only JSON over HTTP" | It is a REST source: authentication, pagination and the connection settings are all the wizard's |
| "A source on the server already does this; I can copy its `DESC VQL`" | A donor is a source of grammar for the three templates above. For anything else it is still Design Studio |
| "The reference has the grammar for it" | The references hold the grammar of the three templates only |

## Templates

Each template is one file, applied whole. `CREATE OR REPLACE` throughout, so re-applying
after a fix is safe — with one exception, the JDBC password, called out below.

### Delimited file (CSV) — DF

```sql
-- verified: 9.5.1 (live, 2026-10-07)
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
        created_dt:localdate,
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
  (`s_store_id` holding `1`, `s_city` holding `13-MAR-12`). Narrow the columns in a derived
  view, never in the wrapper — and not in the base view either (below).
- **`IGNOREMATCHINGERRORS = FALSE` is what turns that silence into a message.** The server
  default is `TRUE`: lines whose column count does not match the schema are dropped without
  a word, which is exactly the zero-row case above. With `FALSE` the same wrapper answers
  `[DF ROUTE] [PARSE_ERROR] Invalid line found at data file. Different number of columns` —
  put it in every file source you onboard, and leave it in unless the human wants malformed
  rows skipped in production.
- The wrapper carries **names only**. A type there (`created_dt = 'created_dt' :
  'java.util.Date'`) is `Syntax error … near '''` in any spelling — DF wrappers do not
  take types. Types are declared in `CREATE TABLE`, and Denodo parses the text into them:
  `created_dt:localdate` over `2021-04-12` works.
- `NULLVALUE ''` is for **text** columns only, and it is a decision, not boilerplate:
  without it an empty field stays an empty string, with it becomes `NULL`. Numeric and date
  columns need nothing — an empty field is already `NULL` there.
  *verified: 9.5.1 (live, 2026-09-09)*
- **The base view lists the wrapper's columns in the wrapper's order; narrow in a derived
  view.** A base view with fewer columns creates and reads fine, but an equality `WHERE` on
  it is handed to the DF wrapper **by position** and filters another column of the file,
  without an error; the `(any) OPT ANY` block `DESC VQL` prints does not prevent it. If the
  human wants it narrow anyway, give it `CONSTRAINTS ( ADD <column> NOS ZERO () … )` for
  every one of its columns: Denodo then filters itself, and the answer is right.
  *verified: 9.5.1 (live, 2026-09-30)*
- The `CONSTRAINTS ( … )` block that the server prints in `DESC VQL` is optional for a
  delimited file whose base view mirrors the wrapper — the DF wrapper does filter what the
  server hands it — and so is `I18N` inside `ADD SEARCHMETHOD`. For a JSON file it is not optional (**JSON file** below). `I18N <map>` after the view name is not
  — it is the zone and the language dates and timestamps are read in. Take the one the
  database's other base views declare (`DESC VQL VIEW`), or the human's; with nothing to follow,
  the connected database's (`SELECT GETSESSION('i18n') FROM Dual()`), named in the message —
  the templates' `us_pst` is a placeholder. `LIST MAPS I18N` lists them.
- The path is **on the Denodo server**, not on your machine. If it points to a directory,
  every file in it is read as one table — add `FILENAMEPATTERN = '.*\.csv'` and keep the
  files' schema identical.

### JSON file

```sql
-- verified: 9.5.1 (live, 2026-10-07)
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
        CONSTRAINTS (
            ADD order_id NOS ZERO ()
            ADD customer_id NOS ZERO ()
            ADD order_dt NOS ZERO ()
            ADD status NOS ZERO ()
            ADD total_amount NOS ZERO ()
            ADD shipping NOS ZERO ()
            ADD shipping.country NOS ZERO ()
            ADD shipping.city NOS ZERO ()
            ADD shipping.zip NOS ZERO ()
            ADD lines NOS ZERO ()
        )
        OUTPUTLIST ( order_id, customer_id, order_dt, status, total_amount, shipping, lines )
        WRAPPER (json wr_oms_orders)
    );
```

- **`CONSTRAINTS` with `NOS ZERO ()` on every column and every register subfield is what
  makes `WHERE` work.** Left out, the server declares each column `(any) OPT ANY` — "the
  wrapper filters this itself" — and the JSON wrapper then ignores the condition: `WHERE
  order_id = '…'` returns every order, with no error, and so does every view built on the
  base view, `FLATTEN` included. `NOS ZERO ()` tells the server the wrapper filters nothing,
  and the server filters instead. A register column needs a line per subfield as well
  (`shipping.country`): without it `WHERE (shipping).country = 'DE'` is still ignored. The
  fields of array elements need none — they are filtered after `FLATTEN` in the view above.
  Design Studio writes `NOS ZERO ()` on the JSON base views it creates —
  *verified: 9.5.1 (live, 2026-09-30)*.

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
- Flattening arrays is `/denodo:views`.

### Relational database over JDBC

Assemble `DATABASEURI` from the parts the human gives (**What you need before filling a
template**):

| Source | `DRIVERCLASSNAME` | `DATABASEURI` | `CLASSPATH` | `DATABASENAME` |
|---|---|---|---|---|
| PostgreSQL | `org.postgresql.Driver` | `jdbc:postgresql://<host>:5432/<database>` | `postgresql-<major>` | `postgresql` |
| Oracle, service name | `oracle.jdbc.OracleDriver` | `jdbc:oracle:thin:@<host>:1521/<service>` | `oracle-<release>` | `oracle` |
| Oracle, SID | `oracle.jdbc.OracleDriver` | `jdbc:oracle:thin:@<host>:1521:<sid>` | `oracle-<release>` | `oracle` |
| SQL Server | `com.microsoft.sqlserver.jdbc.SQLServerDriver` | `jdbc:sqlserver://<host>:1433;databaseName=<database>` | `mssql-jdbc` | `sqlserver` |
| Snowflake | `net.snowflake.client.jdbc.SnowflakeDriver` | `jdbc:snowflake://<account>.snowflakecomputing.com/?db=<db>&warehouse=<wh>` | `snowflake-1.x` | `snowflake` |
| Databricks | `com.databricks.client.jdbc.Driver` | `jdbc:databricks://<host>:443/default;httpPath=<path>` | `databricks-3` | `databricks` |
| Another Denodo server | `com.denodo.vdp.jdbc.Driver` | `jdbc:denodo://<host>:9999/<database>` | `vdp-9` | `denodo` |

*verified: 9.5.1 (live, 2026-09-09) — PostgreSQL, Oracle (service name) and SQL Server;
the rest of the rows come from the driver directories the server ships and are unverified.*
`DATABASEVERSION` is the source's own version as a string (`'16'`, `'19c'`, `'2022'`) — ask
for it, do not assume the newest — and `CLASSPATH` the directory matching it (`postgresql-16`,
`oracle-19c`; `oracle` for 23 and newer). MySQL and other databases whose driver Denodo does
not ship need the official one, imported by an administrator first (`references/jdbc.md`).

Certificate and TLS options are driver properties: in the URI or in `PROPERTIES ( … )` —
SQL Server on a self-signed certificate needs `trustServerCertificate=true`, and that is a
question for the human, not a default you add silently.

```sql
-- verified: 9.5.1 (live, 2026-10-07) — created against an unreachable host, ciphertext included
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE DATASOURCE JDBC ds_orders_db
    FOLDER = '/01 - connectivity'
    DRIVERCLASSNAME = 'oracle.jdbc.OracleDriver'
    DATABASEURI = 'jdbc:oracle:thin:@oracle-edw.internal:1521/ORDERSPDB'
    USERNAME = 'appuser'
    USERPASSWORD = '<ciphertext — see Passwords below; fill it in before applying>' ENCRYPTED
    CLASSPATH = 'oracle-19c'
    DATABASENAME = 'oracle'
    DATABASEVERSION = '19c'
    DESCRIPTION = 'Order management database, read-only account';
```

**Then stop writing VQL and ask the server.** Once the data source is up, it introspects
the database for you — you never ask the human for column names or types:

```sql
-- verified: 9.5.1 (live, 2026-09-09) — against live Oracle, SQL Server and PostgreSQL
SELECT status, down_cause FROM PING_DATA_SOURCE()
 WHERE database_name = 'sales_analytics' AND data_source_type = 'JDBC'
   AND data_source_name = 'ds_orders_db';

-- Oracle: no catalog. On SQL Server add AND input_catalog_name = '<database>'
SELECT catalog_name, schema_name, table_name, type FROM GET_JDBC_DATASOURCE_TABLES()
 WHERE input_datasource_name = 'ds_orders_db'
   AND input_schema_name = 'OMS';

SELECT creation_vql FROM GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW()
 WHERE data_source_name = 'ds_orders_db'
   AND schema_name = 'OMS' AND table_name = 'CUSTOMER'
   AND base_view_name = 'bv_orders_db_customer'
   AND folder = '/01 - connectivity';
```

Given a `folder`, `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW` returns **three rows** (*verified: 9.5.1
(live, 2026-10-06)*): a `CREATE OR REPLACE FOLDER` of it without a description — leave it out: the
folder belongs in the project's folder file (`/denodo:catalog`), and over an existing folder it clears
the description — then the `CREATE OR REPLACE WRAPPER JDBC` with every column and its Java type, and
the matching `CREATE OR REPLACE TABLE`. Paste those two into the file under the data source; the
wrapper is given the *base view's* name, so rename it to `wr_…` in both, and `DATASOURCENAME` comes
back database-qualified. The `CREATE TABLE` ends with `CONTEXT('SIMULATE' = 'NO')`, a harmless hint.
**Every table of a schema at once** — what already has a base view, all the statements in one
query, the check per view: `references/jdbc.md`, *Every table of a schema*.

- `PING_DATA_SOURCE` before introspecting: a `DOWN` answer names the cause —
  `UnknownHostException` (network), `ClassNotFoundException` (wrong `CLASSPATH`), an
  authentication error (credentials).
- A database that doubles as Denodo's cache store is full of the server's own cache tables
  (`C_…`); the real tables sit in the business schemas. Show the human the schema list
  before picking.
- The clause order of `CREATE DATASOURCE JDBC` is fixed, and the parser reports the token
  where it gave up, not the one that is out of place. Keep the order of the template.
  Everything the server prints back beyond it — `VALIDATIONQUERY`, `INITIALSIZE`,
  `MAXACTIVE`, the rest of the pool — is default and belongs in the file only when the
  human asked for a specific pool.
- `CLASSPATH` is the **name of a driver directory shipped with Denodo**, not a path to a
  jar (the table above; the server's full list is `references/jdbc.md`).
- The version is **not validated**: `DATABASEVERSION = '99'` is created happily. A wrong
  adapter silently changes what gets delegated to the source; confirm it with the human.

When the server cannot reach the database, the wrapper is written by hand from the schema the
human gives: `references/jdbc.md`, *A wrapper by hand* — a JDBC wrapper may list a subset of
columns, unlike DF.

## When you cannot see the file

A file source needs the header verbatim, and the file lives on the server, where you have
no shell. Three ways to get it, in order of preference:

1. **Read an existing base view over the same file** — when the server has one, this is the
   cheapest and the most accurate, because what comes back is already working on this
   server. Find the candidates:
   ```sql
   -- verified: 9.5.1 (live, 2026-10-07)
   SELECT database_name, name FROM GET_ELEMENTS()
    WHERE type = 'view' AND subtype = 'base' AND name LIKE '%<word from the file name>%';
   ```
   then ask the **base view** — not the source, not the wrapper — for its VQL, qualifying
   the name so you do not have to switch databases:
   ```bash
   # verified: 9.5.1 (live, 2026-09-12)
   ${CLAUDE_PLUGIN_ROOT}/scripts/denodo vql desc --env dev "<other db>.<base view>" --vql
   ```
   One call returns the whole chain: the `ROUTE` with the server-side path, the parse clauses
   (`COLUMNDELIMITER`, `ENDOFLINEDELIMITER`, `HEADER`, `CHARSET`), the wrapper's complete
   `OUTPUTSCHEMA` in file order, and the `CREATE TABLE` types that are known to work.
   The same call **on the source** returns only the source — no wrapper and no column list,
   which is the one thing you came for. Reading other databases is allowed anywhere;
   changing them waits for the human's yes (`/denodo:vql`).

   The donor is a source of **grammar, not of defaults**: server-generated sources carry no
   `IGNOREMATCHINGERRORS` and often no `CHARSET`, so you add `IGNOREMATCHINGERRORS = FALSE`
   yourself — inheriting the donor's silence is exactly the failure the template protects you
   from. Its mappings may be quoted upper-case names (`'"HD_DEMO_SK"'`); both forms work, the
   mapping is positional (*verified: 9.5.1 (live, 2026-09-12)*).

   Look at `truncated` in the answer and narrow the query when it is true: a cut read looks
   exactly like "there is no such object" and sends you to way 3 for nothing.
2. **Ask the human for `head -1`** (or the first 20 lines of the JSON). Accurate, and they
   usually have access even when you do not — but it costs a round trip, so it comes second
   when the server already holds an object over the same file.
3. **Let the server read the file for you, as one column per line.** A DF source whose
   `TUPLEPATTERN` captures the whole line returns the raw text of the file — header
   included, and it works for JSON too:
   ```sql
   -- verified: 9.5.1 (live, 2026-10-07)
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

## Passwords: the file only ever holds the ciphertext, and you never see the plaintext

`USERPASSWORD` is the only secret in these templates, and a `.vql` file lives in git. You
need no vault and no manual VQL: one command turns a password into the ciphertext, and the
password never passes through you, through a command argument, or through the transcript.

Ask the human to run it **in their own terminal input** — the `!` prefix — so the password
goes into a hidden prompt:

```bash
# verified: 9.5.1 (live, 2026-09-12)
! ${CLAUDE_PLUGIN_ROOT}/scripts/denodo secret encrypt --env dev
```

They can also pipe it from a password manager (`op read op://vault/db/password | …`). Either
way the answer carries one field, `encrypted` — never the password, not even inside a server
error — and the project file then reads `USERPASSWORD = '<that string>' ENCRYPTED`.

A wrong password encrypts just as happily, and the source answers later with its database's
own authentication error, not a format error — a source on a Virtual DataPort server,
`The username or password is incorrect`. *verified: 9.5.1 (live, 2026-09-12)*

**Never assemble `ENCRYPT_PASSWORD '<password>'` yourself** — neither with `-e` nor through
a file written by a heredoc or `printf`: both put the plaintext into a Bash argument, and Bash
arguments are kept in the session transcript.

- **The ciphertext is tied to the installation's encryption key.** `--env` names the
  environment the file goes to; another one means encrypting again, unless both share the key.
- **A source to the same database may already exist — then you need no password at all.**
  `vql desc --env dev --database <db> <existing_ds> --type "datasource jdbc" --vql`
  prints `USERNAME` and `USERPASSWORD '…' ENCRYPTED`, and both work verbatim in your own
  data source. The donor may live in **any database on that server** — look for it with
  `SELECT database_name, name FROM GET_ELEMENTS() WHERE type = 'datasource' AND subtype = 'jdbc'`
  and compare `DATABASEURI`. *verified: 9.5.1 (live, 2026-09-09)* — this is the first thing
  to try when the human says the password is not theirs to give.
- **A plaintext password is accepted too** (the server stores it encrypted regardless), so
  a `.vql` with a plaintext password *works* — which is exactly why it is easy to commit
  one by accident. Encrypt before writing the file, not after.
- If the human typed a production password into the chat, say so plainly once and suggest
  rotating it; the transcript keeps it.

**`CREATE OR REPLACE DATASOURCE` rewrites the credentials every time the file is applied,
and omitting the clause erases them.** Re-applying the same data source without
`USERPASSWORD` leaves it with no password at all — the next query fails with the source's
`no password was provided`. *verified: 9.5.1 (live, 2026-09-09)* A placeholder does the
same thing, more quietly. So: if you do not have the real value, do not run that statement
— say so, and leave the data source alone rather than replacing a working one.

## What you need before filling a template

"Connect our Oracle" is a complete request and an incomplete specification. Ask for what
is missing **in one message, with the defaults already proposed**, then build everything
else yourself. Three or four lines, not an interview:

> To connect it I need: the host (port 1521 unless you say otherwise), the service name or
> SID, the Oracle version, and the login of the account Denodo should read with. For its
> password I will give you one command to run in your own terminal: only the encrypted
> string reaches the file, and the password never reaches this chat.

| Slot | Where it comes from |
|---|---|
| JDBC host, port, database / service / SID | **the human** — then you assemble `DATABASEURI` from the table above; never ask for a JDBC URL |
| JDBC product and version | **the human** — it picks `DRIVERCLASSNAME`, `CLASSPATH` and the adapter |
| JDBC login | **the human**; it goes into the file |
| Any password | **the human**, through `secret encrypt` (**Passwords**), asked last |
| JDBC schema, tables, columns, types | **the server** — `GET_JDBC_DATASOURCE_TABLES` and `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW` after the source is up. Ask only which tables the human wants, and only if they did not name them — "every table of the schema" names them |
| File path | **the human** — and it is **server-side**: the file must be readable by the Denodo server, not by you |
| Delimiter, header, charset | the human, or a sample of the file; `,` + `HEADER = TRUE` + `UTF-8` is the common case |
| **Every column name of a file, in order** | the file header, verbatim and complete (**When you cannot see the file**) — never inferred from the columns the human wants |
| JSON shape | a sample of the document — nesting decides `REGISTER OF` / `ARRAY OF`, and you cannot guess it. Same three ways |
| Object names | the conventions in `/denodo:vql` — unless the human asked for something specific in this request (a prefix, a naming scheme). An explicit instruction wins over the convention; keep the type marker inside it (`acme_ds_store`, not `acme_store`) |
| Column types of a file source | your decision in `CREATE TABLE`: text unless the format is unambiguous; a wrong type costs `NULL`s, not an error |
| Database, folder | `/denodo:catalog`; folder and names from `/denodo:vql` |

Do not ask about caching, pooling, statistics or delegation options. They have defaults,
and they are in the references when the human raises them.
Do not ask a question whose answer is one read away: what exists (`LIST DATASOURCES <type>`),
how a similar object is written here (`vql desc … --vql`), whether the source answers
(`PING_DATA_SOURCE`).

## Reference

- `references/df.md` — `CREATE DATASOURCE DF` / `WRAPPER DF` for a local delimited file:
  delimiters, a directory of files, quoting, `NULLVALUE`, what the parser accepts in
  `OUTPUTSCHEMA`, typing.
- `references/json.md` — `CREATE DATASOURCE JSON` / `WRAPPER JSON` for a local JSON file:
  `TUPLEROOT`, nested registers and arrays, `CREATE TYPE`, reading registers.
- `references/jdbc.md` — `CREATE DATASOURCE JDBC` / `WRAPPER JDBC` over tables: the driver
  directory names on the server, adapters, the connection pool, a wrapper by hand,
  introspection procedures.
- `references/base-view.md` — full `CREATE TABLE`: search methods and constraints, cache
  clauses, primary keys, tags, indexes, `ONSCHEMACHANGE`, VQL types.

## Verify

`ok: true` on the `CREATE` statements proves the parser was happy and nothing else. Read
the data back, every time:

| Check | How | What a failure looks like |
|---|---|---|
| Rows arrive | `vql run --env dev --database <db> -e "SELECT COUNT(*) FROM <bv>"` | `0` — a DF wrapper missing columns, or an empty/unreachable file |
| The count is *right* | compare with what the human expects the source to hold | a JSON wrapper without the `REGISTER OF` wrapper inflates rows through nested arrays |
| **A filter filters** | `SELECT COUNT(*) FROM <bv> WHERE <key> = '<one value>'`, and one on a register subfield if there is one; for a number, compare with `WHERE <key> + 0 = <value>`, which Denodo evaluates itself | the whole table — a JSON base view without the template's `CONSTRAINTS … NOS ZERO ()`; or a different count from the two forms — a DF base view narrower than its wrapper, filtering another column. Every consumer's `WHERE` is then wrong, and nothing else in this table notices |
| Values are values | `SELECT * FROM <bv>` with `--max-rows 5`, look at every column | a whole column of `NULL` = the type in `CREATE TABLE` does not match the data (`cust_id:int` over `C-10472`) |
| Text values have no padding | the same read-back — look at where each string **ends**, not just at what it says | `"0-500          "` — an export padded to a fixed width. Nothing fails, and then every `WHERE col = '0-500'` and every `GROUP BY` a consumer writes is wrong. `TRIM` it in the view above and say so in the `DESCRIPTION`; `NULLVALUE ''` (text columns only) handles the empty-string half of the same problem |
| Schema is what you wrote | `vql desc --env dev --database <db> <bv>` | missing or extra columns |
| A JDBC source can be reached | `PING_DATA_SOURCE`, above | `DOWN` and its cause (above) |
| The folder exists before you use it | `SELECT name, folder FROM GET_ELEMENTS() WHERE input_database_name = '<db>' AND type = 'folder'` — `LIST FOLDERS` does not exist |  `Syntax error … near 'FOLDERS'` |
| The base view is in the catalog | `SELECT name, subtype, folder FROM GET_ELEMENTS() WHERE input_database_name = '<db>' AND type = 'view'` | **not** `LIST VIEWS`: it lists derived views only and answers an empty set for a database full of base views — *verified: 9.5.1 (live, 2026-09-09)*. `LIST TABLES` does not exist |
| What already exists | `LIST DATASOURCES DF` / `JSON` / `JDBC`, `LIST WRAPPERS DF`, `LIST TYPES` — the **type is mandatory** on `LIST DATASOURCES` | — |

`GET_ELEMENTS()` takes its filters as `input_database_name` / `input_type` and returns
`database_name`, `name`, `type`, `subtype`, `folder` — the input columns carry the `input_`
prefix, the output ones do not.

A detail of the three sources no template covers: read an existing object's `vql desc …
--type "<type>" --vql` — for a file, its base view (**When you cannot see the file**).
Another kind of source stays Design Studio's, whatever a donor shows.

## Common mistakes

Each row is a named fix. A failure that is not here, or that survives its fix, ends the
attempt: **When a template does not work straight away**, above.

| You wrote | What happens | Fix |
|---|---|---|
| DF `OUTPUTSCHEMA` with the columns the human asked for | `CREATE` succeeds, `SELECT` returns **0 rows** | list every column of the file; narrow in a derived view |
| DF `OUTPUTSCHEMA` with the right count but the wrong order | rows arrive with values under the wrong names | the mapping is positional — reorder to match the header |
| DF source without `IGNOREMATCHINGERRORS = FALSE` | schema mismatches are dropped row by row, silently | add it; the mismatch becomes `[DF ROUTE] [PARSE_ERROR] Invalid line found at data file` |
| `Different number of columns` while the wrapper's count and order already match the header | the records do not split one per line on the delimiter — a line break inside quoted values, or a delimiter inside an unquoted one | nothing to fix in VQL: stop, Design Studio (**When a template does not work straight away**) |
| `FOLDER = '/x'` where `/x` does not exist | `Error creating data source: destination folder '/x' not found` | create the folder first (`/denodo:catalog`) |
| DF `OUTPUTSCHEMA` with types (`: 'java.util.Date'`) | `Syntax error … near '''` | DF wrappers take `name = 'mapping'` only, plus `(OPT)` / `NULLVALUE` |
| Wrapper with no `OUTPUTSCHEMA` at all | creates, then `SELECT` fails: DF `[NO_CREATED_ACCESS] Unable to create xml raw access`, JSON `[JSON WRAPPER] [PROCESSING]` | the server does not introspect files — write the schema |
| JSON `OUTPUTSCHEMA` as a flat field list | `CREATE` succeeds, row count is wrong (arrays multiply rows) | wrap the fields in `<name> = 'JSONFile' : REGISTER OF ( … )` |
| `CREATE TABLE … ( lines:ARRAY OF (…) )` | `Syntax error` | declare `CREATE OR REPLACE TYPE` first, use its name |
| JSON base view without `CONSTRAINTS` | `CREATE` succeeds, `SELECT` works, and every `WHERE` on it returns all rows | the template's block: `ADD <column> NOS ZERO ()` for every column and every register subfield |
| DF base view with fewer columns than its wrapper | `CREATE` succeeds, `SELECT` works, and `WHERE col = x` returns the rows where another column is `x` | list every wrapper column, in its order, and narrow in a derived view — or `ADD <column> NOS ZERO ()` for each column of the base view |
| `CACHE OFF ADD SEARCHMETHOD` | `Syntax error … near 'ADD'` | `CACHE OFF TIMETOLIVEINCACHE DEFAULT ADD SEARCHMETHOD` |
| `cust_id:int` over text keys | column comes back all `NULL`, no error | fix the type in `CREATE TABLE`, re-apply |
| `DATABASENAME`/`DATABASEVERSION` without `CLASSPATH` | `error creating new data source: Cannot invoke "java.util.List.size()"` | add `CLASSPATH = '<driver directory>'` |
| JDBC clauses in a different order | `Syntax error` naming a clause that is fine | restore the template's order; the named token is where the parser stopped |
| `SELECT shipping.country` | `Field not found 'shipping.country' in view 'shipping'` | `(shipping).country` |
| `LIST DATASOURCES` | `Syntax error … near 'DATASOURCES'` | the type is mandatory: `LIST DATASOURCES DF` |
| `SELECT` from a JDBC base view whose source is unreachable | `[JDBC ROUTE] [CONNECTION_ERROR]` in `raw` | expected without the database; the objects are still correct — verify with `PING_DATA_SOURCE` |
| Relative path in `ROUTE LOCAL` | `[DF ROUTE] [PARSE_ERROR] … Error getting input Stream` | absolute path, on the server's filesystem |

Dropping a source takes its wrappers and base views with it (`CASCADE`), and that is the
human's call — `/denodo:vql`. Re-applying a source your project's own file declares is the
normal loop. A source no file of yours declares — made in Design Studio, or another team's — is
the human's yes before any `CREATE OR REPLACE`: your text replaces its whole configuration, the
stored password included, and a base view re-declared the same way loses its cache settings
(`references/base-view.md`, "Cache, swap, MPP").
