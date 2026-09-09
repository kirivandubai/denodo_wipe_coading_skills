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
-- verified: 9.5.1 (стенд, 2026-09-09)
CREATE OR REPLACE TABLE bv_crm_customers I18N us_pst (
        cust_id:text,
        created_dt:date
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
| `I18N <map>` after the name | **yes** — the parser needs it. `us_pst` unless the project says otherwise; `LIST MAPS I18N` lists all 76 |
| `CACHE OFF` | no, but explicit is better than a server default that may differ per environment |
| `TIMETOLIVEINCACHE DEFAULT` | **yes when `CACHE OFF` is followed by `ADD SEARCHMETHOD`** — otherwise `Syntax error … near 'ADD'`. *verified: 9.5.1 (стенд, 2026-09-09)* |
| `ADD SEARCHMETHOD … WRAPPER (…)` | **yes** — without it the view has no source |
| `I18N` *inside* the search method | no |
| `CONSTRAINTS ( … )` | no — the server generates it in `DESC VQL` (`ADD <field> (any) OPT ANY` for DF/JDBC, `ADD <field> NOS ZERO ()` for JSON), and views created without it query normally. *verified: 9.5.1 (стенд, 2026-09-09)* |
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

- The base view's declared type is what Denodo *parses the source value into*. Over a text
  file, `created_dt:date` on `2021-04-12` works; a type that does not match returns `NULL`
  for that column, with **no error**. *verified: 9.5.1 (стенд, 2026-09-09)*
- Over JDBC, introspection picks the type from the source: Oracle `NUMBER(10)` → `long`,
  `NVARCHAR2` → `text`, PostgreSQL `date` → `localdate`, SQL Server `bigint` → `long`.
  *verified: 9.5.1 (стенд, 2026-09-09)*
- `bigint` is not a VQL type — it is `long`. Field properties from introspection
  (`sourcetypename`, `sourcetypesize`, …) are informative and can be dropped.

## Primary keys, tags, indexes

```sql
CONSTRAINT 'pk_customer' PRIMARY KEY ( 'cust_id' )
TAGS ( pii )
DECLARE VIEW INDEX idx_customer_country ON ( country ASC )
```

- The primary key changes execution plans (it tells the optimizer rows are unique) — declare
  it when the source really guarantees it, not because it looks tidy.
- `TAGS ( … )` attaches existing VDP tags at creation; the tags themselves are
  `/denodo:catalog`.
- View indexes are hints for the optimizer over a source that has them; cache indexes
  belong to cache work, outside v1.

## Cache, swap, MPP

`CACHE PARTIAL/FULL`, `BATCHSIZEINCACHE`, `CACHE_TABLE_NAME`, `CREATE_TABLE_TEMPLATES`,
`SWAP`, `MAXRESULTSIZE`, `ONSCHEMACHANGE`, `DELEGATESTATSQUERY` and the
`SMART_ONLY` / `SMART_THEN_ATSOURCE_THROUGH_VDP` / `ATSOURCE_THROUGH_VDP_ONLY` group are
performance and lifecycle features. They are out of v1 scope: get the view returning
correct rows first. `ONSCHEMACHANGE` is the one worth remembering — it decides what
happens when the source's schema drifts.

## Changing and dropping

- `ALTER TABLE` exists for base views but is an `ALTER`: it needs the human's yes
  (`/denodo:vql`). Re-applying the file with `CREATE OR REPLACE` is the normal path, and it
  keeps dependent views working as long as the change is additive.
- `DROP VIEW <name>` removes a base view (there is no `DROP TABLE` for it — and `DESC
  TABLE` does not exist either; it is `DESC VIEW`). Dropping the data source with `CASCADE`
  takes wrappers and base views with it.
- **`LIST VIEWS` does not list base views** — it answers with the derived ones only, and
  returns an empty set in a database that holds nothing but base views. `LIST TABLES` does
  not exist. The listing that shows them is
  `SELECT name, subtype, folder FROM GET_ELEMENTS() WHERE input_database_name = '<db>' AND
  type = 'view'` (`subtype` is `base` / `derived` / `interface`).
  *verified: 9.5.1 (стенд, 2026-09-09)*
- Replacing a base view whose column a derived view selects, with that column removed or
  retyped, breaks the dependent view. Check dependents first:
  `SELECT view_name, dependency_name, dependency_type, depth FROM
  GET_PUBLIC_VIEW_DEPENDENCIES() WHERE input_view_database_name = '<db>' AND
  input_view_name = '<bv>'` — the parameter is `input_view_database_name`, not
  `input_database_name`. *verified: 9.5.1 (стенд, 2026-09-09)*
