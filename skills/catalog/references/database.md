# Virtual database — full syntax

Source: Virtual DataPort VQL Guide 9.5, "Creating and Modifying Virtual DataPort
Databases". Only administrators can run `CREATE`, `ALTER` and `DROP DATABASE`.

Each clause carries its own status. Verified means it ran on a 9.5.1 server; unverified
means the syntax is taken from the documentation and has not been exercised.

## CREATE DATABASE

```sql
-- verified: 9.5.1 (live, 2026-09-09) — name, description, CHARSET, AUTHENTICATION LOCAL
CREATE [ OR REPLACE ] DATABASE <name> [ '<description>' ]
    [ CHARSET { UNICODE | RESTRICTED | DEFAULT } ]
    [ AUTHENTICATION LOCAL ]
```

```sql
-- unverified: 9.5 documentation only
CREATE [ OR REPLACE ] DATABASE <name> [ '<description>' ]
    [ VCS { OFF | ON ( [ REMOTEDB = <id> ] [ ENVIRONMENT = <id> ] [ PROPERTIES ( '<k>' = '<v>' [, …] ) ] )
               | ON ( URL = '<url>' SYSTEM = 'git' REMOTEDB = <id> [ USER = '<u>' ] [ PASSWORD = '<p>' [ ENCRYPTED ] ]
                      [ ENVIRONMENT = <id> ] [ PROPERTIES ( '<k>' = '<v>' [, …] ) ] ) } ]
    [ CHARSET { UNICODE | RESTRICTED | DEFAULT } ]
    [ AUTHENTICATION LDAP <db>.<ldap datasource>
          USERBASE = '<dn>' [, '<dn>' ]*
          USERATTRIBUTENAME = '<attr>'
          USERSEARCH = '<pattern>'
          ROLEBASE = '<dn>' [, '<dn>' ]*
          ROLEATTRIBUTENAME = '<attr>'
          ROLESEARCH = '<pattern with @{USERDN} or @{USERLOGIN}>'
          [ ROLESSEARCHAUTHENTICATION ] [ WITH_ALLUSERS_ROLE ] ]
    [ CREDENTIALS_VAULT ( STATUS { ON | OFF | DEFAULT }
          [ PROVIDER { HASHICORP ( NAMESPACE = '<ns>' )
                     | CYBERARK ( APPLICATION_ID = '<id>' { AGENT | AGENT_LESS ( CLIENT_KEY = '<k>' [ CLIENT_KEY_PASSWORD = '<p>' [ ENCRYPTED ] ] ) } ) } ] ) ]
    [ DATA_MOVEMENT ALLOWED_TARGETS DATABASES { DEFAULT | NONE | SELF | ( <db> [, <db> ]* ) } ]
    [ ODBC AUTHENTICATION { NORMAL | KERBEROS } ]
    [ CHECK_VIEW_RESTRICTIONS { ALWAYS | DIRECT_QUERIES_ONLY | DEFAULT } ]
    [ <grant> ]*
```

Order matters: the description literal is the first thing after the name; `CHARSET`
after it. With `CHARSET` before the description the parser stops at the quote.

| Clause | Meaning | Default |
|---|---|---|
| `'<description>'` | free text, shown by `DESC DATABASE` and `GET_DATABASES()` | none |
| `CHARSET` | which characters Design Studio lets users put in identifiers. `UNICODE` any; `RESTRICTED` a limited set; `DEFAULT` the server setting. Does not change the server's behaviour | `DEFAULT` — what that means is the server's setting; `GET_DATABASES()` → `charset`, `charset_default` |
| `AUTHENTICATION LOCAL` | users are VDP users. This is "Global authentication settings" in Design Studio | this, when the clause is absent |
| `AUTHENTICATION LDAP …` | authentication and roles delegated to an LDAP server through an LDAP data source that already exists in `<db>`. Needs the six values — two base DNs, two attribute names, two search patterns — get them from the human or the Administration Guide setup, never guess | — |
| `VCS` | per-database version-control integration | server setting |
| `CREDENTIALS_VAULT` | HashiCorp / CyberArk configuration for this database | server setting |
| `DATA_MOVEMENT ALLOWED_TARGETS DATABASES` | where the optimizer may move this database's data | `DEFAULT` (anywhere that allows it) |
| `ODBC AUTHENTICATION KERBEROS` | Kerberos for ODBC / ADO.NET clients | `NORMAL` |
| `CHECK_VIEW_RESTRICTIONS` | see the Upgrade Guide before changing | `DEFAULT` |
| `<grant>` | privileges — `/denodo:security`; the tool flags a `CREATE DATABASE` that carries one `security` | — |

`CREATE OR REPLACE DATABASE` on an existing database updates the description and settings
and **keeps every object inside** — *verified: 9.5.1 (live, 2026-09-09)*. `CREATE
DATABASE` without `OR REPLACE` on an existing one: `error creating database: Database
already exists`.

## ALTER DATABASE

```sql
-- verified: 9.5.1 (live, 2026-09-09) — description, CHARSET
ALTER DATABASE <name> [ '<description>' ]
    [ CHARSET { UNICODE | RESTRICTED | DEFAULT } ]
```

```sql
-- unverified: 9.5 documentation only
ALTER DATABASE <name> [ '<description>' ]
    [ CHARSET { UNICODE | RESTRICTED | DEFAULT } ]
    [ COST OPTIMIZATION { ON | OFF | DEFAULT } ]
    [ QUERY SIMPLIFICATION { ON | OFF | DEFAULT } ]
    [ SUMMARY REWRITE { ON | OFF | DEFAULT } ]
    [ DATA_MOVEMENT ALLOWED_TARGETS DATABASES { DEFAULT | ALL | NONE | SELF | ( <db> [, <db> ]* ) } ]
    [ VCS … ]                                   -- as in CREATE DATABASE
    [ AUTHENTICATION { LOCAL [ <grant> ]* | LDAP … } ]
    [ ODBC AUTHENTICATION { NORMAL | KERBEROS } ]
    [ CACHE { DEFAULT | [ ON | OFF ] ( [ MAINTENANCE { OFF | ON } ] [ MAINTAINERPERIOD <seconds> ]
              [ TIMETOLIVE { <seconds> | DEFAULT | NOEXPIRE } ]
              [ DATASOURCE { DEFAULT | CUSTOM | <datasource> DATABASE <db> } ] ) } ]
    [ MEMORYCONFIG { DEFAULT | ( SWAP [ ON | OFF ] ( [ SWAPSIZE <mb> ] [ SWAPBLOCKSIZE <mb> ] )
                     [ MAXRESULTSIZE <mb> ] [ MAXQUERYSIZE <mb> ] ) } ]
    [ CHECK_VIEW_RESTRICTIONS { ALWAYS | DIRECT_QUERIES_ONLY | DEFAULT } ]
    [ <grant> ]*
```

`ALTER` is a change to an existing object: the human confirms it first (`/denodo:vql`),
and on a production profile the tool refuses it without `--allow-destructive`. For a
database that only this project's file has configured, re-applying the file's `CREATE OR
REPLACE DATABASE` is enough. For any other database, change only the clause in question with
`ALTER DATABASE`, after the human's yes: `CREATE OR REPLACE` is not documented to keep the
settings it does not name. On 9.5.1 it kept the `CHARSET`, `COST OPTIMIZATION`,
`ODBC AUTHENTICATION` and `CHECK_VIEW_RESTRICTIONS` set before it —
*verified: 9.5.1 (live, 2026-10-07)* — LDAP authentication, VCS, the vault and the cache were
not tried.

## DROP DATABASE

```sql
-- verified: 9.5.1 (live, 2026-09-09)
DROP DATABASE [ IF EXISTS ] <name>
```

Deletes the database **and everything in it**: data sources, wrappers, views,
associations, folders. Human's confirmation, always. It cannot be run from a connection
that is connected to that database — `This database cannot be dropped because the
connection was established with this database` — so do not put `CONNECT DATABASE x;`
before `DROP DATABASE x;` in the same file, and do not run it with `--database x`.

## Reading databases back

```sql
-- verified: 9.5.1 (live, 2026-10-07)
LIST DATABASES;                                   -- name
DESC DATABASE <name>;                             -- name, description
SELECT db_name, description, charset, authentication, odbc_authentication,
       cost_optimization, query_simplification, summary_rewrite, vcs, cache,
       check_view_restrictions
FROM GET_DATABASES() WHERE db_name = '<name>';
```

`GET_DATABASES()` has no `database_name` column; the name is `db_name`. `charset`,
`cost_optimization`, `query_simplification`, `summary_rewrite`, `cache` and
`check_view_restrictions` each have a `<setting>_default` column, true only when the database
is set to Default (false for an explicit value even if it equals the server's);
`authentication`, `odbc_authentication` and `vcs` have none. `DESC VQL DATABASE <name>` prints
the objects of the database as VQL, not the `CREATE DATABASE` statement itself, unless
`('includeCreateDatabase' = 'yes')` adds `CREATE DATABASE` and `ALTER DATABASE` with its
settings — behind a `DROP DATABASE IF EXISTS` line: read it, do not apply it. Its first line
carries the server version.
