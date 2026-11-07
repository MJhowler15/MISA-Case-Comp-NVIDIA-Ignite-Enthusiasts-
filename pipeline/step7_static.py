"""
step7_static.py - static HTML backup of the proof-of-concept (demo fallback if the live app fails).
Builds outputs/poc_static.html from pipeline outputs only: per scenario the summary, three heatmaps
(recommended heads, change vs draft, P(meet) after callouts), the cost/service frontier, the flagged blocks
and a 'why' table for every open block. Inline CSS, no external assets, no scripts.
"""
from __future__ import annotations
import os, sys, json, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from viz import heatmap, fig_to_base64, frontier_chart, DAY_LABEL

CSS = """
body { background:#f4f3ef; color:#1a1a1a; font-family: Helvetica, Arial, sans-serif; font-size:14px; margin:0; padding:24px 32px; }
h1 { font-size:22px; font-weight:600; margin:0 0 4px 0; }
h2 { font-size:17px; font-weight:600; margin:28px 0 8px 0; border-bottom:1px solid #55554f; padding-bottom:4px; }
h3 { font-size:14px; font-weight:600; margin:18px 0 6px 0; }
p, li { max-width: 1100px; line-height:1.45; }
table { border-collapse: collapse; margin: 6px 0 14px 0; }
th, td { border:1px solid #b9b6ad; padding:3px 8px; font-size:12.5px; text-align:right; }
th { background:#e3e0d6; font-weight:600; text-align:center; }
td:first-child, th:first-child { text-align:left; }
img { display:block; max-width:100%; border:1px solid #b9b6ad; margin:6px 0 14px 0; }
.note { color:#444; font-size:12.5px; }
.flag { background:#e9d9d3; }
nav a { margin-right:14px; color:#1f4e79; }
"""


def tbl(df: pd.DataFrame, fmt: dict | None = None, flag_col: str | None = None, flag_thr: float = 0.9) -> str:
    fmt = fmt or {}
    h = ["<table><tr>" + "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns) + "</tr>"]
    for _, r in df.iterrows():
        cls = ' class="flag"' if flag_col and pd.notna(r[flag_col]) and r[flag_col] < flag_thr else ""
        cells = []
        for c in df.columns:
            v = r[c]
            if c in fmt and pd.notna(v):
                v = fmt[c].format(v)
            elif isinstance(v, float):
                v = "" if pd.isna(v) else f"{v:,.2f}"
            cells.append(f"<td>{html.escape(str(v))}</td>")
        h.append(f"<tr{cls}>" + "".join(cells) + "</tr>")
    h.append("</table>")
    return "\n".join(h)


def run(data_dir: str, out_dir: str) -> str:
    rec = pd.read_csv(os.path.join(out_dir, "04_plan_recommended.csv"), parse_dates=["day_date"])
    pvd = pd.read_csv(os.path.join(out_dir, "05_plan_vs_draft.csv"))
    capb = pd.read_csv(os.path.join(out_dir, "04_capacity_bound.csv"))
    pb = pd.read_csv(os.path.join(out_dir, "06_playbook_blocks.csv"))
    draft_blocks = pd.read_csv(os.path.join(out_dir, "05_plan_vs_draft_blocks.csv"), parse_dates=["day_date"])
    th = pd.read_csv(os.path.join(out_dir, "01_service_thresholds.csv"))
    meta = json.load(open(os.path.join(out_dir, "03_forecast_meta.json")))

    parts = [f"<html><head><meta charset='utf-8'><title>Warehouse staffing planner, static backup</title><style>{CSS}</style></head><body>"]
    parts.append("<h1>Warehouse staffing planner, week of Feb 12-18, 2026 (static backup)</h1>")
    parts.append("<p class='note'>Every number and chart on this page is pipeline output (run_all.py). The live tool (app.py) recomputes the same plan when settings change; "
                 "this page shows the recommended plan: 90% service-confidence target, evaluated on heads after expected callouts.</p>")
    parts.append("<nav>" + "".join(f"<a href='#{s}'>{s}</a>" for s in ("BASE", "PEAK", "DISRUPT")) + "<a href='#method'>Method</a></nav>")

    for scn in ("BASE", "PEAK", "DISRUPT"):
        ev = rec[rec.scenario_code == scn].copy()
        dr = draft_blocks[(draft_blocks.scenario_code == scn) & (draft_blocks.plan == "draft")][["store_id", "dept_id", "day_date", "shift_code", "cost", "p_meet_post_callout", "p_meet_submitted", "infeasible_strict"]]
        dr = dr.rename(columns={"cost": "draft_cost", "p_meet_post_callout": "draft_p_post", "p_meet_submitted": "draft_p_sub", "infeasible_strict": "draft_infeasible"})
        ev = ev.merge(dr, on=["store_id", "dept_id", "day_date", "shift_code"], how="left")
        ev["delta_vs_draft"] = ev.heads - ev.draft_heads
        parts.append(f"<h2 id='{scn}'>{scn}</h2>")
        s = pvd[pvd.scenario == scn][["plan", "heads", "cost", "cost_ot", "ot_heads", "flex_heads", "exp_missed_submitted", "exp_missed_post", "avg_p_post", "blocks_below_90_post", "infeasible_strict", "cost_vs_draft_pct"]].copy()
        s["cost_vs_draft_pct"] = s.cost_vs_draft_pct * 100
        parts.append("<h3>Plans compared (planning week, 180 open blocks)</h3>")
        parts.append(tbl(s, fmt={"cost": "${:,.0f}", "cost_ot": "${:,.0f}", "exp_missed_submitted": "{:.1f}", "exp_missed_post": "{:.1f}", "avg_p_post": "{:.3f}", "cost_vs_draft_pct": "{:+.1f}%"}))
        parts.append(f"<img src='data:image/png;base64,{fig_to_base64(frontier_chart(pvd, scn))}' alt='frontier'>")
        for col, kind, fmt, title in [("heads", "seq", "{:.0f}", "Recommended heads"), ("delta_vs_draft", "div", "{:+.0f}", "Change vs draft schedule"),
                                      ("p_meet_post_callout", "risk", "{:.2f}", "P(meet target) after expected callouts"), ("utilization", "seq", "{:.2f}", "Utilization at the forecast")]:
            fig = heatmap(ev, col, f"{scn}: {title}", kind=kind, fmt=fmt)
            fig.savefig(os.path.join(out_dir, f"07_heatmap_{scn}_{col}.png"), dpi=130, bbox_inches="tight")   # slide images
            parts.append(f"<img src='data:image/png;base64,{fig_to_base64(fig)}' alt='{title}'>")
        cb = capb[(capb.setting == "rec_post90") & (capb.scenario == scn)]
        parts.append(f"<h3>Blocks that cannot reach 90% within capacity ({len(cb)})</h3>")
        if len(cb):
            parts.append(tbl(cb[["store_id", "dept", "day_date", "shift_code", "heads", "capacity_loose", "reg", "flex", "ot", "utilization", "p_meet_submitted", "p_meet_post_callout", "draft_heads", "forecast_demand"]],
                             fmt={"utilization": "{:.3f}", "p_meet_submitted": "{:.2f}", "p_meet_post_callout": "{:.2f}", "forecast_demand": "{:.1f}"}))
        parts.append("<h3>Every open block: forecast, heads, fill, cost, P(meet)</h3>")
        o = ev[ev.is_open == 1].copy()
        o["day"] = o.day_date.dt.strftime("%Y-%m-%d").map(DAY_LABEL)
        cols = ["store_id", "dept", "day", "shift_code", "forecast_demand", "required_hours_100", "min_staff", "capacity_loose", "draft_heads", "heads", "reg", "flex", "ot", "utilization", "p_meet_submitted", "p_meet_post_callout", "draft_p_post", "cost", "draft_cost"]
        parts.append(tbl(o.sort_values(["store_id", "day_date", "shift_seq", "dept_id"])[cols],
                         fmt={"forecast_demand": "{:.1f}", "required_hours_100": "{:.1f}", "utilization": "{:.3f}", "p_meet_submitted": "{:.2f}", "p_meet_post_callout": "{:.2f}", "draft_p_post": "{:.2f}", "cost": "${:,.0f}", "draft_cost": "${:,.0f}"},
                         flag_col="p_meet_post_callout", flag_thr=0.9))

    parts.append("<h2 id='method'>Method in one paragraph</h2>")
    parts.append("<p>Demand: level x weekday profile x holiday factor, estimated on six weeks of history with Presidents' Day mapped to the MLK window, Valentine's as a stated assumption; "
                 f"weekly level noise {100*meta['trend']['sd_week_dev_all']:.1f}%. Service: wait = b / (1 - u/c) per department with a warehouse factor, fitted by leave-one-week-out CV; "
                 "P(meet) drops below 90% between u = 0.84 and 0.88. Callouts: binomial at historical rates, half backfilled while overtime room remains. "
                 "Optimizer: per warehouse x date x shift, the cheapest (FE, Merch) pair with both departments at the target under the official fill rule (regular, then cross-trained, then OT); "
                 "where the target is out of reach, expected misses are minimised and the block is flagged.</p>")
    parts.append("<h3>Utilization at which P(meet) falls below 90%</h3>")
    parts.append(tbl(th[th.p_meet_level == 0.90][["dept", "store_id", "u_threshold", "ci90_lo", "ci90_hi"]], fmt={"u_threshold": "{:.3f}", "ci90_lo": "{:.3f}", "ci90_hi": "{:.3f}"}))
    parts.append("</body></html>")
    path = os.path.join(out_dir, "poc_static.html")
    with open(path, "w") as fh:
        fh.write("\n".join(parts))
    return path


if __name__ == "__main__":
    print(run(sys.argv[1], sys.argv[2]))
