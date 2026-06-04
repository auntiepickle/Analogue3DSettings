#!/usr/bin/env python3
"""Set the expansion_pak field on each cart entry from data/expansion_pak.json.

Wikipedia doesn't categorise N64 games by Expansion Pak compatibility and
Wikidata's property bag doesn't record it either, so this is a hand-
curated list — see data/expansion_pak.json for sources + attribution.

    python tools/enrich_expansion_pak.py [--collection community-best]

Match strategy mirrors tools/import_sheet.py: normalize titles by
stripping parens/brackets/all-punctuation and dropping leading articles,
then look up each curated entry in the collection. Multiple regional
variants of the same game all receive the same expansion_pak value.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLECTIONS = ROOT / "collections"
EP_FILE = ROOT / "data" / "expansion_pak.json"

_PAREN = re.compile(r"\([^)]*\)")
_BRACKET = re.compile(r"\[[^\]]*\]")
_NONWORD = re.compile(r"[^\w ]", re.UNICODE)
_WS = re.compile(r"\s+")
_DB_ARTICLE = re.compile(r"^(.+?),\s+(a|an|the)$")
_LEAD_ART = re.compile(r"^(a|an|the)\s+")


def normalize(s):
    """Mirrors tools/import_sheet.normalize so the curated list and the
    cart-DB titles collide on the same normalised key."""
    if not s:
        return ""
    s = s.lower()
    s = _PAREN.sub("", s)
    s = _BRACKET.sub("", s)
    s = _WS.sub(" ", s).strip()
    m = _DB_ARTICLE.match(s)
    if m:
        s = f"{m.group(2)} {m.group(1)}"
    s = _NONWORD.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    s = _LEAD_ART.sub("", s)
    return s


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--collection", default="community-best")
    args = p.parse_args()

    curated = json.loads(EP_FILE.read_text(encoding="utf-8"))
    games_file = COLLECTIONS / args.collection / "games.json"
    data = json.loads(games_file.read_text(encoding="utf-8"))
    games = data.get("games", {})

    # Build a normalised-title → list-of-cart-IDs index. Multiple regional
    # carts of the same game share a normalised title.
    by_title = {}
    for cid, entry in games.items():
        key = normalize(entry.get("title", ""))
        if key:
            by_title.setdefault(key, []).append(cid)

    req_keys = {normalize(t) for t in curated.get("required", [])}
    sup_keys = {normalize(t) for t in curated.get("supported", [])}

    stamp = f"hand-curated-expansion-pak@{date.today().isoformat()}"
    set_req = set_sup = missed = 0
    misses = []

    for level, keys in (("required", req_keys), ("supported", sup_keys)):
        for key in keys:
            carts = by_title.get(key, [])
            if not carts:
                misses.append((level, key))
                missed += 1
                continue
            for cid in carts:
                md = games[cid].setdefault("metadata", {})
                if level == "supported" and md.get("expansion_pak") == "required":
                    continue   # 'required' wins
                md["expansion_pak"] = level
                enriched = list(md.get("enriched_from") or [])
                if stamp not in enriched: enriched.append(stamp)
                md["enriched_from"] = enriched
                if level == "required": set_req += 1
                else:                    set_sup += 1

    sys.stderr.write(f"[set]   required={set_req}  supported={set_sup}\n")
    if misses:
        sys.stderr.write(f"[miss]  curated entries with no matching cart in collection: {missed}\n")
        for lvl, k in misses[:20]:
            sys.stderr.write(f"        [{lvl:9}] {k}\n")

    games_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    sys.stderr.write(f"[write] {games_file.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
