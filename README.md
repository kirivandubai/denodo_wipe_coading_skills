# Denodo Skills

A [Claude Code](https://claude.com/claude-code) plugin that creates **Denodo 9.5** objects
from plain-language intent. You say what you want — *"onboard these return files and give
me a mart of returns by store"* — and the agent decides where the objects belong, writes
the VQL, applies it to a live Virtual DataPort server, and checks that what it made
actually reads.

Sixteen skills: the working loop and the execution layer, and fourteen for what you build —
virtual databases, folders and VDP tags; JDBC, delimited-file and JSON data sources with their
wrappers and base views; derived, interface and metric views and associations; Data
Marketplace tags, categories and external elements; and the work around them — stored
procedures, the full cache of a view, the metadata AI consumers read, roles and security
policies, the server's LLM in a query, writes through views, query results stored as tables,
regression tests and Scheduler jobs.

The skills are general. They were written from the Denodo 9.5 documentation and checked
against a live 9.5.1 server, and they assume nothing about how that server is deployed —
a container, a VM, a managed instance, a cluster behind a load balancer: the only things
the plugin needs are in the profile. The point is to make vibe-coding on the Denodo
platform easier: you describe the objects, the agent produces reviewable VQL and applies
it, and the templates it works from state how far each of them has been verified.

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
- Network access to Virtual DataPort (port `9996` by default; the profile sets it) with an
  account allowed to create objects. Data Marketplace (`9090` by default) only if you use
  `/denodo:marketplace`; the Scheduler administration tool, on the same web container, only if
  you use `/denodo:scheduler`.
- **Python 3.11 or newer** on `PATH`. Nothing else: the plugin's own launcher builds its
  environment on first run — with `uv` if you have it, otherwise a venv under
  `~/.claude/plugins/data/denodo/`. Do not install database drivers by hand.
- For `/denodo:testing` only: the **Denodo Testing Tool**, downloaded from the Denodo support
  site (Denodo Connects) and unzipped anywhere, with **Java 17** or newer, and the Virtual
  DataPort JDBC port (`9999` by default) reachable. The plugin does not ship the tool.

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
# jdbc_port = 9999             # only for /denodo:testing: the JDBC port the Testing Tool connects to
# scheduler_url = "http://localhost:9090/webadmin/denodo-scheduler-admin"  # /denodo:scheduler; default: marketplace_url's web container
# scheduler_uri = "//localhost:8000"                                       # the Scheduler server, as the admin tool reaches it
```

Then ask Claude to check the connection — `env check` reaches VDP and, if configured, the
marketplace and the Scheduler. `env list` shows the profiles on the machine and never prints passwords.
`env check` also reports whether the profile's user is an administrator (`vdp.admin`) and
whether it may run a query as another user (`vdp.impersonation`, the `impersonator` role):
security policies do not apply to administrators, so `/denodo:security` checks a policy by
running the same query as each person it is for — without the role, that check is left to
you. Under `features` it reports what the server has: the Enterprise Plus bundle (tags, global
security policies and the AI functions need it), the cache database and its product, an LLM
and an embedding model, summary rewriting and data movement.

## Check the templates on your server

The templates were run on one 9.5.1 server; yours may have another bundle, another cache
database, no LLM. One command runs them on yours — ask Claude to run it, or run it yourself:

```
~/.claude/plugins/cache/denodo-skills/denodo/*/scripts/denodo verify --env dev
```

It creates its own database (`denodo_skills_test`), runs every verified template of the
skills in dependency order, checks what each one claims, and removes everything it made — the
database and the few server-wide objects it needs, all named `verify_…`. A step that needs
something your server lacks is skipped and says what; the summary counts what was verified,
failed and skipped. The tails that write outside that database or cost money are flags:
`--with-writes` (tables in the cache database), `--with-marketplace`, `--with-scheduler`,
`--with-ai` (about 50 paid requests to your LLM), `--testing-tool <dir>`; `--without <feature>`
skips what needs a feature even when the server has it. On a profile marked `production = true`
it refuses to start.

The values that belong to your installation are read from the server: the embedding model,
the cache data source, the Scheduler's data source. The test data is a handful of small
synthetic files the server reads over HTTP from this repository on GitHub. A server that
cannot reach GitHub, or anything the server does not say (the skip names it), goes into
`~/.denodo/verify.toml` beside the profiles, one table per profile — values of your installation
only; the test database and the names it drops stay the chain's:

```toml
[dev]
fixture_route = "LOCAL 'LocalConnection'"
fixture_base = "/srv/denodo/verify-data"      # verification/data, copied onto the server
scheduler_data_source_id = "7"
```

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
| `/denodo:datasources` | JDBC / DF / JSON data sources, their wrappers, base views; introspecting a source; handing every other source type to Design Studio | VQL |
| `/denodo:views` | derived views, interface views, associations | VQL |
| `/denodo:marketplace` | marketplace tags, categories, external elements, catalog synchronisation | REST |
| `/denodo:procedures` | calling the server's predefined procedures, writing your own in VQL, importing a Java one from a JAR | VQL |
| `/denodo:cache` | the full cache of a view: switching it on and off, loading it with all rows or the ones you name, clearing it; every other cache setting goes to Design Studio | VQL |
| `/denodo:semantics` | what people and AI consumers (MCP Server, Assisted Query, AI SDK) read about existing views: an audit of descriptions, primary keys, associations and the MCP visibility tag, and descriptions written from the data after you approve them | VQL |
| `/denodo:metrics` | metric views: KPIs defined once over a fact view and its dimensions (`CREATE METRIC VIEW`), the views built on them, and querying them with `evaluate_metric` | VQL |
| `/denodo:ai` | the server's LLM and embedding model in a query: classifying, scoring, translating, summarising or extracting from a text column, a cached view that keeps those answers so readers stop paying, and semantic search over stored vectors — never run over more rows than you agreed to | VQL |
| `/denodo:security` | who may read what: a role with read access and giving it to a user, a global security policy that masks columns, filters rows or denies a view over tagged columns, and checking it as each person by impersonation | VQL |
| `/denodo:dml` | rows changed in the database behind a view: update, insert (with the generated key back) and delete by key, a view an application writes through, rows copied from another view or a file, upserts — each previewed, with an undo file, applied only after your yes | VQL |
| `/denodo:materialize` | query results stored as tables: a remote table other tools read and its refresh, a frozen snapshot, a summary the optimizer answers aggregate queries from, a data movement for a slow federated join, a materialized table — a new table where you said is created by the agent, anything that replaces, empties or drops an older one waits for your yes | VQL |
| `/denodo:testing` | regression tests for your data products: `.denodotest` files beside the project's `.vql`, run by Denodo's own Testing Tool — a mart's totals against its input, a unique key, nothing invalid, the contract's columns, the rows a consumer reads, a mart that runs in its database; the tool's configuration written from the profile, outside the repository | Testing Tool |
| `/denodo:scheduler` | work on a schedule in Denodo Scheduler: a cache job that reloads the full cache of views, a job that runs one statement (`REFRESH`, a procedure) or exports a view to a CSV file; running, stopping, enabling and disabling jobs, reading their reports — a new job is created disabled and enabled after your yes when it touches what others read; data sources and every other job type stay in the administration tool | REST |

**A "tag" alone does not say which server you mean.** Virtual DataPort tags
(`CREATE TAG`, VQL) and Data Marketplace tags (REST) are different objects on different
servers; tags imported into the marketplace from VDP are read-only there. `catalog` and
`marketplace` split along that line, not along the word.

## What the skills cover — and what they do not

In scope: what the table above lists — everything needed to take a request from plain
language to a mart a consumer can browse, and the work around it. Several skills start
deliberately narrow: `/denodo:cache` is the full cache of a view only, `/denodo:semantics` the
Virtual DataPort half of view metadata, `/denodo:security` roles and global security
policies, `/denodo:scheduler` cache refreshes, single statements and CSV exports.

Created in Design Studio, not by the agent: every data source beyond a delimited or JSON file
on the server and a JDBC table with a password — REST APIs, Excel, XML, Salesforce, SAP, cloud
storage, base views over a SQL query or a stored procedure, refreshing a base view whose source
changed. `/denodo:datasources` tells the human what to create there and builds on the result.

Deliberately out of scope: a full function reference; performance beyond the full cache and
the tables of `/denodo:materialize` (partial cache, time to live, incremental loads, MPP); security beyond roles and global security policies (user accounts and
passwords, LDAP, per-role row and column restrictions, custom policies); configuring the
LLM, the embedding model or the vector database, and generating embeddings for a table;
publication
(REST/SOAP/GraphQL/OData services); Scheduler data sources and job types beyond a cache job and
a one-statement job; Solution Manager and cross-environment deployment; Denodo versions other
than 9.5.

Every template carries its verification status in a comment on the line above it —
`verified: 9.5.1 (live, <date>)` when it has been run against a live 9.5.1 server, or
`unverified: 9.5 documentation only` when it comes from the documentation alone. An
unverified template is still given to you, marked, so the agent treats it with more care.
Every block marked `verified` is re-run by `verify` (above), or listed at the end of
`verification/chain.toml` with the reason it cannot be — grammar, a fragment, a line you type.

## Safety

This plugin gets installed on production servers, so the rules are conservative by
default:

- **Creating a new object** the agent does on its own. **`DROP`, `ALTER` of an existing
  object, writes into sources (`INSERT`, `UPDATE`), server-wide settings (`SET '<property>'`),
  and anything at all on a profile marked `production = true`** require your
  explicit confirmation — that is a standing rule the skills follow on every server.
  Underneath it, the execution layer adds a hard stop that does not depend on the agent
  reading its instructions: on a `production = true` profile a destructive statement is
  refused outright unless `--allow-destructive` is passed, and `env.production` comes back
  on every single response, so the agent always knows where it is connected. The stop
  goes by the leading keyword and by the name of the procedure called: `SELECT * FROM
  DROP_REMOTE_TABLE(…)` is spelled like a read and is refused like a `DROP`.
- The same applies over REST, stated by method and path rather than by verb: several
  marketplace `POST` calls are destructive — synchronisation endpoints remove entries that
  vanished from the snapshot, and the tag- and category-assignment calls *replace* a
  view's assignments instead of adding to them. The agent synchronises the catalog itself
  only when everything the synchronisation would add or remove was created in the same
  session; anything else waits for your yes. On the Scheduler every `PUT` replaces a
  whole job, a status change starts, stops, enables or disables one, and a new job is judged by
  the statement it will run every night.
- **"Created in this session" is the tool's record, not the agent's memory.** Every `vql run`
  records the objects it created — the server's id with each — in a ledger kept per session
  beside your profiles (`~/.denodo/sessions/`, never in the project; the session is the Claude
  Code conversation, subagents included, or whatever `DENODO_SESSION` names). Before applying a
  file the agent runs `vql plan`, which reads the file against that ledger and the live server
  and says per statement whether the rule above lets the agent apply it or waits for your yes —
  so an object of the same name made by someone else, or a session whose context was
  compacted, does not turn into a guess. The plan informs and refuses nothing: the hard stop
  stays the production flag's. `vql ledger` lists what the session created.
- **Passwords never appear in a command.** Server credentials come from the profile. A
  *data source* password — the one that has to end up in `USERPASSWORD … ENCRYPTED` — is
  turned into its cipher by `secret encrypt`, which reads it from a hidden prompt or
  stdin and returns only the encrypted form. The Testing Tool reads its password from a
  `configuration.properties`: `testing run` gives it one from the profile in a temporary file
  for the run only, and `testing config` writes one beside the profiles file, readable by you
  only, for your own runs — never inside a git repository, never printed.
- **The Testing Tool runs whatever a test holds**, past the guard above. `/denodo:testing`
  writes suites that only read; on a `production = true` profile `testing run` and
  `testing config` refuse without `--allow-destructive`, which comes after your yes.

## Contributing

Skills in this repository are meant to be built together — a new object, a better
template, a reference file for a source type nobody has covered yet. Start with
[CONTRIBUTING.md](CONTRIBUTING.md): it has the layout of the repository, the five-block
shape of a `SKILL.md`, the rule about `verified:` marks, and the checks that guard the
plugin — the unit tests and the lint of the skills run in CI on every pull request.

One thing to know before you read it: the plugin itself — skills, templates, this README —
is written in English, while the project's own design documents under `docs/` and
`CLAUDE.md` are partly in Russian. You do not need to read them to add a skill; CONTRIBUTING.md
covers what they say about the parts you touch.

## License

[MIT](LICENSE).
