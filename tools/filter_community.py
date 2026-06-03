#!/usr/bin/env python3
"""Apply community-best filter criteria to tools/intermediate.json and write
collections/community-best/games.json.

Rules (see docs/FILTER_CRITERIA.md for full explanation):

  1. Minimum votes (default 2) — drop games with too few independent picks.
  2. Per-setting plurality — value = most-voted choice across contributors.
  3. Tie-break — `tools/tie_break.yaml` lists preferred values
     (default: bias toward original-hardware authenticity).
  4. Schema validation — every emitted entry passes
     `schema/game-settings.v1.json`; failures go to outliers.log instead of
     silently coercing.

Stub: not yet implemented.
"""

import sys


def main():
    sys.stderr.write(
        "tools/filter_community.py: stub — implementation pending Phase 3.\n"
        "See docs/FILTER_CRITERIA.md for the rules this will implement.\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
