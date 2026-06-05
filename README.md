# Analogue 3D Settings

Community-curated per-game settings for the Analogue 3D, organised as
**collections** — each collection is a curatorial point of view (period-correct
vs. modern, deblur on vs. off, etc.). One JSON file per collection lists every
covered cart and the recommended settings for that cart.

A consuming app (e.g. the
[Analogue 3D Desktop](https://github.com/auntiepickle/Analogue3DDesktop) or
any third-party tool) lets the user pick which collections to enable, then
writes each game's recommended settings into the canonical Analogue 3D
location on the SD card:
`/Library/N64/Games/<title> <cartId>/settings.json`.

## Collections

| Collection | What it picks for | Status |
|---|---|---|
| [`conservative`](collections/conservative/) | Period-correct CRT look, deblur off, original hardware path | seeding |
| [`cutting-edge`](collections/cutting-edge/) | Modern clean output, deblur on, max scaler, overclock | seeding |
| [`community-best`](collections/community-best/) | Pure consensus from the community Google Sheet | pending Phase 3 |
| [`editorial`](collections/editorial/) | Our opinionated pick — defaults to community, dissents in writing where we disagree | seeding |

How `community-best` derives from raw sheet data, and the rules `editorial`
uses to over-rule it (with explicit dissent), are documented in
[`docs/FILTER_CRITERIA.md`](docs/FILTER_CRITERIA.md). The pipeline lives in
[`tools/`](tools/).

## Data shape

Each collection lives in `collections/<id>/` with two files:

- `collection.json` — metadata: name, description, version, source, license.
- `games.json` — a `{cartId: {title, settings, rationale}}` map covering every cart the collection has an opinion on.

The settings dict matches the **canonical settings schema** in
[`schema/game-settings.v1.json`](schema/game-settings.v1.json), which mirrors
the TypeScript interface the Analogue 3D writes to `settings.json`.

The 8-character lowercase hex `cartId` is the CRC32 of the first 8 KiB of the
Z64 ROM — the same identifier the Analogue 3D itself uses to look up per-cart
settings. See
[A3D-Manager's CART_ID_ALGORITHM.md](https://github.com/TheLeggett/A3D-Manager/blob/main/docs/CART_ID_ALGORITHM.md)
for the reference implementation.

## Credit

The schema, cart-ID algorithm, and SD-card-format spec used here come from
[**TheLeggett/A3D-Manager**](https://github.com/TheLeggett/A3D-Manager), which
did the reverse-engineering. This repo is downstream — it provides curated
*recommendations* against that schema, in a format any tool can consume.

## Adding a game to a collection

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Short version: edit the collection's
`games.json`, run `tools/validate.py` to confirm the entry matches the schema,
open a PR.

## Adding a new collection

Drop a new directory under `collections/`, add a `collection.json` + an
initial `games.json`, and reference it in this README's table. Curators can
maintain their own collections independently.

## Audit / spot-check view

A static site under [`site/`](site/) renders every cart in
[`community-best`](collections/community-best/) as a filterable table — by
genre, year, overclock recommendation, expansion-pak class, source region —
with a per-row "row N" link that jumps straight to the source spreadsheet
row so a community reviewer can verify what we imported against what was
originally written.

Once GitHub Pages is enabled (`main` branch, `/site` folder) the audit view
lives at https://auntiepickle.github.io/Analogue3DSettings/ — open it, drop a
filter (e.g. `Overclock = Unleashed`), and click any "row N" link to inspect
the original sheet cell.

## License

The code in `tools/` and the schema are MIT (see [LICENSE](LICENSE)).
Individual collections may carry their own attribution requirements — see
each collection's `collection.json` `license` field.
