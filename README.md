# Bias Bounty: Mapping Equity Challenge

Working system for [Zindi's Bias Bounty Mapping Equity Challenge](https://zindi.world/competitions/bias-bounty-mapping-equity-challenge)
($10,000 USD, closes 1 Nov 2026). Two goals, one tool:

1. **Get on the leaderboard** by computing the coverage-gap score exactly as documented --
   the formula isn't hidden, it's fully specified in the challenge data's own README, so this
   is direct computation, not modeling.
2. **Win Best Bias Discovery / Best Documentation** with the real finding: the scoring rule
   drops any coverage component (roads, buildings, places) that has nothing in the reference
   data to compare against, so the tracts hardest to map score artificially close to "full
   coverage." Missingness turns out to be driven almost entirely by the **road** component
   (no named highway on record), not buildings or POIs.

Live writeup draft: **https://atindahhillary.github.io/Bias-Bounty-Mapping-Equity-Challenge/**

## Data source

All challenge data is public, no signup: `source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge`.
`src/pipeline.py` queries it directly over HTTPS via DuckDB's `httpfs`/`spatial` extensions --
nothing needs to be downloaded first, though the full run does pull real compute (spatial joins
over up to 4.4M building footprints for the largest region).

## Run it

```bash
pip install -r requirements.txt
python scripts/run_pipeline.py    # computes all 4 regions from the live bucket -- takes a while
streamlit run app.py
```

Three tabs:

- **Submission Lab** — the per-region submission CSV, already in the exact
  `<region>-sample-submission.csv` shape with real components filled in; a constant-submission
  RMSE cross-check; a 10-per-day / 300-total submission budget tracker.
- **Bias Discovery** — parts-defined-per-tract counts, breakdowns by real strata (urban/rural,
  SVI, tribal, drought, wildfire hazard, heat days), which component drives the missingness,
  and the hidden-gap re-score that ranks tracts by how much their score would rise if a missing
  component counted as a full gap instead of being dropped.
- **Writeup** — auto-drafts the "yardstick is missing where the risk is" narrative from whatever
  is currently loaded, editable, exportable as Markdown, regenerates `docs/index.html` for
  GitHub Pages.

## Method (validated against the challenge's own published numbers)

See [`data/README.md`](data/README.md) for the exact formula. `src/pipeline.py` was checked
against the README's claim that northern-ca has exactly 218 of 591 tracts with no named highway
at all (transport component undefined) — it reproduces that number exactly before anything else
was trusted.

## Status

Pipeline runs against the live challenge bucket; `data/` is gitignored (regenerate with
`python scripts/run_pipeline.py`, real challenge data shouldn't live in a public repo anyway).
