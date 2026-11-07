"""
step2_diagnosis.py - Diagnosis of historical staffing (Phase 1, Step 2).

For every open historical block, the Step 1 curve gives P(meet | heads). We compute
  n90 = smallest head count (>= min_staff) with P(meet) >= 90% at the block's ACTUAL demand
and classify the block on its WORKED heads (what served demand) and, separately, on its
SCHEDULED heads (what the manager planned before callouts):
  over-staffed   heads > n90 (heads could drop and still keep P(meet) >= 90%)
  right-sized    heads == n90
  under-staffed  heads < n90 (P(meet) < 90%)

Dollars beyond the 90% need = surplus heads x paid hours x the rate those marginal heads were
paid (OT hours come off first because they are the last filled under the official rule).

Writes:
  outputs/02_block_classification.csv   one row per open historical block
  outputs/02_pattern_wh_dept_shift_daytype.csv   systematic patterns
  outputs/02_summary_wh_dept.csv        surplus $ vs deficit $ by warehouse x dept, feasibility of moving hours
  outputs/02_headline.json              numbers for the headline sentence
"""
from __future__ import annotations

import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from common import load_all, hist_frame, DEPT_SHORT
from step1_service import pmeet_from_params

P_LEVEL = 0.90


def heads_for_level(req_hours, paid_hours, min_staff, store, params, target, level=P_LEVEL, max_heads=80):
    """Smallest integer head count n >= min_staff with P(meet | u = req/(n*paid)) >= level."""
    n = np.arange(1, max_heads + 1)
    u = req_hours / (n * paid_hours)
    pm = pmeet_from_params(params, u, np.full_like(n, store), target)
    ok = np.where(pm >= level)[0]
    n_needed = int(n[ok[0]]) if len(ok) else max_heads
    return max(n_needed, int(min_staff))


def classify(n, n90):
    return np.where(n > n90, "over", np.where(n < n90, "under", "right"))


def run(data_dir: str, out_dir: str, params: dict | None = None) -> dict:
    tabs = load_all(data_dir); h = hist_frame(tabs)
    if params is None:
        with open(os.path.join(out_dir, "01_service_params.json")) as fh:
            params = json.load(fh)
    o = h[(h.is_open == 1)].copy()

    n90 = []
    for r in o.itertuples(index=False):
        p = params[DEPT_SHORT[r.dept_id]]
        n90.append(heads_for_level(r.required_hours_100, r.paid_hours, r.min_staff, r.store_id, p, p["target"]))
    o["n90"] = n90
    o["p_meet_worked"] = [float(pmeet_from_params(params[DEPT_SHORT[r.dept_id]], np.array([r.utilization]),
                                                  np.array([r.store_id]), params[DEPT_SHORT[r.dept_id]]["target"])[0])
                          for r in o.itertuples(index=False)]
    o["p_meet_sched"] = [float(pmeet_from_params(params[DEPT_SHORT[r.dept_id]], np.array([r.sched_utilization]),
                                                 np.array([r.store_id]), params[DEPT_SHORT[r.dept_id]]["target"])[0])
                         for r in o.itertuples(index=False)]
    o["class_worked"] = classify(o.worked_employees.values, o.n90.values)
    o["class_sched"] = classify(o.scheduled_employees.values, o.n90.values)
    o["gap_worked"] = o.worked_employees - o.n90          # + = surplus heads, - = deficit heads
    o["gap_sched"] = o.scheduled_employees - o.n90

    # surplus $ (worked basis): remove surplus heads from the top of the fill stack (OT first)
    surplus = np.clip(o.gap_worked, 0, None)
    ot_cut = np.minimum(surplus, o.worked_overtime_employees)
    reg_cut = surplus - ot_cut
    o["surplus_heads"] = surplus
    o["surplus_hours"] = surplus * o.paid_hours
    o["surplus_cost"] = (ot_cut * o.loaded_overtime_hourly_cost + reg_cut * o.loaded_regular_hourly_cost) * o.paid_hours
    # deficit $ (worked basis): add heads at the regular rate if regular availability allows, else OT
    deficit = np.clip(-o.gap_worked, 0, None)
    reg_room = np.clip(o.available_regular_employees - o.worked_regular_employees, 0, None)
    reg_add = np.minimum(deficit, reg_room)
    ot_room = np.clip(o.max_overtime_employees - o.worked_overtime_employees, 0, None)
    ot_add = np.minimum(deficit - reg_add, ot_room)
    unfillable = deficit - reg_add - ot_add
    o["deficit_heads"] = deficit
    o["deficit_hours"] = deficit * o.paid_hours
    o["deficit_cost"] = (reg_add * o.loaded_regular_hourly_cost + ot_add * o.loaded_overtime_hourly_cost) * o.paid_hours
    o["deficit_unfillable_heads"] = unfillable  # heads the block could not have added even with all regular + OT
    o["missed"] = (o.met_target == 0).astype(int)
    o["missed_understaffed"] = ((o.met_target == 0) & (o.class_worked == "under")).astype(int)
    o["missed_badluck"] = ((o.met_target == 0) & (o.class_worked != "under")).astype(int)

    keep = ["store_id", "dept_id", "dept", "day_date", "day_name", "day_type", "holiday_window_role", "shift_code", "week_idx",
            "shift_demand_units", "required_hours_100", "paid_hours", "min_staff", "scheduled_employees", "callout_employees",
            "backfill_employees", "worked_employees", "worked_regular_employees", "worked_overtime_employees",
            "available_regular_employees", "max_overtime_employees", "cross_trained_flex_employees",
            "utilization", "sched_utilization", "metric_value", "target_value", "met_target", "p_meet_worked", "p_meet_sched",
            "n90", "class_worked", "class_sched", "gap_worked", "gap_sched", "surplus_heads", "surplus_hours", "surplus_cost",
            "deficit_heads", "deficit_hours", "deficit_cost", "deficit_unfillable_heads", "missed", "missed_understaffed",
            "missed_badluck", "labor_cost"]
    o[keep].to_csv(os.path.join(out_dir, "02_block_classification.csv"), index=False)

    # systematic patterns
    pat = o.groupby(["store_id", "dept", "shift_code", "day_type"]).agg(
        blocks=("gap_worked", "size"),
        avg_gap_worked=("gap_worked", "mean"), avg_gap_sched=("gap_sched", "mean"),
        pct_over=("class_worked", lambda s: (s == "over").mean()),
        pct_under=("class_worked", lambda s: (s == "under").mean()),
        pct_over_sched=("class_sched", lambda s: (s == "over").mean()),
        pct_under_sched=("class_sched", lambda s: (s == "under").mean()),
        avg_util=("utilization", "mean"), pct_met=("met_target", "mean"),
        surplus_cost=("surplus_cost", "sum"), deficit_cost=("deficit_cost", "sum"),
        missed=("missed", "sum"), missed_understaffed=("missed_understaffed", "sum")).reset_index()
    pat["verdict"] = np.where(pat.avg_gap_sched >= 1.0, "systematically OVER",
                              np.where(pat.avg_gap_sched <= -0.5, "systematically UNDER", "mixed / about right"))
    pat.to_csv(os.path.join(out_dir, "02_pattern_wh_dept_shift_daytype.csv"), index=False)

    # warehouse x dept summary: can surplus pay for deficit?
    sm = o.groupby(["store_id", "dept"]).agg(
        blocks=("gap_worked", "size"), labor_cost=("labor_cost", "sum"),
        over_blocks=("class_worked", lambda s: (s == "over").sum()),
        under_blocks=("class_worked", lambda s: (s == "under").sum()),
        right_blocks=("class_worked", lambda s: (s == "right").sum()),
        surplus_hours=("surplus_hours", "sum"), surplus_cost=("surplus_cost", "sum"),
        deficit_hours=("deficit_hours", "sum"), deficit_cost=("deficit_cost", "sum"),
        deficit_unfillable_heads=("deficit_unfillable_heads", "sum"),
        missed=("missed", "sum"), missed_understaffed=("missed_understaffed", "sum"),
        missed_badluck=("missed_badluck", "sum"), pct_met=("met_target", "mean")).reset_index()
    sm["net_cost_of_fix"] = sm.deficit_cost - sm.surplus_cost
    sm["surplus_pct_of_cost"] = sm.surplus_cost / sm.labor_cost
    sm.to_csv(os.path.join(out_dir, "02_summary_wh_dept.csv"), index=False)

    tot = dict(
        open_blocks=int(len(o)), labor_cost=float(o.labor_cost.sum()),
        over_blocks=int((o.class_worked == "over").sum()), under_blocks=int((o.class_worked == "under").sum()),
        right_blocks=int((o.class_worked == "right").sum()),
        over_blocks_sched=int((o.class_sched == "over").sum()), under_blocks_sched=int((o.class_sched == "under").sum()),
        surplus_hours=float(o.surplus_hours.sum()), surplus_cost=float(o.surplus_cost.sum()),
        surplus_pct_of_cost=float(o.surplus_cost.sum() / o.labor_cost.sum()),
        deficit_hours=float(o.deficit_hours.sum()), deficit_cost=float(o.deficit_cost.sum()),
        deficit_unfillable_heads=int(o.deficit_unfillable_heads.sum()),
        net_cost_of_fix=float(o.deficit_cost.sum() - o.surplus_cost.sum()),
        missed_blocks=int(o.missed.sum()), missed_understaffed=int(o.missed_understaffed.sum()),
        missed_badluck=int(o.missed_badluck.sum()),
        hit_rate=float(o.met_target.mean()),
        expected_hit_rate_if_all_at_n90=float(np.mean(np.where(o.class_worked == "under",
                                                                 P_LEVEL, np.maximum(o.p_meet_worked, P_LEVEL)))),
        avg_surplus_heads_over_blocks=float(o.loc[o.class_worked == "over", "surplus_heads"].mean()),
        avg_deficit_heads_under_blocks=float(o.loc[o.class_worked == "under", "deficit_heads"].mean()),
    )
    # same-warehouse, same-dept matching of surplus and deficit hours (labor cannot cross warehouses)
    sm2 = sm.copy()
    sm2["matched_cost"] = np.minimum(sm2.surplus_cost, sm2.deficit_cost)
    tot["deficit_coverable_by_same_wh_dept_surplus_pct"] = float(sm2.matched_cost.sum() / sm2.deficit_cost.sum())
    # pooled within warehouse: FE + Merch share cross-trained staff, Pharmacy is its own pool
    sm3 = sm.copy(); sm3["pool"] = np.where(sm3.dept == "Pharm", "Pharm", "FE+Merch")
    sm3 = sm3.groupby(["store_id", "pool"]).agg(surplus_cost=("surplus_cost", "sum"), deficit_cost=("deficit_cost", "sum")).reset_index()
    sm3["matched_cost"] = np.minimum(sm3.surplus_cost, sm3.deficit_cost)
    tot["deficit_coverable_by_same_wh_pool_pct"] = float(sm3.matched_cost.sum() / sm3.deficit_cost.sum())
    tot["pool_table"] = {f"W{r.store_id}-{r.pool}": dict(surplus=round(float(r.surplus_cost)), deficit=round(float(r.deficit_cost)))
                         for r in sm3.itertuples()}
    tot["net_cost_by_wh_dept"] = {f"W{r.store_id}-{r.dept}": round(float(r.net_cost_of_fix), 0) for r in sm.itertuples()}
    with open(os.path.join(out_dir, "02_headline.json"), "w") as fh:
        json.dump(tot, fh, indent=2)
    return dict(blocks=o, patterns=pat, summary=sm, headline=tot)


if __name__ == "__main__":
    res = run(sys.argv[1], sys.argv[2])
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(json.dumps(res["headline"], indent=1))
    print(res["summary"].round(2).to_string(index=False))
    pat = res["patterns"]
    print(pat.sort_values("avg_gap_sched").round(2).to_string(index=False))
