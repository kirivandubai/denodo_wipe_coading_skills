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
| Unassign one | `DELETE /public/api/tags/{id}/views/{viewId}` | | `200`, empty, whether it was assigned or not |
| Unassign several | `DELETE /public/api/tags/{id}/views` | `[viewId, …]` | |
| Replace a view's tags (**replaces**) | `POST /public/api/views/{viewId}/tags` + `tagsId` | | destroys the view's other tags |
| A view's tags | `GET /public/api/views/{viewId}/tags` | | array of tags |
| Everything a tag is on | `GET /public/api/tags/{id}/elements` | | `{views[], webservices[]}` |
| External elements | `POST`/`GET`/`DELETE /public/api/tags/{id}/external-elements` | `[elementId]` | assign answers with an **empty body**, not a list |
| Web services | `POST`/`DELETE /public/api/tags/{id}/webservices` | `[webserviceId]` | |
| Tags a view may still get | `GET /public/api/elements/{viewId}/view/available-tags` | | |

`descriptionType` is `TEXT` or `RICH_TEXT`; `RICH_TEXT` renders HTML in the marketplace UI.
All of the above is
*verified: 9.5.1 (live, 2026-09-10)* except `delete-multiple`, the webservice endpoints and
`available-tags`, which are *unverified: 9.5 documentation only* (the server's OpenAPI).

## Taking a tag off one view

```bash
# verified: 9.5.1 (live, 2026-10-07)
# 1. the view: its id on the server that holds it — per database and view, never per name
api get --env dev /public/api/view-details --param databaseName=sales_analytics --param viewName=household_income_by_band
# 2. what the tag is on now — the views that keep it
api get --env dev /public/api/tags/<tag_id>/elements
# 3. off this view only
api delete --env dev /public/api/tags/<tag_id>/views/<view_id>
# 4. read back from the view's side
api get --env dev /public/api/views/<view_id>/tags
```

- **One assignment goes; the tag and the view stay.** Deleting the tag instead takes it off
  every view it is on; `POST /views/{id}/tags` with the rest of the set rewrites the view's tags
  and races anyone tagging it meanwhile. The `DELETE` per assignment is the call.
- The tag by its **exact** name (`nameFilter` matches substrings — `pii` also finds
  `pii_legacy`), the view by `databaseName` and `viewName`: the same view name in two
  databases is two elements, and the id from step 1 is the only handle.
- The `DELETE` answers `200` and an empty body whether the assignment existed or not: step 4
  is the answer — the tag gone from the view, the views of step 2 still there.
- **An imported VDP tag** (`vdpTag: true`) refuses with `403`: it comes off in VDP (`ALTER TAG
  … REMOVE_FROM`, `/denodo:catalog`) and the marketplace copy follows at the next import of VDP
  tags — the call below, the human's.
- **Every unassignment waits for the human's yes** — one your own call made in this
  conversation too: the two named exceptions (`SKILL.md`, **Who sends it**) are not this one.
  Show the `DELETE` with what step 2 keeps. When the yes comes late, read step 1
  and 2 again right before the `DELETE`: ids do not move, assignments do. A label that is not
  a tag — a deprecation endorsement, `deprecations` in `view-details` — is another object.

## Importing VDP tags — the most destructive call in this skill

VDP tags can be copied into the marketplace, where they become read-only mirrors
(`vdpTag: true`). Their assignments come from VDP, so `ALTER TAG … ADD_TO` in
`/denodo:catalog` shows up here after the next import. Only with the Semantics FeaturePack
(Enterprise Plus; the About dialog of Design Studio or the Data Marketplace shows the bundle):
without it there is no import, and a label the consumer must see in the marketplace is a
marketplace tag.

| Call | What it is |
|---|---|
| `GET /public/api/tags/vdp` | tags that exist in VDP, read live |
| `GET /public/api/tags/vdp/local` | **names already imported** — a plain list of strings |
| `GET /public/api/tags/vdp/changes` | per tag: `name`, `description`, `inLocal`, `nameConflict` |
| `POST /public/api/tags/vdp/synchronize` | `{"vdpTags":[name, …]}` — the import |

**The body is the complete set of imported tags, not an addition.** Every imported tag whose
name is absent from that list is deleted, together with what it carried. The UI hides this by
ticking the previously imported tags for you; the API has no such default —
*verified: 9.5.1 (live, 2026-09-08) — the deletion was observed once and is
deliberately not re-proven on every run, because it costs existing tags.* The safe form:

```bash
# verified: 9.5.1 (live, 2026-10-07) — reading the list; the POST is the human's call
api get --env dev /public/api/tags/vdp/local
# → ["finance","hr_restricted", …]     ← send these back plus the new one
```

Two traps around it, both *verified: 9.5.1 (live, 2026-09-10)*:

- **`inLocal` in `/changes` does not mean "imported".** It means a marketplace tag of that
  name exists — including an unrelated local one: a VDP tag `finance` reports `inLocal: true,
  nameConflict: true`, while `/tags/vdp/local` does not list it, when a separate marketplace
  tag `Finance` exists. Names collide case-insensitively. **What the import then does with the local namesake — refuse it,
  replace it, merge into it — is *unverified*:** the UI never offers it (the documentation: its
  check box is disabled when a marketplace tag of that name exists), and finding out what the
  API does costs someone else's tag, so ask the human whether to rename one of the two first.
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
Change it in VDP instead (`/denodo:catalog`) — *verified: 9.5.1 (live, 2026-09-08)*.
