# Denodo Skills

A [Claude Code](https://claude.com/claude-code) plugin that creates **Denodo 9.5** objects
from plain-language intent. You say what you want — *"onboard these return files and give
me a mart of returns by store"* — and the agent decides where the objects belong, writes
the VQL, applies it to a live Virtual DataPort server, and checks that what it made
actually reads.

Six skills cover sixteen objects: virtual databases, folders and VDP tags; JDBC,
delimited-file and JSON data sources with their wrappers and base views; derived views,
interface views and associations; and Data Marketplace tags, categories and external
elements.

## How it works

**The VQL goes into a file in your project, and the file is what gets applied.** That is
the rule the whole plugin is built around:

```
intent in plain language
  → placement decided from naming conventions (database, folder, layer)
  → a .vql file written into your repository
  → applied to the server
  → verified (DESC, a test SELECT)
  → the file stays in git
```

Objects that live only on a server exist in no artifact: nobody can review them, promote
them to the next environment, or rebuild them after a rollback. Data Marketplace is the
one exception to the VQL part — it is a separate server driven by REST — but the rest of
the loop is the same.

Naming follows Denodo's own *VDP Naming Conventions* out of the box (`ds_`, `bv_`, `iv_`,
`a_`, numbered layer folders). A project that has its own standard overrides them in
`.denodo/conventions.md` — plain markdown, no schema to learn.

## Requirements

- **Claude Code** (the plugin is installed from its marketplace).
- **Denodo 9.5.** Only 9.5. There are no version branches in the templates, and nothing
  here is tested against 8.x or earlier 9.x releases.
- Network access to Virtual DataPort (port `9996` by default) with an account allowed to
  create objects. Data Marketplace (port `9090`) only if you use `/denodo:marketplace`.
- **Python 3.11 or newer** on `PATH`. Nothing else: the plugin's own launcher builds its
  environment on first run — with `uv` if you have it, otherwise a venv under
  `~/.claude/plugins/data/denodo/`. Do not install database drivers by hand.

## Install

In Claude Code:

```
/plugin marketplace add kirivandubai/denodo_wipe_coading_skills
/plugin install denodo@denodo-skills
```

The marketplace is `denodo-skills`, the plugin inside it is `denodo`, and the GitHub
repository has a third name — all three are correct as written above.

## Set up an environment profile

Credentials never appear in a command, because command arguments are recorded in the
session transcript. They live in a profile file outside any repository — by default
`~/.denodo/profiles.toml` (override with `DENODO_PROFILES`) — and commands name only the
*profile*.

**Run this yourself, not through the agent** — it prompts for the password with a hidden
input, so nothing is echoed into the transcript. In Claude Code, prefix it with `!`:

```
! ~/.claude/plugins/cache/denodo-skills/denodo/*/scripts/denodo env init
```

Or write the file by hand:

```toml
[dev]
host = "localhost"
port = 9996                    # VDP, default 9996
database = "admin"             # default database for the connection
user = "…"
password = "…"                 # or password_env = "DENODO_DEV_PASSWORD"
production = false             # see Safety below — this flag is not decorative
transport = "vql_psycopg2"
marketplace_url = "http://localhost:9090/denodo-data-catalog"  # only for /denodo:marketplace
# marketplace_server_id = 1    # required when the marketplace has several VDP servers registered
```

Then ask Claude to check the connection — `env check` reaches VDP and, if configured, the
marketplace. `env list` shows the profiles on the machine and never prints passwords.

## Quick start

With a profile in place, talk to Claude normally:

> Connect to the profile `dev`, onboard `/data/store_returns.csv` and `/data/store.csv`,
> and build me a mart of returned amount by store and month.

What happens: the agent picks `/denodo:datasources`, creates a `DF` data source, its
wrapper and base views in the connectivity layer, then `/denodo:views` for the derived
view in the business layer, writes each step into `.vql` files in your project, applies
them, and finishes with a `SELECT` to prove the mart reads. If something is missing from
your request — where the files live, which column is the key — it asks rather than
inventing.

You rarely name a skill. Descriptions are written so that the right one is chosen from the
phrasing; `/denodo:vql` is the entry point when the request is ambiguous.

## The skills

| Skill | Objects | Channel |
|---|---|---|
| `/denodo:vql` | the working loop, naming conventions, safety rules, idempotency — the core every other skill builds on | — |
| `/denodo:execute` | applying VQL and REST calls to a live server, reading the JSON envelope, interpreting Denodo's error messages | both |
| `/denodo:catalog` | virtual database, folder, VDP tag (and assigning a tag to views and columns) | VQL |
| `/denodo:datasources` | JDBC / DF / JSON data sources, their wrappers, base views; introspecting a source | VQL |
| `/denodo:views` | derived views, interface views, associations | VQL |
| `/denodo:marketplace` | marketplace tags, categories, external elements, catalog synchronisation | REST |
| `/denodo:procedures` | calling the server's predefined procedures, writing your own in VQL, importing a Java one from a JAR | VQL |

**A "tag" alone does not say which server you mean.** Virtual DataPort tags
(`CREATE TAG`, VQL, port 9996) and Data Marketplace tags (REST, port 9090) are different
objects; tags imported into the marketplace from VDP are read-only there. `catalog` and
`marketplace` split along that line, not along the word.

## What v1 covers — and what it does not

In scope: the sixteen objects of the first six skills, everything needed to take a request
from plain language to a mart a consumer can browse. `/denodo:procedures` sits outside that
scope — stored procedures are not part of the mart scenario — and is there because it is
useful on its own.

Deliberately out of scope: a full function reference; performance and caching (summary
views, materialized tables, remote tables, MPP); security and publication (users, roles,
privileges, row/column restrictions, REST/SOAP/GraphQL/OData services); Scheduler,
Solution Manager and cross-environment deployment; Denodo versions other than 9.5.

Every template carries its verification status in a comment on the line above it —
`verified: 9.5.1 (стенд, <date>)` when it has been run against a live server, or
`unverified: только по документации 9.5` when it comes from the documentation alone. An
unverified template is still given to you, marked, so the agent treats it with more care.

## Safety

This plugin gets installed on production servers, so the rules are conservative by
default:

- **Creating a new object** the agent does on its own. **`DROP`, `ALTER` of an existing
  object, and anything at all on a profile marked `production = true`** require your
  explicit confirmation — that is a standing rule the skills follow on every server.
  Underneath it, the execution layer adds a hard stop that does not depend on the agent
  reading its instructions: on a `production = true` profile a destructive statement is
  refused outright unless `--allow-destructive` is passed, and `env.production` comes back
  on every single response, so the agent always knows where it is connected.
- The same applies over REST, stated by method and path rather than by verb: several
  marketplace `POST` calls are destructive — synchronisation endpoints remove entries that
  vanished from the snapshot, and the tag- and category-assignment calls *replace* a
  view's assignments instead of adding to them.
- **Passwords never appear in a command.** Server credentials come from the profile. A
  *data source* password — the one that has to end up in `USERPASSWORD … ENCRYPTED` — is
  turned into its cipher by `secret encrypt`, which reads it from a hidden prompt or
  stdin and returns only the encrypted form.

## Contributing

Skills in this repository are meant to be built together — a new object, a better
template, a reference file for a source type nobody has covered yet. Start with
[CONTRIBUTING.md](CONTRIBUTING.md): it has the layout of the repository, the five-block
shape of a `SKILL.md`, the rule about `verified:` marks, and the four checks that guard
the plugin.

One thing to know before you read it: the plugin itself — skills, templates, this README —
is written in English, while the project's own design documents under `docs/` and
`CLAUDE.md` are in Russian. You do not need to read them to add a skill; CONTRIBUTING.md
covers what they say about the parts you touch.

## License

[MIT](LICENSE).
