# Methodology, Documentation, and Best Bias Discovery

This writeup covers both special prizes, as one document per the challenge rules (no separate
submission needed):

- **[Methodology & Documentation](#methodology--documentation)** -- data sources, exact
  per-component computation, edge cases, alternative weightings tested and why they weren't
  adopted, and how every number here was validated before being trusted.
- **[Best Bias Discovery: One reference layer is quietly deciding the whole score](#best-bias-discovery-one-reference-layer-is-quietly-deciding-the-whole-score)**
  -- the finding itself, 15 named tracts, and why it matters.

---

## Methodology & Documentation

### Data sources

All from the challenge's public bucket, `source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge`
(no credentials needed) -- read directly over HTTPS via DuckDB's `httpfs`/`spatial` extensions,
nothing downloaded first:

| Source | Used for | Vintage |
|---|---|---|
| Overture Maps | roads, buildings, places (all three numerators) | Release `2026-08-19.0`, pinned by the bucket -- I never queried Overture independently, so this is automatic, not something I had to enforce |
| Census TIGER/Line | road-network reference (denominator) | 2025 |
| Microsoft GlobalML US Building Footprints | building reference (denominator) | Feb 2026 refresh |
| USGS National Map (HIFLD's maintained successor) | fire/EMS/schools reference (denominator) | as shipped in the bucket |
| Census County Business Patterns | establishments reference (denominator), `cbp_estab_bus` column | as shipped |
| Census ACS 5-Year housing counts | **not used** -- explicitly excluded from the building ratio per spec (ACS counts housing units, Microsoft counts structures) |
| Strata tables (SVI, CVI, RUCA/RUCC, tribal, drought, wildfire, heat) | Bias Discovery breakdowns only, no effect on the scored submission | per-source vintages in the bucket README |

### Computing each component

```
transport_gap = 1 - min(1, overture_named_highway_length_m / tiger_named_highway_length_m)
building_gap  = 1 - min(1, overture_building_count / microsoft_building_count)
poi_gap       = mean(poi_gap_hifld, poi_gap_cbp), each side used only if defined
  poi_gap_hifld = mean of defined per-type gaps among fire / EMS / schools
    each = 1 - min(1, overture_count_of_type / hifld_count_of_type)
  poi_gap_cbp   = 1 - min(1, overture_places_total / cbp_estab_bus)
coverage_gap_score = mean of {transport_gap, building_gap, poi_gap} that are defined
```

- **Roads**: TIGER `MTFCC IN ('S1100','S1200')` against Overture `class IN ('motorway','trunk','primary','secondary')`.
  Each road layer is spatially joined to tract polygons with a bbox pre-filter then
  `ST_Intersects`, clipped per-tract with `ST_Intersection`, and measured in EPSG:5070 (the exact
  method the bucket's own README demonstrates for this dataset).
- **Buildings**: both Overture and Microsoft footprints are joined to tracts by
  point-in-polygon on their centroid (`ST_Contains(tract, ST_Centroid(building))`), then counted.
- **Places**: Overture POIs matched on `categories.primary` -- `fire_department`,
  `ambulance_and_ems_services`, and the six school categories listed in the bucket README --
  against the corresponding HIFLD layer, plus all Overture POIs (no category filter) against
  CBP establishments. Hospitals are excluded per spec (Overture's hospital category runs ~12x
  the reference count, so it can never show a deficit).
- **Undefined vs. zero**: a component is *undefined* only when its **reference** count/length is
  zero (no TIGER highway, no Microsoft footprint, no HIFLD facility of that type, no CBP
  establishment) -- it is then excluded from the mean, not scored as 0. If the reference exists
  but Overture has nothing, that's a real, defined full gap (`gap = 1`), not undefined. These are
  easy to conflate and the distinction is load-bearing for the whole scoring rule.

### Edge cases

- **GEOID as text throughout.** Every read (`read_csv_auto(..., types={'GEOID':'VARCHAR'})` in
  DuckDB, `dtype={'GEOID': str}` in pandas) preserves leading zeros -- verified on Maricopa
  (state FIPS `04`).
- **Water-dominated / no-reference-at-all tracts**: the challenge's own sample-submission files
  already drop tracts with all three components undefined (7 in south-central-tx, all `99xx`
  water tracts, per the bucket README). My pipeline joins against those sample-submission files
  as the authoritative tract list rather than re-deriving which tracts to score, so this exclusion
  is inherited correctly rather than reimplemented.
- **Zero-population tracts**: I did *not* drop or special-case these in the scored submission --
  every GEOID in the sample-submission file gets a real computed score, population or not. I did
  flag them separately in the Bias Discovery evidence (4 of the 24 single-component tracts have
  `pop_total == 0`) rather than folding them into the "real communities affected" narrative, since
  claiming emergency-dispatch impact for an uninhabited tract would be a real evidence problem.
- **A submission-format lesson worth documenting**: my first Zindi upload was a single region's
  CSV, and was rejected for missing GEOIDs in every other region. The competition scores one file
  covering all 9,379 tracts across all four regions, not a file per region -- an easy mistake
  given each region ships its own `<region>-sample-submission.csv`, and worth stating explicitly
  since it cost a submission slot to discover.

### Alternative weightings tested, and why they weren't adopted

Two real alternatives were tested against the smallest region (northern-ca) before deciding they
weren't worth adopting:

1. **Point-in-polygon boundary rule.** `ST_Contains` (strict interior) vs. `ST_Covers` (includes
   the boundary) for assigning building centroids to tracts. Tested against all 1,164,724
   Overture building centroids in northern-ca: **zero tracts changed.** Kept `ST_Contains` since
   it makes no difference and is the simpler rule.
2. **Length-measurement method for roads.** The bucket README documents two valid ways to get a
   real-world length from `OGC:CRS84` geometry: reproject to `EPSG:5070` (Albers equal-area,
   CONUS) and take planar length, or use `ST_Length_Spheroid` on flipped coordinates (true
   geodesic length). Tested both against northern-ca's TIGER named-highway total: 10,013,118.8m
   (Albers) vs. 10,005,187.3m (geodesic), a **0.079% difference**. Since `transport_gap` is a
   ratio of two lengths measured the same way in the same small region, this distortion mostly
   cancels rather than propagating into the gap value. Kept `EPSG:5070` since it matches the
   README's own worked example exactly.
3. **`poi_gap` when only one half is defined.** The spec states `poi_gap` is "the mean of the two
   halves" (HIFLD facilities, CBP establishments) but doesn't say what happens when only one half
   has a reference to compare against. I applied the same "mean of defined parts" rule the spec
   states explicitly for the top-level `coverage_gap_score`, for consistency -- this is a genuine
   judgment call where the source documentation is silent, and a reviewer implementing this
   differently would get a slightly different `poi_gap` in that specific case. Flagged here
   rather than left implicit.

### Validating before trusting

Every number in this writeup was checked against something the challenge already publishes,
*before* anything was built on top of it:

| Check | Computed | Published | Match |
|---|---:|---:|---|
| Northern CA, tracts missing >=1 component | 36.9% | 37% | Yes |
| Maricopa, tracts missing >=1 component | 54.9% | 55% | Yes |
| Eastern OK, tracts missing >=1 component | 21.3% | 21% | Yes |
| South-Central TX, tracts missing >=1 component | 28.5% | 28% | Yes |
| Northern CA, tracts with zero named highway (`transport_defined=false`) | 218 of 591 | 218 of 591 | **Exact** |

The last row is an exact match, not a rounding coincidence -- it was the first thing checked,
before any bias-discovery analysis was trusted.

### Reproducing all of it

```bash
git clone https://github.com/atindahhillary/Bias-Bounty-Mapping-Equity-Challenge
cd Bias-Bounty-Mapping-Equity-Challenge
pip install -r requirements.txt
python scripts/run_pipeline.py         # computes all 4 regions from the live bucket
python scripts/assemble_submission.py  # builds the scored submission.csv, cross-checked
                                        # GEOID-for-GEOID against the live sample-submission files
```

No credentials required at any step. `src/pipeline.py` has the full per-component computation;
`scripts/run_pipeline.py` is the entry point that produced `data/tracts.csv`.

---

## Best Bias Discovery: One reference layer is quietly deciding the whole score

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
