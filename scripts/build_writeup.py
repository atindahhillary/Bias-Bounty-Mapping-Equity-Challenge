"""Regenerate docs/index.html without launching Streamlit -- used to seed/refresh the
GitHub Pages site from whatever is currently in data/tracts.csv (real if the pipeline has
run, synthetic demo data otherwise).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

STRATA_COLS = ["region", "ur_class", "svi_quartile", "tribal_any", "rucc_metro",
               "usdm_summer_dsci", "usfs_WHP_mean", "epht_heat_days_summer"]


def main():
    real_path = ROOT / "data" / "tracts.csv"
    if real_path.exists():
        df = pd.read_csv(real_path, dtype={"GEOID": str})
        is_mock = False
    else:
        from src.mock_data import generate as generate_mock
        df = generate_mock()
        is_mock = True

    group_col = "region" if "region" in df.columns else next(c for c in STRATA_COLS if c in df.columns)
    grp = df.groupby(group_col, dropna=False).agg(
        n_tracts=("GEOID", "count"),
        pct_missing_ge1=("parts_defined", lambda s: float((s < 3).mean() * 100)),
    ).reset_index()
    worst_group = grp.sort_values("pct_missing_ge1", ascending=False).iloc[0]

    driver = "roads"
    if all(c in df.columns for c in ["transport_defined", "building_defined", "poi_defined"]):
        rates = df[["transport_defined", "building_defined", "poi_defined"]].mean()
        driver = rates.idxmin().replace("_defined", "")

    parts = ["transport_gap", "building_gap", "poi_gap"]
    defined = ["transport_defined", "building_defined", "poi_defined"]
    if all(c in df.columns for c in parts + defined):
        hidden = df[parts].where(df[defined].values, other=1.0)
        df["score_hidden_gap"] = hidden.mean(axis=1)
    else:
        df["score_hidden_gap"] = df["coverage_gap_score"]
    df["delta"] = df["score_hidden_gap"] - df["coverage_gap_score"]
    movers_ranked = df.sort_values("delta", ascending=False).head(15)

    html_rows = "".join(
        f"<tr><td>{row['GEOID']}</td><td>{row.get('region','?')}</td><td>{row['parts_defined']}</td>"
        f"<td>{row['coverage_gap_score']:.3f}</td><td>{row['score_hidden_gap']:.3f}</td><td>{row['delta']:.3f}</td></tr>"
        for _, row in movers_ranked.iterrows()
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
.badge{{display:inline-block;background:#fff3cd;border:1px solid #ffe69c;color:#664d03;padding:4px 10px;border-radius:6px;font-size:13px;margin-bottom:16px}}
</style></head><body>
<h1>Bias Bounty: Mapping Equity Challenge</h1>
{'<p class="badge">Built from synthetic demo data -- real challenge data not yet computed</p>' if is_mock else ''}
<h2>The yardstick is missing where the risk is</h2>
<p>The scoring rule drops any coverage component (roads, buildings, places) with nothing in the
reference data to compare against. A tract then scores on one or two components instead of
three, and the hardest tracts to map can look fully covered.</p>
<p>Worst-affected group by <code>{group_col}</code>: <b>{worst_group[group_col]}</b> --
{worst_group['pct_missing_ge1']:.1f}% of tracts missing at least one component. Driven mostly by
<b>{driver}</b> coverage.</p>
<h2>Hidden-gap re-score: top movers</h2>
<table><tr><th>GEOID</th><th>Region</th><th>Parts defined</th><th>Coverage score</th><th>Hidden-gap score</th><th>Delta</th></tr>
{html_rows}</table>
<h2>Why it matters</h2>
<ul>
<li><b>Dispatch</b>: no fire/EMS station on record means routing has nothing to send responders from or to.</li>
<li><b>Evacuation</b>: no named highway means planning falls back to unnamed local roads neither dataset scores.</li>
<li><b>Relief</b>: FEMA/NGO metrics like this one can rank these communities as low-need when the real story is "unmeasured."</li>
</ul>
<p><i>Source: <a href="https://github.com/atindahhillary/Bias-Bounty-Mapping-Equity-Challenge">Bias-Bounty-Mapping-Equity-Challenge</a> repo, computed {'directly from the live challenge data at source.coop' if not is_mock else 'from synthetic demo data'}. Full interactive workbench runs locally via <code>streamlit run app.py</code>.</i></p>
</body></html>"""

    docs_dir = ROOT / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"Wrote {docs_dir / 'index.html'} (mock data: {is_mock})")


if __name__ == "__main__":
    main()
