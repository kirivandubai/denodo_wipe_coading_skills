# Base views (`CREATE TABLE`) — full syntax

A base view is the object every other Denodo view reads. It has a schema, a folder, and at
least one **search method** binding it to a wrapper. Source of the grammar: VQL Guide 9.5,
*Creating a Base View*. Facts marked `verified:` were run on a 9.5.1 server.

## CREATE TABLE

```sql
CREATE [ OR REPLACE ] TABLE [<database>.]<name> I18N <map>
    ( <field> [, <field> ]* )
    [ FOLDER = <literal> ]
    [ DESCRIPTION = <literal> ]
    [ [ CONSTRAINT <literal> ] PRIMARY KEY ( <literal> [, … ] ) ]
    [ TAGS ( <tag> [, <tag> ]* ) ]
    [ CACHE { OFF | PARTIAL [ EXACT ] [ PRELOAD ] | FULL [ [ FORCE ] { NO_STATUS | WITH_STATUS } ]
            | INVALIDATE [ ON CASCADE ] [ NOATOMIC [ INVALIDATEBLOCKSIZE <int> ] ] [ WHERE <cond> ] } ]
    [ BATCHSIZEINCACHE { <int> | DEFAULT } ]
    [ TIMETOLIVEINCACHE { <seconds> | DEFAULT | NOEXPIRE } ]
    [ ONSCHEMACHANGE { RECREATE | APPEND | SYNCHRONIZE } [ { INCREMENTAL_LOAD | INCREMENTAL_REFRESH } ] ]
    [ CACHE_TABLE_NAME <literal> ]
    [ CREATE_TABLE_TEMPLATES ( [ CACHE = <template>, ] [ REMOTE_TABLE = <template> ] ) ]
    [ SWAP { ON | OFF | DEFAULT } ] [ SWAPSIZE <mb> ] [ MAXRESULTSIZE <mb> ]
    [ <search method> ]*
    [ <index clause> ]*
    [ DELEGATESTATSQUERY = <boolean> ]
    [ { SMART_ONLY | SMART_THEN_ATSOURCE_THROUGH_VDP | ATSOURCE_THROUGH_VDP_ONLY } ]
    [ CHECK_INDIRECT_ACCESS { ON | OFF } ]

<field> ::= <name>:<type> [ ( <property> [ = <value> ] [, … ] ) ] [ TAGS ( <tag>, … ) ]

<search method> ::=
    ADD SEARCHMETHOD <name> (
        [ I18N <map> ]
        [ CONSTRAINTS ( <constraint> [ <constraint> ]* ) ]
        [ OUTPUTLIST ( <field> [, <field> ]* ) ]
        [ WRAPPER ( <wrapper type> <wrapper name> )
          ALTERNATIVE_WRAPPERS ( JDBC <wrapper name> [, JDBC <wrapper name> ]* ) ]
    )

<index clause> ::=
    DECLARE { CACHE | VIEW } [ CLUSTER | HASH | OTHER ] INDEX <name> ON ( <field> [ ASC | DESC ], … )
  | DELETE { CACHE | VIEW } INDEX <name>
```

## The minimum that works

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CREATE OR REPLACE TABLE bv_crm_customers I18N us_pst (
        cust_id:text,
        created_dt:localdate
    )
    FOLDER = '/01 - connectivity'
    CACHE OFF
    TIMETOLIVEINCACHE DEFAULT
    ADD SEARCHMETHOD wr_crm_customers (
        OUTPUTLIST ( cust_id, created_dt )
        WRAPPER (df wr_crm_customers)
    );
```

| Element | Required? |
|---|---|
| `I18N <map>` after the name | **yes** — the parser needs it, and it decides the zone and language dates are read in. The one the database's other base views declare, or the project's; with nothing to follow, `GETSESSION('i18n')` of the connected database. `LIST MAPS I18N` lists them |
| `CACHE OFF` | no, but keep it explicit |
| `TIMETOLIVEINCACHE DEFAULT` | **yes when `CACHE OFF` is followed by `ADD SEARCHMETHOD`** — otherwise `Syntax error … near 'ADD'`. *verified: 9.5.1 (live, 2026-09-09)* |
| `ADD SEARCHMETHOD … WRAPPER (…)` | **yes** — without it the view has no source |
| `I18N` *inside* the search method | no |
| `CONSTRAINTS ( … )` | **for JSON, yes**: `ADD <field> NOS ZERO ()` for every column and every register subfield (`shipping.country`). Left out, the server fills in `ADD <field> (any) OPT ANY` for every wrapper type; the DF and JDBC wrappers then filter what they are handed, the JSON wrapper ignores it, and every `WHERE` on a JSON base view returns all rows without an error. For JDBC it can be left out, and for DF when the base view lists the wrapper's columns in the wrapper's order. **A DF base view with fewer columns needs it** (`NOS ZERO ()` for each of its columns): without it an equality is handed to the wrapper by position and filters another column of the file. *verified: 9.5.1 (live, 2026-09-30)* |
| `OUTPUTLIST` | in practice yes — it is the list of fields the search method returns |
| The wrapper type in `WRAPPER (…)` | **yes**, and it must match: `df`, `json`, `jdbc` |

The search method's name is conventionally the wrapper's name; it is a label, not a
reference — the reference is `WRAPPER (<type> <name>)`.

## Types

`LIST TYPES` on a 9.5.1 server:

```
blob boolean date decimal double float int intervaldaysecond intervalyearmonth
localdate long text time timestamp timestamptz xml
vector<double> vector<float> vector<int> vector<long>
```

plus every user-defined type (`CREATE TYPE … AS REGISTER OF (…)` / `ARRAY OF …`) —
`references/json.md`.

- `date` is deprecated (a timestamp with a zone offset): declare `localdate`, `timestamp` or
  `timestamptz`.
- The base view's declared type is what Denodo *parses the source value into*. Over a text
  file, `created_dt:localdate` on `2021-04-12` works; a type that does not match returns `NULL`
  for that column, with **no error**. *verified: 9.5.1 (live, 2026-10-07)*
- Over JDBC, introspection picks the type from the source: Oracle `NUMBER(10)` → `long`,
  `NVARCHAR2` → `text`, PostgreSQL `date` → `localdate`, SQL Server `bigint` → `long`.
  *verified: 9.5.1 (live, 2026-09-09)*
- `bigint` is not a VQL type — it is `long`. Field properties from introspection
  (`sourcetypename`, `sourcetypesize`, …) are informative and can be dropped.

## Primary keys, tags, indexes

```sql
-- verified: 9.5.1 (live, 2026-10-07) — the key and the tags after the field list, the index after the search method
    CONSTRAINT 'pk_customer' PRIMARY KEY ( 'cust_id' )
    TAGS ( pii )
    CACHE OFF
    TIMETOLIVEINCACHE DEFAULT
    ADD SEARCHMETHOD wr_crm_customers (
        OUTPUTLIST ( cust_id, country )
        WRAPPER (df wr_crm_customers)
    )
    DECLARE VIEW INDEX idx_customer_country ON ( country ASC );
```

`DECLARE VIEW INDEX` before `CACHE` is `Syntax error … near 'DECLARE'`: an index is declared
after the search methods, where `DESC VQL` writes it too.

- The primary key changes execution plans (it tells the optimizer rows are unique) — declare
  it when the source really guarantees it, not because it looks tidy.
- `TAGS ( … )` attaches existing VDP tags at creation; the tags themselves are
  `/denodo:catalog`.
- View indexes are hints for the optimizer over a source that has them; cache indexes are a
  cache setting, made in Design Studio (`/denodo:cache`).

## Cache, swap, MPP

A full cache on a base view is `CACHE FULL WITH_STATUS` in place of `CACHE OFF` in this
statement — `/denodo:cache` has what it does and how it is loaded. It lives here, not in an
`ALTER`: re-applying this file with `CACHE OFF` switches an existing cache off without a
word, and the loaded rows come back stale if it is ever switched on again — *verified: 9.5.1
(live, 2026-09-30)*. Read `DESC VQL` before re-applying a base view file someone else may
have cached.

`CACHE PARTIAL`, `BATCHSIZEINCACHE`, `CACHE_TABLE_NAME`, `CREATE_TABLE_TEMPLATES`,
`SWAP`, `MAXRESULTSIZE`, `ONSCHEMACHANGE`, `DELEGATESTATSQUERY` and the
`SMART_ONLY` / `SMART_THEN_ATSOURCE_THROUGH_VDP` / `ATSOURCE_THROUGH_VDP_ONLY` group are
performance and lifecycle features. They are out of scope: get the view returning
correct rows first. When the source's schema drifts under a base view, the base view is
refreshed in Design Studio (**Source Refresh**, `SKILL.md`), not rewritten by hand.

## Changing and dropping

- `ALTER TABLE` exists for base views but is an `ALTER`: it needs the human's yes
  (`/denodo:vql`). Re-applying the file with `CREATE OR REPLACE` is the normal path, and it
  keeps dependent views working as long as the change is additive.
- `DROP VIEW <name>` or `DROP TABLE <name>` removes a base view; `DESC TABLE` does not
  exist — it is `DESC VIEW` (both measured on a 9.5.1 server). Dropping the data source with
  `CASCADE` takes wrappers and base views with it.
- **`LIST VIEWS` does not list base views** — it answers with the derived ones only, and
  returns an empty set in a database that holds nothing but base views. `LIST TABLES` does
  not exist. The listing that shows them is
  `SELECT name, subtype, folder FROM GET_ELEMENTS() WHERE input_database_name = '<db>' AND
  type = 'view'` (`subtype = 'base'` picks the base views).
  *verified: 9.5.1 (live, 2026-09-09)*
- Before a column of an existing base view is dropped or retyped, find who uses it:
  `SELECT view_name, used_by_database_name, used_by_name, depth FROM USED_BY() WHERE
  input_view_database_name = '<db>' AND input_view_name = '<bv>'` (`/denodo:views`, *Before
  a column changes*). `GET_PUBLIC_VIEW_DEPENDENCIES()` answers the opposite question — what
  the view is built on: for a base view, only its data source (measured on a 9.5.1 server).
