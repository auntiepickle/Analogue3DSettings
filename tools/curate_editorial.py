#!/usr/bin/env python3
"""Lint collections/editorial/games.json against collections/community-best.

  - Every editorial setting that differs from community-best MUST carry a
    matching `dissent` block (game-level) explaining the divergence.
  - Every `dissent.diff` MUST reference a setting whose community-best value
    is what dissent.diff[<key>].theirs claims — so when the community
    revises a pick, our criticism doesn't quietly drift to stale.

Does NOT modify any files — read-only lint. Exits non-zero on first failure.

Stub: not yet implemented.
"""

import sys


def main():
    sys.stderr.write(
        "tools/curate_editorial.py: stub — implementation pending Phase 3.\n"
        "See docs/FILTER_CRITERIA.md for the rules this will enforce.\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
