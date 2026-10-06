---
name: marketplace
description: Use when something has to appear or be labelled in the Denodo 9.5 Data Marketplace — the separate server behind /denodo-data-catalog that is driven by REST, not VQL. Covers a marketplace tag, a category tree, assigning either to the views a consumer browses, importing VDP tags into the marketplace, synchronising the marketplace catalog with Virtual DataPort, and registering an external element (asset extension) — a dashboard, ETL job, data contract, notebook or AI agent from another tool — so it shows up in the 360 graph beside the views it uses. Also for "tag it in the marketplace", "put this data product in a category", "show our BI dashboards in the catalog", "why does the marketplace not see this view". Not for VDP tags (CREATE TAG, ALTER TAG) — those are /denodo:catalog.
---

# Marketplace tags, categories and external elements

Three objects that live in the **Data Marketplace**, not in Virtual DataPort: the
marketplace **tag**, the **category**, and the **external element** that represents an asset
from another tool. The channel is REST — `scripts/denodo api` — and the server is the one
in `marketplace_url`, not the VDP port.

A "tag" alone does not say which object the human means. A **VDP tag** is `CREATE TAG` in
Virtual DataPort and belongs to `/denodo:catalog`; a **marketplace tag** is
`POST /public/api/tags` here. They are different objects on different servers, and a request
sent to the wrong one succeeds — on the wrong side. When the request does not say, ask — or
look at where the object has to be visible: a consumer who only browses the marketplace means
a marketplace tag.
Views themselves are `/denodo:views` and `/denodo:datasources`; applying anything is
`/denodo:execute`; the safety rule and the working loop are `/denodo:vql`.

## Two rules that govern everything below

**1. Names are not keys.** Every object here is addressed by a numeric `id` that the server
assigns and that differs between installations. A template cannot contain one. There is no
`CREATE OR REPLACE`: idempotence is a *sequence* — look the name up, then `POST` if it is
missing or `PUT` if it is there. Two calls, every time, and the lookup is not optional.

**2. Nothing can be attached to a view the marketplace has not synchronised.** The
marketplace keeps its own copy of the VDP catalog. A view that exists in VDP but is not in
that copy has no id, and `view-details` says so:
`{"id": null, "inLocal": false, "inVDP": true}` — *verified: 9.5.1 (live, 2026-09-10)*.
Synchronise first (see the template), then assign.

**But that answer has two causes, and they look identical.** A view queried against the
*wrong* `serverId` returns exactly the same body — `id: null`, `inLocal: false`, and
`inVDP: true` even from a server that never saw the database — and nothing in the response
names the server it means — *verified: 9.5.1 (live, 2026-09-10)*. So before concluding
"needs synchronising", repeat the `view-details` call against the other registered servers:
if one of them answers `inLocal: true`, you had the wrong id and nothing needs
synchronising. Getting this backwards means changing a shared catalog to fix a query
parameter. `VIEWS/changes` does not shortcut the round: a server that never carried the
database lists its views under `serverElements` too, as views it would import —
*verified: 9.5.1 (live, 2026-10-01)*.

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

*verified: 9.5.1 (live, 2026-09-10).* Read the ids once:

```bash
# verified: 9.5.1 (live, 2026-10-06)
api get --env dev /public/api/configuration/servers
# → [{"id":<serverId>,"name":"<VDP server as registered>","url":"//<vdp-host>:9999/admin"}, …]
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
# verified: 9.5.1 (live, 2026-09-10)

# 1. does it exist? — the lookup that replaces CREATE OR REPLACE
api get --env dev /public/api/tag-management/tags \
    --param offset=0 --param limit=50 --param nameFilter=pii
# → {"count":1,"elements":[{"id":<another tag's id>,"name":"pii_legacy", …}]}   ← NOT your tag

# 2a. missing → create it
api post --env dev /public/api/tags \
    --json '{"name":"pii","description":"Personal data, GDPR scope","descriptionType":"TEXT"}'
# → {"id":<tag_id>,"name":"pii","vdpTag":false, …}

# 2b. present → update it, id and all four fields in the body
api put --env dev /public/api/tags \
    --json '{"id":<tag_id>,"name":"pii","description":"Personal data, GDPR scope","descriptionType":"TEXT"}'

# 3. hang it on views, by marketplace view id
api post --env dev /public/api/tags/<tag_id>/views --json '[<view_id>]'
# → []   ← empty list IS the success
```

- **`nameFilter` is a case-insensitive *substring* match, so the lookup needs a second step:
  compare `name` yourself, exactly.** `nameFilter=pii` also returns a tag called `pii_legacy`,
  and `nameFilter=finance` one called `Finance` — *verified: 9.5.1 (live, 2026-09-10)*. Taking the first element and calling it yours is how a script ends up
  `PUT`-ing over somebody else's tag. A namesake differing only in case is a collision, not a
  match: creating the second one is `409`, so that case is a question for the human, not
  something to resolve automatically.
- **The two base paths are the API's own, not a slip in this template:** the paged lookup is
  `/public/api/tag-management/tags`, while create, update and the per-tag reads are
  `/public/api/tags/…`. Do not "correct" one to match the other.
- `name`, `description` and `descriptionType` are all mandatory on create; missing ones are
  `400 VALIDATE_FIELD`. `descriptionType` is `TEXT` or `RICH_TEXT` (the latter renders HTML).
- A duplicate name is `409` with an **empty body** — no message to read. That is why step 1
  exists.
- **`POST /tags/{id}/views` adds; `POST /views/{id}/tags` replaces** the view's whole tag
  set. Use the first unless you mean to wipe what other people put there.
- The response is the list of ids that were **not** assigned. `[]` is success; `[<view_id>]`
  means "already assigned" **or** "no such view" — the two are indistinguishable, both come
  back `200` — *verified: 9.5.1 (live, 2026-09-10)*. Read the assignment back.
- **Anything that runs twice must read before it writes.** A second run of the same script
  hits an assignment that is already there and gets `[<view_id>]` — which is neither the success
  the first run saw nor a failure worth stopping on. So check
  `GET /public/api/tags/{id}/elements` first and skip the `POST` when the view is listed;
  then `[<view_id>]` in a response means what it should mean — something is wrong. The same holds
  for the tag itself: look it up by name, and `PUT` only when a field actually differs.
- Assigning to an external element instead of a view is
  `POST /public/api/tags/{id}/external-elements` with the same body shape, and it answers
  with an **empty body**, not a list.

### Category tree

```bash
# verified: 9.5.1 (live, 2026-09-10)
api post --env dev /public/api/category-management/categories \
    --json '{"name":"Consumer marts","description":"What analysts read","descriptionType":"TEXT"}'
# → {"id":<category_id>,"parentId":null, …}

api post --env dev /public/api/category-management/categories \
    --json '{"name":"Retail","description":"Retail marts","descriptionType":"TEXT","parentId":<category_id>}'

api post --env dev /public/api/category-management/categories/<category_id>/views \
    --json '[<view_id>]'
# → []
```

Same lookup-first rule (`GET …/categories/tree`), same empty-list-is-success rule. Two
differences from tags, both *verified: 9.5.1 (live, 2026-09-10)*:

- **Deleting a parent deletes its children.** No warning, no mention of them in the
  response, and the assignments go with them. Read the tree before you offer a delete.
- **A repeated `DELETE` answers `200`**, where a repeated tag delete answers `500`. Do not
  read a status to decide whether something existed.

### Synchronising the marketplace catalog with VDP

Needed before any assignment to a view, and before an external element can name one. Look
at the radius first — the whole point of `changes` is that it costs nothing:

```bash
# verified: 9.5.1 (live, 2026-10-06)
api get --env dev /public/api/element-management/DATABASES/changes
api get --env dev /public/api/element-management/VIEWS/changes
# → {"serverElements":[…new…], "modifiedElements":[…], "localElements":[…gone from VDP…]}

api post --env dev /public/api/element-management/DATABASES/synchronize \
    --json '{"proceedWithConflicts":"SERVER_WITH_LOCAL_CHANGES"}'
api post --env dev /public/api/element-management/VIEWS/synchronize \
    --json '{"proceedWithConflicts":"SERVER_WITH_LOCAL_CHANGES"}'
# → {"inserted":[…],"modified":[…],"removed":[…]}
```

- **Both steps.** A new database registers with the first call and its views still have no
  ids; only `VIEWS/synchronize` gives them ids — *verified: 9.5.1 (live, 2026-09-10)*.
- `proceedWithConflicts` decides what happens to descriptions that differ:
  `SERVER_WITH_LOCAL_CHANGES` takes VDP's but keeps edits made in the marketplace,
  `LOCAL` keeps the marketplace's, `SERVER` overwrites them. **Use the first**; `SERVER`
  is the one that quietly destroys other people's work.
- `localElements` in `changes` is the list of things that will be **removed** from the
  marketplace because VDP no longer has them, whatever the conflict mode. **A view renamed in
  VDP is in that list under its old name** — the next template.
- A `modifiedElements` entry with `reason: "DESCRIPTION,FIELD_DESCRIPTION"` is usually an
  element whose descriptions were edited in the marketplace: it is listed on every reading,
  and `SERVER_WITH_LOCAL_CHANGES` keeps those edits — *verified: 9.5.1 (live, 2026-10-01)*.
  Such an entry loses nothing in the call — say so when you show the human the radius.
- **The radius is a reading, not a promise, and there is no scope.** `changes` describes the
  moment you asked; anything created between then and the call comes along too, and the call
  cannot be narrowed to one database — it synchronises the whole server. On a shared server
  that means other people's new views land in the catalog with yours. Re-read the response:
  `inserted` says what actually happened.
- **Who sends it.** You, when the same call with `--plan`, right before it, says `needs_yes:
  false`: it reads both `changes` — both, even when only `VIEWS/synchronize` is needed — and
  finds only what this session created (`radius.own`): every `serverElements` entry a database
  or view of yours, every `localElements` entry the element of a view of yours; with
  `SERVER_WITH_LOCAL_CHANGES`, on a profile that is not production; `modifiedElements` do not
  change it. Then read `removed` and `inserted` against that radius, and both `changes` again:
  once a database is gone from VDP, its elements left the catalog with `removed` empty in both
  responses — *verified: 9.5.1 (live, 2026-10-06)* — so only the second reading shows what went.
  Tell the human at once about anything you did not expect. One entry in `radius.not_own` —
  another team's new database, an orphan you did not make — and the body goes in a file and the call waits for the yes (`/denodo:vql`).
- Measured once, on a catalog of some 600 views: `changes` about 1 s, `VIEWS/synchronize`
  about 1.4 s when it inserts 10 and modifies none — *verified: 9.5.1 (live, 2026-09-10)*.
  Not a long-running job at that size, but a change to a catalog everybody shares.
- The user running it needs `METADATA` on the whole VDP catalog. Under a narrower account
  the marketplace treats what it cannot see as deleted and **removes it** —
  *unverified: 9.5 documentation only* (Synchronize with Virtual DataPort).

### A view in the marketplace is renamed, recreated or moved

What people add in the marketplace — tags, categories, descriptions edited there, custom
property values, endorsements — belongs to its **element**, and an element is found by
database and view name. A synchronisation sees a renamed view as one element gone
(`localElements`, old name) and one new (`serverElements`, new name), and acts on exactly
that: the old element is removed with everything on it, the new one arrives empty under a new
id. Nothing in either response says "renamed".

**Match the pair in the `synchronize` call and the element survives whole** — the same id,
and every tag, category, description, field description, property value and endorsement on
it — *verified: 9.5.1 (live, 2026-10-01)*. It is the REST form of the "Renamed elements"
drag-and-drop in the marketplace's own synchronisation dialog. The rename itself is
`/denodo:views`.

```bash
# verified: 9.5.1 (live, 2026-10-01)

# 0. BEFORE the rename: is the view in the marketplace, and what is on it?
#    id not null and inLocal: true → this template applies. Save the whole answer to a file:
#    it is the only copy of the element's metadata if anything goes wrong.
#    id null on every registered server (the two causes, above) → no element, nothing to
#    carry: rename, do not synchronise, and say so — the next synchronisation imports it
api get --env dev /public/api/view-details \
    --param databaseName=sales_analytics --param viewName=household_income_by_band
# → {"id":<view_id>,"inLocal":true,"tags":[…],"categories":[…],"endorsements":[…], …}

# 1. the rename, in VDP (/denodo:views):
#    ALTER VIEW household_income_by_band RENAME household_income_per_band;

# 2. the radius: the old name under localElements, the new one under serverElements
api get --env dev /public/api/element-management/VIEWS/changes

# 3. synchronise with the pair matched — localElement is the OLD name (what the marketplace
#    has), serverElement the NEW one (what VDP has now). Nothing else goes in the pair
api post --env dev /public/api/element-management/VIEWS/synchronize --json '{
    "proceedWithConflicts":"SERVER_WITH_LOCAL_CHANGES",
    "matchedElements":[{
        "localElement": {"databaseName":"sales_analytics","elementName":"household_income_by_band"},
        "serverElement":{"databaseName":"sales_analytics","elementName":"household_income_per_band"}}]}'
# → the pair is in neither "inserted" nor "removed"; everything else pending is

# 4. read back under the new name: the id from step 0, with its tags, categories, endorsements
api get --env dev /public/api/view-details \
    --param databaseName=sales_analytics --param viewName=household_income_per_band
```

- **No `type` in the pair.** The server's OpenAPI lists `type` (`View`, `Web service`, …) and
  `reason` in it, and any `type` — `View`, `VIEW`, `view` — fails the whole call with
  `400 "Invalid input JSON"` — *verified: 9.5.1 (live, 2026-10-01)*. The marketplace UI sends
  the two names and nothing else.
- **The response does not confirm the match.** A matched pair is simply absent from
  `inserted` and `removed` — and so is a pair the server ignored (moved views, below). Step 4
  is the confirmation: the old id under the new name.
- **Rename and matched synchronisation belong together, one right after the other.** Until
  step 3 runs, any synchronisation by anyone — the "Sync with VDP" button, a deployment that
  synchronises, a script — removes the old element and imports the new one empty. After that
  the step 0 file is all that is left. Even before that, from the moment VDP has no view of
  the old name, the element drops out of its tag's and its category's listings — consumers
  browsing by them no longer find it — *verified: 9.5.1 (live, 2026-10-01)*. Renaming a view
  that existed before this session is an `ALTER`, so it waits for the human's yes
  (`/denodo:vql`) — a request that names the rename is the task, not that yes. Ask for both in
  one go: the `ALTER` and the step 3 call, each written out; one yes covers the two. A view you
  created in this session is yours to rename, and its matched call is yours when the rest of the
  radius is too (Who sends it, above).
- **Matched, the old name is not a removal — and the call is still a `synchronize`:** whose it
  is depends on the whole radius, as for any other. When you cannot ask — the rename was a
  colleague's and the human is away — leave the body in a file and say in the message what an
  unmatched synchronisation by anyone would cost meanwhile; do not send it.
- **A pair is a rename only when you know it is one** — you renamed it, or the human says a
  colleague did. An old name under `localElements` beside a new one under `serverElements` in
  the same database is a hint, not proof. Matching two different views would hand one view's
  certification to another.
- Renamed by someone else, there is no step 0 to read: once VDP has no view of that name,
  `view-details` answers `404`, and the tag's and the category's own listings no longer show
  the element. The names are all the match needs; step 4 then shows what came across.
- What breaks outside the marketplace — every client reading the old name, and the view's own
  file bringing the old name back — is `/denodo:views`, "Renaming a view"; the human needs to
  hear both, whoever did the rename.

**Recreated under the same name — `DROP VIEW` then `CREATE VIEW` — needs nothing.** As long as
no synchronisation runs between the two, the marketplace never sees the gap: the element keeps
its id and everything on it — *verified: 9.5.1 (live, 2026-10-01)*. So the `DROP` and the
`CREATE` go in one file, applied in one run. `CREATE OR REPLACE` never leaves a gap at all.

**Moved to another database, the match is silently ignored.** A pair whose two
`databaseName`s differ changes nothing: neither name appears in `inserted` or `removed`, the
response says nothing, the old element stays under `localElements` and the new view is not
imported — *verified: 9.5.1 (live, 2026-10-01), twice*. The next synchronisation without the
pair removes the old element and imports the new one empty. No REST call keeps an element
across databases, so tell the human **before** the move what it costs, and if they go ahead,
build the new element before removing the old one: step 0's file; create the view in the
target database; a plain synchronisation (previous template, its rule included) — it only inserts; re-apply to
the new id what can honestly be re-applied, from the table below, and read it back; only then
drop the old view and synchronise again — that one only removes. Two synchronisations instead
of one, and in return the view never drops out of its tag and category, and the old element
stays whole until the new one is proven — *verified: 9.5.1 (live, 2026-10-01)*.

| What | Call — *verified: 9.5.1 (live, 2026-10-01)* | Note |
|---|---|---|
| marketplace tags | `POST /public/api/tags/{tagId}/views` with `[<newId>]` | adds |
| categories | `POST /public/api/category-management/categories/{id}/views` with `[<newId>]` | adds |
| description edited in the marketplace | `PUT /public/api/views` with `{"id":<newId>,"description":"…","descriptionType":"TEXT"}` | |
| field descriptions edited there | `PUT /public/api/views/fields` with `{"databaseName","viewName","fieldName","fieldDescription"}` | one call per field; step 0 has them under `schema[].description` — under `field.allFields` the same fields read empty |
| custom property values | `POST /public/api/property-management/views/{newId}/groups` with `[<groupId>, …]`, then `PUT /public/api/views/property-values` with `[{"propertyId","elementId":<newId>,"visualValue"}]` | the first call **replaces** the view's set of groups, and a group left out loses its values: send every group step 0 shows (`propertyInfo`; there is no `GET` for a view's groups — `405`). A value before its group is assigned is `500 "Incorrect number of updated tuples"`. Send what step 0 has under `visualValueToEdit`, not `visualValue`: a property with *Allow variables in value* shows `$element_name` already filled in there, and copying that freezes the old name |
| endorsements, warnings, deprecations | `POST /public/api/endorsement-management/views/{newId}/endorsements` with `{"comment":"…"}`; `…/warnings` and `…/deprecations` take the same body — *unverified: 9.5 documentation only* (the server's OpenAPI) | the human's call, not a default: each is somebody's statement, and a copy is yours, dated today — even under the same account, it claims a check made now on a view that just moved. List them, and re-create only the ones the human asks for once they have seen the list — "keep everything" said before anyone looked is not that |

### External element — a dashboard, job or contract from another tool

There is no `POST /external-elements`. An external element is *imported*: the marketplace
reads an interface view in VDP and creates, updates and deletes elements to match it. So the
chain runs VQL and REST alternately, and the whole block below carries one verification mark.

```bash
# verified: 9.5.1 (live, 2026-09-10) — the chain as a whole

# 0. the views this element will link to must already be in the marketplace catalog
#    (previous template) — otherwise step 4 fails and nothing is created
# 0b. the element type the VQL half names ('DASHBOARD') must be listed, or created (below)

# 1. provider type: the tool the metadata comes from. Multipart, but the icon is optional
api post --env dev /public/api/external-providers-types \
    --part 'request=json:{"name":"ACME_BI","visualName":"Acme BI"}'
# → 201 {"externalProviderTypeId":<provider_type_id>,"iconImage":null, …}
#   with a logo:  --part 'icon=@./acme.svg'
#   the next call answers 200, this one 201 — check 2xx, never a particular code
#   — verified: 9.5.1 (live, 2026-09-12)

# 2. the server that will read the contract. The interface view need not exist yet
api post --env dev /public/api/external-tool-servers \
    --json '{"type":"CUSTOM","name":"acme_bi_server","description":"Acme BI dashboards",
             "externalProviderTypeId":<provider_type_id>,
             "databaseName":"sales_analytics","viewName":"i_acme_bi_elements"}'
# → {"id":<tool_server_id>, …}

# 3. ask the marketplace for the contract it expects. NOT a file to apply as it stands:
#    the two CREATE TYPE come back usable verbatim, the interface view comes back
#    without SET IMPLEMENTATION and without FOLDER — you write the implementation
api get --env dev /public/api/external-tool-servers/<tool_server_id>/vql-metadata
# → a JSON string: CONNECT DATABASE …; two CREATE TYPE; CREATE INTERFACE VIEW (columns only)

# 4. import
api post --env dev /public/api/external-tool-servers/synchronize \
    --json '{"externalToolServerIds":[<tool_server_id>]}'
# → externalElementsAdded / Updated / Deleted, per server
```

**Step 4 is a `synchronize`, and the safety rule of `/denodo:vql` says stop and ask before
one — but the first import on a server you have just created cannot delete anything.** The
call deletes elements *absent from the snapshot*, and a server created in this same session
has imported none. So: your own new server, first import — go, and say in the summary what
was imported. **From the second import on, the confirmation is back**, because the interface
view is the whole picture and a row that stopped being selected is an element that gets
removed with its tags and categories. Read the current set first and show the human what is
about to disappear — the server's own elements are
`POST /public/api/search/external-elements/metadata` with `externalToolServerIds: [<id>]`
and the nine other mandatory fields — *verified: 9.5.1 (live, 2026-09-12)*.
There is no `GET …/external-tool-servers/{id}/external-elements`: that path is `404`.
None of this changes the tool: the call is stamped
`destructive: replace` either way, and on a `production` profile it is refused without
`--allow-destructive`, which only a human may add.

**Look each type up before creating it — they are different objects.** The element type, what
the asset *is*, is listed by `GET /public/api/external-elements-types`, which returns the name as
`externalElementTypeName` (sent as `name`) and has no `description`; the provider type, the tool
it *comes from*, by `GET /public/api/external-providers-types`. **That listing embeds every icon
as base64 and can be large** — read it into a file and project
`{externalProviderTypeId, name, visualName}` rather than letting it into the conversation —
*verified: 9.5.1 (live, 2026-09-10)*. Tableau and Power BI are the documented native tools: the
`REPORT` element type, the `TABLEAU` and `POWERBI` providers. Every other type a marketplace
lists (`DASHBOARD`, `ETL_JOB`, an `…_PROVIDER`) was created there, and another marketplace may
lack it — the template's `DASHBOARD` included. A new type is a marketplace-wide object that
everyone then sees. Step 1 of the chain above is skipped only when a listed provider type
really is the asset's tool; an element type the listing lacks is created before step 4 with
`POST /public/api/external-elements-types` — all six fields mandatory, `iconKey` a FontAwesome key.

The VQL half — the implementation behind the contract from step 3. **Its names are outside
the naming convention of `/denodo:vql` on purpose:** the interface view's name is part of
the contract you gave the tool server, and the three views under it are its implementation,
not integration-layer or business-entity objects. Keep them together in one folder and named
after the tool, as below; do not rename them to `iv_…` to match the table.



```sql
-- verified: 9.5.1 (live, 2026-10-06)
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

Four things here are load-bearing, each *verified: 9.5.1 (live, 2026-09-10)*:

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
| A new category's parent | `GET …/categories/tree` first; a *domain* the human names is a category of this tree, usually a root one. A live marketplace's tree is a taxonomy somebody designed — hang the new category inside the branch it belongs to. A **new top-level** category is a question for the human, not a default: it adds an axis to what everybody browsing sees. (`GET …/categories/{id}/potential-parent` is for moving an existing one) |
| Every numeric id | never a template, never memory: a `GET` in this session. Ids differ per installation and per server |
| View ids to assign to | `GET /public/api/view-details?databaseName=…&viewName=…`; `id:null` means synchronise first. Save the answer to a file and read `id`, `inLocal` and `inVDP` out of it with a script — it carries the view's whole field list and its connection URIs, and truncating it instead is how the three fields get missed |
| Whether the catalog may be synchronised | you, when the call with `--plan`, right before it, says `needs_yes: false` — both `changes` hold only databases and views you created in this session (`modifiedElements` aside) and the profile is not production; the human for any other radius — it is a shared catalog |
| Whether a view about to be renamed, recreated or moved is in the marketplace | `view-details` on it **before** the change — `id` not null and `inLocal: true`. The answer is also what to keep: it is the only copy of the element's metadata |
| Which removed element is which new one | you renamed it, or the human says so. The same database and the same columns are a hint, not proof |
| For an external element: the type | `GET /public/api/external-elements-types` — list it; create one if none fits |
| For an external element: id, name, url, timestamps | the source tool. `updated_at` is what drives updates — an element whose `updated_at` does not move is never refreshed |
| Which views the element links to | the human, plus their exact `database.view` — an association naming a view the marketplace does not know fails the whole import |
| Direction and role | `IN`/`OUT` plus free text (`consumes`, `feeds`, `validates`). The documentation calls `direction` the data-flow direction and the 360 graph draws its arrow by it, without saying from whose side; Denodo's own sample marks every association `OUT`, a dashboard that *reads* a view included, and what `IN` changes is *unverified*. Follow the marketplace's existing elements, say which you chose, and look at the arrow after the first import. The role is the label on the edge of the 360 graph |

Do not ask about property groups, endorsements, requests or personalisation — they are
marketplace features with their own screens, not part of creating these objects.

## Reference

- `references/tags.md` — the full tag surface, taking a tag off one view, importing VDP tags
  and why that call is the most destructive one here, webservice targets, `delete-multiple`.
- `references/categories.md` — the tree endpoints, moving a category, taking a view out of one,
  assignment from the view's side, what cascades.
- `references/external-elements.md` — the element and provider type surface, the association
  record in detail, element-to-element associations, what synchronisation adds, updates and
  deletes, and how to read `/details`.

The server is also its own reference: `GET /v3/api-docs` on the marketplace returns the whole
OpenAPI document, which settles any path or body this skill does not
cover.

## Verify

A `200` here means less than usual: assignments report failure inside a `200` body, and the
import reports what it did rather than whether it worked. Read the object back, from the
other side where there is one. Every read-back below — *verified: 9.5.1 (live, 2026-10-05)*; the external element's
`/details`, *verified: 9.5.1 (live, 2026-09-10)*.

| Question | Read-back |
|---|---|
| Did the tag/category land | `GET /public/api/tags/{id}` · `GET /public/api/category-management/categories/{id}` |
| Is the assignment real, from the tag's side | `GET /public/api/tags/{id}/elements` → `{"views":[…],"webservices":[…]}` |
| … from the category's side | `GET /public/api/category-management/categories/{id}/views` — **`offset` and `limit` are mandatory**, without them it is `400 MISSING_REQUEST_PARAMETER` |
| … from the view's side | `GET /public/api/views/{viewId}/tags` · `GET /public/api/category-management/views/{viewId}/categories` |
| Is the view in the catalog at all | `GET /public/api/view-details?databaseName=…&viewName=…` → `id`, `inLocal`, `inVDP` |
| Did a renamed view keep its element | `view-details` on the new name → the `id` the old name had, with its tags, categories and endorsements. The `synchronize` response cannot tell you: a matched pair and an ignored one look the same there |
| What a synchronisation would change | `GET /public/api/element-management/{DATABASES\|VIEWS}/changes` — **before**, not after |
| Did the import create what you meant | the `synchronize` response names each element: `externalElementsAdded/Updated/Deleted` with `originalExternalElementId` |
| Did the element import (read as you) | `GET /public/api/external-elements/{id}/details` — type, server, url, and its lineage. A consumer sees the element only with the Visualize permission of its element type — a new type adds its own column, which an administrator grants to roles (External element, in the Permissions tab of the marketplace's Server Set-Up) — plus `METADATA` on every view it links to and `CONNECT` on their databases: tell the human what a new type still needs |
| **Does the view show the element** | `GET /public/api/views/tree/external-elements/lineage?databaseName=…&viewName=…` — the question a human actually asked ("what consumes this?"), answered from the other end. The view node must resolve to `databaseName`/`viewName`, not stay a bare string |
| Is it really gone | `GET` it: `404` is the answer you want. The tool reports that as `ok:false` and exit `1`, so a verification script must treat `404` as success here rather than stopping — *verified: 9.5.1 (live, 2026-09-10)* |
| Which VDP tags are imported | `GET /public/api/tags/vdp/local` — a plain list of names. **Not** `inLocal` in `/tags/vdp/changes`: that flag means "a marketplace tag of this name exists", which is also true for an unrelated local tag — *verified: 9.5.1 (live, 2026-09-10)* |

## Common mistakes

| You did | Server says | Fix |
|---|---|---|
| any tag or view call with several VDP servers registered | `500 GENERIC "Session Expired."` | the profile has no `marketplace_server_id` — a human sets it, from `/public/api/configuration/servers`. `--param serverId=…` gets one call through in the meantime |
| the same on `/external-tool-servers` | `403`, empty | the same cause, a different code |
| read `id: null` from `view-details` as "not synchronised" | `200`, and the same body a wrong `serverId` produces | ask the other servers first; only then synchronise |
| `GET …/categories/{id}/views` without paging | `400 MISSING_REQUEST_PARAMETER` | `--param offset=0 --param limit=50` |
| `POST /tags` with a name that exists | `409`, empty body | look up by name first, then `PUT` |
| take the first element `nameFilter` returned | `200`, the wrong tag | the filter matches substrings and ignores case — compare `name` exactly |
| `POST /tags/{id}/views` for a view that is not synchronised | `200` and `[<view_id>]` | it is not an error and not an assignment — synchronise, then re-assign |
| read a `200` from an assignment as success | — | success is `[]`; a non-empty list is what failed |
| `POST /views/{id}/tags` to add one tag | `200` | that endpoint **replaces** the view's tags; use `/tags/{id}/views` |
| `DELETE` a parent category | `200` | its children went too — read `…/categories/tree` before offering it |
| `DELETE` the same tag twice | `500 GENERIC "Incorrect number of deleted tuples"` | it was already gone; categories answer `200` and servers `404` for the same thing |
| `synchronize` a tool server before the associated view is in the catalog | `400 INVALID_VDP_EXTERNAL_ELEMENT_METADATA "The view '…' does not exist"` | the view **does** exist in VDP — it is the marketplace copy that is missing. Synchronise the catalog |
| rename the association array type | `400 INVALID_EXTERNAL_ELEMENT_INTERFACE_VIEW … expected type external_element_association_array_type` | keep the contract's names |
| `LEFT OUTER JOIN` for elements without associations | `400 … Required field 'associated_element_id' is null` | `INNER JOIN` plus a `UNION ALL` branch with a NULL array |
| drop an element from a non-empty snapshot | `200`, and the element is **deleted** with its tags and categories | that is the contract: the interface view is the full picture, not a delta |
| empty the snapshot entirely to clear elements | `200`, nothing deleted | an empty result is treated as "no data", not "delete everything" — *verified: 9.5.1 (live, 2026-09-10)* |
| `DELETE` an external tool server to tidy up | `200` | every element it imported disappeared with it, tags and categories included |
| rename a view in VDP, then synchronise without `matchedElements` | `200`, old name under `removed`, new under `inserted` | the element went with every tag, category, description and endorsement on it; the new one is empty. Match the pair in the same call — and if it already ran, only a `view-details` saved before the rename can say what to re-apply |
| `"type":"View"` (or any `type`) in a matched pair | `400 "Invalid input JSON"` | the pair is `localElement` and `serverElement`, nothing else |
| match a view moved to another database | `200`, the pair in neither `inserted` nor `removed` | ignored, not applied: nothing happened. Re-apply from the saved `view-details` after a plain synchronisation |
| `POST /property-management/views/{id}/groups` to add one group | `200` | it **replaces** the view's groups, and the values of the ones left out are gone |

Destructive here is decided by method and path, not by the word in it: `DELETE` of a category
(with its children), of a tool server (with its elements), of an assignment (a tag or a category
off a view), `POST /tags/vdp/synchronize` (`references/tags.md`), every catalog `POST …/synchronize`
— `"SERVER"` mode and a rename with the pair left unmatched worst of all — and `POST
/views/{id}/tags` and `POST /property-management/views/{id}/groups`, which replace rather
than add. All of them are the human's call — `/denodo:vql` — except a catalog synchronisation
whose radius is yours (Who sends it) and the first import on a tool server you created in this
session.
