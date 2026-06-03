#!/usr/bin/env python3
"""Fetch the community settings spreadsheet and normalize rows into the
intermediate format consumed by filter_community.py.

    python tools/import_sheet.py [--sheet-url URL] [--out PATH]

Pulls the published-as-CSV export of the configured Google Sheet, applies
column_map.yaml to translate sheet column headers into our schema's
settings keys, and emits tools/intermediate.json:

    {
      "fetched_at": "ISO-8601",
      "source_url": "...",
      "rows": [
        {"cart_id": "a1b2c3d4", "title": "...", "contributor": "...",
         "settings": {...partial schema dict...}, "raw": {...original row...}},
        ...
      ]
    }

Stub: not yet implemented — see tools/README.md for the pipeline and
docs/FILTER_CRITERIA.md for the criteria filter_community.py will apply
to this output.
"""

import sys


def main():
    sys.stderr.write(
        "tools/import_sheet.py: stub — implementation pending Phase 3 of the\n"
        "Analogue3DSettings build-out. See tools/README.md.\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
