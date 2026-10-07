# Folders — full syntax

Source: Virtual DataPort VQL Guide 9.5, "Creating Folders". Folders hold data sources,
stored procedures, wrappers, views and web services. They do not make names unique: two
elements in one database cannot share a name even in different folders.

Every folder statement runs **inside a database**: `CONNECT DATABASE <db>;` first in the
file, or `--database <db>` on the command. Paths are quoted literals, start with `/`, may
contain spaces, digits and dashes, and match case-insensitively.

## CREATE FOLDER

```sql
-- verified: 9.5.1 (live, 2026-09-09)
CREATE [ OR REPLACE ] FOLDER '/<path>' [ DESCRIPTION '<description>' ]
```

- `DESCRIPTION` takes the literal directly. `DESCRIPTION = '…'` is
  `Syntax error: Exception parsing query near '='`.
- The parent must exist: `Cannot create folder /a/b: parent not found`. Create top-down,
  one statement per level.
- `CREATE OR REPLACE FOLDER` on an existing folder keeps its subfolders and elements and
  **replaces the description with what the statement says** — a statement without
  `DESCRIPTION` clears it. Keep the description in the file, not only on the server.
  `CREATE FOLDER` without `OR REPLACE` on an existing one:
  `Error creating folder: /a already exists`.

## ALTER FOLDER

```sql
-- verified: 9.5.1 (live, 2026-09-09) — DESCRIPTION, RENAME (same parent and across parents, with DESCRIPTION), MOVE VIEW
ALTER FOLDER '/<path>' DESCRIPTION '<description>';
ALTER FOLDER '/<path>' RENAME '/<new path>' [ DESCRIPTION '<description>' ];
ALTER FOLDER '/<target path>' MOVE VIEW <view>;
```

```sql
-- unverified: 9.5 documentation only
ALTER FOLDER '/<target path>' MOVE <element> <name>;
ALTER FOLDER '/<target path>' COPY <element> <old name> AS <new name>;

<element> ::= DATASOURCE <type> | WRAPPER <type> | TABLE | VIEW | PROCEDURE | WEBSERVICE
<type>    ::= CUSTOM | DF | ESSBASE | JDBC | JSON | LDAP | MONGODB | ODBC | OLAP
            | SALESFORCE | SAPBWBAPI | SAPERP | WS | XML
```

- `RENAME` with a different parent **moves** the folder:
  `ALTER FOLDER '/03 - business entities/budget' RENAME '/02 - integration/budget'`.
  The target parent must exist.
- `MOVE` is written on the **destination** folder and names the element:
  `ALTER FOLDER '/02 - integration' MOVE VIEW order_summary`. `TABLE` is a base view.
- Moving an element does not change its name and does not break dependents.
- `ALTER FOLDER`: `vql plan` says whether it waits for the human's yes (`/denodo:vql`).

## DROP FOLDER

```sql
-- verified: 9.5.1 (live, 2026-09-09)
DROP FOLDER [ IF EXISTS ] '/<path>' [ CASCADE ]
```

- Without `CASCADE`, a folder with subfolders or elements is refused:
  `error dropping folder: folder /x contains elements and can not be dropped`.
  `IF EXISTS` does not change that — it only silences the "does not exist" error.
- With `CASCADE`, the folder, its subfolders and **every element in them** are dropped.
- Two safe ways to empty a tree: drop the leaves first, bottom-up, one statement per
  folder; or `CASCADE` after showing the human what `GET_ELEMENTS()` lists under the path.
  `IF EXISTS … CASCADE` on a path that does not exist is a no-op.

## Reading folders back

```sql
-- verified: 9.5.1 (live, 2026-10-07)
DESC FOLDER '/<path>';                            -- name, path, description
DESC VQL FOLDER '/<path>';                        -- CREATE OR REPLACE FOLDER … as the server writes it

SELECT name, type, subtype, folder, description
FROM GET_ELEMENTS()
WHERE input_database_name = '<db>' AND type <> 'type';
```

`type` values in a database on 9.5.1: `folder`, `datasource`, `wrapper`, `view` (subtype
`base`, `derived`, `interface`, `materialized`, `metric`), `association`, `storedProcedure`,
`webService`, and `type` — registers and arrays, `folder = null`: your own `CREATE TYPE`s and
the `_register_…` / `_array_register_…` types a view with `NEST` or `REGISTER` leaves behind
(`/denodo:views`). Folder descriptions read back as `null` when unset, view descriptions as `''`.

Server-generated VQL (`DESC VQL DATABASE`) lists folders under `# FOLDERS` in creation
order, which is the order to reuse in a file.
