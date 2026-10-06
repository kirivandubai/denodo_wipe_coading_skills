# T44 — what an agent would get wrong on another server: implementation plan

**Spec:** `docs/TASKS.md`, item T44, and the findings it names in
`docs/superpowers/specs/2026-10-06-final-review-findings.md` (the verdict is
`docs/superpowers/specs/2026-10-06-final-review.md`). Architecture: the design spec
`docs/superpowers/specs/2026-09-04-denodo-skills-design.md`.

**Goal:** fix every finding of points 1 and 4 of the final review (high, medium and low, file by
file), the version pin, the `safety.py` gap and the `verify` guards — 207 findings — so that an
agent on a server other than the one the skills were tuned on is not told the wrong thing.

**What T44 covers.** Every finding of *Point 1* and *Point 4* of the appendix, except `repo-7`,
`repo-5`, `repo-17` and `repo-18` (T46: evals README, CONTRIBUTING, README's supported systems);
plus `scope-maintainer-8` (point 5), `datasources-A13` (point 3, the `USED_BY` pair of
datasources-B1) and the side observations `side-1`, `side-3`, `side-4`, `side-6`, `side-7`,
`side-11`, `side-12`, `side-13`. The other side observations and every other point-3 finding are
T45; the rest of point 5 is T46.

**Execution.** One task per skill and one for everything outside `skills/`. The tasks touch
disjoint files except `verification/chain.toml` and `tests/skills_lint.py`, which several may
touch in different places, so implementers run in parallel waves, each in its own git worktree,
and the controller merges. The live chain run that re-marks the changed templates is the
controller's (Task 18), because it writes to the shared test server.

## Global constraints

These bind every task.

1. **Where the findings are.** Each task's full finding rows (problem and the verifier's fix) are in
   `<workspace>/findings/<group>.md` — the brief names the file. Line numbers there are as of commit
   `2fa6fbd`; `skills/` has not changed since. Apply the verifier's fix; where it offers options,
   take the one that fits the file, and say which in the report. A finding whose claim turns out
   wrong on reading the file or the documentation is not applied — the report says why.
2. **Documentation.** Every point-4 change agrees with the Denodo 9.5 documentation. The guides are
   downloaded as text: `/private/tmp/claude-501/-Users-ishtadeva-github-denodo-skills/f74e1c06-808a-4669-8012-a07b155c9f1e/scratchpad/docs/text/*.txt`
   (`../INDEX.tsv` maps each file to its title; the Testing Tool manual is
   `connects_testing_tool_user_manual.txt`). `grep` them; cite the page file in the report for each
   point-4 change.
3. **Skills stay generic and English** (`CLAUDE.md`, *Invariants*): no Cyrillic, no name of the
   test installation, no task ids, no "v1", no ports of the test server, no profile name `lab` in
   `skills/` (examples use `dev`). Engine behaviour is labelled with its engine ("on SQL Server");
   a measurement says where it was measured. British spelling, the files' own terse style. The lint
   (`tests/skills_lint.py`, part of the unit tests) enforces most of this.
4. **Marks and the chain.** Every block marked `-- verified: …` / `-- unverified: …` keeps its mark
   line; never edit a mark's date or status by hand — the controller's chain run rewrites it
   (`verify --update-marks`). A changed marked block must still be found and pass its step in
   `verification/chain.toml`: steps address a block as `file#heading[n]` and some carry
   `substitute = { "<literal>" = … }` strings that must still occur in the block. Renaming a
   heading or reordering marked blocks means updating every address that names them. A new marked
   block needs a step or a `[not_run]` line (a unit test holds both directions). Prefer prose
   fixes; change a template only where a finding requires it.
5. **No routing changes.** Do not edit the `description` front matter of any `SKILL.md` (a change
   there needs the routing eval suite). If a finding seems to need it, report it instead.
6. **No growth.** T45 cuts duplication next; do not add new sections, and keep a fix to the size of
   what it replaces where possible. Do not do T45's restructuring (moving text between skills,
   cutting duplicates) unless the T44 finding itself asks for it. `SKILL.md` length limits are in
   the lint (`LONG_SKILLS`); do not add a skill to that list.
7. **Live probes are optional and bounded.** A finding marked "measure" or a claim you cannot settle
   from the documentation may be probed on the test server with `scripts/denodo vql run --env lab …`
   from the worktree root: read-only statements anywhere (`SELECT`, `DESC`, `GET_ELEMENTS()`,
   `GET_VIEWS()`); objects only in a database of your own named `zq44_<skill>`, created and dropped
   within the task (`DROP DATABASE zq44_<skill> CASCADE`). Never: server-wide objects (users, roles,
   tags, policies), any `…_AI` / `EMBED_AI` / `VECTOR_DISTANCE` call, writes to source databases,
   any Data Marketplace or Scheduler call that is not a `GET`, reading `~/.denodo/profiles.toml`.
   Report every probe and its result.
8. **Tests.** `PYTHONPATH=scripts python3 -m unittest discover -s tests -t .` from the worktree root
   must pass before committing (it includes the lint and the chain-manifest test). Code changes
   come with unit tests (TDD).
9. **Commits.** In English, conventional prefix (`fix(<skill>): …`), each ending with
   `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Commit on the worktree's
   branch; do not push, merge or rebase.

## Measurements already made (controller, 2026-10-06, test server 9.5.1)

- **side-11:** `SELECT * FROM GET_VIEWS() WHERE input_database_name = '<missing>'` fails —
  `Received exception with message 'Database '<name>' …` — it does not answer with no rows.
- **side-6:** the `p_cursor` template of `procedures/references/vql-procedures.md` over a three-row
  view returns exactly three rows (1, 2, 3): the last row does not come back twice.

## Task 1: datasources

Findings: `<workspace>/findings/datasources.md` (25: datasources-B2 and -B1 high, with
datasources-A13 the `USED_BY` pair). Files: `skills/datasources/**`, the chain steps that read its
blocks. `date` → `localdate` and `TO_DATE` → `TO_LOCALDATE` throughout `datasources` (the chain
checks of `df-source` and `base-view-minimum` count `created_dt`; they must still hold). The
dependants check in `references/base-view.md` uses `USED_BY` with the columns of its documented
output schema. The `execute/references/errors.md:70` half of datasources-B6/execute-B1 belongs to
Task 6.

## Task 2: dml

Findings: `<workspace>/findings/dml.md` (17: dml-A1 high, the time zone of writes, with dml-A2,
dml-B2, dml-B3, sweep-1; side-3, side-4). Files: `skills/dml/**` and the chain steps of its blocks.
The zone text must agree with how `skills/vql/references/dialect.md` describes the server's zone;
read it, do not edit it — if it is itself wrong, report it as a concern for Task 15.

## Task 3: marketplace

Findings: `<workspace>/findings/marketplace.md` (13: marketplace-B1 high — the "built-in" types —
with -A1, -A8, -B2, -B3, -B4, -A9, sweep-2). Files: `skills/marketplace/**`. The element id `7446`
leaves the template's response comment for a placeholder.

## Task 4: procedures and `safety.py`

Findings: `<workspace>/findings/procedures.md` (16: procedures-B1 high — parameter names; -B2 and
-B3 — `GET_STATS_FOR_FIELDS`, `CHECK_METADATA`, `CHECK_CACHE_NAMES`, `MIGRATE_DATE_TYPES` change
state; side-6). Files: `skills/procedures/**`, `scripts/denodo_cli/safety.py`,
`tests/test_safety.py` (or the existing test that compares the skill's list of state-changing
procedures with `safety.py` — find it; if none exists, add one), and the chain step
`procedure-cursor` (its check may now count the rows: three, per the measurement above). The
classifier change is TDD: a failing test that `GET_STATS_FOR_FIELDS` (with `input_save = true` if
the classifier reads arguments; otherwise the procedure name) and the other three are flagged
destructive, then the change.

## Task 5: materialize

Findings: `<workspace>/findings/materialize.md` (11: materialize-B1 high — summaries are off only in
Professional and Standard). Files: `skills/materialize/**`.

## Task 6: execute

Findings: `<workspace>/findings/execute.md` (8, including execute-B1 — the `date`/`TO_DATE` row of
`references/errors.md:70` — and execute-A1, the wrong-password message). Files: `skills/execute/**`.

## Task 7: security

Findings: `<workspace>/findings/security.md` (11: licences, an administrator profile, people who
are not VDP users, `ALLOWED_PATHS`, `VIEW_DATABASES`, `impersonate_roles` and `allusers`,
`CATALOG_PERMISSIONS`). Files: `skills/security/**`.

## Task 8: cache

Findings: `<workspace>/findings/cache.md` (12: `CONTEXT ('cache' = 'off')` and who it binds,
`CLEAN_CACHE_DATABASE` for global administrators, `USED_BY` as seen by the caller, SQL Server
results stated as general, maintenance assumed on). Files: `skills/cache/**`.

## Task 9: catalog

Findings: `<workspace>/findings/catalog.md` (12: licence of tags, `folder` in lower case before
`DROP FOLDER … CASCADE`, `CREATE OR REPLACE DATABASE` and authentication). Files:
`skills/catalog/**`.

## Task 10: views

Findings: `<workspace>/findings/views.md` (13: the `CREATE ASSOCIATION` page exists — views-B1;
data movement and MPP — views-B3, -B4; the referential constraint — views-B2;
`GET_CATALOG_METADATA_WS` — views-B5). Files: `skills/views/**`. The association grammar's `(+)`
multiplicity may be added to the grammar block (a `[not_run]` grammar, not a statement).

## Task 11: semantics

Findings: `<workspace>/findings/semantics.md` (12: licence of tags, what AI consumers send, the MCP
tag and privileges, side-7 — settle the MCP Server's user against the MCP Server manual if it is in
the dump, else say "documentation does not say" in one wording in both places). Files:
`skills/semantics/**`.

## Task 12: ai

Findings: `<workspace>/findings/ai.md` (10: the LLM provider's properties stated as Denodo's;
side-1). Files: `skills/ai/**`. Prose only: no marked block of `ai` changes unless a finding
requires it (its chain tail costs paid requests).

## Task 13: scheduler

Findings: `<workspace>/findings/scheduler.md` (10, low). Files: `skills/scheduler/**`.

## Task 14: metrics

Findings: `<workspace>/findings/metrics.md` (6, low). Files: `skills/metrics/**`.

## Task 15: vql

Findings: `<workspace>/findings/vql.md` (11: the `CATALOG_*` procedures that are deprecated —
four, not all; window functions; a directory read by one source; sweep-5 the collation; side-12
`NULL` order on `DESC`). Files: `skills/vql/**`.

## Task 16: testing

Findings: `<workspace>/findings/testing.md` (6, low; side-11 — use the measurement above).
Files: `skills/testing/**`. Prose only unless a finding requires a template change (its chain tail
needs the Testing Tool).

## Task 17: outside `skills/`

Findings: `<workspace>/findings/outside.md` (14). Files: `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json`, `README.md`, `CONTRIBUTING.md`, `scripts/denodo_cli/cli.py`,
`scripts/denodo_cli/commands/verify.py`, `verification/chain.toml`, `verification/data/README.md`,
`verification/data/generate.py` (its docstring only), tests.

- **Version (repo-3, scope-maintainer-8 — decided by the owner):** remove `"version"` from
  `plugin.json` and `metadata.version` from `marketplace.json`. README, Install section: one note
  that an install made before this change reinstalls once (the facts are in the brief's addendum,
  from the Claude Code documentation), and the launcher commands use a path that cannot pick an
  orphaned older copy (repo-13).
  *Facts from the Claude Code plugin documentation (code.claude.com/docs/en/plugins/loading,
  …/install, …/cli-reference; checked 2026-10-06):* with `version` absent from the manifest and
  the marketplace entry, a relative-path plugin in a Git-hosted marketplace is versioned by "the
  commit SHA of the installed directory"; "that version is how it detects an update" — so an
  install recorded as `0.1.0` should be replaced by the next update (inference, not stated). The
  user runs `claude plugin marketplace update denodo-skills` then `claude plugin update
  denodo@denodo-skills` (auto-update is off by default for third-party marketplaces); a running
  session keeps the old copy until `/reload-plugins` or a restart. If the update reports the
  plugin current, uninstall and install once. The cache path is
  `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`; after an update the previous
  directory gets an `.orphaned_at` marker and is removed 14 days later, so a `*` in the path can
  match two copies. `claude plugin list --json` prints each plugin's `installPath`;
  `${CLAUDE_PLUGIN_ROOT}` is not set in a shell. `metadata.version` of `marketplace.json` is not a
  field Claude Code reads. `claude plugin validate` warns on a missing `version` (CI runs it without
  `--strict` — check it still passes).
- **repo-1 (high, code, TDD):** `verify --with-marketplace` reads both
  `/public/api/element-management/{DATABASES,VIEWS}/changes` before the marketplace tail, dropping
  the entries of the run's own database, as `evals/outcome/run.py` `catalog_pending` does; if
  anything is left it skips every `marketplace = true` step and says why. Before the synchronize
  pair at the end of `[cleanup] http` it reads again; if foreign entries appeared, it skips the pair
  and reports that the run's own entries were left as orphans. Reuse, do not copy, the pending
  logic if it can be shared cleanly (`evals/outcome/run.py` imports from `scripts/`?) — otherwise a
  small function in `verify.py` with its own tests. README's "removes everything it made" says the
  guard.
- **repo-4:** move `jdbc-generate-schema` after `cache-load`, `needs = ["cache-load"]`, comment
  reworded.
- **The rest:** repo-10 (CLI help texts), repo-11, repo-12, repo-14, repo-20, side-13 (one figure
  for the AI tail, taken from the chain: count the AI calls the `--with-ai` steps make if the chain's
  figure is in doubt), repo-15, repo-16, repo-19.

## Task 18 (controller): the live chain

Merge every task, run the unit tests, then `scripts/denodo verify --env lab --update-marks` with
the tails whose templates changed (`--with-writes` for `dml`/`materialize`, `--with-marketplace`
for `marketplace` — after dropping probe databases, `--with-scheduler`, `--testing-tool`,
`--with-ai` only if an `ai` block changed). Every changed template is a green step. Clean the server.

## Task 19 (controller): bookkeeping

TASKS.md: T44 to *Сделано* with what was done and measured; the open questions it closes (the `DF
template declares created_dt:date` item) marked; what is left for T45. PR with the session's
account.
