# Denodo error reference

Two classes of errors reach the agent through `scripts/denodo`:

1. **Virtual DataPort** (`vql run`, `vql desc`, exit `1`): the server has no error codes,
   only text. Match by **substring** of `statements[failed_at].error.message` (the
   `raw` field keeps the driver's full two-line message). Names in quotes vary.
2. **Data Marketplace** (`api`, exit `1`): HTTP `status`, plus `body.code` when the
   server bothers to send a body — it often does not.

Client-side failures (exit `2`/`3`, `error.kind` set) are listed last.

Every row was reproduced on a 9.5.1 stand on 2026-09-08 unless marked
*T11 report* (same stand, same day, taken from the marketplace spike instead of
re-triggered).

## 1. Virtual DataPort messages

### Object already exists (idempotency)

Fix for all of them: use `CREATE OR REPLACE` — supported by every VQL object type
in v1 — instead of retrying `DROP` + `CREATE`.

| Substring | Statement | Meaning |
|---|---|---|
| `Database already exists` | `CREATE DATABASE` | there is no `CREATE OR REPLACE DATABASE` ambiguity — it exists, connect to it |
| `Error creating folder: /x already exists` | `CREATE FOLDER` | folder exists |
| `Invalid tag name: already exists` | `CREATE TAG` | tag exists |
| `Duplicate object identifier` | `CREATE DATASOURCE`, `CREATE WRAPPER` | source/wrapper of that name exists (message prefix names which) |
| `already exists` (`Invalid view name` / `invalid view name`) | `CREATE VIEW`, `CREATE TABLE` | derived or base view exists |

### Referenced object not found (order of creation)

Fix: create the missing dependency first — `datasource → wrapper → base view →
derived view → interface view / association` — or fix the name/database.

| Substring | Statement | Meaning |
|---|---|---|
| `View '<name>' not found` | `CREATE VIEW … AS SELECT`, `SELECT`, `CREATE INTERFACE VIEW … SET IMPLEMENTATION` | the view in `FROM` / `SET IMPLEMENTATION` is missing in the *current* database; check `CONNECT DATABASE` / `--database` |
| `Field not found '<col>' in view with schema:` | `CREATE VIEW`, `SELECT` | column name wrong; the schema follows in `raw` |
| `Error loading referenced views` | `CREATE ASSOCIATION` | an endpoint view does not exist |
| `Data source <name> not found` | `CREATE WRAPPER` | wrapper's `DATASOURCENAME` missing |
| `Error loading wrapper '<db>.<type>/<name>'` | `CREATE TABLE` | base view's `WRAPPER (…)` missing |
| `destination folder '/x' not found` | any `FOLDER = '/x'` | create the folder first (`CREATE FOLDER '/x'`) |
| `Cannot create folder /a/b: parent not found` | `CREATE FOLDER` | create `/a` first; folders are not created recursively |
| `Error loading database '<db>'` (`error opening new session`) | `CONNECT DATABASE` | database does not exist or no privilege |
| `Error loading view '<name>' in database '<db>'` | `DESC VIEW` | object missing, or it is not a view — `--type` decides |
| `Function '<name>' with arity N not found` | any | no such VQL function with that number of arguments |

### Syntax

`Syntax error: Exception parsing query near '<token>'` — the token is where the parser
gave up, which is usually *after* the real mistake. Known causes, by token:

| near | Cause | Fix |
|---|---|---|
| `'''` (a quote) | `FOLDER '/x'` or `DESCRIPTION 'x'` without `=` in `CREATE VIEW`/`TABLE`/`DATASOURCE`/`WRAPPER` | write `FOLDER = '/x'`, `DESCRIPTION = 'x'` (bare `FOLDER '/x'` is only `CREATE FOLDER` syntax) |
| `'IF'` | `CREATE … IF NOT EXISTS` | VQL has no `IF NOT EXISTS`; use `CREATE OR REPLACE` |
| `'ADD'` | `CREATE TABLE … CACHE OFF ADD SEARCHMETHOD` | `TIMETOLIVEINCACHE DEFAULT` is required between `CACHE OFF` and `ADD SEARCHMETHOD` |
| `''` (empty) after `ALTER TAG … ADD_TO (…)` | `ADD_TO` without `REMOVE_FROM` | both blocks are mandatory: `ADD_TO ( VIEWS (…) COLUMNS () ) REMOVE_FROM ( VIEWS () COLUMNS () )` |
| `'one'` | `SELECT 1 AS one` | `one` is a reserved word; pick another alias |
| `'TABLE'` / `'WRAPPER'` / `'/'` | `DESC TABLE x`, `DESC WRAPPER x`, `DESC FOLDER /x` | base views are `DESC VIEW x`; wrappers and datasources carry their type (`wrapper df`, `datasource df`); folder paths are quoted (`--type folder "'/x'"`) |
| `'RELATIONSHIP'` | `CREATE ASSOCIATION … ADD RELATIONSHIP` | the clause is `ADD MAPPING a = b`; endpoints need cardinality: `ENDPOINT x v PRINCIPAL (0,1) ENDPOINT y w (0,*)` |
| a keyword | misspelled keyword (`VIEWW`) | fix the spelling |

### Type declarations

| Substring | Statement | Fix |
|---|---|---|
| `error while loading the type of the field 'bigint'` | `CREATE INTERFACE VIEW`, `CREATE TABLE` | use VQL types: `long`, `int`, `text`, `decimal`, `date`, `timestamp`, `boolean` — not SQL ones |

### Dependencies on DROP

`DROP … IF EXISTS` silences only "does not exist"; it does not remove dependents.
Drop bottom-up: association / interface → derived views → base views → wrappers →
datasources → folders → database.

| Substring | Statement | Meaning |
|---|---|---|
| `There are some elements that depend on this one` | `DROP VIEW`, `DROP DATASOURCE`, `DROP WRAPPER` | dependents exist; drop them first |
| `Some elements depend on '<tag>'` | `DROP TAG` | tag is still assigned; `ALTER TAG … REMOVE_FROM` first |
| `folder /x contains elements and can not be dropped` | `DROP FOLDER [IF EXISTS]` | empty the folder first; `IF EXISTS` does not help |
| `The database does not contain the specified view` | `DROP VIEW` without `IF EXISTS` | already gone; use `IF EXISTS` |
| `cannot be dropped because the connection was established with this database` | `DROP DATABASE` | the session is connected to it: run the drop with `--database admin` (and no `CONNECT DATABASE <db>` before it) |

### Runtime (the object exists, the query fails)

| Substring | Where | Meaning |
|---|---|---|
| `Error executing query. Total time …` + in `raw`: `[DF ROUTE] [PARSE_ERROR] … Error getting input Stream` | `SELECT` from a DF base view | the file path in the datasource `ROUTE` is wrong or unreadable on the *server* (paths are server-side) |
| `authentication error: The username or password is incorrect` | any (arrives as `error.kind: connection`) | profile password wrong — the human edits `profiles.toml` |

Silent failures worth knowing — `ok:true` and a broken object, every one of them
*verified: 9.5.1 (стенд)*:

| What creates cleanly | What is actually wrong | How you find out |
|---|---|---|
| a DF wrapper whose `OUTPUTSCHEMA` lists only some of the file's columns | its base view returns **zero rows** | `SELECT` — list every column of the file (`/denodo:datasources`) |
| `CREATE OR REPLACE VIEW` that renames or drops a column | every view above it goes to `view_status = 'INVALID'`, every association mapping it goes to `valid = false` | `GET_VIEWS(… input_retrieve_invalid_views_only = true)` and `GET_ASSOCIATIONS()` (`/denodo:views`) |
| `SET IMPLEMENTATION` over a view that does not match the interface | the contract fails on `SELECT` with `… <NAME> [INTERFACE] [ERROR]`, which names nothing else | `SELECT` through the interface view, and `view_status` — `INVALID`, or `INTERFACE_NOT_IMPLEMENTED` when there is no implementation at all |
| `ENDPOINT … PRINCIPAL` without `REFERENTIAL CONSTRAINT` | not a foreign key; clients see no relationship | `is_referential_constraint` in `GET_ASSOCIATIONS()` |
| an `ADD_TO` naming a view or column that does not exist | the tag is simply not assigned | `GET_VIEW_TAGS()` (`/denodo:catalog`) |

The shape is always the same: the statement is checked, the object is not. **Read the
object back** — that is what the Verify section of every domain skill is for.

## 2. Data Marketplace HTTP

`body` is `null` on most errors; when present it is `{code, message, status, …}`.

| `status` | `body.code` / body | When | Action |
|---|---|---|---|
| `401` | `{"status":401,"error":"Unauthorized"}` (Spring) — *T11 report* | no `Authorization` header (not reachable through the tool) | — |
| `401` | `AUTHENTICATION_SERVER_NOT_FOUND` "Server not found" | wrong `marketplace_server_id` in the profile, **or** wrong VDP password with a serverId set | fix the profile; a single registered VDP server may leave `marketplace_server_id` unset |
| `500` | `GENERIC` "Session Expired." | **more than one VDP server is registered and no server was named** — the marketplace cannot tell which catalog you mean | set `marketplace_server_id` in the profile and the tool names the server on every call; the ids are in `GET /public/api/configuration/servers`. `--param serverId=<id>` overrides the profile for one call |
| `403` | empty, on `/external-tool-servers` and other server-scoped paths | the same missing `serverId` — this family answers `403` where tags answer `500` | as above: name the server |
| `403` | empty — *T11 report* | `PUT`/`POST …/views`/`DELETE` on a tag imported from VDP (`vdpTag:true`) | imported tags are read-only here; change them in VDP (`/denodo:catalog`) |
| `404` | empty | `DELETE` of a non-existent server, element type, provider type; `GET` of an object that is gone | look the object up by name first. **When you are checking that something was deleted, `404` is the answer you wanted** — the envelope still says `ok:false` and exits `1`, so a verification script has to expect it |
| `404` | `{"status":404,"error":"Not Found","path":…}` (Spring) | wrong path | check the path under `/public/api/…` |
| `400` | `MISSING_REQUEST_PARAMETER` | a paged endpoint called without `offset`/`limit` (`…/categories/{id}/views`, `/tag-management/tags`) | add `--param offset=0 --param limit=50` |
| `409` | empty | duplicate name: tag, category, element type, provider type | find by name (`GET` list) and `PUT` instead of `POST` |
| `409` | `SERVER_DUPLICATED` — *T11 report* | duplicate external tool server name | same |
| `400` | `VALIDATE_FIELD` `{"description":"must not be null",…}` | body missing required fields (`description`, `descriptionType` on tags) | send all fields; `descriptionType` is `"TEXT"` |
| `400` | `INVALID_VDP_EXTERNAL_ELEMENT_METADATA` "The view '…' does not exist" | an association names a view the **marketplace catalog** does not have — it may well exist in VDP | synchronise the catalog (`/denodo:marketplace`), then re-run the import |
| `400` | `INVALID_VDP_EXTERNAL_ELEMENT_METADATA` "Required field 'associated_element_id' is null … association index 0" | the interface view built its association array with a `LEFT OUTER JOIN`, so an element with no associations carries one all-null record | `INNER JOIN` plus a `UNION ALL` branch with a NULL array — `/denodo:marketplace` |
| `400` | `INVALID_EXTERNAL_ELEMENT_INTERFACE_VIEW` "expected type external_element_association_array_type" | the association array type was renamed; the marketplace matches the contract's type name literally | keep the names from `…/vql-metadata` |
| `400` | `INVALID_EXTERNAL_TOOL_SERVER` — *T11 report* | `…/changes` on a CUSTOM server (endpoint is for Tableau/Power BI only) | use `synchronize`, not `changes` |
| `400` | Spring `problemDetail` with `MethodArgumentTypeMismatchException` | non-numeric id in the path (`/tags/None`) | you never resolved the id; `GET` the list and take `id` |
| `500` | `GENERIC` "Incorrect number of deleted tuples" | `DELETE` of an already-deleted tag, or of an imported VDP tag | tag is gone (or read-only); do not retry |
| `500` | `GENERIC` "Cannot invoke \"java.lang.Long.longValue()\" because \"elementId\" is null" | `null` inside the id list of a body | resolve every id before the call |
| `500` | `GENERIC` "Error executing query…" (`view-details`) | `databaseName` does not exist in VDP | fix the database name |
| `200` | `[<viewId>, …]` from `POST /tags/{id}/views` or `/categories/…` | ids that were **not** assigned: unknown view, or already assigned | success is `[]`; unknown ids are not errors for the server |
| `200` | `{"id":null,"inLocal":false,"inVDP":true}` from `GET view-details` | the view exists in VDP but is not synchronised into the marketplace, so it has no id to assign anything to | synchronise the catalog first — `/denodo:marketplace` covers which call and which conflict mode, and both are choices a human confirms |

Repeated `DELETE` is not idempotent across object types: `500` for tags, `200` for
categories, `404` for element types and servers. Look up by name before deleting
instead of relying on the status.

## 3. Client-side (`error.kind`)

| `kind` | Exit | Message | Action |
|---|---|---|---|
| `usage` | 2 | `no environment given: pass --env <profile> or set DENODO_ENV` | add `--env` |
| `usage` | 2 | `give exactly one input: a .vql file, '-' for stdin, or -e VQL` | one input only |
| `usage` | 2 | `no VQL statements to run` | the file is empty or only comments |
| `config` | 2 | `profiles file not found: …` | the human runs `env init` (see SKILL.md, *No profile*) |
| `config` | 2 | `profile 'x' not found in …; available profiles: …` | use a listed name, or the human runs `env init` |
| `config` | 2 | `takes its password from environment variable X, which is not set` | the human exports the variable in the shell that runs Claude Code — not you, not in the chat |
| `config` | 2 | `lacks required field(s)` / `unknown field(s)` / `cannot parse` | the human edits `profiles.toml` |
| `config` | 2 | profile has no `marketplace_url` (from `api`) | the human adds `marketplace_url` to the profile |
| `connection` | 1 | `connection to server at "host", port N failed: Connection refused` | VDP not running or wrong host/port; `env check` |
| `connection` | 1 | `<urlopen error [Errno 61] Connection refused>` (from `api`) | marketplace not running or wrong `marketplace_url` |
| `connection` | 1 | `authentication error: The username or password is incorrect` | wrong password in the profile |
| `refused` | 2 | `profile 'x' is marked production and … destructive …; nothing was executed` | show `error.destructive` to the human; flag only after their yes |
| `environment` | 3 | `the Denodo driver stack is not importable` + `hint` | show the hint verbatim; the launcher normally handles this |
