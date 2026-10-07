# Arrays and registers in full

Everything `/denodo:views` leaves out of the `FLATTEN` and `NEST` templates. A register is a
record inside a column (`shipping` with `country`, `city`); an array is a list of registers
inside a column (`lines`, each with `line_no`, `sku`, …). They come from JSON and XML base
views (`/denodo:datasources`) and from `NEST` and `REGISTER` in a derived view.

## Reading a register

`(shipping).country` — the parentheses are required; `shipping.country` is read as
*view.column*. With a table alias: `(o.shipping).country`. A register stays one column
through `SELECT *` and through `FLATTEN` of another column.

One element of an array by position: `lines[0].sku` — from 0, no parentheses; past the end it
is `NULL`. `WHERE lines.sku = …` is `Field not found 'lines.sku'`; parenthesised, `WHERE
(lines).sku = 'x'` keeps the parents with such an element in any position, so `(lines).sku <> 'x'`
keeps a parent that has an `'x'` too — *verified: 9.5.1 (live, 2026-10-07)*. There is no
array-length function (`SIZE`, `CARDINALITY`, `ARRAY_LENGTH` do not exist) and
`COUNT(lines)` counts rows, not elements: count elements after `FLATTEN`.
`lines IS NULL` tells a missing array from an empty one, which `FLATTEN` makes look the same —
*verified: 9.5.1 (live, 2026-09-30)*.

## FLATTEN: an array to rows

```
FLATTEN <view> AS <alias> ( <alias> [ . <register field> ]* . <array field> ) [ ( … ) ]*
```

`FLATTEN` stands where a view would in `FROM`, can be a subquery's `FROM`, and works on a view
of another database (`FLATTEN other_db.bv_x AS v (v.items)`) — *verified: 9.5.1 (live,
2026-09-30)*.

| Question | Answer (*verified: 9.5.1 (live, 2026-09-30)* unless marked) |
|---|---|
| What rows come out | one per array element, the parent's columns repeated on each |
| An empty array `[]` or a missing / `NULL` array | **one row**, every element field `NULL` — the parent is kept, like an outer join. Filter `WHERE <element field that is never null> IS NOT NULL` when you want elements only |
| What columns come out | the parent's columns except the flattened array, then the element's fields **without a prefix**. Selecting the array itself afterwards is `Field not found 'lines' in view with schema …` |
| An element field named like a parent column | renamed `<array>_<field>`: `status` inside `lines` comes out as `lines_status`, next to the parent's `status`. Nothing is refused; `SELECT status` silently reads the parent's |
| An array inside a register | `FLATTEN v AS x (x.detail.lines)`; the register's other fields come out as top-level columns too, and a clash is prefixed with the whole path: `detail_lines_status` |
| Two arrays in one `FLATTEN` | `(x.a) (x.b)` is accepted and gives **every pairing** of the two arrays' elements — a parent with 3 and 4 elements becomes 12 rows; the second array's clashing fields get its prefix. Two independent lists are two views, not one `FLATTEN` |
| Primary key of the result | the parent key plus the element's own: `PRIMARY KEY ( 'order_id', 'line_no' )` is accepted |
| Filters on element fields | `WHERE sku = …`, `WHERE qty > …` after `FLATTEN` filter correctly |
| Filters on the parent's fields | as correct as the base view underneath: over a JSON base view created without `CONSTRAINTS … NOS ZERO ()` they are dropped, through `FLATTEN`, every view above and below a `GROUP BY` (`HAVING` is still applied) — `/denodo:datasources`. Over such a base view that is not yours, project the parent columns through an expression (`TRIM(o.order_id) AS order_id`): the server then filters itself, while a plain alias still hands the condition to the wrapper |

**The parent's measures repeat.** After `FLATTEN`, `SUM(total_amount)` adds each order once
per line and `COUNT(*)` counts lines plus one row per order without lines. Take the parent's
figures from the unflattened view and the element's from the flattened one, and join the two
at the grain the result needs; `COUNT(DISTINCT order_id)` is right over the flattened rows only
for counting parents.

### One row per parent, every parent kept

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CREATE OR REPLACE VIEW order_line_summary
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'One row per order, every order included. line_count and line_value are 0 for an order without lines; bulk_lines (lines of 5 or more units) is NULL when there is none.'
    PRIMARY KEY ( 'order_id' )
    AS SELECT o.order_id                  AS order_id,
              o.total_amount              AS total_amount,
              COALESCE(l.line_count, 0)   AS line_count,
              COALESCE(l.line_value, 0)   AS line_value,
              b.bulk_lines                AS bulk_lines
       FROM bv_oms_orders o
            LEFT OUTER JOIN ( SELECT order_id          AS order_id,
                                     COUNT(*)          AS line_count,
                                     SUM(qty * price)  AS line_value
                              FROM iv_oms_order_lines
                              GROUP BY order_id ) l
            ON o.order_id = l.order_id
            LEFT OUTER JOIN ( SELECT order_id                  AS order_id,
                                     NEST(line_no, sku, qty)   AS bulk_lines
                              FROM iv_oms_order_lines
                              WHERE qty >= 5
                              GROUP BY order_id ) b
            ON o.order_id = b.order_id
    CONTEXT ('formatted' = 'yes');
```

Over the element view of `SKILL.md`, so the empty-array rows are already gone. The parent view
drives, each aggregate joins `LEFT OUTER`, and what a missing group means is decided in the
projection: a count or a sum becomes `0` through `COALESCE`, a minimum or an array stays `NULL`.
Write the decision into the `DESCRIPTION`.

## NEST: rows to an array

```
NEST( <field> [, <field> ]* )      NEST( * )
```

An aggregate function: under `GROUP BY` it gives one array per group, whose elements are
registers of the listed fields, named after them. Without `GROUP BY` it gives one row holding
the whole view. `NEST(*)` takes every column, the grouping key included — *verified: 9.5.1
(live, 2026-09-30)*.

| Question | Answer (*verified: 9.5.1 (live, 2026-09-30)*) |
|---|---|
| Renaming an element field | `NEST(line_no AS n, …)` is `Syntax error … near 'AS'`. Rename in the view below, or in a subquery |
| The column's type | a view creates it: `_register_<fields>` and `_array_register_<fields>`, catalog types of the view's database (`LIST TYPES`); an ad-hoc `SELECT … NEST(…)` creates none. **They stay after `DROP VIEW`** — removing them is a `DROP TYPE`, and the human's call like any drop |
| Filtering elements before nesting | a `WHERE` before `GROUP BY` drops every parent with no matching element. To keep them, `LEFT OUTER JOIN` the nested result back to the parent view: the array is then `NULL`, not empty |
| `FLATTEN` then `NEST` again | the row that stood for an empty array nests back as `[null]` — one element, all fields `NULL` — not `[]`. Filter that row out before `NEST` |
| An empty array | no way was found to build `[]`; `NULL` is what a missing group gives |

`REGISTER( <field>, … )` builds one register from columns in the same way (no `GROUP BY`):
`SELECT order_id, REGISTER(status, lines) AS detail FROM bv_oms_orders` — *verified: 9.5.1
(live, 2026-09-30)*. **A view that applies `REGISTER` to a view of another database creates
its `_register_<fields>` type in that other database**, not in its own — a write outside
yours. Build it over a view of your own database; `NEST` does not do this.

## Checking a flatten

| Question | Read-back |
|---|---|
| Were elements lost | `COUNT(<element field>)` over the `FLATTEN` of the base view equals `COUNT(*)` of your element view |
| Were parents lost | `COUNT(DISTINCT <parent key>)` of the element view plus the parents with an empty or missing array equals `COUNT(*)` of the parent view |
| Does a parent filter filter | `SELECT COUNT(*) FROM <element view> WHERE <parent key> = '<one value>'` returns that parent's elements, not the whole view |
| A view that nests again | its `COUNT(*)` equals the parents; the elements of all its arrays (`COUNT(<element field>)` over its own `FLATTEN`) equal the filtered source elements; the `NULL` arrays equal the parents with no matching element |
