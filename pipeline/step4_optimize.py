"""
step4_optimize.py - Staffing optimizer (Phase 2, Step 4).

Writes:
  outputs/04_callout_rates.csv        callout rates by dept x day category (flu cluster excluded) + flu-cluster rates
  outputs/04_plans_all.csv            every evaluated plan row: scenario x setting x block (heads, fill, cost, P(meet) both bases)
  outputs/04_plan_summary.csv         one row per scenario x setting: cost split, expected misses, flags
  outputs/04_plan_recommended.csv     the recommended plan (post-callout basis, tau = 0.90) for the three scenarios
  outputs/04_capacity_bound.csv       blocks that cannot reach tau at full capacity, with remaining risk
  outputs/04_threshold_cost.csv       cost and expected misses at tau = 0.80 / 0.90 / 0.95 per scenario
  outputs/04_marginal_value.csv/.png  marginal P(meet) per marginal dollar at the recommended plan
"""
from __future__ import annotations

import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from common import load_all, hist_frame, planning_grid, DEPT_SHORT
from engine import build_blocks, optimize_trio, evaluate_plan, summarize, fill_block, av_from_rows, BlockModel

SETTINGS = [  # name, basis, tau, demand_quantile, valentine
    ("rec_post90", "post_callout", 0.90, None, "mid"),
    ("post80", "post_callout", 0.80, None, "mid"),
    ("post95", "post_callout", 0.95, None, "mid"),
    ("sub90", "submitted", 0.90, None, "mid"),
    ("post90_q80", "post_callout", 0.90, 0.80, "mid"),
    ("post90_val_low", "post_callout", 0.90, None, "low"),
    ("post90_val_high", "post_callout", 0.90, None, "high"),
]
RECOMMENDED = "rec_post90"


def callout_rates(h: pd.DataFrame) -> pd.DataFrame:
    o = h[h.is_open == 1].copy()
    o["flu"] = o.availability_note.str.contains("Flu", na=False)
    o["post_hol"] = o.day_date.isin(pd.to_datetime(["2026-01-02", "2026-01-20"]))
    o["cat"] = np.where(o.post_hol, "post_holiday", np.where(o.day_type == "Weekday", "weekday", "weekend"))
    base = o[~o.flu].groupby(["dept_id", "cat"]).agg(scheduled=("scheduled_employees", "sum"), callouts=("callout_employees", "sum"),
                                                     backfills=("backfill_employees", "sum"), blocks=("callout_employees", "size")).reset_index()
    base["rate"] = base.callouts / base.scheduled
    base["backfill_share"] = base.backfills / base.callouts
    base["se_rate"] = np.sqrt(base.rate * (1 - base.rate) / base.scheduled)
    base["dept"] = base.dept_id.map(DEPT_SHORT); base["source"] = "history excl. W2 flu cluster Jan 22-28"
    flu = o[o.flu].groupby("dept_id").agg(scheduled=("scheduled_employees", "sum"), callouts=("callout_employees", "sum"),
                                          backfills=("backfill_employees", "sum"), blocks=("callout_employees", "size")).reset_index()
    flu["rate"] = flu.callouts / flu.scheduled; flu["backfill_share"] = flu.backfills / flu.callouts
    flu["se_rate"] = np.sqrt(flu.rate * (1 - flu.rate) / flu.scheduled); flu["cat"] = "flu_cluster_W2"
    flu["dept"] = flu.dept_id.map(DEPT_SHORT); flu["source"] = "W2 flu cluster only (not used for planning; DISRUPT illness is in availability)"
    allr = o.groupby("dept_id").agg(scheduled=("scheduled_employees", "sum"), callouts=("callout_employees", "sum")).reset_index()
    allr["rate"] = allr.callouts / allr.scheduled; allr["cat"] = "all_blocks_incl_flu"; allr["dept"] = allr.dept_id.map(DEPT_SHORT)
    allr["source"] = "reference only"
    # MLK Monday check
    mlk = o[o.day_date == pd.Timestamp("2026-01-19")].groupby("dept_id").agg(scheduled=("scheduled_employees", "sum"), callouts=("callout_employees", "sum")).reset_index()
    mlk["rate"] = mlk.callouts / mlk.scheduled; mlk["cat"] = "MLK_Monday_only"; mlk["dept"] = mlk.dept_id.map(DEPT_SHORT); mlk["source"] = "reference only (n = 9 blocks)"
    return pd.concat([base, flu, allr, mlk], ignore_index=True)


def valentine_overrides(out_dir: str, which: str) -> dict:
    """Multipliers (relative to the mid forecast) for FE/Merch Feb 13-14 blocks, from 03_valentine_sensitivity.csv."""
    if which == "mid":
        return {}
    vs = pd.read_csv(os.path.join(out_dir, "03_valentine_sensitivity.csv"), parse_dates=["day_date"])
    out = {}
    for r in vs.itertuples():
        m = (r.low if which == "low" else r.high) / r.mid
        for sh in ("OPEN", "MID", "EVE"):
            out[(int(r.store_id), int(r.dept_id), r.day_date, sh)] = float(m)
    return out


def run_plan(blocks: pd.DataFrame, params: dict, basis: str, tau: float, demand_quantile=None):
    heads = {}; models = {}
    for (store, date, shift), trio in blocks.groupby(["store_id", "day_date", "shift_code"], sort=False):
        res = optimize_trio(trio, params, tau=tau, basis=basis, demand_quantile=demand_quantile)
        for d, n in res["heads"].items():
            heads[(store, date, shift, d)] = int(n)
        for d, m in res["models"].items():
            models[(store, date, shift, d)] = m
    ev = evaluate_plan(blocks, heads, params, tau=tau, models_cache=models, demand_quantile=demand_quantile)
    return ev, heads, models


def run(data_dir: str, out_dir: str) -> dict:
    t0 = time.time()
    tabs = load_all(data_dir); h = hist_frame(tabs); grid = planning_grid(tabs)
    params = json.load(open(os.path.join(out_dir, "01_service_params.json")))
    fc = pd.read_csv(os.path.join(out_dir, "03_forecast_shift.csv"), parse_dates=["day_date"])
    rates = callout_rates(h)
    rates.to_csv(os.path.join(out_dir, "04_callout_rates.csv"), index=False)
    base_rates = rates[rates.cat.isin(["weekday", "weekend", "post_holiday"])]

    all_rows, summ, capb = [], [], []
    models_by_scn = {}
    for name, basis, tau, dq, val in SETTINGS:
        for scn in ("BASE", "PEAK", "DISRUPT"):
            blocks = build_blocks(grid, fc, base_rates, scn, demand_mult=valentine_overrides(out_dir, val))
            ev, heads, models = run_plan(blocks, params, basis, tau, dq)
            ev.insert(0, "setting", name); ev.insert(1, "basis", basis); ev.insert(2, "tau", tau)
            all_rows.append(ev)
            s = summarize(ev); s.update(setting=name, scenario=scn, basis=basis, tau=tau, demand_quantile=dq, valentine=val)
            summ.append(s)
            if name == RECOMMENDED:
                models_by_scn[scn] = (blocks, heads, models, ev)
            # capacity-bound blocks (optimizer could not reach tau on the chosen basis)
            pcol = "p_meet_post_callout" if basis == "post_callout" else "p_meet_submitted"
            cb = ev[(ev.is_open == 1) & (ev[pcol] < tau)]
            for r in cb.itertuples():
                capb.append(dict(setting=name, scenario=scn, store_id=r.store_id, dept=r.dept, day_date=r.day_date.date(), shift_code=r.shift_code,
                                 heads=r.heads, capacity_loose=r.capacity_loose, reg=r.reg, flex=r.flex, ot=r.ot, utilization=r.utilization,
                                 p_meet_submitted=r.p_meet_submitted, p_meet_post_callout=r.p_meet_post_callout, draft_heads=r.draft_heads,
                                 forecast_demand=r.forecast_demand))
            print(f"   {name:16s} {scn:8s} cost ${s['cost']:>10,.0f}  exp missed (sub/post) {s['exp_missed_submitted']:5.1f}/{s['exp_missed_post']:5.1f}  "
                  f"below tau (sub/post) {s['blocks_below_tau_submitted']:3d}/{s['blocks_below_tau_post']:3d}  OT heads {s['ot_heads']:3d}  [{time.time()-t0:.0f}s]")
    plans = pd.concat(all_rows, ignore_index=True)
    plans.to_csv(os.path.join(out_dir, "04_plans_all.csv"), index=False)
    summary = pd.DataFrame(summ)
    summary.to_csv(os.path.join(out_dir, "04_plan_summary.csv"), index=False)
    rec = plans[plans.setting == RECOMMENDED].copy()
    rec.to_csv(os.path.join(out_dir, "04_plan_recommended.csv"), index=False)
    pd.DataFrame(capb).to_csv(os.path.join(out_dir, "04_capacity_bound.csv"), index=False)

    # threshold cost table
    tc = summary[summary.setting.isin(["post80", "rec_post90", "post95"])][["scenario", "tau", "cost", "exp_missed_post", "exp_missed_submitted",
                                                                               "blocks_below_tau_post", "ot_heads", "heads", "labor_hours"]].sort_values(["scenario", "tau"])
    tc.to_csv(os.path.join(out_dir, "04_threshold_cost.csv"), index=False)

    # marginal value at the recommended plan: +1 head on each open block
    mv = []
    for scn, (blocks, heads, models, ev) in models_by_scn.items():
        for (store, date, shift), trio in blocks.groupby(["store_id", "day_date", "shift_code"], sort=False):
            av = av_from_rows(trio)
            n0 = {int(r.dept_id): heads[(store, date, shift, int(r.dept_id))] for r in trio.itertuples()}
            f0 = fill_block(n0, av)
            for r in trio.itertuples():
                d = int(r.dept_id)
                if not r.open:
                    continue
                m = models[(store, date, shift, d)]
                for delta in (-1, +1):
                    n1 = dict(n0); n1[d] = n0[d] + delta
                    if n1[d] < 1:
                        continue
                    f1 = fill_block(n1, av)
                    if f1[d]["infeasible_strict"] and delta > 0:
                        continue
                    p0 = m.p_post_callout(n0[d], max(0, av[d]["O"] - f0[d]["ot"]))
                    p1 = m.p_post_callout(n1[d], max(0, av[d]["O"] - f1[d]["ot"]))
                    dc = (f1[fe := 38]["cost"] + f1[92]["cost"] + f1[95]["cost"] if 95 in f1 else 0) - (f0[38]["cost"] + f0[92]["cost"] + (f0[95]["cost"] if 95 in f0 else 0))
                    mv.append(dict(scenario=scn, store_id=store, dept=r.dept, day_date=date.date(), shift_code=shift, heads=n0[d], delta=delta,
                                   utilization_at_plan=m.utilization(n0[d]), p_meet_plan=p0, p_meet_after=p1, delta_p=p1 - p0, delta_cost=dc,
                                   dp_per_100usd=(p1 - p0) / dc * 100 if dc > 0 else np.nan))
    mv = pd.DataFrame(mv)
    mv.to_csv(os.path.join(out_dir, "04_marginal_value.csv"), index=False)
    chart_marginal(mv, out_dir)
    print(f"   step 4 done in {time.time()-t0:.0f}s")
    return dict(plans=plans, summary=summary, rates=rates, capacity_bound=pd.DataFrame(capb), threshold=tc, marginal=mv)


def chart_marginal(mv: pd.DataFrame, out_dir: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x = mv[(mv.scenario == "BASE") & (mv.delta == 1)]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    colors = {"FE": "#1f5f8b", "Merch": "#4e8542", "Pharm": "#c0504d"}
    ax = axes[0]
    for d, g in x.groupby("dept"):
        ax.scatter(g.utilization_at_plan, g.delta_p, s=14, alpha=0.7, color=colors[d], label=d, edgecolor="none")
    ax.set_xlabel("Utilization at the recommended head count"); ax.set_ylabel("Gain in P(meet) from one more head")
    ax.set_title("Where one more head matters (BASE, post-callout basis)", fontsize=10); ax.legend(frameon=False, fontsize=8)
    ax = axes[1]
    y = mv[(mv.scenario == "BASE") & (mv.delta == -1)]
    for d, g in y.groupby("dept"):
        ax.scatter(g.utilization_at_plan, -g.delta_p, s=14, alpha=0.7, color=colors[d], label=d, edgecolor="none")
    ax.set_xlabel("Utilization at the recommended head count"); ax.set_ylabel("Loss in P(meet) from one fewer head")
    ax.set_title("What one fewer head costs in service (BASE)", fontsize=10)
    fig.suptitle("The curve is steep: a head below the plan loses far more service than a head above it gains", fontsize=11)
    fig.tight_layout(); fig.savefig(os.path.join(out_dir, "04_marginal_value.png"), dpi=150); plt.close(fig)


if __name__ == "__main__":
    res = run(sys.argv[1], sys.argv[2])
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(res["summary"].round(2).to_string(index=False))
    print(res["capacity_bound"].round(3).to_string(index=False))
