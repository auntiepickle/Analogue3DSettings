#!/usr/bin/env python3
"""Enrich a collection's games.json with factual metadata from Wikidata.

    python tools/enrich_wikidata.py [--collection community-best] [--dry-run]

For each cart in the target collection, this:

  1. Resolves the cart's title (or alt-title) to a Wikidata Q-ID by querying
     the SPARQL endpoint with `instance of: video game` + `platform: N64`
     + a `CONTAINS()` match on the rdfs:label.
  2. Fetches a fixed property bundle for that Q-ID (genre, developer,
     publisher, release_year, series, external IDs).
  3. Writes the result into entry.metadata using the source-agnostic shape
     from schema/game-metadata.v1.json.

Stdlib-only. Polite to Wikidata: 5 req/s ceiling, a User-Agent header, and
results cached in tools/.wikidata_cache.json so re-runs hit zero network.

Unmatched / ambiguous titles get logged to tools/enrich_misses.log for
curator review. Existing metadata fields the enricher would have set are
left alone if `--preserve-manual` is set (default) — manual curator edits
survive re-runs."""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLECTIONS = ROOT / "collections"
CACHE_PATH = ROOT / "tools" / ".wikidata_cache.json"

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "Analogue3DSettings-enricher/0.1 (+https://github.com/auntiepickle/Analogue3DSettings)"

# Wikidata Q-IDs we lean on
Q_VIDEO_GAME = "Q7889"
Q_N64        = "Q184839"

# Q-ID → human label for the small set of N64-relevant genres. Anything not
# in this map is dropped; tighter than free-text per FILTERS.md.
# Mapped from the real frequencies surfaced by tools/debug_genres.py against
# the 269 US carts in this collection. Sub-genres (3D platform game, ice
# hockey video game, etc.) collapse to their canonical parent so the genre
# filter doesn't fragment; see FILTERS.md for the canonical list.
GENRE_CANON = {
    # Action / Action-Adventure
    "Q270948":    "Action",
    "Q1755234":   "Action",
    "Q2070892":   "Action",          # vehicular combat
    "Q343568":    "Action-Adventure",
    # Adventure
    "Q1018713":   "Adventure",
    # Fighting + wrestling sub-collapses
    "Q846224":    "Fighting",
    "Q105221690": "Wrestling",
    # Platformer (every flavour)
    "Q828322":    "Platformer",
    "Q116790461": "Platformer",      # 3D platform game
    "Q104819482": "Platformer",      # collect-a-thon
    # Puzzle
    "Q54767":     "Puzzle",
    "Q13717398":  "Puzzle",          # maze
    # Racing
    "Q860750":    "Racing",
    # RPG
    "Q744038":    "RPG",
    # Shooter (FPS / TPS / shmup all collapse)
    "Q185029":    "Shooter",         # first-person shooter
    "Q380266":    "Shooter",         # third-person shooter
    "Q1044478":   "Shooter",         # shoot 'em up
    # Sports (every sport)
    "Q868217":    "Sports",
    "Q63915391":  "Sports",          # American football
    "Q63915027":  "Sports",          # basketball
    "Q71474750":  "Sports",          # ice hockey
    "Q1478420":   "Sports",          # association football
    "Q71467408":  "Sports",          # winter sports
    "Q61719251":  "Sports",          # bowling
    # Strategy / Sim / Party (small categories)
    "Q208595":    "Strategy",
    "Q1196129":   "Simulation",
    "Q7888616":   "Party",
}

# SPARQL: resolve title to Q-ID. Matches "instance of (a subclass of) video
# game" with N64 platform, then case-insensitive substring on the English
# label or any alias. Limit + ORDER BY so re-runs are deterministic.
RESOLVE_QUERY = """
SELECT ?game ?label WHERE {{
  ?game wdt:P31/wdt:P279* wd:Q7889 ;
        wdt:P400 wd:Q184839 ;
        rdfs:label ?label .
  FILTER (LANG(?label) = "en")
  FILTER (CONTAINS(LCASE(?label), "{needle}"))
}}
ORDER BY ASC(STRLEN(?label))
LIMIT 5
"""

# SPARQL: fetch the property bundle for a known Q-ID.
DETAILS_QUERY = """
SELECT ?prop ?value ?valueLabel WHERE {{
  VALUES ?prop {{
    wdt:P136     # genre
    wdt:P178     # developer
    wdt:P123     # publisher
    wdt:P577     # publication date
    wdt:P179     # part of series
    wdt:P5794    # IGDB ID
    wdt:P1933    # MobyGames ID
    wdt:P5359    # Metacritic ID
  }}
  wd:{qid} ?prop ?value .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


# ---------- network helpers ----------

def _http_json(url, params=None, timeout=30):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/sparql-results+json",
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def sparql(query, sleep=0.3):
    """Wikidata's public endpoint asks for ≤5 req/s; we run nowhere near that
    even with sleep=0.3."""
    time.sleep(sleep)
    return _http_json(SPARQL_ENDPOINT, {"query": query, "format": "json"})


# ---------- cache ----------

def load_cache():
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(c):
    CACHE_PATH.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")


# ---------- resolve + fetch ----------

_RX_PAREN = re.compile(r"\([^)]*\)")
_RX_BRACKET = re.compile(r"\[[^\]]*\]")


def title_for_lookup(title):
    """Strip cart-DB cruft and lowercase. ROM-database article suffix
    swap ('Bug's Life, A' → 'A Bug's Life') runs BEFORE the comma is gone."""
    s = _RX_PAREN.sub("", title or "")
    s = _RX_BRACKET.sub("", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    m = re.match(r"^(.+?),\s+(a|an|the)$", s)
    if m:
        s = f"{m.group(2)} {m.group(1)}"
    return s


def lookup_variants(title):
    """Generate progressively-relaxed needles for SPARQL CONTAINS matching.
    No-Intro cart-DB uses ' - ' between title and subtitle; Wikidata uses
    ': '. We also try a plain-space variant for cases where Wikidata drops
    the separator entirely ('Star Wars Rogue Squadron')."""
    base = title_for_lookup(title)
    seen, out = set(), []
    for variant in (base,
                    base.replace(" - ", ": "),
                    base.replace(" - ", " "),
                    re.sub(r"\s*\bv\d+\b.*$", "", base).strip(),    # drop '(v2)' tails
                    re.sub(r"\s*\bbeta\b.*$", "", base).strip()):    # drop '(Beta)' tails
        v = variant.strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def resolve_qid(title, cache):
    if not title:
        return None
    base = title_for_lookup(title)
    if base in cache and "qid" in cache[base]:
        return cache[base].get("qid")
    qid = None
    for needle in lookup_variants(title):
        try:
            body = sparql(RESOLVE_QUERY.format(needle=needle.replace('"', '\\"')))
        except Exception as e:
            sys.stderr.write(f"[err]  resolve '{needle}': {e}\n")
            continue
        for row in body.get("results", {}).get("bindings", []):
            q = row.get("game", {}).get("value", "")
            if q.startswith("http://www.wikidata.org/entity/Q"):
                qid = q.rsplit("/", 1)[-1]
                break
        if qid:
            break
    cache.setdefault(base, {})["qid"] = qid
    return qid


def fetch_details(qid, cache):
    if qid in cache and "details" in cache[qid]:
        return cache[qid]["details"]
    try:
        body = sparql(DETAILS_QUERY.format(qid=qid))
    except Exception as e:
        sys.stderr.write(f"[err]  details {qid}: {e}\n")
        return None
    out = {
        "genres": set(), "developers": set(), "publishers": set(),
        "series": None, "release_date": None,
        "external_ids": {},
    }
    PROP = {
        "http://www.wikidata.org/prop/direct/P136":  "genres",
        "http://www.wikidata.org/prop/direct/P178":  "developers",
        "http://www.wikidata.org/prop/direct/P123":  "publishers",
        "http://www.wikidata.org/prop/direct/P577":  "release_date",
        "http://www.wikidata.org/prop/direct/P179":  "series",
        "http://www.wikidata.org/prop/direct/P5794": "igdb",
        "http://www.wikidata.org/prop/direct/P1933": "mobygames",
        "http://www.wikidata.org/prop/direct/P5359": "metacritic",
    }
    for row in body.get("results", {}).get("bindings", []):
        p = row.get("prop", {}).get("value", "")
        v = row.get("value", {}).get("value", "")
        vl = row.get("valueLabel", {}).get("value", "")
        slot = PROP.get(p)
        if slot is None:
            continue
        if slot == "genres":
            q = v.rsplit("/", 1)[-1] if v.startswith("http://www.wikidata.org/entity/Q") else None
            if q and q in GENRE_CANON:
                out["genres"].add(GENRE_CANON[q])
        elif slot in ("developers", "publishers"):
            if vl: out[slot].add(vl)
        elif slot == "series":
            # `SERVICE wikibase:label` is inconsistent — sometimes returns the
            # raw Q-ID tail when no English label is cached. Always capture
            # the Q-ID and do a deterministic rdfs:label resolve below.
            if v.startswith("http://www.wikidata.org/entity/Q"):
                out["_series_qid"] = v.rsplit("/", 1)[-1]
            elif vl and not re.match(r"^Q\d+$", vl):
                out["series"] = vl
        elif slot == "release_date":
            # Wikidata returns multiple dates per game (per-platform / per-region
            # rereleases, AND sometimes a franchise-original arcade date going
            # back to the 70s). Keep the EARLIEST date that plausibly falls
            # inside the N64 cart's release window — anything before 1996 is
            # franchise noise, anything after 2003 is a reissue.
            d = v[:10] if v[:10].count("-") == 2 else None
            if d and "1996-01-01" <= d <= "2003-12-31":
                if not out.get("release_date") or d < out["release_date"]:
                    out["release_date"] = d
        elif slot in ("igdb", "mobygames", "metacritic"):
            out["external_ids"][slot] = v
    # Resolve a series Q-ID we collected but couldn't label inline.
    if out.get("_series_qid") and not out.get("series"):
        try:
            body2 = sparql(
                f'SELECT ?l WHERE {{ wd:{out["_series_qid"]} rdfs:label ?l . FILTER (LANG(?l)="en") }} LIMIT 1')
            rows2 = body2.get("results", {}).get("bindings", [])
            if rows2:
                out["series"] = rows2[0].get("l", {}).get("value", "") or None
        except Exception:
            pass
    out.pop("_series_qid", None)
    # finalise
    out["genres"] = sorted(out["genres"]) or None
    out["developers"] = sorted(out["developers"]) or None
    out["publishers"] = sorted(out["publishers"]) or None
    out["external_ids"] = out["external_ids"] or None
    cache.setdefault(qid, {})["details"] = out
    return out


# ---------- merge into games.json ----------

def merge_metadata(entry, details, qid):
    md = entry.get("metadata") or {}
    # External IDs: never clobber an existing manual entry; merge dicts.
    ext = dict(md.get("external_ids") or {})
    ext.setdefault("wikidata", qid)
    for k, v in (details.get("external_ids") or {}).items():
        ext.setdefault(k, v)
    md["external_ids"] = ext

    for field in ("genres", "developers", "publishers"):
        if not md.get(field) and details.get(field):
            md[field] = details[field]
    if not md.get("series") and details.get("series"):
        md["series"] = details["series"]
    if details.get("release_date"):
        md.setdefault("release_date", details["release_date"])
        if "release_year" not in md:
            try: md["release_year"] = int(details["release_date"][:4])
            except ValueError: pass

    stamp = f"wikidata@{date.today().isoformat()}"
    enriched = list(md.get("enriched_from") or [])
    if stamp not in enriched: enriched.append(stamp)
    md["enriched_from"] = enriched

    entry["metadata"] = md


# ---------- driver ----------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--collection", default="community-best")
    p.add_argument("--limit", type=int, default=0,
                   help="Cap how many entries to enrich this run (0 = all). "
                        "Helpful for first-time test runs.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print summary, don't touch games.json or the cache file.")
    args = p.parse_args()

    games_file = COLLECTIONS / args.collection / "games.json"
    data = json.loads(games_file.read_text(encoding="utf-8"))
    games = data.get("games", {})
    cache = load_cache()
    sys.stderr.write(f"[start] {len(games)} entries in {args.collection}, "
                     f"cache has {len(cache)} keys\n")

    matched = unmatched = 0
    misses = []
    for i, (cid, entry) in enumerate(sorted(games.items())):
        if args.limit and i >= args.limit:
            break
        title = entry.get("title") or ""
        qid = resolve_qid(title, cache)
        if not qid:
            unmatched += 1
            misses.append(f"{cid}  {title}")
            continue
        details = fetch_details(qid, cache)
        if not details:
            unmatched += 1
            misses.append(f"{cid}  {title}  (Q-ID {qid} but no details)")
            continue
        merge_metadata(entry, details, qid)
        matched += 1
        if i % 25 == 0:
            sys.stderr.write(f"[prog] {i}/{len(games)}  matched={matched}\n")

    sys.stderr.write(f"[done] matched={matched}  unmatched={unmatched}\n")
    if misses:
        log = ROOT / "tools" / "enrich_misses.log"
        log.write_text("\n".join(misses), encoding="utf-8")
        sys.stderr.write(f"[miss] wrote {len(misses)} → {log.relative_to(ROOT)}\n")
    if args.dry_run:
        return 0
    save_cache(cache)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    games_file.write_text(payload, encoding="utf-8")
    sys.stderr.write(f"[write] {games_file.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
