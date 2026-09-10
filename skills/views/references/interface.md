# Interface views in full

An interface view is a schema plus a pointer. It holds no logic of its own: the query is
delegated to the view named after `SET IMPLEMENTATION`. That is the whole idea — the name
and the field list are a contract, and what satisfies the contract can change underneath.

## Grammar (documentation 9.5)

```
CREATE [ OR REPLACE ] INTERFACE VIEW <name>
    ( <field> [, <field> ]* )
    [ SET IMPLEMENTATION <view>
        [ ( <interface field> = <expression> [, <interface field> = <expression> ]* ) ]
    ]
    [ FOLDER = <literal> ]
    [ DESCRIPTION = <literal> ]
    [ TAGS ( <tag> [, … ] ) ]
```

`SET IMPLEMENTATION` sits between the field list and `FOLDER`, and nowhere else:
`Syntax error: Exception parsing query near 'SET'` — *verified: 9.5.1 (стенд,
2026-09-10)*.

Field types are **VQL** names: `int`, `long`, `text`, `double`, `decimal`, `float`,
`boolean`, `localdate`, `timestamp`. `bigint`, `integer` and `varchar` in a field list are
`error while loading the type of the field '<name>'` — *verified: 9.5.1 (стенд,
2026-09-10)*. Those are the `CAST` spellings; the table in `/denodo:views` has both
columns.

Design Studio also writes `sourcetypeid`, `sourcetypesize`, `sourcetypedecimals` and
`description` into each field's parentheses. They are metadata carried over from the
implementation, they are not needed in a hand-written file, and copying them from a
`DESC VQL` of another view pins the contract to that view's source types.

## Field mapping

Without a mapping, fields are matched to the implementation **by name**. With one, each
interface field is bound explicitly:

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
    SET IMPLEMENTATION iv_household_income_v2 (
        household_sk       = household_key,
        income_band_sk     = band_key,
        buy_potential      = buy_potential,
        dependents         = dependent_count,
        vehicles           = vehicle_count,
        income_lower_bound = band_lower,
        income_upper_bound = band_upper )
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Household income data product.';
```

Left of `=` is the interface field, right is the implementation's column. The mapping is
what makes a contract outlive a rename: the consumer keeps reading `vehicles`, the
implementation renames its column to `vehicle_count`, and one line of the file absorbs it.

## The schema is not checked when you set it

`CREATE OR REPLACE INTERFACE VIEW … SET IMPLEMENTATION` accepts an implementation that
does not satisfy the contract, with no error and no warning —
*verified: 9.5.1 (стенд, 2026-09-10)*, in all of these shapes:

| What you point at | DDL | `DESC` | `SELECT` |
|---|---|---|---|
| a view whose column names do not match | accepted | declared schema | `… <NAME> [INTERFACE] [ERROR]` |
| a view missing one of the declared fields | accepted | declared schema | same |
| a view with three columns under a seven-field contract | accepted | declared schema | same |
| nothing at all (no `SET IMPLEMENTATION`) | accepted | declared schema | same |

The `SELECT` error names the view and nothing else — no missing field, no line number.
So the two read-backs below are the only things that tell you the truth, and both belong
in the same step as applying the file.

## States

`SELECT name, view_type, view_status FROM GET_VIEWS() WHERE input_database_name = '<db>'`
— `view_type` is `2` for an interface view, and `view_status` is *verified: 9.5.1 (стенд,
2026-09-10)*:

| `view_status` | Means |
|---|---|
| `OK` | the implementation satisfies the contract |
| `INVALID` | an implementation is set and does not satisfy it — names, count or a broken view below |
| `INTERFACE_NOT_IMPLEMENTED` | no `SET IMPLEMENTATION` at all. Legitimate while a top-down design is in progress; a leftover otherwise |

`… WHERE input_retrieve_invalid_views_only = true` narrows the same query to what is
broken. Empty is the answer you want.

## Types do not have to match exactly

Declaring `household_sk:text` over an implementation column of type `int` is accepted and
the `SELECT` returns strings — *verified: 9.5.1 (стенд, 2026-09-10)*. The interface casts.
That is useful when a contract has to keep a type the source has moved away from, and it
is a trap when the mismatch was a typo: nothing reports it, the consumer just starts
getting a different type than the model says.

A field list narrower than the implementation is normal and works: an interface view is
also how you publish a subset of a wide view — *verified: 9.5.1 (стенд, 2026-09-10)*.

## Swapping the implementation

Two ways, same result:

```sql
-- verified: 9.5.1 (стенд, 2026-09-10)
ALTER INTERFACE VIEW household_income SET IMPLEMENTATION iv_household_income_v2
    ( household_sk = household_key, income_band_sk = band_key, … );
```

`ALTER` is for the case the clause was built for — the contract was created first, the
implementation arrives later — and for that case it is the only option: re-applying a file
whose statement has no `SET IMPLEMENTATION` **clears** the implementation and puts the view
back to `INTERFACE_NOT_IMPLEMENTED`, *verified: 9.5.1 (стенд, 2026-09-10)*. Everywhere else,
re-apply the file with the new view after `SET IMPLEMENTATION`: the file stays the record
of what is deployed. `ALTER` is a change to an existing object, so the human confirms it
(`/denodo:vql`).

After either one: `SELECT` through the contract. Every time.

## Interface views elsewhere

- **Data Marketplace external elements** are imported from an interface view in VDP whose
  schema the marketplace itself dictates. That chain is `/denodo:marketplace`; the
  interface view in the middle of it is built exactly as above.
- An interface view can be an **association endpoint** — *verified: 9.5.1 (стенд,
  2026-09-10)* — which is how a published data product gets its relationships into the
  catalog without exposing the integration layer underneath.
