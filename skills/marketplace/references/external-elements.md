# External elements in full

An external element is an asset owned by another tool — a dashboard, a pipeline, a data
contract, an AI agent — that the marketplace shows next to the views it touches. It is
**imported, never created**: `POST /public/api/external-elements` does not exist. The
marketplace queries an interface view in VDP and makes its own copy match it.

That inverts the usual order: the VQL comes first and the REST call only triggers the read.

## The four moving parts

| Part | Created by | Scope |
|---|---|---|
| Element type (`DASHBOARD`, `PIPELINE`, …) | `POST /public/api/external-elements-types`, or one of the 24 built in | the whole marketplace |
| Provider type (the tool: Acme BI, Airflow) | `POST /public/api/external-providers-types`, multipart | the whole marketplace |
| External tool server | `POST /public/api/external-tool-servers`, `type: CUSTOM` | one VDP server |
| The elements themselves | `POST /public/api/external-tool-servers/synchronize` | one tool server |

Built-in element types on 9.5.1, from `GET /public/api/external-elements-types`:
`AI_AGENT, AI_LLM, AI_SKILL, APPLICATION, CATALOG, DASHBOARD, DATA_CONTRACT, DATA_PRODUCT,
DOCUMENT, ETL_JOB, GLOSSARY, KNOWLEDGE_BASE, NOTEBOOK, PIPELINE, POLICY, PROMPT, QUALITY_RULE,
REPORT, RULE, SCHEDULER_JOB, SQL_SCRIPT, STORED_PROCEDURE, STREAM, WORKFLOW` —
*verified: 9.5.1 (стенд, 2026-09-10)*. Reuse one; a new type is a marketplace-wide object.

### Element type

`{name, description, visualName, iconKey, iconColorCode, reversedIconColorCode}`. `name` is
the code the interface view will repeat verbatim, `visualName` is what the UI shows,
`iconKey` is a FontAwesome key (`fas fa-cube`). The OpenAPI document marks all six required
while the documentation calls `description` optional; send all six. Duplicate `name` → `409`.

### Provider type

Multipart: a part named `request` of type `application/json` carrying `{name, visualName}`,
and optionally a part `icon` with an `.svg` or `.png`. **The icon is optional** — the call
returns `201` with `iconImage: null` without it, though both the documentation and spike T11
call it mandatory — *verified: 9.5.1 (стенд, 2026-09-10)*. Through the tool:

```bash
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
| `description` | text | no | HTML is fine and renders |
| `external_element_type` | text | yes | an element type's `name`, character for character |
| `url` | text | no | becomes the "open in tool" link |
| `created_at` | timestamp | yes | |
| `updated_at` | timestamp | yes | **drives updates** — an element whose value has not moved is never refreshed |
| `associations` | `external_element_association_array_type` | no | the 360 graph edges |

Association record: `associated_element_id`, `external_tool_server_name`,
`associated_element_type`, `direction`, `role`.

- `associated_element_type` is `VIEW` or `EXTERNAL_ELEMENT`.
- For `VIEW`, `associated_element_id` is `database.view` and `external_tool_server_name` is
  NULL. **The view must already be in the marketplace catalog** — otherwise the whole import
  fails with `400 INVALID_VDP_EXTERNAL_ELEMENT_METADATA "The view '…' does not exist"`, a
  message that means "not in the marketplace copy", not "not in VDP" —
  *verified: 9.5.1 (стенд, 2026-09-10)*.
- For `EXTERNAL_ELEMENT`, `associated_element_id` is the other element's `id` and
  `external_tool_server_name` names the server it lives on — that is how a contract links to
  the pipeline that implements it. *unverified here: read off the demo content of the 9.5.1
  stand, not created by hand.*
- `direction` is `IN` or `OUT`; `role` is free text and is the label drawn on the edge.

**The type names are part of the contract.** Renaming
`external_element_association_array_type` fails validation with
`400 INVALID_EXTERNAL_ELEMENT_INTERFACE_VIEW … expected type
external_element_association_array_type, but found …`. Types belong to a database, so the
fixed names cost nothing.

**Building the array.** `NEST(...)` over the association rows, cast to the array type, with a
`GROUP BY` over every non-association column. An element with no associations needs a second
branch, because a `LEFT OUTER JOIN` gives `NEST` a row of NULLs and the import rejects it
(`400 … Required field 'associated_element_id' is null … association index 0`):

```sql
-- verified: 9.5.1 (стенд, 2026-09-10)
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
*verified: 9.5.1 (стенд, 2026-09-10)*:

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

| Call | Gives |
|---|---|
| `GET /public/api/external-elements/{id}/details` | the card: type, provider, tool server, attribute groups (`<type>_default` is created automatically from `url`), and `edges`/`nodes` of its lineage |
| `GET /public/api/views/tree/external-elements/lineage?databaseName=…&viewName=…` | the same graph **from the view's side** — the answer to "what consumes this view" |
| `POST /public/api/search/external-elements/metadata` | search by name: `{text, whereToSearchList:["ELEMENT_NAME"], searchType:"EXACT_MATCH", offset, limit}` plus empty filter lists |
| `GET /public/api/browse/elements/type/EXTERNAL_ELEMENTS` | what a consumer browsing sees |
| `PUT /public/api/external-elements/{id}/name`, `…/description`, `…/properties/{propertyId}` | marketplace-side edits, which survive later imports |

In the lineage answer the view node must carry `databaseName`, `viewName` and `viewSubtype`.
A node that stayed a bare string means the association named something the marketplace could
not resolve.
