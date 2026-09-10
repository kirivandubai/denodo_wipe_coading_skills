# Categories in full

A category is a folder for consumers browsing the marketplace: a tree, not a flat list, and
a view or external element may sit in several of them. Categories are the one family here
that is **not** scoped to a VDP server — they answer without `serverId` — but pass it anyway
so every call in a file looks the same.

## The surface

| Action | Call | Body / params | Answer |
|---|---|---|---|
| Whole tree | `GET /public/api/category-management/categories/tree` | | nested `{id, name, description, parentId, children[]}` |
| Flat list | `GET /public/api/category-management/categories` | | array |
| Paged list | `POST /public/api/category-management/categories/list` | paging body | |
| Count | `GET /public/api/category-management/categories/count` | | number |
| One | `GET /public/api/category-management/categories/{id}` | | `404` when gone |
| Create | `POST /public/api/category-management/categories` | `{name, description, descriptionType, parentId?}` | `200` + `{id, parentId, path}` |
| Update | `PUT /public/api/category-management/categories/{id}` | `{name, description, descriptionType}` — `parentId` may be omitted | `200` |
| Move | `POST /public/api/category-management/category/change-parent` | | |
| Where it may move | `GET /public/api/category-management/categories/{id}/potential-parent` | | the subtree cannot be its own parent |
| Children | `GET`/`DELETE /public/api/category-management/categories/{id}/children` | | |
| Delete | `DELETE /public/api/category-management/categories/{id}` | | `200`; again → `200` |
| Delete several | `DELETE /public/api/category-management/categories` + `categoryIds` | | |
| Assign views (**adds**) | `POST /public/api/category-management/categories/{id}/views` | `[viewId, …]` | `200` + ids **not** assigned |
| What is in a category | `GET /public/api/category-management/categories/{id}/views` | `offset` and `limit` **mandatory** | `400 MISSING_REQUEST_PARAMETER` without them |
| Unassign | `DELETE /public/api/category-management/categories/{id}/views/{viewId}` or `…/views?elementIds=` | | |
| A view's categories | `GET /public/api/category-management/views/{viewId}/categories` | | |
| Replace a view's categories (**replaces**) | `POST /public/api/category-management/views/{id}/categories` | | wipes the others |
| Add to a view's categories (**adds**) | `POST /public/api/category-management/add/views/{id}/categories` | | |
| External elements | `GET`/`POST`/`DELETE /public/api/category-management/categories/{id}/external-elements` | `[elementId]` | assign answers with an empty body |
| Web services | `…/categories/{id}/webservices` | | |
| Browse one | `GET /public/api/browse/categories/{id}` | | the category itself, **without** its elements — those come from `…/browse/categories/{id}/elements/type/{elementType}` |

Creation, the child, duplicate `409`, assignment, cascade and repeated delete are
*verified: 9.5.1 (стенд, 2026-09-10)*; the rest is *unverified: OpenAPI of the 9.5.1 server*.

## What differs from tags

- **Delete cascades to children**, silently: deleting a parent removes every descendant and
  their assignments, and the response mentions none of it. Read `…/categories/tree` and show
  the human what goes.
- **Repeated delete is `200`**, not `500`. Neither status tells you whether the object was
  there — look it up first.
- **Two "assign" endpoints on the view's side**, and their names are nearly identical:
  `category-management/views/{id}/categories` replaces the view's set,
  `category-management/add/views/{id}/categories` adds to it. The path that reads as the
  obvious one is the destructive one.
- **`PUT` is shaped differently from the tag's.** A category takes its id in the *path*
  (`PUT …/categories/{id}`) and a tag takes its id in the *body* (`PUT /public/api/tags`).
  A repeatable script writes both, and the two are easy to swap.
- `path` comes back empty on creation even for a child; the tree is where the hierarchy is
  visible.
