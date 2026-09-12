# Contributing

The point of this repository is that skills get built together. A new object, a better
template, a `references/` file for a source type nobody has covered yet, an error message
decoded — all of it is welcome, and none of it requires touching the execution layer.

This file is what you need in order to work here. The design documents under `docs/` are
in Russian and are the authority on *why* things are the way they are; everything in them
that constrains the parts you will touch is restated below in English.

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
│   └── marketplace/         marketplace tags, categories, external elements + references/
├── scripts/
│   ├── denodo               launcher — standard library only
│   └── denodo_cli/          the implementation behind it
├── verification/chain.toml  the chain of templates run against a live stand
├── evals/                   phrase → expected skill
├── tests/                   unit tests, plus integration/ against a stand
└── docs/                    design documents and the task tracker (Russian)
```

A skill directory's name becomes its command: the plugin adds its own namespace, so
`skills/views/` is invoked as `/denodo:views`. **Never prefix a directory with `denodo-`**
— `skills/denodo-views/` would become `/denodo:denodo-views`.

## What you need to verify anything

A live **Denodo 9.5** server and a profile for it in `~/.denodo/profiles.toml` (see the
README for the format, and run `scripts/denodo env init` yourself rather than through an
agent). A local Denodo Express or a lab container is enough; templates that depend on an
external database can be checked for syntax without one, because Denodo's parser accepts
DDL pointing at a host it cannot reach.

**On a shared stand, write only into your own database.** Create one for your checks and
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
  of options, and notes on what Design Studio generates, live in `references/`. `SKILL.md`
  is loaded into context once and is not re-read, so write it as standing rules, not as a
  one-time recipe.

Order and dependencies belong in the skill too: an agent has to know
`data source → wrapper → base view` before it starts, not after it fails.

**Descriptions compete with each other.** The `description` in a skill's frontmatter is
the entire basis on which the right skill gets chosen, it has a budget of 1536 characters
in the listing, and it should carry both trigger phrasings and an explicit "not for X —
that is /denodo:Y" line. Any edit to a `description` — however cosmetic — means running
the eval suite; see below.

## The `verified:` mark

**Every template carries its verification status, on the line above it**, as a comment in
whatever form the channel uses:

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
CREATE DATASOURCE JDBC ...

-- unverified: только по документации 9.5
CREATE DATASOURCE JDBC ... WITH SOME_EXOTIC_OPTION ...
```

The wording of the mark is Russian, for historical reasons, and those two forms are the
only ones in use — copy them verbatim and change the version and date to what you actually
ran against. A template with no mark counts as unverified.

The comment character follows the channel: `--` in VQL, `#` above a `scripts/denodo api`
call in the marketplace skill, and in prose a mark in italics at the end of the sentence
it applies to. A chain of calls is marked as a whole, not call by call. Unverified
templates are still shipped — marked, so the agent proceeds more carefully and checks the
result harder. Do not promote a mark to `verified:` because the statement looks right;
promote it because you ran it.

Targeting **Denodo 9.5 only** is what keeps this workable — there are no version branches
in the templates, and adding one is not a fix.

## Checks

Four, each answering a different question.

**Unit tests** — the execution layer. No dependencies, no server, fast:

```
PYTHONPATH=scripts python3 -m unittest discover -s tests -t .
```

**Integration tests** — the same layer against a real stand. Skipped unless
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
scripts/denodo verify --env lab
```

`--with-marketplace` adds the REST tail (which writes to the shared marketplace catalog),
`--keep` leaves the objects for inspection, and `--update-marks` rewrites the `verified:`
line of every step that passed. Run this before blaming a skill's text for a failure — a
broken template looks exactly like a badly worded skill.

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
verified against a live stand, and what you knowingly left open. The file list is already
in the diff; it is the reasoning that is not.

If the work is not finished, open it as a draft with an honest "what's left" section.

## Language

The plugin is in English: skill descriptions, `SKILL.md` files, `references/`, README,
this file. The project's own documents — `docs/` and `CLAUDE.md` — are in Russian, and
stay that way. You do not need to read them to contribute; if something in them turns out
to constrain your change and is not restated here, that is a gap in this file worth
reporting.
