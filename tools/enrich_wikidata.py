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
GENRE_CANON = {
    "Q828322":   "Action",
    "Q1018713":  "Adventure",
    "Q1107":     "Action-Adventure",
    "Q860750":   "Fighting",
    "Q828326":   "Platformer",
    "Q604984":   "Platformer",
    "Q1067369":  "Puzzle",
    "Q4106152":  "Racing",
    "Q526877":   "RPG",
    "Q173814":   "RPG",
    "Q63451704": "Shooter",
    "Q336103":   "Shooter",
    "Q1196129":  "Simulation",
    "Q839863":   "Sports",
    "Q208595":   "Strategy",
    "Q3010474":  "Wrestling",
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
    """Strip cart-DB cruft: '007 - GoldenEye (USA)' → '007 - goldeneye'.
    Lowercased + parens-stripped so SPARQL's CONTAINS(LCASE()) just works."""
    s = _RX_PAREN.sub("", title or "")
    s = _RX_BRACKET.sub("", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def resolve_qid(title, cache):
    needle = title_for_lookup(title)
    if needle in cache and "qid" in cache[needle]:
        return cache[needle].get("qid")
    if not needle:
        return None
    try:
        body = sparql(RESOLVE_QUERY.format(needle=needle.replace('"', '\\"')))
    except Exception as e:
        sys.stderr.write(f"[err]  resolve '{needle}': {e}\n")
        return None
    rows = body.get("results", {}).get("bindings", [])
    qid = None
    for row in rows:
        q = row.get("game", {}).get("value", "")
        if q.startswith("http://www.wikidata.org/entity/Q"):
            qid = q.rsplit("/", 1)[-1]
            break
    cache.setdefault(needle, {})["qid"] = qid
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
            # The SERVICE wikibase:label clause sometimes drops the label
            # for series — fall back to a follow-up resolve if we got a
            # raw Q-ID. Keeps the data clean for filter UIs.
            if vl and not re.match(r"^Q\d+$", vl):
                out["series"] = vl
            elif v.startswith("http://www.wikidata.org/entity/Q") and not out.get("series"):
                out["_series_qid"] = v.rsplit("/", 1)[-1]
        elif slot == "release_date":
            # Wikidata returns multiple dates per game (per-platform / per-region
            # rereleases). Keep the EARLIEST so we get the original N64 release,
            # not the 2016 Virtual Console re-issue.
            d = v[:10] if v[:10].count("-") == 2 else None
            if d and (not out.get("release_date") or d < out["release_date"]):
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
