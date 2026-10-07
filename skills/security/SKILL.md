---
name: security
description: Use when deciding who may read what in Denodo 9.5 — masking or hiding columns (PII, contact details, salaries, bank accounts) from some users or roles, letting a role see only some rows (a country, a tenant) or each person only their own, taking someone's access away (ALTER USER … REVOKE), denying a view to a group, a global security policy (CREATE GLOBAL_SECURITY_POLICY) and the VDP tags it reads, giving a user a role or giving a role access to a database or views (CREATE ROLE … GRANT EXECUTE, ALTER USER … GRANT ROLE), checking what a given user really gets back, or a user who sees data a restriction should hide ("he still gets every row", "the masking stopped working"). Not for a tag as a label without a policy (/denodo:catalog) or for descriptions and the MCP visibility tag (/denodo:semantics).
---

# Who may read what

Everything here is server-wide, and it changes what real people get back from views —
silently. The statement succeeds; then an analyst's report shows `********` where a name
was, an amount comes back `NULL`, one analyst still reads every row, or a policy stops
being evaluated without anyone being told. Two facts shape every step below:

1. **Administrators are never restricted** — global administrators, and local administrators of
   the view's database (`ADMIN` on it). The profile you connect with may be one: `env check` →
   `vdp.admin`. **Your own `SELECT` proves nothing about a restriction.**
2. **The proof is the same query run as the person** — `CONTEXT ('impersonate_user' = '<user>')`,
   or `('impersonate_roles' = '<role>')` — with their privileges and every policy, and no password.
   It needs `vdp.impersonation: true` (the profile's user has the `impersonator` role).

A tag as a plain label is `/denodo:catalog` (its full syntax lives there); descriptions and the
MCP visibility tag are `/denodo:semantics`. User accounts and passwords, LDAP and
identity-provider groups, per-role row and column restrictions, custom policies,
session-attribute audiences and server properties are set in Design Studio by the
administrator — say so and stop. Applying files is `/denodo:execute`; the working loop and the
core safety rule are `/denodo:vql`.

## Before you change anything

Reads only, and every decision below comes from them — complete only for a global administrator
(`vdp.admin: true`). For anyone else, a local administrator too, query 1 silently returns only the
profile's own grants and its roles': say the list of readers is partial.

```sql
-- verified: 9.5.1 (live, 2026-10-07)
-- 1. Who reads the database, and through what: one row per grant. A user's row with
--    userrolename empty = granted to that user directly; a row with username empty = a
--    role's own grant (a role nobody holds shows only this way); elementname empty = the
--    whole database
SELECT username, userrolename, elementname, dbconnect, dbexecute, elementexecute, dbadmin
FROM CATALOG_PERMISSIONS() WHERE dbname = 'sales_analytics';

-- 2. Policies already on the server, and whether each is still evaluated (INVALID = not)
SELECT name, element_status, description FROM GET_ELEMENTS() WHERE type = 'globalSecurityPolicy';

-- 3. Which policy reads which tag
SELECT global_security_policy_name, tag_name FROM GET_GLOBAL_SECURITY_POLICIES_TAGS();

-- 4. Tags already on the views of the database
SELECT view_name, column_name, tag_name FROM GET_VIEW_TAGS() WHERE input_database_name = 'sales_analytics';
```

- Then `DESC VQL GLOBAL_SECURITY_POLICY <name>` for each policy that names a tag, a role or a
  database you are about to touch — its audience is not in any of the queries above. Like query 3,
  it needs an administrator of the database. It starts with `DROP … CASCADE`: read it, never apply it.
- **A tag that a policy names is a security switch**, not a label: adding it to a column
  restricts that column for the policy's audience, removing it lifts the restriction.
- One user's grants in the database: query 1 with `AND username = '<user>'`. Not `DESC VQL USER`:
  without `('includeUserPrivileges' = 'yes')` it shows no roles at all, and with it, for a
  local user, it prints the password hash into the transcript.
- Someone known only to LDAP, Kerberos or an identity provider is no VDP user: no row in query 1, and
  `impersonate_user` says `does not exist`. Their access is the roles of their groups: ask the human
  which, check them with `impersonate_roles`, and hand the check of a per-person filter to the human.
- Whether a role exists: `DESC ROLE <name>` (`Error loading role` when it does not).
  `GET_USERS_WITH_ROLE()` answers a missing role with 0 rows and no error, and `LIST ROLES`
  is cut at the tool's 100 rows (`truncated: true`) unless you pass `--max-rows 5000`.

**A user sees what they should not** — in this order, each step a read:

1. Query 2: is the policy `INVALID`? `DESC VQL` of it ends with `# Invalid object policy`;
   then `DESC ROLE` each role of its audience — one that is gone switched the policy off for
   all of them (Silent failures, 6).
2. Query 1 for that user: a row with `userrolename` empty, a role outside the audience, or
   `dbadmin = true` is a path the policy does not restrict (Choosing the audience).
3. Query 4: is the tag on the lowest view the user can read, and on the column the view
   exposes? `SELECT column_name, dependency_name, depth FROM COLUMN_DEPENDENCIES() WHERE
   input_view_database_name = '<db>' AND input_view_name = '<view>'` names the views and the
   base column behind each output column (`/denodo:views`, lineage) — *verified: 9.5.1 (live, 2026-10-05)*.
4. The impersonated query as that user, now and after each fix you propose.

## Who applies what

| What the statements touch | You apply yourself | Only after the human's yes |
|---|---|---|
| only objects you created in this session: a role no person holds yet, whose grants name only objects you created in this session, a policy limited by `VIEW_DATABASES` to a database you created in this session and whose audience is such a role, tags on views you created | create, change, check | — |
| anything that existed before this session — a role, a user, a tag a policy names, a policy, someone else's view; any grant or revoke of a role or a privilege to a person; a new policy whose audience or views include existing ones; re-creating a role someone dropped | the reads, the impersonated checks, the files | every statement |

`vql plan` on the file names, per statement, every existing object it touches that this
session did not create (`touches`) — the first row needs that list empty (`/denodo:vql`).
The tool marks `CREATE` of a role, a user or a policy `destructive: security`.

The yes is to the statements, after you have shown them in this shape:

```
Database sales_analytics. Readers today (CATALOG_PERMISSIONS): role sales_analyst — mlee,
rpatel; kchen also has EXECUTE on household_income granted to her directly.
1. security/personal_data.vql: tag personal_data, policy analyst_masking (role sales_analyst)
2. model/iv_household_income.vql: the view's file gains TAGS on buy_potential, dependents
After: mlee, rpatel see buy_potential as ********, dependents as NULL — in every view on
iv_household_income; avg_dependents in household_income_by_band becomes NULL for them.
Not covered: kchen still reads both in clear (direct grant). Revoking it is a separate yes.
Also exposed, not asked about: the role reads every column of the base views below.
Apply 1 and 2?
```

When you cannot ask — the human is away, the deadline is close — the answer is the files and
this message, with the impersonated checks the human can run after applying, not the
statements applied. Say what waiting costs, and which file goes first. A file waiting for a
yes keeps the template's `verified:` mark — the template was run, this file was not — and
the message says it is not applied. It waits whole: a statement the plan calls yours (a new tag)
waits with the rest, or it is left behind with nothing to do. Run its impersonated checks now anyway: today's answers
are the "before" the human compares with.

| Rationalization | Reality |
|---|---|
| "They named the exact columns and the treatment — that is the yes" / "they said *set it up and make sure it works*" | They named an outcome. They have not seen that a number becomes `NULL` in every report, nor which user the policy leaves out. The yes comes after the statements. |
| "Every object is new, carries my prefix and is limited to one database" | A name you chose does not make what it touches yours. The policy restricts the people who read that database, the tag sits on someone else's view: the first row of the table needs the database and the views created by you in this session, not the policy. |
| "It only restricts — it can only make things safer" | A mask changes what reports compute: a `GROUP BY` on the masked column collapses into one group, an aggregate over a hidden number becomes `NULL`, a filter on it finds nothing. Someone's dashboard breaks silently in the morning. |
| "It is reversed with one `REMOVE_FROM` / `DROP`" | The readers already got the result; and `DROP TAG … CASCADE` deletes every policy that names the tag. |
| "Only new objects — a pure `CREATE`" | A new policy restricts existing people; a re-created role revives an invalid policy; `CREATE OR REPLACE` of an existing role or user adds to it. Global objects are nobody's own by being new. |
| "Revoking can only make it safer" | `ALTER ROLE … REVOKE` on a role others hold cuts them off too, and a data source or a Scheduler job that logs in as the person stops working tonight. The yes is to the revokes, shown with who keeps what. |
| "I can't log in as them, so I'll create a test user" | A user with a password puts it in a file and in the transcript; a user with a role is a person with access. Impersonate the real people, or report the check as not done. |
| "I'll give my profile the `impersonator` role to check" | That changes your account's privileges on a shared server — the administrator's decision. Ask for it; meanwhile the result is unverified. |

**Red flags — stop:** the database in `VIEW_DATABASES`, or a view you tag, existed before
this session and you are about to apply rather than show; `env.production` is `true`; you
are about to run `ALTER USER`, `ALTER ROLE`, `CREATE OR REPLACE` of a role, a user, a tag a
policy names, or a policy that existed; you are writing `DROP TAG … CASCADE` or `DROP ROLE`;
you are about to call a restriction verified without an impersonated query; you are typing a
password.

## Templates

The four blocks below run in this order: the role, then the tag and the policy, then the
view's own file, then the check. Names follow the example database of `/denodo:views`.

### A role that reads the marts, given to a user

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CREATE OR REPLACE ROLE sales_analyst 'Sales analysts: read the household marts'
    GRANT CONNECT ON sales_analytics
    GRANT EXECUTE ON sales_analytics.household_income
    GRANT EXECUTE ON sales_analytics.household_income_by_band;

ALTER USER mlee GRANT ROLE sales_analyst;
```

- **There is no `SELECT` privilege**: reading is `EXECUTE`, and nothing works without
  `CONNECT` on the database. `EXECUTE` on a view is enough to query it — the views below it
  need no grant, and are better left without one (see "Where the tag goes").
- **Grant the views, not the database.** `GRANT EXECUTE ON sales_analytics` hands over every
  base view, every view added later, and makes the role read past a tag placed on the top
  view only.
- **`CREATE OR REPLACE ROLE` adds, never removes**: re-declared with fewer `GRANT`s, a role
  kept every privilege and every member — *verified: 9.5.1 (live, 2026-10-01)*. Deleting a
  line from this file revokes nothing; revoking is `ALTER ROLE sales_analyst REVOKE EXECUTE
  ON sales_analytics.household_income_by_band`.
- `ALTER USER … GRANT ROLE` adds the role; the user's other roles stay. A user's privileges
  are the union of their own and every role's — no role narrows another.
- Giving a role to a person is always the second row of the table above.

### Tag the columns, then the policy

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CREATE OR REPLACE TAG personal_data
    DESCRIPTION = 'Personal data of a household. Masked for sales analysts by policy analyst_masking.';

CREATE OR REPLACE GLOBAL_SECURITY_POLICY analyst_masking
    DESCRIPTION = 'Sales analysts get the columns tagged personal_data masked: text as asterisks, numbers and dates empty.'
    ENABLED = TRUE
    AUDIENCE ( ANY ROLES ( sales_analyst ) )
    ELEMENTS ( VIEW_DATABASES ( sales_analytics ) COLUMNS TAGGED ANY ( personal_data ) )
    RESTRICTION ( FILTER = ''
                  MASKING ANY ( personal_data )
                  WITH ( HIDE ) ( texts WITH REDACT_ASTERISK, numbers WITH HIDE, datetimes WITH HIDE ) );
```

- The tag exists before anything names it — the policy (`The following tags do not exist`)
  and the view's file below. The columns get it in their views' own files.
- **`VIEW_DATABASES` always**: without it the policy is checked on the views of every
  database of the server.
- **Name every type the tagged columns have.** A column whose type is missing from the list
  came back `NULL`. `HIDE` is `NULL` for any type; `ROUND` on an integer is no mask at all.
  The other expressions and the row filter and deny forms are in `references/policies.md`:
  a filter is `RESTRICTION ( FILTER = '<tag> = ''EMEA''' REJECT )` — the condition names the
  tag, not the column — and a deny is `ELEMENTS ( … VIEWS TAGGED ANY ( <tag> ) )` with
  `RESTRICTION ( DENY )`.
- `ENABLED` and `FILTER = ''` are mandatory: without them the statement is a syntax error.
- The audience decides which grants are restricted — next section, before you pick one.

### The tag in the view's own file

The view of `/denodo:views`, re-declared with its field properties. This is the file that is
re-applied on every change of the view, so this is where the tag has to live:

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE VIEW iv_household_income
    FOLDER = '/02 - integration'
    DESCRIPTION = 'Households enriched with the bounds of their income band. One row per household.'
    PRIMARY KEY ( 'household_sk' )
    ( buy_potential TAGS ( personal_data ), dependents TAGS ( personal_data ) )
    AS SELECT hd.hd_demo_sk         AS household_sk,
              hd.hd_income_band_sk  AS income_band_sk,
              hd.hd_buy_potential   AS buy_potential,
              hd.hd_dep_count       AS dependents,
              hd.hd_vehicle_count   AS vehicles,
              ib.ib_lower_bound     AS income_lower_bound,
              ib.ib_upper_bound     AS income_upper_bound
       FROM bv_household_demographics hd
            INNER JOIN bv_income_band ib
            ON hd.hd_income_band_sk = ib.ib_income_band_sk
    CONTEXT ('formatted' = 'yes');
```

- **Re-applying the view's file without the `TAGS` removes the tag, and the mask with it** —
  for a derived view and for a base view alike, without an error — *verified: 9.5.1 (live,
  2026-10-01)*. A base view carries it in its `CREATE TABLE` column list:
  `hd_buy_potential:text TAGS (personal_data),`.
- On a view whose file is not yours, the tag goes on with
  `ALTER TAG personal_data ADD_TO ( VIEWS () COLUMNS ( sales_analytics.<view>.<column> ) ) REMOVE_FROM ( VIEWS () COLUMNS () )`
  (`/denodo:catalog`; *verified: 9.5.1 (live, 2026-10-05)*) — after the yes — and the message says that the owner's file must get
  the same `TAGS`, or their next apply unmasks it. `ALTER TAG` keeps the tag's description;
  `CREATE OR REPLACE TAG … ADD_TO` does the same assignment but rewrites the description and
  is not flagged by the tool at all — which changes nothing about the yes.
- A mask applies where the tag is, and everything computed above sees the masked value
  (`references/policies.md`, Masking).

### Check it as the people it is for

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

SELECT buy_potential, dependents FROM household_income LIMIT 5
CONTEXT ('impersonate_user' = 'mlee');

SELECT COUNT(*) AS unmasked FROM household_income WHERE buy_potential <> '********'
CONTEXT ('impersonate_user' = 'mlee');

SELECT avg_dependents FROM household_income_by_band LIMIT 3
CONTEXT ('impersonate_roles' = 'sales_analyst,allusers');
```

- The impersonated queries are the first three rows of *Verify* below; write down what each
  returned — that table is the result of the work.
- A role nobody holds yet is checked with `impersonate_roles` — named roles only, so `allusers`,
  which a local user holds too, goes with it. When no reader outside the audience exists, say so —
  the administrator is not one: it sees everything anyway.
- A file stops at its first failure: an expected refusal (`does not have EXECUTE
  privileges`) goes last, or into a call of its own.
- A filter compares the masked value, so `unmasked` is `0` when every row is masked. For a
  row filter, compare `COUNT(*)` as the person with the admin's `COUNT(*) WHERE <condition>`.
- **Impersonation checks reads only.** An `INSERT`, `UPDATE` or `DELETE` with the same
  `CONTEXT` ran with the profile's own privileges: a user with nothing but `EXECUTE` on a view
  updated it and a base view they had no grant on — *verified: 9.5.1 (live, 2026-10-02)*.
  Whether someone may write is proven only by a session as them — their own login, or (documentation
  only) `CONNECT USER <u>` without a password from a profile with the `impersonator` role. Both run
  real writes: hand that check to the human (`/denodo:dml`).

### Each person sees only their own rows

The rows carry the login of the person they belong to; a tag on that column, and a filter that
compares the tag with the login of whoever is asking:

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

CREATE OR REPLACE TAG row_owner
    DESCRIPTION = 'The login of the person a row belongs to. Sales reps see only their own rows: policy own_opportunities_only.';

CREATE OR REPLACE VIEW opportunities
    FOLDER = '/03 - business entities'
    DESCRIPTION = 'Open sales opportunities with the login of the rep who owns each. One row per opportunity. Reps see only their own: policy own_opportunities_only.'
    PRIMARY KEY ( 'opportunity_id' )
    ( sales_rep TAGS ( row_owner ) )
    AS SELECT opportunity_id, account_name, amount, sales_rep
       FROM iv_opportunities
    CONTEXT ('formatted' = 'yes');

CREATE OR REPLACE GLOBAL_SECURITY_POLICY own_opportunities_only
    DESCRIPTION = 'Sales reps see only the rows whose column tagged row_owner holds their own login, case ignored, in sales_analytics and every view built on those columns.'
    ENABLED = TRUE
    AUDIENCE ( ANY ROLES ( sales_reps ) )
    ELEMENTS ( VIEW_DATABASES ( sales_analytics ) COLUMNS TAGGED ANY ( row_owner ) )
    RESTRICTION ( FILTER = 'UPPER(row_owner) = UPPER(GETSESSION(''user''))' REJECT );
```

- **`GETSESSION('user')` in the condition is the login of whoever runs the query** — under
  `impersonate_user`, the person impersonated. The condition names the tag, not the column.
- **`COLUMNS TAGGED`, not `VIEWS TAGGED`.** With the tag on a column, `VIEWS TAGGED ANY ( row_owner
  )` is created, `GET_ELEMENTS()` says `OK`, and nobody's rows are filtered.
- **Before the policy, compare the column with the people**: `SELECT sales_rep, COUNT(*)
  FROM opportunities GROUP BY sales_rep` against `GET_USERS_WITH_ROLE()` of the
  audience. A login is case-sensitive (impersonating `MLEE` is `The user 'MLEE' does not exist`),
  so a value stored in another case matches nobody under `=`; a row with no owner is seen by
  nobody in the audience, nor is a departed person's. Show the human the values that match no
  login. `UPPER` on both sides is a choice — it would also let a future user `MLEE` see `mlee`'s
  rows — and the exact `=` is the other.
- The audience sees its own rows in this view and in every view built on it — an aggregate above
  counts only theirs. Everyone outside the audience, a director through another role, and every
  administrator sees all rows ("Choosing the audience").
- The tag lives in the view's file, as above ("The tag in the view's own file"); on someone else's
  view it goes on with `ALTER TAG` after the yes.

```sql
-- verified: 9.5.1 (live, 2026-10-07)
CONNECT DATABASE sales_analytics;

-- 1. What each person should see, as the administrator: rows per owner.
SELECT UPPER(sales_rep) AS owner, COUNT(*) AS rows_owned
FROM opportunities
GROUP BY UPPER(sales_rep);

-- 2. As each person of the audience: their count, and 0 rows of anyone else.
SELECT COUNT(*) AS rows_seen,
       SUM(CASE WHEN sales_rep IS NULL OR UPPER(sales_rep) <> UPPER('mlee') THEN 1 ELSE 0 END) AS not_theirs
FROM opportunities
CONTEXT ('impersonate_user' = 'mlee');
```

**Check a per-person filter only with `impersonate_user`**, one query per person: under
`impersonate_roles` the session's user is `__roles_impersonator_user__`, so the filter returns no
rows — it looks like the restriction works and proves nothing (*verified: 9.5.1 (live,
2026-10-06)*). `rows_seen` equals that person's `rows_owned`, and `not_theirs` is `0`.

### Take someone's access away

```sql
-- verified: 9.5.1 (live, 2026-10-07)
-- 1. Every path into the database: the rows with userrolename empty are granted to the person,
--    the others come with a role.
SELECT username, userrolename, elementname, dbconnect, dbexecute, elementexecute, dbadmin
FROM CATALOG_PERMISSIONS()
WHERE dbname = 'sales_analytics' AND username = 'kchen';

-- 2. Who else holds each role the first query names: revoking from the role cuts them off too.
SELECT name FROM GET_USERS_WITH_ROLE() WHERE role = 'sales_analyst' AND include_indirect_roles = true;

-- 3. Who holds it directly: someone only in 2 has it through another role, and that is the role to revoke.
SELECT name FROM GET_USERS_WITH_ROLE() WHERE role = 'sales_analyst' AND include_indirect_roles = false;
```

The file, one statement per path of query 1 — it waits for the yes (Who applies what):

```sql
-- verified: 9.5.1 (live, 2026-10-07)
ALTER USER kchen REVOKE ROLE sales_analyst;
ALTER USER kchen REVOKE EXECUTE ON sales_analytics.household_income;
ALTER USER kchen REVOKE CONNECT ON sales_analytics;
```

- **From the person, never from a role others hold**: `ALTER ROLE … REVOKE` takes it from every
  member of query 2.
- **Every row of query 1 is a way in, and each one alone reads data**: a direct `EXECUTE` on a view
  kept working after the person's own `CONNECT` was revoked, because a role still granted
  `CONNECT`; a role with `EXECUTE` on the whole database reads every view.
- **`REVOKE` of a role or a privilege the person does not have answers `ok`** — a misspelled role
  too. Query 1 again, after, is the answer: no row.
- **The check as the person runs from another database** — the profile's own — naming the view
  with its database: `SELECT COUNT(*) FROM sales_analytics.household_income CONTEXT
  ('impersonate_user' = 'kchen')` answers `The user does not have CONNECT privileges on the
  database 'sales_analytics'` — that database, not the one you run from. Run in
  `sales_analytics` itself, an impersonated query does not check `CONNECT`: a person with nothing
  left but an `EXECUTE` on one view still read it there — *verified: 9.5.1 (live, 2026-10-06)*.
- **What a revoke does not reach**: `dbadmin = true` in query 1 — a local administrator — and a
  global administrator (`LIST USERS`, column `admin`) read everything; a role that comes from an
  LDAP or identity-provider group comes back at the next login — the administrator's, in Design
  Studio or the identity provider; copies the person already exported.
- **What stops working with it**: a VDP data source or a Scheduler job that logs in as the person
  (`api --server scheduler get /public/api/dataSources` → `login`). Name them in the message.
- The message is the shape above — readers today, the file, who reads what after, what is not
  covered.

## Choosing the audience

**An audience restricts only the grant path it names; every other path that grants
`EXECUTE` on the view returns the data unrestricted** — *verified: 9.5.1 (live, 2026-10-01)*:

| Audience | Restricted | Reads in clear anyway |
|---|---|---|
| `ANY ROLES ( r )` | what role `r` grants | a direct grant to the user (on the database **or on that one view**), any other role that grants `EXECUTE`, a local administrator |
| `NOT_IN ROLES ( r )` | what every role except `r` grants | a direct grant to the user, a local administrator |
| `ANY USERS ( u )`, `NOT_IN USERS ( u )` | what is granted to those users directly | everything that comes through their roles, a local administrator |
| `ALL` | every path, every non-administrator | local and global administrators only |

So: before a role audience, read query 1 — every path in the third column is a person who
keeps reading in clear. One audience takes one form — roles or users, never both
(`Syntax error … near 'USERS'`) — so the two ways to close a direct grant are revoking it
(`ALTER USER kchen REVOKE EXECUTE ON sales_analytics.household_income`) or a second policy,
the same but with `AUDIENCE ( ANY USERS ( kchen ) )` — either way the user was masked from
then on, *verified: 9.5.1 (live, 2026-10-01)*. Both are the human's choice, with a yes.
"Everyone except the auditors" with `ALL` is impossible — `ALL` restricts them too;
`NOT_IN ROLES ( auditor )` works only while nobody reads by a direct grant.

## Where the tag goes

- A mask or a filter on a tagged column applies to that view and **to every view built on
  it**; an aggregate over the column changes with it.
- A tag on the top view only leaves the views below it unrestricted. Tag the lowest view that
  carries the column — the base view when the audience can read the whole database — or grant
  the audience only the views above the tag.
- "It must also cover views built later": a tag on the base view's column covers every view
  built over it; a new source with its own copy of the column needs its own tag.
- **Many columns** — "mask every column that holds an email": the list, its lineage, where each
  assignment goes and the check row for row are `/denodo:catalog`, *One tag on many columns*;
  which rows wait, *Who applies what*. The impersonated check runs per view of the list, not on
  one example.

## What you need

| Slot | Where it comes from |
|---|---|
| Who is restricted, who is not | the human, as people and roles; then query 1 — the grant paths decide the audience |
| Which columns, which views | the human names the data, often by another name than the column (`buy potential` is `hd_buy_potential` two views down): `COLUMN_DEPENDENCIES()` of the view they read gives the base column. Columns of the same kind the human did not name go into the message, not into the tag |
| How each is shown | the human: masked text, empty, a filter, no access. Not said → ask; the treatment of numbers and dates is part of the question |
| Which databases | the database of every view that carries the tag — the base view's own when the tag sits there — not only the one people query; always in `VIEW_DATABASES` |
| Tag name | the concept (`personal_data`, `sales_territory`); check that no policy already names it (query 3) |
| Can you do it, and check it | `env check` → `features.enterprise_plus` (`false`: tags and policies need Enterprise Plus — say so and stop); `vdp.admin` (`false`: a role needs `create_role`, assigning it `assign_all_roles`, a privilege `ADMIN` on the database or `assignprivileges`, a tag `manage_tags`, a policy `ADMIN` on each database it names or `manage_policies` — else the files go to the human); `vdp.impersonation` |

## Verify

| Check | Query | Expect |
|---|---|---|
| Each person in the audience | the column `SELECT … CONTEXT ('impersonate_user' = '<user>')` | masked / only their rows / `does not have privileges to execute view` |
| A person outside it | the same, as them | the real values |
| Views below the tagged one | the same query on each view the audience can read | restricted too, or not readable |
| The policy is evaluated | query 2 | `element_status = 'OK'` |
| The tags landed | query 4 | one row per tagged column — a misspelled column is accepted silently (`/denodo:catalog`) |
| No path left over | query 1 | nothing outside the audience reads a tagged view, or the human was told |

## Silent failures

Each runs without an error — *verified: 9.5.1 (live, 2026-10-01)*; rows 13–16 —
*verified: 9.5.1 (live, 2026-10-06)*.

| You did | What happens | Instead |
|---|---|---|
| 1. checked as yourself | an administrator sees everything | impersonate |
| 2. a role audience, and someone also has a direct grant or another role with `EXECUTE` | that person reads in clear | read query 1, name them |
| 3. a user audience for people who read through roles | they read in clear | a role audience, or `ALL` |
| 4. tagged only the top view | the views below read in clear for whoever may read them | tag the lowest view; grant views, not the database |
| 5. re-applied a view's file without its `TAGS` | the tag is gone, and the mask | the tags live in the view's file |
| 6. `DROP ROLE` of a role named in a policy's audience | the policy stops being evaluated for **every** role in it; `DESC VQL` still says `ENABLED = TRUE` and ends with `# Invalid object policy`; query 2 says `INVALID` | read query 2 and the audiences before dropping a role. Afterwards two repairs, both a yes: re-create the role empty — the policy is validated and comes back unchanged — or `CREATE OR REPLACE` the policy without it. Which one depends on why the role went: ask |
| 7. `DROP TAG … CASCADE` | the tag and every policy that names it are deleted (without `CASCADE`: `Some elements depend on`) | query 3 first |
| 8. removed a `GRANT` line from a role's file and re-applied it | nothing revoked | `ALTER ROLE … REVOKE` — a yes |
| 9. left a type out of the masking list | that column comes back `NULL` | name texts, numbers and dates |
| 10. masked a column people group, filter or join on | groups collapse into `********`, filters find nothing | say it in the message |
| 11. `ALTER DATABASE … GRANT … TO ROLE` with a misspelled role | `ok`, nothing granted | read query 1 back |
| 12. trusted `GET_CATALOG_EFFECTIVE_PERMISSIONS` | `rowpermissions = true` for a user who reads in clear | impersonate |
| 13. a row filter with `VIEWS TAGGED` while the tag is on a column | created, `OK`, filters nothing | `COLUMNS TAGGED` |
| 14. a per-person filter checked with `impersonate_roles` | no rows — the session's user is `__roles_impersonator_user__` | `impersonate_user`, per person |
| 15. checked a revoke as the person inside the database itself | `CONNECT` is not checked there: a person with one `EXECUTE` left still read | the impersonated query from another database, `<db>.<view>` |
| 16. `ALTER USER … REVOKE` of a role or privilege the person does not have | `ok` | `CATALOG_PERMISSIONS()` for the person, after |

## Common mistakes

| You wrote | Server says | Fix |
|---|---|---|
| a policy without `ENABLED` | `Syntax error: Exception parsing query near 'AUDIENCE'` | `ENABLED = TRUE` |
| `MASKING` without `FILTER = ''` | `Syntax error: Exception parsing query near 'MASKING'` | `FILTER = '' MASKING …` |
| `MASKING ANY ( t )` with no `WITH` | `Syntax error: Cannot invoke "…getDefaultMasking()" because "mt" is null` | `WITH ( HIDE ) ( texts WITH …, numbers WITH …, datetimes WITH … )` |
| an audience role that does not exist | `There was an error creating the global security policy. Role 'x' does not exist` | the role first; check the spelling with `--max-rows` |
| a tag that does not exist | `The following tags do not exist: 'x'` | `CREATE OR REPLACE TAG` first |
| `CREATE USER u EXTERNAL GRANT ROLE r` | `Syntax error … near 'GRANT'` | accounts are the administrator's; a role is given with `ALTER USER u GRANT ROLE r` |
| an impersonated query | `This user cannot impersonate. Only users with role 'impersonator' can impersonate.` | the check is unverified — hand the human the queries and the expected answers; ask the administrator |
| an impersonated query | `The user does not have CONNECT privileges on the database '<db>'` | a real answer: that user cannot read the database |
| `GET_USERS_WITH_ROLE()` with only `role` | `No search methods ready to be run. … include_indirect_roles` | `WHERE role = 'r' AND include_indirect_roles = true` |

## Reference

- `references/policies.md` — the `CREATE GLOBAL_SECURITY_POLICY` grammar, every masking
  expression as measured, the row filter and deny, enabling and disabling, the audience
  table per grant path, what removes or disables a policy silently, and its errors.
- `references/privileges.md` — roles, users and grants (`CREATE`/`ALTER ROLE`, `ALTER USER`,
  `ALTER DATABASE … TO`), the privilege list, column privileges, owners (`CHOWN`), the
  permission procedures and what each one proves, and impersonation.
