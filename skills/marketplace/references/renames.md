# Renamed, recreated or moved views in full

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
#    id null on every registered server (SKILL.md, rule 2) → no element, nothing to
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
  radius is too (`SKILL.md`, **Who sends it**).
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
target database; a plain synchronisation (`SKILL.md`, **Who sends it** included) — it only inserts; re-apply to
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
