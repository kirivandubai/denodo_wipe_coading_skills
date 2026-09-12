---
name: marketplace
description: Use when something has to appear or be labelled in the Denodo 9.5 Data Marketplace — the separate server behind /denodo-data-catalog that is driven by REST, not VQL. Covers a marketplace tag, a category tree, assigning either to the views a consumer browses, importing VDP tags into the marketplace, synchronising the marketplace catalog with Virtual DataPort, and registering an external element (asset extension) — a dashboard, ETL job, data contract, notebook or AI agent from another tool — so it shows up in the 360 graph beside the views it uses. Also for "tag it in the marketplace", "put this data product in a category", "show our BI dashboards in the catalog", "why does the marketplace not see this view". Not for VDP tags (CREATE TAG, ALTER TAG) — those are /denodo:catalog.
---

# Marketplace tags, categories and external elements

Three objects that live in the **Data Marketplace**, not in Virtual DataPort: the
marketplace **tag**, the **category**, and the **external element** that represents an asset
from another tool. The channel is REST — `scripts/denodo api` — and the server is the one
in `marketplace_url`, not the VDP port.

A "tag" alone does not say which object the human means. A **VDP tag** is `CREATE TAG` on
port 9996 and belongs to `/denodo:catalog`; a **marketplace tag** is `POST /public/api/tags`
here. They are different objects on different servers, and a request sent to the wrong one
succeeds — on the wrong side. When the request does not say, ask. Views themselves are
`/denodo:views` and `/denodo:datasources`; applying anything is `/denodo:execute`; the safety
rule and the working loop are `/denodo:vql`.

## Two rules that govern everything below

**1. Names are not keys.** Every object here is addressed by a numeric `id` that the server
assigns and that differs between installations. A template cannot contain one. There is no
`CREATE OR REPLACE`: idempotence is a *sequence* — look the name up, then `POST` if it is
missing or `PUT` if it is there. Two calls, every time, and the lookup is not optional.

**2. Nothing can be attached to a view the marketplace has not synchronised.** The
marketplace keeps its own copy of the VDP catalog. A view that exists in VDP but is not in
that copy has no id, and `view-details` says so:
`{"id": null, "inLocal": false, "inVDP": true}` — *verified: 9.5.1 (стенд, 2026-09-10)*.
Synchronise first (see the template), then assign.

**But that answer has two causes, and they look identical.** A view queried against the
*wrong* `serverId` returns exactly the same body — `id: null`, `inLocal: false`, and
`inVDP: true` even from a server that never saw the database — and nothing in the response
names the server it means — *verified: 9.5.1 (стенд, 2026-09-10)*. So before concluding
"needs synchronising", repeat the `view-details` call against the other registered servers:
if one of them answers `inLocal: true`, you had the wrong id and nothing needs
synchronising. Getting this backwards means changing a shared catalog to fix a query
parameter.

## Name the server: `serverId`

The marketplace can have several VDP servers registered, and tags, views and external tool
servers are **per server** — the same call against two ids returns two different catalogs.
With more than one registered, omitting the server is an error whose text names something
else entirely:

| Call without a server named | Answer |
|---|---|
| `/public/api/tags`, `/public/api/views/…` | `500 {"code":"GENERIC","message":"Session Expired."}` |
| `/public/api/external-tool-servers` | `403`, empty body |
| `/public/api/category-management/…` | works — categories are not server-scoped |

*verified: 9.5.1 (стенд, 2026-09-10).* Read the ids once:

```bash
# verified: 9.5.1 (стенд, 2026-09-10)
api get --env lab /public/api/configuration/servers
# → [{"id":306,"name":"Demo Standard Default","url":"//localhost:9999/admin"}, …]
```

**The id belongs in the profile, as `marketplace_server_id` — a human puts it there, not
you — and the tool adds it to every call by itself.** That is why no template below names a
server: the profile is the single place the environment is described, so the same template
works against any marketplace. One registered server needs no id at all.

`--param serverId=<id>` overrides the profile for one call, and the transport then leaves
that call alone. Reach for it only when you genuinely mean a different server than the
profile's — asking each registered server which one holds a view, just below, is the case
that needs it. Putting it on ordinary calls silently pins the environment into a command.

**Which id is the right one is not visible in the list** — the names and urls describe the
VDP connection, not which databases a server carries. Ask the object you care about:
`GET /public/api/view-details?databaseName=…&viewName=…` against each id, and take the one
answering `inLocal: true`. Guessing is expensive rather than merely wrong: everything is
created happily under the wrong server and only the import fails, with a message about a view
that "does not exist".

## Templates

### Tag, with an assignment

```bash
# verified: 9.5.1 (стенд, 2026-09-10)

# 1. does it exist? — the lookup that replaces CREATE OR REPLACE
api get --env lab /public/api/tag-management/tags \
    --param offset=0 --param limit=50 --param nameFilter=pii
# → {"count":1,"elements":[{"id":627,"name":"pii_data", …}]}   ← NOT your tag

# 2a. missing → create it
api post --env lab /public/api/tags \
    --json '{"name":"pii","description":"Personal data, GDPR scope","descriptionType":"TEXT"}'
# → {"id":627,"name":"pii","vdpTag":false, …}

# 2b. present → update it, id and all four fields in the body
api put --env lab /public/api/tags \
    --json '{"id":627,"name":"pii","description":"Personal data, GDPR scope","descriptionType":"TEXT"}'

# 3. hang it on views, by marketplace view id
api post --env lab /public/api/tags/627/views --json '[7484]'
# → []   ← empty list IS the success
```

- **`nameFilter` is a case-insensitive *substring* match, so the lookup needs a second step:
  compare `name` yourself, exactly.** `nameFilter=pii` returns `pii_data`, and
  `nameFilter=sensitive` returns a tag called `Sensitive` — *verified: 9.5.1 (стенд,
  2026-09-10)*. Taking the first element and calling it yours is how a script ends up
  `PUT`-ing over somebody else's tag. A namesake differing only in case is a collision, not a
  match: creating the second one is `409`, so that case is a question for the human, not
  something to resolve automatically.
- `name`, `description` and `descriptionType` are all mandatory on create; missing ones are
  `400 VALIDATE_FIELD`. `descriptionType` is `TEXT` or `RICH_TEXT` (the latter renders HTML).
- A duplicate name is `409` with an **empty body** — no message to read. That is why step 1
  exists.
- **`POST /tags/{id}/views` adds; `POST /views/{id}/tags` replaces** the view's whole tag
  set. Use the first unless you mean to wipe what other people put there.
- The response is the list of ids that were **not** assigned. `[]` is success; `[7484]`
  means "already assigned" **or** "no such view" — the two are indistinguishable, both come
  back `200` — *verified: 9.5.1 (стенд, 2026-09-10)*. Read the assignment back.
- **Anything that runs twice must read before it writes.** A second run of the same script
  hits an assignment that is already there and gets `[7484]` — which is neither the success
  the first run saw nor a failure worth stopping on. So check
  `GET /public/api/tags/{id}/elements` first and skip the `POST` when the view is listed;
  then `[7484]` in a response means what it should mean — something is wrong. The same holds
  for the tag itself: look it up by name, and `PUT` only when a field actually differs.
- Assigning to an external element instead of a view is
  `POST /public/api/tags/{id}/external-elements` with the same body shape, and it answers
  with an **empty body**, not a list.

### Category tree

```bash
# verified: 9.5.1 (стенд, 2026-09-10)
api post --env lab /public/api/category-management/categories \
    --json '{"name":"Consumer marts","description":"What analysts read","descriptionType":"TEXT"}'
# → {"id":352,"parentId":null, …}

api post --env lab /public/api/category-management/categories \
    --json '{"name":"Retail","description":"Retail marts","descriptionType":"TEXT","parentId":352}'

api post --env lab /public/api/category-management/categories/352/views \
    --json '[7484,7485]'
# → []
```

Same lookup-first rule (`GET …/categories/tree`), same empty-list-is-success rule. Two
differences from tags, both verified on 9.5.1 (стенд, 2026-09-10):

- **Deleting a parent deletes its children.** No warning, no mention of them in the
  response, and the assignments go with them. Read the tree before you offer a delete.
- **A repeated `DELETE` answers `200`**, where a repeated tag delete answers `500`. Do not
  read a status to decide whether something existed.

### Synchronising the marketplace catalog with VDP

Needed before any assignment to a view, and before an external element can name one. Look
at the radius first — the whole point of `changes` is that it costs nothing:

```bash
# verified: 9.5.1 (стенд, 2026-09-12)
api get --env lab /public/api/element-management/DATABASES/changes
api get --env lab /public/api/element-management/VIEWS/changes
# → {"serverElements":[…new…], "modifiedElements":[…], "localElements":[…gone from VDP…]}

api post --env lab /public/api/element-management/DATABASES/synchronize \
    --json '{"proceedWithConflicts":"SERVER_WITH_LOCAL_CHANGES"}'
api post --env lab /public/api/element-management/VIEWS/synchronize \
    --json '{"proceedWithConflicts":"SERVER_WITH_LOCAL_CHANGES"}'
# → {"inserted":[…],"modified":[…],"removed":[…]}
```

- **Both steps.** A new database registers with the first call and its views still have no
  ids; only `VIEWS/synchronize` gives them ids — *verified: 9.5.1 (стенд, 2026-09-10)*.
- `proceedWithConflicts` decides what happens to descriptions that differ:
  `SERVER_WITH_LOCAL_CHANGES` takes VDP's but keeps edits made in the marketplace,
  `LOCAL` keeps the marketplace's, `SERVER` overwrites them. **Use the first**; `SERVER`
  is the one that quietly destroys other people's work.
- `localElements` in `changes` is the list of things that will be **removed** from the
  marketplace because VDP no longer has them. Non-empty means show the human before running.
- **The radius is a reading, not a promise, and there is no scope.** `changes` describes the
  moment you asked; anything created between then and the call comes along too, and the call
  cannot be narrowed to one database — it synchronises the whole server. On a shared stand
  that means other people's new views land in the catalog with yours. Re-read the response:
  `inserted` says what actually happened.
- Cost on a catalog of ~600 views: `changes` about 1 s, `VIEWS/synchronize` about 1.4 s when
  it inserts 10 and modifies none — *verified: 9.5.1 (стенд, 2026-09-10)*. It is not a
  long-running job at that size, but it is a change to a catalog everybody shares.
- The user running it needs `METADATA` on the whole VDP catalog. Under a narrower account
  the marketplace treats what it cannot see as deleted and **removes it** —
  *unverified: documentation 9.5 (Synchronize with Virtual DataPort)*.

### External element — a dashboard, job or contract from another tool

There is no `POST /external-elements`. An external element is *imported*: the marketplace
reads an interface view in VDP and creates, updates and deletes elements to match it. So the
chain runs VQL and REST alternately, and the whole block below carries one verification mark.

```bash
# verified: 9.5.1 (стенд, 2026-09-10) — the chain as a whole

# 0. the views this element will link to must already be in the marketplace catalog
#    (previous template) — otherwise step 4 fails and nothing is created

# 1. provider type: the tool the metadata comes from. Multipart, but the icon is optional
api post --env lab /public/api/external-providers-types \
    --part 'request=json:{"name":"ACME_BI","visualName":"Acme BI"}'
# → 201 {"externalProviderTypeId":30,"iconImage":null, …}
#   with a logo:  --part 'icon=@./acme.svg'

# 2. the server that will read the contract. The interface view need not exist yet
api post --env lab /public/api/external-tool-servers \
    --json '{"type":"CUSTOM","name":"acme_bi_server","description":"Acme BI dashboards",
             "externalProviderTypeId":30,
             "databaseName":"sales_analytics","viewName":"i_acme_bi_elements"}'
# → {"id":217, …}

# 3. ask the marketplace for the contract it expects, and apply it as VQL
api get --env lab /public/api/external-tool-servers/217/vql-metadata
# → a JSON string: CONNECT DATABASE …; two CREATE TYPE; CREATE INTERFACE VIEW …

# 4. import
api post --env lab /public/api/external-tool-servers/synchronize \
    --json '{"externalToolServerIds":[217]}'
# → externalElementsAdded / Updated / Deleted, per server
```

**Both type steps are usually unnecessary, and they are different objects.** Look each one
up before creating it — a new type is a marketplace-wide object that everyone then sees:

| | Built in on 9.5.1 | List it with | Examples |
|---|---|---|---|
| **Element type** — what the asset *is* | 24 | `GET /public/api/external-elements-types` | `DASHBOARD`, `REPORT`, `PIPELINE`, `DATA_CONTRACT`, `AI_AGENT`, `NOTEBOOK`, `ETL_JOB`, `QUALITY_RULE` |
| **Provider type** — the tool it *comes from* | 28 | `GET /public/api/external-providers-types` | `AIRFLOW_PROVIDER`, `GITHUB_PROVIDER`, `TABLEAU`, `POWERBI`, `COLLIBRA_PROVIDER`, `DATABRICKS_PROVIDER`, `SNOWFLAKE_PROVIDER`, `JUPYTER_PROVIDER` |

*verified: 9.5.1 (стенд, 2026-09-10).* **The provider listing carries every icon as base64
and weighs about 290 KB** — read it into a file and project
`{externalProviderTypeId, name, visualName}` rather than letting it into the conversation.
Step 1 of the chain above only applies when no built-in provider type fits; the same goes for the element type
(`POST /public/api/external-elements-types`, all six fields mandatory, `iconKey` is a
FontAwesome key). Both listings return the name under a different key than the one you send:
the element type is `externalElementTypeName` when read and `name` when written, and the read
form has no `description` at all.

The VQL half — the implementation behind the contract from step 3:

```sql
-- verified: 9.5.1 (стенд, 2026-09-12)
CONNECT DATABASE sales_analytics;

-- the two types come from vql-metadata verbatim. The names are part of the contract
CREATE OR REPLACE TYPE external_element_association_type AS REGISTER OF (
    associated_element_id:text, external_tool_server_name:text,
    associated_element_type:text, direction:text, role:text);
CREATE OR REPLACE TYPE external_element_association_array_type AS ARRAY OF external_element_association_type;

CREATE OR REPLACE VIEW acme_bi_metadata FOLDER = '/02 - integration'
    AS SELECT 'ACME-DASH-01'                       AS id,
              'Revenue cockpit'                    AS name,
              'Weekly revenue by region'           AS description,
              'DASHBOARD'                          AS external_element_type,
              'https://acme.example/d/revenue'     AS url,
              CAST('timestamp', '2026-01-19 09:00:00') AS created_at,
              CAST('timestamp', '2026-09-06 07:45:00') AS updated_at
       FROM DUAL();

CREATE OR REPLACE VIEW acme_bi_associations FOLDER = '/02 - integration'
    AS SELECT 'ACME-DASH-01'                        AS owner_id,
              'sales_analytics.household_income'    AS associated_element_id,
              CAST('text', NULL)                    AS external_tool_server_name,
              'VIEW'                                AS associated_element_type,
              'OUT'                                 AS direction,
              'consumes'                            AS role
       FROM DUAL();

CREATE OR REPLACE VIEW acme_bi_elements FOLDER = '/02 - integration'
    AS SELECT m.id AS id, m.name AS name, m.description AS description,
              m.external_element_type AS external_element_type, m.url AS url,
              m.created_at AS created_at, m.updated_at AS updated_at,
              CAST('external_element_association_array_type',
                   NEST(a.associated_element_id, a.external_tool_server_name,
                        a.associated_element_type, a.direction, a.role)) AS associations
       FROM acme_bi_metadata m INNER JOIN acme_bi_associations a ON m.id = a.owner_id
       GROUP BY m.id, m.name, m.description, m.external_element_type, m.url,
                m.created_at, m.updated_at;

CREATE OR REPLACE INTERFACE VIEW i_acme_bi_elements (
        id:text, name:text, description:text, external_element_type:text, url:text,
        created_at:timestamp, updated_at:timestamp,
        associations:external_element_association_array_type
    )
    SET IMPLEMENTATION acme_bi_elements
    FOLDER = '/02 - integration';
```

Four things here are load-bearing, each verified on 9.5.1 (стенд, 2026-09-10):

- **`external_element_association_array_type` is the name the marketplace checks**, literally.
  Rename it and synchronisation refuses the whole server:
  `400 INVALID_EXTERNAL_ELEMENT_INTERFACE_VIEW … expected type external_element_association_array_type`.
  Types live inside a database, so the contract names never clash across databases.
- **`external_element_type` must equal an element type's `name`**, character for character —
  the field is `name` when you create a type and `externalElementTypeName` when you list them.
- **`INNER JOIN`, not `LEFT OUTER JOIN`.** A left join over an element with no associations
  makes `NEST` produce one all-null record, and the import rejects the element:
  `400 … Required field 'associated_element_id' is null … association index 0`. As written
  above — every element has an association — the inner join is the whole story; only if some
  element has none do you add a second branch, `UNION ALL SELECT …,
  CAST('external_element_association_array_type', NULL) AS associations FROM … WHERE id NOT IN
  (SELECT owner_id FROM …)`.
- `CREATE OR REPLACE INTERFACE VIEW … SET IMPLEMENTATION` in one statement, so the file
  re-applies. `ALTER INTERFACE VIEW` does the same thing but is a change to an existing
  object and needs a human's yes (`/denodo:vql`).

`SELECT * FROM i_acme_bi_elements` before step 4: an interface view accepts an implementation
that does not match it, and only the `SELECT` shows it (`/denodo:views`).

## What you need before filling a template

| Slot | Where it comes from |
|---|---|
| Which "tag" | marketplace tag = visible in the Data Marketplace UI, created here; VDP tag = `LIST TAGS`, `/denodo:catalog`. When the request does not say, ask — the call succeeds either way, on the wrong server |
| `serverId` | `marketplace_server_id` in the profile — the human's to set, and the tool adds it for you; the ids are in `GET /public/api/configuration/servers`. Needed as soon as more than one VDP is registered. Do not put it in a call unless you mean a server other than the profile's |
| Tag or category name, description | the human. Both are shown to consumers browsing the marketplace, so they read as labels, not as identifiers |
| Every numeric id | never a template, never memory: a `GET` in this session. Ids differ per installation and per server |
| View ids to assign to | `GET /public/api/view-details?databaseName=…&viewName=…`; `id:null` means synchronise first |
| Whether the catalog may be synchronised | the human, if `changes` shows anything under `localElements` or a modified element that is not yours — it is a shared catalog |
| For an external element: the type | `GET /public/api/external-elements-types` — 24 built in; invent one only if none fits |
| For an external element: id, name, url, timestamps | the source tool. `updated_at` is what drives updates — an element whose `updated_at` does not move is never refreshed |
| Which views the element links to | the human, plus their exact `database.view` — an association naming a view the marketplace does not know fails the whole import |
| Direction and role | `IN`/`OUT` plus free text (`consumes`, `feeds`, `validates`). The direction is read from the element outwards, so a dashboard that *reads* a view is still `OUT`. The role is the label on the edge of the 360 graph |

Do not ask about property groups, endorsements, requests or personalisation — they are
marketplace features with their own screens, not part of creating these objects.

## Reference

- `references/tags.md` — the full tag surface, importing VDP tags into the marketplace and
  why that call is the most destructive one here, webservice targets, `delete-multiple`.
- `references/categories.md` — the tree endpoints, moving a category, assignment from the
  view's side, what cascades.
- `references/external-elements.md` — the element and provider type surface, the association
  record in detail, element-to-element associations, what synchronisation adds, updates and
  deletes, and how to read `/details`.

The stand is also its own reference: `GET /v3/api-docs` on the marketplace returns the whole
OpenAPI document (375 paths on 9.5.1), which settles any path or body this skill does not
cover.

## Verify

A `200` here means less than usual: assignments report failure inside a `200` body, and the
import reports what it did rather than whether it worked. Read the object back, from the
other side where there is one.

| Question | Read-back |
|---|---|
| Did the tag/category land | `GET /public/api/tags/{id}` · `GET /public/api/category-management/categories/{id}` |
| Is the assignment real, from the tag's side | `GET /public/api/tags/{id}/elements` → `{"views":[…],"webservices":[…]}` |
| … from the category's side | `GET /public/api/category-management/categories/{id}/views` — **`offset` and `limit` are mandatory**, without them it is `400 MISSING_REQUEST_PARAMETER` |
| … from the view's side | `GET /public/api/views/{viewId}/tags` · `GET /public/api/category-management/views/{viewId}/categories` |
| Is the view in the catalog at all | `GET /public/api/view-details?databaseName=…&viewName=…` → `id`, `inLocal`, `inVDP` |
| What a synchronisation would change | `GET /public/api/element-management/{DATABASES\|VIEWS}/changes` — **before**, not after |
| Did the import create what you meant | the `synchronize` response names each element: `externalElementsAdded/Updated/Deleted` with `originalExternalElementId` |
| Is the element visible to a consumer | `GET /public/api/external-elements/{id}/details` — type, server, url, and its lineage |
| **Does the view show the element** | `GET /public/api/views/tree/external-elements/lineage?databaseName=…&viewName=…` — the question a human actually asked ("what consumes this?"), answered from the other end. The view node must resolve to `databaseName`/`viewName`, not stay a bare string |
| Is it really gone | `GET` it: `404` is the answer you want. The tool reports that as `ok:false` and exit `1`, so a verification script must treat `404` as success here rather than stopping — *verified: 9.5.1 (стенд, 2026-09-10)* |
| Which VDP tags are imported | `GET /public/api/tags/vdp/local` — a plain list of names. **Not** `inLocal` in `/tags/vdp/changes`: that flag means "a marketplace tag of this name exists", which is also true for an unrelated local tag — *verified: 9.5.1 (стенд, 2026-09-10)* |

## Common mistakes

| You did | Server says | Fix |
|---|---|---|
| any tag or view call with several VDP servers registered | `500 GENERIC "Session Expired."` | the profile has no `marketplace_server_id` — a human sets it, from `/public/api/configuration/servers`. `--param serverId=…` gets one call through in the meantime |
| read `id: null` from `view-details` as "not synchronised" | `200`, and the same body a wrong `serverId` produces | ask the other servers first; only then synchronise |
| `GET …/categories/{id}/views` without paging | `400 MISSING_REQUEST_PARAMETER` | `--param offset=0 --param limit=50` |
| the same on `/external-tool-servers` | `403`, empty | the same cause, a different code |
| `POST /tags` with a name that exists | `409`, empty body | look up by name first, then `PUT` |
| take the first element `nameFilter` returned | `200`, the wrong tag | the filter matches substrings and ignores case — compare `name` exactly |
| `POST /tags/{id}/views` for a view that is not synchronised | `200` and `[7484]` | it is not an error and not an assignment — synchronise, then re-assign |
| read a `200` from an assignment as success | — | success is `[]`; a non-empty list is what failed |
| `POST /views/{id}/tags` to add one tag | `200` | that endpoint **replaces** the view's tags; use `/tags/{id}/views` |
| `DELETE` a parent category | `200` | its children went too — read `…/categories/tree` before offering it |
| `DELETE` the same tag twice | `500 GENERIC "Incorrect number of deleted tuples"` | it was already gone; categories answer `200` and servers `404` for the same thing |
| `synchronize` a tool server before the associated view is in the catalog | `400 INVALID_VDP_EXTERNAL_ELEMENT_METADATA "The view '…' does not exist"` | the view **does** exist in VDP — it is the marketplace copy that is missing. Synchronise the catalog |
| rename the association array type | `400 INVALID_EXTERNAL_ELEMENT_INTERFACE_VIEW … expected type external_element_association_array_type` | keep the contract's names |
| `LEFT OUTER JOIN` for elements without associations | `400 … Required field 'associated_element_id' is null` | `INNER JOIN` plus a `UNION ALL` branch with a NULL array |
| drop an element from a non-empty snapshot | `200`, and the element is **deleted** with its tags and categories | that is the contract: the interface view is the full picture, not a delta |
| empty the snapshot entirely to clear elements | `200`, nothing deleted | an empty result is treated as "no data", not "delete everything" — *verified: 9.5.1 (стенд, 2026-09-10)* |
| `DELETE` an external tool server to tidy up | `200` | every element it imported disappeared with it, tags and categories included |

Destructive here is decided by method and path, not by the word in it: `DELETE` of a
category (with its children), `DELETE` of a tool server (with its elements),
`POST /tags/vdp/synchronize` (see `references/tags.md`), `POST …/synchronize` with
`proceedWithConflicts: "SERVER"`, and `POST /views/{id}/tags`, which replaces rather than
adds. All of them are the human's call — `/denodo:vql`.
