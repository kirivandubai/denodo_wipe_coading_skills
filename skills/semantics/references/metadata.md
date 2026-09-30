# View metadata for people and AI consumers — full reference

Everything below was run on 9.5.1 unless it says *documentation only*. Sources for the
consumers: the Denodo MCP Server and Denodo AI SDK user manuals (Denodo Connects, 9.5), and
"Assisted Query" in the Data Marketplace guide.

## What each consumer reads

| | MCP Server | Assisted Query | AI SDK |
|---|---|---|---|
| Reads from | Denodo, over JDBC, live | the Data Marketplace catalog | the Data Marketplace, into its own vector store |
| Which views | tagged with one of `mcp.visibility.tags`; all the user may read when unset | the view the user asks about, plus its direct associations | the databases or tags named in its `getMetadata` call (`vdp_database_names` / `vdp_tag_names`) |
| View | name, database, description, tags | name, database, subtype, description, tags with their descriptions, property groups (if included in AI context) | everything in the view's schema |
| Field | name, type, description, tags, `[PK]`, `[NOT NULL]`, sample values | name, logical name, type, source type, description, primary key, nullable, obligatory, tags with descriptions | the same, plus sample rows (needs the cache) |
| Joins | associations, as `JOINs` with their descriptions | direct associations, with the same metadata as the view | associations |
| Picks up a change | on its schema refresh (`mcp.schema-refresh.enabled`) | after the marketplace is synchronised | after synchronisation and a new `getMetadata` run |

*Documentation only* — no MCP Server, Assisted Query or AI SDK was queried for this
reference. What was measured is the Denodo side: the procedures below return the same
effective values (inherited descriptions included) that JDBC metadata carries.

MCP Server configuration that decides visibility, in its `config/application.properties`:

| Property | Effect |
|---|---|
| `mcp.visibility.tags` | comma-separated tags; only views carrying one are visible, from any database. The shipped file sets `mcp`. Unset: every view the user may read |
| `mcp.tools.view-tag` | deprecated; also `mcp` in the shipped file; creates one query tool per tagged view |
| `mcp.schema-refresh.enabled` | off: changes to views and tags are not seen until a restart |

Privileges are the final filter: `CONNECT` on the database and `EXECUTE` on the view for the
MCP Server's user; the AI SDK's synchronisation user also needs `METADATA`.

## Reading the metadata

| Procedure or statement | Gives |
|---|---|
| `GET_ELEMENTS()` with `input_type = 'views'` | `name`, `subtype` (`base`, `derived`, `interface`, `metric`), `folder`, `description` — the whole database, or every database when `input_database_name` is left out |
| `GET_VIEW_COLUMNS()` | per field: `column_remarks` (the effective description), `column_is_primary_key`, `column_is_nullable`, `column_vdp_type` (`int`, `text`, …), `column_sql_type` (`INTEGER`, `VARCHAR`, …) — the whole database in one call |
| `CATALOG_VDP_METADATA_VIEWS()` | per field: `column_description` (effective, `''` when none), `view_type` as a number |
| `GET_PRIMARY_KEYS()` | one row per key column |
| `GET_VIEW_TAGS()` | one row per assignment; `column_name` empty for the view itself. Filter by `tag_name`, not `input_tag_names` (an array) |
| `GET_ASSOCIATIONS()` with `input_type = 'views'` | `association_name`, `association_description`, `mappings`, `valid` |
| `DESC TAG <tag>` | the tag's description |
| `DESC VQL VIEW <view>` | the view's own clauses: `DESCRIPTION`, `PRIMARY KEY`, `TAGS`, field properties — not the inherited descriptions |
| `GET_VIEW_STATISTICS()` | per field: rows, distinct values, `NULL`s, min, max, average size — only when statistics were gathered, 0 rows otherwise |

The `input_…` parameters take `=` only; `IN` returns zero rows.

## Writing — every form

All *verified: 9.5.1 (live, 2026-09-30)*; each is marked `destructive: alter` by the tool.

```sql
-- derived and interface views
ALTER VIEW <view> DESCRIPTION = '<text>';
ALTER VIEW <view> DESCRIPTION = '';                        -- removes it
ALTER VIEW <view> (
    ALTER COLUMN <field> ADD ( DESCRIPTION = '<text>' )
    ALTER COLUMN <field> ADD ( DESCRIPTION = '<text>' )    -- several in one statement
);
ALTER VIEW <view> ( ALTER COLUMN <field> DROP DESCRIPTION );
ALTER VIEW <view> ADD PRIMARY KEY ( '<field>' [, '<field>' ]* );   -- replaces a declared key
ALTER VIEW <view> DROP PRIMARY KEY;

-- base views: the same forms with ALTER TABLE
ALTER TABLE <base view> DESCRIPTION = '<text>';
ALTER TABLE <base view> ( ALTER COLUMN <field> ADD ( DESCRIPTION = '<text>' ) );
ALTER TABLE <base view> ADD PRIMARY KEY ( '<field>' );

-- associations
ALTER ASSOCIATION <association> DESCRIPTION = '<text>';

-- tags: the description, and adding views or fields to the tag
ALTER TAG <tag> DESCRIPTION = '<text>';
ALTER TAG <tag>
    ADD_TO ( VIEWS ( <db>.<view> ) COLUMNS ( <db>.<view>.<field> ) )
    REMOVE_FROM ( VIEWS () COLUMNS () );
```

- `DESCRIPTION` needs `=`; without it: `Syntax error: Exception parsing query near '''`.
- A view description of 4,001 characters fails with `Error storing views modified during
  transaction: Error storing view '<view>': Error accessing the metadata while
  loading/storing objects`; 4,000 is stored. A field description of 4,001 was stored.
- `ALTER TAG … ADD_TO` keeps the tag's other assignments. `ALTER TABLE <base view> ( ALTER
  TAGS ( VIEW ( … ) COLUMNS ( … ) ) )` sets the complete list for that view and its columns:
  a tag it does not name is removed from both.
- In the view's own statement the same metadata is `DESCRIPTION = '…'`, `PRIMARY KEY ( … )`,
  `TAGS ( … )` and `( <field> ( description = '…' ) TAGS ( … ) )`, in the clause order of
  `/denodo:views`; in an association, `DESCRIPTION = '…'` right after `FOLDER`. `DESC VQL`
  prints tags assigned with `ALTER TAG` as a `TAGS` clause of the view.

## What survives what

| | description, field descriptions, key, tags | cache and its loaded rows | views built on it | privileges granted on it |
|---|---|---|---|---|
| any `ALTER` above | changed as written | kept, still served | `OK`, same rows | kept |
| `CREATE OR REPLACE VIEW` with the same columns, without the metadata clauses | **all removed** | (see `/denodo:cache`) | `OK` | kept |

A view-level `EXECUTE` granted to a role was checked through both. `last_modification_date`
in `GET_ELEMENTS()` moves with every `ALTER`.

## Inheritance of field descriptions

A field without a description of its own shows the description of the column it passes
through, resolved when read, not copied:

- inherited through a plain column reference, an alias (`x AS y`), a join, and a `GROUP BY`
  key — including views created before the column below was described;
- not inherited through anything computed: `TRIM`, `CAST`, `COALESCE`, arithmetic,
  `SUM`, `MAX`, `COUNT`;
- a description of its own wins; `DROP DESCRIPTION` shows the inherited one again;
- `GET_VIEW_COLUMNS().column_remarks` and `CATALOG_VDP_METADATA_VIEWS().column_description`
  both show the inherited text; `DESC VQL` does not.

So the audit counts a field as described when it inherits, and one description on a base
view's column reaches every view above that passes it through unchanged. Check that the
inherited text is still true where it arrives: a view that filters or re-grains may need
its own.

## Keys and nullability

A declared primary key sets `column_is_nullable = false` on its columns, and removing or
replacing the key sets it back. Neither is enforced: Denodo answers whatever the data holds.
The MCP Server prints both as `[PK] [NOT NULL]` (documentation).

## Descriptions drafted by the Denodo Assistant

`DENODO_ASSISTANT_GENERATE_VIEW_DESCRIPTION(<db>, <view>, <max words>)` and
`DENODO_ASSISTANT_GENERATE_FIELDS_DESCRIPTION(<db>, <view>, <array of fields>)` call the
LLM configured for the Denodo Assistant and return text; they need that configuration and the
`use_large_language_model_role` role (*documentation only*). Each call is a paid LLM request.
What they return is a draft built from names and sample values, held to the same rule as
yours: every sentence confirmed by the profile, approved by the human before it is written.
