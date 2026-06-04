#!/usr/bin/env python3
"""Two more passes over the enriched collection:

  A) alt_titles  — Wikidata aliases for each cart's Q-ID (batch wbgetentities).
                   Gives the consuming UI better free-text-search recall —
                   matches against working titles, JP romanisations, and
                   the labels Wikidata uses for redirects.

  B) series       — parse the Wikipedia article's infobox for the
                   `| series = …` field. Wikidata's P179 is patchy for
                   older N64 games (~40% coverage on this corpus); the
                   en-Wikipedia infobox is more reliable.

    python tools/enrich_extras.py [--collection community-best]

Stdlib only. Both passes read the wikidata Q-ID already stored on each
entry's external_ids — they piggyback on enrich_wikidata.py's resolve work
rather than re-resolving titles."""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLECTIONS = ROOT / "collections"
CACHE_PATH = ROOT / "tools" / ".extras_cache.json"

UA = "Analogue3DSettings-extras/0.1 (+https://github.com/auntiepickle/Analogue3DSettings)"


def _http_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------- A) Aliases ----------

def fetch_aliases_batch(qids, sleep=0.3):
    """One wbgetentities call returns aliases + sitelinks for up to 50 Q-IDs."""
    out = {}
    if not qids: return out
    chunk = "|".join(qids)
    params = {
        "action": "wbgetentities", "ids": chunk,
        "props": "aliases|sitelinks", "languages": "en",
        "sitefilter": "enwiki", "format": "json",
    }
    body = _http_json("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(params))
    for qid, ent in (body.get("entities") or {}).items():
        if not qid.startswith("Q"):
            continue
        aliases = [a["value"] for a in (ent.get("aliases") or {}).get("en", [])]
        site = (ent.get("sitelinks") or {}).get("enwiki") or {}
        wp_title = site.get("title")
        out[qid] = {"aliases": aliases, "wp_title": wp_title}
    time.sleep(sleep)
    return out


# ---------- B) Series from Wikipedia infobox ----------

# Infobox 'series' lines in wikitext have many shapes:
#   | series   = [[Mario Kart]]
#   |series=Mario Party
#   | series = [[Mario Kart|Mario Kart series]]
# We match a series field value loosely and then strip wiki link decoration.
_SERIES_LINE = re.compile(r"^\s*\|\s*series\s*=\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_WIKILINK    = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")
_REF_TAG     = re.compile(r"<ref[^>]*>.*?</ref>", re.DOTALL)
_HTML_TAG    = re.compile(r"<[^>]+>")
_TEMPLATE    = re.compile(r"\{\{[^}]*\}\}")


def fetch_series_from_wikipedia(wp_title, sleep=0.3):
    """Return the infobox 'series =' value, or None. Pulls just the lead
    section to keep the response small."""
    if not wp_title:
        return None
    params = {
        "action": "parse", "page": wp_title,
        "prop": "wikitext", "section": "0", "format": "json",
    }
    try:
        body = _http_json("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params))
    except Exception as e:
        sys.stderr.write(f"[err]  series wiki {wp_title!r}: {e}\n")
        return None
    time.sleep(sleep)
    text = (body.get("parse") or {}).get("wikitext", {}).get("*", "")
    if not text:
        return None
    m = _SERIES_LINE.search(text)
    if not m:
        return None
    raw = m.group(1)
    # Strip refs, templates, HTML tags; resolve wikilink → display text.
    raw = _REF_TAG.sub("", raw)
    raw = _TEMPLATE.sub("", raw)
    raw = _HTML_TAG.sub("", raw)
    raw = _WIKILINK.sub(lambda m_: m_.group(1), raw)
    raw = raw.strip().strip("'\"")
    return raw or None


# ---------- driver ----------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--collection", default="community-best")
    p.add_argument("--limit", type=int, default=0,
                   help="Cap entries this run (0 = all).")
    args = p.parse_args()

    games_file = COLLECTIONS / args.collection / "games.json"
    data = json.loads(games_file.read_text(encoding="utf-8"))
    games = data.get("games", {})
    cache = json.loads(CACHE_PATH.read_text("utf-8")) if CACHE_PATH.exists() else {}

    # Pair each cart with its Wikidata Q-ID — the rest of this script reads
    # only the carts that have one.
    pairs = [(cid, (e.get("metadata") or {}).get("external_ids", {}).get("wikidata"))
             for cid, e in games.items()]
    pairs = [(cid, q) for cid, q in pairs if q]
    if args.limit:
        pairs = pairs[:args.limit]
    sys.stderr.write(f"[start] {len(pairs)} carts have a Q-ID; mining aliases + series\n")

    # ----- A) batch aliases + sitelinks -----
    need_alias = [q for _, q in pairs if q not in cache]
    sys.stderr.write(f"[A] need to fetch {len(need_alias)} alias bundles\n")
    for i in range(0, len(need_alias), 50):
        chunk = need_alias[i:i+50]
        try:
            res = fetch_aliases_batch(chunk)
            for q, data_ in res.items():
                cache[q] = {**cache.get(q, {}), **data_}
        except Exception as e:
            sys.stderr.write(f"[err]  alias batch {i}: {e}\n")
        if i % 200 == 0:
            sys.stderr.write(f"[A] {i}/{len(need_alias)}\n")

    # ----- B) per-Q-ID series fetch (only where missing) -----
    series_added = 0
    for i, (cid, qid) in enumerate(pairs):
        md = games[cid].setdefault("metadata", {})
        # Apply aliases (always — cheap, idempotent).
        ent = cache.get(qid) or {}
        aliases = ent.get("aliases") or []
        if aliases:
            existing = md.get("alt_titles") or []
            # Stable merge — preserve manual edits, dedupe.
            merged = list(existing)
            for a in aliases:
                if a not in merged and a != md.get("title"):
                    merged.append(a)
            if merged != existing:
                md["alt_titles"] = merged
                _stamp(md, "wikidata-aliases")

        # Series — only fetch if Wikidata didn't already fill it.
        if md.get("series"):
            continue
        if "series" not in ent:
            wp_title = ent.get("wp_title")
            if wp_title:
                ent["series"] = fetch_series_from_wikipedia(wp_title)
                cache[qid] = ent
        s = ent.get("series")
        if s:
            md["series"] = s
            series_added += 1
            _stamp(md, "wikipedia-infobox")
        if i % 25 == 0:
            sys.stderr.write(f"[B] {i}/{len(pairs)}  series_added={series_added}\n")

    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    games_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    sys.stderr.write(f"[done] aliases applied across {len(pairs)} carts; "
                     f"series filled on {series_added} new carts\n")
    return 0


def _stamp(md, source):
    s = f"{source}@{date.today().isoformat()}"
    arr = list(md.get("enriched_from") or [])
    if s not in arr: arr.append(s)
    md["enriched_from"] = arr


if __name__ == "__main__":
    sys.exit(main())
