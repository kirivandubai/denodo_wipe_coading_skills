# LLM functions in full

Everything `/denodo:ai` leaves out of its templates: each function's arguments and defaults,
what it returned on 9.5.1, and what the documentation gets wrong. Every call below is one
paid request per row it is evaluated on — the counting rules and the human's number are in
the skill, and they apply to every example here. Lines marked *documentation only* were not
run.

## Before any of them

- **Licence and configuration** — the Enterprise Plus bundle, and both the Denodo Assistant
  and its LLM configured in Design Studio (*Server configuration → Denodo Assistant*). The
  administrator's; the plugin changes neither.
- **Privilege** — the role `use_large_language_model` (not `use_large_language_model_role`).
  Without it every function fails with `The current user does not have the required
  privileges to execute this function.` in `error.raw` — for an ad-hoc query and for a view
  whose AI column is computed, not read from a cache. *verified: 9.5.1 (live, 2026-10-02)*
- **What leaves the server** — the arguments you pass, row by row, to the configured
  provider. Whether the organisation agreed to send that data is the human's question, not
  the server's: enabling the Assistant does not say which columns may go.
- **Temperature** — the last optional argument everywhere, from `0` to `1`. Defaults: `0.0`
  for every function except `ENRICH_AI` and `ENRICH_AI_BINARY` (`0.4`). At `0.0` the same
  input still changed its answer between two runs (one of nine texts, `SENTIMENT_AI`).

## CLASSIFY_AI

`CLASSIFY_AI(<text>, <scale>[, <temperature>]) → text`

```sql
-- verified: 9.5.1 (live, 2026-10-02)
SELECT CLASSIFY_AI('The screen cracked after two days',
                   { ROW('Product Quality', 'Broken or faulty'),
                     ROW('Delivery', 'Late or lost'),
                     ROW('Other', 'None of the above') }) AS topic
FROM Dual();
-- Product Quality
```

- The scale is an array of `ROW(label [, description [, example]])`, and every `ROW` must
  have the same number of fields: `{ ROW('a', 'd'), ROW('b') }` is `classify_ai: invalid
  classification scales.`, raised before any request.
- It returns one of the labels exactly as written — case and spaces kept — and always one:
  a text that fits none is given the nearest. With an `other` label, "what are your opening
  hours" was `other`; without one, `billing`.
- The labels can come from a table: `CLASSIFY_AI('<text>', NEST(label))` over a view of
  labels is one request — `NEST` builds the array (documentation; `/denodo:views` for `NEST`).

## SENTIMENT_AI

`SENTIMENT_AI(<text>[, <scale>][, <temperature>]) → text`

- Default answers: `negative`, `neutral`, `mixed`, `positive`, in lower case. *verified: 9.5.1
  (live, 2026-10-02)*
- A custom scale is an array of `ROW(name [, description [, example]])`, like
  `CLASSIFY_AI`'s (documentation only).
- `''` answers `neutral` — after a request.

## EXTRACT_AI

`EXTRACT_AI(<text>, <array of entity names>[, <temperature>]) → register`

```sql
-- verified: 9.5.1 (live, 2026-10-02)
SELECT (x.facts).city AS city,
       (x.facts)."customer name" AS customer,
       NULLIF((x.facts)."contract end", '') AS contract_end
FROM (SELECT EXTRACT_AI('Hi, this is Maria Lopez. Since Tuesday my fibre in Valencia drops every evening.',
                        {'customer name', 'city', 'contract end'}) AS facts
      FROM Dual()) x;
-- Valencia | Maria Lopez | NULL
```

- One field per entity, named exactly as the entity — with its spaces, so quote it:
  `(x.facts)."customer name"`. Parentheses around the register are required (`/denodo:views`,
  `references/arrays.md`).
- **An entity the text does not contain is `''`, not `NULL`.** `NULLIF(…, '')` makes it `NULL`
  for counts and joins.
- **One request per row, however many fields you read**: three rows took the same time with
  one field read and with two.
- The tool prints the whole register as one string of its values joined by spaces; read
  the fields.
- A view with an `EXTRACT_AI` column creates the type `_register_<entities>` in its own
  database, and the type **stays after `DROP VIEW`** — removing it is a `DROP TYPE`, the
  human's call like any drop.

## SUMMARIZE_AI

`SUMMARIZE_AI(<text>[, <words>][, <temperature>]) → text`

- `<words>` is approximate: `15` gave one sentence of 16 words, and the same text summarised
  twice came back with one word changed. *verified: 9.5.1 (live, 2026-10-02)*
- The summary is in the text's own language, not the Assistant's: a summary in English of a
  Spanish text is `TRANSLATE_AI(SUMMARIZE_AI(…), 'en')` — two requests — or one `ENRICH_AI`
  with a prompt asking for both.

## TRANSLATE_AI

`TRANSLATE_AI(<text>, <target language>[, <source language>][, <temperature>]) → text`

- `'en'` and `'German'` were both understood as the target. *verified: 9.5.1 (live,
  2026-10-02)*
- A text already in the target language is a request too, and comes back reworded —
  spelling, apostrophes and dashes changed. Translate only the rows that need it, when a
  column says which; a step that asks the LLM which language each row is in is itself a run
  over every row.
- Without such a column, one `ENRICH_AI` per row does both — it answers a marker for a text
  already in the language, and the translation otherwise:
  `COALESCE(NULLIF(ENRICH_AI('If this text is in English, reply exactly ENGLISH; otherwise
  reply with its English translation only: ' || body, 0.0), 'ENGLISH'), body)`. English texts
  then stay exactly as written. `NULLIF` and `COALESCE` evaluate the call once — the same time
  as the bare call.

## ENRICH_AI

`ENRICH_AI(<prompt>[, <temperature>]) → text`

```sql
-- verified: 9.5.1 (live, 2026-10-02)
SELECT ENRICH_AI('Answer with one word, no punctuation. Which country is this city in: ' || 'Valencia', 0.0) AS country
FROM Dual();
-- Spain
```

- The prompt is free text; a row's values go in by concatenation (`||`). It is the function
  for anything the others do not do — a one-sentence summary in English, a reply draft.
- Default temperature `0.4`: pass `0.0` when the answer must be the same every time it can be.
- Ask for the shape you need ("one word", "a number only"): the answer is whatever the model
  writes, and nothing checks it.

## ENRICH_AI_BINARY

`ENRICH_AI_BINARY(<prompt>, <blob>, <mime type>[, <temperature>]) → text` — *documentation
only*. `<mime type>` is one of `image/jpeg`, `image/jpg`, `image/png`, `image/gif`,
`image/webp`, `application/pdf`. One request per row, and the whole file goes with it.

## What the documentation gets wrong

- The examples of the LLM functions page are screenshots; the scale syntax is in them only.
- `use_large_language_model_role`, named in some pages for the Assistant procedures, does not
  exist on 9.5.1: `DESC ROLE use_large_language_model_role` → `Error loading role`. The role
  is `use_large_language_model`.
- The page recommends a cache "in the views that use these functions" without saying what it
  changes: with a full cache, readers send nothing and need no role; without one, every read
  of the column is a run.
