# Marketplace tags in full

Everything here is REST against `marketplace_url`, and every call takes `serverId` (see
`SKILL.md`). Marketplace tags are **not** VDP tags: `CREATE TAG` is `/denodo:catalog`.

## The surface

| Action | Call | Body | Answer |
|---|---|---|---|
| List all | `GET /public/api/tags` | | array of `{id, name, description, descriptionType, vdpTag}` |
| Search by name, paged | `GET /public/api/tag-management/tags` + `offset`, `limit`, `nameFilter` | | `{count, elements[]}` — `nameFilter` matches **substrings, case-insensitively**, so filter the result by exact `name` before using it |
| How many | `GET /public/api/tags/count` | | number |
| One | `GET /public/api/tags/{id}` | | the tag, `404` when gone |
| Create | `POST /public/api/tags` | `{name, description, descriptionType}` — all three | `200` + tag with `id` |
| Update | `PUT /public/api/tags` | `{id, name, description, descriptionType}` | `200`, empty body |
| Delete | `DELETE /public/api/tags/{id}` | | `200`; again → `500` |
| Delete several | `DELETE /public/api/tags/delete-multiple` + `tagsId` | | |
| Assign to views (**adds**) | `POST /public/api/tags/{id}/views` | `[viewId, …]` | `200` + ids **not** assigned |
| Unassign one | `DELETE /public/api/tags/{id}/views/{viewId}` | | `200` |
| Unassign several | `DELETE /public/api/tags/{id}/views` | `[viewId, …]` | |
| Replace a view's tags (**replaces**) | `POST /public/api/views/{viewId}/tags` + `tagsId` | | destroys the view's other tags |
| A view's tags | `GET /public/api/views/{viewId}/tags` | | array of tags |
| Everything a tag is on | `GET /public/api/tags/{id}/elements` | | `{views[], webservices[]}` |
| External elements | `POST`/`GET`/`DELETE /public/api/tags/{id}/external-elements` | `[elementId]` | assign answers with an **empty body**, not a list |
| Web services | `POST`/`DELETE /public/api/tags/{id}/webservices` | `[webserviceId]` | |
| Tags a view may still get | `GET /public/api/elements/{viewId}/view/available-tags` | | |

`descriptionType` is `TEXT` or `RICH_TEXT`; `RICH_TEXT` renders HTML in the marketplace UI,
which is how the demo content carries formatted descriptions. All of the above is
*verified: 9.5.1 (стенд, 2026-09-10)* except `delete-multiple`, the webservice endpoints and
`available-tags`, which are *unverified: OpenAPI of the 9.5.1 server*.

## Importing VDP tags — the most destructive call in this skill

VDP tags can be copied into the marketplace, where they become read-only mirrors
(`vdpTag: true`). Their assignments come from VDP, so `ALTER TAG … ADD_TO` in
`/denodo:catalog` shows up here after the next import.

| Call | What it is |
|---|---|
| `GET /public/api/tags/vdp` | tags that exist in VDP, read live |
| `GET /public/api/tags/vdp/local` | **names already imported** — a plain list of strings |
| `GET /public/api/tags/vdp/changes` | per tag: `name`, `description`, `inLocal`, `nameConflict` |
| `POST /public/api/tags/vdp/synchronize` | `{"vdpTags":[name, …]}` — the import |

**The body is the complete set of imported tags, not an addition.** Every imported tag whose
name is absent from that list is deleted, together with what it carried. The UI hides this by
ticking the previously imported tags for you; the API has no such default —
*unverified here: the destruction itself was verified during spike T11 on the 9.5.1 stand of
2026-09-08, and this stand's demo content was not spent re-proving it.* The safe form:

```bash
# verified: 9.5.1 (стенд, 2026-09-10) — reading the list; the POST is the human's call
api get --env lab /public/api/tags/vdp/local --param serverId=306
# → ["business_views","customers", …]     ← send these back plus the new one
```

Two traps around it, both *verified: 9.5.1 (стенд, 2026-09-10)*:

- **`inLocal` in `/changes` does not mean "imported".** It means a marketplace tag of that
  name exists — including an unrelated local one. On this stand `sensitive` reports
  `inLocal: true, nameConflict: true` while `/tags/vdp/local` does not list it, because a
  separate marketplace tag `Sensitive` exists. Names collide case-insensitively. **What the
  import then does with the local namesake — refuse it, replace it, merge into it — is
  *unverified*:** finding out costs someone else's tag, so ask the human whether to rename
  one of the two first.
- **An imported tag brings its VDP assignments, and no more.** A VDP tag assigned to nothing
  arrives in the marketplace empty, which usually is not what the request meant. Check
  `GET_VIEW_TAGS()` in VDP (`/denodo:catalog`) before importing, and if the tag is bare, the
  work belongs in VDP first.
- **The list you read has a short shelf life.** Between reading `/tags/vdp/local` and posting
  it, anyone importing another tag loses it, and the call answers `200` with no body — there
  is nothing in the response to notice it by.

There is no `proceedWithConflicts` here and no diff of what would be removed. That is the
difference from `element-management/…/synchronize`, where the radius is measurable before the
call: this one you cannot check, only re-read afterwards.

## Read-only mirrors

An imported tag rejects every change with `403` and an empty body: `PUT`, assignment,
unassignment. `DELETE` answers `500 "Incorrect number of deleted tuples"` and the tag stays.
Change it in VDP instead (`/denodo:catalog`) — *T11 report, 9.5.1 stand of 2026-09-08*.
