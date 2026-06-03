#!/usr/bin/env python3
"""Validate every collection's games.json against the canonical schema.

    python tools/validate.py [collection_id ...]

With no args, validates all collections. Exits non-zero on the first failure
so CI can gate PRs on it. Schema-only — does NOT enforce editorial-collection
rules (those are in curate_editorial.py).
"""

import json
import os
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    sys.stderr.write(
        "tools/validate.py needs jsonschema:  pip install jsonschema\n")
    sys.exit(2)


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "game-settings.v1.json"
COLLECTIONS = ROOT / "collections"


def main(argv):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    ids = argv[1:] or sorted(p.name for p in COLLECTIONS.iterdir() if p.is_dir())
    errors = 0
    for cid in ids:
        games_file = COLLECTIONS / cid / "games.json"
        if not games_file.exists():
            print(f"[skip] {cid}: no games.json", file=sys.stderr)
            continue
        data = json.loads(games_file.read_text(encoding="utf-8"))
        for cart_id, entry in data.get("games", {}).items():
            settings = entry.get("settings", {})
            for err in validator.iter_errors(settings):
                errors += 1
                print(f"[fail] {cid}/{cart_id}: {err.message} "
                      f"(at {'/'.join(map(str, err.absolute_path)) or '<root>'})",
                      file=sys.stderr)
        print(f"[ok]   {cid}: {len(data.get('games', {}))} entries")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main(sys.argv)
