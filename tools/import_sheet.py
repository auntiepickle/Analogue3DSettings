#!/usr/bin/env python3
"""Pull the community Analogue 3D settings spreadsheet, match each row to a
cart ID via data/cart-names.json, and write collections/community-best/games.json.

    python tools/import_sheet.py
    python tools/import_sheet.py --sheet-id ... --gid ...        # override
    python tools/import_sheet.py --dry-run                        # don't write

Stdlib-only (urllib + csv + json). Pipeline:

    sheet CSV  ───►  rows[{Game, Recommended Overclock, ...}]
                          │
                          ▼
                  normalize(title)  ─── lookup in cart-names.json (also normalized) ───► one or more cart IDs
                          │
                          ▼
              games[cartId] = {title, settings, source}
                          │
                          ▼
              collections/community-best/games.json

Unmatched sheet rows are logged so a maintainer can either rename the sheet
entry, extend the cart-names snapshot, or add an alias.
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CART_NAMES = ROOT / "data" / "cart-names.json"
OUT_FILE = ROOT / "collections" / "community-best" / "games.json"
SHEET_ID = "1SGo9l_NEzy0ESbWAgqOKAZSFJyXQhAAkZXZcSdZPeBA"
DEFAULT_GID = "1975911248"

OVERCLOCK_VALUES = {"Auto", "Enhanced", "Enhanced+", "Unleashed"}

# ---------- title normalisation ----------

_PAREN     = re.compile(r"\([^)]*\)")
_BRACKET   = re.compile(r"\[[^\]]*\]")
_NONWORD   = re.compile(r"[^\w ]", re.UNICODE)         # strip all punctuation + symbols (°, !, ', ., :, etc.)
_WS        = re.compile(r"\s+")
_DB_ARTICLE = re.compile(r"^(.+?),\s+(a|an|the)$")    # "Bug's Life, A"  →  "A Bug's Life"
_LEAD_ART   = re.compile(r"^(a|an|the)\s+")            # drop leading article

# Sheet → cart-DB title aliases for picks the normaliser can't bridge —
# numbering swaps ("007 GoldenEye" ↔ "GoldenEye 007"), subtitle additions
# ("Daikatana" ↔ "John Romero's Daikatana"), explicit JP/USA flags that
# don't appear in the cart DB. Keys are normalised sheet titles; values
# are normalised cart-DB titles. Build out over time as misses surface.
ALIASES = {
    "007 goldeneye":   "goldeneye 007",
    "daikatana":       "john romero's daikatana",
    "bomberman 64 jp": "bomberman 64",
}


def normalize(s):
    """Sheet names ('1080° Snowboarding', 'A Bug's Life') and cart-DB names
    ('1080 Snowboarding (Japan, USA)', 'Bug's Life, A (USA)') collide after
    this is applied to both. Strips parens-/-brackets, all punctuation and
    symbols (°, !, ', ., :, /, -), handles the ROM-database article suffix
    ('Bug's Life, A' → 'A Bug's Life'), and drops a leading article so both
    sides agree on 'bugs life'."""
    if not s:
        return ""
    s = s.lower()
    s = _PAREN.sub("", s)
    s = _BRACKET.sub("", s)
    s = _WS.sub(" ", s).strip()
    # ROM-DB suffix detection has to run BEFORE we strip the comma.
    m = _DB_ARTICLE.match(s)
    if m:
        s = f"{m.group(2)} {m.group(1)}"
    s = _NONWORD.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    s = _LEAD_ART.sub("", s)
    return s


def title_variants(sheet_title):
    """Sheet rows occasionally list multiple alternates separated by ' / '
    (e.g. 'Bomberman 64 / Baku Bomberman'). Try each chunk independently so
    a region-specific cart name still matches via one of the alternates."""
    parts = [sheet_title] + [p.strip() for p in sheet_title.split(" / ") if p.strip()]
    seen = set()
    for p in parts:
        n = normalize(p)
        if n and n not in seen:
            seen.add(n)
            yield n


# ---------- I/O ----------

def fetch_csv(sheet_id, gid):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    sys.stderr.write(f"[fetch] {url}\n")
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode("utf-8")


def load_cart_index(path):
    """Build {normalized_name: [cart_entry, ...]}. Multiple regional variants
    of one game collide on the same normalized name and ALL get returned —
    sheet recommendations apply to every variant unless the sheet pins a
    specific region (and we emit per-variant entries anyway, so the
    consuming app picks the row matching what's actually on the user's card)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    idx = {}
    for c in raw:
        key = normalize(c.get("name", ""))
        if not key:
            continue
        idx.setdefault(key, []).append(c)
    return idx


# ---------- per-row mapping ----------

def map_settings(row):
    """Convert a sheet row into a partial settings dict per
    schema/game-settings.v1.json. Only the columns this sheet actually carries
    get mapped. Anything we don't know about is left out — collection entries
    are partial overlays on the user's existing settings."""
    settings = {}
    oc = (row.get("Recommended Overclock") or "").strip()
    if oc in OVERCLOCK_VALUES:
        settings.setdefault("hardware", {})["overclock"] = oc
    return settings


def map_source(row, row_idx):
    """Free-text context the schema doesn't capture but a curator would want
    when reviewing or surfacing in a UI tooltip."""
    src = {
        "sheet_row": row_idx,
        "observed_firmware": (row.get("Firmware") or "").strip() or None,
        "observed_region": (row.get("Region") or "").strip() or None,
        "rationale": (row.get("Performance Gains") or "").strip() or None,
        "caveats": (row.get("Known Issues") or "").strip() or None,
    }
    return {k: v for k, v in src.items() if v not in (None, "")}


# ---------- driver ----------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sheet-id", default=SHEET_ID)
    p.add_argument("--gid", default=DEFAULT_GID)
    p.add_argument("--cart-names", default=str(CART_NAMES))
    p.add_argument("--out", default=str(OUT_FILE))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    cart_index = load_cart_index(args.cart_names)
    sys.stderr.write(f"[carts] {sum(len(v) for v in cart_index.values())} entries, "
                     f"{len(cart_index)} unique names\n")

    csv_text = fetch_csv(args.sheet_id, args.gid)
    reader = csv.DictReader(io.StringIO(csv_text))

    games = {}
    matched = unmatched = skipped = 0
    misses = []

    for i, row in enumerate(reader, start=2):  # row 1 = header
        title = (row.get("Game") or "").strip()
        if not title:
            skipped += 1
            continue
        settings = map_settings(row)
        if not settings:
            skipped += 1                       # no actionable setting in row
            continue
        # Try each alias-mapped, "/"-split variant until something matches.
        carts = []
        for k in title_variants(title):
            carts = cart_index.get(ALIASES.get(k, k), [])
            if carts:
                break
        if not carts:
            unmatched += 1
            misses.append(title)
            continue
        source = map_source(row, i)
        for c in carts:
            cart_id = c.get("id")
            if not cart_id:
                continue
            games[cart_id] = {
                "title": c.get("name", title),
                "settings": settings,
                "source": source,
            }
        matched += 1

    sys.stderr.write(f"[match] {matched} sheet rows → {len(games)} cart entries "
                     f"(unmatched={unmatched}, skipped={skipped})\n")
    if misses:
        log = ROOT / "tools" / "unmatched_titles.log"
        log.write_text("\n".join(sorted(misses)), encoding="utf-8")
        sys.stderr.write(f"[miss] wrote {len(misses)} unmatched titles → {log.relative_to(ROOT)}\n")

    out = {
        "collection_id": "community-best",
        "version": "0.1.0",
        "updated": date.today().isoformat() if not os.environ.get("A3DS_FROZEN_DATE")
                                            else os.environ["A3DS_FROZEN_DATE"],
        "games": dict(sorted(games.items())),
    }
    payload = json.dumps(out, indent=2, ensure_ascii=False) + "\n"

    if args.dry_run:
        sys.stdout.write(payload)
        return 0
    Path(args.out).write_text(payload, encoding="utf-8")
    sys.stderr.write(f"[write] {args.out}  ({len(games)} entries)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
