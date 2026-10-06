# Contributing

The point of this repository is that skills get built together. A new object, a better
template, a `references/` file for a source type nobody has covered yet, an error message
decoded — all of it is welcome, and none of it requires touching the execution layer.

This file is what you need in order to work here. The design documents under `docs/` are
partly in Russian and are the authority on *why* things are the way they are; everything in
them that constrains the parts you will touch is restated below in English.

## What this repository is

It is three things at once: the plugin, the marketplace that serves it, and the project
that develops it.

```
denodo_skills/
├── .claude-plugin/
│   ├── plugin.json          the plugin: name "denodo"
│   └── marketplace.json     the marketplace: name "denodo-skills", one plugin, source "./"
├── skills/
│   ├── vql/                 the core: working loop, conventions, safety, idempotency
│   ├── execute/             the live-call layer + references/errors.md
│   ├── catalog/             databases, folders, VDP tags
│   ├── datasources/         data sources, wrappers, base views + references/
│   ├── views/               derived views, interface views, associations + references/
│   ├── marketplace/         marketplace tags, categories, external elements + references/
│   ├── procedures/          predefined, VQL and Java stored procedures + references/
│   ├── cache/               the full cache of a view + references/
│   ├── semantics/           descriptions, keys, associations, MCP visibility + references/
│   ├── metrics/             metric views and the views over them + references/
│   ├── security/            roles, grants, global security policies + references/
│   ├── ai/                  LLM functions, their cached answers, semantic search + references/
│   ├── dml/                 rows changed through a view: INSERT, UPDATE, DELETE + references/
│   ├── materialize/         query results stored as tables: remote tables, summaries + references/
│   ├── testing/             regression tests run by the Denodo Testing Tool + references/
│   └── scheduler/           Denodo Scheduler jobs + references/
├── .github/workflows/ci.yml the checks every pull request runs
├── scripts/
│   ├── denodo               launcher — standard library only
│   └── denodo_cli/          the implementation behind it
├── verification/           the chain of templates run against a live server (chain.toml)
│                            and the files its fixtures read (data/)
├── evals/                   phrase → expected skill
├── tests/                   unit tests and the lint of the skills, plus integration/ against a server
└── docs/                    design documents and the task tracker
```

A skill directory's name becomes its command: the plugin adds its own namespace, so
`skills/views/` is invoked as `/denodo:views`. **Never prefix a directory with `denodo-`**
— `skills/denodo-views/` would become `/denodo:denodo-views`.

## What you need to verify anything

A live **Denodo 9.5** server and a profile for it in `~/.denodo/profiles.toml` (see the
README for the format, and run `scripts/denodo env init` yourself rather than through an
agent). Any 9.5 you are allowed to write to is enough — Denodo Express, a container image,
a shared development server; templates that depend on an external database can be checked
for syntax without one, because Denodo's parser accepts
DDL pointing at a host it cannot reach.

**On a shared server, write only into your own database.** Create one for your checks and
send every statement that changes state — `CREATE`, `ALTER`, `DROP`, any DDL — there.
Other databases are free to *read*: `SELECT`, `DESC`, `DESC VQL` and `GET_ELEMENTS()` are
the best source of real syntax there is, better than the documentation. But not one
state-changing statement outside your own database, tidy-ups and "harmless" fixes
included.

## Adding or changing a skill

A domain skill has five blocks, in this order:

```
1. The fork          "this is about X; if you need Y, go to /denodo:Y"   (3–5 lines)
2. Minimal template  a working call, immediately, with no preamble
3. What to find out  what is missing before the template can be filled in
4. Where to go next  links into references/ for the non-standard cases
5. Verification      how to tell the object was created correctly
```

Three things about that shape are load-bearing:

- **A template need not be VQL.** It is the minimal working call *in the channel that owns
  the object* — a VQL statement, or a `scripts/denodo api` request for Data Marketplace.
  The other four blocks do not depend on the channel. That is why a new platform server
  can be added as a skill without rewriting the existing ones.
- **Block 3 is what makes a skill a procedure rather than a reference.** Given "connect
  Oracle", an agent is missing the host, the port, the schema and the account. Say
  explicitly what comes from the environment profile, what comes from conventions, and
  what has to be asked — otherwise the agent either invents values or interrogates the
  user with ten questions.
- **Two levels of detail.** The minimal working template lives in `SKILL.md`; the full set
  of options, and notes on what Design Studio generates, live in `references/`. A reference
  holds grammar only for what the skill has the agent build: `datasources` sends every other
  source type to Design Studio, so its references stop at the three it builds. `SKILL.md`
  is loaded into context once and is not re-read, so write it as standing rules, not as a
  one-time recipe.

Order and dependencies belong in the skill too: an agent has to know
`data source → wrapper → base view` before it starts, not after it fails.

**Descriptions compete with each other.** The `description` in a skill's frontmatter is
the entire basis on which the right skill gets chosen, and it should carry both trigger
phrasings and an explicit "not for X — that is /denodo:Y" line. **Keep it within 900
characters.** The Agent Skills limit is 1024; what is left is room for the next trigger
phrase, and syntax in parentheses does little for routing — cut that first. The lint fails
a description over 900 unless the skill is listed in `OVER_BUDGET` in
`tests/skills_lint.py` with its length, which then may only shrink. Any edit to a `description` — however cosmetic — means running
the eval suite; see below. A feature renamed in 9.x goes into the description under both
names, because users say the old one and the 9.5 documentation the new one: Data Catalog →
Data Marketplace, Cache → Materialization, Embedded MPP → Lakehouse Accelerator, VDPCache
job → Simple Cache Management, Reference Lineage → 360 Graph.

## The `verified:` mark

**Every template carries its verification status, on the line above it**, as a comment in
whatever form the channel uses:

```sql
-- verified: 9.5.1 (live, 2026-09-09)
CREATE DATASOURCE JDBC ...

-- unverified: 9.5 documentation only
CREATE DATASOURCE JDBC ... WITH SOME_EXOTIC_OPTION ...
```

Those two forms are the only ones in use — copy them verbatim and change the version and
date to what you actually ran against; `live` stays as written, whatever the server was. A
template with no mark counts as unverified, and the lint fails it: every fenced block under
`skills/` carries a mark inside it or in the paragraph right above or below, or is listed
in `UNMARKED_BLOCKS` in `tests/skills_lint.py` with the reason it is not a template —
grammar, a diagram, the shape of a message, a command for the human.

The comment character follows the channel: `--` in VQL, `#` above a `scripts/denodo api`
call in the marketplace skill, and in prose a mark in italics at the end of the sentence
it applies to. A chain of calls is marked as a whole, not call by call. Unverified
templates are still shipped — marked, so the agent proceeds more carefully and checks the
result harder. Do not promote a mark to `verified:` because the statement looks right;
promote it because you ran it.

**A block marked `verified:` is a step of the verification chain**, or a line of `[not_run]`
at the end of `verification/chain.toml` saying why it cannot be one — grammar, a fragment that
no substitution makes a statement, a line the human types. A unit test
(`tests/test_chain_manifest.py`) holds both directions: a new marked block without a step or a
line fails it, and so does a line for a block that has since become a step. A prose mark — a
fact in a sentence or a table cell — is outside the chain and is re-dated by hand.

Targeting **Denodo 9.5 only** is what keeps this workable — there are no version branches
in the templates, and adding one is not a fix.

## Checks

Four, each answering a different question. The first runs in CI on every pull request
(`.github/workflows/ci.yml`), together with `claude plugin validate .`; the other three
need a server or a paid model and are yours to run.

**Unit tests** — the execution layer, and the lint of what a plugin user and the agent
read. No dependencies, no server, fast:

```
PYTHONPATH=scripts python3 -m unittest discover -s tests -t .
```

The lint (`tests/skills_lint.py`, run by `tests/test_skills_lint.py`) fails on Cyrillic in
the skills, README, this file, the manifests, the CLI or the eval cases; on names of one
installation — a test server's own tags, databases, hosts, ports and profile, the
prefixes of test runs — and on the project's task ids and release-scope words; on a
description over its budget or a `SKILL.md` over 500 lines (the longer ones are listed in
`LONG_SKILLS` and may only shrink); on a template without a mark or a mark in any other
wording; on a `references/` file, a `/denodo:<name>` or a relative link that does not
resolve. Every finding names the file and line. `PYTHONPATH=scripts python3 -m tests.skills_lint [root]` prints them all for
any tree. It cannot tell a generic word from a server's own name — a tag called `sensitive`
passes — so the names it knows are the ones a review found.

**Integration tests** — the same layer against a real server. Skipped unless
`DENODO_TEST_ENV` names a non-production profile; everything is created in
`denodo_skills_test` and removed afterwards:

```
DENODO_TEST_ENV=dev PYTHONPATH=scripts uv run --with denodo-sqlalchemy \
    --with psycopg2-binary python -m unittest tests.integration.test_stand
```

**Template verification** — do the skills' own templates still work? The chain in
`verification/chain.toml` creates its own test database, runs the templates in dependency
order, and cleans up after itself:

```
scripts/denodo verify --env dev
```

`--with-marketplace` adds the REST tail (which writes to the shared marketplace catalog),
`--with-ai` adds the steps that call the server's LLM and embedding model (about 50 paid
requests), `--with-writes` the tables in the cache database, `--with-scheduler` the Scheduler
jobs, `--testing-tool <dir>` the `.denodotest` templates; `--keep` leaves the objects for
inspection, and `--update-marks` rewrites the `verified:` line of every step that passed. Run
this before blaming a skill's text for a failure — a broken template looks exactly like a badly
worded skill.

It runs on any 9.5 server. What belongs to an installation is read from the server before the
first step — the embedding model, the cache data source with its catalog, schema and product,
the Scheduler's data source — and `env check` shows it under `features`, with the bundle, the
LLM, summary rewriting and data movement. A step that needs what the server lacks is skipped
with the reason (`requires` in the manifest). The fixtures read `verification/data` over HTTP
from the repository; a server without internet access reads a copy on its own disk. Both, and
anything the server does not say, are set in `~/.denodo/verify.toml`, one table per profile
(`--values <file>` for another) — installation values only: the test database and the prefix stay
the chain's. `--without <feature>` rehearses a server that lacks one. A step that uses what an
earlier step creates declares it in `needs = [...]` unless both are gated alike; a unit test reads
the manifest and fails when a step that may be skipped would leave a later one to fail on its
missing object. The data files are written by `verification/data/generate.py`
and held to it by a unit test; change the generator, not the files.

**Eval suite** — does the right skill fire for a given phrase? From the repository root,
no installation needed:

```
claude plugin eval . --ablation none
```

Mandatory whenever you add a skill or change any `description`. The cases and how to read
a failure are in [`evals/README.md`](evals/README.md).

## Invariants that break silently

Each one is a consequence of a design decision; breaking it does not raise an error, it
just makes something quietly wrong.

- **No `denodo-` prefix on skill directories.** The namespace is added by the plugin.
- **No credentials in the repository, and none in command arguments** — arguments end up
  in the session transcript. A command names a *profile*; the profile lives in
  `~/.denodo/profiles.toml`, outside any repository.
- **No customer data.** No real hosts, schemas or system names — this repository is
  public.
- **Every template carries a verification mark.**
- **Not every object is created through VQL.** Data Marketplace is a separate server with
  a REST API. VDP tags (`CREATE TAG`) and marketplace tags are *different objects*; a
  skill that confuses them issues a perfectly valid call to the wrong server.
- **`scripts/denodo` uses the standard library only.** It sets up the environment, so it
  has to run before any dependency exists.
- **Denodo 9.5 only.**

## Branch, then PR

Work goes on a branch off `main` — `<type>/<short-subject>`, e.g. `feat/execute-transport`,
`fix/vql-quoting` — never directly on `main`. Open a PR when you are done, and write the
description as an account of *what you did and why*: the decisions you made, what you
verified against a live server, and what you knowingly left open. The file list is already
in the diff; it is the reasoning that is not.

If the work is not finished, open it as a draft with an honest "what's left" section.

## Language

The plugin is in English: skill descriptions, `SKILL.md` files, `references/`, README,
this file, the CLI. The project's own documents — `docs/` and `CLAUDE.md` — are partly in
Russian from earlier work; new text there is English too. You do not need to read them to
contribute; if something in them turns out to constrain your change and is not restated
here, that is a gap in this file worth reporting.
