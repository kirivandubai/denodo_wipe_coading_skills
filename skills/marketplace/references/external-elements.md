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
the code the interface view will repeat verbatim — note that the **listing** calls the same
thing `externalElementTypeName`, so the field you send and the field you read back have
different names. `visualName` is what the UI shows,
`iconKey` is a FontAwesome key (`fas fa-cube`). The OpenAPI document marks all six required
while the documentation calls `description` optional; send all six. Duplicate `name` → `409`.

### Provider type

**Check the 28 built-in ones first** (`GET /public/api/external-providers-types`):
`AIRFLOW_PROVIDER`, `GITHUB_PROVIDER`, `TABLEAU`, `POWERBI`, `QLIK_PROVIDER`,
`LOOKER_PROVIDER`, `COLLIBRA_PROVIDER`, `DATABRICKS_PROVIDER`, `SNOWFLAKE_PROVIDER`,
`INFORMATICA_PROVIDER`, `FIVETRAN_PROVIDER`, `MATILLION_PROVIDER`, `TALEND_PROVIDER`,
`JENKINS_PROVIDER`, `JUPYTER_PROVIDER`, `N8N_PROVIDER`, `MCP_PROVIDER`, `SERVICENOW_PROVIDER`,
`ATLAN_PROVIDER`, `AWS_GLUE_PROVIDER`, `FABRIC_PROVIDER`, `CONFLUENT_PROVIDER`,
`ABINITIO_PROVIDER`, `T24_TEMENOS_PROVIDER`, `SCHEDULER_PROVIDER`, `DENODO_DQ_PROVIDER`,
`DATA_PRODUCT_PROVIDER`, `GLOSSARY_PROVIDER` — *verified: 9.5.1 (стенд, 2026-09-10)*. They
arrive with the vendor's icon; a new one is a marketplace-wide object that everybody sees,
and one created without an icon stands in that shared list logo-less next to the rest. The
listing embeds those icons as base64 and is ~290 KB on 9.5.1: save it and project
`{externalProviderTypeId, name, visualName}`.

**"None fits" is decided by whose logo ends up on the card.** A provider type is what the
consumer sees as the origin of the asset, so reusing `TABLEAU` for a dashboard that is not
Tableau's puts another vendor's name and logo on it — a false statement about provenance,
and cheaper only in calls. A own type without an icon is the better trade; it stands
logo-less, which is honest. `name` is not validated against a shape: every built-in one is
`UPPER_SNAKE`, and a lowercase name is accepted just the same — *verified: 9.5.1 (стенд,
2026-09-12)*.

Creating one is multipart: a part named `request` of type `application/json` carrying
`{name, visualName}`,
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

Two gaps the source tool usually leaves, and both are yours to close: a date without a time
(the columns are `timestamp`) — take midnight and write the convention down next to the
view, because switching later to end-of-day moves `updated_at` backwards for the same day
and the next import silently updates nothing; and a missing `description` — it is optional
in the contract but it is the first thing a consumer reads, so build one out of facts you
already have (what the asset is, which view it reads) rather than leaving it empty or
inventing an audience for it.
| `associations` | `external_element_association_array_type` | no | the 360 graph edges |

Association record: `associated_element_id`, `external_tool_server_name`,
`associated_element_type`, `direction`, `role`.

- `associated_element_type` is `VIEW` or `EXTERNAL_ELEMENT`.
- For `VIEW`, `associated_element_id` is `database.view` and `external_tool_server_name` is
  NULL. **The view must already be in the marketplace catalog** — otherwise the whole import
  fails with `400 INVALID_VDP_EXTERNAL_ELEMENT_METADATA "The view '…' does not exist"`, a
  message that means "not in the marketplace copy", not "not in VDP" —
  *verified: 9.5.1 (стенд, 2026-09-10)*.
- For `EXTERNAL_ELEMENT`, `associated_element_id` is the other element's **`id` from its
  interface view** — the string you wrote there, never the numeric marketplace id, which does
  not exist until that element has been imported — and `external_tool_server_name` names the
  tool server it lives on. That is how a pipeline links to the contract it implements —
  *verified: 9.5.1 (стенд, 2026-09-10)*. Two consequences: elements from two different tools
  need two provider types and therefore **two tool servers**, and the server holding the
  target must be imported **first**, or the association has nothing to resolve to.
- `direction` is `IN` or `OUT` — *documentation 9.5*. It reads from the external element
  outwards and is not the direction of the data: in the demo content of the 9.5.1 stand a
  dashboard that *reads* a view carries `OUT` with role `consumes`, and a pipeline that
  *writes* one carries `OUT` with role `feeds`. Every association there, and every one
  created while verifying this skill, is `OUT`; no `IN` example exists on the stand, so what
  the marketplace does differently with it is *unverified*. `role` is free text and is the
  label drawn on the edge.

**The type names are part of the contract.** Renaming
`external_element_association_array_type` fails validation with
`400 INVALID_EXTERNAL_ELEMENT_INTERFACE_VIEW … expected type
external_element_association_array_type, but found …`. Types belong to a database, so the
fixed names cost nothing.

**Building the array.** `NEST(...)` over the association rows, cast to the array type, with a
`GROUP BY` over every non-association column. When every element has at least one
association, the `INNER JOIN` alone is the whole implementation. The second branch below is
needed **only** when some element has none: a `LEFT OUTER JOIN` would give `NEST` a row of
NULLs and the import rejects the element
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

All five below are *verified: 9.5.1 (стенд, 2026-09-10)* except the `PUT` row, which is
*unverified: OpenAPI of the 9.5.1 server*.

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
