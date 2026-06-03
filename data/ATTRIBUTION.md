# Vendored data

## `cart-names.json`

A snapshot of the cart ID ↔ canonical-name database from
[**TheLeggett/A3D-Manager**](https://github.com/TheLeggett/A3D-Manager/blob/main/data/cart-names.json),
which reverse-engineered both the SD-card format and the cart-ID algorithm
(CRC32 of the first 8 KiB of the Z64 ROM). We use it as the lookup table that
turns sheet-style game titles (e.g. "007 GoldenEye") into the 8-char hex
`cartId` (e.g. `ac631da0`) the Analogue 3D itself stores per-game settings
under.

- **Upstream**: <https://github.com/TheLeggett/A3D-Manager>
- **License**: MIT — see `A3D-Manager/LICENSE`.
- **Snapshot vendored**: 2026-06-03 (341 entries).

Each entry is `{id, gameCode, name, region, languages, videoMode, releaseType, revision}`.

Refreshing this file is a manual `curl` of the upstream raw URL until we wire
up a scheduled job. If A3D-Manager's schema or filename changes upstream,
update `tools/import_sheet.py` to match.
