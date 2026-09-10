---
name: views
description: Use when building on top of views that already exist in Denodo 9.5 — a derived view over base views (CREATE VIEW … FOLDER … AS SELECT, a join, an aggregate, a mart, a parameterised view), an interface view used as a stable contract whose implementation can be swapped (CREATE INTERFACE VIEW … SET IMPLEMENTATION), or an association that records how two views relate (CREATE ASSOCIATION … REFERENTIAL CONSTRAINT … ENDPOINT … ADD MAPPING). Also for changing a view that other views depend on, for "make a mart", "expose this as a data product", "link these two views", and for a view that was created without an error but fails on SELECT or turns up INVALID. Not for connecting a source or making base views — that is /denodo:datasources; not for databases, folders or VDP tags — /denodo:catalog.
---

# Derived views, interface views and associations

Three objects, all built **on top of views that already exist**: the derived view that
transforms, the interface view that publishes a fixed contract, and the association that
records how two views relate. Order in the chain: **base view → derived view → interface
view → association**.

Sources, wrappers and base views are `/denodo:datasources`; databases, folders and VDP
tags are `/denodo:catalog`; the SELECT inside `AS` — expressions, functions, dialect — is
`/denodo:query`. Applying files is `/denodo:execute`, and the working loop, the naming
defaults and the safety rule are `/denodo:vql`.

**The dangerous part of this skill is what happens after a successful statement.** All
three objects can be accepted by the server and be broken, and all three break *other
people's* objects the same way: the DDL returns success, and the failure surfaces later,
on someone's `SELECT`. The Verify section is not optional.

## Templates

Each template is one file, applied whole, `CREATE OR REPLACE` throughout — re-applying
after a fix is safe.

### Derived view

```sql
-- verified: 9.5.1 (стенд, 2026-09-10)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW iv_household_income
    FOLDER = '/02 - integration'
    DESCRIPTION = 'Households enriched with the bounds of their income band. One row per household.'
    PRIMARY KEY ( 'household_sk' )
    AS SELECT hd.hd_demo_sk         AS household_sk,
              hd.hd_income_band_sk  AS income_band_sk,
              hd.hd_buy_potential   AS buy_potential,
              hd.hd_dep_count       AS dependents,
              hd.hd_vehicle_count   AS vehicles,
              ib.ib_lower_bound     AS income_lower_bound,
              ib.ib_upper_bound     AS income_upper_bound
       FROM bv_household_demographics hd
            INNER JOIN bv_income_band ib
            ON hd.hd_income_band_sk = ib.ib_income_band_sk;

CREATE OR REPLACE VIEW household_income_by_band
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Households per income band. One row per income band.'
    AS SELECT income_band_sk            AS income_band_sk,
              income_lower_bound        AS income_lower_bound,
              income_upper_bound        AS income_upper_bound,
              COUNT(household_sk)       AS household_count,
              ROUND(AVG(dependents), 2) AS avg_dependents,
              ROUND(AVG(vehicles), 2)   AS avg_vehicles
       FROM iv_household_income
       GROUP BY income_band_sk, income_lower_bound, income_upper_bound;
```

Clause order: `FOLDER` → `DESCRIPTION` → `PRIMARY KEY` → `TAGS` → `( field properties )` →
`AS SELECT`. Everything before `AS` is optional; put `FOLDER` in anyway, because a view
without one lands at the root of the database.

- **One view per grain.** The join lives in `/02 - integration` at the row grain of the
  entity; the aggregate is a second view in `/03 - business entities`. Stacking `GROUP BY`
  on top of the join in a single statement works, but the join is then not reusable and
  the mart cannot be checked against it.
- **Naming.** In `/02 - integration` the prefix is `iv_` and the name says what the view
  does; in `/03 - business entities` there is no prefix and the name says what the
  consumer gets (`household_income_by_band`). `iv_` means *integration view*, not
  *interface view* — the interface view is the one below, and it is the one that gets the
  bare business name.
- `AVG` over an integer already returns a double — *verified: 9.5.1 (стенд, 2026-09-10)*.
  Casting it first is not a fix for anything and `AVG(TO_DECIMAL(x))` under a `GROUP BY`
  is rejected outright (see Common mistakes).
- Attaching tags: `TAGS ( pii )` before the field properties for the whole view,
  `( email ( description = '…' ) TAGS ( pii ) )` for one column — both
  *verified: 9.5.1 (стенд, 2026-09-10)*. The tag itself is `/denodo:catalog` and must
  exist first.

### Interface view — a contract you can re-implement

```sql
-- verified: 9.5.1 (стенд, 2026-09-10)
CREATE OR REPLACE INTERFACE VIEW household_income (
        household_sk:int,
        income_band_sk:int,
        buy_potential:text,
        dependents:int,
        vehicles:int,
        income_lower_bound:int,
        income_upper_bound:int
    )
    SET IMPLEMENTATION iv_household_income
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Household income data product. Name and schema are the contract; the implementation behind them may change.';
```

**Clause order is fixed and unforgiving: `( fields )` → `SET IMPLEMENTATION` → `FOLDER` →
`DESCRIPTION`.** `SET IMPLEMENTATION` after `FOLDER` is
`Syntax error: Exception parsing query near 'SET'` — *verified: 9.5.1 (стенд, 2026-09-10)*.

Use an interface view when the *name and schema* have to survive a change of the thing
underneath: a published data product, a consumer outside the team, a top-down design where
the contract is agreed before the implementation exists. If nothing has to survive, a
derived view is the simpler object.

**Swapping the implementation** is a re-apply of the same file with a different view after
`SET IMPLEMENTATION`. Nothing the consumer sees changes. When the new implementation names
its columns differently, map them — the field list stays as it was:

```sql
-- verified: 9.5.1 (стенд, 2026-09-10)
    SET IMPLEMENTATION iv_household_income_v2 (
        household_sk       = household_key,
        income_band_sk     = band_key,
        buy_potential      = buy_potential,
        dependents         = dependent_count,
        vehicles           = vehicle_count,
        income_lower_bound = band_lower,
        income_upper_bound = band_upper )
```

Left of `=` is the interface field, right is the implementation's column.
`ALTER INTERFACE VIEW <name> SET IMPLEMENTATION <view> ( … )` does the same thing in
place, and it is what you use when the contract was created ahead of its implementation —
but it is an `ALTER` of an existing object, so the human confirms it first
(`/denodo:vql`). Re-applying the file is the default.

### Association — the relationship, recorded

```sql
-- verified: 9.5.1 (стенд, 2026-09-10)
CREATE OR REPLACE ASSOCIATION a_income_band_household REFERENTIAL CONSTRAINT
    FOLDER = '/06 - associations'
    ENDPOINT income_band bv_household_demographics (0,*)
    ENDPOINT households  bv_income_band PRINCIPAL (1)
    ADD MAPPING hd_income_band_sk = ib_income_band_sk;
```

There is **no `CREATE ASSOCIATION` page in the public VQL Guide 9.5** — the documentation
covers the Design Studio dialog only. This template comes from the server itself. Read one
endpoint like this:

```
ENDPOINT <role name>  <view>  [PRINCIPAL]  (<multiplicity>)
            │            │         │             │
            │            │         │             └─ rows of THIS view per one row of the other
            │            │         └─ this view is the parent of the foreign key
            │            └─ the view at this endpoint
            └─ what you reach FROM the other side — i.e. the other view's name
```

The first identifier is the **role name of the other end, not an alias for this view** —
the endpoint carrying `bv_household_demographics` is named `income_band`, because a
household leads you to its band. Above: a band has zero or more households `(0,*)`, a
household has exactly one band `(1)`.

- **`REFERENTIAL CONSTRAINT` is what makes it a foreign key.** Without it, `PRINCIPAL` is
  accepted and silently ignored, and JDBC/ODBC clients never see the relationship —
  *verified: 9.5.1 (стенд, 2026-09-10)*. Leave it out only for a link that is genuinely
  not a foreign key.
- The `PRINCIPAL` endpoint must be `(1)` or `(0,1)`. Two `PRINCIPAL`s is
  `In a 1:N association, the principal endpoint must have multiplicity 1 or 0..1`.
- Multiplicity is written `(0,*)`, `(1)`, `(0,1)`, `(1,*)`, `(*)`. The `0..1` from the
  documentation is UI notation and a syntax error in VQL.
- In `ADD MAPPING`, the left column belongs to the **first** endpoint's view and the right
  to the second. Several mappings = several `ADD MAPPING` lines for a composite key.
- **Role names are unique per view**: a second association reusing a role name on the same
  view is `The association endpoint role name 'x' already exists for the selected view`.
  Name roles after the other view and the clash tells you something real.
- Endpoints may be interface views, base views, derived views, and may live in different
  databases (`ENDPOINT band other_db.bv_income_band …`) — *verified: 9.5.1 (стенд,
  2026-09-10)*. An association does not make joins implicit: a query still writes its own
  `ON`. What it changes is the catalog, and — for a `REFERENTIAL CONSTRAINT` — the foreign
  keys the JDBC and ODBC drivers report to clients.
- A role precondition (which rows show the link in `SELECT_NAVIGATIONAL` and the RESTful
  service) is `PRECONDITION ( <condition> )` **after** the multiplicity, and the condition
  is parenthesised, not quoted. No public documentation covers the VQL form —
  `references/associations.md` has the verified one.

### Types: the names invert between a declaration and a `CAST`

The one thing here that costs attempts. A column *declaration* takes VQL type names; a
`CAST` inside the SELECT takes SQL names — *verified: 9.5.1 (стенд, 2026-09-10)*:

| | declaring a column | `CAST(x AS …)` |
|---|---|---|
| 32-bit integer | `int` | `integer` |
| 64-bit integer | `long` | `bigint` |
| string | `text` | `varchar` |
| floating point | `double` | `double precision` |

`bigint` in a field list is `error while loading the type of the field 'bigint'`;
`CAST(x AS int)` is `Syntax error … near 'int'`. If you would rather hold one set of names
in your head, the two-argument cast `CAST('int', x)` takes the VQL ones, so the whole file
can then be written in VQL names. Unchanged either way: `decimal`, `float`, `boolean`,
`localdate`, `timestamp`.

## What you need before filling a template

| Slot | Where it comes from |
|---|---|
| The views underneath | read them, do not assume: `vql desc --env lab --database <db> <view>` gives the exact column names and types. A misremembered column is the most common failure of the whole skill |
| Grain of the result | the human — "per customer" or "per band" decides whether there is a `GROUP BY` and what the primary key is |
| Which columns the consumer needs | the human. When the answer is "everything", say what everything is at the moment and let them cut |
| Folder | `/02 - integration` for the joining and transforming layer, `/03 - business entities` for what consumers read, `/06 - associations` for associations — or `.denodo/conventions.md` if the project has one |
| Name | conventions in `/denodo:vql`; the `iv_` / bare-name split above |
| Derived view or interface view | interface view only when name and schema must survive a change of the implementation. Otherwise a derived view |
| Interface field types | the types of the implementation's columns, in VQL names (`int`, `long`, `text`) — read them off `DESC`, do not translate from memory |
| Association endpoints and multiplicity | the data, not the wish: check with a `SELECT` that the child really has at most one parent before writing `(1)` |
| `REFERENTIAL CONSTRAINT` or not | yes for a real foreign key. The source guarantees the integrity, Denodo does not enforce it — declaring it where it does not hold gives wrong results, not errors |
| Existing dependants | `USED_BY()` before touching anything that already exists — see Verify |

Do not ask about cache, swap, statistics or indexes: they have server defaults, they are
not part of creating these objects, and they are outside v1.

## Reference

- `references/derived.md` — the full `CREATE VIEW` grammar, field properties,
  `USING PARAMETERS`, `WITH CHECK OPTION`, `CONTEXT`, what `ALTER VIEW` can and cannot
  change, `DROP VIEW`.
- `references/interface.md` — the full `CREATE INTERFACE VIEW` grammar, field mapping,
  `ALTER INTERFACE VIEW`, the states an interface view can be in and what each means.
- `references/associations.md` — multiplicity in detail, role preconditions, composite
  mappings, `GET_ASSOCIATIONS()` columns, what an association changes for clients.

## Verify

**A successful statement is not a working object, and the two silent failures below are
the reason this skill exists.** After applying, always:

| Question | Read-back |
|---|---|
| Did the objects land, and where | `SELECT name, type, subtype, folder FROM GET_ELEMENTS() WHERE input_database_name = '<db>' AND type IN ('view', 'association')` — `subtype` is `base`, `derived` or `interface` |
| **Is anything broken now** | `SELECT name, view_type, view_status FROM GET_VIEWS() WHERE input_database_name = '<db>' AND input_retrieve_invalid_views_only = true` — **empty is the only good answer.** `view_type`: `0` base, `1` derived, `2` interface |
| Does it carry rows | `SELECT * FROM <view> LIMIT 10`, and a count that can be checked against the input |
| Schema of the contract | `vql desc --env lab --database <db> <interface view>` — the columns the consumer sees |
| Are the associations still whole | `SELECT association_name, mappings, valid FROM GET_ASSOCIATIONS() WHERE input_database_name = '<db>' AND input_type = 'views'` — **`valid` must be `true`** |
| One association in full | `vql desc --env lab --database <db> <name> --type association` — roles, multiplicities, mappings, principal side |
| Who depends on this view | `SELECT view_name, used_by_name, depth FROM USED_BY() WHERE input_view_database_name = '<db>' AND input_view_name = '<view>'` — run it **before** a change, not after |

**Silent failure 1: a replaced view invalidates everything above it, without an error.**
`CREATE OR REPLACE VIEW` that renames or drops a column is accepted; every derived and
interface view that used that column goes to `view_status = 'INVALID'` and every
association that mapped it goes to `valid = false`. Nothing is reported at DDL time, the
replaced view itself still selects fine, and the failure lands on whoever queries the
dependant next — *verified: 9.5.1 (стенд, 2026-09-10)*. Adding a column is safe;
restoring the column repairs the dependants automatically.

**Silent failure 2: `SET IMPLEMENTATION` does not check the schema.** An implementation
whose column names do not match the interface's field list, or that is missing a field
entirely, is accepted by `CREATE OR REPLACE INTERFACE VIEW` without a word. `DESC` keeps
showing the declared schema. Only `SELECT` fails, with a message that names nothing:
`Error executing query. Total time 0.0 seconds. HOUSEHOLD_INCOME [INTERFACE] [ERROR]` —
*verified: 9.5.1 (стенд, 2026-09-10)*. **A `SELECT` through the contract is part of
applying it**, every time, including a swap of the implementation.

So the read-back after any change to something that already existed is: `USED_BY()`
before, `GET_VIEWS(… invalid only)` and `GET_ASSOCIATIONS().valid` after, then a `SELECT`
through each dependant that matters.

## Common mistakes

| You wrote | Server says | Fix |
|---|---|---|
| `CREATE INTERFACE VIEW v ( … ) FOLDER = '/x' SET IMPLEMENTATION w` | `Syntax error … near 'SET'` | `( fields ) SET IMPLEMENTATION w FOLDER = '/x'` |
| `household_count:bigint` in a field list | `error while loading the type of the field 'bigint'` | VQL names in declarations: `long` |
| `CAST(x AS int)`, `CAST(x AS double)` | `Syntax error … near 'int'` / `near ')'` | SQL names in a `CAST`: `integer`, `double precision` — or `CAST('int', x)` |
| `AVG(TO_DECIMAL(x))` under a `GROUP BY` | `The following fields cannot be projected: avg(to_decimal(x)) AS …` | drop the cast: `AVG` over an integer already returns a double |
| `SELECT 1 AS one` | `Syntax error … near 'one'` | `one` is reserved; name the column something else |
| two output columns with the same alias | `The following fields cannot be projected: … AS x` | alias them apart |
| `ENDPOINT (0..1)` | `Syntax error … near '0.'` | VQL multiplicity is `(0,1)` |
| both endpoints `PRINCIPAL` | `In a 1:N association, the principal endpoint must have multiplicity 1 or 0..1` | exactly one `PRINCIPAL`, on the `(1)` or `(0,1)` side |
| a second association reusing a role name | `The association endpoint role name 'x' already exists for the selected view` | role names are unique per view |
| `ADD MAPPING a = b` with a column that does not exist | `Field not found 'v.b' in view 'v'` | read the columns first |
| `ENDPOINT … PRINCIPAL` without `REFERENTIAL CONSTRAINT` | nothing — accepted | add `REFERENTIAL CONSTRAINT`, or it is not a foreign key |
| `CREATE OR REPLACE VIEW` renaming a column | nothing — accepted | check `GET_VIEWS(… invalid only)`; either keep the old name or map it in the dependants |
| `SET IMPLEMENTATION` over a mismatched view | nothing — accepted | `SELECT` through the contract; map the fields |
| `DROP VIEW v` with dependants | `error removing view: There are some elements that depend on this one` | `USED_BY()` first, then ask the human — `CASCADE` takes the dependants with it |
| `DROP ASSOCIATION a` when there is none | `error removing association: Error loading association 'a'.` | `DROP ASSOCIATION IF EXISTS` — it has no `CASCADE`, unlike the view drops |
| `WHERE input_database_name = …` on `VIEW_DEPENDENCIES()` | `Field not found 'input_database_name'` | that one is `input_view_database_name`, like `USED_BY()` |
| `WHERE input_type IN ('view','association')` on `GET_ELEMENTS()` | nothing — zero rows | input parameters take `=` only; run one query per value |

Dropping is the human's call — `/denodo:vql`. Before asking, show what goes with it:
`USED_BY()` for a view, `GET_ASSOCIATIONS()` for the associations that hang off it.
