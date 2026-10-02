---
name: ai
description: Use when a Denodo 9.5 query or view should call the LLM or the embedding model configured on the server — CLASSIFY_AI, SENTIMENT_AI, SUMMARIZE_AI, TRANSLATE_AI, EXTRACT_AI or ENRICH_AI over a text column ("tag every ticket by topic", "add a sentiment column", "translate the reviews into English", "pull the amount out of each complaint"), or semantic search over stored embeddings — the vector type, EMBED_AI, VECTOR_DISTANCE, VECTOR_COSINE_DISTANCE ("find similar tickets", "a search view the app sends a sentence to"). Also when such a query or view is slow or expensive, labels an empty text, or fails with "does not have the required privileges to execute this function". Not for drafting view or field descriptions with the Denodo Assistant (/denodo:semantics), and not for configuring the LLM, the embedding model or the vector database (the administrator, in Design Studio).
---

# AI functions: the server's LLM in a query

Every `…_AI` function sends **one request per row it is evaluated on** to the LLM the
administrator configured for the server: about a second each, one after another, billed by
the provider, and the row's text travels with it. `EMBED_AI`, and `VECTOR_DISTANCE` with a
text, do the same against the embedding model. Nothing marks such a query: it reads like a
`SELECT`, the tool flags nothing, and `--max-rows` does not stop it.

This skill covers: the six text functions over rows; a view that keeps their answers so
readers do not pay again; semantic search over a vector column a database already stores, and
a search view an application passes a sentence to. Configuring the LLM, the embedding model
or the vector database, and the Enterprise Plus licence the functions need, are the
administrator's, in Design Studio — say so and stop. Embeddings for a whole table belong in a
vector-capable database, generated outside Denodo: a full cache cannot hold a vector column.
`ENRICH_AI_BINARY` (images, PDF) is in `references/functions.md`, documentation only.
Descriptions drafted by the Denodo Assistant are `/denodo:semantics`; the full cache itself is
`/denodo:cache`; the view around the expressions is `/denodo:views`; applying files is
`/denodo:execute`.

## How many requests a query makes

*verified: 9.5.1 (live, 2026-10-02)* — by timing, one request is 0.7–2 s and they run one
after another:

| The AI function is | Requests |
|---|---|
| only in the `SELECT` list, the query has `LIMIT n` | `n` — the only form a `LIMIT` bounds |
| in the `WHERE`, or a condition on an AI column of a view or subquery | one per row read, until `n` rows match — up to every row; and again for each row kept and projected. Over a file source the condition is evaluated **before** your other filters, on every row of the file: 4 rows wanted, 39 requests over a 35-row file. Over JDBC the other filters went to the database first, and the 4 rows cost 8 |
| under `ORDER BY`, `GROUP BY`, `DISTINCT`, an aggregate, a join condition | every row, whatever the `LIMIT` |
| a column of a view the query does not read (`COUNT(*)`, other columns, a filter on another column) | none |
| a column of a view with a loaded full cache | none |
| given `NULL` | none — the answer is `NULL` |
| given `''` | one, and a confident answer: `neutral`, one of your labels, `''` |
| in the branch of a `CASE` that is not taken | none |
| given the same text in many rows, or a literal | one per row — nothing is reused |
| given a literal, under `GET_QUERY_EXECUTION_PLAN` | evaluated while planning: a plan is a request too |

- **`--max-rows` cuts what the tool prints, not what the server computes**: the tool reads
  every row the query returns. Only a `LIMIT` in the query bounds the work.
- A filter on source columns runs first — delegated to the database when the source can —
  so only the rows that pass it are sent.
- 1,000 rows are 15–30 minutes. A file source gives `''`, not `NULL`, for an empty field.

## The rule: the human's number

**An AI function runs over the rows of a view or a table only up to a number the human
agreed to.** Every row is a paid request, and the text of every row goes to the provider.
The number counts requests: rows × the AI functions evaluated per row.

| You run it yourself | Only with the human's number |
|---|---|
| one call on `Dual()` to see that the server answers | any query that evaluates an AI function on rows: a sample, a count by label, a check, a cache load |
| trying an expression on `Dual()` with up to three texts, each through the functions you are trying — three texts through two functions are six requests — written by you or pasted from rows you read | a second full run of the same thing: new labels, a reload, a reload after the view's columns changed, a retry after a failed load |
| a search with a literal text, or a query of the search view below once its plan shows `embed_ai` only under `Dual()` — one request, however many rows | a search view whose requests grow with the rows (below, "A search view") |
| counting the rows a run would cover — no AI function in the query | |

**What counts as the number:** the human says one or approves one you showed — "show me
five" is five, "classify the 148" is 148, "yes" after "148 tickets, 296 requests, about five
minutes" is 296, and so is a ceiling named up front — "up to 400 requests, no need to come
back to me" lets you run anything under 400, the `Dual()` tries, samples and any retry
counted against it. A vague one — "a handful", "a few examples" — is at most five rows
(with two AI columns, ten requests); say which rows you took — a filter on a column may pick
them so that the sample covers each case. "Tag every ticket", said before anyone saw the
count, is the task, not the number. A second full run is a new number.

Show it in this shape, after the `Dual()` tries and before any run over rows:

```
sales_analytics.product_review: 2,400 reviews, 2,310 with text (90 empty — no request).
Topic and sentiment are 2 requests per review: 4,620 requests, about 1½ hours, each
sending the review text to the LLM configured on the server.
Tried on Dual() with three reviews: "arrived broken" → quality, negative; …
1. model/product_review_ai.vql — the view and its full cache; applying it sends nothing
2. cache/product_review_ai_load.vql — the load: 4,620 requests now, again on every reload
After: readers get the stored answers, no request per read; new reviews wait for the next load.
Run 2 now, or a sample of 20 first?
```

When you cannot ask — the human is away, the deadline is close — and no number was given,
the answer is the files, the `Dual()` tries and this message, not the run. Say what waiting
costs. The figures they wanted arrive minutes after their yes. A figure that is not the
run's — your own reading of the rows — goes into the message only marked as yours: the
stored run is what the dashboard will show.

| Rationalization | Reality |
|---|---|
| "They asked for every ticket — that is the number" | They asked for an outcome before seeing the count, the time, and that every text leaves for an outside provider. The number is the one they say after yours. |
| "It is only a few hundred rows, a few cents" | You know neither the provider's price nor what else runs on that key, and the same load file runs nightly on a table that grows. The rule is the number, not your estimate of the bill. |
| "I deduplicated / filtered first — it is far fewer calls" | Still a run over rows. Show the number you will actually run; that is the one they agree to. |
| "They need the counts for the deck in 30 minutes" | Files, `Dual()` tries, the message. A guess run under a deadline is still a run nobody agreed to. |
| "A cache load is setup, not a query" | A load is the full run: every row of the view, every AI column. |
| "`--max-rows 10` keeps it small" | It keeps the printout small. The server computed every row. |
| "A sample of five is harmless" | It is a run over rows. Try the expression on `Dual()`, or ask for the sample size with the count. |

**Red flags — stop:** an AI function under `ORDER BY`, `GROUP BY`, `DISTINCT` or in a `WHERE`;
a query on rows with no `LIMIT`; a cache load of a view with an AI column; a `SELECT` "to
check the view" on a view whose AI columns are not cached; `env.production` is `true`.

## Templates

The example database is the one of `/denodo:views`, `sales_analytics`, with a view of product
reviews. The blocks run in this order in the verification chain.

### Does the server answer

```sql
-- verified: 9.5.1 (live, 2026-10-02)
SELECT SENTIMENT_AI('The parcel was late, but support refunded me the same day.') AS want_mixed
FROM Dual();
```

- One request. An answer back — `mixed` here — means the LLM is configured and you may call
  it.
- `The current user does not have the required privileges to execute this function.` (in
  `error.raw`; `message` says only `Error executing query`) — the profile's user lacks the
  role `use_large_language_model`. Granting it is `/denodo:security`, the human's yes.
  The role is for the `…_AI` text functions: `EMBED_AI` answered a user who did not have it.
- Any other refusal — no LLM configured, no Enterprise Plus — is the administrator's; stop.
  The texts of those errors were not observed on a server that has both.

### Count before you run

```sql
-- verified: 9.5.1 (live, 2026-10-02)
CONNECT DATABASE sales_analytics;

SELECT COUNT(*) AS reviews,
       SUM(CASE WHEN review_text IS NULL OR TRIM(review_text) = '' THEN 0 ELSE 1 END) AS with_text
FROM product_review;
```

`with_text` × the AI columns per row is the number of requests a full run makes.

### Classify, score, extract — over rows

```sql
-- verified: 9.5.1 (live, 2026-10-02)
CONNECT DATABASE sales_analytics;

SELECT review_id,
       CASE WHEN TRIM(review_text) = '' THEN NULL ELSE
            CLASSIFY_AI(review_text, { ROW('quality',  'The product is broken, faulty or not as described'),
                                       ROW('delivery', 'Late, lost or damaged in transit, wrong item sent'),
                                       ROW('fit',      'Size, compatibility, does not work with what the customer has'),
                                       ROW('other',    'Anything that is none of the above') })
       END AS topic,
       CASE WHEN TRIM(review_text) = '' THEN NULL ELSE SENTIMENT_AI(review_text) END AS sentiment
FROM product_review
LIMIT 5;
```

- **The AI functions stay in the `SELECT` list**, so the `LIMIT` is the number of rows sent.
  Filter on columns (`WHERE review_date >= …`), never on an AI result.
- **Always an `other` label.** A text that fits none of them still gets one of yours: "what
  are your opening hours" came back `billing` from a scale without `other`, and `other` with
  it. It returns the label as you wrote it.
- **Every label has the same fields** — all `ROW(label)`, all `ROW(label, description)` or all
  `ROW(label, description, example)`. Mixed: `classify_ai: invalid classification scales.`
  Descriptions are what tell close labels apart; read them as the model will — two that
  overlap send borderline texts to either. **One label per row**: a text that asks for three
  things gets one of them.
- **The `CASE` sends no request for an empty text.** `NULL` costs nothing anyway; `''` would be
  a request and a confident `neutral` or label.
- `SENTIMENT_AI` answers `negative`, `neutral`, `mixed` or `positive` in lower case (the
  documentation's screenshots show `Positive`).
- Two runs over the same rows are not the same: one of nine short texts changed its sentiment
  between two runs at the default temperature 0. What people read should come from a stored
  run — next template.
- `EXTRACT_AI`, `SUMMARIZE_AI`, `TRANSLATE_AI` and `ENRICH_AI` — their arguments, defaults and
  what they return as measured — are in `references/functions.md`.

### A view that keeps the answers

The answers are computed once, by a load the human agreed to, and stored in the view's full
cache: readers — a dashboard refreshing every hour, a `GROUP BY` for a report — read the
stored rows and send nothing. Two files.

```sql
-- verified: 9.5.1 (live, 2026-10-02)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW product_review_ai
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Product reviews with a topic and a sentiment computed by the LLM configured on the server. Stored by the full cache: refreshed only when the load file runs.'
    PRIMARY KEY ( 'review_id' )
    AS SELECT review_id, review_text,
              CASE WHEN TRIM(review_text) = '' THEN NULL ELSE
                   CLASSIFY_AI(review_text, { ROW('quality',  'The product is broken, faulty or not as described'),
                                              ROW('delivery', 'Late, lost or damaged in transit, wrong item sent'),
                                              ROW('fit',      'Size, compatibility, does not work with what the customer has'),
                                              ROW('other',    'Anything that is none of the above') })
              END AS topic,
              CASE WHEN TRIM(review_text) = '' THEN NULL ELSE SENTIMENT_AI(review_text) END AS sentiment
       FROM product_review
    CONTEXT ('formatted' = 'yes');

ALTER VIEW product_review_ai CACHE FULL WITH_STATUS;
```

```sql
-- verified: 9.5.1 (live, 2026-10-02)
CONNECT DATABASE sales_analytics;

SELECT * FROM product_review_ai
CONTEXT ('cache_preload' = 'true',
         'cache_invalidate' = 'all_rows',
         'cache_wait_for_load' = 'true',
         'cache_return_query_results' = 'false');
```

- **Applying the first file sends nothing**; `CREATE VIEW` evaluates no row. **The second is
  the full run** — every row of the view times its AI columns — and runs only with the human's
  number. Every later run of it is a new number: a refresh job runs it again every night.
- **Without the cache, every read of the AI column is a run**: a dashboard's `GROUP BY topic`
  sends every row on every refresh, the labels drift between refreshes, and every reader needs
  the role `use_large_language_model` — a reader without it got `The current user does not
  have the required privileges to execute this function.` from a view whose AI column was
  computed, and its rows from a cached one. *verified: 9.5.1 (live, 2026-10-02)*
- **A new view, not a column in someone's view.** The view people already read keeps its
  readers, its privileges and its cost; they move to the new one when they choose — say that
  the dashboard has to be pointed at it, after the load, not before. Built over
  another team's view, it becomes one of its dependants (`USED_BY`) and goes with their
  `DROP … CASCADE` — say so.
- The cache rules are `/denodo:cache`'s, and three of them cost money here: from the
  `ALTER VIEW … CACHE` until the load finishes the view returns 0 rows; re-applying the
  view's file with a column added, removed or retyped empties the cache, and refilling it is
  a new full run; a text longer than the cache column (4,000 characters on SQL Server) fails
  the load, which then keeps serving the previous content.
- The texts and the answers are stored in the cache database. Say so when the texts may hold
  personal data.
- **A sample before the full load**, without touching the cache: `SELECT * FROM
  product_review_ai WHERE TRIM(review_text) <> '' LIMIT 20 CONTEXT ('cache' = 'off')` reads
  the source and computes the 20 rows — 20 × the AI columns — and stores nothing; the loaded
  rows and their date stayed as they were.
- **The view holds only what the load stored**: a row added to the source afterwards is not
  in the view at all until the next load. And a load is never incremental here — it re-sends
  every row with text, old ones included, so over a source refreshed nightly each refresh is
  a full run. Incremental loads are set in Design Studio (`/denodo:cache`).
- **A failed load keeps the previous content**, and a retry is the full run again — inside
  the number, or a new one.
- **When texts repeat word for word** (`COUNT(DISTINCT review_text)` far below `COUNT(*)`), the
  cached view can classify `SELECT DISTINCT review_text` instead, and the view people read
  joins it back on the text: one request per distinct text, and identical texts get identical
  answers. Show the distinct count as the number. Join on the same expression on both sides
  (`TRIM(review_text)`), keep the rows without text with a `LEFT OUTER JOIN`, and check that
  the joined view has exactly the source's rows — a case-insensitive cache database can merge
  two texts that differ only in case (`/denodo:cache`, Silent failures, 9).

### Semantic search over a stored vector column

```sql
-- verified: 9.5.1 (live, 2026-10-02)
CONNECT DATABASE sales_analytics;

SELECT review_id, review_text,
       VECTOR_DISTANCE(review_vector, 'arrived broken and the box was crushed') AS distance
FROM product_review_vector
WHERE review_vector IS NOT NULL
ORDER BY distance
LIMIT 5;
```

- **One request, however many rows**: the text is embedded once, the distances are arithmetic.
- `VECTOR_DISTANCE` embeds the text with the model named by the column's `embeddingmodel`
  property, and uses the cosine distance (0 = the same meaning). The property is on the base
  view's field (`review_vector:vector<float,3072> (embeddingmodel = '…')`) and derived views
  keep it — read it before searching: `SELECT view_name, column_name, column_extra_properties
  FROM GET_VIEW_COLUMNS() WHERE input_database_name = 'sales_analytics' AND column_vdp_type
  LIKE 'vector%'` → `[embeddingmodel text-embedding-3-large ]`. A column without it is
  compared with the server's default model, and vectors made by another model of the same
  size give distances that look real and mean nothing (documentation).
- **`WHERE review_vector IS NOT NULL`** — a row with a `NULL` vector fails the whole query as
  soon as it would be in the result: `Error executing query`, and in `error.raw` `Invalid
  parameter types for vector_cosine_distance() function`.
- **Five rows come back for any text**, related or not. Give the reader a threshold, or the
  distances, and say that they depend on the model and the metric.
- Where the distance is computed: `references/vectors.md`, "Delegation". With the data
  source's `delegatevectorliteral = false` every row's vector travels to Denodo — fine for
  thousands of rows, not for millions; the data source is its owner's to change.

### A search view the application sends a sentence to

```sql
-- verified: 9.5.1 (live, 2026-10-02)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW product_review_search
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'The 5 reviews closest in meaning to search_text, closest first. Query: SELECT * FROM product_review_search WHERE search_text = ''<sentence>''. One embedding request per query.'
    AS SELECT r.review_id, r.review_text,
              VECTOR_COSINE_DISTANCE(r.review_vector, q.search_vector) AS distance
       FROM product_review_vector r
            CROSS JOIN ( SELECT EMBED_AI(search_text, 'text-embedding-3-large') AS search_vector
                         FROM Dual() ) q
       WHERE r.review_vector IS NOT NULL
       USING PARAMETERS ( search_text : text )
       ORDER BY distance
       LIMIT 5
    CONTEXT ('formatted' = 'yes');
```

- **Not `VECTOR_DISTANCE(review_vector, search_text)`**, the documentation's own example: with
  a parameter instead of a literal, the plan keeps `embed_ai(search_text, …)` in the per-row
  projection, and every search sends **one embedding request per row of the table** — 4 rows
  took 2 s, 32 rows 13 s; this form, 0.9 s. *verified: 9.5.1 (live, 2026-10-02)*
- **The model is written out** — the one the column's `embeddingmodel` names. Over `Dual()`
  there is no column to read it from; without it the server's default is used silently, and
  with it a server configured with another model refuses: `Cannot execute embed_ai() function:
  the model '…' specified in the query does not match the configured`.
- The reader passes the sentence as an equality: `SELECT * FROM product_review_search WHERE
  search_text = '…'`. Without it: `View without search methods: The following obligatory
  fields cannot be removed: search_text`.
- **What it costs at scale:** the cross join with `Dual()` runs in Denodo, so every query
  reads every vector from the source (about 12 KB a row at 3,072 floats) and no vector index
  or approximate search can serve it — right for thousands of rows; for millions, say so and
  leave the design to the human. A user who only queries it needs no LLM role.
- A `WHERE` on another column is applied **before** the five are chosen: `WHERE review_id =
  5` returned review 5, ranked sixth without it. A filtered search is a search within the
  filter.

## What you need

| Slot | Where it comes from |
|---|---|
| Which rows, which column | the human; the count from "Count before you run" |
| The labels | the human's list, each with a description, plus `other` — added by you and said |
| The number | the human, after your message |
| Who reads the answers | the human: a dashboard or a report means the view with a cache |
| Whether the server answers | the `Dual()` call |
| The vector column and its model | `GET_VIEW_COLUMNS()` → `column_extra_properties` |
| Target language | the human; `'en'` and `'German'` both worked for `TRANSLATE_AI` |

## Verify

Reads that send nothing — run them after the load, on the cached view:

| Check | Query | Expect |
|---|---|---|
| Loaded | `SELECT expirationdate FROM CACHE_CONTENT('<db>', '<view>')` | the time of the load |
| Only your labels | `SELECT topic, COUNT(*) FROM <view> GROUP BY topic` | each value one of your labels, or `NULL` for empty texts |
| No answer for an empty text | `SELECT COUNT(*) FROM <view> WHERE TRIM(review_text) = '' AND topic IS NOT NULL` | `0` |
| An answer for every text | `SELECT COUNT(*) FROM <view> WHERE TRIM(review_text) <> '' AND (topic IS NULL OR sentiment IS NULL)` | `0` |
| Readers send nothing | `SELECT execution_plan FROM GET_QUERY_EXECUTION_PLAN() WHERE input_query = 'SELECT topic, COUNT(*) FROM <view> GROUP BY topic'` | the SQL names the `C_<VIEW>…` cache table, and no `_ai` function appears |
| A search sends one request | the plan of the search view's query | `embed_ai` only under the `Dual()` branch |

A `LIMIT` in the planned query makes `GET_QUERY_EXECUTION_PLAN` answer `Error executing
query`: plan it without the `LIMIT`. A view with a `LIMIT` inside, like the search view,
plans fine.

## Silent failures

Each runs without an error — *verified: 9.5.1 (live, 2026-10-02)*.

| You did | What happens | Instead |
|---|---|---|
| 1. an AI function in `WHERE`, `ORDER BY` or `GROUP BY`, or a condition on a view's AI column, with `LIMIT 5` | every row is sent — over a file source, every row of the file, before your other filters | AI only in the `SELECT` list; filter and sort on columns |
| 2. trusted `--max-rows` | every row the query returns is computed | a `LIMIT` in the query |
| 3. a label list without `other` | every text gets one of your labels | add `other`, and say so |
| 4. sent `''` | a request, and `neutral` or a label | the `CASE` around each call |
| 5. a view with AI columns and no cache under a dashboard | every refresh is a full run, the labels drift, readers without the role fail | the view with a cache |
| 6. reloaded, or re-ran a sample | some answers change | answers come from one stored run; a new run is a new number |
| 7. `EXTRACT_AI` for something the text does not contain | `''`, not `NULL`: `COUNT(field)` counts it | `NULLIF((x).field, '')` |
| 8. `VECTOR_DISTANCE(col, <parameter>)` in a view | one embedding request per row on every search | the `Dual()` form above |
| 9. searched a vector column without `embeddingmodel` | the server's default model; distances meaningless if the vectors came from another (documentation) | read the property; write the model into `EMBED_AI` |
| 10. `ORDER BY distance LIMIT 5` | five rows for any text | a threshold, or show the distances |
| 11. `TRANSLATE_AI` over texts already in the target language | a request each, and reworded text (spelling, punctuation) | translate only the rows that need it, when a column says which |
| 12. `GET_QUERY_EXECUTION_PLAN` of a query with an AI literal | a request while planning | count it |

## Common mistakes

| You wrote | Server says | Fix |
|---|---|---|
| labels with different fields | `classify_ai: invalid classification scales.` | the same fields in every `ROW` |
| any AI function, as a user without the role | `Error executing query`; `error.raw`: `The current user does not have the required privileges to execute this function.` | the role `use_large_language_model` — `/denodo:security`, a yes; or read from a cached view |
| `EMBED_AI(text, '<model>')` with a model the server is not configured with | `Cannot execute embed_ai() function: the model '…' specified in the query does not match the configured` | the configured model — or the column's vectors need another embedding model, the administrator's |
| a `NULL` vector reaching the result | `Error executing query`; `error.raw`: `Invalid parameter types for vector_cosine_distance() function` | `WHERE <vector> IS NOT NULL` |
| vectors of different sizes | `Error executing query` | the same model, the same dimension |
| `VECTOR_INNER_PRODUCT_DISTANCE` (the documentation's example) | `Function 'vector_inner_product_distance' with arity 2 not found` | `VECTOR_NEGATIVE_INNER_PRODUCT` |
| `ALTER VIEW … CACHE FULL` on a view with a vector column | `Error executing ALTER operation: Cannot invoke "java.lang.Integer.toString()" … getSourceTypeSize() is null` | a full cache cannot hold vectors; store them in a vector database |
| the search view without its parameter | `View without search methods: The following obligatory fields cannot be removed: search_text` | `WHERE search_text = '…'` |
| `GET_QUERY_EXECUTION_PLAN` of a query with `LIMIT` | `Error executing query` | plan it without the `LIMIT` |

## Reference

- `references/functions.md` — each LLM function: signature, default temperature, what it
  returns as measured, `EXTRACT_AI`'s register and how to read it, `ENRICH_AI_BINARY`, the
  privileges and licence, and what the documentation gets wrong.
- `references/vectors.md` — the vector type and its literals, the four distance functions
  with measured values, how `EMBED_AI` and `VECTOR_DISTANCE` choose the model, delegation and
  approximate search, a vector column in a base view, `NULL`s and dimensions.
