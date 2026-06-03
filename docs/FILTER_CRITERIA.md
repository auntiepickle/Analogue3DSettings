# Filter criteria — how the community sheet becomes a collection

The community Google Sheet is the **raw input**. Two collections derive from
it via tools in `tools/`, each with explicit, defensible filtering rules.

## `community-best` — consensus only

Goal: a faithful "what the community actually picked" snapshot. No editorial
override. Useful as a baseline both for users and for our own
[`editorial`](../collections/editorial/) layer.

`tools/import_sheet.py` + `tools/filter_community.py` apply these rules:

1. **Minimum votes** — drop any game with fewer than `N` independent
   recommendations (default `N=2`). Single-voice picks are noise.
2. **Per-setting majority** — for each setting key, the value is whichever
   choice the *plurality* of contributors picked.
3. **Tie-break** — when two values tie, prefer the one closer to original
   hardware (`forceOriginalHardware: true`, `disableDeblur: false`,
   `region: 'Auto'`, etc.). Documented in `tools/tie_break.yaml`.
4. **Schema validation** — every emitted entry is validated against
   `schema/game-settings.v1.json` and dropped (with a logged reason) if it
   doesn't conform.
5. **Outlier flagging** — picks that fall outside the schema's enum (e.g. a
   typoed display mode) are written to `tools/outliers.log` for manual
   curator review rather than silently coerced.
6. **No interpretation** — `community-best` MUST NOT contain any setting that
   doesn't come directly from the sheet data. Editorial opinions live in the
   editorial collection.

A game entry looks like:

```json
"a1b2c3d4": {
  "title": "Mario Kart 64",
  "settings": { /* fully-qualified per the schema */ },
  "source": { "votes": 7, "sheet_row": 132 }
}
```

## `editorial` — opinions and dissent

Goal: our best pick per game. Starts from `community-best` and overrides
where we have a defensible reason. Authored by hand; the tools below assist
but don't decide.

Every entry MUST carry a `rationale` field. Entries that **diverge** from
the consensus MUST also carry a `dissent` block:

```json
"a1b2c3d4": {
  "title": "Mario Kart 64",
  "settings": { /* may differ from community */ },
  "rationale": "Why we picked these — short, defensible.",
  "dissent": {
    "from": "community-best",
    "diff": { "hardware.disableDeblur": { "ours": false, "theirs": true } },
    "reason": "Plain-language explanation of why we disagree."
  }
}
```

`tools/curate_editorial.py` is a *scaffolding* helper, not a decider. It:

- diffs the editorial collection against community-best,
- warns when an editorial entry overrides a setting without a `dissent` block,
- warns when a `dissent` references a community value that no longer matches
  the current `community-best` snapshot (so we keep our criticism honest
  when the community changes its mind).

## Adding a new criterion

Either filter pass is open to PRs. Two grounding rules:

1. Criteria MUST be expressible as a deterministic transform on the raw
   data plus a config file — no "the maintainer's gut feel" inside the
   pipeline (that's what the editorial collection is for).
2. Adding a criterion that drops games or overrides a community pick MUST
   include a small fixtures test under `tests/` showing the before/after on
   representative rows. This keeps the criteria reviewable.
