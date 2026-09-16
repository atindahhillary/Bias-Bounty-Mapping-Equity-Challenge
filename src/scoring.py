"""Core scoring math for the Overture coverage-gap challenge.

Schema assumed per tract (one row, GEOID as string):
  roads_ref, roads_overture           -- TIGER S1100/S1200 vs Overture motorway/trunk/primary/secondary
  buildings_ref, buildings_overture   -- authoritative building count vs Overture building count (no ACS)
  fire_ref, fire_overture             -- USGS facility counts
  ems_ref, ems_overture
  schools_ref, schools_overture
  establishments_ref, establishments_overture
Any *_ref value of NaN means "nothing to compare against" -> that part is dropped, not zeroed.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

PART_PAIRS = {
    "roads": ("roads_ref", "roads_overture"),
    "buildings": ("buildings_ref", "buildings_overture"),
    "places": None,  # composite, handled separately
}

FACILITY_PAIRS = [("fire_ref", "fire_overture"), ("ems_ref", "ems_overture"), ("schools_ref", "schools_overture")]
ESTABLISHMENT_PAIR = ("establishments_ref", "establishments_overture")


def component_gap(ref: pd.Series, overture: pd.Series, clip_low: bool = True, clip_high: bool = True) -> pd.Series:
    """gap = 1 - overture/ref, undefined (NaN) when ref is NaN or 0.

    clip_low  -> floor negative gaps (Overture over-counts) at 0, the "don't reward over-mapping" reading.
    clip_high -> ceiling gaps above 1 at 1 (Overture has nothing, ref has plenty).
    """
    ref = ref.astype(float)
    overture = overture.astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = 1 - (overture / ref)
    raw = raw.where(ref.notna() & (ref != 0))
    if clip_low:
        raw = raw.clip(lower=0)
    if clip_high:
        raw = raw.clip(upper=1)
    return raw


def facility_gap(df: pd.DataFrame, **clip_kwargs) -> pd.Series:
    """Places-facilities sub-score: average of fire/EMS/schools gaps that are defined."""
    gaps = [component_gap(df[r], df[o], **clip_kwargs) for r, o in FACILITY_PAIRS]
    stacked = pd.concat(gaps, axis=1)
    return stacked.mean(axis=1, skipna=True)


def places_gap(df: pd.DataFrame, **clip_kwargs) -> pd.Series:
    """Places = half facilities (fire/EMS/schools avg), half establishments."""
    fac = facility_gap(df, **clip_kwargs)
    est = component_gap(df[ESTABLISHMENT_PAIR[0]], df[ESTABLISHMENT_PAIR[1]], **clip_kwargs)
    both = pd.concat([fac, est], axis=1)
    both.columns = ["facilities", "establishments"]
    # if only one side is defined, the doc's "average of parts that exist" rule applies at the top level,
    # but places itself is defined as (facilities + establishments)/2 with each side potentially undefined too.
    return both.mean(axis=1, skipna=True)


def per_tract_parts(df: pd.DataFrame, **clip_kwargs) -> pd.DataFrame:
    """Returns roads/buildings/places gap columns plus parts_defined count and overall score."""
    out = pd.DataFrame(index=df.index)
    out["roads_gap"] = component_gap(df["roads_ref"], df["roads_overture"], **clip_kwargs)
    out["buildings_gap"] = component_gap(df["buildings_ref"], df["buildings_overture"], **clip_kwargs)
    out["places_gap"] = places_gap(df, **clip_kwargs)
    part_cols = ["roads_gap", "buildings_gap", "places_gap"]
    out["parts_defined"] = out[part_cols].notna().sum(axis=1)
    out["score_coverage"] = out[part_cols].mean(axis=1, skipna=True)  # official rule: average of defined parts only
    out["score_hidden_gap"] = out[part_cols].fillna(1.0).mean(axis=1)  # treat missing as full gap (Part 2 finding)
    return out


def rmse(a: pd.Series, b: pd.Series) -> float:
    a, b = a.align(b, join="inner")
    return float(np.sqrt(np.mean((a.values - b.values) ** 2)))


def constant_submission_solve(c1: float, r1: float, c2: float, r2: float) -> tuple[float, float]:
    """Given two constant submissions c1,c2 and their returned RMSE r1,r2 against the hidden
    reference, solve RMSE^2 = variance + (mean-c)^2 for (mean, variance) of the reference scores.
    """
    if c2 == c1:
        raise ValueError("c1 and c2 must differ")
    mean = (r1**2 - r2**2 - c1**2 + c2**2) / (2 * (c2 - c1))
    variance = r1**2 - (mean - c1) ** 2
    return mean, variance


def expected_rmse_for_constant(c: float, mean: float, variance: float) -> float:
    return float(np.sqrt(variance + (mean - c) ** 2))
