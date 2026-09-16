"""Synthetic tract data shaped like the real challenge dataset, for testing the app
before real data is downloaded. Regional missing-part rates are calibrated to the
figures already published on the challenge page (55/37/28/21%); tribal and high-SVI
tracts are given elevated missingness so the app can show whether that hypothesis
holds once real data replaces this.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

REGIONS = {
    "Maricopa": 0.55,
    "Northern California": 0.37,
    "South-Central Texas": 0.28,
    "Eastern Oklahoma": 0.21,
}


def generate(n_per_region: int = 150, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    tract_seq = 0
    for region, base_missing_rate in REGIONS.items():
        for _ in range(n_per_region):
            tract_seq += 1
            geoid = f"{abs(hash(region)) % 9000 + 1000}{tract_seq:06d}"  # kept as string throughout
            tribal = rng.random() < 0.12
            svi_quartile = int(rng.integers(1, 5))
            rural = rng.random() < (0.55 if region != "Maricopa" else 0.25)
            wildfire_exp = rng.random() < (0.4 if region == "Northern California" else 0.15)
            heat_exp = rng.random() < (0.5 if region == "Maricopa" else 0.2)

            # elevated missingness for tribal + high-SVI + rural tracts -- the bias we expect to confirm
            miss_boost = (0.25 if tribal else 0) + (0.15 if svi_quartile == 4 else 0) + (0.10 if rural else 0)
            miss_rate = min(base_missing_rate + miss_boost, 0.95)

            def maybe_missing(p_extra=0.0):
                return rng.random() < min(miss_rate + p_extra, 0.97)

            roads_ref = np.nan if maybe_missing() else rng.integers(1, 40)
            buildings_ref = np.nan if maybe_missing(-0.35) else rng.integers(20, 900)  # buildings rarely fully absent
            fire_ref = np.nan if maybe_missing(0.05) else rng.integers(0, 3)
            ems_ref = np.nan if maybe_missing(0.05) else rng.integers(0, 3)
            schools_ref = np.nan if maybe_missing(0.02) else rng.integers(0, 5)
            establishments_ref = np.nan if maybe_missing(-0.1) else rng.integers(5, 300)

            ratio_regional = rng.uniform(0.71, 1.59)  # the road ratio spread the page warns about

            def overture_from(ref, spread=0.3):
                if np.isnan(ref):
                    return rng.integers(0, 5) if rng.random() < 0.3 else np.nan
                factor = np.clip(rng.normal(loc=1.0, scale=spread), 0.05, 1.6)
                return max(0, ref * factor)

            roads_overture = overture_from(roads_ref) if not np.isnan(roads_ref) else (overture_from(roads_ref))
            if not np.isnan(roads_ref):
                roads_overture = max(0, roads_ref * ratio_regional * np.clip(rng.normal(1.0, 0.15), 0.3, 1.8))
            buildings_overture = overture_from(buildings_ref, spread=0.25)
            fire_overture = overture_from(fire_ref, spread=0.4)
            ems_overture = overture_from(ems_ref, spread=0.4)
            schools_overture = overture_from(schools_ref, spread=0.3)
            establishments_overture = overture_from(establishments_ref, spread=0.35)

            rows.append(dict(
                GEOID=geoid,
                region=region,
                tribal=tribal,
                svi_quartile=svi_quartile,
                rural_urban="rural" if rural else "urban",
                wildfire_exposure=wildfire_exp,
                heat_exposure=heat_exp,
                roads_ref=roads_ref, roads_overture=roads_overture,
                buildings_ref=buildings_ref, buildings_overture=buildings_overture,
                fire_ref=fire_ref, fire_overture=fire_overture,
                ems_ref=ems_ref, ems_overture=ems_overture,
                schools_ref=schools_ref, schools_overture=schools_overture,
                establishments_ref=establishments_ref, establishments_overture=establishments_overture,
            ))
    df = pd.DataFrame(rows)
    df["GEOID"] = df["GEOID"].astype(str)
    return df
