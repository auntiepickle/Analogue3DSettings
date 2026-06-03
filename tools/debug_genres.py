#!/usr/bin/env python3
"""Dump every genre Q-ID Wikidata returns for the carts in a collection,
along with their English labels, sorted by frequency. Use the output to
populate GENRE_CANON in enrich_wikidata.py — anything that shows up enough
times to matter, but is missing from the canon, is what we should add.

    python tools/debug_genres.py [--collection community-best] [--top 30]

Reads each cart's external_ids.wikidata so it doesn't have to re-resolve
titles. Hits the SPARQL endpoint with rate-limit sleep; cached under
tools/.genre_debug_cache.json so re-runs are cheap.
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tools" / ".genre_debug_cache.json"

ENDPOINT = "https://query.wikidata.org/sparql"
UA = "Analogue3DSettings-genre-debug/0.1 (+https://github.com/auntiepickle/Analogue3DSettings)"


def sparql(query):
    time.sleep(0.3)
    url = f"{ENDPOINT}?{urllib.parse.urlencode({'query': query, 'format': 'json'})}"
    req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--collection", default="community-best")
    p.add_argument("--top", type=int, default=30)
    args = p.parse_args()

    games = json.loads((ROOT / "collections" / args.collection / "games.json").read_text("utf-8"))["games"]
    qids = sorted({(v.get("metadata") or {}).get("external_ids", {}).get("wikidata")
                   for v in games.values()} - {None})
    sys.stderr.write(f"[start] {len(qids)} carts with Wikidata Q-IDs\n")

    cache = json.loads(CACHE.read_text("utf-8")) if CACHE.exists() else {}
    counter = Counter()
    labels = {}
    for i, qid in enumerate(qids):
        if qid not in cache:
            try:
                body = sparql(f"""
                    SELECT ?g ?gl WHERE {{
                      wd:{qid} wdt:P136 ?g .
                      ?g rdfs:label ?gl . FILTER (LANG(?gl) = "en")
                    }}""")
                cache[qid] = [(b["g"]["value"].rsplit("/", 1)[-1], b["gl"]["value"])
                              for b in body.get("results", {}).get("bindings", [])]
            except Exception as e:
                sys.stderr.write(f"[err] {qid}: {e}\n")
                cache[qid] = []
        for gqid, glabel in cache[qid]:
            counter[gqid] += 1
            labels[gqid] = glabel
        if i % 25 == 0:
            sys.stderr.write(f"[prog] {i}/{len(qids)}\n")

    CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\n# Top {args.top} genre Q-IDs across {len(qids)} N64 carts")
    print(f"# Add to GENRE_CANON in tools/enrich_wikidata.py if not already mapped.\n")
    print(f"{'count':>5}  {'Q-ID':<14}  label")
    for gqid, n in counter.most_common(args.top):
        print(f"{n:>5}  {gqid:<14}  {labels[gqid]}")


if __name__ == "__main__":
    sys.exit(main())
