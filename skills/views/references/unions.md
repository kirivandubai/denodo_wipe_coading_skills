# Unions in full

Everything `/denodo:views` leaves out of the union template: the three spellings, how the
columns of the branches are matched, which union shapes let the optimizer skip a branch, and
how to see that it did. `INTERSECT` and `MINUS` are not covered.

## Spellings

| You write | The server does | Note |
|---|---|---|
| `UNION ALL` | the SQL union: branches matched **by position**, duplicates kept | `DESC VQL` shows it as `SQL UNION ALL` unless the view carries `CONTEXT ('formatted' = 'yes')` — *verified: 9.5.1 (live, 2026-09-30)* |
| `UNION` | the SQL union with duplicates removed | the whole result is compared row by row; `a UNION ALL b UNION c` removes the duplicates of all three. It also stops the optimizer from pushing a `GROUP BY` or a join below the union |
| `SQL UNION ALL`, `SQL UNION` | the same two, spelled explicitly | — |
| `EXTENDED UNION ALL` | Denodo's own union: branches matched **by name**, a column missing from a branch is `NULL` there | Design Studio's *Union (extended)* |
| `UNION DISTINCT`, `EXTENDED UNION` | `Syntax error … near 'DISTINCT'` / `near 'SELECT'` | there is no deduplicating extended union |

Different column counts are refused: `Invalid UNION view, views must have the same number of
columns`. Different types are not: an `int` branch under a `text` branch makes the column
`text`, an `int` under a `decimal` makes it `decimal` — silently. Cast in the branch when the
sources disagree.

A server property, `com.denodo.vdb.union.enableStandardSQLUnion = 'false'`, turns plain
`UNION` / `UNION ALL` into the extended union (documentation 9.5). A union whose branches
list the same columns in the same order under the same names means the same thing either
way, which is one more reason to write them like that.

## How the SQL union matches columns

By position — the names are not compared. What the server then *calls* each column is not the
first branch's name, as in standard SQL: at each position it takes the name from a later
branch whenever that name already exists somewhere among the columns. Measured on 9.5.1
(*live, 2026-09-30*):

| Branches | Header of the result |
|---|---|
| `a, b` ∪ `c, d` | `a, b` |
| `a, b` ∪ `b, a` | `b, a` — the first branch's `a` is now called `b` |
| `a, b` ∪ `b, c` | `b, b` — two columns with one name |
| `a, b, c` ∪ `a, c, b` | `a, c, b` |

A view built on such a union is accepted, and then **different queries against it disagree**.
Over `1 AS qty, 2 AS reason UNION ALL 3 AS reason, 4 AS qty`: `SELECT qty` returns `1, 3`,
`SELECT qty, reason` returns `(4, 3), (2, 1)`, and `WHERE qty = 1` returns no rows. There is
no ordering of the branches that makes this safe; the only safe shape is every branch listing
the same columns, in the same order, under the same aliases.

`EXTENDED UNION ALL` matches `a, b` ∪ `b, a` correctly by name. Its failure is the opposite
one: an alias that differs by a letter becomes an extra column, `NULL` in every other branch,
where the SQL union would have refused the column count.

`ORDER BY` and `LIMIT` after the last branch apply to the whole union.

## Partitioned unions: reading only the branch a query needs

When a query's `WHERE` contradicts the condition a branch is defined by, the optimizer removes
that branch from the plan ("Branch Pruning"). The branch has to *carry* a condition for this
to happen. Every row below was checked with one branch pointing at a file that does not
exist, so a branch that was not pruned failed the query — *verified: 9.5.1 (live,
2026-09-30)*:

| Shape of the union | `WHERE channel = 'web'` reads |
|---|---|
| a constant per branch, `SELECT 'store' AS channel, … FROM a UNION ALL SELECT 'web' AS channel, … FROM b` | every branch |
| the same, with each branch a view of its own holding only the constant | every branch |
| each branch a subquery with a `WHERE` on its constant (the template) | the web branch only |
| each branch two views: one adds the constant, a second one filters on it (documentation's recipe) | the web branch only |
| any of the pruning shapes as `EXTENDED UNION ALL` | the web branch only |

- The `WHERE` has to sit outside the `SELECT` that defines the constant:
  `SELECT 'web' AS channel … WHERE channel = 'web'` is `Field not found 'channel' in view with
  schema …`, because a condition cannot use an alias of its own projection.
- What the consumer writes decides it too. `=`, `IN (…)`, `OR` and `<>` prune; a function over
  the partition column does not: `UPPER(channel) = 'WEB'`, `key + 0 >= x` read every branch.
- It survives views built on top: a `GROUP BY` view over the union and an `INNER JOIN` of the
  union to another view both prune on `channel = 'web'`.
- **The constant's values are part of the contract, to the letter.** `channel = 'Web'`
  contradicts every branch: the plan prunes all of them and the query returns no rows, with no
  error. Name the values in the view's `DESCRIPTION`.

**A real column as the partition key** — sales of the current year in one database, earlier
years in another — works the same way, and needs no subquery: the branch filters the source's
own column, and the consumer's filter on the alias still prunes (the wrapper in the template
exists only because a constant is an alias):

```sql
-- verified: 9.5.1 (live, 2026-09-30)
    AS SELECT sr_item_sk AS item_sk, sr_returned_date_sk AS returned_date_sk, sr_return_amt AS return_amount
       FROM bv_store_returns_live
       WHERE sr_returned_date_sk >= 2457754 OR sr_returned_date_sk IS NULL
       UNION ALL
       SELECT sr_item_sk AS item_sk, sr_returned_date_sk AS returned_date_sk, sr_return_amt AS return_amount
       FROM bv_store_returns_archive
       WHERE sr_returned_date_sk < 2457754
```

`>=`, `>`, `BETWEEN`, `=` and `IS NULL` on the key prune. **Rows whose key is `NULL` satisfy
neither range and disappear**: two complementary branches over one file returned that file
minus every row with a `NULL` key (*live, 2026-09-30*), and nothing reported the difference.
`OR <key> IS NULL` goes into the branch of the source that owns those rows — the choice is
about authority, not speed: range queries prune the same whichever branch holds it.

- **The ranges are also what stops double counting** when the sources overlap — a migration
  whose copy was never trimmed, a replica. Then every source holds rows of the others, and only
  the branch conditions keep each row once; check it with the primary key (`SKILL.md`, Verify).
- A constant naming the source is optional here: pruning does not need it. Add it when the
  consumer has to know where a row came from.
- A branch condition relative to the clock, such as `sale_date >= TRUNC(CURRENT_DATE, 'Y')`, is
  the documentation's own example — *unverified: 9.5 documentation only*.

## Seeing the plan

`DESC QUERYPLAN` answers with no rows through the tool, `EXPLAIN` does not parse, and a
`TRACE` clause returns the ordinary result with no trace (the trace only reaches Design
Studio). The plan comes from a procedure:

```sql
-- verified: 9.5.1 (live, 2026-09-30)
SELECT execution_plan
  FROM GET_QUERY_EXECUTION_PLAN()
 WHERE input_query = 'SELECT COUNT(*) FROM returns WHERE channel = ''web''';
```

One row of text. It plans the query without running it — a branch over a missing file shows
`state = OK` — so it is safe on any view. The query can be an ad-hoc union with inline
subqueries, so a union's shape can be checked for pruning **before any view exists**. What to
read in it:

| In the text | Means |
|---|---|
| `optimizationsApplied = [Branch Pruning]` | at least one branch was removed |
| a `BASE PLAN (` block, whose next lines are `name = <base view>` and `database = <db>` | one per base view the query reads — count the blocks. Search for `BASE PLAN (` alone: the name is on the next line |
| `LOCAL ROUTE … filename: '<path>'` inside a file source's block | the file that is read |
| no `BASE PLAN (` block at all | nothing is read — every branch contradicted the query, and it returns no rows |
| `staticOptimized = true` | the plan was simplified before execution; `false` on a union that reads everything |

## Column descriptions

Field properties on the union itself are refused: `( channel ( description = '…' ) )` is
`The field properties can only be specified for derived fields`. Put the union in
`/02 - integration` under an `iv_` name and give the consumer's view in
`/03 - business entities` the field properties — `SELECT channel, … FROM iv_…` over it takes
them, and pruning goes through the extra layer (*verified: 9.5.1 (live, 2026-09-30)*).
Without column descriptions, the union is the `/03` object itself.
