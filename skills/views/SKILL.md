---
name: views
description: Use when building on top of views that already exist in Denodo 9.5 — a derived view (a join, an aggregate, a mart, a filtered or parameterised view, a UNION ALL of views of one entity, FLATTEN of a JSON array into rows, NEST of rows into an array), an interface view, or an association between two views. Also before changing a view others depend on — "what uses this view", "can I drop this column", "where does this field come from" — for whether a mart over a database runs there or pulls every row into Denodo, for "combine these sources into one view", "expose this as a data product", and for a view created without an error that fails on SELECT or turns up INVALID. Not for sources and base views — /denodo:datasources; databases, folders, VDP tags — /denodo:catalog; a view's cache — /denodo:cache; a copy stored as a table — /denodo:materialize; a metric view — /denodo:metrics.
---

# Derived views, interface views and associations

Three objects, all built **on top of views that already exist**: the derived view that
transforms, the interface view that publishes a fixed contract, and the association that
records how two views relate. Order in the chain: **base view → derived view → interface
view → association**. A derived view is also how several views of one entity become one
(a union) and how an array becomes rows and back (`FLATTEN`, `NEST`).

Sources, wrappers and base views are `/denodo:datasources`; databases, folders and VDP
tags are `/denodo:catalog`. Describing, keying and tagging views that already exist — an
audit of a database for people and AI consumers — is `/denodo:semantics`. Metric views —
KPIs declared once over a fact and its dimensions, and the views built on them — are
`/denodo:metrics`; a mart of one fixed grain stays here. A view with a column that calls the
server's LLM or embedding model (`CLASSIFY_AI`, `EMBED_AI`, `VECTOR_DISTANCE` …) is
`/denodo:ai` first: every row it is read for is a request to the provider. Expressions that
return a wrong value without an error are the table in `/denodo:vql` and its `dialect.md`;
applying files is `/denodo:execute`; the loop, naming and the safety rule are `/denodo:vql`.

**The dangerous part of this skill is what happens after a successful statement.** All
three objects can be accepted by the server and be broken, and all three break *other
people's* objects the same way: the DDL returns success, and the failure surfaces later,
on someone's `SELECT`. So does a mart over a database that quietly stops running in it.
The Verify section is not optional, and neither is "Before a column changes" when the view
already has dependants.

## Templates

Each template is one file, applied whole, `CREATE OR REPLACE` throughout — re-applying
after a fix is safe. It is also the whole truth about the view: a description, field
description, key or tag added to the view since by `ALTER` is removed by the next apply,
silently — keep them in the file (`/denodo:semantics`).

### Derived view

```sql
-- verified: 9.5.1 (live, 2026-10-07)
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
            ON hd.hd_income_band_sk = ib.ib_income_band_sk
    CONTEXT ('formatted' = 'yes');

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
       GROUP BY income_band_sk, income_lower_bound, income_upper_bound
    CONTEXT ('formatted' = 'yes');
```

Clause order: `FOLDER` → `DESCRIPTION` → `PRIMARY KEY` → `TAGS` → `( field properties )` →
`AS SELECT` → `USING PARAMETERS` → `CONTEXT`. Everything before `AS` is optional; put
`FOLDER` in anyway, because a view without one lands at the root of the database.

- **Every `CREATE VIEW` ends with `CONTEXT ('formatted' = 'yes')`.** Without it the server
  stores the `SELECT` re-serialised (lower-cased functions, dropped aliases, `SQL UNION ALL`),
  and `DESC VQL` no longer matches the file; with it, everything after `AS` is stored as
  written — *verified: 9.5.1 (live, 2026-09-30)*. `--` comments never reach the server, so
  what a reviewer must read goes into the `DESCRIPTION`.

- **One view per grain.** The join lives in `/02 - integration` at the row grain of the
  entity; the aggregate is a second view in `/03 - business entities`. One statement with
  both works, but the join is then not reusable and the mart cannot be checked against it;
  the consumer still reads one object. **When no aggregate is wanted**, the join *is* the
  `/03 - business entities` object, with the bare business name — no pass-through view above.
- **Count the dimension before you join it.** `SELECT COUNT(*), COUNT(DISTINCT <business
  key>) FROM <dimension>` — a dimension that keeps history has several rows per business
  key, and joining on that key multiplies every figure in the mart with no error anywhere.
  In the TPC-DS sample data the `store` and `call_center` dimensions keep two rows per business
  key; the fact carries the surrogate key, so join on that and project the business key as a
  column, so the consumer can still roll up. **The hint is a pair of validity columns**
  (`rec_start_date` / `rec_end_date`), and the `COUNT` decides: over one row per business key
  they are not history.
- **`INNER` drops facts, and nobody is told.** The template joins `INNER` because its two
  TPC-DS tables match completely; real data usually does not — in the TPC-DS returns, some
  store returns carry no store key at all and some web returns name no reason. Decide which
  you want and record the decision in the `DESCRIPTION`:
  - the unmatched rows matter → `LEFT OUTER JOIN` from the fact, with a label for the
    group: `COALESCE(TRIM(r.reason_desc), '(reason not specified)')`. Two different things
    land in that group — the fact's key is `NULL`, or the key has no row in the dimension —
    so count the second kind (`WHERE fk IS NOT NULL AND dim_key IS NULL`) before you label
    them, or the label is a lie;
  - they do not → keep `INNER JOIN`, and put the number of rows you dropped in the
    `DESCRIPTION`, measured, not guessed.
- **Naming.** `/02 - integration`: `iv_` and what the view does; `/03 - business entities`: no
  prefix, what the consumer gets (`household_income_by_band`). `iv_` is *integration view*, not
  *interface view* — the interface view below takes the bare business name.
- **Types an aggregate produces** — needed for an interface view over the mart: `COUNT` →
  `long` (`DESC` prints `BIGINT`), `AVG` over an integer → `double` — *verified: 9.5.1 (live,
  2026-09-10)*. **`SUM` over an `int` stays `int`**, and past 2 147 483 647 returns `NULL` or
  a wrong figure, with no error: `SUM(CAST('long', x))`, for an `int` column only — over a
  `decimal` the cast truncates every row (`/denodo:vql`, Expressions). Under `GROUP BY`,
  `COUNT(DISTINCT x)`, that cast and expressions over grouped columns work — *verified: 9.5.1
  (live, 2026-09-12)*; `AVG(TO_DECIMAL(x))` is refused (Common mistakes).
- Attaching tags: `TAGS ( pii )` before the field properties for the whole view,
  `( email ( description = '…' ) TAGS ( pii ) )` for one column — both
  *verified: 9.5.1 (live, 2026-09-10)*. The tag itself is `/denodo:catalog` and must
  exist first.

### Union — one entity from several views

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW returns
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Return lines of every sales channel. One row per return line; channel names the source.'
    PRIMARY KEY ( 'channel', 'item_sk', 'order_number' )
    AS SELECT *
       FROM ( SELECT 'store'             AS channel,
                     sr_item_sk          AS item_sk,
                     sr_ticket_number    AS order_number,
                     sr_returned_date_sk AS returned_date_sk,
                     sr_reason_sk        AS reason_sk,
                     sr_return_quantity  AS return_quantity,
                     sr_return_amt       AS return_amount
              FROM bv_retail_store_returns ) store_returns
       WHERE channel = 'store'
       UNION ALL
       SELECT *
       FROM ( SELECT 'web'               AS channel,
                     wr_item_sk          AS item_sk,
                     wr_order_number     AS order_number,
                     wr_returned_date_sk AS returned_date_sk,
                     wr_reason_sk        AS reason_sk,
                     wr_return_quantity  AS return_quantity,
                     wr_return_amt       AS return_amount
              FROM bv_retail_web_returns ) web_returns
       WHERE channel = 'web'
    CONTEXT ('formatted' = 'yes');
```

One branch per source, and a constant column that says which source a row came from.

- **Every branch lists the same columns, in the same order, under the same aliases.**
  `UNION ALL` matches branches by position, and the name a column ends up with can come from
  any branch. A union whose second branch reads `reason, qty` against the first's
  `qty, reason` is accepted, and then `SELECT qty` and `WHERE qty = 1` over it disagree about
  which values `qty` holds — no error anywhere. A source that lacks a column gets a typed
  `NULL` in its place (`CAST(NULL AS integer) AS store_sk`); a column whose type differs is
  cast in the branch, or the union widens it silently (`int` under `text` becomes `text`).
- **`UNION ALL`, not `UNION`.** `UNION` removes duplicate rows — identical return lines too —
  and stops the optimizer pushing a `GROUP BY` or a join below the union.
- **The constant does nothing for speed by itself.** A query `WHERE channel = 'web'` reads
  every source unless each branch carries a `WHERE` on its own constant; then the branches
  that contradict the query are removed from the plan and only one source is read. The
  `WHERE` wraps a subquery because a condition cannot name an alias of its own `SELECT`. The
  consumer's filter decides too: `=`, `IN`, `<>` prune; `UPPER(channel) = 'WEB'` reads
  everything, and `channel = 'Web'` contradicts every branch and returns no rows. The
  constant's values are part of the contract — name them in the `DESCRIPTION`.
- **When the split is a real column** — the current year in one database, earlier years in
  another — each branch filters that column of its source directly, no subquery needed, and
  **rows whose key is `NULL` fall into no branch and vanish**. Put `OR <key> IS NULL` into
  the branch of the source that owns them. When the sources overlap (a copy never trimmed),
  the ranges are also what keeps each row once.
- Column descriptions cannot go on a union: when the consumer needs them, it goes to `/02` as
  `iv_…`, and the `/03` view over it carries them; the pruning survives the layer.

`references/unions.md` has the measurements behind each point and how to read the plan.

### Arrays — `FLATTEN` to rows, `NEST` back

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW iv_oms_order_lines
    FOLDER = '/02 - integration'
    DESCRIPTION = 'Order lines of the order management export. One row per order line; an order without lines has no row here.'
    PRIMARY KEY ( 'order_id', 'line_no' )
    AS SELECT o.order_id           AS order_id,
              o.customer_id        AS customer_id,
              (o.shipping).country AS shipping_country,
              o.line_no            AS line_no,
              o.sku                AS sku,
              o.qty                AS qty,
              o.price              AS price
       FROM FLATTEN bv_oms_orders AS o ( o.lines )
       WHERE o.line_no IS NOT NULL
    CONTEXT ('formatted' = 'yes');

CREATE OR REPLACE VIEW iv_customer_orders
    FOLDER = '/02 - integration'
    DESCRIPTION = 'One row per customer, with the array of their orders.'
    PRIMARY KEY ( 'customer_id' )
    AS SELECT customer_id                             AS customer_id,
              NEST(order_id, order_dt, total_amount)  AS orders
       FROM bv_oms_orders
       GROUP BY customer_id
    CONTEXT ('formatted' = 'yes');
```

`FLATTEN <view> AS <alias> ( <alias>.<array> )` gives one row per array element;
`(o.shipping).country` reads a register (`/denodo:datasources` builds both from JSON).

- **An empty or missing array is not dropped — it becomes one row with every element field
  `NULL`.** A view of elements needs the template's `WHERE <element field> IS NOT NULL`, on a
  field no real element leaves empty; without it `COUNT(*)` counts an empty order as a line.
- **The parent's measures repeat on every element row** (`SUM(total_amount)` adds each order
  once per line): aggregate them from the unflattened view, join at the result's grain.
- **Names.** The element's fields come out without a prefix and the array column is gone. An
  element field named like a parent column is renamed `<array>_<field>` — a line's `status`
  comes out as `lines_status`, while plain `status` is still the order's. Look at
  `SELECT * FROM FLATTEN … LIMIT 1` before you write the projection.
- **`NEST` is an aggregate:** one array per `GROUP BY` group, its elements named after the
  listed columns (rename in the view below). The server creates the array's type itself
  (`_array_register_<fields>`), and the type outlives the view. A `WHERE` before `NEST` drops
  the parents left with no element; keep them with a `LEFT OUTER JOIN` from the parent view,
  and the array is then `NULL`.
- **A filter on the parent's fields is only as good as the JSON base view underneath.** One
  created without `CONSTRAINTS ( ADD <field> NOS ZERO () … )` silently drops every `WHERE` on
  its fields, and the loss reaches through `FLATTEN` and every view above — below a
  `GROUP BY` too: `WHERE country = 'DE'` over an aggregate returns every country. Before
  building on a JSON base view, run `SELECT COUNT(*) FROM <base view> WHERE <key> = '<one
  value>'`: anything but one row means `/denodo:datasources` has to fix the base view first.
  `DESC VQL` of the base view shows the cause directly: `ADD <column> (any) OPT ANY` where
  `NOS ZERO ()` should be. **When the base view is not yours to fix**, tell its owner;
  `references/arrays.md` (filters on the parent's fields) has the workaround meanwhile.
- **Where the element view goes**: read by the consumer, it is the `/03 - business entities`
  object under its bare name, like a join with no aggregate; read only by other views, an `iv_`
  in `/02 - integration`, as in the template.

`references/arrays.md` has one row per parent with every parent kept (counts from the
elements, a re-nested array), arrays inside registers, two arrays at once, and `REGISTER`.

### Interface view — a contract you can re-implement

```sql
-- verified: 9.5.1 (live, 2026-10-07)
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
`DESCRIPTION`** — *verified: 9.5.1 (live, 2026-09-10)*.

Use an interface view when the *name and schema* have to survive a change of the thing
underneath: a published data product, a consumer outside the team, a top-down design where
the contract is agreed before the implementation exists. If nothing has to survive, a
derived view is the simpler object.

**Where the implementation lives.** The derived view above sits in
`/03 - business entities` because it *is* what the consumer reads. As soon as a contract
goes in front of it, it stops being that: the interface view takes the business name and
the `/03` folder, and the aggregate moves to `/02 - integration` under an `iv_` name with
the rest of the machinery. Everything the consumer does not name belongs in `/02`.

**Swapping the implementation** is a re-apply of the same file with a different view after
`SET IMPLEMENTATION`. Nothing the consumer sees changes. When the new implementation names
its columns differently, map them — the field list stays as it was:

```sql
-- verified: 9.5.1 (live, 2026-09-10)
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
but it is an `ALTER`: `vql plan` says whether it waits for the human's yes (`/denodo:vql`).
Re-applying the file is the default.

**When a column is renamed underneath an existing contract**, the mapping and the contract
are two different answers, and the request decides which:

| The rename is | Do | Because |
|---|---|---|
| internal — a tidy-up, a refactor, a naming convention inside your layer | keep the field list, map the new column: `SET IMPLEMENTATION v ( vehicles = vehicle_count, … )` | that is the whole point of the contract; the consumer is not involved |
| the point — "call it that everywhere, including what they read" | change the field list too, in the same file | a contract that hides the rename does not deliver the request |

Changing the field list **is a breaking change for the consumer**, whatever it says on the
object: the old column is gone. Say so when you report it, and if the request was
ambiguous, ask before you narrow the contract — widening it is safe, dropping a field is
not.

### Association — the relationship, recorded

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CREATE OR REPLACE ASSOCIATION a_income_band_household REFERENTIAL CONSTRAINT
    FOLDER = '/06 - associations'
    ENDPOINT income_band bv_household_demographics (0,*)
    ENDPOINT households  bv_income_band PRINCIPAL (1)
    ADD MAPPING hd_income_band_sk = ib_income_band_sk;
```

The VQL Guide's grammar (*RESTful Architecture → Associations*) has no `PRINCIPAL`; this
template is the form the server writes back (`DESC VQL`). Read an endpoint like this:

```
ENDPOINT <role name>  <view>  [PRINCIPAL]  (<multiplicity>)
            │            │         │             │
            │            │         │             └─ rows of THIS view per one row of the other
            │            │         └─ this view is the parent of the foreign key
            │            └─ the view at this endpoint
            └─ what you reach FROM this endpoint's view — i.e. the other view's name
```

The first identifier is the **role name of the other end, not an alias for this view** —
the endpoint carrying `bv_household_demographics` is named `income_band`, because a
household leads you to its band. Above: a band has zero or more households `(0,*)`, a
household has exactly one band `(1)`.

- **`REFERENTIAL CONSTRAINT` is what makes it a foreign key.** Without it, `PRINCIPAL` is
  accepted and silently ignored, and JDBC/ODBC clients never see the relationship —
  *verified: 9.5.1 (live, 2026-09-10)*. Leave it out only for a link that is genuinely
  not a foreign key.
- **`(1)` on the principal end is a promise that every row of the other view has a match.**
  A metric view over the association keeps that promise for you: rows without a match are
  dropped from every grouped figure, even with `RIGHT` written — *verified: 9.5.1 (live,
  2026-10-01)*. When some rows have a `NULL` or unknown key, write `(0,1)`
  (`/denodo:metrics`).
- At most one endpoint is `PRINCIPAL`, and it must be `(1)` or `(0,1)`.
- Multiplicity is `(1)`, `(0,1)`, `(*)` or `(0,*)`, and `(+)` or `(1,*)` for one or more; the
  server writes `(0,*)` and `(+)`. The dialog's `0..1` is a syntax error in VQL.
- In `ADD MAPPING`, the left side — a column, or an expression or `CASE` over columns — is
  the **first** endpoint's view's, the right the second's. A composite key is several lines.
- **Role names are unique per view**: a second association cannot reuse one on the same
  view. Name roles after the other view and the clash tells you something real.
- Endpoints may be interface views, base views, derived views, and may live in different
  databases (`ENDPOINT band other_db.bv_income_band …`) — *verified: 9.5.1 (live,
  2026-09-10)*. An association does not make joins implicit: a query still writes its own
  `ON`. What it changes is the catalog and, for a `REFERENTIAL CONSTRAINT`, the foreign keys
  clients see and the optimizer: across two data sources it is the documented condition for
  pushing a `GROUP BY` below their join (`references/delegation.md`).
- A role precondition (which rows show the link in `SELECT_NAVIGATIONAL` and the RESTful
  service) is `PRECONDITION <condition>` **after** the multiplicity, as documented, and the
  condition is not quoted — `references/associations.md`.

### Types: the names invert between a declaration and a `CAST`

The one thing here that costs attempts. A column *declaration* takes VQL type names; a
`CAST` inside the SELECT takes SQL names — *verified: 9.5.1 (live, 2026-09-10)*:

| | declaring a column | `CAST(x AS …)` |
|---|---|---|
| 32-bit integer | `int` | `integer` |
| 64-bit integer | `long` | `bigint` |
| string | `text` | `varchar` |
| floating point | `double` | `double precision` |
| date | `localdate` | `date` |

The two-argument `CAST('int', x)` takes the VQL names, so a file can use one set throughout.
Unchanged either way: `decimal`, `float`, `boolean`, `timestamp`.

## What you need before filling a template

| Slot | Where it comes from |
|---|---|
| The views underneath | read them, do not assume: `vql desc --env dev --database <db> <view>` gives the exact column names and types. A misremembered column is the most common failure of the whole skill. A view of another database is read by its qualified name, `FROM other_db.bv_x` — *verified: 9.5.1 (live, 2026-09-30)* |
| Grain of the result | the human — "per customer" or "per band" decides whether there is a `GROUP BY` and what the primary key is. **One row per key among several** — the latest version, the current row of a history, a feed loaded twice — is `references/one-row-per-key.md`: a window runs only where it can be delegated (a database, or an MPP engine or data movement the server is set up for), and the usual `MAX(<date>)` joined back keeps ties and drops undated keys, without an error |
| Which columns the consumer needs | the human. When the answer is "everything", say what everything is at the moment and let them cut |
| Folder | `/02 - integration` for the joining and transforming layer, `/03 - business entities` for what consumers read, `/06 - associations` for associations — or `.denodo/conventions.md` if the project has one, else the folders a database that already holds objects uses (`/denodo:vql`) |
| Name | conventions in `/denodo:vql`; the `iv_` / bare-name split above |
| Derived view or interface view | interface view only when name and schema must survive a change of the implementation. Otherwise a derived view |
| Interface field types | the types of the implementation's columns, in VQL names (`int`, `long`, `text`) — read them off `DESC`, do not translate from memory |
| Association endpoints and multiplicity | the data, not the wish: `(1)` claims every child row has a parent, so a **nullable foreign key makes it `(0,1)`** — count the NULLs before choosing. Orphans (a key with no match) are a different question and rule out `REFERENTIAL CONSTRAINT`, not the multiplicity |
| `REFERENTIAL CONSTRAINT` or not | yes for a real foreign key. The source guarantees the integrity, Denodo does not enforce it — declaring it where it does not hold gives wrong results, not errors |
| Whether the measures are complete | `COUNT(*)` counts rows, `COUNT(<measure>)` counts rows where the measure is not null, and when they differ, `AVG` divides by the second while the consumer will divide by the first. Count the NULLs; if there are any, either publish both counts or say in the `DESCRIPTION` which one the average is over. Both notes have a place in the DDL: the per-column `( <column> ( description = '…' ) )` field property for what one column means, the view `DESCRIPTION` for the counts — with the date you measured them, because the next load changes them. The same NULLs decide `INNER JOIN` against `LEFT JOIN` |
| Union branches | one per source of the same entity. Read each with `vql desc`: sources name, order and type their columns differently, and every branch lists them in the union's order, not its source's |
| What the union is split on | what consumers filter by — a constant per source (`channel`) or a real column (a date). "Fast for one channel" or "only this year's data from the warehouse" is the request for a split |
| Grain after a flatten | the element (one row per line) or the parent (one row per order, with figures from its lines) — the human. The second joins the element figures, aggregated, to the parent's figures at the result's grain (`references/arrays.md`), never a `SUM` of the parent's measures over flattened rows |
| Existing dependants | `USED_BY()` before touching anything that already exists; for a column that changes, "Before a column changes" below. Whether the name already exists, and whose it is, is `vql plan` on the file (`exists`, `own`) |

Do not ask about cache, swap, statistics or indexes: they have server defaults. A cache the
human asks for is `/denodo:cache`, once the view returns the right rows; whether a view over a
database runs in that database is not one of them — Verify checks it.

## When the request asks for something the data does not have

A mart is asked for in business words, and those words routinely name a dimension the sources
do not carry — "broken down by sales channel" over sources with no channel column anywhere.
The failure to avoid is inventing it: a plausible-looking expression yields a mart that
answers a different question and says nothing about the substitution.

1. **Establish it, do not assume it.** Read every column of both sides — `vql desc`, or
   `SELECT column_name FROM GET_VIEW_COLUMNS() WHERE input_view_name = '<view>'` — then look
   for the attribute in the neighbouring objects, and check they can be joined to the same
   key at all — in TPC-DS each returns table *is* a channel, and only the store one carries a
   store key.
2. **Then choose, and write the choice into the `DESCRIPTION`:**
   - the attribute is a constant across the data you have → keep the column as a literal
     (`'store' AS sales_channel`). The grain is then the one that was asked for, and a
     second channel arrives later as another `UNION ALL` branch instead of a schema change;
   - it exists somewhere that cannot be joined → leave it out and say where it lives. A mart
     at the grain that *is* joinable is a different object, not a compromise version of this
     one;
   - it exists nowhere → leave it out.
3. **Report the gap in the answer, not only in the DDL.** The human asked for a breakdown;
   they need to hear that one of its axes is not in the data, and what you read to be sure.

The same holds for a measure named loosely — "how many returns" over a file whose rows are
return *lines*. Publish both counts under names that say which is which
(`return_ticket_count`, `return_line_count`) rather than picking one silently.

## Before a column changes: who uses it

"Can this column go", "can we rename it", "what breaks if the source drops it" — asked about
a view that already has dependants, before anything is changed. Everything here only reads.

```sql
-- verified: 9.5.1 (live, 2026-10-07)
-- Can ib_income_band_sk go from bv_income_band?
-- 1. The views that name bv_income_band in their own definition. Only these can use its columns.
SELECT used_by_database_name, used_by_name
  FROM USED_BY()
 WHERE input_view_database_name = 'sales_analytics'
   AND input_view_name = 'bv_income_band'
   AND depth = 1;

-- 2. The definition of each of them: search it for the column
--    (for a metric view, also its ASSOCIATIONS list for the associations of step 3).
DESC VQL VIEW iv_household_income ('includeDependencies' = 'no', 'dropElements' = 'no');

-- 3. The associations that map it.
SELECT association_name, mappings, valid
  FROM GET_ASSOCIATIONS()
 WHERE input_database_name = 'sales_analytics'
   AND input_type = 'views'
   AND input_name = 'bv_income_band';

-- 4. Everything built on a view the column breaks goes down with it.
SELECT used_by_database_name, used_by_name, depth
  FROM USED_BY()
 WHERE input_view_database_name = 'sales_analytics'
   AND input_view_name = 'iv_household_income';
```

In the templates of this skill the answer is: `iv_household_income` uses `ib_income_band_sk`
only in its join's `ON`, and `a_income_band_household` maps it — so the column breaks both,
and `household_income_by_band` and the `household_income` contract with them.

- **Step 2 is not optional, and `COLUMN_DEPENDENCIES()` does not replace it.** That procedure
  traces *output* columns: a column a dependant uses only in `ON`, `WHERE`, `GROUP BY` or
  `HAVING` has no row there, and removing it still turns the dependant `INVALID` —
  *verified: 9.5.1 (live, 2026-09-30)*. An empty answer from it is not "unused". Search the
  whole definition: the `SELECT` list, every `ON`, the filters and the grouping.
- **A view above a broken one keeps `view_status = 'OK'`** and fails on every `SELECT`. So
  step 4 is the list of what breaks without being reported — `GET_VIEWS(… invalid only)`
  names only the views that used the column themselves. An empty step 4 is the good answer:
  nothing is built on top. A metric view that names the column in a dimension or a metric
  is a direct user and goes `INVALID`; one that reaches it only through an association from
  step 3 (`valid = false`) stays `OK`, and every metric grouped or filtered by a dimension
  reached through it fails with `Error applying metric transformation.` — *verified: 9.5.1
  (live, 2026-09-30)*.
- `USED_BY()` finds dependants in every database, and only views: no associations (step
  3), no web services, nothing outside the catalog. The web services that publish the view,
  in every database, with the fields each publishes: `SELECT DISTINCT database_name, ws_name,
  ws_type, column_name FROM GET_CATALOG_METADATA_WS() WHERE schema_database = '<db>' AND
  schema_name = '<view>' AND schema_type = 'view'` — *verified: 9.5.1 (live, 2026-10-07)*;
  it shows only the services you hold `METADATA` on (documentation). What no query finds —
  reports, clients, jobs reading the view — goes into the report as what the list cannot see.
- **Report it as a list the human can act on**: each object, how it uses the column
  (`SELECT` list and which output column, join condition, filter, grouping, mapping), and
  what goes down with it — then what the list cannot see. The decision to go ahead is
  theirs (`/denodo:vql`).
- **The four steps answer it without building anything.** A copy of the real views built to
  rehearse the change in another database becomes a dependant of them: it shows up in their
  `USED_BY()` for everyone else, and their `DROP … CASCADE` takes it along.
- When the change is made, it goes through the view's own file — for a view that has none,
  the recipe below. The output of plain `DESC VQL` is not a file to edit and re-run: it opens
  with `DROP … CASCADE`, which removes the very dependants this section listed.
- **A view with a full cache** (its `DESC VQL` ends with `ALTER VIEW … CACHE FULL`) comes back
  from a changed column with an empty cache: 0 rows for it and everything on it, no error,
  until its load runs again — *verified: 9.5.1 (live, 2026-09-30)*. The load, and the rest
  of what a cache does to a change, is `/denodo:cache`.
- **A remote table loaded from the view is not in `USED_BY()`** — a summary over it is. The
  remote table's query is text in its base view's `DATA_LOAD_QUERY`, and its next `REFRESH`
  after the change fails *after* emptying the table — *verified: 9.5.1 (live, 2026-10-02)*.
  Search `DESC VQL DATABASE <db>` (an administrator or the `metadata_export` role) for the
  view's name — one large text, with the data sources' ciphertexts: never in the project.

**A view with no file yet** — built in Design Studio, the usual case on a server people
already use — changes through a file all the same, started from the server's text of it alone:

```sql
-- verified: 9.5.1 (live, 2026-10-07)
DESC VQL VIEW iv_household_income ('includeDependencies' = 'no', 'dropElements' = 'no');
```

Save the answer as the view's file: `CREATE VIEW` becomes `CREATE OR REPLACE VIEW`, its `CONTEXT`
gains `'formatted' = 'yes'`, and the rest stays as printed — `FOLDER`, description, field
descriptions, key, `TAGS`, the `ALTER VIEW … CACHE` line with its time to live. What the file
leaves out, the apply removes; grants stay — *verified: 9.5.1 (live, 2026-10-07)*. Make the change; a new column
goes last unless the human placed it — one in the middle moves the others for readers by
position. `vql plan` holds it for the yes: show it with the dependants (step 1; all four steps for
a column dropped, renamed or retyped), new description texts where the change makes the old ones
wrong, and for a cached view its reload, which comes back empty (`/denodo:cache`). After the
apply, Verify the view and each dependant, and only then commit the file: a committed file vouches
for the view in a later session's plan. Before a later apply, compare it with the server's text —
an edit made in Design Studio since would be lost. A data source or a base view a wizard built
goes back to Design Studio instead (`/denodo:datasources`).

**"Where does this field come from"** is the question `COLUMN_DEPENDENCIES()` does answer:
with `input_column_name` it walks one field down to the base view and the data source in one
call, with the expression wherever the value is computed. The query, how to read
its rows, and the step from a base view to the table and column in the database are in
`references/dependencies.md`.

**Renaming a view, or moving it to another database,** is the same question one level up:
`ALTER VIEW <old> RENAME <new>` (`references/derived.md`) breaks every dependant that names the
view — step 1 first, for the view itself. With a `marketplace_url`, read its `view-details`
**before** the change and match the rename (`/denodo:marketplace`, "A view in the marketplace is
renamed, recreated or moved"), or the next synchronisation removes its element with every tag,
category and endorsement; a move to another database cannot be matched. Report every client
that reads it by name — reports, JDBC, ODBC, REST and OData URLs (`connectionUris`). Rename it in
its file too, or the next apply brings the old name back; a moved view loses its grants.

## Reference

- `references/derived.md` — the full `CREATE VIEW` grammar, field properties,
  `USING PARAMETERS`, `WITH CHECK OPTION`, `CONTEXT`, what `ALTER VIEW` can and cannot
  change, `DROP VIEW`.
- `references/interface.md` — the full `CREATE INTERFACE VIEW` grammar, field mapping,
  `ALTER INTERFACE VIEW`, the states an interface view can be in and what each means.
- `references/associations.md` — multiplicity in detail, role preconditions, composite
  mappings, `GET_ASSOCIATIONS()` columns, what an association changes for clients.
- `references/unions.md` — `UNION`, `UNION ALL` and `EXTENDED UNION ALL`, how the branches'
  columns are matched and named, which union shapes skip a branch and which do not, reading
  `GET_QUERY_EXECUTION_PLAN()`, `NULL` partition keys, column descriptions over a union.
- `references/arrays.md` — `FLATTEN` in full (empty arrays, renamed fields, arrays inside
  registers, two arrays), a parent summary that keeps every parent, `NEST`, `REGISTER`, the
  types they leave behind, element access by position, checking a flatten.
- `references/dependencies.md` — `USED_BY`, `VIEW_DEPENDENCIES` and `COLUMN_DEPENDENCIES`
  in full: what each one cannot see, measured use by use, reading a field's lineage down to
  the source table, the name and privilege rules.
- `references/delegation.md` — reading the plan for delegation, the causes measured on SQL
  Server and PostgreSQL, why the answer is per query, why `GET_DELEGATED_SQLSENTENCE` is not
  the check, and the options to put in front of the human.
- `references/one-row-per-key.md` — the current row of a history, the latest version per key in
  a database and from a file, ties, `NULL` dates, a feed loaded twice, and the checks.

## Verify

After applying, always:

| Question | Read-back |
|---|---|
| Did the objects land, and where | `SELECT name, type, subtype, folder FROM GET_ELEMENTS() WHERE input_database_name = '<db>' AND type = 'view'` — `subtype` is `base`, `derived`, `interface` or `metric` (*verified: 9.5.1 (live, 2026-10-05)*); associations are `type = 'association'`. `type` is an output column and takes `IN`; the `input_…` parameters take `=` only |
| **Is anything broken now** | `SELECT name, view_type, view_status FROM GET_VIEWS() WHERE input_database_name = '<db>' AND input_retrieve_invalid_views_only = true` — **empty is the only good answer** — not the whole one: Silent failure 1. `view_type` here is the same fact as `subtype` above in numbers: `0` base, `1` derived, `2` interface, `5` metric |
| Does it carry rows | `SELECT * FROM <view> LIMIT 10`, and a count that can be checked against the input |
| **Did the join keep every fact** | add the mart's row counters back up and compare with the fact it was built from: `SUM(<row count column>)` over the mart equals `COUNT(*)` of the input, minus exactly the rows you decided to drop. A join that quietly dropped the unmatched facts, or doubled them on a duplicated dimension key, passes every other check in this table |
| Schema of the contract | `vql desc --env dev --database <db> <interface view>` — the columns the consumer sees |
| **Which implementation is actually behind a contract** | `vql desc … <interface view> --vql` — plain `DESC` can never tell you: it shows the declared schema whatever is underneath. This is also how you prove a swap happened |
| Nothing changed for the consumer | take the schema and a `SELECT … LIMIT n` through the contract **before** the change, keep them, and diff against the same two afterwards. That is the only claim the consumer cares about, and it is cheap to make checkable |
| Are the associations still whole | `SELECT association_name, mappings, valid FROM GET_ASSOCIATIONS() WHERE input_database_name = '<db>' AND input_type = 'views'` — **`valid` must be `true`** |
| One association in full | `vql desc --env dev --database <db> <name> --type association` — roles, multiplicities, mappings, principal side |
| Who depends on this view | `SELECT view_name, used_by_database_name, used_by_name, depth FROM USED_BY() WHERE input_view_database_name = '<db>' AND input_view_name = '<view>'` — run it **before** a change, not after. For one column, "Before a column changes" |
| **Does a view over a database run in the database** | for every view whose base views are JDBC: `SELECT execution_plan FROM GET_QUERY_EXECUTION_PLAN() WHERE input_query = 'SELECT * FROM <view>'`. Delegated whole: exactly one `SQLSentence =`, and it holds the joins and the `GROUP BY`. `noDelegationCauses = [The aggregate function 'median' cannot be delegated to this database]` names what keeps the rest in Denodo. Two or more `JDBC ROUTE (` blocks with **no cause printed** mean two data sources, joined in Denodo — then a `GROUP BY` in the big table's `SQLSentence` (`optimizationsApplied = [Aggregation Push-down]`) means groups travel, its absence means every row does. Anything but the first is Silent failure 3 — unless `optimizationsApplied` names `Data Movement` and one `SQLSentence` joins the moved copy (`/denodo:materialize`) |
| **Does each branch of a union arrive whole** | `SELECT channel, COUNT(*), SUM(<measure>) FROM <union> GROUP BY channel` — or `GROUP BY` a `CASE` of the branch conditions when the split is a real column — against `COUNT(*)` and `SUM` of each source view under its own branch condition. It catches a branch whose columns are out of order and the rows a `NULL` partition key lost — neither raises an error |
| **Is the declared primary key unique** | `SELECT <key columns>, COUNT(*) FROM <view> GROUP BY <key columns> HAVING COUNT(*) > 1` — no rows. Denodo does not enforce a `PRIMARY KEY`; over overlapping union branches or a flatten, this is the proof nothing was counted twice |
| **Does a one-source query read one source** | `SELECT execution_plan FROM GET_QUERY_EXECUTION_PLAN() WHERE input_query = '<the query, quotes doubled>'`: `optimizationsApplied = [Branch Pruning]`, and one `BASE PLAN (` block per source read, its `name = …` on the next line; no block at all means the query reads nothing. It plans without running the query, so an ad-hoc union can be checked before the view exists. `DESC QUERYPLAN` answers with nothing through the tool, and `TRACE` with the plain result |
| **Did the flatten keep the right rows** | `COUNT(*)` of the element view against `COUNT(<element field>)` over `FLATTEN` of the source, and a filter on one parent key returning that parent's elements only |

**Silent failure 1: a replaced view invalidates everything above it, without an error.**
`CREATE OR REPLACE VIEW` that renames or drops a column is accepted; every derived and
interface view that used that column goes to `view_status = 'INVALID'` and every
association that mapped it goes to `valid = false`. Nothing is reported at DDL time, the
replaced view itself still selects fine, and the failure lands on whoever queries the
dependant next — *verified: 9.5.1 (live, 2026-09-10)*. The views built on those dependants
do not even change status: they stay `OK` and fail on `SELECT` — *verified: 9.5.1 (live,
2026-09-30)*. Adding a column is safe; restoring the column repairs the views and
associations automatically. Not a REST web service that published the field: it drops the
field from its own definition and does not take it back — *verified: 9.5.1 (live,
2026-09-30)*.

**Silent failure 2: `SET IMPLEMENTATION` does not check the schema.** An implementation
whose column names do not match the interface's field list, or that is missing a field
entirely, is accepted by `CREATE OR REPLACE INTERFACE VIEW` without a word. `DESC` keeps
showing the declared schema. Only `SELECT` fails, with a message that names nothing:
`Error executing query. Total time 0.0 seconds. HOUSEHOLD_INCOME [INTERFACE] [ERROR]` —
*verified: 9.5.1 (live, 2026-09-10)*. **A `SELECT` through the contract is part of
applying it**, every time, including a swap of the implementation.

**Silent failure 3: a view over a database that does not run in the database.** One
expression the database cannot run — `MEDIAN` on SQL Server, a `CAST` of text to integer on
PostgreSQL — keeps its node and everything above it in Denodo. The database still does the
joins below it, and every joined row travels to Denodo to be aggregated there. The rows are
right, nothing reports an error, and the cost grows with the fact table: a second on sample
data, minutes in production — *verified: 9.5.1 (live, 2026-09-30)*. Which expressions
delegate depends on the database, so read the plan (Verify), not a list. Then:

- **Tell the human, and let them decide.** Name the expression and the column it computes,
  or the two data sources: every row below that point is read into Denodo, at production
  volume. Swapping the function for one that delegates (`AVG` for `MEDIAN`) changes the
  answer, and even an exact rewrite is a second definition of the measure: both are their
  call. When you cannot ask, build what was asked and put the cost and the options in the
  report.
- **The answer is per query:** plan `SELECT *` and the consumer's own query; a `COUNT(*)` or
  key check never runs the blocking column.

`references/delegation.md`: the measured causes, how to read each node, the options to offer.

So the read-back after any change to something that already existed is: `USED_BY()`
before, `GET_VIEWS(… invalid only)` and `GET_ASSOCIATIONS().valid` after, then a `SELECT`
through each dependant that matters.

These read-backs, kept in files the team's CI runs on every change — the counts that add up,
the unique key, nothing `INVALID`, the contract, the plan — are `/denodo:testing`, with the
Denodo Testing Tool. A mart that will be rewritten later gets them before the rewrite.

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
| `ALTER VIEW … RENAME` of a view the Data Marketplace lists | nothing — accepted | the next synchronisation removes its marketplace element, with every tag, category and endorsement on it: `view-details` before the rename, and the marketplace half from `/denodo:marketplace` |
| `SET IMPLEMENTATION` over a mismatched view | nothing — accepted | `SELECT` through the contract; map the fields |
| `DROP VIEW v` with dependants | `error removing view: There are some elements that depend on this one` | `USED_BY()` first, then ask the human — `CASCADE` takes the dependants with it |
| `DROP ASSOCIATION a` when there is none | `error removing association: Error loading association 'a'.` | `DROP ASSOCIATION IF EXISTS` — it has no `CASCADE`, unlike the view drops |
| `WHERE input_database_name = …` on `VIEW_DEPENDENCIES()` | `Field not found 'input_database_name'` | that one is `input_view_database_name`, like `USED_BY()` |
| `WHERE input_type IN ('view','association')` on `GET_ELEMENTS()` | nothing — zero rows | `input_type` takes the documented plural values, with `=` only: `input_type = 'views'`, then `input_type = 'associations'` — or filter the output column `type IN ('view','association')` |
| union branches listing the same columns in a different order | nothing — accepted; queries then disagree about which value is which | same columns, same order, same aliases in every branch |
| `SELECT 'web' AS channel, … FROM x UNION ALL …` with no `WHERE` per branch | nothing — `WHERE channel = 'web'` still reads every source | wrap each branch: `SELECT * FROM ( … ) w WHERE channel = 'web'` |
| `SELECT 'web' AS channel … WHERE channel = 'web'` | `Field not found 'channel' in view with schema …` | the `WHERE` outside, around a subquery |
| `QUALIFY ROW_NUMBER() OVER (…) = 1`; or `ROW_NUMBER()` in a view over a file | `Syntax error … near 'ROW_NUMBER'`; or `OK` at create, then `Function row_number is not executable` on `SELECT` | the rank in a subquery, `WHERE <rank> = 1` outside; over a file, the anti-join — `references/one-row-per-key.md` |
| `( col ( description = '…' ) )` on a union | `The field properties can only be specified for derived fields` | on a view over the union |
| `UNION DISTINCT`, `EXTENDED UNION` | `Syntax error … near 'DISTINCT'` / `near 'SELECT'` | `UNION`; the extended union exists only as `EXTENDED UNION ALL` |
| `COUNT(*)` over `FLATTEN` as the number of lines | nothing — each order without lines counts as a line | `COUNT(<element field>)`, or the template's `IS NOT NULL` |
| `SELECT lines …` after `FLATTEN … ( o.lines )` | `Field not found 'lines' in view with schema …` | the array is gone; select its fields |
| `NEST(line_no AS n, …)` | `Syntax error … near 'AS'` | rename in the view below |
| no row in `COLUMN_DEPENDENCIES()` for a column, read as "nothing uses it" | nothing — a join key, a filter or a grouping column is not an output column | read the definition of each direct dependant ("Before a column changes") |
| `SELECT` from a view whose column went away underneath | `View without search methods:` | the view is `INVALID`: `GET_VIEWS(… invalid only)`, then restore the column or change the dependant |
| `USED_BY()` / `COLUMN_DEPENDENCIES()` with `'%sales%'`, or a name in the wrong case | `… USED_BY [STORED PROCEDURE] [ERROR] Received exception with` — nothing more | the exact name as `GET_ELEMENTS()` prints it; `%` and `_` work in `GET_ELEMENTS()`, `GET_VIEWS()`, `GET_VIEW_COLUMNS()` only |
| a SQL back from `GET_DELEGATED_SQLSENTENCE`, read as "delegated" | nothing — it returns the delegated part only | `GET_QUERY_EXECUTION_PLAN()`: one `SQLSentence`, no `noDelegationCause` |
| "no `noDelegationCause` in the plan", read as "delegated" | nothing — two data sources print no cause | count the `JDBC ROUTE (` blocks as well |

Dropping is the human's call — `/denodo:vql`. Before asking, show what goes with it:
`USED_BY()` for a view, `GET_ASSOCIATIONS()` for the associations that hang off it.
