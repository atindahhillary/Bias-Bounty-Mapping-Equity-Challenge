# Expected data file

Drop the real challenge export here as `tracts.csv` (gitignored — don't commit real challenge
data). The app auto-detects it and switches off the synthetic demo data.

## Required columns

| Column | Notes |
|---|---|
| `GEOID` | **Read as text**, not a number (leading zeros matter) |
| `roads_ref`, `roads_overture` | TIGER `S1100`/`S1200` vs Overture `motorway`/`trunk`/`primary`/`secondary` only |
| `buildings_ref`, `buildings_overture` | Do not use ACS housing counts for `buildings_ref` |
| `fire_ref`, `fire_overture` | USGS facility counts (hospitals excluded) |
| `ems_ref`, `ems_overture` | |
| `schools_ref`, `schools_overture` | |
| `establishments_ref`, `establishments_overture` | Business establishment counts |

Leave a `*_ref` cell blank/NaN when the tract has nothing to compare against — don't fill it with
0. That's exactly the case the scoring rule drops, and the bias-discovery tab depends on being
able to tell "zero" apart from "missing."

## Strata columns (any of the ~232 columns not listed above)

Anything else in the CSV is treated as a strata column you can break down by in the Bias
Discovery tab — e.g. `region`, `tribal`, `svi_quartile`, `rural_urban`, `wildfire_exposure`,
`heat_exposure`. No need to register them anywhere; the app picks them up automatically.
