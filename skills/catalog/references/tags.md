# VDP tags — full syntax

Source: Virtual DataPort VQL Guide 9.5, "Tags". A VDP tag is a server-wide label with an
optional description, attached to views and to columns of views. It is a different object
from a Data Marketplace tag (REST, `/denodo:marketplace`); the marketplace can *import*
VDP tags, and the imported copies are read-only there.

Tags are not per database: `CREATE TAG` while connected to any database creates the same
global tag, and `LIST TAGS` shows all of them. The assignments carry the database name.

## CREATE TAG / CREATE TAGS

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
CREATE [ OR REPLACE ] TAG <name>
    [ DESCRIPTION = '<description>' ]
    [ ADD_TO      ( VIEWS ( <db>.<view> [, …] ) COLUMNS ( <db>.<view>.<column> [, …] ) )
      REMOVE_FROM ( VIEWS ( <db>.<view> [, …] ) COLUMNS ( <db>.<view>.<column> [, …] ) ) ]

CREATE [ OR REPLACE ] TAGS ( <tag definition> [, <tag definition> ]* )
```

- `DESCRIPTION =` with the equals sign. `DESCRIPTION 'x'` is
  `Syntax error: Exception parsing query near '''`. A tag may have no description.
- Assignments: **both** blocks, **both** sections in each, even empty —
  `ADD_TO ( VIEWS () COLUMNS ( … ) ) REMOVE_FROM ( VIEWS () COLUMNS () )`. Any block or
  section missing: `Syntax error: Exception parsing query near ''`.
- Targets are database-qualified. `COLUMNS ( customer.email )` without the database:
  `Syntax error: Exception parsing query near ')'`. Base views (`CREATE TABLE`) are
  addressed the same way as views.
- Names: lowercase unquoted; a quoted name (`"SSN"`, `"Mixed_Case"`) keeps its case.
  `CREATE TAG` on an existing name: `Invalid tag name: already exists`.
- `CREATE OR REPLACE TAG` on an existing tag updates the description and **keeps the
  existing assignments**; the `ADD_TO` list is added to them. This makes one statement
  with `ADD_TO` both the creation and the idempotent re-apply.
- **A target that does not exist is accepted silently** — no error, and the assignment
  is not recorded. `ADD_TO ( VIEWS ( db.ghost ) COLUMNS () )` returns success. Read
  `GET_VIEW_TAGS()` after every assignment.

## ALTER TAG

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
ALTER TAG <name>
    [ DESCRIPTION = '<description>' ]
    [ ADD_TO ( VIEWS ( … ) COLUMNS ( … ) ) REMOVE_FROM ( VIEWS ( … ) COLUMNS ( … ) ) ]
```

Same rules as `CREATE TAG`. `REMOVE_FROM` with a target detaches the tag from it:
`ALTER TAG pii ADD_TO ( VIEWS () COLUMNS () ) REMOVE_FROM ( VIEWS () COLUMNS ( db.v.email ) )`.
`ALTER` is a change to an existing object: human's confirmation first, and the tool
refuses it on a production profile without `--allow-destructive`. There is no
`ALTER VIEW … TAGS` or `ALTER VIEW … ADD TAGS` — the tag side is the only ALTER path;
the view side is `TAGS ( <tag> [, …] )` inside `CREATE OR REPLACE VIEW`.

## DROP TAG / DROP TAGS

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
DROP TAG  [ IF EXISTS ] <name> [ CASCADE ]
DROP TAGS [ IF EXISTS ] ( <name> [, <name> ]* ) [ CASCADE ]
```

- A tag with assignments is refused without `CASCADE`: `Some elements depend on '<name>'`.
  `CASCADE` removes the tag and every assignment; they cannot be recreated from the tag
  alone, so list them (`GET_VIEW_TAGS()`) before asking the human.
- `IF EXISTS` on a name that does not exist is a no-op, also inside `DROP TAGS`.
- A tag imported into the Data Marketplace disappears there on the next
  `tags/vdp/synchronize` — that call is `/denodo:marketplace`'s destructive one.

## Reading tags back

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
LIST TAGS;                                        -- name, all tags on the server
DESC TAG <name>;                                  -- one cell: name='pii' description=…
DESC VQL TAG <name>;                              -- CREATE OR REPLACE TAG … without assignments

SELECT database_name, view_name, column_name, tag_name
FROM GET_VIEW_TAGS()
WHERE input_database_name = '<db>';               -- everything tagged in one database

SELECT database_name, view_name, column_name, tag_name
FROM GET_VIEW_TAGS()
WHERE tag_name = 'pii';                           -- everywhere one tag is assigned
```

`GET_VIEW_TAGS()` columns: `input_database_name`, `input_view_name`, `input_column_name`,
`input_tag_names` (an **array** — `WHERE input_tag_names = 'pii'` fails with `Unable to
execute condition using types 'text' and 'array'`; filter on `tag_name` instead),
`database_name`, `view_name`, `column_name` (`null` for a whole-view assignment),
`tag_name`. Without a `WHERE` it returns every assignment on the server.

`DESC TAG` fails on a tag that does not exist (`Error loading tag '<name>'`), which
makes it a cheap existence check before deciding between `CREATE OR REPLACE TAG` and
touching someone else's tag.
