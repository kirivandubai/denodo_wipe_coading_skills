# Associations in full

An association is a declaration about two views: how their rows correspond, which side is
the parent, and whether the correspondence is a foreign key. It stores no data and changes
no query result on its own.

**The public VQL Guide 9.5 has no `CREATE ASSOCIATION` page.** The documentation covers
the Design Studio dialog (*Creating an Association*, *Multiplicity of Associations*,
*Referential Integrity in Associations*, *Role Preconditions*) and the procedure
`GET_ASSOCIATIONS()`; the statement itself is documented only by the server. Everything
below was taken off a live 9.5.1 instance.

## Grammar as the server accepts it

```
CREATE [ OR REPLACE ] ASSOCIATION <name> [ REFERENTIAL CONSTRAINT ]
    [ FOLDER = <literal> ]
    ENDPOINT <role name> [<database>.]<view> [ PRINCIPAL ] ( <multiplicity> )
        [ PRECONDITION ( <condition> ) ]
    ENDPOINT <role name> [<database>.]<view> [ PRINCIPAL ] ( <multiplicity> )
        [ PRECONDITION ( <condition> ) ]
    ADD MAPPING <left column> = <right column>
    [ ADD MAPPING <left column> = <right column> ]*
```

*verified: 9.5.1 (стенд, 2026-09-10)*, every clause including the optional ones.
`FOLDER` may be omitted — the association then lands at the root of the database.

## Reading an endpoint

```
ENDPOINT income_band bv_household_demographics (0,*)
ENDPOINT households  bv_income_band PRINCIPAL (1)
```

- **Role name first, and it names the other end.** The endpoint carrying
  `bv_household_demographics` is called `income_band` because that is what a household
  leads you to. Design Studio names roles this way; `SELECT_NAVIGATIONAL` and the RESTful
  service use the role as the link label.
- **Multiplicity is how many rows of *this* endpoint's view exist per one row of the
  other.** A band has zero or more households → the households endpoint is `(0,*)`. A
  household has exactly one band → the bands endpoint is `(1)`. Getting these the wrong
  way round produces no error and a wrong model.
- Forms: `(0,*)`, `(*)`, `(1)`, `(0,1)`, `(1,*)`. The `0..1` and `*` notation in the
  documentation is the dialog's, and `(0..1)` in VQL is `Syntax error … near '0.'` —
  *verified: 9.5.1 (стенд, 2026-09-10)*.
- **Role names are unique per view.** A second association reusing a role name on the same
  view is rejected: `The association endpoint role name 'x' already exists for the selected
  view`. Naming each role after the other view makes the collision meaningful rather than
  annoying.
- Endpoints may be base, derived or interface views, may be in different databases, and
  may be the same view twice (a self-association, with two different role names) —
  *verified: 9.5.1 (стенд, 2026-09-10)*.

## `REFERENTIAL CONSTRAINT` and `PRINCIPAL`

`REFERENTIAL CONSTRAINT` says the association is a foreign key: every row of the dependent
side has a match on the principal side. `PRINCIPAL` marks which side that is.

- Without `REFERENTIAL CONSTRAINT`, `PRINCIPAL` is **accepted and ignored** —
  `is_referential_constraint` reads `false` and the JDBC and ODBC drivers report no foreign
  key — *verified: 9.5.1 (стенд, 2026-09-10)*. The pair belongs together.
- The principal endpoint must be `(1)` or `(0,1)`. Two principals is
  `Error creating association: invalid endpoint: In a 1:N association, the principal
  endpoint must have multiplicity 1 or 0..1`.
- **Virtual DataPort does not enforce it.** Declaring a referential constraint the data
  does not honour does not raise an error; it licenses the optimiser to act on a false
  statement, and wrong results are the failure mode. Check with a `SELECT` before
  declaring:

  ```sql
  SELECT COUNT(*) AS orphans
  FROM bv_household_demographics hd
  WHERE hd.hd_income_band_sk NOT IN ( SELECT ib_income_band_sk FROM bv_income_band );
  ```

## Mappings

`ADD MAPPING <left> = <right>`: the left column belongs to the view of the **first**
`ENDPOINT`, the right to the second. A composite key is several `ADD MAPPING` lines —
*verified: 9.5.1 (стенд, 2026-09-10)*.

A column that does not exist is caught at creation:
`Field not found 'bv_income_band.ib_no_such_column' in view 'bv_income_band'`. That is the
one thing about associations the server does check eagerly.

`GET_ASSOCIATIONS()` reads the mappings back fully qualified:
`bv_household_demographics.hd_income_band_sk=bv_income_band.ib_income_band_sk`.

## Role preconditions

A precondition restricts which rows show a link to the other end in
`SELECT_NAVIGATIONAL` and the RESTful web service. It goes **after the multiplicity**, and
the condition is parenthesised, not a string literal:

```sql
-- verified: 9.5.1 (стенд, 2026-09-10)
CREATE OR REPLACE ASSOCIATION a_income_band_household REFERENTIAL CONSTRAINT
    FOLDER = '/06 - associations'
    ENDPOINT income_band bv_household_demographics (0,*)
    ENDPOINT households  bv_income_band PRINCIPAL (1) PRECONDITION ( ib_lower_bound > 0 )
    ADD MAPPING hd_income_band_sk = ib_income_band_sk;
```

- A quoted condition is `Error executing CREATE operation: Operator 'is true' for type
  'text' not found` — the parentheses are what makes it a condition rather than a string.
- **The *other* endpoint must be `*` or `0..1`**, or the server refuses: `To set a
  precondition in an end point, the other end point must have cardinality * or 0..1.`
  The reasoning is in the documentation: a precondition means "there may be nothing on the
  other side", which a mandatory multiplicity contradicts.
- The condition refers to the columns of the view at the endpoint that carries it.
- Read it back in `left_role_precondition` / `right_role_precondition`.

## Reading associations back

```sql
SELECT association_name, left_view_name, left_role, left_multiplicity,
       right_view_name, right_role, right_multiplicity, mappings, valid,
       is_left_principal, is_referential_constraint, association_database
FROM GET_ASSOCIATIONS()
WHERE input_database_name = '<db>' AND input_type = 'views';
```

`input_type` is mandatory and is `'views'` or `'webservices'`. `input_name` narrows to one
view; leave it out for the whole database. The procedure only shows an association if you
hold `METADATA` on both endpoints.

`valid` is the column that matters: **an association whose mapped column disappears stays
in the catalog and flips `valid` to `false`, silently** — no error when the view is
replaced, and the view itself keeps selecting fine — *verified: 9.5.1 (стенд,
2026-09-10)*. Restoring the column flips it back. There is no `view_status` equivalent for
associations, so `GET_ASSOCIATIONS()` after any change to a view is the only check.

`vql desc --env lab --database <db> <name> --type association` gives the same facts for
one association, and `--vql` gives the statement the server would write — the reference
worth copying when a hand-written form is not being accepted.

## Dropping

```
DROP ASSOCIATION [ IF EXISTS ] <name>
```

No `CASCADE` — an association has nothing beneath it. Without `IF EXISTS` on a name that
is not there: `error removing association: Error loading association '<name>'.`

An association counts as a dependant of the views it links: `DROP VIEW` on either endpoint
is `error removing view: There are some elements that depend on this one`, and
`DROP VIEW … CASCADE` takes the association with it — *verified: 9.5.1 (стенд,
2026-09-10)*. That is part of what a human agrees to when they confirm a `CASCADE`, so
list the associations (`GET_ASSOCIATIONS()`) before asking.

## Where associations come from in practice

Design Studio can derive them from the foreign keys of a JDBC source: select the base
views, then *More → Discover associations*, which reads the `REFERENCES` parameters that
`CREATE WRAPPER JDBC` recorded when the base views were created. For file sources, derived
views and anything else, the association is written by hand — this file. If a source's
foreign keys changed after the base views were made, the discovered list is stale until
the base view is refreshed.
