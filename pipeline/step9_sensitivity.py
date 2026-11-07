"""
step9_sensitivity.py - tornado inputs for the appendix: re-optimise the BASE plan under one-at-a-time changes.

Writes outputs/09_tornado.csv and outputs/09_tornado.png
"""
from __future__ import annotations
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from common import load_all, planning_grid
from engine import build_blocks, optimize_trio, evaluate_plan
from step4_optimize import valentine_overrides


def plan(grid, fc, rates, params, scenario, tau, basis, demand_mult=None, callout_mult=1.0, log_sd_mult=1.0):
    blocks = build_blocks(grid, fc, rates, scenario, demand_mult=demand_mult, callout_mult=callout_mult)
    blocks["log_sd"] = blocks.log_sd * log_sd_mult
    heads, models = {}, {}
    for (store, date, shift), trio in blocks.groupby(["store_id", "day_date", "shift_code"], sort=False):
        res = optimize_trio(trio, params, tau=tau, basis=basis)
        for d, n in res["heads"].items():
            heads[(store, date, shift, d)] = int(n)
        for d, m in res["models"].items():
            models[(store, date, shift, d)] = m
    ev = evaluate_plan(blocks, heads, params, tau=tau, models_cache=models)
    o = ev[ev.is_open == 1]
    return dict(cost=float(o.cost.sum()), heads=int(o.heads.sum()), ot=int(o.ot.sum()), exp_missed_post=float((1 - o.p_meet_post_callout).sum()),
                exp_missed_sub=float((1 - o.p_meet_submitted).sum()), below=int((o.p_meet_post_callout < tau).sum()))


def run(data_dir: str, out_dir: str):
    tabs = load_all(data_dir); grid = planning_grid(tabs)
    params = json.load(open(os.path.join(out_dir, "01_service_params.json")))
    fc = pd.read_csv(os.path.join(out_dir, "03_forecast_shift.csv"), parse_dates=["day_date"])
    rates = pd.read_csv(os.path.join(out_dir, "04_callout_rates.csv")); rates = rates[rates.cat.isin(["weekday", "weekend", "post_holiday"])]
    hol_days = [pd.Timestamp(d) for d in ("2026-02-13", "2026-02-14", "2026-02-15", "2026-02-16")]
    def hol_mult(m):
        return {(s, d, day, sh): m for s in (1, 2, 4) for d in (38, 92, 95) for day in hol_days for sh in ("OPEN", "MID", "EVE")}
    def promo_mult(m):  # extra lift on Fri-Mon FE/Merch only (a 'promo beyond the holiday factor' case)
        return {(s, d, day, sh): m for s in (1, 2, 4) for d in (38, 92) for day in hol_days for sh in ("OPEN", "MID", "EVE")}
    cases = [
        ("Base case (90%, post-callout)", dict(tau=0.90, basis="post_callout")),
        ("Service target 80%", dict(tau=0.80, basis="post_callout")),
        ("Service target 95%", dict(tau=0.95, basis="post_callout")),
        ("No callout buffer (submitted basis)", dict(tau=0.90, basis="submitted")),
        ("Callout rate x0.5", dict(tau=0.90, basis="post_callout", callout_mult=0.5)),
        ("Callout rate x1.5", dict(tau=0.90, basis="post_callout", callout_mult=1.5)),
        ("Valentine's low (none)", dict(tau=0.90, basis="post_callout", demand_mult=valentine_overrides(out_dir, "low"))),
        ("Valentine's high (+10% FE Sat)", dict(tau=0.90, basis="post_callout", demand_mult=valentine_overrides(out_dir, "high"))),
        ("Holiday factors 5 pts lower (Feb 13-16 x0.95)", dict(tau=0.90, basis="post_callout", demand_mult=hol_mult(0.95))),
        ("Holiday factors 5 pts higher (Feb 13-16 x1.05)", dict(tau=0.90, basis="post_callout", demand_mult=hol_mult(1.05))),
        ("Promo lift +5% FE/Merch Feb 13-16 (beyond holiday)", dict(tau=0.90, basis="post_callout", demand_mult=promo_mult(1.05))),
        ("Forecast uncertainty halved", dict(tau=0.90, basis="post_callout", log_sd_mult=0.5)),
        ("Forecast uncertainty doubled", dict(tau=0.90, basis="post_callout", log_sd_mult=2.0)),
    ]
    rows = []
    for name, kw in cases:
        r = plan(grid, fc, rates, params, "BASE", **kw); r["case"] = name; rows.append(r)
        print(f"   {name:48s} cost ${r['cost']:>9,.0f}  heads {r['heads']}  OT {r['ot']:3d}  exp missed post {r['exp_missed_post']:5.1f}")
    t = pd.DataFrame(rows)[["case", "cost", "heads", "ot", "exp_missed_sub", "exp_missed_post", "below"]]
    base = t.iloc[0]
    t["cost_delta"] = t.cost - base.cost; t["cost_delta_pct"] = t.cost_delta / base.cost; t["missed_delta"] = t.exp_missed_post - base.exp_missed_post
    t.to_csv(os.path.join(out_dir, "09_tornado.csv"), index=False)
    chart(t, out_dir)
    return t


def chart(t: pd.DataFrame, out_dir: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x = t.iloc[1:].copy(); x = x.reindex(x.cost_delta.abs().sort_values().index)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
    ax = axes[0]
    ax.barh(x.case, x.cost_delta / 1000, color=np.where(x.cost_delta >= 0, "#2f5f7e", "#8c3b2e"))
    ax.axvline(0, color="#1a1a1a", lw=0.8); ax.set_xlabel("Change in BASE labor cost vs base case ($000)")
    ax.set_title("What moves the cost", fontsize=10, loc="left")
    ax = axes[1]
    ax.barh(x.case, x.missed_delta, color=np.where(x.missed_delta >= 0, "#8c3b2e", "#2f5f7e"))
    ax.axvline(0, color="#1a1a1a", lw=0.8); ax.set_xlabel("Change in expected missed blocks (after callouts) vs base case")
    ax.set_title("What moves the service risk", fontsize=10, loc="left"); ax.set_yticklabels([])
    fig.suptitle(f"BASE sensitivity (base case: ${t.iloc[0].cost:,.0f}, {t.iloc[0].exp_missed_post:.1f} expected missed blocks)", fontsize=11)
    fig.tight_layout(); fig.savefig(os.path.join(out_dir, "09_tornado.png"), dpi=150); plt.close(fig)


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
