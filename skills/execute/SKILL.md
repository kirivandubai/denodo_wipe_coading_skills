---
name: execute
description: Use when VQL or a Data Marketplace REST call has to run against a live Denodo 9.5 server — applying a .vql file, running DESC or a test SELECT, calling the marketplace API, checking a connection — or when `scripts/denodo` returned JSON with `ok:false` that needs interpreting. Not for writing VQL — that is /denodo:vql and the domain skills.
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/denodo *)
---

# Executing against Denodo

One tool, `${CLAUDE_PLUGIN_ROOT}/scripts/denodo`, does every live call. Every invocation
prints exactly one JSON document on stdout; read `ok`, `error.kind` and the exit code
before doing anything else. The tool sets up its own Python environment on first run
(`uv` or a venv under the plugin data directory) — never install drivers by hand.

**Violating the letter of the rules below is violating their spirit.** They exist
because this plugin is installed on production servers.

## Commands

Every command takes `--env <profile>` (or `DENODO_ENV`). The profile is a *name*; the
tool reads host, user and password from `~/.denodo/profiles.toml` itself.

| Task | Command |
|---|---|
| Apply a file | `vql run --env dev model/sales/views.vql` |
| Apply inline VQL | `vql run --env dev -e "SELECT COUNT(*) FROM bv_orders"` |
| Read stdin | `vql run --env dev -` |
| Another database | add `--database <db>` (or put `CONNECT DATABASE <db>;` first in the file) |
| Schema of an object | `vql desc --env dev bv_orders` (`--type view` is the default and covers base views too — there is no `DESC TABLE`) |
| Server-generated VQL | `vql desc --env dev bv_orders --vql` — read it, do not apply it: it rebuilds the whole dependency chain and opens with `DROP … CASCADE` for every object in it |
| Other types | `--type database`, `--type "datasource df"`, `--type "wrapper df"`, `--type tag`, `--type association`, `--type "interface view"`; folders take a quoted path: `vql desc --env dev "'/sales'" --type folder --vql` |
| Marketplace call | `api get --env dev /public/api/tags` |
| … with a body | `api post --env dev /public/api/tags --json '{"name":"pii","description":"…","descriptionType":"TEXT"}'` |
| … query params / multipart | `--param k=v` (repeatable), `--part field=@file` / `field=json:{…}` |
| Which profiles exist | `env list` (never shows passwords) |
| Is the server reachable | `env check --env dev` (VDP, and the marketplace if configured) |
| Verify the skills' own templates | `verify --env dev` runs the chain in `verification/chain.toml` and removes everything it made: its own test database, and two server-level `verify_` tags beside it; `--with-marketplace` adds the REST tail, which also writes to the shared marketplace catalog and takes those entries back out during cleanup; `--keep` leaves it all for inspection, `--update-marks` rewrites the `verified:` lines that passed, `--allow-destructive` is required on a production profile — without it the whole run is refused before it creates anything |

Prefix every command with `${CLAUDE_PLUGIN_ROOT}/scripts/denodo`. Keep results
readable: `--max-rows N` (default 100) caps every result set; `row_count` is the
true count and `truncated` says whether rows were cut.

**`-e` does not repeat.** Two `-e` flags in one command run only the last one, silently —
`total: 1`. Several statements go into a file, or into one `-e` separated by `;`.

## Reading the result

Common envelope: `ok`, `command`, `env {name, production, transport, database}`,
and on failure `error {kind, message}`. **Look at `env.production` on every
response** — it tells you where you are connected.

| Exit | Meaning | What to do |
|---|---|---|
| `0` | success | verify the object (DESC / SELECT), report |
| `1` | the server refused a statement or call, or the network failed | read the message in `references/errors.md` |
| `2` | usage, configuration, or a refused destructive operation | fix the command, the profile, or stop for a human |
| `3` | driver stack could not be set up | show the human `error.hint` verbatim; do not `pip install` yourself |

**`vql run`** returns `statements[]` (one entry per statement: `index`, `statement`
head, `destructive`, `ok`, `error`, `columns`, `rows`, `row_count`), `failed_at`,
`executed`, `total`. The file is split into statements client-side and executed one by
one in one session. On the first failure execution **stops**: statements before
`failed_at` are applied, statements after it are not, and nothing is rolled back.
The server message you match against the error reference is
`statements[failed_at].error.message`.

**`api`** returns `status` separately from `body`; `body` is often `null` (`200`,
`403`, `404`, `409` all come with an empty body). `ok` is true only for 2xx. Some
marketplace calls report failure inside a `200`: `POST /tags/{id}/views` answers
with the list of ids it could *not* assign — success is an empty list.

**`vql desc`** returns the DESC rows as `columns`/`rows` (`DESC VQL` puts the
whole script in one cell).

**A `decimal` value arrives as a JSON string** (`"12.34"`), while `int`, `long` and
`double` arrive as JSON numbers. That is the transport, not the column: it says
nothing about the type in Denodo. To check a type, read it — `vql desc --env dev
<view>` — or do arithmetic on the server (`SELECT SUM(price * 2) …`); a text column
would fail there.

## When it fails — by `error.kind`

| `error.kind` | Cause | Action |
|---|---|---|
| `usage` | wrong arguments (no `--env`, no input, both file and `-e`) | fix the command; `--help` on the subcommand |
| `config` | profile missing, incomplete or unreadable; no `marketplace_url` for `api` | see **No profile** below |
| `connection` | host/port unreachable, wrong password, marketplace down | `env check --env <name>`; report the message; do not retry blindly |
| `refused` | destructive operation on a production profile | see **Destructive operations** below |
| `environment` | driver stack not importable | show `hint` to the human, stop |
| *(none, exit 1)* | the server rejected a statement or call | `references/errors.md`, fix the VQL/call, re-apply |

### No profile

`config` with "profiles file not found" or "profile 'x' not found" means the human
has to create one. Ask them to run **in their own terminal input**:

```
! ${CLAUDE_PLUGIN_ROOT}/scripts/denodo env init
```

It is interactive and hides the password. Then re-run your command.

- Do not ask for host, user or password in the chat, even if offered.
- Do not write or edit `profiles.toml` yourself.
- Do not pass a password through an argument, an environment variable, `-e`, or a
  heredoc — anything that goes through Bash is kept in the session transcript.
- If the human already pasted a password into the chat, say so and suggest rotating it.

### Destructive operations

`DROP`, `ALTER`, `DELETE`, `TRUNCATE`, HTTP `DELETE`, and the marketplace `POST`s that
replace a whole set or delete what is missing from the payload — `tags/vdp/synchronize`,
`element-management/{all,DATABASES,VIEWS,WEBSERVICES,EXTERNAL_ELEMENTS}/synchronize`, the
`external-tool-servers/synchronize` family, `views/{id}/tags` and
`category-management/views/{id}/categories`. Every result carries a `destructive` field: the
kind (`drop`, `alter`, `delete`, `replace`) when it is one of these, and `null` — not
`false` — when it is not. On a profile with `production: true` the tool refuses them with
`error.kind = "refused"` and executes **nothing**.

`--allow-destructive` is set only after the human has read the list of destructive
statements from `error.destructive` and confirmed, in this conversation, after the
refusal. The rule that requires the confirmation is the core skill (`/denodo:vql`);
this skill enforces its half: the flag is never yours to add.

When refused:
1. Show the human `env.name`, and each `error.destructive[].statement`.
2. Ask: "Apply these on production profile `<name>`?"
3. Only after an explicit yes, re-run the same command with `--allow-destructive`.

| Rationalization | Reality |
|---|---|
| "The user named this file and this profile — that is the confirmation" | Naming a file is not reading a `DROP`. The confirmation comes after the refusal, on the listed statements. |
| "The user said they can't answer right now / just make it work" | Then the answer is "waiting for your confirmation", not the flag. A demo is cheaper than a dropped object. |
| "It's `DROP … IF EXISTS` on the object the next line recreates" | `IF EXISTS` silences the error, not the data loss; and the recreate may fail after the drop succeeded. |
| "The object doesn't even exist, the drop is a no-op" | Your read of the catalog is a snapshot. The refusal is on the statement, not on its effect. |
| "It's only a test database on the production server" | The profile says `production`. Database names are not the rule. |
| "I'll disclose it afterwards" | Disclosure after the fact is not consent. |

**Red flags — stop and ask the human:** you are typing `--allow-destructive`; the
previous result had `error.kind: "refused"`; `env.production` is `true` and the VQL
contains `DROP` or `ALTER`.

### Error in the middle of a file

Do not reach for `--continue-on-error` to get past a failure. Read
`statements[failed_at].error.message`, fix the statement in the file, re-apply the
whole file: templates are `CREATE OR REPLACE`, so re-applying already-created
statements is safe. `--continue-on-error` is for the human's explicit request on a
file whose statements are independent.

## Verify before reporting

Success of `CREATE` is not success of the object. After applying:

- `vql desc --env dev <name>` for the schema, or `SELECT * FROM <name>` with
  `--max-rows 5` for a base or derived view;
- for a marketplace object, `GET` it back by name (all marketplace operations use
  numeric ids that only exist after creation).

A DF wrapper listing only part of the file's columns creates fine and returns zero
rows — the SELECT is what catches it.

## Not this skill

Writing the VQL or choosing where an object lives: `/denodo:vql` (conventions,
safety, idempotency) and the domain skills `/denodo:catalog`, `/denodo:datasources`,
`/denodo:views`, `/denodo:marketplace`. Trigger phrase confusion: VDP tags
(`CREATE TAG`, VQL) and marketplace tags (`POST /public/api/tags`, REST) are
different objects on different servers; the tool does not translate between them.
