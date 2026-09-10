# `CREATE VIEW` in full

Everything `/denodo:views` leaves out of the minimal template. The SELECT itself —
functions, expressions, joins, the Denodo dialect — is `/denodo:query`.

## Grammar (documentation 9.5)

```
CREATE [ OR REPLACE ] VIEW [<database>.]<name>
    [ FOLDER = <literal> ]
    [ DESCRIPTION = <literal> ]
    [ PRIMARY KEY ( '<field>' [, '<field>' ]* ) ]
    [ TAGS ( <tag> [, <tag> ]* ) ]
    [ ( <field properties> [, <field properties> ]* ) ]
    [ CHECK_INDIRECT_ACCESS { ON | OFF } ]
    AS <select>
    [ USING PARAMETERS ( <parameter> [, <parameter> ]* ) ]
    [ ORDER BY <field> [ ASC | DESC ] [, … ] ]
    [ OFFSET <number> [ ROW | ROWS ] ]
    [ FETCH { FIRST | NEXT } [ <number> ] { ROW | ROWS } ONLY | LIMIT [ <number> ] ]
    [ WITH [ CASCADED | LOCAL ] CHECK OPTION ]
    [ CONTEXT ( <context information> [, … ] ) ]

<field properties> ::= <name> ( <property list> ) [ TAGS ( <tag> [, … ] ) ]
<parameter>       ::= <name> [ MULTIVALUED ] : <type> [ <default> | ( <default> [, … ] ) ]
```

The order is not advisory: every optional clause before `AS` must appear in the position
above. `TAGS` after the field properties is `Syntax error … near 'TAGS'` —
*verified: 9.5.1 (стенд, 2026-09-10)*.

## Field properties

The parenthesised list after `TAGS` documents individual columns. It carries the column
description that Data Marketplace and Design Studio show, and the per-column tags:

```sql
-- verified: 9.5.1 (стенд, 2026-09-10)
CREATE OR REPLACE VIEW customer_contact
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'One row per customer, contact details only.'
    PRIMARY KEY ( 'customer_id' )
    TAGS ( gdpr )
    ( customer_id ( description = 'Surrogate key of the customer' ),
      email       ( description = 'Primary contact address' ) TAGS ( pii ) )
    AS SELECT cust_id AS customer_id, email AS email FROM bv_crm_customers;
```

Only the columns you want to annotate need listing. The tags must already exist
(`/denodo:catalog`), and assignments are visible in `GET_VIEW_TAGS()`.

## Parameterised views

`USING PARAMETERS` gives the view mandatory inputs. The parameter is referenced **by name,
directly** in the SELECT — not through `GETVAR` — and it appears as a column of the result:

```sql
-- verified: 9.5.1 (стенд, 2026-09-10)
CREATE OR REPLACE VIEW household_in_band
    FOLDER = '/02 - integration'
    AS SELECT household_sk, income_band_sk, buy_potential
       FROM iv_household_income
       WHERE income_band_sk = band
    USING PARAMETERS ( band : int );
```

Querying it without a value is
`No search methods ready to be run. The following fields are obligatory: household_in_band.band`
— *verified: 9.5.1 (стенд, 2026-09-10)*. That is not a bug to fix, it is what the clause
means; `SELECT … WHERE band = 3` is how the view is used. A default after the type makes
the parameter optional and `MULTIVALUED` takes a list of values — both
*unverified: только по документации 9.5*.

A parameterised view is the wrong tool for a filter that a consumer could write themselves
in a `WHERE`. It earns its place when the parameter has to reach the source — a mandatory
search field of a web service, a partition key — because a plain `WHERE` over a full scan
would be the alternative.

## Clauses that are rarely worth using

| Clause | What it does | Note |
|---|---|---|
| `ORDER BY … LIMIT n` | freezes an ordering and a row cap into the view | *verified: 9.5.1 (стенд, 2026-09-10)*. A consumer's own `ORDER BY` overrides the ordering but not the cap; a "top 100" view surprises whoever filters it |
| `OFFSET` / `FETCH FIRST … ROWS ONLY` | the SQL-standard spelling of the same thing | same caveat |
| `WITH CHECK OPTION` | rejects `INSERT`/`UPDATE` through the view that would not satisfy its own `WHERE` | *unverified: только по документации 9.5*. Only meaningful for a writable view |
| `CONTEXT ( … )` | pins execution options into the view definition | *verified: 9.5.1 (стенд, 2026-09-10)*. Design Studio emits `CONTEXT ('i18n' = 'es_euro')` on views it generates; do not copy it into hand-written VQL without a reason |
| `CHECK_INDIRECT_ACCESS ON` | makes the server check the `INDIRECT_ACCESS` privilege for this view | *verified: 9.5.1 (стенд, 2026-09-10)*. Privileges are outside v1 |

## `ALTER VIEW`: what it cannot do

**`ALTER VIEW` cannot change the SELECT of a derived view.** There is no
`ALTER VIEW … AS SELECT`; changing what a view computes means `CREATE OR REPLACE VIEW`
with the whole statement, which is why the template is the whole statement in a file.

What `ALTER VIEW` does change: cache configuration (`CACHE`, `TIMETOLIVEINCACHE`,
`CACHE_TABLE_NAME`, `ONSCHEMACHANGE`), swapping (`SWAP`, `SWAPSIZE`, `MAXRESULTSIZE`),
`DECLARE CACHE INDEX`, `DATAMOVEMENTPLAN`, the primary key, `DELEGATESTATSQUERY`,
`CHECK_INDIRECT_ACCESS`, `LAYOUT`, and the name:

```sql
-- verified: 9.5.1 (стенд, 2026-09-10)
ALTER VIEW household_in_band RENAME household_by_band;
```

A rename breaks every dependant that names the view, silently, the same way a renamed
column does — `USED_BY()` first.

`LAYOUT (…)` is Design Studio's canvas geometry. It shows up in `DESC VQL` output and
means nothing to the server; leave it out of hand-written files and do not treat its
absence as a difference.

## `DROP VIEW`

```
DROP { VIEW | INTERFACE VIEW | TABLE } [ IF EXISTS ] <name> [ CASCADE ]
```

- `DROP VIEW` works on interface views too — the keyword does not have to match the
  subtype — *verified: 9.5.1 (стенд, 2026-09-10)*. `DROP TABLE` is the one for base views.
- With dependants and no `CASCADE`:
  `error removing view: There are some elements that depend on this one`.
- `CASCADE` removes the dependants as well. It makes the drop shorter, not safer: run
  `USED_BY()` and show the human the list before asking (`/denodo:vql`).

## Reading a view back

| Want | Statement |
|---|---|
| Schema and types | `vql desc --env lab --database <db> <view>` |
| The exact VQL, including everything underneath | `vql desc --env lab --database <db> <view> --vql` — one row holding the whole dependency chain. The best syntax reference on any server, and **not something to apply as it stands**: it opens with `DROP … CASCADE` for every object in the chain |
| Health | `SELECT name, view_type, view_status FROM GET_VIEWS() WHERE input_database_name = '<db>'` |
| Dependants | `SELECT view_name, used_by_name, depth FROM USED_BY() WHERE input_view_database_name = '<db>' AND input_view_name = '<view>'` |
| Dependencies (downwards) | `SELECT * FROM VIEW_DEPENDENCIES() WHERE input_view_database_name = '<db>' AND input_view_name = '<view>'` — note `input_view_database_name`, not `input_database_name` |
| Which source column feeds which output column | `COLUMN_DEPENDENCIES()` |
