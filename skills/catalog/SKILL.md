---
name: catalog
description: Use when creating or changing the structure of a Denodo 9.5 catalog — a virtual database (CREATE DATABASE, description, CHARSET, authentication), a folder or a folder tree (CREATE FOLDER, ALTER FOLDER, rename or move, drop with CASCADE), or a VDP tag (CREATE TAG, ALTER TAG, assign a tag to views and columns, list where a tag is assigned, "mark this column as PII in VDP"). Not for Data Marketplace tags or categories — that is /denodo:marketplace; not for views themselves.
---

# Databases, folders and VDP tags

This skill is about the three objects that give a Virtual DataPort catalog its structure:
the **database**, the **folder** inside it and the **VDP tag** that is attached to views
and columns. Everything here is VQL. A *marketplace* tag or category (REST) is
`/denodo:marketplace`; when the request does not say which, see the *Which "tag"* row below.
Data sources, wrappers and base views live in `/denodo:datasources`; derived and interface
views in `/denodo:views`. The working loop, the naming defaults and the safety rule are in
`/denodo:vql`; apply files with `/denodo:execute`.

## Templates

### Database

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CREATE OR REPLACE DATABASE sales_analytics 'Sales data products' CHARSET DEFAULT;
```

Everything after the description is optional. `CHARSET RESTRICTED`: Design Studio takes
names of `a`-`z`, digits and `_` only (capitals become lowercase); `UNICODE`: any character —
capitals, dashes, spaces, non-ASCII; `DEFAULT`: the server setting. Only Design Studio is
affected. `CREATE OR REPLACE DATABASE` keeps the objects inside.

### Folders

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE FOLDER '/01 - connectivity' DESCRIPTION 'data sources, wrappers, base views';
CREATE OR REPLACE FOLDER '/02 - integration';
CREATE OR REPLACE FOLDER '/03 - business entities';
CREATE OR REPLACE FOLDER '/03 - business entities/customer' DESCRIPTION 'Customer 360 views';
CREATE OR REPLACE FOLDER '/06 - associations';
```

The path is a quoted literal starting with `/`. Folders take `DESCRIPTION 'x'`, tags
`DESCRIPTION = 'x'`. `CONNECT DATABASE` first in the file, or `--database` on the command —
folders live in a database and the profile's default is usually `admin`. Re-applying a folder
statement rewrites its description: a statement without `DESCRIPTION` clears it, so keep the
description in the file.

### Tags, with their assignments

VDP tags need the Enterprise Plus bundle (`env check --env dev` → `features.enterprise_plus`).
A user who is not an administrator needs the role `manage_tags` to create, change or drop a
tag, and `assign_tags` plus `METADATA` on the view — or admin rights on its database — to
assign one. Either refusal is the administrator's to fix: stop and report it.

Read the targets first (`vql desc --env dev --database <db> <view>`): a target that `DESC`
did not show is not listed — ask the human about it — because a misspelled or missing target
is accepted silently (see Verify). Check the tag too: `vql desc --env dev <tag> --type tag`
fails with `Error loading tag` when it does not exist yet. If it does exist, `CREATE OR REPLACE`
rewrites its description for every database that uses it — that is a change to an
existing object, show it and get a yes first. Tagging a view you did not create in this session
waits for a yes (`/denodo:vql`), and so does a tag a policy names (below); `vql plan` flags both.

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CREATE OR REPLACE TAG pii
    DESCRIPTION = 'Personal data, GDPR scope'
    ADD_TO      ( VIEWS () COLUMNS ( sales_analytics.customer.email, sales_analytics.customer.phone ) )
    REMOVE_FROM ( VIEWS () COLUMNS () );

CREATE OR REPLACE TAG finance_sensitive
    DESCRIPTION = 'Contains revenue figures'
    ADD_TO      ( VIEWS ( sales_analytics.order_summary ) COLUMNS () )
    REMOVE_FROM ( VIEWS () COLUMNS () );
```

- One statement creates the tag and assigns it, and re-applying it keeps the assignments
  already there. On a tag that already exists, `ALTER TAG … ADD_TO … REMOVE_FROM ( VIEWS ()
  COLUMNS () )` adds without rewriting its description.
- Tags are **server-wide**, not per database. `pii` created while connected to one
  database is the same `pii` everywhere; `LIST TAGS` shows all of them. The assignments
  are what carry the database name, so a tag file needs no `CONNECT DATABASE`.
- Several at once: `CREATE OR REPLACE TAGS ( a DESCRIPTION = '…' ADD_TO (…) REMOVE_FROM (…), b … );`

**A view with a file in the project carries its tags in that file**: `TAGS ( pii )` on the
field in its `CREATE OR REPLACE VIEW` or `CREATE TABLE` (`/denodo:views`, `/denodo:security`).
Re-applying the file without them removes every assignment, whichever statement made it — so
`ADD_TO` is for views that have no file you apply. A view over a `UNION` refuses field
properties (`The field properties can only be specified for derived fields`); its file gets an
`ALTER TAG … ADD_TO` for its columns, right after the view — *verified: 9.5.1 (live,
2026-10-06)*.

**A tag that a global security policy names is not a label.** Put on a column, it masks or
filters that column for the policy's audience; taken off — or lost when the view's file is
re-applied without it — it lifts the restriction. Before assigning, removing or dropping an
existing tag, ask the server:
`SELECT global_security_policy_name FROM GET_GLOBAL_SECURITY_POLICIES_TAGS() WHERE tag_name = '<tag>'`.
A row means the change is `/denodo:security`'s, and the human's yes comes first.

The tag the Denodo MCP Server shows views by (`mcp` in its shipped configuration) — which
views carry it, and why an agent does not see a view — is `/denodo:semantics`.

### One tag on many columns

"Every column that holds an email", across a database, is a list first (`/denodo:vql`, **Many
objects at once**). Two reads give it whole — every field, and for every field of a derived view
each column under it that its value comes from, down to the base view:

```sql
-- verified: 9.5.1 (live, 2026-10-07)
SELECT view_name, column_name, column_vdp_type
  FROM GET_VIEW_COLUMNS() WHERE input_database_name = 'sales_analytics';

SELECT e.name AS view_name, d.column_name, d.dependency_name, d.dependency_column_name
  FROM GET_ELEMENTS() AS e
       INNER JOIN COLUMN_DEPENDENCIES() AS d
       ON (d.input_view_database_name = e.database_name AND d.input_view_name = e.name)
 WHERE e.input_database_name = 'sales_analytics' AND e.input_type = 'views'
   AND e.subtype = 'derived' AND d.view_name = e.name
   AND d.dependency_column_name IS NOT NULL;
```

- A name pattern finds candidates, not the list. A field renamed on the way up
  (`notify_to` over `email`) or one that carries several (`handle`, a union of emails and phone
  numbers) is on the list by its lineage. A field that matches and holds something else — an
  `email_verified` flag, an `email_bounce_count` — is a row with "none" and why: look at its
  values. Whether a column falls inside what the human named is theirs to say — a question row.
- Each row says where its assignment goes: into the view's file when the project applies one
  (`TAGS`, or the `ALTER TAG` after a union view) — whoever created the view, or its next apply
  takes the tag off — and into one `ALTER TAG … ADD_TO` file for the views that have none. Which
  rows wait: `/denodo:vql`. The tag itself first, in a file of its own: the views' files name it.
- One `CREATE OR REPLACE TAG … ADD_TO` over your own views' columns is the shortcut that loses
  them: the next apply of any of those files takes its tags off, and nothing reports it.
- An assignment belongs to one view: a tag on a base view's column does not appear in
  `GET_VIEW_TAGS()` for the views that pass the column through — a report that reads the tags
  view by view needs each of those columns on the list (a security policy masks through them
  anyway: `/denodo:security`) — *verified: 9.5.1 (live, 2026-10-06)*.
- The check: the Verify read of `GET_VIEW_TAGS()` with `tag_name = '<tag>'`, against the list
  row for row — a misnamed column is simply absent.

## What you need before filling the template

| Slot | Where it comes from |
|---|---|
| Database name, description | the human; name per conventions (`sales_analytics`, no environment suffix) |
| `CHARSET` | `DEFAULT` unless the human says names need anything beyond lowercase letters, digits and `_` → `UNICODE` |
| Authentication | omit: no clause means the server's global authentication settings, which is what Design Studio's "Global authentication settings" does — if the server is on LDAP globally, the database follows. Per-database LDAP: `references/database.md` — ask for every value. "Same login as everyone else" means omit: `GET_DATABASES()` shows what the other databases do |
| Folder tree | `.denodo/conventions.md` if the project has one; else, in a database that already holds objects, the folders it has (the query below); else the layer folders from `/denodo:vql` |
| Folder for a new tag's targets | not needed: tags have no folder |
| Tag name, description | the human; name is the concept (`pii`, `gdpr`), lowercase unless quoted |
| Tag targets | the exact `db.view` / `db.view.column` — read them first: `vql desc --env dev --database <db> <view>` |
| Which "tag" | VDP tag = `CREATE TAG`, visible in Design Studio and `LIST TAGS`; marketplace tag = created in the Data Marketplace (an imported VDP tag shows there too, read-only). When the request does not say, ask |

Do not ask for VCS, credentials vault, data-movement or cache settings — they are not
part of creating a database and have server defaults. They are in the reference if the
human brings them up.

## Reference

- `references/database.md` — full `CREATE DATABASE` / `ALTER DATABASE` options, what is
  verified and what only comes from the documentation.
- `references/folders.md` — `ALTER FOLDER` (description, rename, move a folder, move or
  copy an element), `DROP FOLDER … CASCADE`.
- `references/tags.md` — `CREATE TAGS`, `ALTER TAG`, `DROP TAG … CASCADE`, `DROP TAGS`,
  `GET_VIEW_TAGS()` columns.

## Verify

Success of the statement is not success of the object. After applying, read back:

| Object | Read-back |
|---|---|
| Database | `vql desc --env dev <db> --type database` → `name, description`; settings: `SELECT db_name, description, charset, authentication FROM GET_DATABASES() WHERE db_name = '<db>'` |
| Folder tree | `SELECT name, type, subtype, folder, description FROM GET_ELEMENTS() WHERE input_database_name = '<db>' AND type <> 'type'` — `folder` is the parent path, in lowercase; the full path is `'/' + name` at the top level (`folder = '/'`) and `folder + '/' + name` below it, so compare paths with `lower()`. The `type` values: `references/folders.md` |
| What is inside a folder before a drop | the same query **without a type filter**: `WHERE input_database_name = '<db>' AND (lower(folder) = lower('/<path>') OR lower(folder) LIKE lower('/<path>/%'))` — `folder` comes back in lowercase, so `folder LIKE '/Sales Data%'` misses a folder named with capitals; a type filter hides exactly the object you did not think of |
| One folder | `vql desc --env dev --database <db> "'/03 - business entities'" --type folder` → `name, path, description` |
| Tag | `vql desc --env dev <tag> --type tag` → `name='pii' description=…` (description only; `DESC VQL TAG` omits the assignments too) |
| Tag assignments | `SELECT database_name, view_name, column_name, tag_name FROM GET_VIEW_TAGS() WHERE input_database_name = '<db>'` — `column_name` is `null` for a whole-view assignment |
| Where a tag is used anywhere on the server | the same `SELECT` with `WHERE tag_name = '<tag>'` — the question to answer before replacing or dropping a tag |

**Always read `GET_VIEW_TAGS()` after assigning.** An `ADD_TO` that names a view or a
column that does not exist is accepted without an error and is silently not recorded —
*verified: 9.5.1 (live, 2026-09-09)*. A typo in a column name looks exactly like
success until you read the assignments back.

## Common mistakes

| You wrote | Server says | Fix |
|---|---|---|
| `CREATE DATABASE x CHARSET UNICODE 'desc'` | `Syntax error … near '''` | description first, then `CHARSET` |
| `CREATE FOLDER '/x' DESCRIPTION = 'd'` | `Syntax error … near '='` | folders: no `=` |
| `CREATE TAG t DESCRIPTION 'd'` | `Syntax error … near '''` | tags: `DESCRIPTION = 'd'` |
| `CREATE FOLDER '/a/b'` with no `/a` | `Cannot create folder /a/b: parent not found` | create `/a` first |
| `CREATE FOLDER` while connected to `admin` | folder lands in `admin` | `CONNECT DATABASE` first, or `--database` |
| `ADD_TO ( VIEWS ( v ) COLUMNS () )` without `REMOVE_FROM`, or without an empty `VIEWS ()` / `COLUMNS ()` | `Exception parsing query near ''` | both blocks, each with both sections, even empty: add `REMOVE_FROM ( VIEWS () COLUMNS () )` |
| `COLUMNS ( customer.email )` | `Syntax error … near ')'` | `COLUMNS ( sales_analytics.customer.email )` |
| `COLUMNS ( db.customer.emial )` | nothing — accepted | read `GET_VIEW_TAGS()`; fix the name; re-apply |
| `DROP FOLDER '/x'` with content | `folder /x contains elements and can not be dropped` | `DROP FOLDER IF EXISTS '/x' CASCADE` — after the human confirms; it takes subfolders and every object in them |
| `DROP TAG t` while assigned, or named by a global security policy | `Some elements depend on 't'` | `DROP TAG t CASCADE` — after the human confirms; it removes every assignment **and deletes every policy that names the tag** (`/denodo:security`) |
| `WHERE input_tag_names = 'pii'` on `GET_VIEW_TAGS()` | `Unable to execute condition using types 'text' and 'array'` | filter on `tag_name`, or on `input_database_name` |
| `WHERE database_name = …` on `GET_DATABASES()` | `Field not found 'database_name'` | the column is `db_name` |
