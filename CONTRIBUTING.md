# Contributing

## Adding or updating a game in an existing collection

1. Find the cart's 8-char hex ID. Easiest: it's the suffix of the folder name
   the Analogue 3D creates under `/Library/N64/Games/` (e.g. `GoldenEye 007 [a1b2c3d4]`
   → `cartId = "a1b2c3d4"`). Programmatically: CRC32 of the first 8 KiB of the
   Z64 ROM.
2. Edit `collections/<collection>/games.json`. Add the entry under `games`:
   ```json
   {
     "a1b2c3d4": {
       "title": "GoldenEye 007",
       "settings": { ... },
       "rationale": "Why this collection picks these."
     }
   }
   ```
3. The `settings` object must validate against
   [`schema/game-settings.v1.json`](schema/game-settings.v1.json). Partial
   settings are fine — anything you omit is left at whatever the user/console
   already has.
4. Run `python tools/validate.py` (no deps beyond stdlib).
5. Open a PR. Keep the PR scoped to one collection per change so reviewers can
   judge curatorial intent.

## Proposing a new collection

A collection is a curatorial *point of view*. If the angle is genuinely new
("portable-display-friendly", "speedrunner-preferred", "specific CRT-set
matched") and isn't covered by an existing collection's tweaks, open an issue
first so we can settle on the directory name + scope before the PR.

Minimum to merge a new collection:

- `collections/<id>/collection.json` with `id`, `name`, `description`,
  `version`, `updated`, `license`, optional `source`.
- `collections/<id>/games.json` with at least one game.
- A row in [`README.md`](README.md)'s collections table.

## Schema changes

The schema in `schema/game-settings.v1.json` is anchored to TheLeggett's
reverse-engineered TypeScript interface. If the Analogue 3D firmware ever adds
a new setting, the right move is:

1. File the change against [A3D-Manager](https://github.com/TheLeggett/A3D-Manager) first.
2. Once their schema absorbs it, bump our schema to `v2`, keep `v1` around for
   older collections, and migrate.

This way the two repos don't drift.
