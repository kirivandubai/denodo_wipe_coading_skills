---
name: semantics
description: Use when the views of an existing Denodo 9.5 database have to be understood by people and by AI consumers — the Denodo MCP Server, Assisted Query in the Data Marketplace, the AI SDK. Auditing a database for views and fields without descriptions, primary keys that are missing or not unique, missing associations and the VDP tag the MCP Server shows views by; writing view, field, association and tag descriptions from the data (ALTER VIEW … DESCRIPTION, ALTER COLUMN … ADD (DESCRIPTION …), ADD PRIMARY KEY). Also for "describe / document these views", "prepare this database for AI, MCP or Assisted Query", "why does the agent not see this view through MCP", a description that says the wrong thing. Not for building or changing what a view computes — /denodo:views; not for marketplace-only metadata (logical names, property groups, marketplace tags) — /denodo:marketplace.
---

# Make views understandable: descriptions, keys, associations, visibility

AI consumers of Denodo build their prompts from the metadata of a view, not from its rows.
The Denodo MCP Server, Assisted Query and the AI SDK all read the view's description, each
field's description, type, primary-key and nullable flags, the names and descriptions of its
tags, and its direct associations — joins are built only from associations. The MCP Server
also shows a view at all only when it carries the tag it is configured with. A view with a
cryptic name and no description is answered with a guess; a wrong description or a primary
key that is not unique is answered with confidence.

**This skill audits a database and fills that metadata in:** view, field, association and
tag descriptions, primary keys, the associations that are missing, and the MCP visibility
tag. Logical names, property groups and descriptions edited in the marketplace live only in
the Data Marketplace (`/denodo:marketplace`, or its UI); configuring the MCP Server, the AI
SDK or Assisted Query is the administrator's. Applying files is `/denodo:execute`; the
working loop and the safety rule are `/denodo:vql`.

**A view you are building now** (`/denodo:views`) gets the same metadata in its own file:
profile it (section 2), write the texts (section 3), put them and the MCP tag in its
`CREATE OR REPLACE VIEW` (section 5), apply and verify — no approval step, it is yours.
What the data cannot settle stays out of the text and goes to the human as a question.

## The rule: from the data, approved before it is written

1. **Every sentence comes from the data, the view's definition or the human.** A column name
   is a question, not an answer: a `count` column holding `-1` for a fifth of the rows, a
   `code` column that turns out to be a region, a `GROUP BY` on a label that two keys share
   — none of it shows in a name. What the data cannot settle (what `-1` means, the currency,
   whether an amount is monthly or yearly) is a question in your proposal, never "probably"
   in a description.
2. **Nothing is written to a view you did not create in this session until the human says
   yes to the texts** — whatever the statement: `ALTER VIEW`, `ALTER TAG`, or the view
   re-declared with `CREATE OR REPLACE VIEW`. Re-declaring a view to change its metadata is
   still writing to it, and it rewrites its stored definition besides. The texts are what
   every consumer will believe; the human who owns the views approves them.
3. **When you cannot ask** — the human is away, the go-live is close — the answer is the
   audit, the proposal and the statement file, not the statements applied. Say which file
   to apply and what applying it changes. The one exception is a view the human named to be
   made visible to an agent: that request is the yes for its tag (MCP visibility, below).

| Rationalization | Reality |
|---|---|
| "`CREATE OR REPLACE` is mine to do; only `ALTER` needs a yes" | Re-declaring someone's view to change its description is a write to their view. The rule is about the object, not the keyword. |
| "The request was exactly to describe these views" | They asked for descriptions. The yes is to the texts, after they read them. |
| "A wrong description misleads the AI, so fixing it cannot wait" | Show the wrong one with the evidence first; the owner may know why it says what it says. |
| "The wrong key tells the AI the view has one row per customer" | True — and the fix is a proposal with the counts, not an `ALTER` nobody reviewed. |
| "The view is not in the MCP tag yet, so tagging it is harmless" | The tag publishes the view's rows to every agent on that server. Which views get it is the owner's decision, view by view. |

## 1. Audit — read-only

```sql
-- verified: 9.5.1 (live, 2026-09-30)
SELECT e.name, e.subtype, e.folder,
       CASE WHEN e.description IS NULL OR TRIM(e.description) = '' THEN 'none' ELSE 'yes' END AS view_description,
       c.fields, c.undescribed_fields, c.pk_fields,
       CASE WHEN t.view_name IS NULL THEN 'no' ELSE 'yes' END AS mcp_tag
  FROM GET_ELEMENTS() AS e
       LEFT OUTER JOIN (
           SELECT view_name, COUNT(*) AS fields,
                  SUM(CASE WHEN column_remarks IS NULL OR TRIM(column_remarks) = '' THEN 1 ELSE 0 END) AS undescribed_fields,
                  SUM(CASE WHEN column_is_primary_key THEN 1 ELSE 0 END) AS pk_fields
             FROM GET_VIEW_COLUMNS()
            WHERE input_database_name = 'sales_analytics'
            GROUP BY view_name) AS c
       ON e.name = c.view_name
       LEFT OUTER JOIN (
           SELECT DISTINCT view_name
             FROM GET_VIEW_TAGS()
            WHERE input_database_name = 'sales_analytics' AND tag_name = 'mcp' AND column_name IS NULL) AS t
       ON e.name = t.view_name
 WHERE e.input_database_name = 'sales_analytics' AND e.input_type = 'views'
 ORDER BY subtype, name;

SELECT view_name, column_name, column_is_primary_key, column_is_nullable, column_remarks
  FROM GET_VIEW_COLUMNS()
 WHERE input_database_name = 'sales_analytics';

SELECT association_name, association_description, mappings, valid
  FROM GET_ASSOCIATIONS()
 WHERE input_database_name = 'sales_analytics' AND input_type = 'views';
```

One row per view, then every field, then every association — the whole database in three
calls. `'mcp'` in the first query is the tag the MCP Server is configured with (MCP
visibility, below) — put in the one the human names; until you know it, drop the second
`LEFT OUTER JOIN` and the `mcp_tag` column rather than guess. Then, per view the consumers
will read:

- **An existing description is checked, not trusted.** "One row per household" is a claim
  about the grain; the profile (next section) confirms it or not. Descriptions copied from
  another view are common.
- **A declared primary key is checked**: `SELECT COUNT(*), COUNT(<key>), COUNT(DISTINCT <key>)
  FROM <view>` — all three equal. For a composite key: `SELECT COUNT(*) FROM (SELECT <k1>,
  <k2> FROM <view> GROUP BY <k1>, <k2> HAVING COUNT(*) > 1) d` is `0`, and `COUNT(<k1>)`,
  `COUNT(<k2>)` equal `COUNT(*)`. Denodo does not enforce keys. A declared key also marks
  its columns `NOT NULL` in the metadata, so a wrong key is two wrong facts.
- **A view with no key to give it** — an aggregate grouped by a label two keys share, or
  with a `NULL` group — gets none; its description says what one row is instead.
- **Missing associations**: a column that carries another view's key (same values, 0
  orphans — the check is in `/denodo:views`) with no association between the two. The AI
  cannot join them. Creating one is the association template in `/denodo:views`; between
  views you did not create it goes into the proposal like the texts — it becomes a
  dependant of both views, and their owner's `DROP VIEW` then needs `CASCADE`.
- **Tags**: `DESC TAG <tag>` gives its name and description only, no assignments — the AI
  reads that description; a tag without one tells it nothing.
- `column_remarks` is the description a consumer sees, **inherited ones included**: a field
  that passes a column through unchanged shows the description of the column below. `DESC
  VQL` shows only the view's own. Base views: their field descriptions reach every view
  above that passes the column through, so one description there can cover many views.
- **A metric view** (`subtype = 'metric'`) is described like any view, field by field —
  its dimensions and metrics. A view built over it inherits the descriptions of the
  dimensions it passes through and none of the metrics: its `evaluate_metric` columns need
  their own (`/denodo:metrics`).

## 2. Profile — what the data says

```sql
-- verified: 9.5.1 (live, 2026-09-30)
CONNECT DATABASE sales_analytics;

-- The grain: the key the description will name. Equal counts, no NULL key.
SELECT COUNT(*) AS row_count, COUNT(household_sk) AS keys_not_null,
       COUNT(DISTINCT household_sk) AS distinct_keys
  FROM iv_household_income;

-- Every column in one pass: NULLs, distinct values, range, padding.
SELECT COUNT(buy_potential) AS buy_potential_not_null,
       COUNT(DISTINCT buy_potential) AS buy_potential_distinct,
       MAX(LEN(buy_potential)) AS buy_potential_len,
       MAX(LEN(TRIM(buy_potential))) AS buy_potential_len_trimmed,
       COUNT(vehicles) AS vehicles_not_null,
       MIN(vehicles) AS vehicles_min, MAX(vehicles) AS vehicles_max,
       COUNT(DISTINCT vehicles) AS vehicles_distinct
  FROM iv_household_income;

-- The values themselves, for each column with a short list.
SELECT vehicles, COUNT(*) AS row_count
  FROM iv_household_income GROUP BY vehicles ORDER BY vehicles;
```

What to read out of it, and where it goes:

| You see | It means | The description says |
|---|---|---|
| `distinct_keys` = `row_count`, no `NULL` key | the grain | "One row per household (`household_sk`)" |
| a value far outside the rest (`-1`, `0`, `9999`, `'Unknown'`) | a sentinel | what it stands for — if the data or the human says; otherwise a question |
| `LEN` > `LEN(TRIM)` | padded text | "compare with `TRIM(x) = '…'`" — an equality on the raw value finds nothing |
| a short value list | codes | each code with its meaning, when known |
| `NULL`s in a column | missing values | what a `NULL` stands for, when known |
| an aggregate grouped by a label | one row per label, not per key | two keys with the same text are one row — compare the label's distinct count with the key's |
| a join in the definition (`DESC VQL`) | rows dropped (`INNER`), doubled, or — an outer join under a `GROUP BY` — gathered into one `NULL` row | which rows are in, and what the `NULL` row holds |

Each query reads the whole view. Over a view with statistics gathered, `SELECT * FROM
GET_VIEW_STATISTICS() WHERE input_database_name = '<db>' AND input_name = '<view>'` gives
rows, distinct values, `NULL`s and ranges without reading it (0 rows = not gathered).

## 3. The texts

**A view description** says what one row is and its key; what the view leaves out or adds
(a filter, a join that drops rows, a group of `NULL`s); how to query it where that is not
obvious (padding, a sentinel to exclude). **A field description** says what the value means,
its unit, its values and what each code or sentinel stands for, and what `NULL` means. **An
association description** says what the relationship is in business words. **A tag
description** says what carrying the tag means.

- No row counts or `NULL` counts: the next load changes them, and a consumer reads them as
  today's. A count belongs in a description only when it is the point, with its date.
- No restating the name (`dep_count` → "The dependent count"). No "probably", "likely",
  "appears to".
- Keep a correct description; propose a replacement for a contradicted one, with the
  evidence. A description of up to 4,000 characters; a few sentences are enough.
- `''` inside a text is a quote: `'the band''s households'`.

## 4. The proposal — what the human approves

```
Database claims_analytics — 12 views audited.
Wrong now:
  policies: PRIMARY KEY holder_id — 4,210 distinct in 9,800 rows. Proposed: policy_id (9,800 distinct, no NULL).
  claims_by_region: its description is the one of claims_by_month. Proposed: "Claims per region: one row per …"
New texts:
  | object            | proposed text                                    | from the data            |
  | policies (view)   | Insurance policies. One row per policy (…)       | 9,800 rows = 9,800 keys  |
  | policies.status   | Policy status: A active, L lapsed, X <your answer> | values A, L, X          |
Questions: what does status X mean? Is premium monthly or yearly?
MCP: which views should the agent see? (tag <name>, from the MCP Server's configuration)
Statements: semantics/claims_analytics.vql — applied after your yes.
```

## 5. Write it where the view is defined

| Where the view's definition lives | Write the metadata |
|---|---|
| a `.vql` file in the project that is applied (git, CI, `/denodo:views`) | **in that file**: `DESCRIPTION`, `PRIMARY KEY`, `TAGS ( … )` and `( <field> ( description = '…' ) )` in the view's own `CREATE OR REPLACE VIEW`, in the clause order of `/denodo:views`; then re-apply it |
| only on the server (built in Design Studio) | an `ALTER` file of its own, `semantics/<database>.vql` — the template below. Do not re-declare the view to change its metadata |
| a base view | `ALTER TABLE <view> …`, the same forms as below |

Statements still waiting for a yes go into a file of their own, next to the one being
applied — each file is applied whole, so what has a yes never goes out with what has not.

**The file wins.** Re-applying a `CREATE OR REPLACE VIEW` without these clauses removes the
description, the field descriptions, the primary key and every tag assignment of that view,
silently — including the MCP tag, so the view disappears from the agent. An `ALTER` over a
view that has a file lasts until the file is next applied.

```sql
-- verified: 9.5.1 (live, 2026-09-30)
CONNECT DATABASE sales_analytics;

ALTER VIEW household_income_by_band
    DESCRIPTION = 'Households per income band. One row per income band (income_band_sk); a band with no households has no row.';

ALTER VIEW household_income_by_band (
    ALTER COLUMN household_count ADD ( DESCRIPTION = 'Number of households in the band.' )
    ALTER COLUMN avg_dependents ADD ( DESCRIPTION = 'Average number of dependents of the band''s households, rounded to two decimals.' )
);

ALTER VIEW household_income_by_band ADD PRIMARY KEY ( 'income_band_sk' );

ALTER ASSOCIATION a_income_band_household
    DESCRIPTION = 'The income band a household belongs to. Every household has one band; a band has many households.';

ALTER TAG mcp
    ADD_TO ( VIEWS ( sales_analytics.household_income_by_band ) COLUMNS () )
    REMOVE_FROM ( VIEWS () COLUMNS () );
```

- Each statement changes that metadata and nothing else: the cache, the views built on it,
  their status and the privileges granted on it stay as they were — *verified: 9.5.1 (live,
  2026-09-30)*. The tool marks each one `destructive: alter`.
- **`ADD PRIMARY KEY` replaces a declared key** without an error — the old columns lose
  the flag and their `NOT NULL`. `ALTER VIEW <view> DROP PRIMARY KEY` removes it.
- `ALTER TAG … ADD_TO` adds to the tag's assignments and keeps the others. The tag must
  exist (`/denodo:catalog`). `ALTER TABLE <base view> ( ALTER TAGS ( … ) )` replaces the whole
  set of the view's tags — do not use it to add one.
- A field description on a view whose field passes a column through replaces the inherited
  one for that view only; `ALTER COLUMN <field> DROP DESCRIPTION` brings the inherited one
  back. A field computed by an expression, a cast or an aggregate inherits nothing.
- An empty text, `DESCRIPTION = ''`, removes a view's description.

## MCP visibility — "the agent does not see this view"

The MCP Server shows only views tagged with one of the tags in `mcp.visibility.tags` of its
`config/application.properties`; the file it ships with sets `mcp`. When the property is not
set, it shows every view its user may read, in every database, base views included. That
file is on the MCP Server's host, not in Denodo: ask the human which tag, or read their copy
of it. "We run the shipped configuration" settles it as `mcp`, and the tag carried by the
views the agent does see confirms it. Otherwise do not guess a tag name, and do not create
one to make a view appear.

In order:

1. **The tag is on the view, not only on a column**:
   `SELECT view_name, column_name FROM GET_VIEW_TAGS() WHERE input_database_name = '<db>' AND input_view_name = '<view>' AND tag_name = '<tag>'`
   — a row with an empty `column_name`. A tag on a column leaves the view hidden
   (documentation).
2. **The agent's user may read it.** The MCP Server runs everything with the Denodo
   credentials its client sends, so the user is the agent's own account (ask the human
   which). `SELECT dbconnect, elementname, elementexecute FROM GET_CATALOG_EFFECTIVE_PERMISSIONS()
   WHERE input_user_name = '<user>' AND input_database_name = '<db>'` — the database row
   needs `dbconnect = true`, the view's row `elementexecute = true`. A user that exists only
   in the identity provider is not returned (documentation). Granting is a change of who
   reads what: `/denodo:security`, after the human's yes.
3. **The server has picked the change up**: it refreshes its schema while
   `mcp.schema-refresh.enabled` is on; otherwise it needs a restart. A new client session
   lists views again.
4. The view's file does not carry the tag → the next apply of that file hides the view
   again (section 5).

Adding the tag is a write to a shared object that publishes the view's rows to every agent on
that server: the human names the views. "Make `<view>` visible to the agent" names one — that
is the yes for the tag on that view, and only for it; its missing description, and every
other view, go into the proposal. The statement is `ALTER TAG … ADD_TO`, plus `TAGS ( <tag> )`
in the view's file if it has one — never a re-declared view. The tag is server-wide, but
`ADD_TO` one view changes nothing else about it: its description and other assignments stay.
With the shipped configuration (`mcp.tools.view-tag=mcp`, deprecated) the same tag also makes
the MCP Server create a query tool of its own for the view.

## After writing: when each consumer sees it

- **The MCP Server** reads Denodo directly — the next schema refresh.
- **Assisted Query and the AI SDK** read through the Data Marketplace: nothing changes for
  them until the marketplace is synchronised with Denodo (`/denodo:marketplace`, a
  server-wide call that needs its own yes — and the way to see whether the database is in
  the marketplace at all, on every registered server), and the AI SDK until its
  `getMetadata` runs again for that database or tag — whoever runs the SDK does that.
- The AI SDK pointed at a **database** reads every view in it, base views included; pointed
  at a **tag**, only the tagged ones. Which it is decides whether base views need describing
  for it.

## Verify

| Check | Query | Expect |
|---|---|---|
| View descriptions | the audit query, section 1 | `view_description = 'yes'` for every view you wrote |
| Field descriptions | `SELECT column_name, column_remarks FROM GET_VIEW_COLUMNS() WHERE input_database_name = '<db>' AND input_view_name = '<view>'` | your texts; an unchanged field still shows the inherited one |
| Primary key | the same query with `column_is_primary_key` | the key you proposed, and only it |
| The key holds | `SELECT COUNT(*), COUNT(DISTINCT <key>) FROM <view>` | equal |
| Association descriptions | `SELECT association_name, association_description FROM GET_ASSOCIATIONS() WHERE input_database_name = '<db>' AND input_type = 'views'` | your texts, `valid = true` |
| MCP tag | `SELECT view_name FROM GET_VIEW_TAGS() WHERE input_database_name = '<db>' AND tag_name = '<tag>' AND column_name IS NULL` | exactly the views the human named — `ADD_TO` a view that does not exist succeeds and records nothing |
| The file agrees | `vql desc --env dev --database <db> <view> --vql` against the view's file | the same clauses — or the next apply undoes them |

## Silent failures

Each runs without an error — *verified: 9.5.1 (live, 2026-09-30)*.

| You did | What consumers get | Instead |
|---|---|---|
| 1. `ALTER` on a view whose `.vql` file is applied later | description, field descriptions, key and tags gone after that apply; the view drops out of MCP | the metadata in the file |
| 2. declared a key without counting | a key that is not unique, and its columns marked `NOT NULL` — the AI counts and joins as if both were true | the count first |
| 3. described only the top view | fields computed by an expression or aggregate stay empty; pass-through fields inherit from below | describe computed fields where they are computed |
| 4. `ALTER TAG … ADD_TO` a misspelt view | `ok`, no assignment | read `GET_VIEW_TAGS()` back |
| 5. `ALTER TABLE <base view> ( ALTER TAGS ( VIEW ( mcp ) COLUMNS () ) )` | every other tag of that view and of its columns removed | `ALTER TAG <tag> ADD_TO` |
| 6. `ADD PRIMARY KEY` on a view that has one | the old key silently replaced | read the key first (audit, section 1) |

A tag on a column only, not on the view, leaves the view hidden from the MCP Server
(documentation only — the MCP Server manual speaks of views tagged).

## Common mistakes

| You wrote | Server says | Fix |
|---|---|---|
| a view description over 4,000 characters | `Error storing view '<view>': Error accessing the metadata while loading/storing objects` | shorten it |
| `WHERE input_view_name IN ('a', 'b')` on a `GET_*` procedure | nothing — zero rows | one query per view, or the whole database and filter on `view_name` |
| `DESCRIPTION 'x'` without `=` | `Syntax error: Exception parsing query near '''` | `DESCRIPTION = 'x'` |
| `SELECT e.name FROM GET_ELEMENTS() AS e … ORDER BY e.name` — one procedure, aliased | `Error in ORDER BY clause: Invalid field name: e.name` | `ORDER BY name` — over a join of procedures both work |

## Reference

- `references/metadata.md` — what each AI consumer reads and from where, every statement
  form for views, base views, interface views, associations and tags, what survives which
  statement, inheritance in full, the procedures that read metadata, statistics, and the
  Denodo Assistant procedures that draft descriptions.
