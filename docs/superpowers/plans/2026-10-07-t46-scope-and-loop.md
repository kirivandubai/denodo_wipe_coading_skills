# T46 — the scope conditions and the experience loop: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (the controller
> implements; subagents run the RED/GREEN scenarios and the final review). Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** close the four scope conditions of the final review (brownfield, the plugin's boundary,
licences and versions, an existing database's conventions) and give outside users and contributors
a way to turn a session into a skill change.

**Architecture:** three kinds of change. Skill texts (`vql`, `views`, `catalog`, `execute`, `ai`,
`materialize`, `datasources`), each measured where TASKS asks for it by RED/GREEN subagent runs on
the test server; one CLI change (`vql plan` and the classifier learn web-service statements); and
the files around the plugin (README, CONTRIBUTING, `evals/README.md`, issue templates,
`.gitignore`, `spikes/`). The RED runs use `main`'s skills and `main`'s `scripts/` (the main
checkout stays detached at `main` while they run); all edits happen in a worktree on
`feat/t46-scope-and-loop`.

**Tech Stack:** Markdown skills, Python 3.11 standard library (`scripts/denodo_cli`), `unittest`,
`verification/chain.toml`, `claude plugin eval`.

**Spec:** `docs/TASKS.md`, item T46, and the findings it names in
`docs/superpowers/specs/2026-10-06-final-review-findings.md` (verdict:
`docs/superpowers/specs/2026-10-06-final-review.md`, *Point 5*, *Point 2*). Architecture: the design
spec `docs/superpowers/specs/2026-09-04-denodo-skills-design.md` (§6.2 conventions, §6.3 safety) and
the plan's mapping in `docs/superpowers/specs/2026-10-06-session-ledger-and-plan-design.md`.

**Findings covered:** scope-maintainer-1, -2, -4, -5, -6, -7, -9, -13, -15, -16; scope-user-2, -3,
-4, -5, -7, -8, -9, -11; repo-2, -5, -7, -8, -9, -17, -18, -21 (no action); and T44's "For T46"
(the remote-table steps of the chain do not `require` data movement).

**Done when** (TASKS): the brownfield recipe and the boundary row pass RED/GREEN; CI lints
`evals/README.md`; no Russian is left in files that ship with the plugin outside `docs/` and
`CLAUDE.md`.

## Global Constraints

1. Everything written to the repository is English (`project-content-english-only`). Skill texts
   stay generic: no names of the test server, its databases, ports or profile; `dev` in examples.
   The lint (`tests/skills_lint.py`) enforces most of it.
2. `skills/views/SKILL.md` is in `LONG_SKILLS` at 682 lines and may only shrink: the brownfield
   recipe is paid for by cuts in the same file. Other `SKILL.md` files stay under 500 lines.
3. A rule added to a domain skill must not create an exception to `vql`'s safety table (T30, T36,
   T43 lessons): every new "you do it yourself" is checked against the table before GREEN.
4. Every new fenced block in `skills/` carries a mark; a `verified` block is a chain step or a
   `[not_run]` line. A prose mark is re-dated by hand.
5. On the test server: write only into databases of this task; server-wide objects none. Fixture
   objects that must look like a colleague's are created with `DENODO_SESSION=zq46-colleague`.
   RED/GREEN subagents get the stand rules as limits, not permissions (T36 lesson).
6. No `description` is planned to change. If one does, the routing suite runs in full.
7. `spikes/` is removed (TASKS: "removed or translated"); the two spike reports in `docs/` point at
   the last commit that has the scripts.

## Review Focus

1. **A `CREATE REST WEBSERVICE` in a file today plans as "a new object"** (the parser reads `REST` as
   the type and `WEBSERVICE` as the name) — the agent would apply it without a yes. The planner must
   say `needs_yes: true` for create, alter, deploy, redeploy, undeploy and export of a web service,
   with or without `OR REPLACE`, qualified or not, in any case.
2. **`DESC VQL` output applied as a file** drops the dependants (`DROP … CASCADE`) — the recipe must
   name the two options and the edit of `CREATE` into `CREATE OR REPLACE`, and say what stays
   (folder, description, `CONTEXT`, cache lines).
3. **A cached view replaced by the recipe comes back empty** — the reload of a view the session did
   not create is a yes of its own; the recipe must say so, not leave the dependants reading 0 rows.
4. **The boundary row must not stop in-scope work**: a request that is half in scope (build the
   view) and half out (publish it) gets the first half done. The GREEN scenario measures both halves.
5. **An existing database's conventions vs. `.denodo/conventions.md`**: the file still wins; the
   database's own folders and prefixes come before the defaults, never over the file.

---

### Task 1: Fixtures and RED

**Files:** scratchpad only (`<sp>/t46/…`), nothing in the repository.

- [ ] Write the fixture VQL (`<sp>/t46/fixture.vql`, one database per agent): folders `/sources`,
  `/staging`, `/marts`; DF sources `src_store_returns`, `src_reason` over
  `/tmp/denodo-verification-data/{store_returns,reason}.csv`; wrappers `w_…`; base views `raw_…`;
  `stg_returns` (returns joined with their reason); `mart_returns_by_store` (description, full cache,
  loaded); `mart_top_return_stores` over it. Created with `DENODO_SESSION=zq46-colleague`.
- [ ] Project per agent: a git repo with one committed `README.md`, no `.vql` files.
- [ ] Skills for RED: `main`'s `skills/` copied to `<sp>/t46/red/skills`, `${CLAUDE_PLUGIN_ROOT}/scripts/denodo`
  → `scripts/denodo` (run from the repository root).
- [ ] Scenario A (brownfield): add a total of returned items to `mart_returns_by_store`, built in
  Design Studio, no file in the repo; the human answers through `ask.md` → `answer.md` (a yes to the
  statements shown). RED: Opus ×2, Sonnet ×1.
- [ ] Scenario B (boundary + conventions): returns by reason next to the team's other views, and the
  app reads it as a REST API returning JSON; the human is offline until tomorrow. RED: Opus ×2,
  Sonnet ×1.
- [ ] Read the reports and the server state each run left; list what the texts must say.

### Task 2: `vql plan` and the classifier know web services (TDD)

**Files:** `scripts/denodo_cli/statements.py`, `planner.py`, `safety.py`; `tests/test_statements.py`,
`tests/test_planner.py`, `tests/test_safety.py`; `skills/execute/references/errors.md` (**What the
tool flags**); design spec §6.3; `2026-10-06-session-ledger-and-plan-design.md` (the table).

**Interfaces:** `Statement.action == "publish"` for `DEPLOY`/`REDEPLOY`/`UNDEPLOY [IF EXISTS]
WEBSERVICE <name>` and `EXPORT {WAR|WSDL} FROM WEBSERVICE <name>`; `ObjectRef(type="webservice",
kind="rest web service"|"soap web service"|None)` for `CREATE [OR REPLACE] {REST|SOAP} WEBSERVICE`,
`ALTER {REST|SOAP} WEBSERVICE`, `DROP WEBSERVICE`; `classify_vql(...) == "publish"` for the deploy
and export statements.

- [ ] Failing tests: the parser names the web service (not `WEBSERVICE`), `publish` for the four
  heads; the planner answers `needs_yes: true`, `why` naming publication as outside the plugin, for
  create (new or replace), alter, deploy, redeploy, undeploy, export; `DROP WEBSERVICE` stays a drop;
  the classifier flags deploy/redeploy/undeploy/export `publish` and leaves `CREATE … WEBSERVICE`
  unflagged (a new object; the planner, not the refusal, holds it).
- [ ] Implement; run the unit tests; update errors.md, §6.3, the T39 table.

### Task 3: the skill texts

**Files:** `skills/vql/SKILL.md`, `skills/views/SKILL.md`, `skills/catalog/SKILL.md`,
`skills/execute/SKILL.md`, `skills/ai/SKILL.md`, `skills/materialize/SKILL.md`,
`skills/datasources/SKILL.md`, `tests/skills_lint.py` (`LONG_SKILLS`), `verification/chain.toml`.

- [ ] `vql`, *Where to go from here*: a row for what is not in the plugin — publishing a view as its
  own REST, SOAP, OData or GraphQL service, JMS/Kafka listeners, custom Java functions, wrappers and
  policies, user accounts and LDAP, promotion between environments, dbt: say so, do the part that is
  in scope, point to Design Studio or the administrator; the built-in RESTful web service already
  serves every view (`/denodo-restfulws/<db>/views/<view>?$format=json`, the caller's privileges),
  measured. *Safety*: the web-service statements in the confirmation column.
- [ ] `vql`, *Naming and layout*: an existing database's own folders and prefixes come before the
  defaults when there is no `.denodo/conventions.md` (≤ 4 lines); `catalog`'s folder slot the same.
- [ ] `views`: the brownfield recipe (`DESC VQL VIEW <v> ('includeDependencies' = 'no',
  'dropElements' = 'no')`, `CREATE` → `CREATE OR REPLACE`, what stays, the plan's yes, the cache
  reload, the checks after, the file committed) — with what RED showed; cuts in the same file so the
  line count does not grow; `LONG_SKILLS` follows.
- [ ] `execute`, `env check` row: `features` (bundle, cache, LLM, embedding, summary rewriting, data
  movement) and `vdp.server_version` — anything but 9.5: say the templates are written for 9.5
  before applying one.
- [ ] `ai`: read `features.llm`, `features.embedding`, `features.enterprise_plus` before the first
  call. `materialize`: `features.data_movement` before a remote table, summary or data movement,
  `features.summary_rewrite` before a summary.
- [ ] `datasources`: a file only on the human's computer (scope-user-4), in place.
- [ ] `verification/chain.toml`: a step for the recipe's block (or `[not_run]` with the reason); the
  remote-table and summary steps `require` `data_movement`.
- [ ] Unit tests and the lint pass.

### Task 4: routing cases

**Files:** `evals/routing-vql-publish/`, `evals/routing-views-brownfield/`.

- [ ] `routing-vql-publish`: "publish this view as a REST API for our app" → `vql` fires (nothing is
  created). `routing-views-brownfield`: a column added to a view built in Design Studio with no file →
  `views` fires.
- [ ] Run both, three runs each (`claude plugin eval . --ablation none --case …`); and on `main`'s
  descriptions, to know whether they guard a change or only the present.

### Task 5: the experience loop and the files around the plugin

**Files:** `README.md`, `CONTRIBUTING.md`, `evals/README.md`, `tests/skills_lint.py`,
`tests/test_skills_lint.py`, `.github/ISSUE_TEMPLATE/{session-report.yml,verify-failure.yml,config.yml}`,
`.gitignore`, `spikes/` (removed), `docs/superpowers/specs/2026-09-08-spike-t2-ddl-over-9996.md`,
`docs/superpowers/specs/2026-09-08-spike-t11-marketplace-api.md`.

- [ ] Issue templates: the request in words, what the agent did, what was expected, the plugin
  commit (`claude plugin list`, or the cache directory name), `vdp.server_version` and `features`
  from `env check`, the `.vql`, the `vql plan` JSON and the error envelope; how to strip names;
  never a profile, a password or a ciphertext. `verify` failure: the report's failed steps, the
  skipped ones with reasons, `features`.
- [ ] CONTRIBUTING: the invitation (sessions, failing templates, decoded errors); *What we accept*;
  *From a session to a change* (the map from a kind of failure to the artifact, and the method:
  redact, reproduce on a synthetic fixture, RED, the narrowest change, GREEN, keep a regression);
  five checks with the outcome runner; the tree line for `evals/`; the server-wide rules for a shared
  server; the language section (no `spikes/`).
- [ ] README: *When the agent got it wrong*; out-of-scope list (dbt, listeners, Java extensions,
  marketplace governance, client code; "incremental cache loads"); the skills table rows of
  `marketplace`, `security`, `scheduler`; the platforms under Requirements; the Contributing
  paragraph.
- [ ] `evals/README.md` in English without task ids and "v1"; the eight unlisted cases described; the
  installed-plugin check rewritten; the new cases. `_docs()` lints it.
- [ ] `.gitignore` comments in English; `spikes/` removed and the reports pointed at its last commit.

### Task 6: GREEN, review, close

- [ ] Drop RED databases; rebuild fixtures; grep the new texts for fixture names (T28/T34/T43 lessons).
- [ ] GREEN: Opus ×2 and Sonnet ×1 per scenario, with the branch's skills and `scripts/` (main
  checkout detached at the branch head); reports as reviews of the text.
- [ ] Fix what the reviews found; Sonnet re-run where the text changed.
- [ ] `verify --env lab` (core chain) — the new step green; unit tests; `claude plugin validate .`.
- [ ] Whole-branch code review by a subagent (planner, texts against `vql`'s table, docs); fixes.
- [ ] TASKS: T46 under *Сделано*, scope-user-9 entries closed, open questions; design spec §6.2/§6.3;
  CLAUDE.md's line on the lint; remove every `zq46`/fixture database; PR.
