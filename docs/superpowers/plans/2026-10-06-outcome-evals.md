# Outcome evals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Six repeatable agent scenarios against a test server, graded by a program on the trace, the session ledger and the server state (T42).

**Architecture:** A stdlib-only runner in `evals/outcome/` resets each scenario's fixture with `scripts/denodo verify` (a manifest per scenario), runs headless `claude -p` with the plugin and a narrow tool allow-list, then grades with deterministic checks (an LLM judge only for what a trace cannot show). `verify` gains `--cleanup-only`.

**Tech Stack:** Python 3.11+ standard library (`tomllib`, `subprocess`, `json`, `unittest`); Claude Code CLI (`claude -p --output-format stream-json`); the repository's `scripts/denodo`.

**Spec:** `docs/superpowers/specs/2026-10-06-outcome-evals-design.md`

## Global Constraints

- The runner and its modules use the standard library only; Python ≥ 3.11 (`tomllib`).
- Nothing under `evals/outcome/` is named `prompt.md`, `case.yaml` or `graders/` — `claude plugin eval` must not discover it.
- Every object a scenario creates or names starts with `eval_`.
- The runner refuses a profile marked `production` before the first reset.
- Credentials never appear in a command line: the runner passes only the profile name.
- Unit tests run with `PYTHONPATH=scripts python3 -m unittest discover -s tests -t .`, no server.
- Project text in English; no Cyrillic, no names of the test server in `skills/` (the lint).

## Review Focus

- A `scripts/denodo` result cut in the middle by the harness: checks needing a statement they could not read must fail with that reason, not pass — tested in Task 2.
- A compound Bash command running the tool twice (`a.vql && b.vql`): both JSON documents must be read — tested in Task 2.
- The agent reading a view before creating it: `checked_after` must look at reads *after the last change*, not the first read — tested in Task 3.
- A scenario whose fixture step `verify` skips (missing feature or value): the scenario is skipped with the reason, not failed — tested in Task 5.
- A scenario with a second turn: checks limited to `turn = 1` must not see the write of turn 2 — tested in Task 3.

---

### Task 1: `verify --cleanup-only`

**Files:**
- Modify: `scripts/denodo_cli/commands/verify.py` (`run_chain`)
- Modify: `scripts/denodo_cli/cli.py` (verify parser and dispatch)
- Test: `tests/test_commands_verify.py` (`CleanupTest`), `tests/test_cli.py`

**Interfaces:**
- Produces: `run_chain(..., cleanup_only: bool = False)`; CLI flag `verify --cleanup-only` (usage error together with `--keep`). With it no step runs, every step is reported skipped with reason `--cleanup-only`, cleanup runs under the same gates.

- [ ] Step 1: tests — `test_cleanup_only_runs_no_step_and_cleans_up` (FakeVql sees only the cleanup statements, `doc["cleanup"]["ran"]` true, every step `skipped`), `test_cleanup_only_with_keep_is_a_usage_error` (CLI), `test_cleanup_only_keeps_the_gates` (`writes` statements only with `with_writes=True`).
- [ ] Step 2: run, see them fail.
- [ ] Step 3: implement: in `run_chain`, when `cleanup_only`, skip the step loop (append `_skipped(step, "--cleanup-only", cause="cleanup-only")` for each) but keep values resolution; in the CLI add the flag and reject it with `--keep`.
- [ ] Step 4: run the whole unit suite.
- [ ] Step 5: commit.

### Task 2: the transcript parser — `evals/outcome/transcript.py`

**Files:**
- Create: `evals/outcome/transcript.py`
- Test: `tests/test_outcome_transcript.py` (imports with `sys.path.insert(0, <repo>/evals/outcome)`)

**Interfaces:**
- Produces:
  - `@dataclass Call: index:int, turn:int, tool:str, input:dict, result:str|None, is_error:bool, docs:list[dict]` — `docs` are the JSON documents the tool printed (`scripts/denodo` output).
  - `@dataclass Statement: call:int, turn:int, command:str ('vql run'|'vql plan'|…), text:str, ok:bool|None, destructive:str|None, affected:int|None, rows:list|None, source:str|None, readable:bool`.
  - `@dataclass Transcript: calls:list[Call], final_text:str, cost_usd:float|None, turns:int|None, session_id:str|None, cut:list[int]` (indexes of calls whose tool output could not be fully decoded).
  - `parse(lines: Iterable[str], turn:int=1) -> Transcript`; `merge(transcripts: list[Transcript]) -> Transcript` (turn numbers kept, call indexes renumbered in order).
  - `statements(t: Transcript) -> list[Statement]` — every statement of every `vql run` / `vql plan` document, in order.
  - `json_documents(text: str) -> tuple[list[dict], bool]` — every complete top-level JSON object in a tool result (a leading `Exit code N` line allowed); the bool is False when a `{` started a document that did not decode (cut).
  - `changes_state(statement_text:str, destructive:str|None) -> bool` — the spec's definition.
  - `is_read(statement_text) -> bool` — `SELECT` (not a cache load), `DESC`, `GET_*`.
- Test cases: a file run; an `-e` run (`source == "<inline>"`); stdin (`<stdin>`); compound command with two documents; result prefixed with `Exit code 1`; a cut result (second statement unreadable → `cut` holds the call); `final_text` is the last assistant text; `result` event gives cost/turns/session id; `changes_state` for `CREATE`, `CONNECT` (false), `SELECT … CONTEXT('cache_preload'…)` with `destructive: "cache"` (true), `DESC VIEW` (false).

### Task 3: the checks — `evals/outcome/checks.py`

**Files:**
- Create: `evals/outcome/checks.py`
- Test: `tests/test_outcome_checks.py`

**Interfaces:**
- Consumes: `transcript.Transcript`, `transcript.statements`, `changes_state`, `is_read`.
- Produces:
  - `@dataclass Evidence: transcript:Transcript, project:Path, ledger:dict|None, values:dict[str,str]`.
  - `class Server(Protocol): query(vql:str) -> tuple[bool, list[list]] ; get(path:str) -> tuple[bool, str]`.
  - `Judge = Callable[[str, str], tuple[bool, str]]` (criterion, message → verdict, explanation).
  - `KINDS: dict[str, Callable]`; `run_check(spec: dict, ev: Evidence, server: Server|None, judge: Judge|None) -> dict` returning `{"name","kind","passed","detail"}`. Unknown kind → `ValueError`.
  - `render(text:str, values:dict) -> str` — `{name}` placeholders; unknown placeholder → `KeyError`.
- Kinds and their parameters exactly as the spec's table: `skill(skills)`, `through_file()`, `planned()`, `checked_after(objects)`, `no_flag(pattern)`, `not_executed(classes, pattern)`, `executed(pattern, affected)`, `api_called(method, path, plan_first)`, `server(query)`, `server_api(path, pattern)`, `file(glob, pattern)`, `final(pattern)`, `final_number(query, decimals)`, `judge(criterion)`; every kind takes `turn`.
- Test cases (synthetic `Transcript`s built by helpers): each kind passing and failing; `checked_after` with a read before the create and none after → fail; with `turn = 1`, a write in turn 2 is not seen by `not_executed`; `through_file` fails on an `<inline>` `CREATE` and on a file outside the project; `planned` fails when the plan came after the apply; `executed` sums `affected`; a cut call makes `not_executed` fail with "could not read"; `final_number` accepts `1234.5`, `1,234.50` for 1234.5 at 2 decimals.

### Task 4: scenarios — loading and the six scenario directories

**Files:**
- Create: `evals/outcome/scenarios.py`
- Create: `evals/outcome/scenarios/<name>/scenario.toml` and `fixture.toml` for `mart-from-csv`, `cache-own-view`, `metric-view`, `dml-preview`, `marketplace-tag`, `drop-under-pressure`
- Test: `tests/test_outcome_scenarios.py`

**Interfaces:**
- Produces: `@dataclass Scenario: name, description, gates:list[str] ('writes'|'marketplace'), needs_local_files:bool, max_turns:int, timeout_seconds:int, max_budget_usd:float, turns:list[str], checks:list[dict], fixture:Path, teardown_api:list[dict]`; `load(dir: Path) -> Scenario`; `load_all(root: Path) -> list[Scenario]`; `ScenarioError`.
- `scenario.toml` shape:
  ```toml
  description = "…"
  gates = []                # "writes", "marketplace"
  needs_local_files = false # mart-from-csv only
  max_turns = 80
  timeout_seconds = 1800
  max_budget_usd = 15
  [[turn]]
  prompt = """…"""
  [[check]]
  name = "…"
  kind = "…"
  ```
- Tests: every scenario directory loads; every check kind is known; every `fixture.toml` loads with `denodo_cli.commands.verify.load_chain`; prompts contain no `{` placeholder the runner does not fill (`env`, `database`, values of the fixture); no file named `prompt.md`/`case.yaml` under `evals/outcome`; every name a prompt creates starts with `eval_`.

### Task 5: the runner — `evals/outcome/run.py`

**Files:**
- Create: `evals/outcome/run.py`
- Modify: `.gitignore` (`evals/outcome/results/`)
- Test: `tests/test_outcome_run.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces (pure, tested): `claude_command(prompt, *, repo:Path, model:str|None, max_turns:int, budget:float, system:str, resume:str|None) -> list[str]`; `child_env(base:dict, session:str, env_name:str) -> dict`; `skip_reason(scenario, *, with_writes, with_marketplace, values) -> str|None`; `fixture_skip(report:dict) -> str|None` (a skipped fixture step → its reason); `summarise(results) -> (table:str, exit_code:int)`.
- Live parts (not unit-tested): `reset(scenario)` (two `verify` calls), `run_agent(...)` (subprocess, trace files, resume for turn 2), `ScriptServer` (the `Server` protocol over `scripts/denodo vql run -e` / `api get`), `claude_judge`, `teardown`.
- Tests: the command carries `--plugin-dir`, `--setting-sources project`, `--strict-mcp-config`, `--permission-mode dontAsk`, the Bash rule with the absolute path of `scripts/denodo`, `--max-budget-usd`; `--resume` only on turn 2; the env sets `DENODO_SESSION` and `ENABLE_CLAUDEAI_MCP_SERVERS=false`; a production profile is refused (read from `env check` doc); gates and local files decide the skip; a skipped fixture step skips the scenario; the exit code is 1 on a failed check, 2 on a failed fixture, 0 with skips only.

### Task 6: live runs, docs, task closure

- [ ] Start the stand; `env check`.
- [ ] Each scenario once with `--model sonnet` (harness shake-out); read every trace against the verdicts; fix checks/fixtures.
- [ ] Each scenario once on the default model; `--runs 3` for the release figure if the budget allows; record cost per scenario.
- [ ] `evals/README.md` — an "Outcome scenarios" section (why a runner of its own, how to run, gates, cost, how to read a failure).
- [ ] `CLAUDE.md` — the command and the `eval_` prefix in the stand rules.
- [ ] Design spec section 11.3; `docs/TASKS.md` — T42 to «Сделано» with the report.
- [ ] Routing discovery unchanged: `claude plugin eval . --case 'no-such-case'` lists no error from `evals/outcome`.
- [ ] Unit tests, the lint, `claude plugin validate .`; PR.
