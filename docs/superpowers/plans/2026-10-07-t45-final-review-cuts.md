# T45 — the drifted duplicates, then the cuts: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task.

**Goal:** apply every point-3 finding of the final review (the economy of context), the ten
duplicates that drifted apart first, plus the side observations and the items T44 left for this
task — so that a skill states each fact once, where the agent that needs it reads it.

**Architecture:** one task per skill, each in its own git worktree, editing only its own skill's
files and the shared lines its brief names; the controller merges, runs the live chain, the routing
suite and two outcome scenarios.

**Spec:** `docs/TASKS.md`, item T45, and the findings it names in
`docs/superpowers/specs/2026-10-06-final-review-findings.md` (verdict:
`docs/superpowers/specs/2026-10-06-final-review.md`, *Point 3*). Architecture: the design spec
`docs/superpowers/specs/2026-09-04-denodo-skills-design.md`.

**What T45 covers.** Every finding of *Point 3* except `datasources-A13` (done in T44) — 160 —
plus `scope-maintainer-10`, `side-2`, `side-5`, `side-8`, `side-9`, `side-10`: 166 findings. And
what T44 left (`docs/TASKS.md`, T44, *Left for T45*, and its deferred review minors): the
ciphertext's portability worded two ways (`execute`, `datasources`); `CONTEXT ('cache' = 'off')`
comparisons in `scheduler` and `dml` without the caveat `cache` carries; `view_name` of `USED_BY`
said two ways (`cache`, `views`); task ids in `verification/chain.toml` comments; "Every row is a
paid request" beside "billed when hosted" (`ai`); the long licence cell of `security` and the "full
syntax" heading of its `policies.md`; the `{ds:vdp}` clause of `testing` and its unfenced Windows
launcher line; "evaluates it itself" and the measured case stated generally in `metrics`;
`materialize`, `scheduler` and `security` at the 500-line limit.

**Done when** (TASKS): the characters of the sixteen `SKILL.md` files, before and after, are in the
report; chain addresses and lint lists follow every move; the outcome scenarios `marketplace-tag`
and `drop-under-pressure` pass again; the routing suite runs (three descriptions change:
`execute-A18`, `cross-14`, `semantics-A10`).

## Global Constraints

These bind every task. The workspace is
`/Users/ishtadeva/github/denodo_skills/.superpowers/sdd/2026-10-07-t45-final-review-cuts/`.

1. **Where the findings are.** `<workspace>/findings/<skill>.md` — the appendix row and the full
   review record of each finding. Line numbers are as of commit `2fa6fbd`; **T44 has changed
   `skills/` since — find each place by its quote.** Apply the verifier's fix; where it offers
   options, take the one that fits the file and say which. A finding whose claim is wrong on reading
   the file is not applied — the report says why. **A ruling in this plan or in the brief overrides
   the finding it names.**
2. **What stays** (the review's own verdict, *Point 3*, "Kept on purpose"): the descriptions (except
   the three a brief names), the templates, the *Silent failures* and *Common mistakes* tables, the
   domain copies of the safety rules — each domain's confirmation table, "the request is not the
   yes", "when you cannot ask", the AI cost reminder, the production red flag — the summary of
   `dialect.md` in `vql`'s body, and *Many objects at once* in `vql`. A finding that would cut the
   last copy of a safety rule inside a skill in favour of `vql` or `execute` is applied only as far
   as it removes a second copy inside the same skill. When an error text is quoted in prose and again
   in *Common mistakes*, the table keeps it — it is the copy the agent matches a server error against.
3. **A cut leaves the fact somewhere the agent reads.** Before cutting a statement because another
   skill "owns" it, read that skill's current text (`git show origin/main:skills/<other>/…`, or the
   file in your worktree) and confirm it says the same thing. If it does not, keep yours and report
   it. A pointer to another skill names the skill and a heading that exists there
   (`/denodo:datasources`, **Passwords**); a pointer to a reference file of another skill is written
   only where the brief says the file exists.
4. **Edit only your skill's files**, plus the shared lines your brief names (`tests/skills_lint.py`
   entries of your skill, `verification/chain.toml` steps of your blocks). Something wrong in another
   skill's files: report it, do not edit it.
5. **No growth.** T45 is a cut: no new sections beyond a move the brief names; a fix that replaces
   text is no longer than it, a pointer excepted. Report the characters (`wc -m`) and lines of
   `SKILL.md` and of each reference you touched, before and after. A skill in `LONG_SKILLS`
   (`tests/skills_lint.py`) lowers its number to its new length, or leaves the list at 500 lines or
   fewer; a skill at 500 lines ends with headroom.
6. **Skills stay generic and English** (`CLAUDE.md`, *Invariants*): no Cyrillic, no name of the
   test installation, no task ids, no "v1", no ports of the test server, no profile `lab` in
   `skills/` (examples use `dev`). British spelling, the files' own terse style. The lint enforces
   most of this.
7. **Marks and the chain.** Every block marked `-- verified: …` / `-- unverified: …` keeps its mark
   line, unedited — the controller's chain run rewrites marks. A moved marked block moves with its
   mark, and every `verification/chain.toml` step that addresses it (`file#heading[n]`) follows it;
   `substitute` literals must still occur in the block. A block that is deleted loses its step or
   its `[not_run]` line, and an `UNMARKED_BLOCKS` entry that matches no block any more is removed (the
   lint reports a stale one). Prefer prose cuts; change a template only where a finding requires it.
8. **Descriptions.** Do not edit the `description` front matter of any `SKILL.md`, except the one
   finding your brief names.
9. **Live probes are optional and bounded.** A claim the file and the documentation cannot settle
   may be probed with `scripts/denodo vql run --env lab …` from the worktree root: read-only
   statements anywhere; objects only in a database of your own named `zq45_<skill>`, created and
   dropped within the task. Never: server-wide objects, any `…_AI` / `EMBED_AI` / `VECTOR_DISTANCE`
   call, writes to source databases, a Data Marketplace or Scheduler call that is not a `GET`,
   reading `~/.denodo/profiles.toml`. The documentation is downloaded as text:
   `/private/tmp/claude-501/-Users-ishtadeva-github-denodo-skills/f74e1c06-808a-4669-8012-a07b155c9f1e/scratchpad/docs/text/*.txt`
   (`../INDEX.tsv` maps files to titles).
10. **Tests.** `PYTHONPATH=scripts python3 -m unittest discover -s tests -t .` from the worktree root
    passes before each commit (the lint and the chain-manifest test are in it).
11. **Commits.** English, `refactor(<skill>): …` for a cut or move, `fix(<skill>): …` for a drifted
    duplicate, each ending with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
    Commit on the worktree's branch; do not push, merge or rebase.

## Rulings made before execution

- **The marketplace's HTTP rules and the two `synchronize` exceptions live in full in
  `marketplace`; `vql` keeps a short paragraph.** `vql-A1`/`cross-1` cut them from `vql`;
  `marketplace-A3` would cut the same text from `marketplace` in favour of `vql`. Applying both
  loses the rule. The review's verdict puts the waste on the core side and keeps domain copies of
  safety rules, so `cross-1`'s adjusted version wins: `vql` keeps one paragraph (which calls are as
  destructive as a `DROP`, the complete-list clause of `tags/vdp/synchronize`, the two exceptions
  named in one line each with "nothing else about a `synchronize` is exempt", neither on production,
  the pointer to `/denodo:marketplace`, **Who sends it**); `marketplace` keeps **Who sends it** and
  its Step 4 paragraph in full, takes `vql`'s call/what-it-loses table in place of its closing prose
  (only what it lacks) and `vql`'s two marketplace rationalization rows beside **Who sends it**, and
  turns its own pointers to "the core's exceptions" into pointers to its own section.
  `marketplace-A3` is applied only to marketplace's internal repeats. Cost if wrong: an agent
  that loads `vql` without `marketplace` for an HTTP call reads the short rule only — but no HTTP
  call is made without `marketplace`, which holds every endpoint.
- **`execute`'s `verify` row becomes one short row, with no new reference file.** `cross-2` proposes
  `references/verify.md`; `execute-A4` and `scope-maintainer-10` a short row pointing to `verify
  --help`, which already describes every flag. The row keeps what the agent must know before running
  it: the run's own test database plus the server-wide `verify_` objects it creates and removes
  (security checks need `vdp.impersonation`); each tail and what it touches outside the test
  database — the shared marketplace catalog (and its pending-changes guard), a table in a source
  database, the shared Scheduler, paid LLM requests (the count the chain gives); a production
  profile needs `--allow-destructive`; everything else `verify --help`. No new rule ("each needs
  the human's yes") is invented. A fact the row drops that `verify --help` lacks is added to the
  help text in `scripts/denodo_cli/cli.py`. Cost if wrong: an agent asked for an unusual flag reads
  `--help` first — one call.
- **The data-source password procedure is `datasources`'s.** `execute`'s section goes; its command
  row ends with "the procedure is `/denodo:datasources`, **Passwords**"; the ciphertext's
  portability is said once, in `datasources`, in T44's wording (tied to the installation's
  encryption key).
- **Marketplace renames move to `skills/marketplace/references/renames.md`; `SKILL.md` keeps a short
  stub under the same heading, "A view in the marketplace is renamed, recreated or moved".** Other
  skills point to the heading, not to the file, so they do not depend on the move landing first.
- **`view_name` of `USED_BY`:** `views/references/dependencies.md` describes it ("the view at that
  depth"); `cache`'s "the view you asked about, not a reader" holds only at depth 1 — `cache` aligns
  with `views`, after checking the `USED_BY` documentation page.
- **Re-applying a file after an error** (`execute-A12`): both `execute` ("Error in the middle of a
  file") and `vql` ("One file per change, applied whole") say that statements before the failed one
  stay applied, a `CREATE OR REPLACE` of a view re-applies safely, and a write, a cache or AI load,
  or `OR REPLACE` over a table that holds rows runs again (`/denodo:dml`, `/denodo:materialize`).
- **Task ids in `verification/chain.toml` comments** go with the `execute` task (it owns the
  `verify` text).

## Execution

Implementers on the most capable model, each in its own worktree (`isolation: worktree`), in two
waves of eight; reviewers on a mid-tier model; one whole-branch review on the most capable model.
Worktrees are cut from `main`, not from the task branch — the plan reaches implementers as files in
the workspace. The controller cherry-picks each reviewed task onto `refactor/final-review-t45` and
resolves the shared lines (`LONG_SKILLS`, `UNMARKED_BLOCKS`, chain addresses) by hand.

## Task 1: vql

Findings: `<workspace>/findings/vql.md` (11: `vql-A1`, `cross-1` high; `cross-6`, `cross-5`,
`vql-A2`, `vql-A3`, `vql-A4` medium). Files: `skills/vql/**`; `tests/skills_lint.py` (the
`dialect.md` entry of `UNMARKED_BLOCKS`, `vql-A3`). Also the `vql` half of `execute-A12` (ruling
above: "One file per change, applied whole"). Rulings above: the marketplace paragraph (`vql` keeps
rationalization rows other than the two marketplace rows; row "Data Marketplace" of the core table
points to `/denodo:marketplace`); the short map keeps one row per skill, 3–6 words of scope (the
owner decided to keep a map — design spec §10), and the lines after it on VDP tags versus
marketplace tags. Report any statement in the design spec (§6.3, §10) that names text `vql` no
longer holds.

## Task 2: execute

Findings: `<workspace>/findings/execute.md` (21: `cross-2` high; `execute-A10`, `-A4`, `-A5`,
`cross-7`, `cross-3`, `execute-A12`, `scope-maintainer-10` medium; the rest low, `side-5`, and
`testing-A1`, which is about `execute`'s row). Files: `skills/execute/**`;
`tests/skills_lint.py` (the `secret encrypt` entry of `UNMARKED_BLOCKS`, gone with the section);
`scripts/denodo_cli/cli.py` (help text only, per the `verify` ruling); `verification/chain.toml`
(comments only: remove every task id — `grep -nE '\bT[0-9]{2}\b'`). Rulings above: the `verify`
row, the password section, `execute-A12`'s wording. The flagged-statement list moves to
`references/errors.md` under a heading **What the tool flags** (`cross-3`, `execute-A7`); the
marketplace span of it stays as the tool's own list (the `execute-A7` verifier). `execute-A15`:
"synchronise the catalog first (`/denodo:marketplace`, **Who sends it**)". `execute-A18` is the one
description edit allowed. *Not this skill* becomes one line (`execute-A13`).

## Task 3: marketplace

Findings: `<workspace>/findings/marketplace.md` (12: `marketplace-A3`, `-A2`, `-A4` medium).
Files: `skills/marketplace/**`; `verification/chain.toml` (the steps addressing the rename
section); `tests/skills_lint.py` (`LONG_SKILLS["marketplace"]`). Also the marketplace halves of
`cross-1` (read `skills/vql/SKILL.md` as it is on `main`: its HTTP table and rationalization rows
"one `radius.not_own` entry" and the rename-plus-matched-call row) and of `cross-11`
(row "Which tag", with `marketplace-A11`). Rulings above: the marketplace paragraph, the rename move
(stub keeps the heading and the safety facts `marketplace-A2` lists; the sentence other skills
link back to — "Renaming a view, or moving it to another database" in `views` — is not yours to
edit). `references/tags.md`'s "the core's table has two named exceptions" points to **Who sends
it**.

## Task 4: datasources

Findings: `<workspace>/findings/datasources.md` (13: `datasources-A9`, `-A10`, `-A11`, `-A8`,
`-A6`, `-A12` medium). Files: `skills/datasources/**`; `verification/chain.toml` (steps addressing
moved blocks — `datasources-A8` moves the hand-written JDBC wrapper to `references/jdbc.md`);
`tests/skills_lint.py` (`LONG_SKILLS["datasources"]`). Also: `references/jdbc.md`'s pointer to
`/denodo:execute`, "A password for a data source" points to **Passwords** in this skill (the
`execute-A5` ruling); the ciphertext's portability in one wording.

## Task 5: views

Findings: `<workspace>/findings/views.md` (13: `views-A5`, `cross-9`, `views-A8`, `views-A13`,
`views-A7`, `cross-8`, `views-A6` medium). Files: `skills/views/**`;
`tests/skills_lint.py` (`LONG_SKILLS["views"]`); chain steps of any block you change. The rename
paragraph (`views-A7` with `cross-8`'s added clause) and `references/derived.md`'s rename pointer
name `/denodo:marketplace`, "A view in the marketplace is renamed, recreated or moved" — the heading,
not a file. `views-A13`'s wording matches `catalog-A4`'s: "`vql plan` says whether it waits for the
human's yes". `references/dependencies.md` keeps the `USED_BY` `view_name` description; check it
against the `USED_BY` documentation page.

## Task 6: catalog

Findings: `<workspace>/findings/catalog.md` (14: `catalog-A2`, `-A1`, `-A5`, `-A4` medium;
`side-2`). Files: `skills/catalog/**`; chain steps of any block you change. `cross-11`: only the
catalog half (lines 12-13); the marketplace row is Task 3's.

## Task 7: dml

Findings: `<workspace>/findings/dml.md` (11: `dml-A6`, `dml-A5` medium). Files: `skills/dml/**`.
Also: every `CONTEXT ('cache' = 'off')` comparison in `dml` carries `cache`'s caveat (it binds only
on a view the user holds WRITE on, or with the `disable_cache_query` role; otherwise the server
reads the cache) in a clause or a pointer to `/denodo:cache`, **Verify**.

## Task 8: metrics

Findings: `<workspace>/findings/metrics.md` (11: `metrics-A8`, `-A7`, `-A12`, `-A11` medium).
Files: `skills/metrics/**`. Also T44's minors: "evaluates it itself" (say what evaluates what);
`references/periods.md`'s `Function sum is not executable` over files, stated generally — say the
server it was measured on moves no data for windows, or that the delegation decides.

## Task 9: procedures

Findings: `<workspace>/findings/procedures.md` (10: `procedures-A1`, `-A2` (with `procedures-B4`
already corrected in T44 — check), `-A4`, `-A5` medium). Files: `skills/procedures/**`.

## Task 10: materialize

Findings: `<workspace>/findings/materialize.md` (6: `materialize-A4` medium). Files:
`skills/materialize/**`. `SKILL.md` is at 500 lines: end with headroom.

## Task 11: security

Findings: `<workspace>/findings/security.md` (8: `security-A12` medium). Files:
`skills/security/**`. Also: the long licence cell (T44's `security-A3` wording) shortened; the
`references/policies.md` title's "full syntax" (it is not the full grammar — `GRANTED_BY` is
missing) reworded. `SKILL.md` is at 500 lines: end with headroom.

## Task 12: scheduler

Findings: `<workspace>/findings/scheduler.md` (6, low). Files: `skills/scheduler/**`. Also: every
`CONTEXT ('cache' = 'off')` comparison carries `cache`'s caveat as in Task 7. `SKILL.md` is at 500
lines: end with headroom.

## Task 13: semantics

Findings: `<workspace>/findings/semantics.md` (9: `semantics-A4` medium). Files:
`skills/semantics/**`. `semantics-A10` is the one description edit allowed.

## Task 14: testing

Findings: `<workspace>/findings/testing.md` (8: `testing-A4` medium; `side-8`, `side-9`,
`side-10`). Files: `skills/testing/**`; `tests/skills_lint.py` (`UNMARKED_BLOCKS` of testing, if a
fenced launcher line is added). `cross-14` is the one description edit allowed. Also: the `{ds:vdp}`
bullet's last clause ("and where one exists beside the tested one, it checks that one") said
plainly; the Windows launcher line fenced like the Unix one.

## Task 15: ai

Findings: `<workspace>/findings/ai.md` (7, low). Files: `skills/ai/**`. Prose only: no marked block
changes (its chain tail costs paid requests). Also: "Every row is a paid request" agrees with
"billed when the provider is hosted" — one wording.

## Task 16: cache

Findings: `<workspace>/findings/cache.md` (6, low). Files: `skills/cache/**`. Also: `view_name` of
`USED_BY` (ruling above).

## Task 17 (controller): merge and the live chain

Cherry-pick every reviewed task; resolve `LONG_SKILLS`, `UNMARKED_BLOCKS` and chain addresses; run
the unit tests; `scripts/denodo verify --env lab --update-marks` with the tails whose marked blocks
moved or changed (`--with-marketplace` for the rename move — after dropping probe databases;
others as the reports name). Every moved or changed template is a green step. Clean the server.

## Task 18 (controller): routing suite and outcome scenarios

`claude plugin eval . --ablation none` (three descriptions changed); `python3 evals/outcome/run.py
--env lab --scenario drop-under-pressure` and `--scenario marketplace-tag --with-marketplace`. A
failure is read as `evals/README.md` says and fixed before the PR.

## Task 19 (controller): whole-branch review and bookkeeping

Whole-branch review on the most capable model, given the cross-skill facts to check (every pointer
by heading resolves; no fact cut from one skill is missing from the skill pointed to; the rulings
above hold in every file). One fix wave. Then `docs/TASKS.md`: T45 to *Сделано* with the characters
before and after; the design spec if a report names a statement it holds; PR with the session's
account.
