"""
step6_playbook.py - Leader playbook: triggers and actions computed from the recommended plan and the service curve.

For every open block of the recommended BASE plan:
  callout_tolerance_80 / _50  the number of same-block callouts (no backfill) at which P(meet) falls below 80% / 50%
  flex_pull_ok                how many cross-trained partner heads can be pulled before the PARTNER drops below 90%
  ot_room                     overtime heads still unused by the plan (backfill capacity)
  ot_cost_per_head            cost of one OT head for this block
Writes:
  outputs/06_playbook_blocks.csv      block-level triggers
  outputs/06_playbook_rules.csv       the one-page rules table (warehouse x dept x shift x day type)
  outputs/06_peak_delta.csv           heads to add when switching BASE -> PEAK, by warehouse x day x dept
  outputs/06_escalation_costs.csv     cost of each escalation step
  outputs/06_playbook.md              the one-page playbook text
"""
from __future__ import annotations

import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from common import load_all, planning_grid, DEPT_SHORT
from engine import build_blocks, BlockModel, fill_block, av_from_rows, PARTNER, worked_dist, BACKFILL_Q


def run(data_dir: str, out_dir: str) -> dict:
    tabs = load_all(data_dir); grid = planning_grid(tabs)
    params = json.load(open(os.path.join(out_dir, "01_service_params.json")))
    fc = pd.read_csv(os.path.join(out_dir, "03_forecast_shift.csv"), parse_dates=["day_date"])
    rates = pd.read_csv(os.path.join(out_dir, "04_callout_rates.csv")); base_rates = rates[rates.cat.isin(["weekday", "weekend", "post_holiday"])]
    rec = pd.read_csv(os.path.join(out_dir, "04_plan_recommended.csv"), parse_dates=["day_date"])
    rows = []
    for scn in ("BASE", "PEAK", "DISRUPT"):
        blocks = build_blocks(grid, fc, base_rates, scn)
        plan = rec[rec.scenario_code == scn]
        heads = {(r.store_id, r.day_date, r.shift_code, int(r.dept_id)): int(r.heads) for r in plan.itertuples()}
        for (store, date, shift), trio in blocks.groupby(["store_id", "day_date", "shift_code"], sort=False):
            av = av_from_rows(trio)
            n = {int(r.dept_id): heads[(store, date, shift, int(r.dept_id))] for r in trio.itertuples()}
            fb = fill_block(n, av)
            models = {int(r.dept_id): BlockModel(r.demand, r.log_sd, r.std, r.paid, int(store), params[r.dept], r.p_callout)
                      for r in trio.itertuples() if r.open}
            for r in trio.itertuples():
                d = int(r.dept_id)
                if not r.open:
                    continue
                m = models[d]; nd = n[d]
                p0 = m.p_submitted(nd)
                tol80 = tol50 = None
                for k in range(0, nd):
                    pk = m.p_submitted(nd - k)
                    if tol80 is None and pk < 0.80:
                        tol80 = k
                    if tol50 is None and pk < 0.50:
                        tol50 = k; break
                tol80 = nd if tol80 is None else tol80; tol50 = nd if tol50 is None else tol50
                # flex that can be pulled from the partner before the partner falls below 90%
                flex_ok = 0; pd_partner = None
                p = PARTNER.get(d)
                if p is not None and p in models and av[p]["open"]:
                    spare = max(0, av[p]["A"] - fb[p]["reg"])
                    maxpull = min(av[d]["F"], spare + fb[p]["reg"])  # could in principle pull partner regulars that are working
                    pd_partner = models[p].p_submitted(n[p])
                    for k in range(1, maxpull + 1):
                        if n[p] - k < av[p]["min_staff"] or models[p].p_submitted(n[p] - k) < 0.90:
                            break
                        flex_ok = k
                ot_room = max(0, av[d]["O"] - fb[d]["ot"])
                rows.append(dict(scenario=scn, store_id=int(store), dept=r.dept, dept_id=d, day_date=date.date(), day_name=r.day_name, day_type=r.day_type,
                                 shift_code=shift, heads=nd, reg=fb[d]["reg"], flex=fb[d]["flex"], ot=fb[d]["ot"], p_meet_submitted=p0,
                                 p_meet_post_callout=m.p_post_callout(nd, ot_room), expected_callouts=nd * r.p_callout,
                                 callout_tolerance_80=tol80, callout_tolerance_50=tol50, p_after_1_callout=m.p_submitted(nd - 1),
                                 p_after_2_callouts=m.p_submitted(max(nd - 2, 1)), flex_pull_ok=flex_ok, partner_p_meet=pd_partner,
                                 ot_room=ot_room, ot_cost_per_head=float(r.paid * r.ro), reg_cost_per_head=float(r.paid * r.rr),
                                 ot_premium_per_head=float(r.paid * (r.ro - r.rr)), utilization=m.utilization(nd),
                                 forecast_demand=float(r.demand), capacity_loose=int(r.A + r.F + r.O)))
    pb = pd.DataFrame(rows)
    pb.to_csv(os.path.join(out_dir, "06_playbook_blocks.csv"), index=False)

    # rules table: BASE, warehouse x dept x shift x day type
    b = pb[pb.scenario == "BASE"].copy()
    b["dtype"] = np.where(b.day_type == "Weekday", "weekday", "weekend")
    rules = b.groupby(["store_id", "dept", "shift_code", "dtype"]).agg(
        blocks=("heads", "size"), typical_heads=("heads", "median"), exp_callouts=("expected_callouts", "mean"),
        tolerance_80=("callout_tolerance_80", "min"), tolerance_50=("callout_tolerance_50", "min"),
        flex_pull_ok=("flex_pull_ok", "min"), ot_room=("ot_room", "min"), ot_premium=("ot_premium_per_head", "mean"),
        p_meet=("p_meet_post_callout", "mean")).reset_index()
    rules["trigger"] = rules.apply(lambda r: f"callouts > {int(r.tolerance_80)} by shift start" if r.tolerance_80 < r.typical_heads else "none (block has slack)", axis=1)
    def action(r):
        steps = []
        if r.dept in ("FE", "Merch") and r.flex_pull_ok > 0:
            steps.append(f"pull up to {int(r.flex_pull_ok)} cross-trained from {'Merch' if r.dept == 'FE' else 'FE'} (partner stays >= 90%)")
        if r.ot_room > 0:
            steps.append(f"then OT up to {int(r.ot_room)} head(s) (+${r.ot_premium:.0f}/head)")
        else:
            steps.append("OT already fully used in the plan: no backfill room")
        steps.append("beyond that: accept risk, see escalation table")
        return "; ".join(steps)
    rules["action"] = rules.apply(action, axis=1)
    rules.to_csv(os.path.join(out_dir, "06_playbook_rules.csv"), index=False)

    # PEAK switch: heads to add vs BASE
    base = rec[rec.scenario_code == "BASE"][["store_id", "dept", "day_date", "shift_code", "heads"]].rename(columns={"heads": "base_heads"})
    peak = rec[rec.scenario_code == "PEAK"][["store_id", "dept", "day_date", "shift_code", "heads", "ot"]].rename(columns={"heads": "peak_heads", "ot": "peak_ot"})
    dl = base.merge(peak, on=["store_id", "dept", "day_date", "shift_code"]); dl["delta"] = dl.peak_heads - dl.base_heads
    pk = dl.groupby(["store_id", "day_date", "dept"]).agg(base_heads=("base_heads", "sum"), peak_heads=("peak_heads", "sum"), delta=("delta", "sum")).reset_index()
    pk = pk[pk.delta != 0]
    pk.to_csv(os.path.join(out_dir, "06_peak_delta.csv"), index=False)
    # DISRUPT: what changes
    dis = rec[rec.scenario_code == "DISRUPT"][["store_id", "dept", "day_date", "shift_code", "heads", "p_meet_post_callout"]].rename(columns={"heads": "disrupt_heads", "p_meet_post_callout": "disrupt_p"})
    dd = base.merge(dis, on=["store_id", "dept", "day_date", "shift_code"]); dd["delta"] = dd.disrupt_heads - dd.base_heads
    dd = dd[dd.delta != 0]
    dd.to_csv(os.path.join(out_dir, "06_disrupt_delta.csv"), index=False)

    # Thursday EVE Merch pre-stock capacity (PEAK): spare regular heads at <= 90% line
    thu = pb[(pb.scenario == "PEAK") & (pb.dept == "Merch") & (pb.day_date == pd.Timestamp("2026-02-12").date()) & (pb.shift_code == "EVE")]

    # escalation costs
    mv = pd.read_csv(os.path.join(out_dir, "04_marginal_value.csv"))
    minus = mv[(mv.scenario == "BASE") & (mv.delta == -1)]
    esc = []
    for d in ("FE", "Merch", "Pharm"):
        x = b[b.dept == d]; y = minus[minus.dept == d]
        esc.append(dict(dept=d, step1_reallocate_within_dept="move a head between shifts of the same day: $0 (same rate), limited by availability",
                        step2_cross_train=("pull a cross-trained partner head: $0 premium; partner loses the P(meet) shown in 06_playbook_blocks" if d != "Pharm" else "not available (licensure)"),
                        step3_ot_premium_per_head=float(x.ot_premium_per_head.mean()), step3_ot_cost_per_head=float(x.ot_cost_per_head.mean()),
                        step4_accept_risk_median_p_loss_per_head_short=float(-y.delta_p.median()), step4_accept_risk_p90_loss=float(-y.delta_p.quantile(0.1))))
    esc = pd.DataFrame(esc); esc.to_csv(os.path.join(out_dir, "06_escalation_costs.csv"), index=False)

    write_playbook_md(out_dir, rules, pk, dd, thu, esc, pb, rec)
    return dict(blocks=pb, rules=rules, peak_delta=pk, disrupt_delta=dd, escalation=esc)


def write_playbook_md(out_dir, rules, pk, dd, thu, esc, pb, rec):
    L = []
    A = L.append
    A("# Leader playbook, planning week Feb 12-18 (one page)\n")
    A("Every number below comes from the fitted service curve and the recommended plan (`outputs/06_*.csv`). "
      "'Tolerance' = callouts a block can absorb before P(meet target) drops below 80%. Base plan heads already include the expected-callout buffer.\n")
    A("## 1. Daily rules by warehouse (BASE plan)\n")
    A("| Warehouse | Dept | Shift | Days | Plan heads | Expected callouts | Tolerance (80% / 50%) | Flex you can pull | OT room | Action |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for r in rules.sort_values(["store_id", "dept", "dtype", "shift_code"]).itertuples():
        A(f"| {r.store_id} | {r.dept} | {r.shift_code} | {r.dtype} | {int(r.typical_heads)} | {r.exp_callouts:.1f} | {int(r.tolerance_80)} / {int(r.tolerance_50)} | "
          f"{int(r.flex_pull_ok)} | {int(r.ot_room)} | {r.action} |")
    A("\nHow to read a row: if callouts in that block exceed the 80% tolerance before the shift starts, act in the order shown. "
      "A tolerance of 0 means the block is already at its planning limit (usually all OT used): the first callout needs an action.\n")
    A("## 2. Scenario switches\n")
    A("**Storm advisory upgraded or promotion confirmed (switch to the PEAK plan).** Heads to add vs BASE, by warehouse and day:\n")
    A("| Warehouse | Date | Dept | BASE heads | PEAK heads | Add |")
    A("|---|---|---|---|---|---|")
    for r in pk.sort_values(["store_id", "day_date", "dept"]).itertuples():
        A(f"| {r.store_id} | {pd.Timestamp(r.day_date).date()} | {r.dept} | {int(r.base_heads)} | {int(r.peak_heads)} | {int(r.delta):+d} |")
    if len(thu):
        A("\nPre-stock on Thursday Feb 12 EVE: Merch Thursday evening blocks run at utilization "
          + ", ".join(f"W{int(r.store_id)} {r.utilization:.2f} ({int(r.heads)} heads, OT room {int(r.ot_room)})" for r in thu.itertuples())
          + ". Each extra head there carries about 5 Merch workload units at the standard (6 h x 0.83 units/h), which is what one Friday OPEN head would otherwise carry. "
            "Moving receiving work to Thursday evening is the cheapest lever because Thursday OT room is unused and Friday/Saturday OPEN blocks are at capacity in PEAK.\n")
    A("**Illness cluster or crew shortage reported (switch to the DISRUPT plan).** Blocks that change vs BASE:\n")
    A("| Warehouse | Date | Shift | Dept | BASE | DISRUPT | Change | P(meet) in DISRUPT |")
    A("|---|---|---|---|---|---|---|---|")
    for r in dd.sort_values(["store_id", "day_date", "shift_code", "dept"]).itertuples():
        A(f"| {r.store_id} | {pd.Timestamp(r.day_date).date()} | {r.shift_code} | {r.dept} | {int(r.base_heads)} | {int(r.disrupt_heads)} | {int(r.delta):+d} | {r.disrupt_p:.2f} |")
    A("\n**Pharmacy cannot flex.** Pharmacy has no cross-trained cover and min_staff 2. When a pharmacy team member is out, OT is the only lever: "
      "protect pharmacy first because one missing head on a 3-4 head block moves P(meet) from above 0.95 to below 0.5 (see `06_playbook_blocks.csv`, p_after_1_callout).\n")
    A("## 3. Escalation order and what each step costs\n")
    A("| Dept | 1. Reallocate within dept | 2. Cross-train | 3. Overtime (premium per head-shift) | 4. Accept risk (P(meet) lost per head short, median / bad case) |")
    A("|---|---|---|---|---|")
    for r in esc.itertuples():
        A(f"| {r.dept} | {r.step1_reallocate_within_dept} | {r.step2_cross_train} | ${r.step3_ot_premium_per_head:.0f} on top of ${r.step3_ot_cost_per_head - r.step3_ot_premium_per_head:.0f} | "
          f"{r.step4_accept_risk_median_p_loss_per_head_short:.2f} / {r.step4_accept_risk_p90_loss:.2f} |")
    A("\nRule of thumb from the curve: a head short on a block at the 90% line costs 0.1-0.4 of a block's P(meet); a head of OT costs $35-70 of premium. "
      "At $35-70 per head against a 10-40 point drop in P(meet), OT is almost always worth it on a block at its planning limit, and never worth it on a block with slack (tolerance >= 2).\n")
    A("## 4. Blocks to watch (recommended plan, P(meet) after callouts below 80%)\n")
    w = pb[(pb.p_meet_post_callout < 0.80)].sort_values(["scenario", "p_meet_post_callout"])
    A("| Scenario | Warehouse | Date | Shift | Dept | Heads | Capacity | P(meet) submitted | P(meet) after callouts | Why |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for r in w.itertuples():
        why = "demand exceeds capacity even with all OT" if r.heads >= r.capacity_loose - 1 and r.p_meet_submitted < 0.5 else ("all OT used, no backfill room" if r.ot_room == 0 else "capacity-bound")
        A(f"| {r.scenario} | {r.store_id} | {r.day_date} | {r.shift_code} | {r.dept} | {int(r.heads)} | {int(r.capacity_loose)} | {r.p_meet_submitted:.2f} | {r.p_meet_post_callout:.2f} | {why} |")
    with open(os.path.join(out_dir, "06_playbook.md"), "w") as fh:
        fh.write("\n".join(L))


if __name__ == "__main__":
    res = run(sys.argv[1], sys.argv[2])
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(res["rules"].round(2).to_string(index=False))
    print(res["escalation"].round(3).to_string(index=False))
