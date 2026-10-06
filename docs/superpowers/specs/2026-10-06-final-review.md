# Final review of the skills (2026-10-06)

The owner asked for a final review of the repository on five points:

1. every skill is phrased generically, not tied to cases of the server the skills were tuned on;
2. the skills contain no language but English;
3. the texts carry no redundancy that wastes the agent's context;
4. every statement agrees with the official Denodo 9.5 documentation;
5. the minimal necessary scope is covered, and further development should come only from
   vibe-coding experience on the platform.

This document is the verdict. Every finding behind it, with its location and fix, is in
[2026-10-06-final-review-findings.md](2026-10-06-final-review-findings.md); the fixes are tasks
T44–T46 in [TASKS.md](../../TASKS.md).

**Base commit:** `2fa6fbd` (after T43). Line numbers are as of that commit.

**Method.** Mechanical checks first: the unit tests (848 OK), the skills lint (clean), a scan of
every non-ASCII character in `skills/`, and a shingle scan for near-duplicate prose (137 line
pairs, 49 of them across skills). Then the documentation: 1,000 pages of the 9.5 guides (VQL,
VDP Administration, Developer, Data Marketplace, Scheduler, release and upgrade notes) and the
Testing Tool manual, downloaded as text so that every claim could be checked against a page
rather than against memory. Then 37 read-only reviewers: for each skill, one on points 1–3 and
one on point 4, each reading every line of the skill and its references; and five across the
repository — context economy across skills, scope through a user's and a maintainer's lens, the
files outside `skills/`, and a pattern sweep for installation values. Every finding then went to
a separate skeptical verifier told to refute it when uncertain: **448 reported, 62 refuted, 386
survive** (216 as reported, 170 with a corrected severity, line or fix). The highest claims were
re-checked by hand against the documentation pages. No server was contacted: the `verified`
marks were not re-run.

## Results

| Point | Verdict | Survived (high / medium / low) |
|---|---|---|
| 1 — generic | **Passes on names and values; a residue of one installation's settings stated as Denodo's behaviour.** No ids, hosts, datasets or test-run names beyond one element id; what remains are time zones, licences, privileges, the LLM provider and SQL Server results presented as the rule | 54 (2 / 12 / 40) |
| 2 — English | **Passes in `skills/`.** Outside it, `evals/README.md` is half Russian and is where `CONTRIBUTING.md` sends contributors | 4 (0 / 1 / 3) |
| 3 — economy | **About 13 % of the `SKILL.md` text repeats itself** — about 65,000 of 483,000 characters, plus about 25,000 in references. The waste sits in a few places; ten duplicates have already drifted into contradictions | 161 (3 / 46 / 112) |
| 4 — documentation | **Strong on syntax, weaker in prose.** Every grammar matches; the defects are in what the prose says about privileges, licences, deprecated forms and the alternatives the documentation describes. Five statements are wrong in a way that changes what the agent does | 147 (5 / 40 / 102) |
| 5 — scope | **Agree, with conditions.** No object skill is missing; four boundaries the agent cannot see, and the loop that turns a session into a skill change is not in the repository yet. The plugin's pinned version keeps every existing install on the September snapshot | 20 (1 / 4 / 15) |

By skill (all points):

| Skill | 1 | 2 | 3 | 4 | 5 | high | medium | low |
|---|---|---|---|---|---|---|---|---|
| ai | 6 | 0 | 7 | 3 | 0 | 0 | 1 | 15 |
| cache | 2 | 0 | 6 | 10 | 0 | 0 | 3 | 15 |
| catalog | 0 | 0 | 13 | 12 | 0 | 0 | 7 | 18 |
| datasources | 7 | 0 | 14 | 17 | 1 | 2 | 12 | 25 |
| dml | 4 | 0 | 11 | 11 | 0 | 1 | 7 | 18 |
| execute | 2 | 0 | 19 | 6 | 2 | 1 | 11 | 17 |
| marketplace | 4 | 0 | 12 | 9 | 0 | 1 | 8 | 16 |
| materialize | 2 | 0 | 6 | 9 | 0 | 1 | 4 | 12 |
| metrics | 1 | 0 | 11 | 5 | 0 | 0 | 4 | 13 |
| procedures | 3 | 0 | 10 | 12 | 0 | 1 | 9 | 15 |
| scheduler | 4 | 0 | 6 | 6 | 0 | 0 | 0 | 16 |
| security | 3 | 0 | 8 | 8 | 0 | 0 | 8 | 11 |
| semantics | 3 | 0 | 9 | 8 | 0 | 0 | 2 | 18 |
| testing | 2 | 0 | 5 | 3 | 0 | 0 | 1 | 9 |
| views | 1 | 0 | 13 | 12 | 1 | 0 | 11 | 16 |
| vql | 4 | 0 | 11 | 6 | 4 | 2 | 10 | 13 |
| outside `skills/` | 6 | 4 | 0 | 10 | 12 | 2 | 5 | 25 |

Several findings were reported by more than one reviewer; the sections below name each defect
once with all its ids.

## Point 1 — generic

The lint and the sweep agree: no name of the test installation is left in `skills/`, and engine
behaviour is mostly labelled with its engine. One stray value the lint cannot see: a real element
id, `7446`, in a response comment of a marketplace template (`marketplace/SKILL.md:240`,
marketplace-A9). The rest is subtler — a setting or a property of the server the skills were
tuned on, written as if Denodo did it everywhere.

**High.**

- **Time zones of writes** (dml-A1, dml-A2, dml-B2, dml-B3, sweep-1). `dml/SKILL.md:220-222`
  offers `TIMESTAMP WITH TIME ZONE '… -07:00'` "(stored as `16:30`)" for a UTC column, and
  `references/statements.md:116-117` says such values are "converted to UTC". That holds only
  where the server's zone is UTC; the VQL Guide converts with the zone of the server's i18n. On a
  server in CET the same write stores 18:30, silently, in a source table that cannot be rolled
  back. Fix: convert and write a `TIMESTAMP '…'` literal; say that a zoned value lands in the
  server's zone (UTC on the server measured).
- **"Built-in" external element and provider types** (marketplace-A1, marketplace-B1,
  marketplace-A8, sweep-2; also point 4). `marketplace/SKILL.md:376-387, 485` and
  `references/external-elements.md:14-47` call 24 element types and 28 provider types "built in on
  9.5.1" and the type steps "usually unnecessary". The documentation names only the Report type
  (Tableau, Power BI) as always present and creates `DATA_PRODUCT`, `GLOSSARY`,
  `DATA_PRODUCT_PROVIDER`, `SCHEDULER_PROVIDER` and others by `POST` in its own setup example: the
  list is the sample content of one installation.

**Medium — what the tuning server had and the text assumes.**

- **Licences and add-ons never stated in `SKILL.md`.** VDP tags and global security policies
  need the Enterprise Plus bundle (security-A1, catalog-B2, semantics-A1, semantics-A3); importing
  VDP tags into the marketplace needs the Semantics FeaturePack (marketplace-B3). `env check`
  already reports `features`; no skill reads it before such a path (see point 5).
- **An administrator profile and VDP user objects.** `security` assumes the profile is an
  administrator (security-A3) and that every person is a VDP user — not an LDAP, Kerberos or
  identity-provider account whose access comes from group roles (security-A2).
- **The LLM provider's properties as Denodo's** (ai-A1, ai-A3, ai-A2, sweep-7, sweep-8): "about a
  second each" turns into the time the human approves; "billed by the provider" and "every text
  leaves for an outside provider" are false for a self-hosted model; lower-case sentiment labels
  are the model's answer, not a contract.
- **SQL Server results stated as general:** the cache's collation, `NULL` order and decimal scale
  (cache-A1), `DENY` (materialize-A2), `numeric(38,20)` (materialize-A3), a case-insensitive
  collation as SQL Server's behaviour (vql-A9, sweep-5).
- **The wrong-password message** (execute-A1): `The username or password is incorrect` is VDP's own
  text — the check behind the mark used a data source pointing at VDP itself. PostgreSQL, SQL
  Server and Oracle answer with their own messages.

**Low** (in the appendix): `us_pst` as the fallback i18n (sweep-3), driver directories pinned to
the tuning databases' versions (datasources-A1, sweep-4), `Errno 61` of macOS (execute-A2), a
Unix-only launcher line (sweep-10), padded text attributed to file sources (vql-A10, testing-A6),
"the sample data" (views-A1), TPC-DS data stories told as general cases (vql-A11), a Scheduler
assumed to run in UTC (scheduler-A1), `admin` as the name of an administrator (scheduler-A3),
cache maintenance assumed on (cache-A2).

**Outside `skills/`, high:** `verify --with-marketplace` synchronises the whole shared catalog at
the start and again in cleanup, with no check of what other teams have pending, while README says
the run "removes everything it made" (repo-1). On the tuning server nothing else was pending; on a
shared server the run publishes and deletes other people's catalog entries. The outcome runner
already guards this case (`catalog_pending`); `verify` needs the same guard. Medium: the
`jdbc-generate-schema` step passes only if the cache schema already holds a table, so it fails on a
fresh installation (repo-4, plausible — not reproduced).

## Point 2 — English only

**`skills/` passes.** The only non-ASCII characters are typography (—, …, →, box drawing, ×, ½,
Σ, ¹) and sample strings that demonstrate a behaviour (`straße`, `Tokyo 東京`, `domingo`, `ene`).
Spelling is consistently British, with one mixed optimiser/optimizer in `views`.

Outside `skills/`, in files that ship with the plugin (the marketplace source is `./`, so the
whole repository lands in every user's plugin cache; nothing there loads into context):

- `evals/README.md` has 67 Russian lines — how to run the suite, the anatomy of a case, how to
  read a failure — and `CONTRIBUTING.md:221-222` sends every contributor there; the lint skips the
  file on purpose (repo-2, repo-7, scope-user-8, scope-maintainer-13, medium);
- three comments in `.gitignore` (repo-8), and the two scripts in `spikes/`, mostly Russian with
  paths of the author's server (repo-9);
- `docs/` and `CLAUDE.md` — the owner's working files, Russian in part (repo-21, information).

## Point 3 — economy of context

**What a task costs.** The sixteen descriptions are always loaded: 12,145 characters (about
3,000 tokens). `vql` is 29,200 characters, `execute` 24,300; a domain skill adds 12,500 (`procedures`)
to 55,300 (`views`). The outcome traces show what really loads: `execute` in 39 of 57 runs, `vql`
in only 18 — `metric-view` loaded `metrics` without `vql` 10 of 10, `dml-preview` loaded `dml`
alone 6 of 6. A typical task therefore reads the descriptions, a domain skill and `execute`:
12,000 to 23,000 tokens; `vql` adds 7,300 in about a third of the sessions.

**Consequence: the local copies of the safety rules are not the waste.** The confirmation
table of each domain, "the request is not the yes", "when you cannot ask", the AI cost reminder
and the production red flag carry weight precisely because `vql` is often not loaded
(cross-economy, rules 1–4, 10, 11). The waste is on the core side — `vql` and `execute` holding
domain manuals — and in a few domain bodies that state the same facts two or three times.

**The largest cuts** (savings measured by the verifiers; duplicates across reviewers counted once):

| Where | What | Saves | Ids |
|---|---|---|---|
| `vql/SKILL.md:114-117, 168-216` | the HTTP rules, both synchronize exceptions and two rationalization rows — marketplace-only, read on every `vql` load, all held in full by `marketplace` | ~3,900 | vql-A1, cross-1 |
| `vql/SKILL.md:141-152, 307-325` | long rows of the core table that restate domain tables; a routing table that paraphrases the descriptions — keep a short map (design spec §10 makes the core the map of skills) | ~3,000 | cross-5, cross-6, vql-A2 |
| `execute/SKILL.md:40, 43` | the `verify` row (1,954 characters, the plugin's self-test) and the `testing run` row that `testing` owns | ~2,300 | execute-A4, execute-A10, cross-2, scope-maintainer-10, testing-A1 |
| `execute/SKILL.md:144-166, 189-222` | the data-source password procedure (`datasources` owns it) and the full list of flagged statements (move to `references/errors.md`) | ~2,700 | execute-A5, cross-7, cross-3, execute-A7 |
| `marketplace/SKILL.md:215-320` | rename, recreate and move a view — a rare path entered from `views`: move to `references/renames.md`; takes the file under 500 lines | ~8,200 moved | marketplace-A2 |
| `marketplace/SKILL.md:198-207, 361-374, 482, 555-562` | restatements of `vql`'s two exceptions and `execute`'s refusal | ~1,800 | marketplace-A3 |
| `materialize/SKILL.md:31-50` | a 15-row facts table that repeats the Silent failures table row for row | ~3,500 | materialize-A4 |
| `dml/SKILL.md:13-39` | "What a write does", every row restated in the same body; a table of contents | ~3,100 | dml-A5, dml-A6 |
| `datasources/SKILL.md` | the hand-written JDBC wrapper (a fallback) to `references/jdbc.md`; small rules stated two or three times; a closing paragraph that repeats an earlier section | ~5,000 | datasources-A8–A12 |
| `metrics/SKILL.md`, `references/metric-views.md` | period bullets that restate `periods.md`; dialect rules owned by `vql`; a 25-row query table and an expression table that repeat the body | ~5,100 | metrics-A7, A8, A11, A12 |
| `views/SKILL.md` | `SUM` over `int` at paragraph length; the marketplace rename paragraph; Silent failure 3 restated | ~2,800 | views-A5, A6, A7, cross-8, cross-9 |
| across skills | error texts quoted in the prose and again in Common mistakes — keep the table, the copy the agent matches against | ~3,000 | ai-A5, cache-A5, catalog-A1, procedures-A1, views-A8, scheduler-A9 |

**Duplicates that have drifted** — each is a second copy that now says something else, the
strongest argument for cutting the rest:

- `catalog/SKILL.md:17` builds tags last; the same skill's lines 96-97 and 143-144, `views` and
  `vql` put a tag before the views that name it (catalog-A2);
- `catalog/references/{folders,database,tags}.md` and `views/SKILL.md:333-334` with
  `references/interface.md:125` ask for a yes before any `ALTER`; `vql` asks only for an object
  older than the session (catalog-A4, views-A13);
- `catalog/SKILL.md:188` and `references/folders.md:87-88` disagree on what `type` rows are
  (catalog-A5); two rules for which statement assigns a tag (catalog-A3);
- `marketplace/SKILL.md:481` says "`id:null` means synchronise first" against rule 2 and row 535
  (marketplace-A4);
- `procedures/SKILL.md:171` fixes a syntax error by dropping `AS ( )`, which the body and the
  grammar call required (procedures-A2, procedures-B4);
- `execute/SKILL.md:255-257` calls re-applying a file safe, against `vql`'s exception for tables
  that hold rows, `materialize` and `dml` (execute-A12);
- `datasources/references/base-view.md:154-158` checks dependants with a procedure that answers the
  opposite question, while `views` uses `USED_BY` (datasources-B1, datasources-A13);
- `dml` measures zoned writes in UTC while `vql`'s dialect measured the server's zone as `-07:00`
  on the same server (dml-A1, see point 1).

**Kept on purpose:** the descriptions (one clear 75-character win, cross-14), the templates, the
Silent failures and Common mistakes tables, the domain copies of the safety rules, the summary of
`dialect.md` in `vql`'s body, and the "Many objects at once" section (set requests are frequent).

**Total if every point-3 finding is applied:** about 65,000 characters off the `SKILL.md` bodies
(13 %; about 8,000 of them moved to references, not deleted) and about 25,000 off references —
roughly 10–20 % of the skill text a typical task reads.

## Point 4 — agreement with the documentation

**Where it is strong.** Every grammar the skills give — `CREATE VIEW`, `CREATE INTERFACE VIEW`,
`FLATTEN`, `NEST`, the data source and wrapper statements, `ALTER … CACHE`, `CREATE GLOBAL_SECURITY_POLICY`,
`CREATE METRIC VIEW`, remote tables and summaries, the Scheduler and Testing Tool formats — matches
the guides clause for clause, and the places where the server differs from the guide are marked
live and mostly say so. The defects are in prose, in five recurring forms below.

**High — the agent does the wrong thing.**

- **The dependants check walks the wrong way** (datasources-B1). `base-view.md:154-158` runs
  `GET_PUBLIC_VIEW_DEPENDENCIES` before replacing a base view; the documentation: it "returns the
  nearest lineage of a view … from which a view was built on". On a base view it answers with its
  data source, never the views above, so the check before a destructive replace always comes back
  empty. `USED_BY` is the procedure (as `views` uses).
- **The DF template declares the deprecated `date` type** (datasources-B2, datasources-B6,
  execute-B1; the open question of T43). `datasources/SKILL.md:177, 205`, `df.md:112, 117`,
  `base-view.md:52, 91` and `execute/references/errors.md:70` teach `date` and `TO_DATE`; the
  documentation: `date` "should not be used anymore", `TO_DATE` "avoid … on new projects". Use
  `localdate` and `TO_LOCALDATE`; re-run the chain steps that read those base views.
- **"Input parameters are named `input_…`"** (procedures-B1). False for about forty documented
  procedures — `PING_DATA_SOURCE`, `REFRESH_BASE_VIEW`, `CLEAN_CACHE_DATABASE`,
  `CREATE_REMOTE_TABLE`, `DROP_REMOTE_TABLE`, `CATALOG_PERMISSIONS` — and the fix cell at
  `procedures/SKILL.md:173` sends a failed `PING_DATA_SOURCE` call to a form that fails again.
- **Summaries "on the Enterprise Plus bundle"** (materialize-B1), labelled as documentation; the
  documentation: "not available in Denodo Professional or in Denodo Standard" — Enterprise has
  them. An agent would tell an Enterprise customer the feature does not exist.
- **The marketplace's "built-in" types** — see point 1.

**Medium, by kind** (with the low items of the same kind).

1. *What the skills say about the documentation itself is wrong.* "There is no `CREATE
   ASSOCIATION` page in the public VQL Guide" (`views/SKILL.md:360, 403`,
   `references/associations.md:7-10`) — the VQL Guide documents `CREATE` and `ALTER ASSOCIATION`
   under RESTful Architecture → Associations, with a description per endpoint, expressions in
   mappings and the `(+)` multiplicity the skill does not know (views-B1). "The other `CATALOG_*`
   procedures are deprecated" — only four are; `CATALOG_PERMISSIONS`, which `security` relies on,
   is current (vql-B1). Window functions "by the documentation" run only when delegated (vql-B2).
2. *Alternatives the documentation describes are denied.* A join across two data sources is
   "never" run in a database — Data Movement and MPP do exactly that (views-B3); a referential
   constraint is the documented condition for pushing a `GROUP BY` below such a join (views-B2);
   window functions run through MPP or data movement (views-B4, metrics-B2); `GET_CATALOG_METADATA_WS`
   lists the web services that publish a view, across databases (views-B5); `LIST RESOURCES JDBC`
   lists the drivers an administrator imported (datasources-B4); one JSON or delimited-file source
   reads a whole directory (datasources-B18, vql-B3 — the latter in `vql`'s always-read naming
   table).
3. *Results that depend on who asks are presented as complete.* `CONTEXT ('cache' = 'off')` takes
   effect only with `WRITE` on the view or the `disable_cache_query` role, otherwise the server
   silently reads the cache and the "source vs cache" check compares the cache with itself
   (cache-B2); `CATALOG_PERMISSIONS` returns only the caller's own grants for anyone but a global
   administrator (security-B2); `USED_BY` lists only what the caller may see (cache-B12);
   `CLEAN_CACHE_DATABASE` is for global administrators (cache-B1); a consumer sees an external
   element only with its type's Visualize permission (marketplace-B4).
4. *A feature is described wrongly.* `ALLOWED_PATHS` is a file-system allowlist that replaces the
   `FILE` privilege, not a restriction to catalog folders (security-B1); `VIEW_DATABASES` must name
   the database of the tagged view, not only the one people query (security-B3);
   `impersonate_roles` leaves out `allusers`, which every local user holds (security-B4);
   `CHECK_INDIRECT_ACCESS` protects the procedure itself (procedures-B7); a JAR is uploaded through
   Design Studio or `CREATE JAR`, not placed on the server's disk (procedures-B6);
   `GET_STATS_FOR_FIELDS` with `input_save = true` stores statistics, and `CHECK_METADATA`,
   `CHECK_CACHE_NAMES` and `MIGRATE_DATE_TYPES` change state — missing from the list the tool
   checks (procedures-B2, procedures-B3; `scripts/denodo_cli/safety.py` changes with them);
   `SUMMARY REWRITE` is an `ALTER DATABASE` clause (materialize-B2); a `CUSTOM LOAD QUERY` does not
   make `REFRESH` incremental (materialize-B3); `WITH CHECK OPTION` comes before `CONTEXT` (dml-B1);
   an upsert's key on MySQL and PostgreSQL must be the primary key or a unique index (dml-B4,
   materialize-B5); `ENDOFLINEDELIMITER '\r\n'` is what the Administration Guide forbids
   (datasources-B5); MySQL through the MariaDB driver contradicts "only the official driver"
   (datasources-B3); the marketplace's `direction` is the data flow, not its opposite
   (marketplace-B2); a folder listing before `DROP FOLDER … CASCADE` can miss the folder because
   `GET_ELEMENTS` returns `folder` in lower case (catalog-B1); `CREATE OR REPLACE DATABASE` is not
   documented to keep the authentication it does not name (catalog-B3); "stop" a job where
   disable is meant (scheduler-B2); the AI consumers do send sample rows to their LLM, and the MCP
   tag does not bypass privileges (semantics-B1, semantics-B4); in `errors.md`, only the views that
   used a changed column go `INVALID`, and a policy that names a tag also blocks `DROP TAG`
   (execute-B2, execute-B3).

**Low:** about a hundred terminology and precision items, one line each — deprecated names left
unflagged (`LIST_JDBC_DATASOURCE_TABLES`, `jdbc:vdb`), the Lakehouse Accelerator and Embedded MPP
treated as two features, the 9996 port called the VDP port (it is the ODBC port), "AI assistant"
for Denodo Assistant, Scheduler job types under unofficial names, and so on.

**Not checkable against the guides:** the Data Marketplace REST API (documented only in the
server's Swagger UI) and about thirteen Testing Tool behaviours that come from its sources jar.
Both rest on the live marks.

## Point 5 — scope

**Verdict: agree, with conditions.** The two scope reviewers reached it independently.

**What holds.** All sixteen objects of the first scope are built and were accepted live
(milestones A and B), ten skills go beyond it, and the verification chain runs 174 steps. Of the
twenty most frequent requests of a first week, fifteen have a complete path the agent follows
without guessing syntax. No missing object skill blocks the path from a phrase to a mart, and the
owner's cuts — REST, SQL-query, Excel and SAP sources, schema drift, partial cache, deploy — still
look right: each is rare in the first weeks or a few clicks in Design Studio.

**Beyond a first week:** `ai`, `dml`, `materialize`, `scheduler` and `testing` go past what a
first week asks, by the owner's deliberate choice, and no reviewer found a reason to cut them (the
claims that they, or the Java half of `procedures`, are over-built were refuted: Java stored
procedures are not among the extensions the roadmap dropped). They are the most expensive to keep
verified — 73 of the 174 chain steps run only behind tails that cost money or write outside the
test database — so the recommendation is to freeze them: keep them correct, grow them only from
sessions.

**Conditions before "the minimal scope is covered":**

1. **Brownfield.** On an existing installation the most common request is to change a view a
   colleague built in Design Studio — and it has no project file. Every path assumes one
   (scope-maintainer-5). This is not new: it is the owner's open call recorded in `TASKS.md` since
   the 2026-10-05 review — a single recipe in `views` (read the definition with `DESC VQL`, write
   the file, plan, apply). Both scope reviewers name it as the one decision to revisit.
2. **The boundary the agent cannot see.** Publishing a view as a REST, SOAP, OData or GraphQL
   service, listeners, Java extensions, users and LDAP, promotion between environments, dbt —
   outside the plugin by decision, but stated only in README. `vql`'s map has no row for them, and
   `CREATE … WEBSERVICE` and `DEPLOY` plan as `other`, so the agent could improvise them without a
   yes (scope-user-2, scope-maintainer-6). One row in the map and one line in the confirmation
   column.
3. **Licences and versions.** `env check` returns `features` and `vdp.server_version`; no skill
   reads them before a tag, a policy, a summary or an AI path, or before applying 9.5 syntax to an
   older server (scope-maintainer-9, scope-user-11; the licence gaps of point 1).
4. **An existing database's own conventions.** Only `.denodo/conventions.md` overrides the
   default folders and prefixes, so in a team's database without one the agent creates the layer
   folders beside the team's own (scope-user-3).

**The second half of the claim** — develop only from experience — is the right policy, but the
repository supports it only for its owner today. The tools exist (outcome runner, session ledger,
`vql plan`, a `verify` that runs on any server); the intake and the method do not:

- **The version is pinned.** `.claude-plugin/plugin.json` has said `"version": "0.1.0"` since the
  scaffold (230 commits ago). The Claude Code plugin reference: setting `version` "keeps users on
  that version until you change it" — every existing install still runs the September skill texts,
  and no field report can name the text it ran (scope-maintainer-8, repo-3, high). Either drop the
  field (users then track commits) or bump it on every merge that touches `skills/` or `scripts/`.
- **No intake.** No issue template, no "the agent got it wrong in my session" path, no list of
  what to attach and how to strip client names (scope-maintainer-1, scope-user-5).
- **The method lives outside the repository.** The RED/GREEN routine that drove every task since
  T27 is described nowhere a contributor reads (scope-maintainer-2). `CONTRIBUTING.md` still
  invites new objects and source types the owner has declined (scope-maintainer-7), and leaves out
  the outcome scenarios (scope-user-7, repo-17); the evals guide is half Russian (point 2).
- **The scenarios cover creation, one write and one drop** (low; the set of six is the agreed
  scope of T42). The requests that will produce most of the experience — changing a view others
  use, granting access, a JDBC schema — are the natural next scenarios once sessions show them
  failing (scope-maintainer-4).

## Recommendation

The closing work, then the freeze the owner proposes. In order (split into T44–T46 below):

1. **The version** — the owner's choice between no `version` and a bump rule; one notice to existing
   users to reinstall.
2. **The five high and ~45 medium findings of points 1 and 4**, with `verify` re-run for every
   changed template (`date` → `localdate` touches two chain steps) and `safety.py` extended for the
   state-changing procedures.
3. **The drifted duplicates, then the core-side cuts of point 3** (`vql`'s marketplace section,
   `execute`'s domain manuals, `marketplace` renames to a reference, the facts tables of
   `materialize` and `dml`). Re-run the `marketplace-tag` and `drop-under-pressure` outcome
   scenarios — they measure exactly the rules being moved — and the routing suite if a description
   changes.
4. **Scope conditions 2–4**: the out-of-plugin row and its plan kind, reading `features` and the
   server version, following an existing database's conventions.
5. **The experience loop**: an issue template, a "from a session to a skill change" section in
   `CONTRIBUTING.md` (redact, reproduce on a synthetic fixture, RED, change, GREEN, keep a scenario),
   `evals/README.md` in English, `spikes/` translated or removed.
6. **`verify --with-marketplace`** guarded like the outcome runner, and `jdbc-generate-schema`
   moved after the cache load.

**Decided by the owner (2026-10-06):** the brownfield recipe goes into `views` (condition 1);
`version` is removed from the manifests, so users track commits; `vql` keeps a short map of the
skills. The work is three tasks instead of one — T44 (what an agent would get wrong: points 1 and
4, the version, `verify`), T45 (the drifted duplicates and the cuts of point 3), T46 (the scope
conditions and the experience loop) — in `TASKS.md`. The ~270 low findings are one-line edits made
in the same passes, file by file. Thirteen side observations the reviewers noted outside their
own point were checked afterwards and added to the appendix (three medium: side-3, side-4,
side-12).

After that, the claim of point 5 holds without conditions: no new object skill until a session
asks for it.
