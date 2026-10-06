# Portable verification chain (T40) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scripts/denodo verify` runs on any Denodo 9.5 server: installation values come from the server or a local file, fixtures read synthetic files the server can reach, tails the server lacks are skipped with a reason, and every `verified`-marked block of `skills/` runs or is listed as not run.

**Architecture:** A new module `denodo_cli/features.py` reads the server's features and installation values with read-only calls (`VALIDATE_MPP_LICENSE`, `GET_CACHE_CONFIGURATION`, an allowlist of `GET_PARAMETER` properties, the Scheduler's `dataSources`). `verify.py` resolves `[values]` markers (`@server`, `@dialect`) and a per-profile values file, gates steps by `requires`, skips steps naming unresolved values, and reports `values_from`, `features` and `not_run`. `env check` reports `features`. The manifest gains `[dialects.*]`, `[not_run]`, `requires`, synthetic fixture routes and the reference steps.

**Tech Stack:** Python 3.11+ standard library (`tomllib`), unittest, Denodo 9.5.1 live server for acceptance.

**Spec:** `docs/superpowers/specs/2026-10-06-portable-verify-design.md`

## Global Constraints

- `scripts/denodo` (launcher) stays standard-library only; `denodo_cli` keeps no new dependency.
- Everything written to the repository is English; no Cyrillic, no stand names (`tests/skills_lint.py`).
- `GET_PARAMETER` is called only with the properties of `features.PARAMETERS` — never a secret.
- On the stand, state changes only in own databases (`denodo_skills_test`, `zq40_*`), `verify_`/`zq40_` server-wide objects, the PG schema `zq40_cache`; the server cache switch only as the owner allowed (2026-10-06), reverted at the end.
- AI: at most 200 paid requests in the whole task (each `--with-ai` run ≈ 50).
- Unit tests: `PYTHONPATH=scripts python3 -m unittest discover -s tests -t .` must pass after every task.

## Review Focus

- A values file with a typo in a key → usage error naming the file, the profile table and the known keys (Task 1).
- A non-administrator profile → `GET_PARAMETER` denied → features `null`, values unresolved, steps that need them skipped with the line to add, never a crash (Tasks 2, 3).
- A `NULL` `target_catalog` in `GET_CACHE_CONFIGURATION` → `write_catalog` unresolved, write steps skipped with a reason, `[cleanup] writes` skipped too — never `CATALOG = 'None'` sent (Task 3).
- A manifest whose `requires` names an unknown feature → `ChainError` at load (Task 3).
- A marked block added to a skill without a step or `[not_run]` line → unit test failure naming the block (Task 5).

---

### Task 1: The values file

**Files:**
- Modify: `scripts/denodo_cli/commands/verify.py` (new `load_values_file`, `Chain.dialects`, `Chain.not_run`)
- Modify: `scripts/denodo_cli/cli.py` (`--values`)
- Test: `tests/test_commands_verify.py` (`ValuesFileTest`)

**Interfaces:**
- Produces: `load_values_file(path: Path, profile_name: str, known: set[str]) -> dict[str, str]` — `{}` when the file or the table is missing; raises `ChainError` for an unreadable file, a non-table entry, or a key not in `known`.
- Produces: `default_values_path() -> Path` = `profiles_path().parent / "verify.toml"`.
- Produces: `Chain.dialects: dict[str, dict[str, str]]`, `Chain.not_run: dict[str, str]`.
- Produces: `run_chain(..., values_file: Path | None = None, file_values: dict[str, str] | None = None)`.

- [ ] Write tests: missing file → `{}`; table for another profile only → `{}`; unknown key → `ChainError` mentioning `verify.toml`, `[lab]` and a known key; non-string value (an int) is stringified; `load_chain` reads `[dialects.x]` and `[not_run]` (non-string reason → `ChainError`).
- [ ] Run, see them fail.
- [ ] Implement; `cli.py` resolves `--values` or the default path, passes `file_values` and `values_file` to `run_chain`; known keys = manifest `[values]` ∪ every dialect key.
- [ ] Run the unit tests, pass. Commit.

### Task 2: The features probe and `env check`

**Files:**
- Create: `scripts/denodo_cli/features.py`
- Modify: `scripts/denodo_cli/commands/env.py` (`features` in the envelope)
- Test: `tests/test_features.py`, `tests/test_commands_env.py`

**Interfaces:**
- Produces: `PARAMETERS: dict[str, str]` — short name → property (`llm_enabled`, `llm_provider`, `llm_model`, `embedding_provider`, `embedding_model`, `embedding_disabled`, `summary_rewrite`, `data_movement`).
- Produces: `read_features(transport) -> dict` with keys `enterprise_plus` (bool|None), `mpp` (dict|None), `cache` (dict|None: `on`, `data_source_database`, `data_source`, `adapter`, `adapter_version`, `catalog`, `schema`), `llm` (dict|None: `on`, `provider`, `model`), `embedding` (dict|None: `on`, `provider`, `model`), `summary_rewrite` (bool|None), `data_movement` (bool|None). Every call is wrapped: a failure gives `None` for that feature, never an exception.
- Produces: `server_values(features: dict) -> dict[str, str]` — `embedding_model`, `write_datasource_database`, `write_datasource_name`, `write_catalog`, `write_schema`, `write_dialect`; only keys the server answered (a `NULL` is left out).
- Produces: `scheduler_data_source(rest, user: str) -> tuple[str | None, list[dict]]` — the id of the single VDP data source whose `login == user`, and the candidates (`id`, `projectName`, `login`, `connectionURI`).
- Produces: `FEATURE_NAMES = ("enterprise_plus", "llm", "embedding", "cache", "summary_rewrite", "data_movement", "impersonation")`, `feature_state(features, name) -> bool | None`, `FEATURE_REASONS: dict[str, str]`.

- [ ] Tests with a scripted transport: Enterprise Plus row (`max_processors = 2147483647`, status `-5`) → `enterprise_plus True`, `mpp.status -5`; `-1` → `False`; cache row as on 9.5.1 (`sqlserver`, `enterprise_data`, `dbo`, `ON`); `GET_PARAMETER` raising (non-admin) → `llm None`, `embedding None`; `'true'`/`'false'`/`None` property values → booleans/None; only `PARAMETERS` properties are ever sent; `server_values` drops `None`s; `scheduler_data_source` with one/zero/two matching sources.
- [ ] `env check` test: `features` present, with `impersonation`/`admin` copied from `vdp`; VDP down → `features: null`.
- [ ] Implement, run, pass. Commit.

### Task 3: Markers, `requires` and unresolved values in `run_chain`

**Files:**
- Modify: `scripts/denodo_cli/commands/verify.py`
- Test: `tests/test_commands_verify.py` (`ServerValuesTest`, `RequiresTest`)

**Interfaces:**
- Consumes: `features.read_features`, `features.server_values`, `features.scheduler_data_source`, `features.feature_state`, `features.FEATURE_NAMES`, `features.FEATURE_REASONS`.
- Produces: `Step.requires: list[str]`; `SERVER = "@server"`, `DIALECT = "@dialect"`; `resolve_values(chain, *, database, file_values, server, scheduler) -> tuple[dict, dict, dict]` (values, values_from, unresolved-reasons); report keys `values_from`, `values_file`, `features`, `summary.not_run`.

- [ ] Tests: no marker and no `requires` → no probe call at all (the synthetic manifests of the existing tests keep their transports' statement lists); `@server` filled from a scripted probe; file beats server; `@dialect` from `[dialects.<write_dialect>]`; unknown dialect → unresolved with a reason naming the two values; a step naming an unresolved value is skipped with that reason and does not stop the chain; a `[cleanup] writes` statement naming one is skipped and reported, not sent; `requires` with a feature known false → skipped with `FEATURE_REASONS` text; unknown (`None`) → runs; unknown name in `requires` → `ChainError`; `values_from` and `features` in the report.
- [ ] Implement: probe once after the production refusal and before `_encrypt_throwaways` when any value is a marker or any step has `requires`; Scheduler candidates only with `--with-scheduler`; `_check_cleanup_placeholders` accepts unresolved-but-declared values; `_step_values(step)` collects `{name}`s of body, substitutions, check, files substitutions (the body after rendering the block); skip before running.
- [ ] Run, pass. Commit.

### Task 4: Synthetic fixture data

**Files:**
- Create: `verification/data/generate.py`, `verification/data/{income_band,household_demographics,reason,store_returns,web_returns}.csv`, `verification/data/README.md`
- Test: `tests/test_fixture_data.py`

- [ ] Tests: the committed files equal what `generate.py` writes (regeneration is a no-op); 20 bands, band `k` = (`0` or `(k-1)*10000+1`, `k*10000`); 7,200 households, every (band, buy potential, dependants, vehicles) once; header quoted and upper case as in the wrappers; returns have `NULL` (empty) reason and date keys; only TPC-DS column names.
- [ ] Implement the generator (fixed seed, `random.Random(40)`), write the files, run, pass.
- [ ] Live probe on `zq40_probe`: the generated `household_demographics.csv` equals the demo image's file row for row (`docker exec … md5sum`-free: compare `COUNT`, `SUM` per column through a DF over HTTP from the branch). Commit.

### Task 5: The manifest — values, dialects, requires, coverage

**Files:**
- Modify: `verification/chain.toml`
- Modify: `tests/test_chain_manifest.py` (coverage both ways; `requires` names; dialect keys)

- [ ] `[values]`: `fixture_route`, `fixture_base` (HTTP to the repository's `main`), `embedding_model`/`write_*`/`write_dialect`/`scheduler_data_source_id` = `"@server"`, `write_identity`/`write_timestamp` = `"@dialect"`; `[dialects.sqlserver]`, `[dialects.postgresql]`; fixtures use `ROUTE {fixture_route} '{fixture_base}/<file>'`; the writes fixture uses `{write_identity}`/`{write_timestamp}`.
- [ ] `requires` on the existing steps: tags/semantics tag steps/security policy steps `enterprise_plus`; impersonation checks `impersonation`; cache and Scheduler cache steps `cache`; AI steps `enterprise_plus` + `llm`/`embedding` (+ `cache` for the load); summary steps `summary_rewrite`; data movement `data_movement`.
- [ ] Coverage test: marked blocks (lint's rule) vs step addresses ∪ `files` addresses ∪ `[not_run]` keys, both directions; `[not_run]` lists the six `SKILL.md` blocks and, for now, every reference block (Task 7 moves them out).
- [ ] Header comment and section comments rewritten (no demo paths). Unit tests pass. Commit.

### Task 6: Configuration 1 live — the demo image, HTTP fixtures

- [ ] `~/.denodo/verify.toml` `[lab]`: `fixture_base` = the branch's raw URL (until merge).
- [ ] `scripts/denodo env check --env lab` — features as expected.
- [ ] `scripts/denodo verify --env lab` (default), then with `--with-marketplace --with-writes --with-scheduler --testing-tool <dir>`, then `--with-ai` once (≈40 requests). Fix what fails; record each finding.
- [ ] After cleanup: no `denodo_skills_test`, no `verify_` objects, both marketplace `changes` empty, Scheduler back to `default`. Investigate the leftover `denodo_skills_test` (three types, 2026-10-05) seen before the task.
- [ ] Commit the fixes.

### Task 7: The reference blocks join the chain

**Files:**
- Modify: `verification/chain.toml` (steps, `[not_run]` shrinks), `skills/**/references/*.md` only where a block is wrong

- [ ] Per skill, in chain order: catalog, datasources, views, procedures, security, ai, marketplace, materialize, cache, semantics, dml. For each marked block: a step (substitutions completing a fragment, a `check` stating the block's claim) or a `[not_run]` reason (grammar, fragment, needs a source that answers, a JAR, a shared object).
- [ ] Run the new steps live in groups (default run; `--with-ai` once for the AI blocks ≈10 requests); fix blocks that fail in the skill text.
- [ ] Unit tests pass (coverage test now holds the real split). Commit per group.

### Task 8: Configuration 2 live — PostgreSQL cache, local fixtures

- [ ] `docker exec postgres-pgvector-demo-951 psql -U postgres -d enterprise_data -c "CREATE SCHEMA zq40_cache AUTHORIZATION enterprise_data"`.
- [ ] Database `zq40_cache` with `ds_pg_cache` (PG URI, login `enterprise_data`, ciphertext of `verticals.postgres_retail` copied by a script that never prints it, `DATA_LOAD_CONFIGURATION ( TARGET_CATALOG / TARGET_SCHEMA = 'zq40_cache' )`).
- [ ] `SET 'com.denodo.vdb.cache.jdbc.serverCacheDataSource' = '"zq40_cache"."ds_pg_cache"'`; `docker restart denodo-platform-demo-951`; `env check` shows `adapter: postgresql`.
- [ ] `docker cp verification/data` into the container; values file `[labpg]` (copy of `[lab]` profile name) with `fixture_route = "LOCAL 'LocalConnection'"`.
- [ ] Full run with every tail. Fix templates that assume SQL Server in the skills; rerun until green.
- [ ] Revert: SET back to `"admin"."vdpcachedatasource"`, restart, `DROP SCHEMA zq40_cache CASCADE`, drop `zq40_cache`, remove the copied folder; `env check` shows `sqlserver`.

### Task 9: Documents, marks, the final runs, the PR

- [ ] Design spec 11.1 (values, features, fixtures, coverage), the T40 design status line; `README.md` "Verify the templates on your server"; `CONTRIBUTING.md` (a marked block needs a step or a `[not_run]` line); `skills/execute` if it describes `verify`; `CLAUDE.md` verification paragraph; `docs/TASKS.md` T40 under «Сделано».
- [ ] Final configuration-1 run with every tail and `--update-marks`; unit tests; `claude plugin validate .`; lint clean.
- [ ] Push, PR with the session's decisions, live results, what is left.
