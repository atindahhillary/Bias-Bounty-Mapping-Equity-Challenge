# Best Bias Discovery: One reference layer is quietly deciding the whole score

## The pattern

`coverage_gap_score` is defined as the mean of whichever of the three components
(`transport_gap`, `building_gap`, `poi_gap`) have a reference to compare against. Across all
9,379 scored tracts, that rule doesn't spread evenly:

| Component | % of tracts with a reference to compare against |
|---|---|
| Buildings (Microsoft footprints) | 99.9% |
| Places (HIFLD facilities + CBP establishments) | 99.7% |
| **Roads (TIGER named highway)** | **67.5%** |

Buildings and places are defined almost everywhere. Roads are the one component that's
routinely missing -- 32.5% of all tracts have no TIGER `S1100`/`S1200` highway at all. When that
happens, and the tract also has no HIFLD facility and no CBP establishment on record, its entire
`coverage_gap_score` collapses to whatever the **building** component alone says. Building
coverage from Overture is good almost everywhere, so that lone surviving component is usually
near zero -- meaning a real, populated community can score as "near-perfect coverage" while the
two components that actually matter for emergency response (can a router find a road into this
tract, is there a fire station or business on record) are silently absent, not measured, not
zero.

This is not a restatement of the automated Bias Score's five metrics (Coverage Disparity Ratio,
POI Desert Index, Emergency Access Gap, Road Network Equity Ratio, Climate-Justice Composite).
Those metrics compare mean `coverage_gap_score` across strata -- they take the masked score at
face value. This finding is about *why* that score is sometimes meaningless: not "tribal tracts
score worse," but "some tracts' scores are decided entirely by the one reference layer that
happens to have data, and it's rarely the one that matters for dispatch or evacuation."

**It also runs the other way from the intuitive guess.** Naively, you'd expect this masking to
concentrate in tribal and rural tracts. It doesn't: rural tracts are missing a highway only 7.3%
of the time, versus 38.2% for urban tracts, because a large rural tract is far more likely to
have *some* stretch of state highway crossing it than a small, purely residential urban tract is.
The masking problem here is concentrated in **urban, non-tribal, small-population tracts** --
which is itself worth stating plainly, because it means fixing this scoring rule can't be done by
just adding a rural or tribal adjustment.

## The evidence: 15 named tracts, real population, one working reference layer

These are tracts where `parts_defined == 1` (only the building component exists), that lone
component scores near zero, and the tract has real population -- not water tracts or empty land.
Verified against the raw counts before trusting them (spot-checked, e.g., GEOID `48001950402`:
`tiger_len_m=0`, `cbp_estab_bus=0`, `hifld_fire/ems/schools=0`, but `overture_buildings=165` vs
`ms_buildings=151` and `overture_places_total=9` -- Overture genuinely has map data there; the
*reference* layers are the ones with nothing to compare it against).

| GEOID | Region | Population | `coverage_gap_score` | Would be, unmasked | Notes |
|---|---|---:|---:|---:|---|
| 48001950402 | South-Central TX | 7,115 | 0.000 | 0.667 | No TIGER highway, no CBP establishment, no HIFLD facility |
| 48473980000 | South-Central TX | 5,841 | 0.000 | 0.667 | Same pattern |
| 06061023600 | Northern CA (fire corridor) | 4,361 | 0.0004 | 0.667 | Butte/Shasta/Tehama wildfire region |
| 48121020111 | South-Central TX | 4,402 | 0.006 | 0.667 | |
| 04013082020 | Maricopa, AZ | 4,027 | 0.023 | 0.667 | Heat/drought region |
| 48085031633 | South-Central TX | 3,636 | 0.000 | 0.667 | |
| 04013103305 | Maricopa, AZ | 3,536 | 0.000 | 0.667 | Only component defined here is POI, not buildings |
| 06061021048 | Northern CA (fire corridor) | 3,439 | 0.005 | 0.667 | |
| 48113019301 | South-Central TX | 3,098 | 0.000 | 0.667 | |
| 48201251401 | South-Central TX | 3,011 | 0.002 | 0.667 | |
| 04013116707 | Maricopa, AZ | 2,730 | 0.000 | 0.667 | |
| 48491020609 | South-Central TX | 2,297 | 0.000 | 0.667 | |
| 40143009014 | Eastern OK | 1,924 | 0.000 | 0.667 | **Tribal tract** |
| 04019004054 | Maricopa, AZ | 1,496 | 0.000 | 0.667 | |
| 04013940700 | Maricopa, AZ | 88 | 0.000 | 0.667 | **Tribal, rural** -- smallest population, included because it's the clearest tribal+rural case in the pattern |

(Four more tracts show the identical pattern with zero recorded population -- `04005980200`,
`04013980700`, `04027980003`, `48465980000` -- excluded from the table above as likely
water-dominated or genuinely uninhabited, but flagged here per the challenge's own edge-case
guidance rather than silently dropped.)

## Why it matters

- **Dispatch and evacuation routing don't see these tracts as measured at all.** A router built
  on this coverage-gap metric can't distinguish "this community has excellent road mapping" from
  "this community was never checked" -- both currently read as ~0.000 to ~0.02, the best possible
  score band.
- **A 7,000-person tract (48001950402) is scored identically to a fully-instrumented downtown
  block**, purely because Overture happens to have mapped its buildings well. Whether Overture
  has mapped a single road anyone could actually drive an ambulance down through that tract is
  not part of the number at all.
- **The tribal example (40143009014, Eastern OK, pop. 1,924)** shows the pattern isn't only a
  Texas/Arizona artifact -- it reproduces in a tribal statistical area in the drought/heat region
  the challenge itself flagged as high-risk.
- **FEMA/NGO resource allocation that uses a metric like this at face value** would rank these 15
  communities as adequately mapped. The honest answer is "unmeasured," not "low-gap," and those
  are very different things to act on before a wildfire, heat wave, or drought.

## Reproducing this

1. Run `python scripts/run_pipeline.py` against the public challenge bucket (no credentials
   needed) to get `data/tracts.csv`.
2. Filter to `parts_defined == 1` and `coverage_gap_score < 0.05` — this is the exact query
   behind the table above.
3. Cross-reference `transport_defined`, `building_defined`, `poi_defined` to confirm which single
   component is carrying the score, and `pop_total` from the strata table to exclude
   water/uninhabited tracts.

All code: [`src/pipeline.py`](src/pipeline.py) (the per-tract computation) and
[`scripts/run_pipeline.py`](scripts/run_pipeline.py) (the run that produced `data/tracts.csv`).
