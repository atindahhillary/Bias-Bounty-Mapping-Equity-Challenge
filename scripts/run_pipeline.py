"""Runs the real coverage-gap pipeline for all four regions against the public challenge
bucket and writes data/<region>-computed.csv for each, plus a combined data/tracts.csv.
Safe to re-run: each region is written as soon as it finishes, so a later failure doesn't
lose earlier regions.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from src.pipeline import compute_region, fetch_strata, REGIONS, _connect

DATA_DIR = ROOT / "data"


def main():
    con = _connect()
    con.sql("SET enable_progress_bar=false;")
    frames = []
    for region in REGIONS:
        out_path = DATA_DIR / f"{region}-computed.csv"
        if out_path.exists():
            print(f"[{region}] already computed, loading from disk")
            df = pd.read_csv(out_path, dtype={"GEOID": str})
        else:
            t0 = time.time()
            print(f"[{region}] computing...", flush=True)
            df = compute_region(region, con=con)
            df.to_csv(out_path, index=False)
            print(f"[{region}] done in {time.time()-t0:.1f}s -- {len(df)} tracts, "
                  f"{(df['parts_defined'] < 3).mean()*100:.1f}% missing >=1 part", flush=True)

        strata_path = DATA_DIR / f"{region}-strata.csv"
        if strata_path.exists():
            strata = pd.read_csv(strata_path, dtype={"GEOID": str})
        else:
            print(f"[{region}] fetching strata...", flush=True)
            strata = fetch_strata(region, con=con)
            strata.to_csv(strata_path, index=False)
        df = df.merge(strata, on="GEOID", how="left")
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined.to_csv(DATA_DIR / "tracts.csv", index=False)
    print(f"combined: {len(combined)} tracts -> data/tracts.csv")


if __name__ == "__main__":
    main()
