# Contributing

The skills grow from what happens when people use them. A session where the agent got it wrong, a
template that fails on your server, an error message decoded — all of it is welcome, and most of it
needs no change to the execution layer. What we accept, and how a session turns into a change, are
below.

This file is what you need in order to work here. The design documents under `docs/` are partly in
Russian and are the authority on *why* things are the way they are; everything in them that
constrains the parts you will touch is restated below in English.

**Contents** — [The short version](#the-short-version) · [What this repository is](#what-this-repository-is) ·
[A server to check against](#a-server-to-check-against) · [What we accept](#what-we-accept) ·
[From a session to a change](#from-a-session-to-a-change) · [Adding or changing a skill](#adding-or-changing-a-skill) ·
[The `verified:` mark](#the-verified-mark) · [Checks](#checks) · [Invariants](#invariants-that-break-silently) ·
[Branch, then PR](#branch-then-pr) · [Language](#language)

## The short version

1. **Branch** off `main`: `<type>/<short-subject>`.
2. **Reproduce** what went wrong on a synthetic fixture, with the skills of `main`.
3. Make **the narrowest change** that fixes it — one row, one sentence, one template.
4. **Keep a regression**: an eval case, an outcome scenario, or a `verify` step.
5. **Run the unit tests** — the same command CI runs:
   `PYTHONPATH=scripts python3 -m unittest discover -s tests -t .`
6. Changed a `description`? **Run the eval suite**: `claude plugin eval . --ablation none`.
7. **Open a pull request** that says what you did and why — the diff already shows which files.

## What this repository is

It is three things at once: the plugin, the marketplace that serves it, and the project that
develops it.

```
denodo_wipe_coading_skills/
├── .claude-plugin/
│   ├── plugin.json          the plugin: name "denodo"
│   └── marketplace.json     the marketplace: name "denodo-skills", one plugin, source "./"
├── skills/                  sixteen skills, each a SKILL.md and its references/
│   ├── vql/                 the core: working loop, conventions, safety, idempotency, dialect
│   ├── execute/             the live-call layer; references/errors.md decodes the server's messages
│   ├── catalog/             databases, folders, VDP tags
│   ├── datasources/         data sources, wrappers, base views
│   ├── views/               derived views, interface views, associations
│   ├── marketplace/         marketplace tags, categories, external elements
│   ├── procedures/          predefined, VQL and Java stored procedures
│   ├── cache/               the full cache of a view
│   ├── semantics/           descriptions, keys, associations, MCP visibility
│   ├── metrics/             metric views and the views over them
│   ├── security/            roles, grants, global security policies
│   ├── ai/                  LLM functions, their cached answers, semantic search
│   ├── dml/                 rows changed through a view: INSERT, UPDATE, DELETE
│   ├── materialize/         query results stored as tables: remote tables, summaries
│   ├── testing/             regression tests run by the Denodo Testing Tool
│   └── scheduler/           Denodo Scheduler jobs
├── .github/
│   ├── workflows/ci.yml     the checks every pull request runs
│   └── ISSUE_TEMPLATE/      a session report and a verify failure
├── scripts/
│   ├── denodo               launcher — standard library only
│   └── denodo_cli/          the implementation behind it
├── verification/            the chain of templates run against a live server (chain.toml)
│                            and the files its fixtures read (data/)
├── evals/                   phrase → expected skill; outcome/ what the agent does next
├── tests/                   unit tests and the lint of the skills, plus integration/ against a server
└── docs/                    design documents and the task tracker
```

A skill directory's name becomes its command: the plugin adds its own namespace, so `skills/views/`
is invoked as `/denodo:views`. **Never prefix a directory with `denodo-`** — `skills/denodo-views/`
would become `/denodo:denodo-views`.

## A server to check against

A live **Denodo 9.5** server and a profile for it in `~/.denodo/profiles.toml` — see the README for
the format, and run `scripts/denodo env init` yourself rather than through an agent. Any 9.5 you
are allowed to write to is enough: Denodo Express, a container image, a shared development server.
Templates that depend on an external database can be checked for syntax without one, because
Denodo's parser accepts DDL pointing at a host it cannot reach.

On a shared server, other people's work sits next to yours. The house rules:

- **Write only into your own database.** Create one for your checks and send every statement that
  changes state — `CREATE`, `ALTER`, `DROP`, any DDL — there. Other databases are free to *read*:
  `SELECT`, `DESC`, `DESC VQL` and `GET_ELEMENTS()` are the best source of real syntax there is,
  better than the documentation. But not one state-changing statement outside your own database,
  tidy-ups and "harmless" fixes included.
- **Server-wide objects belong to no database** — users, roles, VDP tags, global security policies,
  Data Marketplace tags and categories, Scheduler projects and jobs. Create them under a prefix
  that names your run and drop them by that name when you are done; read everyone else's, never
  change them.
- **A user you create for a check is `EXTERNAL`.** No password exists to leak, and impersonation
  reads as them.
- **A Scheduler job is created disabled**, or deleted before you finish: it runs as the login of
  its data source and keeps running after you leave.
- **A table written in a source database through Denodo is a real write** — `ROLLBACK` undoes
  nothing — so it is one you created for the check, never another team's.
- **AI functions send one paid request per row**: run them over a few hundred rows at most.

## What we accept

- **A change traced to a session or a `verify` report** — the issue forms ask for what is needed to
  reproduce it. A rule nobody has broken yet is a guess about the next session.
- **Correctness first**: a template that fails on a 9.5 server, a fact a skill states wider than it
  was measured, an error message the skills do not decode, a safety rule an agent got round.
- **Narrow scope.** A source type the skills do not build stays a Design Studio handover in
  `/denodo:datasources`; publishing web services, listeners, custom Java functions, wrappers and
  policies, user accounts and LDAP, promotion between environments and dbt are outside the plugin (README, *What the skills
  cover*). A new object skill comes when sessions keep asking for one, and starts narrow.
- **Every template carries its mark**, and every description change runs the eval suite (below).

## From a session to a change

Each kind of failure has the artifact that fixes it, and the artifact that keeps it fixed:

| What went wrong | The change | What keeps it fixed |
|---|---|---|
| the wrong skill fired, or none | the skill's `description` | a routing or discrimination case in `evals/`, and the suite run |
| the right skill, the wrong action — a guess, a step skipped, a yes not asked | the skill's text | an outcome scenario in `evals/outcome/`, or a RED/GREEN record in the pull request |
| a server message the agent could not read | a row of `skills/execute/references/errors.md`, or the skill's *Common mistakes* | the row's mark |
| a template that failed on a server | the template | its `verify` step |

The method that produced every skill here:

1. **Redact** the session: no client names, hosts, schemas or data — this repository is public.
2. **Reproduce it on a synthetic fixture**: a few files or tables in your own test database with
   names of their own (`eval_…`, or the run's prefix), small enough to read in full.
3. **RED**: run the request with the skills of `main` — a subagent, or `claude -p` with
   `--plugin-dir` — and keep its report. If the failure does not reproduce, there is nothing to
   change yet.
4. **The narrowest change** that addresses what RED did: one row, one sentence, one template.
5. **GREEN**: the same request with the change. Ask the agent for a review of the text, not only
   for the result — what was missing, unclear or wrong — and run a weaker model too.
6. **Keep a regression**: a case, a scenario or a `verify` step from the table above, and the RED
   and GREEN reports summarised in the pull request.

## Adding or changing a skill

The object skills share one skeleton — five blocks, in this order:

```
1. The fork          "this is about X; if you need Y, go to /denodo:Y"   (3–5 lines)
2. Minimal template  a working call, immediately, with no preamble
3. What to find out  what is missing before the template can be filled in
4. Where to go next  links into references/ for the non-standard cases
5. Verification      how to tell the object was created correctly
```

A skill whose actions can wait for the human's yes says who applies what before its templates,
and most close with the mistakes an agent makes there: *Silent failures* — what the server accepts
and gets wrong — and *Common mistakes*. Three things about the shape are load-bearing:

- **A template need not be VQL.** It is the minimal working call *in the channel that owns the
  object* — a VQL statement, a `scripts/denodo api` request for Data Marketplace or the Scheduler,
  a `.denodotest` file for the Testing Tool. The other four blocks do not depend on the channel. That is why a new platform server can be added as a skill
  without rewriting the existing ones.
- **Block 3 is what makes a skill a procedure rather than a reference.** Given "connect Oracle", an
  agent is missing the host, the port, the schema and the account. Say explicitly what comes from
  the environment profile, what comes from conventions, and what has to be asked — otherwise the
  agent either invents values or interrogates the user with ten questions.
- **Two levels of detail.** The minimal working template lives in `SKILL.md`; the full set of
  options, and notes on what Design Studio generates, live in `references/`. A reference holds
  grammar only for what the skill has the agent build: `datasources` sends every other source type
  to Design Studio, so its references stop at the three it builds. `SKILL.md` is loaded into
  context once and is not re-read, so write it as standing rules, not as a one-time recipe.

Order and dependencies belong in the skill too: an agent has to know
`data source → wrapper → base view` before it starts, not after it fails.

### The description

**Descriptions compete with each other.** The `description` in a skill's frontmatter is the entire
basis on which the right skill gets chosen.

- **Carry both** trigger phrasings and an explicit "not for X — that is /denodo:Y" line.
- **Keep it within 900 characters.** The Agent Skills limit is 1024; what is left is room for the
  next trigger phrase, and syntax in parentheses does little for routing — cut that first. The lint
  fails a description over 900 unless the skill is listed in `OVER_BUDGET` in
  `tests/skills_lint.py` with its length, which then may only shrink.
- **Name a renamed feature twice**: users say the old name, the 9.5 documentation the new one.

  | Users say | The 9.5 documentation says |
  |---|---|
  | Data Catalog | Data Marketplace |
  | Cache | Materialization |
  | Embedded MPP | Lakehouse Accelerator |
  | VDPCache job | Simple Cache Management |
  | Reference Lineage | 360 Graph |

- **Any edit to a `description`** — however cosmetic — means running the eval suite; see
  [Checks](#eval-suite).

## The `verified:` mark

**Every template carries its verification status, on the line above it**, as a comment in whatever
form the channel uses:

```sql
-- verified: 9.5.1 (live, 2026-09-09)
CREATE DATASOURCE JDBC ...

-- unverified: 9.5 documentation only
CREATE DATASOURCE JDBC ... WITH SOME_EXOTIC_OPTION ...
```

Those two forms are the only ones in use — copy them verbatim and change the version and date to
what you actually ran against; `live` stays as written, whatever the server was.

- **The comment character follows the channel**: `--` in VQL, `#` above a `scripts/denodo api`
  call and in a `.denodotest` file, and in prose a mark in italics at the end of the sentence it
  applies to. A chain of calls is marked as a whole, not call by call.
- **A template with no mark counts as unverified, and the lint fails it**: every fenced block under
  `skills/` carries a mark inside it or in the paragraph right above or below, or is listed in
  `UNMARKED_BLOCKS` in `tests/skills_lint.py` with the reason it is not a template — grammar, a
  diagram, the shape of a message, a command for the human.
- **Unverified templates are still shipped** — marked, so the agent proceeds more carefully and
  checks the result harder. Do not promote a mark to `verified:` because the statement looks right;
  promote it because you ran it.
- **A block marked `verified:` is a step of the verification chain**, or a line of `[not_run]` at
  the end of `verification/chain.toml` saying why it cannot be one — grammar, a fragment that no
  substitution makes a statement, a line the human types. A unit test
  (`tests/test_chain_manifest.py`) holds both directions: a new marked block without a step or a
  line fails it, and so does a line for a block that has since become a step. A prose mark — a fact
  in a sentence or a table cell — is outside the chain and is re-dated by hand.

Targeting **Denodo 9.5 only** is what keeps this workable — there are no version branches in the
templates, and adding one is not a fix.

## Checks

Five, each answering a different question:

| Check | The question | Needs | Run it |
|---|---|---|---|
| [Unit tests](#unit-tests) | does the execution layer work, and is the text clean? | nothing | every change — CI runs it on every pull request |
| [Integration tests](#integration-tests) | does the execution layer work against a real server? | a non-production server | a change to how `scripts/` talks to a server |
| [Template verification](#template-verification) | do the skills' own templates still work? | a server | a template changed; a failure blamed on a skill's text |
| [Eval suite](#eval-suite) | does the right skill fire for a given phrase? | a paid model | a skill added, any `description` changed |
| [Outcome scenarios](#outcome-scenarios) | what does the agent do after the skill fires? | a server and a paid model | a rule that decides whether the agent acts or asks; before a release |

CI (`.github/workflows/ci.yml`) also runs `claude plugin validate .`. Its warning about a missing
`version` is expected: without one Claude Code versions an install by its commit, so every merge
reaches `claude plugin update`. A `version` in `plugin.json` or in the plugin's entry of
`marketplace.json` would hold every user on it; `metadata.version` is not read.

### Unit tests

The execution layer, and the lint of what a plugin user and the agent read. No dependencies, no
server, fast:

```
PYTHONPATH=scripts python3 -m unittest discover -s tests -t .
```

The lint (`tests/skills_lint.py`, run by `tests/test_skills_lint.py`) fails on:

- **Cyrillic** in any file the plugin ships — everything outside `docs/` and `CLAUDE.md`;
- **names of one installation** — a test server's own tags, databases, hosts, ports and profile,
  the prefixes of test runs — and, in what users and the agent read, the project's task ids,
  release-scope words and the chain's `verify_…` names;
- **a skill's frontmatter**: a missing `SKILL.md`, frontmatter or description, a `name` that is not
  the directory's, a `denodo-` prefix; a description over 1024 characters, or over its budget of
  900 unless listed in `OVER_BUDGET`;
- **a `SKILL.md` over 500 lines** — the longer ones are listed in `LONG_SKILLS` and may only
  shrink;
- **a template without a mark**, or a mark in any other wording;
- **a link that does not resolve** — a `references/` file, a `/denodo:<name>`, a relative link.

Every finding names the file and line. `PYTHONPATH=scripts python3 -m tests.skills_lint [root]`
prints them all for any tree. It cannot tell a generic word from a server's own name — a tag called
`sensitive` passes — so the names it knows are the ones a review found.

### Integration tests

The same layer against a real server. Skipped unless `DENODO_TEST_ENV` names a non-production
profile. The objects are created in `denodo_skills_test` and removed afterwards; the database
itself stays:

```
DENODO_TEST_ENV=dev PYTHONPATH=scripts uv run --with denodo-sqlalchemy \
    --with psycopg2-binary python -m unittest tests.integration.test_stand
```

`tests.integration.test_verify_chain` runs the verification chain itself the same way, and creates
and drops the database; `DENODO_TEST_MARKETPLACE` adds its marketplace case, which synchronises the
shared catalog.

### Template verification

Do the skills' own templates still work? The chain in `verification/chain.toml` creates its own
test database, runs the templates in dependency order, and cleans up after itself:

```
scripts/denodo verify --env dev
```

Run this before blaming a skill's text for a failure — a broken template looks exactly like a badly
worded skill. The first step that fails stops the run — every later step is reported skipped — and
cleanup runs however the run ended.

| Flag | What it does |
|---|---|
| `--with-marketplace` | adds the REST tail, which synchronises the shared marketplace catalog — skipped while anything but the run's own database is pending there |
| `--with-ai` | adds the steps that call the server's LLM and embedding model (about 50 paid requests) |
| `--with-writes` | adds the tables in the cache database |
| `--with-scheduler` | adds the Scheduler jobs |
| `--testing-tool <dir>` | adds the `.denodotest` templates |
| `--without <feature>` | rehearses a server that lacks a feature: `enterprise_plus`, `llm`, `embedding`, `cache`, `summary_rewrite`, `data_movement`, `impersonation` |
| `--database <name>` | gives the run its own database instead of `denodo_skills_test` |
| `--keep` | leaves the objects for inspection |
| `--cleanup-only` | runs no step, only the cleanup, under the same `--with-*` flags — what `--keep` or an interrupted run left |
| `--update-marks` | rewrites the `verified:` line of every step that passed |

Two runs against one server must not overlap: `--database` gives a run its own database, but the
few server-wide `verify_…` objects are shared by name, and each run's cleanup drops them.

It runs on any 9.5 server:

- **What belongs to an installation is read from the server** before the first step. The embedding
  model and the cache data source with its catalog, schema and product are what `env check` shows
  under `features`, with the bundle, the LLM, summary rewriting and data movement; the Scheduler's
  data source is looked up only by `--with-scheduler`.
- **A step that needs what the server lacks is skipped** with the reason (`requires` in the
  manifest). A step that uses what an earlier step creates declares it in `needs = [...]` unless
  both are gated alike; a unit test reads the manifest and fails when a step that may be skipped
  would leave a later one to fail on its missing object.
- **The fixtures read `verification/data` over HTTP** from the repository, with nothing to set. A
  server without internet access reads a copy on its own disk: that copy, and anything the server
  does not say, go into `~/.denodo/verify.toml`, one table per profile (`--values <file>` for
  another) — installation values only: the test database and the prefix stay the chain's.
- **The data files are written by `verification/data/generate.py`** and held to it by a unit test;
  change the generator, not the files. A file on `main` never changes its rows or columns: installed
  copies of the plugin read the files from `main` with the manifest they were installed with, so new
  data goes into a file under a new name.

### Eval suite

Does the right skill fire for a given phrase? From the repository root, no installation needed:

```
claude plugin eval . --ablation none
```

Mandatory whenever you add a skill or change any `description`. The cases and how to read a failure
are in [`evals/README.md`](evals/README.md).

### Outcome scenarios

What does the agent do after the skill fires? Six requests run by headless Claude Code against a
non-production test server and graded on the trace, the session's ledger and the server's state:

```
python3 evals/outcome/run.py --env dev --with-writes --with-marketplace
```

Without the two flags it runs four: `dml-preview` writes a table in the cache database, and
`marketplace-tag` synchronises the shared catalog. `mart-from-csv` also needs the fixture files on
the server's own disk (`fixture_route` in `verify.toml`), or it is skipped. Each run is a paid agent
session — about $4.80 for one run of the six on the default model, about $15 for a release run of
three. Due on any change
to a rule that decides whether the agent acts or asks — `vql`'s safety table, a skill's "who
applies it" — and before a release. How they run, their fixtures and cost:
[`evals/README.md`](evals/README.md), *Outcome scenarios*.

## Invariants that break silently

Each one is a consequence of a design decision; breaking it does not raise an error, it just makes
something quietly wrong.

- **No `denodo-` prefix on skill directories.** The namespace is added by the plugin.
- **No credentials in the repository, and none in command arguments** — arguments end up in the
  session transcript. A command names a *profile*; the profile lives in `~/.denodo/profiles.toml`,
  outside any repository.
- **No customer data.** No real hosts, schemas or system names — this repository is public.
- **Every template carries a verification mark.**
- **Not every object is created through VQL.** Data Marketplace is a separate server with a REST
  API. VDP tags (`CREATE TAG`) and marketplace tags are *different objects*; a skill that confuses
  them issues a perfectly valid call to the wrong server.
- **`scripts/denodo` uses the standard library only.** It sets up the environment, so it has to run
  before any dependency exists.
- **Denodo 9.5 only.**

## Branch, then PR

Work goes on a branch off `main` — `<type>/<short-subject>`, e.g. `feat/execute-transport`,
`fix/vql-quoting` — never directly on `main`. Open a PR when you are done, and write the
description as an account of *what you did and why*: the decisions you made, what you verified
against a live server, and what you knowingly left open. The file list is already in the diff; it
is the reasoning that is not.

If the work is not finished, open it as a draft with an honest "what's left" section.

## Language

The plugin is in English: skill descriptions, `SKILL.md` files, `references/`, README, this file,
the CLI. The project's own documents — `docs/` and `CLAUDE.md` — are partly in Russian from earlier
work; new text there is English too. You do not need to read them to contribute; if something in
them turns out to constrain your change and is not restated here, that is a gap in this file worth
reporting.
