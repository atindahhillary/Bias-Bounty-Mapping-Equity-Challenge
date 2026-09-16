"""Assembles the single, all-region submission file Zindi actually scores.

The competition takes ONE upload covering all 9,379 scored tracts across the four regions --
not a per-region file. Submitting only one region's CSV is exactly what produces a
"missing entries for IDs ..." rejection for every tract outside that region.

This script does not touch Overture/TIGER/HIFLD/CBP or recompute anything -- src/pipeline.py
already did that. It only:
  1. Loads data/tracts.csv (or the four data/<region>-computed.csv files if that's missing).
  2. Cross-checks the GEOID set against each region's real <region>-sample-submission.csv
     pulled live from the public challenge bucket, so a shortfall is caught before upload,
     not after a rejected submission.
  3. Writes the 17-column layout Zindi expects, GEOID read/written as text throughout.

Usage:
    python scripts/assemble_submission.py --out submission.csv
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

BASE = "https://data.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"
REGIONS = ["maricopa-az", "northern-ca", "eastern-ok", "south-central-tx"]

SUBMISSION_COLUMNS = [
    "GEOID", "coverage_gap_score", "region",
    "transport_gap", "transport_defined",
    "building_gap", "building_defined",
    "poi_gap", "poi_defined",
    "poi_gap_fire", "poi_defined_fire",
    "poi_gap_ems", "poi_defined_ems",
    "poi_gap_schools", "poi_defined_schools",
    "poi_gap_cbp", "poi_defined_cbp",
]


def load_computed() -> pd.DataFrame:
    combined_path = ROOT / "data" / "tracts.csv"
    if combined_path.exists():
        return pd.read_csv(combined_path, dtype={"GEOID": str})

    frames = []
    for region in REGIONS:
        path = ROOT / "data" / f"{region}-computed.csv"
        if not path.exists():
            sys.exit(
                f"Missing {path}. Run `python scripts/run_pipeline.py` first -- "
                f"that's what computes the per-tract gaps this script assembles."
            )
        frames.append(pd.read_csv(path, dtype={"GEOID": str}))
    return pd.concat(frames, ignore_index=True)


def official_geoids() -> dict[str, list[str]]:
    """Pulls each region's real scored-tract list straight from the public bucket --
    this is the authoritative list Zindi grades against, not an assumption."""
    import duckdb
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs; SET enable_progress_bar=false;")
    out = {}
    for region in REGIONS:
        url = f"{BASE}/reference/{region}/{region}-sample-submission.csv"
        df = con.sql(f"SELECT GEOID FROM read_csv_auto('{url}', types={{'GEOID':'VARCHAR'}})").df()
        out[region] = df["GEOID"].tolist()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="submission.csv")
    ap.add_argument("--skip-remote-check", action="store_true",
                     help="Skip cross-checking GEOIDs against the live bucket (offline mode).")
    args = ap.parse_args()

    df = load_computed()
    df["GEOID"] = df["GEOID"].astype(str)

    missing_cols = [c for c in SUBMISSION_COLUMNS if c not in df.columns]
    if missing_cols:
        sys.exit(f"data is missing required columns: {missing_cols}")

    dupes = df["GEOID"][df["GEOID"].duplicated()]
    if not dupes.empty:
        sys.exit(f"duplicate GEOIDs found, refusing to write a submission: {dupes.tolist()[:10]}")

    if not args.skip_remote_check:
        print("cross-checking GEOIDs against the live sample-submission files...")
        expected = official_geoids()
        have = set(df["GEOID"])
        problems = []
        for region, geoids in expected.items():
            want = set(geoids)
            missing = want - have
            if missing:
                problems.append(f"  {region}: missing {len(missing)} of {len(want)} tracts, "
                                 f"e.g. {sorted(missing)[:5]}")
            if len(want) != (df["region"] == region).sum():
                problems.append(f"  {region}: expected {len(want)} rows, have "
                                 f"{(df['region'] == region).sum()}")
        if problems:
            sys.exit("GEOID cross-check failed -- refusing to write a bad submission:\n" + "\n".join(problems))
        print(f"cross-check passed: {len(have)} tracts match the live sample-submission files exactly.")

    out_df = df[SUBMISSION_COLUMNS].copy()
    for col in SUBMISSION_COLUMNS:
        if out_df[col].isna().any():
            sys.exit(f"column '{col}' has blank cells -- Zindi rejects any included column with a gap")

    out_df.to_csv(args.out, index=False)
    print(f"wrote {len(out_df)} rows, {len(SUBMISSION_COLUMNS)} columns -> {args.out}")


if __name__ == "__main__":
    main()
