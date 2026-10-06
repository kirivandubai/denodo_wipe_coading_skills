# Global security policies — full syntax and measured behaviour

Source: Virtual DataPort VQL Guide 9.5, "Global Security Policies", and the Administration
Guide page of the same name; every row marked *verified* was run on 9.5.1. A global security
policy is a server-wide object: it applies to every view its `ELEMENTS` reach, in every
database it names, for every user its `AUDIENCE` matches. Global security policies and VDP
tags need the Enterprise Plus subscription bundle.

## CREATE GLOBAL_SECURITY_POLICY

```sql
-- verified: 9.5.1 (live, 2026-10-01)
CREATE [ OR REPLACE ] GLOBAL_SECURITY_POLICY <name>
    [ DESCRIPTION = '<text>' ]
    ENABLED = { TRUE | FALSE }
    AUDIENCE ( <audience> )
    ELEMENTS ( [ VIEW_DATABASES ( <db> [, …] ) ] <elements> )
    RESTRICTION ( <restriction> )
```

| Clause | Forms | Notes |
|---|---|---|
| `ENABLED` | `TRUE`, `FALSE` | mandatory: without it, `Syntax error … near 'AUDIENCE'` |
| `AUDIENCE` | `ALL`; `ANY ROLES ( r, … )`, `ALL ROLES ( … )`, `NOT_IN ROLES ( … )`; `ANY USERS ( u, … )`, `NOT_IN USERS ( … )`; `… ABAC ( 'attribute' = 'value', … )` | who is restricted — but only along the grant path the audience names, see "Audience and grant path" below. **One form per policy**: roles and users together are `Syntax error … near 'USERS'` (or `near ','` with a comma) — two policies instead. Session-attribute (`ABAC`) audiences are Design Studio's |
| `VIEW_DATABASES` | `VIEW_DATABASES ( db1, db2 )` before the element form | without it the policy is checked on the views of **every** database of the server |
| `ELEMENTS` | `ALL VIEWS`; `VIEWS TAGGED { ANY \| ALL } ( t, … )`; `VIEWS NOT TAGGED ( … )`; `COLUMNS TAGGED { ANY \| ALL } ( t, … )`; `COLUMNS NOT TAGGED ( … )`; `COLUMNS TAGGED TOP_VIEW ANY ( … )` | views are reached through tags, never by name. `TOP_VIEW` needs a server property and masks only the final view — Design Studio's |
| `RESTRICTION` | `DENY`; `DENY { ANY \| ALL } ( t, … )`; `FILTER = '<condition>' REJECT [ { ANY \| ALL } ( t, … ) ]`; `FILTER = '<condition>' MASKING { ANY \| ALL } ( t, … ) WITH ( <expr> ) ( <type> WITH <expr>, … )`; `CUSTOM <policy> [ PARAMETERS … ]` | a condition names tags, not columns: `FILTER = 'sales_territory = ''EMEA'''` filters on whichever column carries the tag `sales_territory` |

- `CREATE OR REPLACE` over an existing policy replaces it whole: audience, elements and
  restriction are what the statement says — *verified: 9.5.1 (live, 2026-10-01)*.
- `DESC VQL GLOBAL_SECURITY_POLICY <name>` returns `DROP GLOBAL_SECURITY_POLICY IF EXISTS …
  CASCADE; CREATE GLOBAL_SECURITY_POLICY …` — read it, never apply it as it is.
- Only global administrators, local administrators (for policies limited to their
  databases) and users with the role `manage_policies` create, change or drop a policy.

### Masking

```sql
-- verified: 9.5.1 (live, 2026-10-06)
RESTRICTION ( FILTER = '' MASKING ANY ( personal_data )
              WITH ( HIDE ) ( texts WITH REDACT_ASTERISK, numbers WITH HIDE, datetimes WITH HIDE ) )
```

- `FILTER = ''` is mandatory before `MASKING` (`Syntax error … near 'MASKING'` without it);
  a non-empty condition leaves the rows that satisfy it unmasked.
- The `WITH ( … ) ( … )` pair is mandatory: `MASKING ANY ( t )` alone fails with a
  `NullPointerException` text inside a syntax error; an empty type list `( )` is
  `Syntax error … near ')'`.
- **Name every type the tagged columns have.** A listed type gets its expression; a column
  whose type is not listed came back `NULL`, whatever the first `WITH ( … )` says — with
  `WITH ( REDACT_ASTERISK ) ( numbers WITH ROUND )` the text column returned `NULL`, not
  asterisks.

Expressions, as measured on a text column `'William Ward'`, an `int` `245` and a
`decimal` `0.03`:

| Expression | text | int | decimal |
|---|---|---|---|
| `REDACT_ASTERISK` | `********` | — | — |
| `FIRST_4` | `Will****` | — | — |
| `HIDE` | `NULL` | `NULL` | `NULL` |
| `DEFAULT` | — | `NULL` | `NULL` |
| `SET_MINUS_1` | — | `-1` | `-1` |
| `ROUND` | — | `245` — **not a mask** | `0` |

From the documentation only: `LATEST_4`, `SET_0`, `ONLY_YEAR`, `REMOVE_TIME`, `REMOVE_DAY`,
and `CUSTOM = <expression>` with the special tag name `any_tag` standing for the column.

- A `NULL` stays `NULL` under every expression measured; an empty text becomes `********`
  under `REDACT_ASTERISK`, so "has a value" stays visible to the audience.
- Expressions in views above the tagged one compute on the masked value: `SUBSTR(c, 1, 4)`
  gave `****`, `LEN(c)` the length of the mask (`8`), `CONCAT('Mgr: ', c)` `Mgr: ********`.
- A `WHERE` on a masked column compares the masked value: `manager = 'William Ward'`
  returned 0 rows, so the real value cannot be probed through a filter on that view;
  `GROUP BY` the masked column collapses every row into one group — *verified: 9.5.1
  (live, 2026-10-01)*.

### Row filter and deny

```sql
-- verified: 9.5.1 (live, 2026-10-06)
RESTRICTION ( FILTER = 'sales_territory = ''EMEA''' REJECT )
RESTRICTION ( DENY )
```

- The condition names **tags**, not columns: `sales_territory` is a tag on the column the rows
  are filtered by, and a name that is not a tag is refused at creation with `The following tags
  do not exist: '<name>'`.
- The filter applies whether or not the query projects the tagged column, and on every view
  built over the tagged one: a `COUNT(*)` grouped two views up counted only the rows the
  filter kept. (A per-role row restriction with a column list and without `ANY` behaves
  differently — documentation; it is Design Studio's.)
- `DENY` answers `The user does not have privileges to execute view '<view>'`.

## ALTER GLOBAL_SECURITY_POLICIES — enable, disable

```sql
-- verified: 9.5.1 (live, 2026-10-06)
ALTER GLOBAL_SECURITY_POLICIES ( mask_personal_data ENABLED = FALSE, filter_emea ENABLED = TRUE );
```

The only `ALTER`: everything else is a `CREATE OR REPLACE` of the whole policy.

## DROP

```sql
-- verified: 9.5.1 (live, 2026-10-01)
DROP GLOBAL_SECURITY_POLICY [ IF EXISTS ] <name>;
```

## Audience and grant path

A user's privileges arrive by several paths: granted to the user directly, through each of
their roles, or as a local administrator of the database. **An audience restricts only the
path it names**, and any other path that grants `EXECUTE` on the view returns the data
unrestricted. Measured with a policy masking one column, against six users:

| User's access to the view | `ANY ROLES (sales_analyst)` | `NOT_IN ROLES (auditor)` | `NOT_IN USERS (kai)` | `ALL` |
|---|---|---|---|---|
| role `sales_analyst` only | masked | masked | **clear** | masked |
| `sales_analyst` + role `auditor` | **clear** | **clear** | **clear** | masked |
| `sales_analyst` + `EXECUTE` on the database granted to the user | **clear** | **clear** | **clear** | masked |
| `sales_analyst` + `EXECUTE` on the view granted to the user | **clear** | **clear** | **clear** | masked |
| `EXECUTE` on the database granted to the user, no role | — | **clear** | masked | masked |
| `sales_analyst` + `ADMIN` on the database | **clear** | **clear** | **clear** | **clear** |

*verified: 9.5.1 (live, 2026-10-01)*. So: a role audience restricts what roles grant, a user
audience what is granted to the user directly, `ALL` every path; a local administrator of
the database and a global administrator are never restricted. `impersonate_roles = 'a,b'`
gives the union of the named roles only. A local user — and an LDAP, SAML or Kerberos user when
the server assigns `allusers` at login — also holds `allusers`: to see what a person given the
role would read, add it (`'sales_analyst,allusers'`).

`CATALOG_PERMISSIONS()` lists the paths — one row per grant. A user's row with
`userrolename` empty is the user's own grant; a row with `username` empty is a role's grant,
named in `userrolename` (`rolename` is empty there):

```sql
-- verified: 9.5.1 (live, 2026-10-06)
SELECT username, userrolename, elementname, dbconnect, dbexecute, elementexecute, dbadmin
FROM CATALOG_PERMISSIONS()
WHERE dbname = 'sales_analytics';
```

Closing a direct grant: revoke it (`ALTER USER <u> REVOKE EXECUTE ON <db>.<view>`), or add a
second policy, identical but for `AUDIENCE ( ANY USERS ( <u> ) )`. Either way the user who
read through the role and the direct grant was masked from then on, and a user outside both
audiences kept the values — *verified: 9.5.1 (live, 2026-10-01)*.

## Where the tag sits

- A filter or a mask on a tagged column applies to that view and to every view built on it.
  A tag on a column of the top view leaves the views below it unrestricted: a role with
  `EXECUTE` on the whole database read all 12 rows of the base view while the derived view
  above returned 3. Tag the column in the lowest view that carries it, or grant the
  audience only the views that carry the tag — *verified: 9.5.1 (live, 2026-10-01)*.
- Re-applying a `CREATE OR REPLACE VIEW` without the column's `TAGS` removes the tag, and
  the mask or filter with it, silently. `DESC VQL` prints a column tag as
  `CREATE VIEW v ( manager TAGS ( pii ) ) AS SELECT …` — the view's own file carries it the
  same way.

## What removes a policy, or switches it off, without saying so

| Statement | What happens | *verified: 9.5.1 (live, 2026-10-01)* |
|---|---|---|
| `DROP ROLE r` where `r` is named in a policy's audience | `All roles deleted successfully.`; the policy stays in `LIST GLOBAL_SECURITY_POLICIES`, `DESC VQL` still says `ENABLED = TRUE`, and it is no longer evaluated — for the other roles of its audience too. `GET_ELEMENTS()` shows it `INVALID`. Re-creating the role answers `Global security policies validated : <policy>` and the policy works again | the other role of the audience read the masked column in clear |
| `DROP TAG t` for a tag a policy names | refused, `Some elements depend on 't'` — also when the tag is assigned to nothing | — |
| `DROP TAG t CASCADE` | the tag **and every policy that names it** are deleted | the policy disappeared from `LIST` |
| `ALTER TAG t … REMOVE_FROM ( … COLUMNS ( db.v.c ) )`, or re-applying the view's file without `TAGS` | the column is no longer restricted | the masked column came back in clear |

Policy status, every policy of the server:

```sql
-- verified: 9.5.1 (live, 2026-10-06)
SELECT name, element_status, description FROM GET_ELEMENTS() WHERE type = 'globalSecurityPolicy';
```

## Reading

```sql
-- verified: 9.5.1 (live, 2026-10-06)
LIST GLOBAL_SECURITY_POLICIES;                         -- names
DESC VQL GLOBAL_SECURITY_POLICY <name>;                -- the definition (read it, do not apply it)
SELECT global_security_policy_name, tag_name
FROM GET_GLOBAL_SECURITY_POLICIES_TAGS();              -- which policy names which tag
```

`GET_GLOBAL_SECURITY_POLICIES_TAGS()` filters by array arguments
(`WHERE input_tag_names = {ROW('pii')}`, documentation); filtering its `tag_name` column is
simpler. A policy whose audience names a role and whose elements name no tag (`ALL VIEWS`)
has no row there — `DESC VQL` each policy listed by `LIST` to be complete.

## Errors

| Statement | Server says |
|---|---|
| audience names a role that does not exist | `There was an error creating the global security policy. Role 'x' does not exist` |
| elements or restriction name a tag that does not exist | `The following tags do not exist: 'x'` |
| `VIEW_DATABASES` names a database that does not exist | `There was an error creating the global security policy. Database 'x' does not exist` |
| `ENABLED` left out | `Syntax error: Exception parsing query near 'AUDIENCE'` |
| `MASKING` without `FILTER = ''` | `Syntax error: Exception parsing query near 'MASKING'` |
| `MASKING ANY ( t )` without `WITH` | `Syntax error: Cannot invoke "…MaskingExpressionHolder.getDefaultMasking()" because "mt" is null` |
