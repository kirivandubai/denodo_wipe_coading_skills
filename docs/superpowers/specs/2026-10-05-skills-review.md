# Review of all sixteen skills (2026-10-05)

The owner asked for a full review of the skills on four points: the texts are generic and do not
lean on the server they were written against; every skill is in English; every skill works when
it creates objects on a live server; what else would help vibe-coding on Denodo. This document is
the result. The fixes are task T37 in [TASKS.md](../../TASKS.md); the recommendations at the end
are not part of it.

**Base commit:** `0083642` (after T36). Line numbers below are as of that commit.

**Method.** Mechanical scans of `skills/` (Cyrillic and other non-ASCII, installation words,
ports, ids, demo names, description lengths, marks near code blocks); five read-only reviewers,
each reading every line of three to five skills with their references; a live run of the
verification chain with every optional tail; the eval suite; the unit tests; `claude plugin
validate`. Items marked **(checked)** were confirmed against the file during the review; the
rest come from the reviewers' reports and are to be confirmed when fixed.

## Results

| Check | Result |
|---|---|
| Point 2 — English only | **Passes.** No Cyrillic in `skills/`, `README.md`, `CONTRIBUTING.md`, `scripts/`, `.claude-plugin/` or the eval prompts. Non-ASCII in skills is punctuation, box drawing, `∪`, and intentional sample data (`straße`, `Tokyo 東京`, `domingo`) |
| Point 3 — `scripts/denodo verify` with `--with-marketplace --with-ai --with-writes --with-scheduler --testing-tool` | **80 of 80 template steps verified**, 0 failed, 0 skipped; cleanup left no database, tag, role, user, policy, marketplace orphan (`changes` empty on both halves) or Scheduler project. The CSV export file is left in the Scheduler's export folder by design and was removed by hand |
| Eval suite, `--runs 1 --ablation none` | **64 of 64** cases pass ($14.17) |
| Unit tests | 460 OK (15 skipped) |
| `claude plugin validate .` | passes; one warning: `CLAUDE.md` at the plugin root is not loaded as plugin context |
| Point 1 — generic texts | **Frontmatter descriptions are generic**, with the exceptions in B below. **Bodies are not fully generic**: section A lists values of the test server inside templates, which fail on another installation |

What the chain does **not** cover, so "works" is narrower than the marks suggest:

- The chain runs 80 templates, all from `SKILL.md` sections of fourteen skills (`vql` and
  `execute` have none to run). The skills carry 162 `verified` marks in `SKILL.md` files and
  **170 in `references/`**; the reference ones were each verified once, by hand, and nothing
  re-runs them.
- 21 `unverified` marks remain; about four use a non-canonical form (`unverified: OpenAPI of
  the 9.5.1 server`, `unverified: 9.5 OpenAPI only`, `unverified: documentation 9.5 (…)`,
  `*documentation 9.5*`, `*(live, 2026-09-17)*` without `verified:`).
- The chain itself runs only on the Denodo demo image: `csv_dir = "/opt/denodo/demos/csv"`,
  the write tables' DDL is SQL Server's, the embedding model is a fixed value. A user with
  another server cannot verify the templates as shipped (see recommendation 2).

## A. Values of one installation inside templates — break elsewhere (high)

| Where | What | Effect on another server | Fix |
|---|---|---|---|
| `ai/SKILL.md:298` **(checked)** | `EMBED_AI(search_text, 'text-embedding-3-large')` in the search-view template; also `vector<float,3072>` and `embeddingmodel text-embedding-3-large` at `:271`, `:274`, `:319`, `references/vectors.md:25,30,99` | refused: the model does not match the configured one | `'<the embeddingmodel of the vector column>'`, `<n>` for the dimension, "4 bytes × dimension"; the `substitute` key in `verification/chain.toml:1049` changes with it |
| `marketplace/SKILL.md:104`, `:146–149`, `:333`, `:340–345` **(checked)** | ids `627`, `7484`, `352`, `7485`, `30`, `217` inside runnable calls — against the skill's own rule 1 (`:22–23`, "A template cannot contain one") | a copied call tags or files the wrong object | `<tag_id>`, `<view_id>`, `<category_id>`, `<provider_type_id>`, `<tool_server_id>`; the `substitute` keys at `chain.toml:1476,1488` change with them |
| `marketplace/SKILL.md:62` **(checked)** | `{"id":306,…}` — the test server's id | misleading example | `{"id":<serverId>,…}` |
| `scheduler/SKILL.md:184`, `:243` **(checked)** | `"dataSourceID": 2` in the job files the agent is told to create | the job points at another Scheduler's data source | `"dataSourceID": <data_source_id>`; the `substitute` keys at `chain.toml:593,644,654` change with it |
| `vql/references/dialect.md:140` **(checked)** | `GETMONTHSBETWEEN(birth_date, DATE '2026-09-30')` in the age recipe | every age computed as of that day | `CURRENT_DATE` |
| `materialize/SKILL.md:199–200`, `:396`, `:451` ff., `references/remote-tables.md:96` | SQL Server target types (`nvarchar`, `varchar(4000/8000)`, twenty decimals) presented as the general rule | needless length limits on PostgreSQL, Oracle and others | qualify as "on SQL Server (measured)"; for other targets read the landed types first |
| `datasources/SKILL.md:170,223,272,436,523`, `references/base-view.md:50,65` **(checked)** | `I18N us_pst` as "the usual default"; "the 76 available" | timestamps parsed in Pacific time on a server set up otherwise | use the i18n of the database's existing base views, `us_pst` only when there are none; drop the count |
| `procedures` description and `SKILL.md:13,120`, `references/predefined.md:3,95` | "the 128 predefined procedures", "(14 of them)" | a count presented as universal; it depends on the server's features | "`LIST PROCEDURES` lists them" |
| `metrics/SKILL.md:32` **(checked)** | "after 900 s by default" | the query timeout is a server or client setting | "until the query timeout" |

## B. Frontmatter descriptions

- **Over the Agent Skills limit of 1024 characters:** `views` 1144, `materialize` 1106.
  `metrics` 1014 and `dml` 1001 sit at the limit; any addition breaks them. A reviewer's
  ~880-character rewrite of `materialize` (mechanism phrases removed, triggers kept) is a
  starting point; for `views`, drop the syntax in parentheses.
- `procedures`: the "128" (A); "`GENERATE_STATS() … WHERE input_… = …`" contradicts
  `references/predefined.md:45` ("no `input_` prefix").
- `vql`: lists only the v1 objects and none added since (roles and policies, cache,
  summaries and remote tables, tests, AI columns); "this skill holds the working loop…" summarises
  content rather than giving a trigger.
- `cache`: triggers on `"Invalid object name"`, SQL Server's text; and has no "Not for …
  /denodo:materialize" although "materialize this view" is one of its phrases.
- Every description change runs the eval suite (CLAUDE.md).

## C. Contradictions with the `vql` safety table

- **`procedures/SKILL.md`** **(checked)** never says that some predefined procedures change
  state; the warning lives only in `references/predefined.md:38–73`, while the description
  triggers on "run the stats procedure". Add a paragraph under "Call a predefined procedure"
  naming `GENERATE_STATS`, `CLEAN_CACHE_DATABASE`, `DROP_REMOTE_TABLE`: show the call, wait for
  the yes. Related: `predefined.md:87–88` says `CLEAN_CACHE_DATABASE`, `COMPACT_CACHE`,
  `DROP_NONACTIVE_CACHE_TABLES` "write", but the gate list at `:43–53` (mirrored in
  `scripts/denodo_cli/safety.py`) lacks `COMPACT_CACHE`; `REFRESH_BASE_VIEW`,
  `CREATE_TAGS_FROM_*` and `LOGCONTROLLER` are not in it either. `vql-procedures.md:187` offers
  `CALL LOGCONTROLLER(…, 'DEBUG')` — server-wide logging — with no yes and no "set it back".
- **`datasources/SKILL.md:690`** **(checked)**: "Replacing a working source with `CREATE OR
  REPLACE` is cheap and safe; the one thing it destroys is the stored password" — contradicts
  `:97–99`, `references/base-view.md:116–121` (silently switches a cache off) and `vql`. Safe on
  a source your own file declares; anything else needs the yes.
- **`dml/references/writable-views.md:90`** **(checked)**: `vql desc --env dev <base view>
  --type "wrapper jdbc" --vql` passes a view name to the wrapper type and brings the data source
  with its encrypted password — the form `SKILL.md:134` avoids. Use the SKILL's
  `DESC VQL WRAPPER JDBC <wrapper> ('includeDependencies'='no','dropElements'='no')`.
- **`security/SKILL.md:83`** **(checked)**: "a role no person holds yet" is in the "apply
  yourself" row without saying its grants must name only objects created in this session; `vql`
  requires that every object a security statement touches is the session's own.
- **`semantics/SKILL.md:25`** **(checked)** puts the MCP tag on every view being built, "no
  approval step"; `:52` and `:275` make the tag the owner's decision, view by view. Tag a new
  view only when the human asked for it to be visible to agents.
- **`catalog/SKILL.md:58–64`**: asks for a yes only when the tag exists; assigning a new tag to a
  view not created in this session falls under `vql`'s metadata row.
- **`vql/SKILL.md:130`** puts `CALL CLEAN_CACHE_DATABASE(…)` under the yes always, while
  `cache/SKILL.md:59` lets the agent clear its own session's view with that call. Name the
  exception in one of the two.
- **`materialize/SKILL.md:83`**: inserting into a table created in this session is the agent's
  own call; `vql:121` puts every `INSERT` under the yes. Name the exception in one of the two.
- **`metrics/SKILL.md:283–286`**: "someone else owns" versus `vql`'s "you did not create in this
  session". Use the session criterion.
- **`cache/SKILL.md:92`** **(checked)**: "Test on a view you created" can read as a probe object,
  which `vql:37` forbids. "…on the view you are building in this session's file."
- **Not in T37:** `marketplace`'s conditional `synchronize` (`SKILL.md:186,470,542–547`) versus
  `vql`'s "every `synchronize` waits for a yes". It is already an open question for the owner in
  TASKS.md ("Two answers to 'may the agent synchronise'") and is fixed only after that decision.

## D. Stale statements

- `README.md:9` "Six skills cover sixteen objects"; the "Deliberately out of scope" paragraph
  lists summaries, materialized tables and remote tables, which `/denodo:materialize` covers.
- `.claude-plugin/plugin.json` description omits `security`, `ai`, `testing`, `scheduler`;
  `.claude-plugin/marketplace.json` still says "catalog, data sources, views, and Data
  Marketplace entries".
- "outside v1" where a skill now exists **(checked)**: `views/references/derived.md:88`
  (privileges → `/denodo:security`), `views/references/delegation.md:125–127` ("a copy in one
  database is Design Studio" → `/denodo:materialize`), `views/references/dependencies.md:126–128`
  ("none of them does in the plugin yet" → `/denodo:cache`), `catalog/references/database.md:56`,
  `datasources/references/base-view.md:111–112`, `procedures/references/predefined.md:87,89,92`.
  Also `df.md:123`, `jdbc.md:180`. "v1" is internal scope language in any case.
- `vql/SKILL.md:92` "All twelve VQL object types of v1"; `:45` the chain order lacks metric views,
  cache loads, summaries and Scheduler jobs; `:111` describes the mark as `verified: 9.5 (live,
  date)` while templates use `9.5.1`.
- `execute/references/errors.md:13–15` "Every row was reproduced … on 2026-09-08": several rows
  are later.
- `verification/chain.toml:2` "Verifies 72 of the templates" — the run verified 80.
- `datasources/references/jdbc.md:106` tells the agent to `ls <DENODO_HOME>/lib/extensions/jdbc-drivers`,
  while `SKILL.md:472–473` says there is no shell on the server.
- `scheduler/SKILL.md:43` expects `scheduler.ok: true` from `env check`, which skips the Scheduler
  when the profile has neither `scheduler_url` nor `marketplace_url`.

## E. Installation-flavoured, harmless (medium)

- **Demo data as example data.** TPC-DS tables of the demo image (`income_band`,
  `household_demographics`, `web_returns`, `reason`, `store`) are the example data of `views`,
  `metrics`, `materialize`, `security`, `semantics`, `testing`, `scheduler`, `cache`,
  `datasources`. **Decision for T37:** the verified templates run verbatim in the chain on exactly
  this data, so renaming them means rebuilding fixtures. Default: keep the names in templates
  the chain runs; replace them in prose and unverified examples, and remove the TPC-DS-specific
  tells (`>= 2457754` date key in `views/references/unions.md:89,93`, `'0-500          '`,
  twenty bands verbatim in `testing/SKILL.md:183–203`, `XEPDB1` in `datasources/SKILL.md:363`).
- **Numbers measured on one server** stated without that qualifier: row counts and shares
  (`views/SKILL.md:102–109`, `cache`, `datasources/references/df.md:71`, `vql/references/dialect.md:75,78,109,113,203,208`),
  timings (`ai/SKILL.md:27,33,47,310`, `ai/references/vectors.md:80–84`,
  `marketplace/SKILL.md:197`, `materialize/SKILL.md:212`, `summaries.md:102,155`), sizes of APIs
  (`marketplace/SKILL.md:492` "375 paths", `scheduler/references/rest-api.md:5` "91 paths").
  Keep the behaviour, drop the count or label it "measured once".
- **Quirks of the demo files stated as rules:** "file sources pad text to the column width" and
  "a missing field is `''`" (`vql/SKILL.md:202`, `vql/references/dialect.md:44`,
  `testing/SKILL.md:250`). A file source *may* do this; check with `LEN`.
- **One setup's zones and errors:** `UTC+3` (`scheduler/SKILL.md:108,414–416`), `us_pst` inside
  error texts (`dml/references/writable-views.md:40,65`), the SQL Server driver's truncated text in
  `dml/SKILL.md:39,382`, `'es_euro'` in `views/references/derived.md:87`, `+04:00` in
  `testing/references/format.md:77`, `vdp.dbAdapter=denodo-9.0.0` (`format.md:178`, one release's
  driver folder), "`%TRACE` fails every test on 9.5.1" (`testing/SKILL.md:238`, one Testing Tool
  release).
- **Anecdotes and process words:** "On the server used for verification…"
  (`marketplace/references/tags.md:61–62`, `catalog/references/database.md:48`), "every one created
  while verifying this skill" (`external-elements.md:123–127`), "*Owner's decision for this
  plugin.*" (`materialize/SKILL.md:71`), "in the verification chain" (`materialize/SKILL.md:130`,
  `remote-tables.md:85–86`, `dml:96`, `ai:107`, `security:133`), the probe prefix in
  `remote-tables.md:141`, "A demo is cheaper…" (`execute/SKILL.md:203`).

## F. Verification marks

- Runnable blocks without a mark, per the reviewers: `dml/SKILL.md:134,272–274`;
  `ai/SKILL.md:236–237,272–274`, `ai/references/functions.md:108–111`;
  `security/SKILL.md:74–75,224`; `datasources/SKILL.md:479–480`, `base-view.md:101–105`;
  `materialize/references/summaries.md:146`, `remote-tables.md:29`;
  `views/references/associations.md:75–79,120–126`; `marketplace` Verify table `:503–512`,
  `external-elements.md:63–65`; `scheduler/SKILL.md:235–269,409–420`;
  `semantics/SKILL.md:259,264`; `metrics/SKILL.md:47–50,222–224,328`;
  `testing/SKILL.md:141–142`; `vql/SKILL.md:104`.
- Normalise the off-format marks (Results).
- `materialize/references/summaries.md:124`: the incremental-load example `CUSTOM LOAD QUERY
  'SELECT * FROM sales …'` contradicts the red flag "`SELECT *` in a load query" two lines up.
- Re-mark with `verify --update-marks` after the fixes, not by hand.

## G. Smaller items

Inconsistent `--env dev` versus `<env>` in commands; `procedures/SKILL.md:144–145` looks a user
procedure up without `--database`; `views/SKILL.md:611` omits `metric` from the subtypes;
`catalog/SKILL.md:139` calls `type` rows server-internal while `views/references/arrays.md:97`
says `NEST`/`REGISTER` leave `_array_register_*` types behind; `materialize/SKILL.md:127–129`
(`''`) versus `remote-tables.md:16–17` (`null`) for a database without catalogs;
`ai/SKILL.md:340` heads a table "Reads that send nothing" over a row (`:349`) that sends one
request; `marketplace/SKILL.md:523` puts the `403` of a missing `serverId` under the paging row;
`external-elements.md:52` "A own type"; `ai/references/functions.md:45` mark "(documentation)".

## Recommendations for vibe-coding (not part of T37)

1. **CI on every pull request** — none exists. Unit tests, `claude plugin validate`, and a lint
   for what this review checked by hand: Cyrillic, installation words, description ≤ 1024,
   a mark next to every template, `references/` links and skill names that resolve.
2. **A verification chain any server can run** — fixtures shipped in the repository, the values
   (`csv_dir`, embedding model, write data source and its DDL) overridable from a local file, and
   the `references/` templates added. "Run `verify` on your server" becomes a new user's first
   step and tells them which templates to trust there.
3. **A preview before apply** (`vql plan` or `--dry-run`): which objects are new, which are
   replaced, which statements are destructive — before anything runs.
4. **Outcome evals beside the routing ones** — the acceptance scenarios (T13, T19) as repeatable
   runs against a test server, graded on the objects they leave.
5. **A first-run command** (`/denodo:init` or similar): the profile, `env check`,
   `.denodo/conventions.md` — today manual steps in the README.
6. **Bulk work** — three reviewers hit the same gap independently: base views for forty tables,
   one tag on every email column, descriptions for hundreds of views.
7. **Bringing an existing view into the project's files** (`DESC VQL` with safe options → `.vql`)
   came up in `views` and `vql`; the roadmap review dropped exporting server objects into the
   project with `deploy` — the owner's call whether this narrower case returns.
8. **Narrow template gaps**, under the narrow-scope policy: de-duplication / current row per key
   (`views`), year-over-year and running totals (`metrics`), "each person sees their own rows" and
   revoking access (`security`), deleting a Scheduler job, removing a marketplace tag from a view.
