"""Computes the real coverage-gap score per tract, straight from the challenge's public
Source Cooperative bucket, following the exact method documented in the bucket's own README:

  transport_gap = 1 - min(1, overture_named_highway_length_m / tiger_named_highway_length_m)
  building_gap  = 1 - min(1, overture_building_count / microsoft_building_count)
  poi_gap       = mean(poi_gap_hifld, poi_gap_cbp), each side used only if defined
    poi_gap_hifld = mean of defined per-type gaps among fire/EMS/schools
      each = 1 - min(1, overture_count_of_type / hifld_count_of_type)
    poi_gap_cbp   = 1 - min(1, overture_places_total / cbp_estab_bus)
  coverage_gap_score = mean of {transport_gap, building_gap, poi_gap} that are defined

A component is "defined" only when the tract has a nonzero reference count/length to compare
against (no reference of that kind -> excluded from the mean, not scored as 0).

No credentials needed -- the bucket is public and reachable over plain HTTPS with range-request
support, so DuckDB's httpfs+spatial extensions can query it directly without downloading anything.
"""
from __future__ import annotations
import duckdb
import pandas as pd

BASE = "https://data.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"

REGIONS = ["maricopa-az", "northern-ca", "eastern-ok", "south-central-tx"]

HIFLD_SCHOOL_CATEGORIES = (
    "'elementary_school','middle_school','high_school','school','private_school','public_school'"
)

BBOX_JOIN = (
    "a.bbox.xmin <= b.bbox.xmax AND a.bbox.xmax >= b.bbox.xmin "
    "AND a.bbox.ymin <= b.bbox.ymax AND a.bbox.ymax >= b.bbox.ymin"
)


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
    return con


def _urls(region: str) -> dict:
    ref = f"{BASE}/reference/{region}"
    strata = f"{BASE}/strata/{region}"
    return dict(
        tracts=f"{strata}/{region}-census-tracts.parquet",
        sample=f"{ref}/{region}-sample-submission.csv",
        tiger_roads=f"{ref}/{region}-census-tiger-roads.parquet",
        ov_roads=f"{ref}/{region}-overture-roads.parquet",
        ov_buildings=f"{ref}/{region}-overture-buildings.parquet",
        ms_buildings=f"{ref}/{region}-microsoft-buildings.parquet",
        ov_pois=f"{ref}/{region}-overture-pois.parquet",
        hifld_fire=f"{ref}/{region}-hifld-fire-stations.parquet",
        hifld_ems=f"{ref}/{region}-hifld-ems-stations.parquet",
        hifld_schools=f"{ref}/{region}-hifld-schools.parquet",
        cbp=f"{ref}/{region}-census-cbp.parquet",
        strata_table=f"{strata}/{region}-strata-tract-table.parquet",
    )


def _length_by_tract(con, roads_url: str, tracts_url: str, class_filter: str) -> pd.DataFrame:
    return con.sql(f"""
        WITH roads AS (
            SELECT geometry AS geom, bbox FROM read_parquet('{roads_url}') WHERE {class_filter}
        ),
        tracts AS (
            SELECT GEOID, geometry AS geom, bbox FROM read_parquet('{tracts_url}')
        )
        SELECT t.GEOID,
               sum(ST_Length(ST_Transform(ST_Intersection(a.geom, t.geom), 'EPSG:4326', 'EPSG:5070', always_xy := true))) AS len_m
        FROM roads a
        JOIN tracts t ON {BBOX_JOIN.replace('a.', 'a.').replace('b.', 't.')} AND ST_Intersects(a.geom, t.geom)
        GROUP BY t.GEOID
    """).df()


def _count_by_tract_pip(con, points_url: str, tracts_url: str, where: str = "TRUE", centroid: bool = False) -> pd.DataFrame:
    """Count point (or polygon-centroid) features per tract via point-in-polygon."""
    geom_expr = "ST_Centroid(a.geom)" if centroid else "a.geom"
    return con.sql(f"""
        WITH pts AS (
            SELECT geometry AS geom, bbox FROM read_parquet('{points_url}') WHERE {where}
        ),
        tracts AS (
            SELECT GEOID, geometry AS geom, bbox FROM read_parquet('{tracts_url}')
        )
        SELECT t.GEOID, count(*) AS n
        FROM pts a
        JOIN tracts t ON {BBOX_JOIN.replace('a.', 'a.').replace('b.', 't.')} AND ST_Contains(t.geom, {geom_expr})
        GROUP BY t.GEOID
    """).df()


def compute_region(region: str, con: duckdb.DuckDBPyConnection | None = None) -> pd.DataFrame:
    con = con or _connect()
    u = _urls(region)

    scored = con.sql(f"SELECT GEOID FROM read_csv_auto('{u['sample']}', types={{'GEOID':'VARCHAR'}})").df()

    tiger_len = _length_by_tract(con, u["tiger_roads"], u["tracts"], "MTFCC IN ('S1100','S1200')")
    ov_len = _length_by_tract(con, u["ov_roads"], u["tracts"], "class IN ('motorway','trunk','primary','secondary')")

    ov_bldg = _count_by_tract_pip(con, u["ov_buildings"], u["tracts"], centroid=True)
    ms_bldg = _count_by_tract_pip(con, u["ms_buildings"], u["tracts"], centroid=True)

    ov_all_pois = _count_by_tract_pip(con, u["ov_pois"], u["tracts"])
    ov_fire = _count_by_tract_pip(con, u["ov_pois"], u["tracts"], where="categories.primary = 'fire_department'")
    ov_ems = _count_by_tract_pip(con, u["ov_pois"], u["tracts"], where="categories.primary = 'ambulance_and_ems_services'")
    ov_schools = _count_by_tract_pip(con, u["ov_pois"], u["tracts"], where=f"categories.primary IN ({HIFLD_SCHOOL_CATEGORIES})")

    hifld_fire = _count_by_tract_pip(con, u["hifld_fire"], u["tracts"])
    hifld_ems = _count_by_tract_pip(con, u["hifld_ems"], u["tracts"])
    hifld_schools = _count_by_tract_pip(con, u["hifld_schools"], u["tracts"])

    cbp = con.sql(f"SELECT GEOID, cbp_estab_bus FROM read_parquet('{u['cbp']}')").df()

    def merge(df, name):
        return scored.merge(df.rename(columns={df.columns[-1]: name}), on="GEOID", how="left")[name].fillna(0)

    out = scored.copy()
    out["tiger_len_m"] = merge(tiger_len, "tiger_len_m")
    out["overture_road_len_m"] = merge(ov_len, "overture_road_len_m")
    out["ms_buildings"] = merge(ms_bldg, "ms_buildings")
    out["overture_buildings"] = merge(ov_bldg, "overture_buildings")
    out["hifld_fire"] = merge(hifld_fire, "hifld_fire")
    out["hifld_ems"] = merge(hifld_ems, "hifld_ems")
    out["hifld_schools"] = merge(hifld_schools, "hifld_schools")
    out["overture_fire"] = merge(ov_fire, "overture_fire")
    out["overture_ems"] = merge(ov_ems, "overture_ems")
    out["overture_schools"] = merge(ov_schools, "overture_schools")
    out["overture_places_total"] = merge(ov_all_pois, "overture_places_total")
    out = out.merge(cbp, on="GEOID", how="left")
    out["cbp_estab_bus"] = out["cbp_estab_bus"].fillna(0)

    def gap(overture, ref):
        return 1 - (overture / ref).clip(upper=1)

    out["transport_defined"] = out["tiger_len_m"] > 0
    out["transport_gap"] = gap(out["overture_road_len_m"], out["tiger_len_m"].replace(0, pd.NA)).fillna(0)

    out["building_defined"] = out["ms_buildings"] > 0
    out["building_gap"] = gap(out["overture_buildings"], out["ms_buildings"].replace(0, pd.NA)).fillna(0)

    out["poi_defined_fire"] = out["hifld_fire"] > 0
    out["poi_gap_fire"] = gap(out["overture_fire"], out["hifld_fire"].replace(0, pd.NA)).fillna(0)
    out["poi_defined_ems"] = out["hifld_ems"] > 0
    out["poi_gap_ems"] = gap(out["overture_ems"], out["hifld_ems"].replace(0, pd.NA)).fillna(0)
    out["poi_defined_schools"] = out["hifld_schools"] > 0
    out["poi_gap_schools"] = gap(out["overture_schools"], out["hifld_schools"].replace(0, pd.NA)).fillna(0)

    hifld_parts = out[["poi_gap_fire", "poi_gap_ems", "poi_gap_schools"]].where(
        out[["poi_defined_fire", "poi_defined_ems", "poi_defined_schools"]].values
    )
    out["poi_defined_hifld"] = out[["poi_defined_fire", "poi_defined_ems", "poi_defined_schools"]].any(axis=1)
    out["poi_gap_hifld"] = hifld_parts.mean(axis=1, skipna=True).fillna(0)

    out["poi_defined_cbp"] = out["cbp_estab_bus"] > 0
    out["poi_gap_cbp"] = gap(out["overture_places_total"], out["cbp_estab_bus"].replace(0, pd.NA)).fillna(0)

    poi_parts = out[["poi_gap_hifld", "poi_gap_cbp"]].where(out[["poi_defined_hifld", "poi_defined_cbp"]].values)
    out["poi_defined"] = out["poi_defined_hifld"] | out["poi_defined_cbp"]
    out["poi_gap"] = poi_parts.mean(axis=1, skipna=True).fillna(0)

    parts = out[["transport_gap", "building_gap", "poi_gap"]].where(
        out[["transport_defined", "building_defined", "poi_defined"]].values
    )
    out["parts_defined"] = out[["transport_defined", "building_defined", "poi_defined"]].sum(axis=1)
    out["coverage_gap_score"] = parts.mean(axis=1, skipna=True)
    out["region"] = region
    return out


STRATA_COLUMNS = [
    "GEOID", "pop_total", "ur_class", "pct_urban", "svi_overall", "tribal_any",
    "rucc_metro", "usdm_summer_dsci", "usfs_WHP_mean", "epht_heat_days_summer",
]


def fetch_strata(region: str, con: duckdb.DuckDBPyConnection | None = None) -> pd.DataFrame:
    """Slim strata subset for bias-discovery breakdowns: urban/rural, SVI, tribal, drought,
    wildfire hazard potential, heat days. Column-pruned so it stays a few MB, not the full
    232-column table.
    """
    con = con or _connect()
    url = f"{BASE}/strata/{region}/{region}-strata-tract-table.parquet"
    cols = ", ".join(STRATA_COLUMNS)
    df = con.sql(f"SELECT {cols} FROM read_parquet('{url}')").df()
    df["svi_quartile"] = pd.qcut(df["svi_overall"], 4, labels=[1, 2, 3, 4], duplicates="drop")
    return df


if __name__ == "__main__":
    import sys
    region = sys.argv[1] if len(sys.argv) > 1 else "northern-ca"
    df = compute_region(region)
    print(df.describe())
    print(df.head(10))
