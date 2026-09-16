"""Bias Bounty: Mapping Equity Challenge -- working system.

Run with:  streamlit run app.py

Three tabs:
  1. Formula Lab      -- reverse-engineer the scoring formula, solve the constant-submission
                          trick for mean/variance, track your 10/day submission budget, export CSV.
  2. Bias Discovery    -- "the yardstick is missing where the risk is": parts-defined counts,
                          strata breakdowns, hidden-gap re-score, ranked list of worst-affected tracts.
  3. Writeup           -- auto-drafted narrative pulling live numbers from tab 2, editable,
                          exportable as the submission writeup (also mirrored to docs/index.html).
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from src.scoring import per_tract_parts, rmse, constant_submission_solve, expected_rmse_for_constant
from src.mock_data import generate as generate_mock

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
EXPORTS_DIR = ROOT / "exports"
SUB_LOG = EXPORTS_DIR / "submission_log.csv"
CORE_COLS = {
    "GEOID", "roads_ref", "roads_overture", "buildings_ref", "buildings_overture",
    "fire_ref", "fire_overture", "ems_ref", "ems_overture", "schools_ref", "schools_overture",
    "establishments_ref", "establishments_overture",
}

st.set_page_config(page_title="Bias Bounty: Mapping Equity Challenge", layout="wide")


@st.cache_data
def load_mock():
    return generate_mock()


def load_data() -> tuple[pd.DataFrame, bool]:
    """Returns (df, is_mock). Prefers data/tracts.csv if present, else synthetic demo data."""
    real_path = DATA_DIR / "tracts.csv"
    if real_path.exists():
        df = pd.read_csv(real_path, dtype={"GEOID": str})
        return df, False
    return load_mock(), True


def strata_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in CORE_COLS]


st.title("Bias Bounty: Mapping Equity Challenge")
st.caption("Leaderboard formula copy + Best Bias Discovery workbench")

with st.sidebar:
    st.header("Data")
    uploaded = st.file_uploader("Upload real tracts.csv (GEOID as text)", type="csv")
    if uploaded is not None:
        df = pd.read_csv(uploaded, dtype={"GEOID": str})
        is_mock = False
        st.success(f"Loaded {len(df)} tracts from upload.")
    else:
        df = load_mock() if not (DATA_DIR / "tracts.csv").exists() else pd.read_csv(DATA_DIR / "tracts.csv", dtype={"GEOID": str})
        is_mock = not (DATA_DIR / "tracts.csv").exists()
        if is_mock:
            st.warning("Using synthetic demo data. Drop the real file at data/tracts.csv to switch over.")
        else:
            st.success(f"Loaded {len(df)} tracts from data/tracts.csv.")

    st.divider()
    st.header("Formula variant")
    clip_low = st.checkbox("Floor over-mapped gaps at 0", value=True, help="clip(1-Overture/ref, 0, ...) -- don't reward Overture having more than the reference.")
    clip_high = st.checkbox("Ceiling gaps at 1", value=True)

gap_cols = per_tract_parts(df, clip_low=clip_low, clip_high=clip_high)
full = pd.concat([df, gap_cols], axis=1)

tab_formula, tab_bias, tab_writeup = st.tabs(["Formula Lab", "Bias Discovery", "Writeup"])

# ---------------------------------------------------------------- Formula Lab
with tab_formula:
    st.subheader("Constant-submission solver")
    st.write(
        "Submit the same constant `c` for every tract twice (two different values), read the RMSE the "
        "leaderboard hands back, and solve for the hidden reference mean and variance: "
        "`RMSE^2 = variance + (mean - c)^2`. Costs 2 of your 10 daily submissions."
    )
    c1, r1_col, c2, r2_col = st.columns(4)
    with c1:
        const1 = st.number_input("c1", value=0.0, step=0.05, format="%.2f")
    with r1_col:
        rmse1 = st.number_input("RMSE returned for c1", value=0.30, step=0.001, format="%.4f")
    with c2:
        const2 = st.number_input("c2", value=1.0, step=0.05, format="%.2f")
    with r2_col:
        rmse2 = st.number_input("RMSE returned for c2", value=0.75, step=0.001, format="%.4f")

    if st.button("Solve for mean / variance"):
        try:
            mean_est, var_est = constant_submission_solve(const1, rmse1, const2, rmse2)
            st.success(f"Estimated reference mean = **{mean_est:.4f}**, variance = **{var_est:.4f}** (std = {np.sqrt(max(var_est,0)):.4f})")
            st.session_state["ref_mean"] = mean_est
            st.session_state["ref_var"] = var_est
        except ValueError as e:
            st.error(str(e))

    if "ref_mean" in st.session_state:
        st.write("Sanity check -- expected RMSE for any constant c, given the solved mean/variance:")
        check_c = st.slider("c", 0.0, 1.0, 0.5, 0.01)
        expected = expected_rmse_for_constant(check_c, st.session_state["ref_mean"], st.session_state["ref_var"])
        st.metric("Expected RMSE", f"{expected:.4f}")

    st.divider()
    st.subheader("Submission budget tracker (10/day)")
    EXPORTS_DIR.mkdir(exist_ok=True)
    if not SUB_LOG.exists():
        pd.DataFrame(columns=["date", "note", "public_rmse"]).to_csv(SUB_LOG, index=False)
    log = pd.read_csv(SUB_LOG)
    today = str(date.today())
    used_today = int((log["date"] == today).sum()) if not log.empty else 0
    st.metric("Submissions used today", f"{used_today} / 10")

    with st.form("log_submission"):
        note = st.text_input("What did you submit? (e.g. 'clip variant A, const=0.4')")
        obs_rmse = st.number_input("Public RMSE returned (optional)", value=0.0, step=0.0001, format="%.4f")
        submitted = st.form_submit_button("Log this submission")
        if submitted:
            new_row = pd.DataFrame([{"date": today, "note": note, "public_rmse": obs_rmse or None}])
            log = pd.concat([log, new_row], ignore_index=True)
            log.to_csv(SUB_LOG, index=False)
            st.success("Logged.")
            st.rerun()
    if not log.empty:
        st.dataframe(log.sort_values("date", ascending=False), use_container_width=True)

    st.divider()
    st.subheader("Export current formula's predictions")
    export_df = full[["GEOID", "roads_gap", "buildings_gap", "places_gap", "score_coverage"]].rename(
        columns={"score_coverage": "prediction"}
    )
    st.dataframe(export_df.head(20), use_container_width=True)
    st.download_button(
        "Download submission CSV",
        export_df[["GEOID", "prediction"]].to_csv(index=False).encode(),
        file_name="submission.csv",
        mime="text/csv",
    )

# ---------------------------------------------------------------- Bias Discovery
with tab_bias:
    st.subheader('"The yardstick is missing where the risk is"')
    if is_mock:
        st.info("Synthetic demo data -- swap in data/tracts.csv to see the real pattern.")

    strata = strata_columns(full)
    default_strata = [c for c in ["region", "tribal", "svi_quartile", "rural_urban", "wildfire_exposure", "heat_exposure"] if c in strata]
    group_col = st.selectbox("Break down by", strata, index=strata.index(default_strata[0]) if default_strata else 0)

    grp = full.groupby(group_col).agg(
        n_tracts=("GEOID", "count"),
        mean_parts_defined=("parts_defined", "mean"),
        pct_missing_ge1=("parts_defined", lambda s: float((s < 3).mean() * 100)),
        mean_score_coverage=("score_coverage", "mean"),
        mean_score_hidden_gap=("score_hidden_gap", "mean"),
    ).reset_index()
    grp["hidden_gap_delta"] = grp["mean_score_hidden_gap"] - grp["mean_score_coverage"]

    st.dataframe(grp.style.format({
        "mean_parts_defined": "{:.2f}", "pct_missing_ge1": "{:.1f}%",
        "mean_score_coverage": "{:.3f}", "mean_score_hidden_gap": "{:.3f}", "hidden_gap_delta": "{:.3f}",
    }), use_container_width=True)

    st.bar_chart(grp.set_index(group_col)["pct_missing_ge1"])
    st.caption("Share of tracts with at least one missing part, by group. Published regional figures: Maricopa 55%, Northern California 37%, South-Central Texas 28%, Eastern Oklahoma 21%.")

    st.divider()
    st.subheader("Hidden-gap re-score: biggest movers")
    st.write("Treats a missing part as a full gap of 1 instead of dropping it, then ranks tracts by how much their score would rise.")
    top_n = st.slider("How many tracts to list", 5, 30, 15)
    movers = full.copy()
    movers["delta"] = movers["score_hidden_gap"] - movers["score_coverage"]
    movers_ranked = movers.sort_values("delta", ascending=False).head(top_n)
    show_cols = ["GEOID", "region", "parts_defined", "score_coverage", "score_hidden_gap", "delta"] + [c for c in ["tribal", "svi_quartile", "rural_urban"] if c in movers.columns]
    st.dataframe(movers_ranked[show_cols].style.format({
        "score_coverage": "{:.3f}", "score_hidden_gap": "{:.3f}", "delta": "{:.3f}",
    }), use_container_width=True)
    st.session_state["top_movers"] = movers_ranked[show_cols]
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
        draft = f"""## The yardstick is missing where the risk is

The challenge's scoring rule drops any of the three coverage parts (roads, buildings, places)
when a tract has nothing in the reference data to compare against. A tract then gets scored on
one or two parts instead of three, and can post a near-perfect gap score purely because the
hardest-to-map features were never on record.

Breaking tracts down by **{group_col}**, the worst-affected group is **{worst_group[group_col]}**,
where {worst_group['pct_missing_ge1']:.1f}% of tracts are missing at least one part (published regional
baselines: Maricopa 55%, Northern California 37%, South-Central Texas 28%, Eastern Oklahoma 21%).

### Hidden-gap re-score
Re-scoring with a missing part treated as a full gap of 1 (instead of dropped) moves the following
tracts the most:

{chr(10).join(f"- Tract {row['GEOID']} ({row.get('region','?')}): {row['score_coverage']:.2f} -> {row['score_hidden_gap']:.2f} (parts defined: {row['parts_defined']})" for _, row in movers.head(15).iterrows())}

### Why it matters
- **Dispatch**: no fire/EMS station on record in either dataset means routing has nothing to send
  responders from or to.
- **Evacuation**: no named highway means evacuation planning falls back to unnamed local roads that
  neither dataset scores.
- **Relief**: FEMA/NGO coverage metrics like this one can rank these communities as low-need when the
  real story is "unmeasured," not "low-gap."
"""
        edited = st.text_area("Editable draft", draft, height=500)
        st.download_button("Download writeup.md", edited.encode(), file_name="writeup.md", mime="text/markdown")

        if st.button("Also write docs/index.html (for GitHub Pages)"):
            html_rows = "".join(
                f"<tr><td>{row['GEOID']}</td><td>{row.get('region','?')}</td><td>{row['parts_defined']}</td>"
                f"<td>{row['score_coverage']:.3f}</td><td>{row['score_hidden_gap']:.3f}</td><td>{row['delta']:.3f}</td></tr>"
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
<p>The scoring rule drops any coverage part (roads, buildings, places) with nothing in the reference
data to compare against. A tract then scores on one or two parts instead of three, and the hardest
tracts to map can look fully covered.</p>
<p>Worst-affected group by <code>{group_col}</code>: <b>{worst_group[group_col]}</b> --
{worst_group['pct_missing_ge1']:.1f}% of tracts missing at least one part.</p>
<h2>Hidden-gap re-score: top movers</h2>
<table><tr><th>GEOID</th><th>Region</th><th>Parts defined</th><th>Coverage score</th><th>Hidden-gap score</th><th>Delta</th></tr>
{html_rows}</table>
<h2>Why it matters</h2>
<ul>
<li><b>Dispatch</b>: no fire/EMS station on record means routing has nothing to send responders from or to.</li>
<li><b>Evacuation</b>: no named highway means planning falls back to unnamed local roads neither dataset scores.</li>
<li><b>Relief</b>: FEMA/NGO metrics like this one can rank these communities as low-need when the real story is "unmeasured."</li>
</ul>
<p><i>Generated from {'synthetic demo data -- replace with real challenge data for the actual submission' if is_mock else 'real challenge data'}.</i></p>
</body></html>"""
            docs_dir = ROOT / "docs"
            docs_dir.mkdir(exist_ok=True)
            (docs_dir / "index.html").write_text(html, encoding="utf-8")
            st.success("Wrote docs/index.html -- push and enable GitHub Pages on /docs to make it live.")
