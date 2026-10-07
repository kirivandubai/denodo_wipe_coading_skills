# Vectors and semantic search in full

Everything `/denodo:ai` leaves out of its two search templates. Measured on 9.5.1 unless a
line says *documentation only*. `EMBED_AI` is a request to the embedding model
configured on the server, one per value it embeds; the distance functions are arithmetic and
cost nothing.

## The type

`vector<float, n>`, `vector<double, n>`, `vector<int, n>`, `vector<long, n>` — `n` is the
dimension. A column declared `vector<float>` may hold vectors of different sizes in different
rows: Denodo does not enforce the dimension (documentation).

```sql
-- verified: 9.5.1 (live, 2026-10-06)
SELECT vector<float,3>[1,4,3] AS v,           -- [1.0, 4.0, 3.0]
       vector<double,2>[1.5,2.5] AS d          -- [1.5, 2.5]
FROM Dual();
```

A vector column in a base view, as the server prints it in `DESC VQL` of a pgvector table —
the `embeddingmodel` field property is what `VECTOR_DISTANCE` reads:

```
embedding:vector<float,<dimension>> (embeddingmodel = '<model>', sourcetypeid = '10006', …)
```

It is set in Design Studio (*Edit → the field → Source type properties → Embedding model*)
or in that field list. A derived view keeps it, renamed or not: `GET_VIEW_COLUMNS()` answers
`column_extra_properties = [embeddingmodel <model> ]` for the view's column.
A column computed with `EMBED_AI` in a view has no property (`[]`).

**A full cache over a vector column failed on 9.5.1** (the 9.4 release notes say vector values
can be cached; the error names a missing source type size): `ALTER VIEW … CACHE FULL` over a
view with one failed with `Cannot invoke "java.lang.Integer.toString()" because the return
value of "…SQLSourceTypeInfo.getSourceTypeSize()" is null`. Vectors for a whole table are
generated outside Denodo and stored in a vector-capable source — PostgreSQL with pgvector,
Oracle, SQL Server 2025, Snowflake, Databricks, BigQuery (documentation) — which Denodo then
reads.

## Distance functions

*verified: 9.5.1 (live, 2026-10-02)*, over `[1,4,3]` and `[1,1,6]`:

| Function | `VECTOR_DISTANCE` metric | Result |
|---|---|---|
| `VECTOR_COSINE_DISTANCE(a, b)` | `'cosine'` (the default) | `0.2682725225778554` — 0 is the same direction, 1 orthogonal |
| `VECTOR_L2_DISTANCE(a, b)` | `'euclidean'`, `'l2'` | `4.242640687119285` |
| `VECTOR_L1_DISTANCE(a, b)` | `'manhattan'`, `'l1'` | `6.0` |
| `VECTOR_NEGATIVE_INNER_PRODUCT(a, b)` | `'inner_product'` | `-23.0` — smaller is closer |

- The documentation's example for the last one calls `VECTOR_INNER_PRODUCT_DISTANCE` and shows
  `23`: that function does not exist (`Function 'vector_inner_product_distance' with arity 2
  not found`), and the real one is negative.
- A zero vector gives a cosine distance of `1.0`, not an error.
- Different dimensions: `Error executing query`, nothing more.
- A literal `NULL` argument: `Error executing query`. A `NULL` column value is worse: the
  query fails only when that row would be in the result — `ORDER BY d LIMIT 3` with the
  `NULL` row ranked last answered, the same query with `LIMIT 40` failed with `Invalid
  parameter types for vector_cosine_distance() function` in `error.raw`. Filter it out:
  `WHERE <vector> IS NOT NULL`. Delegated to PostgreSQL, a `NULL` gives a `NULL` distance and
  no error.
- A threshold (`WHERE distance < 0.4`) depends on the model and the metric; take it from the
  distances of texts the human calls related and unrelated, not from the documentation.

## EMBED_AI and VECTOR_DISTANCE: which model

| Call | Model | Runs |
|---|---|---|
| `EMBED_AI(<text>)` | the server's default embedding model | in Denodo |
| `EMBED_AI(<text>, '<model>')` | `<model>` — delegated when the source can, otherwise only if it is the server's model | in the source, or in Denodo; another model fails: `Cannot execute embed_ai() function: the model '<model>' specified in the query does not match the configured` |
| `EMBED_AI(<text>, <vector column>)` | the column's `embeddingmodel`, as the line above; none → the server's default | |
| `VECTOR_DISTANCE(<vector column>, <text> [, <metric>])` | rewritten to `VECTOR_<metric>_DISTANCE(<column>, EMBED_AI(<text>, <column>))` | |

- Vectors made by different models cannot be compared. Same dimension, different model: the
  distances look real and are meaningless — no error anywhere (documentation). Different
  dimension: `Error executing query`.
- A literal text is embedded once per occurrence in the query — a hybrid search with
  `VECTOR_DISTANCE` in both the `SELECT` list and the `WHERE` made two requests, over 32 rows.
- **A view parameter is not a literal**: `VECTOR_DISTANCE(<column>, <parameter>)` plans as
  `vector_cosine_distance(<column>, embed_ai(<parameter>, <column>))` in the per-row
  projection, and runs one request per row — measured once, 4 rows took 2 s and 32 rows 13 s.
  Embedding the parameter in a `Dual()` branch joined to the rows (the skill's search view) is
  one request: 0.9 s over the same 32 rows.
- `GET_QUERY_EXECUTION_PLAN` of a query with a literal text embeds it while planning — one
  request; measured once, the plan took 1 s against 0.3 s for one without AI.

## Delegation

```sql
-- verified: 9.5.1 (live, 2026-10-06)
SELECT execution_plan FROM GET_QUERY_EXECUTION_PLAN()
WHERE input_query = 'SELECT id, VECTOR_DISTANCE(embedding, ''slow mobile data'') AS d FROM <view> ORDER BY d';
```

No `LIMIT` in the planned query: with one the procedure answers `Error executing query`.

| In the plan | Means |
|---|---|
| `SQLSentence = … (t0.embedding <=> …) …` | the distance runs in PostgreSQL (`<=>` is pgvector's cosine distance) |
| `noDelegationCause = Vector literal cannot be delegated to this database`, and the `SQLSentence` selects the vector column | every row's vector travels to Denodo, which computes the distance — 4 bytes a dimension, 12 KB a row at 3,072 |
| `noDelegationCause = The function 'embed_ai' cannot be delegated to this database` on the projection | Denodo embeds per row — a parameter search, above |

The second line comes from the data source: its `SOURCECONFIGURATION ( delegatevectorliteral
= false )` keeps the embedded text out of the SQL sent to the database. Changing it is a
change to the data source — its owner's, in Design Studio (`/denodo:datasources`). A distance
between two columns (`VECTOR_COSINE_DISTANCE(t.embedding, t.embedding)`) has no literal and
was delegated as `<=>`.

An LLM function never runs in the source: `The function 'sentiment_ai' cannot be delegated to
this database`; the filters below it still go down (`WHERE t0.id < ?` in the `SQLSentence`).

## Approximate search

*Documentation only.* With a vector index in the source, a query of the shape `ORDER BY
<distance function> LIMIT n` — the distance first in the `ORDER BY`, a `LIMIT`, and no `WHERE`
except on BigQuery — is rewritten to the source's `VECTOR_SEARCH` (Databricks, BigQuery,
SQL Server) or recognised natively by the source's index (PostgreSQL, Oracle). The answer is
approximate: close rows can be missed. `CONTEXT ('approximate_vector_search' = 'OFF')` forces
the exact search.

## More like this

A distance between two stored vectors costs nothing — no text is embedded:

```sql
-- verified: 9.5.1 (live, 2026-10-06)
SELECT t.review_id, VECTOR_COSINE_DISTANCE(t.review_vector, s.review_vector) AS distance
FROM product_review_vector t,
     (SELECT review_vector FROM product_review_vector WHERE review_id = 1042) s
WHERE t.review_id <> 1042 AND t.review_vector IS NOT NULL
ORDER BY distance;
```
