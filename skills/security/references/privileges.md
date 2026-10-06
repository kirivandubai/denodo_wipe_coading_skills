# Roles, users and privileges — full syntax and measured behaviour

Source: Virtual DataPort VQL Guide 9.5, "Creating Databases, Users, Roles and Access
Privileges", and the Administration Guide, "Databases, Users and Access Rights"; rows marked
*verified* were run on 9.5.1. Users and roles are server-wide. There is no `GRANT … TO`
statement of its own: privileges are clauses of `CREATE`/`ALTER ROLE`, `CREATE`/`ALTER USER`
(`GRANT … ON`) and `CREATE`/`ALTER DATABASE` (`GRANT … TO`).

## Roles

```sql
-- verified: 9.5.1 (live, 2026-10-01)
CREATE [ OR REPLACE ] ROLE <name> [ '<description>' ]
    [ GRANT <database privileges> ON <db> ]*
    [ GRANT <view privileges> ON <db>.<view> ]*
    [ GRANT ROLE <role> [, <role> ]* ]

ALTER ROLE <name> [ '<description>' ]
    [ GRANT … | REVOKE … ]*
```

- **`CREATE OR REPLACE ROLE` over an existing role adds; it never takes away.** Re-declared
  with fewer `GRANT`s, the role kept every privilege it had and every user that held it;
  the new `GRANT`s were added — *verified: 9.5.1 (live, 2026-10-01)*. A role's file is
  therefore not its state: deleting a `GRANT` line from it revokes nothing. Revoking is
  `ALTER ROLE <name> REVOKE EXECUTE ON <db>` (or `… ON <db>.<view>`); a list works the same
  way as in a grant: `REVOKE CONNECT, EXECUTE ON <db>` — *verified: 9.5.1 (live, 2026-10-01)*.
- `DESC VQL ROLE <name>` returns `DROP ROLE IF EXISTS <name>; CREATE ROLE …` with every
  grant — read it, never apply it as it is: the `DROP` takes the role from every user.
- Role inheritance: `GRANT ROLE a, b` inside a role. A user's privileges are the **union** of
  their own and all their roles' — a role never narrows what another role or a direct grant
  gives.
- `ALLOWED_PATHS ( '<folder>', … )` limits a role to folders (documentation only).

## Users

```sql
-- verified: 9.5.1 (live, 2026-10-06)
ALTER USER <name> GRANT ROLE <role> [, <role> ]*;
ALTER USER <name> REVOKE ROLE <role>;
ALTER USER <name> GRANT CONNECT, EXECUTE ON <db>;          -- a privilege of the user's own
ALTER USER <name> REVOKE EXECUTE ON <db>;
ALTER USER <name> REVOKE EXECUTE ON <db>.<view>;            -- a grant on one view
```

- `GRANT ROLE` adds to the roles the user has; the other roles stay. Several clauses go in
  one statement: `ALTER USER u GRANT ROLE r GRANT CONNECT ON db`.
- A new local user is given the role `allusers` automatically — check what `allusers`
  grants before relying on "the user has no other access".
- Reading a user's roles and grants: `DESC VQL USER <name> ('includeUserPrivileges' = 'yes')`
  — without the option it prints no `GRANT` at all. For a local user it also prints the
  password hash; prefer `CATALOG_PERMISSIONS()` (below), which prints none.
- `CREATE [ OR REPLACE ] USER <name> EXTERNAL [ '<description>' ]` creates a user whose
  password lives elsewhere (an identity provider); it takes no `GRANT` clause —
  `… EXTERNAL GRANT …` is `Syntax error … near 'GRANT'`, grant with `ALTER USER` after it.
  `CREATE OR REPLACE USER` over an existing user keeps its roles, like a role keeps its
  grants — *verified: 9.5.1 (live, 2026-10-01)*.
- A user with a password — `CREATE USER <name> '<password>' …`, `ALTER USER … PASSWORD`,
  `CONNECT USER … PASSWORD` — puts a credential into a file and into the session transcript.
  Accounts are the human's (Design Studio, LDAP, the identity provider), never the agent's.

## Database grants from the database side

```sql
-- verified: 9.5.1 (live, 2026-10-06)
ALTER DATABASE <db> GRANT CONNECT, EXECUTE TO ROLE <role>;
ALTER DATABASE <db> REVOKE EXECUTE TO ROLE <role>;
```

`TO` here, `ON` in the role and user forms. **A role or a user that does not exist is
accepted silently**: `ALTER DATABASE … GRANT … TO ROLE <typo>` answered `ok` and created
nothing — read the grant back with `CATALOG_PERMISSIONS()`.

## Privileges

| On | Privileges | Notes |
|---|---|---|
| database | `CONNECT`, `METADATA`, `EXECUTE`, `WRITE`, `CREATE` (= `CREATE_DATA_SOURCE`, `CREATE_VIEW`, `CREATE_DATA_SERVICE`, `CREATE_FOLDER`), `FILE`, `ADMIN`, `ALL PRIVILEGES` | without `CONNECT` the others are ignored: `The user does not have CONNECT privileges on the database '<db>'` |
| view, procedure | `METADATA`, `EXECUTE`, `WRITE`, `INSERT`, `UPDATE`, `DELETE`, `INDIRECT_ACCESS` (roles only, needs a server property) | there is no `SELECT` privilege: reading is `EXECUTE`, which includes `METADATA` |
| columns of a view | `GRANT EXECUTE ( c1, c2 ) ON <db>.<view>` | with `EXECUTE` on the database as well, projecting another column failed with `The user does not have privileges to project these columns: '…'`. Alone, with only `CONNECT` on the database, the same grant answered `The user does not have EXECUTE privileges on the view` — not explained; column privileges are Design Studio's |
| rows of a view, per role | `GRANT EXECUTE WHEN [ ANY ] ( c, … ) THEN '<condition>' [ MASKING … ] ON <db>.<view>` | documentation only, and Design Studio's: with a column list and without `ANY` a query that does not project all the columns gets every row |

- `ADMIN` on a database makes the user its local administrator: global security policies
  and restrictions on that database do not apply to them.
- The documentation says element privileges are ignored while the user has `EXECUTE` or
  `WRITE` on the whole database; for column privileges that did not hold on 9.5.1 (above).

## Who reads a database, and through what

```sql
-- verified: 9.5.1 (live, 2026-10-06)
SELECT username, userrolename, elementname, dbconnect, dbexecute, elementexecute, dbadmin
FROM CATALOG_PERMISSIONS()
WHERE dbname = 'sales_analytics';
```

One row per grant. A user's row with `userrolename` empty: granted to the user directly; with
a role in it: through that role. A row with `username` empty: the role's own grant, named in
`userrolename` — a role nobody holds appears only this way (its `rolename` is empty).
`elementname` empty: on the whole database. `CATALOG_PERMISSIONS()` with `WHERE username_in = '<user>'` gives one
user's grants and those of their roles; `WHERE rolename_in = '<role>'` a role's.

`GET_CATALOG_EFFECTIVE_PERMISSIONS()` (`WHERE input_user_name = '<user>' AND
input_database_name = '<db>'`) gives the effective privilege per element, with policies
counted by default (`input_check_global_security_policies`). Its `rowpermissions` and
`columnpermissions` say a restriction exists, not that it applies — the impersonated query
is the proof.

`GET_USERS_WITH_ROLE()` needs both inputs: `WHERE role = '<role>' AND
include_indirect_roles = true`; without the second, `No search methods ready to be run`. A
role that does not exist answers 0 rows, without an error — `DESC ROLE <name>` is the
existence check (`Error loading role '<name>'`).

The tool keeps 100 rows of a result unless told otherwise: `LIST ROLES` on a server with
more roles comes back cut, with `truncated: true` — pass `--max-rows 5000` before deciding
a role does not exist.

## Owners

```sql
-- unverified: 9.5 documentation only
CHOWN <user> VIEW <view>;
CHOWN <user> FOLDER '<path>';
CHOWN <user> DATASOURCE JDBC <name>;
```

The owner of an element can change and drop it. Changing an owner needs a global
administrator or a local administrator of the database. `GET_ELEMENTS()` shows the creator
and last modifier; `DESC VQL VIEW <view> ('includeUserPrivileges' = 'yes')` includes the
`CHOWN` line — and a `# USER CREATION` section with a `CREATE USER` for every user holding a
privilege on the view or below it, which for a local user is where `DESC VQL USER` prints the
password hash: filter its output down to the `CHOWN` lines before it reaches the transcript.

## Checking as someone else

```sql
-- verified: 9.5.1 (live, 2026-10-06)
SELECT … FROM <view> CONTEXT ('impersonate_user' = '<user>');
SELECT … FROM <view> CONTEXT ('impersonate_roles' = '<role>[,<role>…]');
```

The query runs with that user's — or those roles' — privileges and policies, and without a
password. The profile's user needs the role `impersonator` (a non-administrator also needs
the server property `com.denodo.vdb.security.allowImpersonateToRegularUsers`).

**Only a `SELECT`.** An `INSERT`, `UPDATE` or `DELETE` carrying the same `CONTEXT` was
executed with the profile's own privileges — a user with only `EXECUTE` on a view updated
it, and a base view they had no grant on; a user without `DELETE` deleted a row
(*verified: 9.5.1 (live, 2026-10-02)*). A write privilege is checked by the writer's own
login, never by impersonation.

| Answer | Meaning |
|---|---|
| `This user cannot impersonate. Only users with role 'impersonator' can impersonate.` | the profile's user lacks the role — granting it is the administrator's decision |
| `The user '<u>' does not exist.` / `Impersonation error: Error loading role '<r>'.` | a name typed wrong, or the account lives only in an identity provider |
| `The user does not have CONNECT privileges on the database '<db>'` / `… EXECUTE privileges on the view '<v>'` | the impersonated user or roles cannot read it — a real answer, not an error of the check |
