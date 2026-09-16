"""Sanity check before trusting anything else: the README states northern-ca has exactly
218 of 591 scored tracts with transport_defined = false (no TIGER S1100/S1200 at all).
If this doesn't match, the spatial join logic is wrong and nothing downstream can be trusted.
"""
import duckdb

BASE = "https://data.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"
REGION = "northern-ca"

con = duckdb.connect()
con.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")

tracts_url = f"{BASE}/strata/{REGION}/{REGION}-census-tracts.parquet"
tiger_url = f"{BASE}/reference/{REGION}/{REGION}-census-tiger-roads.parquet"
sample_url = f"{BASE}/reference/{REGION}/{REGION}-sample-submission.csv"

n_scored = con.sql(f"SELECT count(*) FROM read_csv_auto('{sample_url}', types={{'GEOID':'VARCHAR'}})").fetchone()[0]
print(f"scored tracts (sample submission): {n_scored}")

tiger_len = con.sql(f"""
    WITH troads AS (
        SELECT geometry AS geom, bbox FROM read_parquet('{tiger_url}') WHERE MTFCC IN ('S1100','S1200')
    ),
    tracts AS (
        SELECT GEOID, geometry AS geom, bbox FROM read_parquet('{tracts_url}')
    )
    SELECT t.GEOID,
           sum(ST_Length(ST_Transform(ST_Intersection(r.geom, t.geom), 'EPSG:4326', 'EPSG:5070', always_xy := true))) AS tiger_len_m
    FROM troads r
    JOIN tracts t
      ON r.bbox.xmin <= t.bbox.xmax AND r.bbox.xmax >= t.bbox.xmin
     AND r.bbox.ymin <= t.bbox.ymax AND r.bbox.ymax >= t.bbox.ymin
     AND ST_Intersects(r.geom, t.geom)
    GROUP BY t.GEOID
""").df()

scored = con.sql(f"SELECT GEOID FROM read_csv_auto('{sample_url}', types={{'GEOID':'VARCHAR'}})").df()
merged = scored.merge(tiger_len, on="GEOID", how="left")
merged["tiger_len_m"] = merged["tiger_len_m"].fillna(0)
n_undefined = int((merged["tiger_len_m"] <= 0).sum())
print(f"tracts with NO named-highway TIGER length (transport_defined=false): {n_undefined} of {len(merged)}")
print("README says: 218 of 591 for northern-ca")
print("MATCH" if n_undefined == 218 else "MISMATCH -- do not trust downstream numbers yet")
