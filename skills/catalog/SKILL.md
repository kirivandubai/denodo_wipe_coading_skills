---
name: catalog
description: Use when creating or changing the containers of a Denodo 9.5 catalog — a virtual database (CREATE DATABASE, description, CHARSET, authentication), a folder or a folder tree (CREATE FOLDER, ALTER FOLDER, rename or move, drop with CASCADE), or a VDP tag (CREATE TAG, ALTER TAG, assign a tag to views and columns, list where a tag is assigned, "mark this column as PII in VDP"). Not for Data Marketplace tags or categories — that is /denodo:marketplace; not for views themselves.
---

# Databases, folders and VDP tags

This skill is about the three container objects of Virtual DataPort: the **database**, the
**folder** inside it and the **VDP tag** that is attached to views and columns. Everything
here is VQL on port 9996. If you need a *marketplace* tag or category (REST, port 9090),
go to `/denodo:marketplace` — a "tag" alone does not say which one the human means. Data
sources, wrappers and base views live in `/denodo:datasources`; derived and interface
views in `/denodo:views`. The working loop, the naming defaults and the safety rule are in
`/denodo:vql`; apply files with `/denodo:execute`.

Build order: **database → folders (parent before child) → objects → tags**. A tag is
attached to views that must already exist.

## Templates

### Database

```sql
-- verified: 9.5.1 (стенд, 2026-09-10)
CREATE OR REPLACE DATABASE sales_analytics 'Sales data products' CHARSET DEFAULT;
```

The description literal comes **before** `CHARSET`; the other way round is
`Syntax error: Exception parsing query near '''`. Everything after the description is
optional. `CHARSET UNICODE` when identifiers must carry non-ASCII characters;
`RESTRICTED` for ASCII only; `DEFAULT` for the server setting. No `AUTHENTICATION` clause
means local authentication, the same as every database created from Design Studio without
LDAP. `CREATE OR REPLACE DATABASE` keeps the objects inside.

### Folders

```sql
-- verified: 9.5.1 (стенд, 2026-09-10)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE FOLDER '/01 - connectivity' DESCRIPTION 'data sources, wrappers, base views';
CREATE OR REPLACE FOLDER '/02 - integration';
CREATE OR REPLACE FOLDER '/03 - business entities';
CREATE OR REPLACE FOLDER '/03 - business entities/customer' DESCRIPTION 'Customer 360 views';
CREATE OR REPLACE FOLDER '/06 - associations';
```

The path is a quoted literal starting with `/`. `DESCRIPTION` takes the literal **without
`=`** (the tag below is the opposite). A parent must exist before its child:
`Cannot create folder /x/y: parent not found`. `CONNECT DATABASE` first in the file, or
`--database` on the command — folders live in a database and the profile's default is
usually `admin`. Re-applying a folder statement rewrites its description: a statement
without `DESCRIPTION` clears it, so keep the description in the file.

### Tags, with their assignments

One tag per statement; each carries its own targets. Read the targets first
(`vql desc --env dev --database <db> <view>`): a target that `DESC` did not show is not
listed — ask the human about it — because a misspelled or missing target is accepted
silently (see Verify). Check the tag too: `vql desc --env dev <tag> --type tag` fails
with `Error loading tag` when it does not exist yet. If it does exist, `CREATE OR REPLACE`
rewrites its description for every database that uses it — that is a change to an
existing object, show it and get a yes first.

```sql
-- verified: 9.5.1 (стенд, 2026-09-10)
CREATE OR REPLACE TAG pii
    DESCRIPTION = 'Personal data, GDPR scope'
    ADD_TO      ( VIEWS () COLUMNS ( sales_analytics.customer.email, sales_analytics.customer.phone ) )
    REMOVE_FROM ( VIEWS () COLUMNS () );

CREATE OR REPLACE TAG finance_sensitive
    DESCRIPTION = 'Contains revenue figures'
    ADD_TO      ( VIEWS ( sales_analytics.order_summary ) COLUMNS () )
    REMOVE_FROM ( VIEWS () COLUMNS () );
```

- `DESCRIPTION =` **with `=`** — `DESCRIPTION 'text'` is a syntax error near `'`.
- Both blocks, each with both sections, always — even empty. Dropping `REMOVE_FROM` or
  `COLUMNS ()` is `Exception parsing query near ''`.
- Views and columns are **database-qualified**: `db.view` and `db.view.column`. A bare
  `view.column` is a syntax error near `)`.
- One statement does creation and assignment, and it is idempotent: re-applying keeps
  the assignments already there and adds the listed ones. Prefer it over
  `CREATE TAG` + `ALTER TAG`: `ALTER` is a change to an existing object and is marked
  destructive by the tool.
- Tags are **server-wide**, not per database. `pii` created while connected to one
  database is the same `pii` everywhere; `LIST TAGS` shows all of them. The assignments
  are what carry the database name, so a tag file needs no `CONNECT DATABASE`.
- Several at once: `CREATE OR REPLACE TAGS ( a DESCRIPTION = '…' ADD_TO (…) REMOVE_FROM (…), b … );`

The other way to attach a tag is `TAGS (pii)` inside `CREATE OR REPLACE VIEW` — that
belongs to the view's file (`/denodo:views`).

## What you need before filling the template

| Slot | Where it comes from |
|---|---|
| Database name, description | the human; name per conventions (`sales_analytics`, no environment suffix) |
| `CHARSET` | `DEFAULT` unless the human says identifiers need non-ASCII characters → `UNICODE` |
| Authentication | omit: no clause means the server's global authentication settings, which is what Design Studio's "Global authentication settings" does — if the server is on LDAP globally, the database follows. A per-database `AUTHENTICATION LDAP` needs an LDAP data source and six DN patterns; if the human asks for that, ask for those values, do not invent them. "Same login as everyone else" means omit: `GET_DATABASES()` shows what the other databases do |
| Folder tree | `.denodo/conventions.md` if the project has one, else the layer folders from `/denodo:vql` |
| Folder for a new tag's targets | not needed: tags have no folder |
| Tag name, description | the human; name is the concept (`pii`, `gdpr`), lowercase unless quoted |
| Tag targets | the exact `db.view` / `db.view.column` — read them first: `vql desc --env dev --database <db> <view>` |
| Which "tag" | VDP tag = visible in Design Studio and `LIST TAGS`; marketplace tag = visible in the Data Marketplace UI. When the request does not say, ask |

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
| Folder tree | `SELECT name, type, subtype, folder, description FROM GET_ELEMENTS() WHERE input_database_name = '<db>' AND type <> 'type'` — `folder` is the parent path (`/` for top level), the full path is `folder + '/' + name`. Types: `folder`, `datasource`, `wrapper`, `view` (subtype `base`, `derived`, `interface`), `association`, `storedProcedure`; rows with type `type` are server-internal registers, not your objects |
| What is inside a folder before a drop | the same query **without a type filter**, `WHERE folder LIKE '/<path>%'` — a type filter hides exactly the object you did not think of |
| One folder | `vql desc --env dev --database <db> "'/03 - business entities'" --type folder` → `name, path, description` |
| Tag | `vql desc --env dev <tag> --type tag` → `name='pii' description=…` (description only) |
| Tag assignments | `SELECT database_name, view_name, column_name, tag_name FROM GET_VIEW_TAGS() WHERE input_database_name = '<db>'` — `column_name` is `null` for a whole-view assignment |
| Where a tag is used anywhere on the server | the same `SELECT` with `WHERE tag_name = '<tag>'` — the question to answer before replacing or dropping a tag |

**Always read `GET_VIEW_TAGS()` after assigning.** An `ADD_TO` that names a view or a
column that does not exist is accepted without an error and is silently not recorded —
*verified: 9.5.1 (стенд, 2026-09-09)*. A typo in a column name looks exactly like
success until you read the assignments back.

`DESC VQL TAG` shows the tag without its assignments, and `DESC VQL DATABASE` lists the
contents without a `CREATE DATABASE` line — neither tells you what you want here.
`LIST FOLDERS` does not exist; `GET_ELEMENTS()` is the folder listing.

## Common mistakes

| You wrote | Server says | Fix |
|---|---|---|
| `CREATE DATABASE x CHARSET UNICODE 'desc'` | `Syntax error … near '''` | description first, then `CHARSET` |
| `CREATE FOLDER '/x' DESCRIPTION = 'd'` | `Syntax error … near '='` | folders: no `=` |
| `CREATE TAG t DESCRIPTION 'd'` | `Syntax error … near '''` | tags: `DESCRIPTION = 'd'` |
| `CREATE FOLDER '/a/b'` with no `/a` | `Cannot create folder /a/b: parent not found` | create `/a` first |
| `CREATE FOLDER` while connected to `admin` | folder lands in `admin` | `CONNECT DATABASE` first, or `--database` |
| `ADD_TO ( VIEWS ( v ) COLUMNS () )` without `REMOVE_FROM` | `Exception parsing query near ''` | add `REMOVE_FROM ( VIEWS () COLUMNS () )` |
| `COLUMNS ( customer.email )` | `Syntax error … near ')'` | `COLUMNS ( sales_analytics.customer.email )` |
| `COLUMNS ( db.customer.emial )` | nothing — accepted | read `GET_VIEW_TAGS()`; fix the name; re-apply |
| `DROP FOLDER '/x'` with content | `folder /x contains elements and can not be dropped` | `DROP FOLDER IF EXISTS '/x' CASCADE` — after the human confirms; it takes subfolders and every object in them |
| `DROP TAG t` while assigned | `Some elements depend on 't'` | `DROP TAG t CASCADE` — after the human confirms; it removes every assignment |
| `WHERE input_tag_names = 'pii'` on `GET_VIEW_TAGS()` | `Unable to execute condition using types 'text' and 'array'` | filter on `tag_name`, or on `input_database_name` |
| `WHERE database_name = …` on `GET_DATABASES()` | `Field not found 'database_name'` | the column is `db_name` |

Dropping is the human's call — `/denodo:vql`. `CASCADE` makes a drop shorter, not safer:
show what is inside the folder (`GET_ELEMENTS()`) or which views carry the tag
(`GET_VIEW_TAGS()`) before you ask.
