"""
step5_score.py - Score our plan vs the draft (planning week) and backtest the method on the six historical weeks.

Writes:
  outputs/05_plan_vs_draft.csv      one row per scenario x plan (ours at 80/90/95, submitted-basis 90, draft, draft capped)
  outputs/05_plan_vs_draft_blocks.csv  draft evaluated block by block (same columns as 04 plans)
  outputs/05_judges_table.csv       the one table judges can absorb in 10 seconds
  outputs/05_backtest_weekly.csv    week by week: managers (realised and modelled) vs our method (modelled), LOO curves and forecasts
  outputs/05_backtest_blocks.csv    block-level detail of the backtest
  outputs/05_backtest_summary.csv   six-week totals
"""
from __future__ import annotations

import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from common import load_all, hist_frame, planning_grid, DEPT_SHORT, SHIFT_ORDER
from engine import build_blocks, optimize_trio, evaluate_plan, summarize, fill_block, av_from_rows, BlockModel, pmeet_u, worked_dist, BACKFILL_Q
from step1_service import fit_final, U_FIT_MAX
from step3_forecast import daily_history, fit_daily, weekly_levels, predict_daily, shift_shares, HOLIDAY_TRANSFER_SD
from step4_optimize import callout_rates

ROLE_FALLBACK = {"Post_New_Year_Rebound": "Pre_MLK_Weekend", "Pre_MLK_Weekend": "Post_New_Year_Rebound", "MLK_Holiday": "Post_New_Year_Rebound"}


def plan_row(ev: pd.DataFrame, label: str, scn: str, tau=0.90) -> dict:
    o = ev[ev.is_open == 1]
    reg_flex_cost = float(((o.reg + o.flex) * o.paid_hours * o.rr).sum()) if "rr" in o else np.nan
    return dict(scenario=scn, plan=label, heads=int(o.heads.sum()), labor_hours=float((o.heads * o.paid_hours).sum()),
                cost=float(o.cost.sum()), cost_regular_flex=float(o.cost_reg_flex.sum()), cost_ot=float(o.cost_ot.sum()),
                reg_heads=int(o.reg.sum()), flex_heads=int(o.flex.sum()), ot_heads=int(o.ot.sum()),
                exp_missed_submitted=float((1 - o.p_meet_submitted).sum()), exp_missed_post=float((1 - o.p_meet_post_callout).sum()),
                avg_p_submitted=float(o.p_meet_submitted.mean()), avg_p_post=float(o.p_meet_post_callout.mean()),
                blocks_below_90_submitted=int((o.p_meet_submitted < tau).sum()), blocks_below_90_post=int((o.p_meet_post_callout < tau).sum()),
                blocks_below_50_post=int((o.p_meet_post_callout < 0.5).sum()),
                infeasible_strict=int(o.infeasible_strict.sum()), infeasible_loose=int(o.infeasible_loose.sum()), below_min=int(o.below_min.sum()))


def add_cost_split(ev: pd.DataFrame, blocks: pd.DataFrame) -> pd.DataFrame:
    r = blocks[["store_id", "dept_id", "day_date", "shift_code", "rr", "ro"]]
    ev = ev.merge(r, on=["store_id", "dept_id", "day_date", "shift_code"], how="left")
    ev["cost_reg_flex"] = (ev.reg + ev.flex) * ev.paid_hours * ev.rr
    ev["cost_ot"] = ev.ot * ev.paid_hours * ev.ro
    return ev


def run(data_dir: str, out_dir: str) -> dict:
    t0 = time.time()
    tabs = load_all(data_dir); h = hist_frame(tabs); grid = planning_grid(tabs)
    params = json.load(open(os.path.join(out_dir, "01_service_params.json")))
    fc = pd.read_csv(os.path.join(out_dir, "03_forecast_shift.csv"), parse_dates=["day_date"])
    rates = pd.read_csv(os.path.join(out_dir, "04_callout_rates.csv")); base_rates = rates[rates.cat.isin(["weekday", "weekend", "post_holiday"])]
    plans = pd.read_csv(os.path.join(out_dir, "04_plans_all.csv"), parse_dates=["day_date"])

    # ---------------- A. planning week: ours vs draft
    rows, draft_blocks = [], []
    for scn in ("BASE", "PEAK", "DISRUPT"):
        blocks = build_blocks(grid, fc, base_rates, scn)
        models = {}
        draft_heads = {(r.store_id, r.day_date, r.shift_code, int(r.dept_id)): int(r.draft) for r in blocks.itertuples()}
        evd = add_cost_split(evaluate_plan(blocks, draft_heads, params, models_cache=models), blocks)
        evd.insert(0, "plan", "draft"); draft_blocks.append(evd)
        rows.append(plan_row(evd, "Draft schedule (as given)", scn))
        # draft capped at loose capacity (what a feasibility fix-up of the draft would look like)
        capped = {k: min(v, int(blocks[(blocks.store_id == k[0]) & (blocks.day_date == k[1]) & (blocks.shift_code == k[2]) & (blocks.dept_id == k[3])].iloc[0][["A", "O", "F"]].sum()))
                  for k, v in draft_heads.items()}
        evc = add_cost_split(evaluate_plan(blocks, capped, params, models_cache=models), blocks)
        evc.insert(0, "plan", "draft_capped"); draft_blocks.append(evc)
        rows.append(plan_row(evc, "Draft capped at capacity", scn))
        for setting, label in [("post80", "Ours, 80% target"), ("rec_post90", "Ours, 90% target (recommended)"), ("post95", "Ours, 95% target"),
                               ("sub90", "Ours, 90% on submitted heads (no callout buffer)"), ("post90_q80", "Ours, 90% at the 80th demand percentile")]:
            ev = plans[(plans.setting == setting) & (plans.scenario_code == scn)].copy()
            ev = add_cost_split(ev, blocks)
            rows.append(plan_row(ev, label, scn))
    pvd = pd.DataFrame(rows)
    pvd["cost_vs_draft"] = pvd.cost - pvd.groupby("scenario").cost.transform(lambda s: s.iloc[0])
    pvd["cost_vs_draft_pct"] = pvd.cost_vs_draft / pvd.groupby("scenario").cost.transform(lambda s: s.iloc[0])
    pvd.to_csv(os.path.join(out_dir, "05_plan_vs_draft.csv"), index=False)
    pd.concat(draft_blocks, ignore_index=True).to_csv(os.path.join(out_dir, "05_plan_vs_draft_blocks.csv"), index=False)

    jt = pvd[pvd.plan.isin(["Draft schedule (as given)", "Ours, 90% target (recommended)"])][
        ["scenario", "plan", "heads", "cost", "cost_ot", "ot_heads", "exp_missed_submitted", "exp_missed_post", "avg_p_post",
         "blocks_below_90_post", "infeasible_strict", "cost_vs_draft_pct"]]
    jt.to_csv(os.path.join(out_dir, "05_judges_table.csv"), index=False)
    print(pvd[["scenario", "plan", "cost", "ot_heads", "exp_missed_submitted", "exp_missed_post", "blocks_below_90_post", "infeasible_strict"]].round(1).to_string(index=False))

    # ---------------- stress test of the planning-week plans: demand x {0.96, 1.00, 1.04, 1.06}
    stress = []
    for setting, label in [("post80", "80%"), ("rec_post90", "90% (recommended)"), ("post95", "95%"), ("sub90", "90% no callout buffer"),
                           ("post90_q80", "90% at 80th pct")]:
        for scn in ("BASE", "PEAK", "DISRUPT"):
            ev = plans[(plans.setting == setting) & (plans.scenario_code == scn) & (plans.is_open == 1)]
            heads = {(r.store_id, r.day_date, r.shift_code, int(r.dept_id)): int(r.heads) for r in ev.itertuples()}
            for mult in (0.96, 1.00, 1.04, 1.06):
                blocks = build_blocks(grid, fc, base_rates, scn)
                blocks["demand"] = blocks.demand * mult; blocks["log_sd"] = 1e-6   # a realised week: no forecast spread
                evs = evaluate_plan(blocks, heads, params)
                oo = evs[evs.is_open == 1]
                stress.append(dict(setting=setting, plan=label, scenario=scn, demand_mult=mult, cost=float(oo.cost.sum()),
                                   exp_missed_submitted=float((1 - oo.p_meet_submitted).sum()), exp_missed_post=float((1 - oo.p_meet_post_callout).sum()),
                                   hit_rate_submitted=float(oo.p_meet_submitted.mean()), hit_rate_post=float(oo.p_meet_post_callout.mean())))
        # draft too
    for scn in ("BASE", "PEAK", "DISRUPT"):
        blocks0 = build_blocks(grid, fc, base_rates, scn)
        heads = {(r.store_id, r.day_date, r.shift_code, int(r.dept_id)): int(r.draft) for r in blocks0.itertuples()}
        for mult in (0.96, 1.00, 1.04, 1.06):
            blocks = blocks0.copy(); blocks["demand"] = blocks.demand * mult; blocks["log_sd"] = 1e-6
            evs = evaluate_plan(blocks, heads, params); oo = evs[evs.is_open == 1]
            stress.append(dict(setting="draft", plan="Draft", scenario=scn, demand_mult=mult, cost=float(oo.cost.sum()),
                               exp_missed_submitted=float((1 - oo.p_meet_submitted).sum()), exp_missed_post=float((1 - oo.p_meet_post_callout).sum()),
                               hit_rate_submitted=float(oo.p_meet_submitted.mean()), hit_rate_post=float(oo.p_meet_post_callout.mean())))
    stress = pd.DataFrame(stress); stress.to_csv(os.path.join(out_dir, "05_stress_test.csv"), index=False)
    print(f"   stress test done [{time.time()-t0:.0f}s]")

    # ---------------- B. historical backtest, leave-one-week-out
    d = daily_history(h)
    bt_all, blk_all = [], []
    for tau_bt, basis_bt in [(0.90, "post_callout"), (0.80, "post_callout"), (0.70, "post_callout"), (0.95, "post_callout"), (0.90, "submitted")]:
        weekly, blk_rows = backtest(h, d, params, tau_bt, basis_bt, t0)
        bwk = pd.DataFrame(weekly); bwk.insert(0, "basis", basis_bt); bwk.insert(0, "tau", tau_bt)
        blk = pd.DataFrame(blk_rows); blk.insert(0, "basis", basis_bt); blk.insert(0, "tau", tau_bt)
        bt_all.append(bwk); blk_all.append(blk)
    bwk = pd.concat(bt_all, ignore_index=True); blk = pd.concat(blk_all, ignore_index=True)
    bwk.to_csv(os.path.join(out_dir, "05_backtest_weekly.csv"), index=False)
    blk.to_csv(os.path.join(out_dir, "05_backtest_blocks.csv"), index=False)
    tots = []
    for (tau_bt, basis_bt), g in bwk.groupby(["tau", "basis"]):
        tot = g.drop(columns=["week", "tau", "basis"]).sum(numeric_only=True).to_dict()
        bb = blk[(blk.tau == tau_bt) & (blk.basis == basis_bt)]
        tot["forecast_wape"] = float(np.abs(bb.forecast_demand - bb.actual_demand).sum() / bb.actual_demand.sum())
        tot["mgr_hit_rate_realised"] = 1 - tot["mgr_missed_realised"] / tot["blocks"]
        tot["ours_hit_rate_model_post"] = 1 - tot["ours_exp_missed_model_post"] / tot["blocks"]
        tot["ours_hit_rate_model_sub"] = 1 - tot["ours_exp_missed_model_sub"] / tot["blocks"]
        tot["cost_change_pct_planned_plus_backfill"] = tot["ours_cost_incl_exp_backfill"] / tot["mgr_cost_realised"] - 1
        tot["cost_change_pct"] = tot["ours_cost_exp_realised"] / tot["mgr_cost_realised"] - 1
        # excluding the MLK week (week 3), whose holiday had no analog in the training weeks
        g3 = g[g.week != 3]; bb3 = bb[bb.week != 3]
        tot["excl_w3_mgr_cost"] = float(g3.mgr_cost_realised.sum()); tot["excl_w3_mgr_missed"] = int(g3.mgr_missed_realised.sum())
        tot["excl_w3_ours_cost_exp_realised"] = float(g3.ours_cost_exp_realised.sum()); tot["excl_w3_ours_exp_missed_post"] = float(g3.ours_exp_missed_model_post.sum())
        tot["excl_w3_cost_change_pct"] = tot["excl_w3_ours_cost_exp_realised"] / tot["excl_w3_mgr_cost"] - 1
        tot["tau"] = tau_bt; tot["basis"] = basis_bt
        tots.append(tot)
    tots = pd.DataFrame(tots); tots.to_csv(os.path.join(out_dir, "05_backtest_summary.csv"), index=False)
    print(f"   step 5 done in {time.time()-t0:.0f}s")
    return dict(plan_vs_draft=pvd, judges=jt, backtest_weekly=bwk, backtest_blocks=blk, backtest_total=tots, stress=stress)


def backtest(h, d, params, tau, basis, t0):
    weekly, blk_rows = [], []
    for w in range(1, 7):
        tw = time.time()
        tr = h[(h.week_idx != w)]
        # LOO service curve (same functional form, refit on the other five weeks)
        loo_params = {}
        fit_set = tr[(tr.is_open == 1) & tr.metric_value.notna() & (tr.utilization <= U_FIT_MAX)]
        for dept_id, x in fit_set.groupby("dept_id"):
            p, _ = fit_final(x, params[DEPT_SHORT[dept_id]]["model"]); p["target"] = params[DEPT_SHORT[dept_id]]["target"]; p["dept_id"] = int(dept_id)
            loo_params[DEPT_SHORT[dept_id]] = p
        # LOO forecast
        dtr = d[d.week_idx != w]; f = fit_daily(dtr); lv = weekly_levels(f)
        sd_week = float(lv.dev.std(ddof=1))
        test_days = d[(d.week_idx == w) & (d.is_costco_closed == 0)][["store_id", "dept_id", "day_date", "day_name", "holiday_window_role", "week_idx"]].copy()
        test_days["is_post_holiday_rebound"] = (test_days.day_date == pd.Timestamp("2026-01-20")).astype(int)
        pdaily = predict_daily(f, lv, test_days, level_mode="mean", valentine="low", role_fallback=ROLE_FALLBACK)
        sh = shift_shares(tr)
        # LOO callout rates (exclude flu cluster as in planning)
        cr = callout_rates(tr); cr = cr[cr.cat.isin(["weekday", "weekend", "post_holiday"])].set_index(["dept_id", "cat"]).rate
        # block table for week w from actual availability
        hw = h[(h.week_idx == w)].copy()
        hw["window"] = np.where(hw.holiday_window_role == "Normal", "Normal", "HolWin")
        hw = hw.merge(sh[["dept_id", "day_type", "window", "shift_code", "share", "share_sd"]], on=["dept_id", "day_type", "window", "shift_code"], how="left")
        hw = hw.merge(pdaily[["store_id", "dept_id", "day_date", "point"]], on=["store_id", "dept_id", "day_date"], how="left")
        hw["share"] = np.where(hw.is_open == 1, hw.share.fillna(0), 0.0); hw["share_sd"] = hw.share_sd.fillna(0)
        hw["demand"] = hw.point.fillna(0) * hw.share
        hw["log_sd"] = np.sqrt(sd_week ** 2 + np.where(hw.share > 0, (hw.share_sd / hw.share.replace(0, 1)) ** 2, 0)
                               + np.where(hw.holiday_window_role != "Normal", HOLIDAY_TRANSFER_SD ** 2, 0))
        hw["post_hol"] = hw.day_date.isin(pd.to_datetime(["2026-01-02", "2026-01-20"]))
        hw["cat"] = np.where(hw.post_hol, "post_holiday", np.where(hw.day_type == "Weekday", "weekday", "weekend"))
        hw["p_callout"] = [float(cr.get((dd, c), 0.05)) for dd, c in zip(hw.dept_id, hw.cat)]
        hw = hw.rename(columns={"available_regular_employees": "A", "max_overtime_employees": "O", "cross_trained_flex_employees": "F",
                                "paid_hours": "paid", "loaded_regular_hourly_cost": "rr", "loaded_overtime_hourly_cost": "ro",
                                "labor_hours_per_workload_unit": "std"})
        hw["open"] = hw.is_open.astype(int); hw["draft"] = hw.scheduled_employees; hw["scenario_code"] = f"HIST_w{w}"
        hw = hw.sort_values(["store_id", "day_date", "shift_seq", "dept_id"]).reset_index(drop=True)
        # our plan
        heads, models = {}, {}
        for (store, date, shift), trio in hw.groupby(["store_id", "day_date", "shift_code"], sort=False):
            res = optimize_trio(trio, loo_params, tau=tau, basis=basis)
            for dd, n in res["heads"].items():
                heads[(store, date, shift, dd)] = int(n)
            for dd, m in res["models"].items():
                models[(store, date, shift, dd)] = m
        # evaluate both plans against ACTUAL demand with the LOO curve
        for (store, date, shift), trio in hw.groupby(["store_id", "day_date", "shift_code"], sort=False):
            av = av_from_rows(trio)
            n_ours = {int(r.dept_id): heads[(store, date, shift, int(r.dept_id))] for r in trio.itertuples()}
            n_mgr = {int(r.dept_id): int(r.scheduled_employees) for r in trio.itertuples()}
            f_ours = fill_block(n_ours, av); f_mgr = fill_block(n_mgr, av)
            for r in trio.itertuples():
                dd = int(r.dept_id)
                if not r.open:
                    continue
                pdict = loo_params[r.dept]
                act = float(r.shift_demand_units)
                def p_actual(n, ot_used):
                    if n <= 0:
                        return 0.0, 0.0
                    ps = float(pmeet_u(pdict, act * r.std / (n * r.paid), int(store)))
                    wd = worked_dist(n, r.p_callout, BACKFILL_Q, max(0, av[dd]["O"] - ot_used))
                    pp = float(sum(pr * pmeet_u(pdict, act * r.std / (max(wk, 1) * r.paid), int(store)) if wk > 0 else 0.0 for wk, pr in wd))
                    return ps, pp
                ps_o, pp_o = p_actual(n_ours[dd], f_ours[dd]["ot"]); ps_m, pp_m = p_actual(n_mgr[dd], f_mgr[dd]["ot"])
                # expected backfill OT cost on top of the planned cost
                room_o = max(0, av[dd]["O"] - f_ours[dd]["ot"]); exp_bf_o = min(n_ours[dd] * r.p_callout * BACKFILL_Q, room_o)
                blk_rows.append(dict(week=w, store_id=int(store), dept=r.dept, day_date=date, shift_code=shift, actual_demand=act, forecast_demand=float(r.demand),
                                     mgr_scheduled=n_mgr[dd], mgr_worked=int(r.worked_employees), mgr_callouts=int(r.callout_employees),
                                     mgr_cost_realised=float(r.labor_cost), mgr_met_realised=int(r.met_target),
                                     mgr_p_submitted_model=ps_m, mgr_p_post_model=pp_m,
                                     ours_heads=n_ours[dd], ours_reg=f_ours[dd]["reg"], ours_flex=f_ours[dd]["flex"], ours_ot=f_ours[dd]["ot"],
                                     ours_cost=f_ours[dd]["cost"], ours_exp_backfill_cost=float(exp_bf_o * r.paid * r.ro),
                                     ours_exp_realised_cost=float(f_ours[dd]["cost"] * (1 - r.p_callout) + exp_bf_o * r.paid * r.ro),
                                     ours_p_submitted_model=ps_o, ours_p_post_model=pp_o, ours_infeasible=f_ours[dd]["infeasible_strict"],
                                     ours_u_actual=act * r.std / (n_ours[dd] * r.paid), mgr_u_actual=act * r.std / (n_mgr[dd] * r.paid)))
        bw = pd.DataFrame([b for b in blk_rows if b["week"] == w])
        weekly.append(dict(week=w, blocks=len(bw), forecast_wape=float(np.abs(bw.forecast_demand - bw.actual_demand).sum() / bw.actual_demand.sum()),
                           mgr_cost_realised=float(bw.mgr_cost_realised.sum()), mgr_missed_realised=int((bw.mgr_met_realised == 0).sum()),
                           mgr_exp_missed_model_sub=float((1 - bw.mgr_p_submitted_model).sum()), mgr_exp_missed_model_post=float((1 - bw.mgr_p_post_model).sum()),
                           ours_cost_planned=float(bw.ours_cost.sum()), ours_cost_incl_exp_backfill=float((bw.ours_cost + bw.ours_exp_backfill_cost).sum()),
                           ours_cost_exp_realised=float(bw.ours_exp_realised_cost.sum()),
                           ours_exp_missed_model_sub=float((1 - bw.ours_p_submitted_model).sum()), ours_exp_missed_model_post=float((1 - bw.ours_p_post_model).sum()),
                           ours_heads=int(bw.ours_heads.sum()), mgr_heads=int(bw.mgr_scheduled.sum()), ours_ot_heads=int(bw.ours_ot.sum()),
                           ours_infeasible=int(bw.ours_infeasible.sum())))
        print(f"   backtest tau={tau} {basis} week {w}: mgr cost ${weekly[-1]['mgr_cost_realised']:,.0f} missed {weekly[-1]['mgr_missed_realised']} (model {weekly[-1]['mgr_exp_missed_model_post']:.1f}) | "
              f"ours exp realised cost ${weekly[-1]['ours_cost_exp_realised']:,.0f} exp missed {weekly[-1]['ours_exp_missed_model_post']:.1f} | fc WAPE {100*weekly[-1]['forecast_wape']:.1f}% [{time.time()-tw:.0f}s]")
    return weekly, blk_rows


if __name__ == "__main__":
    res = run(sys.argv[1], sys.argv[2])
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(res["backtest_total"].round(3).T.to_string())
    print(res["stress"].round(2).to_string(index=False))
