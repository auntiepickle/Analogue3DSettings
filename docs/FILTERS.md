# Filters — the canonical contract for any UI built on this repo

The metadata block on each cart entry (see `schema/game-metadata.v1.json`) is
shaped around the queries a downstream UI or website actually needs to run.
This document is the **contract**: any field listed here is filterable; any
field added later that isn't here should either earn its place or be moved to
a less-prominent slot.

Source-agnostic. Wikidata, IGDB, MobyGames, and manual curation all fill the
SAME fields — downstream consumers never branch on source.

## Filterable fields

| Field           | UI verb                 | Example query                                                          |
|-----------------|-------------------------|------------------------------------------------------------------------|
| `genres[]`      | "Genre is …"            | `genres contains "Racing"`                                              |
| `developers[]`  | "Developer is …"        | `developers contains "Rare"`                                            |
| `publishers[]`  | "Publisher is …"        | `publishers contains "Nintendo"`                                        |
| `release_year`  | "Released between …"    | `1996 ≤ release_year ≤ 1998`                                            |
| `series`        | "In series …"           | `series == "Super Mario"`                                               |
| `region`        | "Region is …"           | `region == "USA"`                                                       |
| `players.max`   | "Multiplayer support"   | `players.max ≥ 2`                                                       |
| `expansion_pak` | "Expansion Pak"         | `expansion_pak in ["required", "supported"]`                            |
| `tags[]`        | "Tagged …"              | `tags contains "speedrun-friendly"`                                     |
| `rating.<src>`  | "Score ≥ …"             | `rating.metacritic ≥ 80`                                                |

## Sortable fields

The same set, plus:

- `title` (alphabetical, with normalisation matching cart-DB ordering)
- `release_year` / `release_date`
- `rating.<src>` (any single source)

## Cross-collection filters

These come from the `settings` block on a games.json entry, not the metadata
— but UIs typically expose them in the same filter rail, so they belong in
the same vocabulary:

| Field                        | UI verb                       | Example                                              |
|------------------------------|-------------------------------|------------------------------------------------------|
| `settings.hardware.overclock` | "Overclock level"             | `== "Unleashed"`                                     |
| `settings.display.odm`       | "Display mode"                | `== "crt"`                                           |
| `settings.hardware.disableDeblur` | "Deblur"                  | `== false`                                           |
| collection id                | "From collection …"           | `collection in ["editorial", "community-best"]`      |
| collection updated           | "Updated within …"            | within last N days                                   |

## Vocabulary — controlled lists

To make `contains`-style filters actually useful, the values for some fields
need consistent vocabulary across enrichers. Where there's a defensible canonical
list, the enricher MUST normalise to it; new values are added by PR after
discussion.

### Genres (initial; extend by PR)

`Action`, `Action-Adventure`, `Adventure`, `Fighting`, `Party`, `Platformer`,
`Puzzle`, `Racing`, `RPG`, `Shooter`, `Simulation`, `Sports`, `Strategy`,
`Wrestling`.

Sub-genres (Action-Adventure, Racing-Kart, etc.) go into `tags[]` so the
genre filter stays at a usable cardinality.

### Tags (open-ended, but discoverable)

`speedrun-friendly`, `requires-rumble-pak`, `requires-controller-pak`,
`requires-transfer-pak`, `light-gun`, `multiplayer-only`, `single-player-only`,
`co-op`, `online-play` (N64 had a couple), `region-locked`, `cancelled`,
`compilation`. New ones land via curator PR.

### Series

Free-text but `Tools/validate.py` warns on a series name that no other entry
in the same collection shares — typos surface immediately.

## What is NOT here (intentionally)

- Source-specific raw payloads — enrichers extract what they need into the
  generic fields and discard the rest.
- `wikidata_id`, `igdb_id` at the top level — those live under `external_ids`
  so a consumer can fetch deeper data later without the metadata block
  bloating.
- Review scores from one-off sources — use `rating.<source>` only where the
  source is widely recognised (Metacritic, MobyGames, IGDB).
- `screenshots`, `box_art` — handled by the existing cart-art system in the
  Desktop app, not by this repo.
- Anything Analogue 3D firmware-version-specific — that's in the `settings`
  block.

## When to add a filter

Three rules:

1. **A real UI actually wants it.** "Show me games with online play" is a
   genuine query; "show me games whose Wikidata Q-ID starts with 7" is not.
2. **The data is reliably available** from at least one of the enrichers —
   no aspirational fields.
3. **Vocabulary is decidable.** Either a controlled list or a clearly typed
   value (year, integer, bool, source-keyed sub-object).

If a filter passes all three, open a PR adding the field to
`schema/game-metadata.v1.json`, this doc's tables, and update the validator.
