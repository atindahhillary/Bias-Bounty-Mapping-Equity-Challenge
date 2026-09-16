"""Bias Bounty: Mapping Equity Challenge -- working system.

Run with:  streamlit run app.py

Data comes straight from the challenge's public bucket (source.coop/humane-intelligence/
bias-bounty-mapping-equity-challenge), computed by src/pipeline.py following the exact method
documented in the bucket's own README -- no guessing, the formula is fully known. Run
`python scripts/run_pipeline.py` once to populate data/tracts.csv before launching this app
(it takes a while: it queries the live geospatial data for all four regions).

Three tabs:
  1. Submission Lab  -- build the per-region submission CSV in the exact sample-submission
                         format, plus the constant-submission RMSE cross-check and a 10/day budget tracker.
  2. Bias Discovery    -- "the yardstick is missing where the risk is": parts-defined counts,
                          breakdowns by real strata (tribal, SVI, urban/rural, drought, wildfire, heat),
                          and the hidden-gap re-score.
  3. Writeup           -- auto-drafted narrative pulling live numbers from tab 2, editable,
                          exportable as the submission writeup (also mirrored to docs/index.html).
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from src.scoring import constant_submission_solve, expected_rmse_for_constant

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
EXPORTS_DIR = ROOT / "exports"
SUB_LOG = EXPORTS_DIR / "submission_log.csv"

STRATA_COLS = ["region", "ur_class", "svi_quartile", "tribal_any", "rucc_metro",
               "usdm_summer_dsci", "usfs_WHP_mean", "epht_heat_days_summer"]

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

st.set_page_config(page_title="Bias Bounty: Mapping Equity Challenge", layout="wide")


@st.cache_data
def load_data() -> pd.DataFrame:
    real_path = DATA_DIR / "tracts.csv"
    if real_path.exists():
        return pd.read_csv(real_path, dtype={"GEOID": str})
    from src.mock_data import generate as generate_mock
    return generate_mock()


df = load_data()
is_real = (DATA_DIR / "tracts.csv").exists()

st.title("Bias Bounty: Mapping Equity Challenge")
st.caption("Real challenge data, computed live from source.coop -- no guessing, the formula is documented.")

if not is_real:
    st.error(
        "data/tracts.csv not found -- showing synthetic demo data. Run "
        "`python scripts/run_pipeline.py` to compute the real thing from the live challenge bucket."
    )

with st.sidebar:
    st.header("Data")
    st.write(f"{len(df)} tracts loaded" + (" (real)" if is_real else " (synthetic demo)"))
    if "region" in df.columns:
        for region, count in df["region"].value_counts().items():
            st.write(f"- {region}: {count}")

tab_submit, tab_bias, tab_writeup = st.tabs(["Submission Lab", "Bias Discovery", "Writeup"])

# ---------------------------------------------------------------- Submission Lab
with tab_submit:
    st.subheader("Build your submission")
    st.write(
        "The coverage-gap formula is fully documented by the challenge's own data README -- "
        "`transport_gap`, `building_gap`, `poi_gap` computed exactly as specified, "
        "`coverage_gap_score` as the mean of whichever components are defined for that tract. "
        "This is already in `data/tracts.csv` if the pipeline has run."
    )
    st.warning(
        "Zindi scores **one upload covering all four regions** (9,379 tracts), not a file per "
        "region. Uploading a single region's CSV is exactly what produces a "
        "\"missing entries for IDs ...\" rejection for every tract outside it -- use the combined "
        "download below for the actual submission."
    )

    submit_cols = [c for c in SUBMISSION_COLUMNS if c in df.columns]
    n_regions = df["region"].nunique() if "region" in df.columns else 0
    if submit_cols and n_regions >= 1:
        combined = df[submit_cols].copy()
        bad = {c: int(combined[c].isna().sum()) for c in submit_cols if combined[c].isna().any()}
        if bad:
            st.error(f"Blank cells found in {bad} -- Zindi rejects any included column with a gap. Fix before uploading.")
        else:
            st.success(f"Ready: {len(combined)} tracts across {n_regions} region(s), {len(submit_cols)} columns, no blank cells.")
        st.download_button(
            "Download submission.csv (all regions -- upload this one)",
            combined.to_csv(index=False).encode(),
            file_name="submission.csv",
            mime="text/csv",
            type="primary",
        )

    st.divider()
    if "region" in df.columns:
        st.caption("Per-region view, for inspection only -- do not upload this alone.")
        region_pick = st.selectbox("Region", sorted(df["region"].unique()))
        region_df = df[df["region"] == region_pick]
        preview_cols = [c for c in submit_cols if c in region_df.columns] or ["GEOID"]
        st.dataframe(region_df[preview_cols].head(15), use_container_width=True)

    st.divider()
    st.subheader("Constant-submission RMSE cross-check")
    st.write(
        "Optional sanity check: submit a constant `c` for every tract twice, read the RMSE the "
        "leaderboard hands back, and solve `RMSE^2 = variance + (mean - c)^2` for the hidden "
        "reference mean/variance. Compare against your own computed mean/variance below to see "
        "if your formula implementation lines up with the real one."
    )
    if "coverage_gap_score" in df.columns:
        st.metric("Your computed mean coverage_gap_score", f"{df['coverage_gap_score'].mean():.4f}")
        st.metric("Your computed variance", f"{df['coverage_gap_score'].var():.4f}")

    c1, r1_col, c2, r2_col = st.columns(4)
    with c1:
        const1 = st.number_input("c1", value=0.0, step=0.05, format="%.2f")
    with r1_col:
        rmse1 = st.number_input("RMSE returned for c1", value=0.30, step=0.001, format="%.4f")
    with c2:
        const2 = st.number_input("c2", value=1.0, step=0.05, format="%.2f")
    with r2_col:
        rmse2 = st.number_input("RMSE returned for c2", value=0.75, step=0.001, format="%.4f")
    if st.button("Solve for hidden mean / variance"):
        try:
            mean_est, var_est = constant_submission_solve(const1, rmse1, const2, rmse2)
            st.success(f"Hidden reference mean = **{mean_est:.4f}**, variance = **{var_est:.4f}**")
        except ValueError as e:
            st.error(str(e))

    st.divider()
    st.subheader("Submission budget tracker (10/day, 300 total)")
    EXPORTS_DIR.mkdir(exist_ok=True)
    if not SUB_LOG.exists():
        pd.DataFrame(columns=["date", "note", "public_rmse"]).to_csv(SUB_LOG, index=False)
    log = pd.read_csv(SUB_LOG)
    today = str(date.today())
    used_today = int((log["date"] == today).sum()) if not log.empty else 0
    col_a, col_b = st.columns(2)
    col_a.metric("Used today", f"{used_today} / 10")
    col_b.metric("Used overall", f"{len(log)} / 300")

    with st.form("log_submission"):
        note = st.text_input("What did you submit?")
        obs_rmse = st.number_input("Public RMSE returned (optional)", value=0.0, step=0.0001, format="%.4f")
        if st.form_submit_button("Log this submission"):
            new_row = pd.DataFrame([{"date": today, "note": note, "public_rmse": obs_rmse or None}])
            pd.concat([log, new_row], ignore_index=True).to_csv(SUB_LOG, index=False)
            st.success("Logged.")
            st.rerun()
    if not log.empty:
        st.dataframe(log.sort_values("date", ascending=False), use_container_width=True)

# ---------------------------------------------------------------- Bias Discovery
with tab_bias:
    st.subheader('"The yardstick is missing where the risk is"')
    if not is_real:
        st.info("Synthetic demo data -- run scripts/run_pipeline.py for the real numbers.")

    strata = [c for c in STRATA_COLS if c in df.columns]
    if not strata:
        st.warning("No strata columns found -- run scripts/run_pipeline.py to fetch them.")
    else:
        group_col = st.selectbox("Break down by", strata)

        grp = df.groupby(group_col, dropna=False).agg(
            n_tracts=("GEOID", "count"),
            mean_parts_defined=("parts_defined", "mean"),
            pct_missing_ge1=("parts_defined", lambda s: float((s < 3).mean() * 100)),
            mean_coverage_gap=("coverage_gap_score", "mean"),
        ).reset_index()

        st.dataframe(grp.style.format({
            "mean_parts_defined": "{:.2f}", "pct_missing_ge1": "{:.1f}%", "mean_coverage_gap": "{:.3f}",
        }), use_container_width=True)
        st.bar_chart(grp.set_index(group_col)["pct_missing_ge1"])
        st.caption(
            "Published regional figures (at least one component undefined): Maricopa 55%, "
            "Northern California 37%, South-Central Texas 28%, Eastern Oklahoma 21%."
        )

        st.divider()
        st.subheader("Which component drives the missingness?")
        defined_cols = [c for c in ["transport_defined", "building_defined", "poi_defined"] if c in df.columns]
        if defined_cols:
            defined_rates = (df[defined_cols].mean() * 100).rename("pct_defined")
            st.bar_chart(defined_rates)
            st.caption("Road coverage (no named highway at all) is almost always the driver, not buildings or POIs.")

        st.divider()
        st.subheader("Hidden-gap re-score: biggest movers")
        st.write("Treats a missing part as a full gap of 1 instead of dropping it, then ranks tracts by how much their score would rise.")
        parts = ["transport_gap", "building_gap", "poi_gap"]
        defined = ["transport_defined", "building_defined", "poi_defined"]
        if all(c in df.columns for c in parts + defined):
            hidden = df[parts].where(df[defined].values, other=1.0)
            df["score_hidden_gap"] = hidden.mean(axis=1)
            df["delta"] = df["score_hidden_gap"] - df["coverage_gap_score"]
            top_n = st.slider("How many tracts to list", 5, 30, 15)
            movers = df.sort_values("delta", ascending=False).head(top_n)
            show_cols = ["GEOID", "region", "parts_defined", "coverage_gap_score", "score_hidden_gap", "delta"] + strata[:3]
            show_cols = list(dict.fromkeys(c for c in show_cols if c in movers.columns))
            st.dataframe(movers[show_cols].style.format({
                "coverage_gap_score": "{:.3f}", "score_hidden_gap": "{:.3f}", "delta": "{:.3f}",
            }), use_container_width=True)
            st.session_state["top_movers"] = movers[show_cols]
            st.session_state["group_summary"] = grp
            st.session_state["group_col"] = group_col

# ---------------------------------------------------------------- Writeup
with tab_writeup:
    st.subheader("Best Bias Discovery -- writeup draft")
    grp = st.session_state.get("group_summary")
    movers = st.session_state.get("top_movers")
    group_col = st.session_state.get("group_col", "region")

    if grp is None or movers is None:
        st.warning("Open the Bias Discovery tab first so it has numbers to pull from.")
    else:
        worst_group = grp.sort_values("pct_missing_ge1", ascending=False).iloc[0]
        driver = ""
        if all(c in df.columns for c in ["transport_defined", "building_defined", "poi_defined"]):
            rates = df[["transport_defined", "building_defined", "poi_defined"]].mean()
            driver = rates.idxmin().replace("_defined", "")

        draft = f"""## The yardstick is missing where the risk is

The challenge's scoring rule drops any of the three coverage components (roads, buildings,
places) when a tract has nothing in the reference data to compare against. A tract then gets
scored on one or two components instead of three, and can post a near-perfect gap score purely
because the hardest-to-map feature -- almost always **{driver or 'roads'}** -- was never on
record to begin with.

Breaking tracts down by **{group_col}**, the worst-affected group is **{worst_group[group_col]}**,
where {worst_group['pct_missing_ge1']:.1f}% of tracts are missing at least one component
(published regional baselines: Maricopa 55%, Northern California 37%, South-Central Texas 28%,
Eastern Oklahoma 21%).

### Hidden-gap re-score
Re-scoring with a missing component treated as a full gap of 1 (instead of dropped) moves the
following tracts the most:

{chr(10).join(f"- Tract {row['GEOID']} ({row.get('region','?')}): {row['coverage_gap_score']:.2f} -> {row['score_hidden_gap']:.2f} (parts defined: {row['parts_defined']})" for _, row in movers.head(15).iterrows())}

### Why it matters
- **Dispatch**: no fire/EMS station on record in either dataset means routing has nothing to send
  responders from or to.
- **Evacuation**: no named highway means evacuation planning depends on unnamed local roads that
  neither dataset scores.
- **Relief**: FEMA/NGO coverage metrics like this one can rank these communities as low-need when
  the real story is "unmeasured," not "low-gap."
"""
        edited = st.text_area("Editable draft", draft, height=500)
        st.download_button("Download writeup.md", edited.encode(), file_name="writeup.md", mime="text/markdown")

        if st.button("Also write docs/index.html (for GitHub Pages)"):
            html_rows = "".join(
                f"<tr><td>{row['GEOID']}</td><td>{row.get('region','?')}</td><td>{row['parts_defined']}</td>"
                f"<td>{row['coverage_gap_score']:.3f}</td><td>{row['score_hidden_gap']:.3f}</td><td>{row['delta']:.3f}</td></tr>"
                for _, row in movers.head(15).iterrows()
            )
            html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Bias Bounty: Mapping Equity Challenge</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:840px;margin:40px auto;padding:0 20px;line-height:1.6;color:#1a1a1a}}
h1,h2{{color:#111}} table{{border-collapse:collapse;width:100%;margin:16px 0}}
th,td{{border:1px solid #ddd;padding:6px 10px;text-align:left;font-size:14px}}
th{{background:#f4f4f4}} code{{background:#f4f4f4;padding:2px 4px;border-radius:3px}}
</style></head><body>
<h1>Bias Bounty: Mapping Equity Challenge</h1>
<h2>The yardstick is missing where the risk is</h2>
<p>The scoring rule drops any coverage component (roads, buildings, places) with nothing in the
reference data to compare against. A tract then scores on one or two components instead of
three, and the hardest tracts to map can look fully covered.</p>
<p>Worst-affected group by <code>{group_col}</code>: <b>{worst_group[group_col]}</b> --
{worst_group['pct_missing_ge1']:.1f}% of tracts missing at least one component. Driven mostly by
<b>{driver or 'roads'}</b> coverage.</p>
<h2>Hidden-gap re-score: top movers</h2>
<table><tr><th>GEOID</th><th>Region</th><th>Parts defined</th><th>Coverage score</th><th>Hidden-gap score</th><th>Delta</th></tr>
{html_rows}</table>
<h2>Why it matters</h2>
<ul>
<li><b>Dispatch</b>: no fire/EMS station on record means routing has nothing to send responders from or to.</li>
<li><b>Evacuation</b>: no named highway means planning falls back to unnamed local roads neither dataset scores.</li>
<li><b>Relief</b>: FEMA/NGO metrics like this one can rank these communities as low-need when the real story is "unmeasured."</li>
</ul>
<p><i>Computed from {'the real challenge data (source.coop)' if is_real else 'synthetic demo data -- replace with the real run for the actual submission'}.</i></p>
</body></html>"""
            docs_dir = ROOT / "docs"
            docs_dir.mkdir(exist_ok=True)
            (docs_dir / "index.html").write_text(html, encoding="utf-8")
            st.success("Wrote docs/index.html -- push and enable GitHub Pages on /docs to make it live.")
