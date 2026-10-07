# External elements in full

An external element is an asset owned by another tool — a dashboard, a pipeline, a data
contract, an AI agent — that the marketplace shows next to the views it touches. It is
**imported, never created**: `POST /public/api/external-elements` does not exist. The
marketplace queries an interface view in VDP and makes its own copy match it.

That inverts the usual order: the VQL comes first and the REST call only triggers the read.

## The four moving parts

| Part | Created by | Scope |
|---|---|---|
| Element type (`DASHBOARD`, `PIPELINE`, …) | `POST /public/api/external-elements-types`, or one the listing already has | the whole marketplace |
| Provider type (the tool: Acme BI, Airflow) | `POST /public/api/external-providers-types`, multipart | the whole marketplace |
| External tool server | `POST /public/api/external-tool-servers`, `type: CUSTOM` | one VDP server |
| The elements themselves | `POST /public/api/external-tool-servers/synchronize` | one tool server |

Element types are listed by `GET /public/api/external-elements-types`. `REPORT` (Tableau and
Power BI reports) is the documented native one; the rest a marketplace lists were created
there. Reuse one that fits; a new type is a marketplace-wide object.

### Element type

`{name, description, visualName, iconKey, iconColorCode, reversedIconColorCode}`. `name` is
the code the interface view will repeat verbatim — note that the **listing** calls the same
thing `externalElementTypeName`, so the field you send and the field you read back have
different names. `visualName` is what the UI shows,
`iconKey` is a FontAwesome key (`fas fa-cube`). The OpenAPI document marks all six required
while the documentation calls `description` optional; send all six. Duplicate `name` → `409`.

### Provider type

**Check the listed ones first** (`GET /public/api/external-providers-types`): `TABLEAU` and
`POWERBI` are the documented native ones, the rest a marketplace lists were created there.
Existing ones usually carry their vendor's icon; a new one is a marketplace-wide object that
everybody sees, and one created without an icon stands in that shared list logo-less next to
the rest.

**"None fits" is decided by whose logo ends up on the card.** A provider type is what the
consumer sees as the origin of the asset, so reusing `TABLEAU` for a dashboard that is not
Tableau's puts another vendor's name and logo on it — a false statement about provenance,
and cheaper only in calls. A type of your own without an icon is the better trade; it stands
logo-less, which is honest. `name` is not validated against a shape: the native ones and the
documentation's examples are `UPPER_SNAKE`, and a lowercase name is accepted just the same —
*verified: 9.5.1 (live, 2026-09-12)*.

Creating one is multipart: a part named `request` of type `application/json` carrying
`{name, visualName}`,
and optionally a part `icon` with an `.svg` or `.png`. **The icon is optional** — the call
returns `201` with `iconImage: null` without it, though the documentation
calls it mandatory — *verified: 9.5.1 (live, 2026-09-10)*. Through the tool:

```bash
# verified: 9.5.1 (live, 2026-09-10) — the request part; the icon part, 2026-09-12
--part 'request=json:{"name":"ACME_BI","visualName":"Acme BI"}'  --part 'icon=@./acme.svg'
```

### Tool server

`{type:"CUSTOM", name, description?, externalProviderTypeId, databaseName, viewName}`. It may
name an interface view that does not exist yet — the view is only read at synchronisation
time. Duplicate name → `409 SERVER_DUPLICATED`, the one error here that carries a message.
`GET /public/api/external-tool-servers` lists servers **without** `databaseName`/`viewName`;
only `GET …/{id}` has them, so match a server to a template by name.

`GET …/{id}/changes` is for Tableau and Power BI only and answers
`400 INVALID_EXTERNAL_TOOL_SERVER` on a CUSTOM server. `…/{id}/synchronize` expects a prior
`changes` in the same session, so the call to use is the plural
`POST /public/api/external-tool-servers/synchronize` with `{"externalToolServerIds":[id]}` —
it takes exactly the servers you name, unlike `synchronize-all`.

## The contract

`GET /public/api/external-tool-servers/{id}/vql-metadata` returns VQL **as a JSON string**:
`CONNECT DATABASE`, two `CREATE OR REPLACE TYPE`, and the `CREATE OR REPLACE INTERFACE VIEW`.
Skip the `CONNECT DATABASE` line if the session is already in that database.

| Column | Type | Required | Notes |
|---|---|---|---|
| `id` | text | yes | unique per tool server; comes back as `originalExternalElementId` |
| `name` | text | yes | shown in the marketplace |
| `description` | text | no | plain text; whether HTML from the view renders is *unverified* (the documentation states HTML only for the description edited in the marketplace) |
| `external_element_type` | text | yes | an element type's `name`, character for character |
| `url` | text | no | becomes the "open in tool" link |
| `created_at` | timestamp | yes | |
| `updated_at` | timestamp | yes | **drives updates** — an element whose value has not moved is never refreshed |
| `associations` | `external_element_association_array_type` | no | the 360 graph edges |

Two gaps the source tool usually leaves, and both are yours to close: a date without a time
(the columns are `timestamp`) — take midnight and write the convention down next to the
view, because switching later to end-of-day moves `updated_at` backwards for the same day
and the next import silently updates nothing; and a missing `description` — it is optional
in the contract but it is the first thing a consumer reads, so build one out of facts you
already have (what the asset is, which view it reads) rather than leaving it empty or
inventing an audience for it.

Association record: `associated_element_id`, `external_tool_server_name`,
`associated_element_type`, `direction`, `role`.

- `associated_element_type` is `VIEW` or `EXTERNAL_ELEMENT`.
- For `VIEW`, `associated_element_id` is `database.view` and `external_tool_server_name` is
  NULL. **The view must already be in the marketplace catalog** — otherwise the whole import
  fails with `400 INVALID_VDP_EXTERNAL_ELEMENT_METADATA "The view '…' does not exist"`, a
  message that means "not in the marketplace copy", not "not in VDP" —
  *verified: 9.5.1 (live, 2026-09-10)*.
- For `EXTERNAL_ELEMENT`, `associated_element_id` is the other element's **`id` from its
  interface view** — the string you wrote there, never the numeric marketplace id, which does
  not exist until that element has been imported — and `external_tool_server_name` names the
  tool server it lives on. That is how a pipeline links to the contract it implements —
  *verified: 9.5.1 (live, 2026-09-10)*. Two consequences: elements from two different tools
  need two provider types and therefore **two tool servers**, and the server holding the
  target must be imported **first**, or the association has nothing to resolve to.
- `direction` is `IN` or `OUT`, which the documentation calls the data-flow direction; the 360
  graph draws its arrow by it, and neither page says from whose side —
  *unverified: 9.5 documentation only*. A Denodo-authored sample implementation of asset
  extensions marks every association `OUT`: a dashboard that *reads* a view with role
  `consumes`, a pipeline that *writes* one with role `feeds`. What the marketplace does
  differently with `IN` is *unverified*. Follow the marketplace's existing elements, say which
  you chose, and look at the arrow after the first import. `role` is free text and is the
  label drawn on the edge.

**Building the array.** `NEST(...)` over the association rows, cast to the array type, with a
`GROUP BY` over every non-association column. When every element has at least one
association, the `INNER JOIN` alone is the whole implementation. The second branch below is
needed **only** when some element has none: a `LEFT OUTER JOIN` would give `NEST` a row of
NULLs and the import rejects the element
(`400 … Required field 'associated_element_id' is null … association index 0`):

```sql
-- verified: 9.5.1 (live, 2026-09-10)
    SELECT … CAST('external_element_association_array_type',
                  NEST(a.associated_element_id, a.external_tool_server_name,
                       a.associated_element_type, a.direction, a.role)) AS associations
      FROM meta m INNER JOIN assoc a ON m.id = a.owner_id
     GROUP BY m.id, m.name, m.description, m.external_element_type, m.url,
              m.created_at, m.updated_at
     UNION ALL
    SELECT … CAST('external_element_association_array_type', NULL) AS associations
      FROM meta m2
     WHERE m2.id NOT IN ( SELECT owner_id FROM assoc )
```

## What synchronisation does

The response is per server: `externalElementsAdded`, `externalElementsUpdated`,
`externalElementsDeleted`, each naming elements by both ids. All of the following are
*verified: 9.5.1 (live, 2026-09-10)*:

- **Added** — an `id` the marketplace has not seen on this server.
- **Updated** — an existing `id` whose `updated_at` moved forward. Tags, categories and
  descriptions edited in the marketplace survive an update that does not touch them.
- **Deleted** — an existing element **absent from the snapshot**. It goes with its tags and
  categories. The interface view is the whole picture, not a delta.
- **An empty snapshot deletes nothing.** Zero rows is read as "no data", not "delete
  everything" — a guard worth knowing, and the reason you cannot clear elements by emptying
  the view. Remove the tool server instead.
- Re-running with nothing changed is a clean no-op: three empty lists.
- `DELETE /public/api/external-tool-servers/{id}` removes the server **and every element it
  imported**, assignments included; repeating it answers `404`. Provider and element types
  answer `404` on a repeat too.

## Reading an element back

All five below are *verified: 9.5.1 (live, 2026-09-10)* except the `PUT` row, which is
*unverified: 9.5 documentation only* (the server's OpenAPI).

| Call | Gives |
|---|---|
| `GET /public/api/external-elements/{id}/details` | the card: type, provider, tool server, attribute groups (`<type>_default` is created automatically from `url`), and `edges`/`nodes` of its lineage |
| `GET /public/api/views/tree/external-elements/lineage?databaseName=…&viewName=…` | the same graph **from the view's side** — the answer to "what consumes this view" |
| `POST /public/api/search/external-elements/metadata` | search by name. **Ten fields are mandatory** and a missing one answers `400` with `{"count":null,"elements":[]}` — no code, no message: `text`, `externalElementTypeIds`, `categoryIds`, `tagIds`, `externalToolServerIds`, `withEndorsements`, `withWarnings`, `withDeprecations`, `offset`, `limit`. Empty arrays and `false` are what "no filter" means. `whereToSearchList` (`ELEMENT_NAME`, `ELEMENT_DESC`, …) and `searchType` (`EXACT_MATCH`, `ALL_WORDS`, `ANY_WORDS`) are the optional ones |
| `GET /public/api/browse/elements/type/EXTERNAL_ELEMENTS` | what a consumer browsing sees — `offset` and `limit` are **mandatory** (`400 MISSING_REQUEST_PARAMETER` without them) |
| `PUT /public/api/external-elements/{id}/name`, `…/description`, `…/properties/{propertyId}` | marketplace-side edits, which survive later imports |

In the lineage answer the view node must carry `databaseName`, `viewName` and `viewSubtype`.
A node that stayed a bare string means the association named something the marketplace could
not resolve.
