# Tools

Pipeline:

```
Google Sheet (CSV export)
    │
    ▼
tools/import_sheet.py                 fetches raw rows, applies column_map.yaml
    │
    ▼
tools/intermediate.json               raw normalized rows (one per contributor pick)
    │
    ▼
tools/filter_community.py             applies criteria/FILTER_CRITERIA.md rules
    │
    ▼
collections/community-best/games.json
    │
    ▼  (hand-curated, optional)
collections/editorial/games.json      our opinionated overlay
    │
    ▼
tools/curate_editorial.py             lint: every override needs a dissent block
    │
    ▼
tools/validate.py                     every collection conforms to schema/
```

## Files

- [`import_sheet.py`](import_sheet.py) — pull the sheet, normalize.
- [`column_map.yaml`](column_map.yaml) — sheet column → schema key mapping.
- [`filter_community.py`](filter_community.py) — apply minimum-votes, plurality, tie-break.
- [`tie_break.yaml`](tie_break.yaml) — tie-break priority list, period-correct-first.
- [`curate_editorial.py`](curate_editorial.py) — lint editorial overrides vs. community-best.
- [`validate.py`](validate.py) — every `games.json` conforms to `schema/game-settings.v1.json`.

See [`docs/FILTER_CRITERIA.md`](../docs/FILTER_CRITERIA.md) for the rules each
filter implements and the rationale behind each rule.

All scripts are stdlib-only Python 3.10+ where possible (only `import_sheet.py`
needs `requests` for the network fetch). No build step; run directly.
