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
SETTINGS_SCHEMA = ROOT / "schema" / "game-settings.v1.json"
METADATA_SCHEMA = ROOT / "schema" / "game-metadata.v1.json"
COLLECTIONS = ROOT / "collections"


def main(argv):
    s_validator = jsonschema.Draft202012Validator(
        json.loads(SETTINGS_SCHEMA.read_text(encoding="utf-8")))
    m_validator = jsonschema.Draft202012Validator(
        json.loads(METADATA_SCHEMA.read_text(encoding="utf-8"))) \
        if METADATA_SCHEMA.exists() else None
    ids = argv[1:] or sorted(p.name for p in COLLECTIONS.iterdir() if p.is_dir())
    errors = 0
    for cid in ids:
        games_file = COLLECTIONS / cid / "games.json"
        if not games_file.exists():
            print(f"[skip] {cid}: no games.json", file=sys.stderr)
            continue
        data = json.loads(games_file.read_text(encoding="utf-8"))
        for cart_id, entry in data.get("games", {}).items():
            for err in s_validator.iter_errors(entry.get("settings", {})):
                errors += 1
                print(f"[fail] {cid}/{cart_id}/settings: {err.message} "
                      f"(at {'/'.join(map(str, err.absolute_path)) or '<root>'})",
                      file=sys.stderr)
            if m_validator and "metadata" in entry:
                for err in m_validator.iter_errors(entry["metadata"]):
                    errors += 1
                    print(f"[fail] {cid}/{cart_id}/metadata: {err.message} "
                          f"(at {'/'.join(map(str, err.absolute_path)) or '<root>'})",
                          file=sys.stderr)
        print(f"[ok]   {cid}: {len(data.get('games', {}))} entries")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main(sys.argv)
