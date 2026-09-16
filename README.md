# Bias Bounty: Mapping Equity Challenge

Working system for the Overture-vs-reference coverage-gap challenge. Two goals, one tool:

1. **Get on the leaderboard** by reverse-engineering the scoring formula exactly (RMSE against a
   fixed reference, not something to model), not by training anything.
2. **Win Best Bias Discovery / Best Documentation** with the real finding: the scoring rule drops
   any coverage part (roads, buildings, places) that has nothing in the reference data to compare
   against, so the tracts hardest to map score artificially close to "full coverage."

Live writeup draft: **https://atindahhillary.github.io/Bias-Bounty-Mapping-Equity-Challenge/**
(seeded from synthetic demo data until the real challenge export is loaded — see below).

## Run the workbench

```bash
pip install -r requirements.txt
streamlit run app.py
```

Three tabs:

- **Formula Lab** — solves the constant-submission trick (`RMSE^2 = variance + (mean-c)^2`) for
  the hidden reference mean/variance, tracks your 10-submissions/day budget, exports the
  prediction CSV for whichever formula variant you're testing.
- **Bias Discovery** — parts-defined-per-tract counts, breakdowns by any strata column (region,
  tribal, SVI quartile, rural/urban, wildfire/heat exposure, or any of the ~232 columns in the
  real export), and the hidden-gap re-score that ranks tracts by how much their score would rise
  if a missing part counted as a full gap instead of being dropped.
- **Writeup** — auto-drafts the "yardstick is missing where the risk is" narrative from whatever
  is currently loaded, editable, exportable as Markdown, and can regenerate `docs/index.html` for
  GitHub Pages.

## Loading real data

Drop the actual challenge export at `data/tracts.csv` (see [`data/README.md`](data/README.md) for
the exact schema and the traps to avoid — GEOID as text, TIGER `S1100`/`S1200` only, no ACS
housing counts, hospitals excluded). It's gitignored on purpose; don't commit real challenge data
or your submission log to this public repo.

Regenerate the static writeup without launching Streamlit:

```bash
python scripts/build_writeup.py
```

## Status

Currently running on synthetic demo data calibrated to the regional missing-part rates already
published on the challenge page (Maricopa 55%, Northern California 37%, South-Central Texas 28%,
Eastern Oklahoma 21%), with elevated missingness for tribal/high-SVI/rural tracts to test the
core hypothesis. Swap in the real export to replace every number here with the actual finding.
