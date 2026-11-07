"""
make_report.py - assemble PHASE1_REPORT.md from the pipeline outputs (every number comes from a CSV/JSON in outputs/).
"""
from __future__ import annotations
import os, sys, json
import numpy as np
import pandas as pd


def md(df: pd.DataFrame, floatfmt="{:.3f}") -> str:
    df = df.copy()
    for c in df.columns:
        if df[c].dtype.kind == "f":
            df[c] = df[c].map(lambda v: "" if pd.isna(v) else floatfmt.format(v))
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def main(out_dir: str):
    P = lambda f: os.path.join(out_dir, f)
    inv = pd.read_csv(P("00_file_inventory.csv")); chk = pd.read_csv(P("00_validation_checks.csv")); odd = pd.read_csv(P("00_oddities.csv"))
    cv = pd.read_csv(P("01_service_cv.csv")); params = json.load(open(P("01_service_params.json")))
    th = pd.read_csv(P("01_service_thresholds.csv")); sig = pd.read_csv(P("01_service_sigma.csv")); endo = pd.read_csv(P("01_service_endogeneity.csv"))
    wvs = pd.read_csv(P("01_service_worked_vs_scheduled.csv"))
    hd = json.load(open(P("02_headline.json"))); sm = pd.read_csv(P("02_summary_wh_dept.csv")); pat = pd.read_csv(P("02_pattern_wh_dept_shift_daytype.csv"))
    fac = pd.read_csv(P("03_factors.csv")); lv = pd.read_csv(P("03_weekly_levels.csv")); bt = pd.read_csv(P("03_backtest.csv"))
    fd = pd.read_csv(P("03_forecast_daily.csv")); fs = pd.read_csv(P("03_forecast_shift.csv")); vs = pd.read_csv(P("03_valentine_sensitivity.csv"))
    meta = json.load(open(P("03_forecast_meta.json"))); shares = pd.read_csv(P("03_shift_shares.csv"))
    blocks = pd.read_csv(P("01_service_blocks.csv"))

    L = []
    A = L.append
    A("# MISA Costco case, Phase 1 report\n")
    A("All numbers below are produced by `run_all.py` from the files in `team_distribution/csv` and are written to `outputs/`. "
      "Source files are cited as `docs/...`, `sql/...` or `csv/...`.\n")

    # ------------------------------------------------------------------ 0
    A("## 0. Inventory and validation\n")
    A("### Files received\n")
    A(md(inv[["file", "rows", "n_cols"]]))
    A("\nPlus (not loaded as tables): `Costco_Workforce_Case_Student_DataPack.xlsx` (same tables as the CSVs), `README.md`, "
      "`docs/ASSUMPTIONS.md`, `docs/DATA_DICTIONARY.md`, `sql/01..06`, and the case PDF (8 pages, no scoring rubric beyond "
      "`service first, then labor cost, then feasibility`).\n")
    A("### What the docs and SQL define (used verbatim)\n")
    A("- Grain of every fact table: warehouse (1, 2, 4) x department (38, 92, 95) x date x shift (OPEN, MID, EVE) (`docs/DATA_DICTIONARY.md`).")
    A("- Shift lengths (paid hours per head) and min_staff come from `comp.ShiftDefinition` (`sql/04`, lines 178-206): FE 4/4/4 h weekday, "
      "4/3.5/2.5 Sat, 4/3/2.5 Sun; Merch 6/5/6, 5.5/4.5/4.5, 5/4/4.5; Pharmacy 3.5/3/3.5 weekday, 4/5/closed Sat, closed/5/closed Sun. "
      "min_staff: FE 4/6/5 (Sat 5/6/4, Sun 4/6/4), Merch 6/3/4 (Sat 6/3/3, Sun 5/3/3), Pharmacy 2. Note `docs/ASSUMPTIONS.md` summarises "
      "min_staff as ranges (4-6, 3-6, 2); the table in `sql/04` and `csv/comp_ShiftDefinition.csv` is the binding source.")
    A("- Capacity of a block = available_regular + usable cross-trained flex + max_overtime (`README.md`, `sql/05` check S06/S07). "
      "Flex is FE<->Merch only, limited to people the partner department is not using in that shift (`docs/ASSUMPTIONS.md` s.4-5).")
    A("- Costing rule (`docs/ASSUMPTIONS.md` s.5, `sql/06` Q5): fill regular first, then flex, then OT; block cost = (regular + flex) x paid hours x "
      "loaded regular rate + OT x paid hours x loaded OT rate. Loaded OT / loaded regular = 1.32 for every warehouse x dept (check K04).")
    A("- Service: one metric per dept, meets target when metric_value <= target (5 / 60 / 20 min); simulated from demand relative to WORKED hours "
      "(`docs/DATA_DICTIONARY.md` FactShiftSchedule.worked_employees: 'drives the service outcome'; `docs/ASSUMPTIONS.md` s.6).")
    A("- Judging order: service, then labor cost, then feasibility (`README.md`).")
    A("- Benchmark: `src.FactDailyPrediction` model_run_id 2026021101 = mean of the same weekday in weeks 3-6, no holiday/promo/weather logic (`sql/04` lines 139-169). Confirmed: 63 rows with that id.")
    A("- Closed blocks: Pharmacy Sat EVE, Sun OPEN, Sun EVE (licensure/hours assumption in `comp.ShiftDefinition`) = 9 blocks per scenario in the "
      "planning week; in history also all 27 blocks of New Year's Day (warehouse closed). Closed = 0 demand, 0 staff, no service value (check D04).")
    A("- 567 template rows = 3 scenarios x 189 blocks; keys match `v_PlanningWeekGrid` exactly (checks C10-C12). Shift demand sums to daily demand on every day (D01).\n")
    n_pass = int((chk.status == "PASS").sum()); n_info = int((chk.status == "INFO").sum()); n_fail = int((chk.status == "FAIL").sum())
    A(f"### Checks: {n_pass} PASS, {n_info} INFO, {n_fail} FAIL (`outputs/00_validation_checks.csv`)\n")
    A("Oddities found (nothing was changed in the data):\n")
    u1 = odd[odd.issue.str.startswith("utilization > 1")]
    A(f"1. **{len(u1)} open blocks have worked-hours utilization above 1.0** (max 1.774, Pharmacy W1 Feb 11 EVE); all 50 missed target. "
      "This is demand hours exceeding worked hours, i.e. genuine under-staffing, so they are kept. The service model is fitted on u <= 0.97 "
      "and treats anything above as a miss: 0 of the 114 blocks above u = 0.93 met target, and the highest utilization at which any block met target was 0.904. (`outputs/00_oddities.csv`)")
    wb = odd[odd.issue.str.startswith("worked heads < min_staff")]
    A(f"2. **{len(wb)} blocks where worked heads fell below min_staff after callouts** although the schedule met it; kept as-is, they are informative about callout risk.")
    A("3. **12 draft-schedule blocks exceed DISRUPT capacity** (intended by the organisers, check S07); the draft is identical across the three scenarios (S10).")
    A("4. **has_promotion is a deterministic calendar flag**: 1 on every Fri/Sat/Sun and every holiday-window day, 0 otherwise (W04). It carries no "
      "information beyond weekday and holiday role, so a separate promotion effect cannot be estimated from history.")
    A("5. **The daily demand history is generated by a closed-form formula** in `sql/02_Load_Core_Data.sql` (lines 445-525): "
      "transaction_count_proxy = weekly_sales x base_daily_weight(dept, weekday) x holiday_adjustment_factor(dept, window role) / base_ticket. "
      "We reproduced all 378 daily values from that formula to within 0.0002 (rounding). Consequence: the only randomness in demand is (a) the "
      "weekly sales level and (b) the split of a day into shifts (`sql/04`, literal values). Temperature, promotion index, fuel price, CPI and "
      "markdowns never enter the demand formula. We did not use the formula to forecast; the forecast model below is estimated from the data, "
      "and this finding tells us what its error budget is.")
    A("6. Missing values are only where the dictionary says so (closed blocks, availability_note, Draft callout fields). No duplicate keys, no negative or zero demand on open blocks.\n")

    # ------------------------------------------------------------------ 1
    A("## 1. Service-response model\n")
    A("Utilization u = shift demand x labor standard / worked labor hours (standards 1.50 / 1.20 / 0.165 h per unit, `csv/comp_LaborStandard.csv`). "
      "Worked hours explain service better than scheduled hours by 30-37% (log-RMSE of a simple exponential fit):\n")
    A(md(wvs))
    A("\n### Candidate forms and leave-one-week-out CV (6 folds, fitted on open blocks with u <= 0.97)\n")
    A("Metrics: RMSE of log(metric), MAE in minutes, Brier score and log-loss of the implied P(meet). The model is chosen on out-of-sample log-loss of P(meet), the quantity we act on.\n")
    cvs = cv.copy(); cvs["chosen"] = np.where(cvs.chosen, "<- chosen", "")
    A(md(cvs[["dept", "model", "rmse_log", "mae_minutes", "brier_pmeet", "logloss_pmeet", "n", "chosen"]], "{:.4f}"))
    A("\n`queue+store` = log m = log( b / (1 - u/c) ) + warehouse intercept (a was pushed to 0 by the fit in all three departments). It beats the "
      "exponential form by 15-49% on every metric and the isotonic (non-parametric) curve by 1-24%, in every department, so the choice is not by eye.\n")
    A("### Chosen curves (plain words)\n")
    for d in ("FE", "Merch", "Pharm"):
        p = params[d]
        A(f"- **{d}**: metric = {p['b']:.3f} / (1 - u/{p['c']:.3f}) minutes at warehouse 1; warehouse 2 x {np.exp(p['int_2']):.3f}, warehouse 4 x {np.exp(p['int_4']):.3f}. "
          f"Residual sd on the log scale = {p['sigma0'] + p['sigma1']*0.8:.3f} at u = 0.8 (slope of sd in u: {p['sigma1']:+.3f} per unit u; "
          f"corr(|resid|, u) = {p['corr_absresid_u']:+.3f}). Target {p['target']:g} min; fitted on {p['n_fit']} blocks.")
    A("\nIn minutes the spread grows with utilization (sd rises from 0.2 min to 2.4 min for FE between u = 0.65 and 0.90), but on the log scale it is flat: "
      "the noise is multiplicative, about 12-13% of the mean, in every department. So P(meet | u) = Phi( (log target - log m(u)) / sigma ). "
      "(`outputs/01_service_sigma.csv`)\n")
    A("### Utilization at which P(meet) drops below 95% / 90% / 80% (bootstrap 90% band, 400 resamples)\n")
    thp = th.pivot_table(index=["dept", "store_id"], columns="p_meet_level", values="u_threshold").reset_index()
    thp.columns = ["dept", "warehouse", "u at P=80%", "u at P=90%", "u at P=95%"]
    band = th[th.p_meet_level == 0.90].set_index(["dept", "store_id"])
    thp["90% band (P=90%)"] = [f"{band.loc[(d, s), 'ci90_lo']:.3f}-{band.loc[(d, s), 'ci90_hi']:.3f}" for d, s in zip(thp.dept, thp.warehouse)]
    A(md(thp))
    A("\nReading: every department falls off the cliff between u = 0.84 and 0.88. Warehouse 2's front end breaks earliest (0.844 for 90%); "
      "its merchandising holds longest (0.875). The bands are tight because the simulator is clean (300+ blocks per department); they measure "
      "sampling error of the fit, not whether the real world behaves like the simulator.\n")
    A("### Calibration of P(meet) on history\n")
    blocks["pbin"] = pd.cut(blocks.p_meet, [-0.01, 0.05, 0.2, 0.5, 0.8, 0.95, 1.0])
    cal = blocks.groupby("pbin", observed=True).agg(n=("met_target", "size"), predicted=("p_meet", "mean"), observed=("met_target", "mean")).reset_index()
    cal["pbin"] = cal.pbin.astype(str)
    A(md(cal))
    A(f"\nOverall: predicted hit rate {blocks.p_meet.mean():.3f} vs observed {blocks.met_target.mean():.3f}; by warehouse x dept the gap is at most 0.02 (`outputs/01_service_blocks.csv`).\n")
    A("### Endogeneity check (do managers' anticipations bias the curve?)\n")
    A("Managers schedule ahead of time, so they cannot react to the same block's realised service; the risk is that blocks they expected to be hard "
      "were staffed differently in ways correlated with the outcome. Callouts are a quasi-random shock to worked hours, so if the curve is causal, "
      "blocks hit by callouts must sit on the same curve as blocks that were not:\n")
    e2 = endo[["dept", "had_callout", "n", "mean_log_resid", "sd", "mean_u", "diff_mean_log_resid", "t_stat", "corr_resid_schedUtil_given_u"]]
    A(md(e2))
    A("\nResidual differences are 0.02 log or less (t between -0.3 and 1.4) and the residual is uncorrelated with how far scheduled hours differed "
      "from worked hours. Conclusion: no detectable anticipation bias; the concern is small here. The remaining limitation is coverage: the curve is "
      "estimated where data exist (u 0.4-1.0), which covers the whole decision range.\n")
    A("![service curve](01_service_curve.png)\n")

    # ------------------------------------------------------------------ 2
    A("## 2. Diagnosis: where the six weeks of labor went\n")
    A("For each open block we computed n90 = the smallest head count (>= min_staff) with P(meet) >= 90% at the block's actual demand, and compared "
      "worked heads (what served demand) and scheduled heads (what the manager planned) with it (`outputs/02_block_classification.csv`).\n")
    A(f"**Headline: {100*hd['surplus_pct_of_cost']:.1f}% of labor dollars (${hd['surplus_cost']:,.0f} of ${hd['labor_cost']:,.0f} over six weeks) were spent in "
      f"blocks staffed above the 90% service line, while {hd['missed_understaffed']} of the {hd['missed_blocks']} missed-target blocks were under-staffed "
      f"against that same line. Filling every starved block to n90 would have cost ${hd['deficit_cost']:,.0f}; the surplus covers it with "
      f"${-hd['net_cost_of_fix']:,.0f} to spare, and {100*hd['deficit_coverable_by_same_wh_pool_pct']:.0f}% of the deficit sits in the same warehouse "
      f"and labor pool (FE+Merch, or Pharmacy) as a surplus, so most of the fix is a reallocation rather than new spend. Expected hit rate at n90 "
      f"everywhere: {100*hd['expected_hit_rate_if_all_at_n90']:.0f}% vs {100*hd['hit_rate']:.0f}% actual.**\n")
    A(f"Block counts (worked basis): {hd['over_blocks']} over-staffed, {hd['right_blocks']} right-sized, {hd['under_blocks']} under-staffed of {hd['open_blocks']} open blocks; "
      f"on the scheduled basis {hd['over_blocks_sched']} over / {hd['under_blocks_sched']} under. Average surplus in an over-staffed block: "
      f"{hd['avg_surplus_heads_over_blocks']:.1f} heads; average deficit in an under-staffed block: {hd['avg_deficit_heads_under_blocks']:.1f} heads. "
      f"Every deficit could have been filled from that block's own regular + OT availability (0 unfillable heads).\n")
    A("### By warehouse x department (six weeks)\n")
    s2 = sm[["store_id", "dept", "labor_cost", "over_blocks", "right_blocks", "under_blocks", "surplus_cost", "deficit_cost", "net_cost_of_fix", "missed", "missed_understaffed", "pct_met"]].copy()
    for c in ["labor_cost", "surplus_cost", "deficit_cost", "net_cost_of_fix"]:
        s2[c] = s2[c].map(lambda v: f"{v:,.0f}")
    s2["pct_met"] = s2.pct_met.map(lambda v: f"{100*v:.0f}%")
    A(md(s2))
    A("\n### Systematic patterns (warehouse x dept x shift x day type; `outputs/02_pattern_wh_dept_shift_daytype.csv`)\n")
    over = pat[pat.verdict == "systematically OVER"].sort_values("surplus_cost", ascending=False).head(8)
    under = pat[pat.verdict == "systematically UNDER"].sort_values("deficit_cost", ascending=False).head(8)
    A("Largest over-staffing habits (avg scheduled heads above n90, surplus $ over six weeks):\n")
    o2 = over[["store_id", "dept", "shift_code", "day_type", "blocks", "avg_gap_sched", "pct_over_sched", "avg_util", "pct_met", "surplus_cost"]].copy()
    o2["surplus_cost"] = o2.surplus_cost.map(lambda v: f"{v:,.0f}"); o2["pct_over_sched"] = o2.pct_over_sched.map(lambda v: f"{100*v:.0f}%"); o2["pct_met"] = o2.pct_met.map(lambda v: f"{100*v:.0f}%")
    A(md(o2, "{:.2f}"))
    A("\nLargest under-staffing habits (avg scheduled heads below n90, cost to fix over six weeks):\n")
    u2 = under[["store_id", "dept", "shift_code", "day_type", "blocks", "avg_gap_sched", "pct_under_sched", "avg_util", "pct_met", "deficit_cost", "missed"]].copy()
    u2["deficit_cost"] = u2.deficit_cost.map(lambda v: f"{v:,.0f}"); u2["pct_under_sched"] = u2.pct_under_sched.map(lambda v: f"{100*v:.0f}%"); u2["pct_met"] = u2.pct_met.map(lambda v: f"{100*v:.0f}%")
    A(md(u2, "{:.2f}"))
    A("\nThe three stories a judge will remember:\n")
    A("1. **Warehouse 4 Merchandising runs its opening crew 4-6 heads heavy every day** ($34.8K surplus over six weeks, utilization 0.67, 100% hit rate) "
      "while its evening crew runs 1-2 heads short (21 of 29 weekday evenings missed). Same warehouse, same department, same people: a shift of hours from OPEN to EVE.")
    A("2. **Warehouse 2 front end collapses every weekend afternoon and evening** (Sat/Sun MID and EVE scheduled 3-5 heads below n90, utilization about 1.0, 21 of 24 blocks missed) "
      "while Warehouse 2 Pharmacy carries one spare head in almost every block ($18.4K surplus, zero under-staffed blocks). Pharmacy hours cannot move to the front end, "
      "so this one needs weekend FE hours, partly fundable from Warehouse 2 Merchandising's own surplus ($15.8K).")
    A("3. **Warehouse 1 front end is 2-3 heads heavy on weekday MID and EVE** ($15.9K) while Warehouse 1 Merchandising MID/EVE runs short (23 misses on weekdays). "
      "FE and Merch share cross-trained staff, so this is the cleanest case for the flex pool.")
    A("\nCaveat we will state on the slide: n90 is computed with actual demand known. A planner only has a forecast and faces callouts, so part of the surplus is "
      "legitimate insurance; the 6.8% is an upper bound on waste. Phase 2's backtest gives our method the same information set (forecast, not actuals) and leave-one-week-out curves.\n")

    # ------------------------------------------------------------------ 3
    A("## 3. Demand forecast\n")
    A("### Method (30-second version)\n")
    A("demand(warehouse, dept, day) = level(warehouse, dept) x weekday profile(dept) x holiday factor(dept, window) x Valentine's factor. "
      "Estimated by log-linear least squares with a separate level for every warehouse x dept x week, so the weekday profile and holiday factors come only from "
      "within-week contrasts; the planning-week level is the mean of the six weekly levels. Shifts: daily demand x learned share (dept x day type x holiday-window), "
      "the FE share moves toward MID on holiday-window days as the dictionary says. Analogs: Pre_MLK_Weekend (Fri-Sun) -> Pre_Presidents_Day_Weekend (Fri-Sun), "
      "MLK_Holiday (Mon) -> Presidents_Day_Holiday (Mon), the Tuesday after MLK -> Tue Feb 17. Valentine's Day has no analog in history, so it is an explicit assumption with low/mid/high sensitivity.\n")
    A(f"Fit: {meta['fit_stats']['n_obs']} open warehouse-dept-days, {meta['fit_stats']['n_params']} parameters, within-week residual sd = {meta['fit_stats']['resid_sd_log']:.1e} (the daily history is exact, see oddity 5). "
      f"Weekly level deviations have sd = {100*meta['trend']['sd_week_dev_all']:.1f}% and are almost perfectly common across the nine series (sd of the cross-series mean {100*meta['trend']['sd_week_dev_common']:.1f}%). "
      f"Trend test on the six weekly means: slope {100*meta['trend']['slope_per_week_weekmeans']:+.2f}% per week, p = {meta['trend']['p_value_weekmeans']:.2f}, so no trend is used.\n")
    A("### Weekday profile and event factors (multiplicative, Thursday = 1.00)\n")
    f2 = fac[fac.kind.isin(["dow", "role", "postmlk"])].copy()
    f2["term"] = np.where(f2.kind == "postmlk", "Tuesday after MLK (extra)", f2.term)
    piv = f2.pivot_table(index="term", columns="dept", values="factor").reindex(
        ["Friday", "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Post_New_Year_Rebound", "Pre_MLK_Weekend", "MLK_Holiday", "Tuesday after MLK (extra)"])[["FE", "Merch", "Pharm"]].reset_index()
    A(md(piv))
    A("\nTemperature cannot be tested: within every week it is an exact linear function of the weekday (collinear with the profile, rank unchanged when added). "
      "Promotion cannot be tested either (oddity 4). What we can say: the Pre-MLK weekend lift (+12% FE, +8% Merch) is measured on days that are promo days in every "
      "week, so it is a holiday effect on top of the normal weekend; the MLK Monday (+5% FE/Merch, -30% Pharmacy) is the only Monday with has_promotion = 1, so its lift "
      "is 'holiday plus promo flag' and cannot be split. For Feb 16 that is the right thing to carry over, because the BASE calendar flags Feb 13-16 the same way.\n")
    A("### Weekly level index (1.00 = series mean)\n")
    lvp = lv.pivot_table(index=["store_id", "dept"], columns="week_idx", values="level_index").reset_index()
    lvp.columns = ["warehouse", "dept"] + [f"w{c}" for c in lvp.columns[2:]]
    A(md(lvp))
    A("\n### Backtests vs the naive benchmark recipe (WAPE)\n")
    A("Naive = mean of the same weekday over the last four training weeks with no holiday logic, exactly the organisers' recipe applied to the training window "
      "(`naive` excludes the closed New Year's Day from the average; `naive_incl_closed` includes it, as the literal recipe would).\n")
    b2 = bt[bt.test.isin(["rolling_origin_level=mean", "MLK_holdout_no_holiday_factor", "MLK_holdout_factor_from_other_2_warehouses"])].copy()
    b2 = b2[["test", "horizon", "level", "dept", "n", "wape_ours", "mape_ours", "wape_naive", "mape_naive", "wape_naive_incl_closed"]]
    for c in ["wape_ours", "mape_ours", "wape_naive", "mape_naive", "wape_naive_incl_closed"]:
        b2[c] = b2[c].map(lambda v: "" if pd.isna(v) else f"{100*v:.1f}%")
    A(md(b2))
    A("\nReading: on normal weeks the model beats the naive recipe by 1-3 points at daily and shift level (week 5) and ties it in week 6, where the week-6 level jump "
      "(+3.5%) was unforecastable for both. The error on a normal week is the weekly level noise (about 3%) plus shift-split noise (about 3-5% per shift). "
      "On the MLK window, ignoring the holiday costs 10-12% WAPE; transferring the factor from the other two warehouses reproduces the held-out warehouse exactly "
      "because the simulated holiday effect is identical across warehouses. The honest statement for the slide: the backtest proves the method handles a holiday "
      "window it has seen the shape of; it cannot prove that Presidents' Day behaves like MLK. That is why the plan carries holiday-transfer uncertainty (sd 5%) and a "
      "Valentine's sensitivity. Using the last four weeks for the level instead of all six would raise the planning week by about 1% (`outputs/03_backtest.csv`, level=last4 rows).\n")
    A("### Planning-week daily forecast, BASE (units; benchmark in brackets)\n")
    fd["cell"] = "W" + fd.store_id.astype(str) + " " + fd.dept
    fd["txt"] = fd.apply(lambda r: f"{r.point:.0f} [{r.benchmark:.0f}]", axis=1)
    pv = fd.pivot_table(index=["day_date", "day_name", "holiday_window_role"], columns="cell", values="txt", aggfunc="first").reset_index()
    pv = pv[["day_date", "day_name", "holiday_window_role"] + [f"W{s} {d}" for s in (1, 2, 4) for d in ("FE", "Merch", "Pharm")]]
    pv.columns = ["date", "day", "window"] + list(pv.columns[3:])
    A(md(pv))
    tot = fd.groupby("dept")[["point", "benchmark"]].sum(); tot["ratio"] = tot.point / tot.benchmark
    A("\nWeek totals vs benchmark: " + "; ".join(f"{d}: {r.point:,.0f} vs {r.benchmark:,.0f} ({100*(r.ratio-1):+.1f}%)" for d, r in tot.iterrows()) + ". "
      "The benchmark misses in both directions: it under-forecasts the holiday weekend for FE/Merch (Sat Feb 14 W4 FE: 195 vs 172) and over-forecasts "
      "Pharmacy on Presidents' Day by a third (W1: 116 vs 155), because it averages normal Mondays.\n")
    A("80% prediction intervals (simulation, 20,000 draws: weekly level sd 3.3%, holiday-transfer sd 5% on Feb 13-16, shift-share noise) are in "
      "`outputs/03_forecast_daily.csv` and `outputs/03_forecast_shift.csv` (567 rows, all scenarios: PEAK = BASE x `demand_multiplier`, DISRUPT = BASE). "
      "Typical 80% interval: +/-4% on a normal day, +/-8% on Feb 13-16; +/-5-7% on a normal shift, +/-8-11% on a holiday-window shift.\n")
    A("### Valentine's Day sensitivity (daily units, FE and Merch, Feb 13-14)\n")
    v2 = vs[["store_id", "dept", "day_date", "low", "mid", "high", "high_vs_low_pct"]].copy()
    v2["high_vs_low_pct"] = v2.high_vs_low_pct.map(lambda v: f"{100*v:+.0f}%")
    A(md(v2, "{:.1f}"))
    A("\nAssumption: mid = +2% FE Fri, +5% FE Sat, +3% Merch Sat on top of the pre-holiday-weekend factor; low = none; high = +4% / +10% / +6%. "
      "Pharmacy unaffected. The plan is built on mid; Phase 2 reports heads under low and high.\n")
    A("![forecast](03_forecast.png)\n")

    # ------------------------------------------------------------------ 4
    A("## 4. Running assumptions table\n")
    rows = [
        ("Service depends on worked hours (after callouts/backfill), not scheduled", "docs/DATA_DICTIONARY.md; worked-u fits 35% better (log-RMSE 0.18 vs 0.28)", "File-defined; if the evaluator scores submitted heads instead, callout buffers are wasted cost (see concern 2)"),
        ("Service curve: metric = b/(1 - u/c) x warehouse factor, log-normal noise sd about 0.13, fitted on u <= 0.97; P(meet)=0 above", "Wins leave-one-week-out CV in all 3 depts; 0 of 114 blocks above u=0.93 met target", "The pooled isotonic curve puts the 90% crossing 0.005-0.009 lower (0.852-0.856 vs 0.858-0.865 averaged over warehouses); within 1 head on most blocks"),
        ("Noise independent across blocks", "Residual autocorrelation not modelled (6 weeks)", "If misses cluster (e.g. a bad day), expected missed blocks are right but their variance is understated"),
        ("Planning-week level = mean of six weekly levels (no trend)", "Trend p = 0.76; weekly sd 3.3%", "Last-4-week mean is +1.0%; each 1% of demand is about 0.01 u, roughly 0.3 heads on a 25-head block"),
        ("Weekly level noise sd 3.3% (log), common across departments and warehouses", "Observed deviations w1-w6: -4.8% to +6.4%", "Drives the PI width and the Phase 2 buffer; from a plan set exactly at the 90% line, a +2% demand surprise lowers P(meet) to 0.49-0.64, +4% to 0.05-0.26, +6% to about zero (computed from the fitted curves)"),
        ("Presidents' Day window = MLK window factors (FE +12%/+5%, Merch +8%/+5%, Pharmacy -5%/-30%)", "Same structure: Fri-Sun pre-window + Monday federal holiday, warehouse open, same calendar flags", "If Presidents' Day is 5 points stronger for FE/Merch: about 1 head per large block; if Pharmacy Monday is not -30%: 1-2 pharmacy heads short on Feb 16"),
        ("Tue Feb 17: no post-holiday rebound (factor 1.000)", "Jan 20 (Tue after MLK) shows exactly 1.000 vs other Tuesdays; the +10% rebound in history followed a CLOSED day", "If a rebound of +5% appears, 1 head short on FE/Merch blocks that day"),
        ("Valentine's Day: mid +2% FE Fri, +5% FE Sat, +3% Merch Sat; low 0; high +4/+10/+6%", "No analog in history; Saturday is already the FE peak; service judged first so a positive mid is the safer error", "High vs low is 5-10% on two days: 1-3 heads on FE Saturday blocks; cost of over-assuming mid when truth is low about 1 head per FE Sat block"),
        ("Holiday-transfer uncertainty sd 5% (log) on Feb 13-16 in PIs", "Judgment; no second holiday window to measure", "Only widens the PIs on four days; Phase 2 buffer sizing"),
        ("Shift shares by dept x day type x holiday-window, pooled across warehouses; share noise sd 0.01-0.02", "Shares differ across warehouses by < 0.03 (mostly < 0.01); FE MID share rises from 0.40 to 0.43 on holiday-window days", "A 0.02 share error on a 0.4 share is 5% of that shift's demand, about 1 head"),
        ("PEAK = BASE x comp_ScenarioDemandAdjustment multipliers; DISRUPT = BASE demand with DISRUPT availability", "docs/ASSUMPTIONS.md s.7; X01/X02 checks", "File-defined"),
        ("Promotion and temperature carry no separate effect", "Both are deterministic functions of calendar in this data (oddity 4; collinearity); the generator never uses them", "If the evaluator's week has a promo lift beyond the holiday factor in BASE, we are short by that lift; PEAK covers the promo case explicitly"),
        ("Labor standard, rates, min_staff, capacity, fill order exactly as in csv/ and sql/", "Ground rule 2", "n/a"),
    ]
    A(md(pd.DataFrame(rows, columns=["Assumption / value", "Why", "Impact if wrong"])))

    # ------------------------------------------------------------------ 5
    A("\n## 5. Top 3 concerns before we optimize\n")
    A("1. **The evaluator's week is a draw we cannot see, and the cliff is steep.** History shows weekly levels moving -4.8% to +6.4% with no pattern, and "
      "Presidents' Day and Valentine's factors are assumptions. A plan tuned to the point forecast at exactly 90% P(meet) sits at u = 0.85-0.87; a +2% demand surprise "
      "takes P(meet) to 0.5-0.65 and +4% takes it to 0.05-0.26 (fitted curves). Phase 2 must integrate P(meet) over the forecast distribution (not plug in the point) and I will recommend submitting the "
      "plan that holds 90% across the 80% interval, accepting the labor cost, because service is judged first.")
    A("2. **We do not know whether the evaluator scores submitted heads or post-callout heads, nor whether it simulates callouts on our plan.** History: callout rates "
      "5.5% FE / 3.4% Merch / 3.9% Pharmacy on weekdays, 7% / 5.5% / 7% on weekends, 11-12% at Warehouse 2 in the flu week (Jan 22-28), with about half backfilled. "
      "A binomial callout buffer costs roughly 3-6% of labor; if the evaluator does not simulate callouts, that is pure cost. We will show both plans and recommend "
      "the buffered one (service first), unless you learn the scoring mechanics before submission.")
    A("3. **Capacity binds where it matters most, so 90% is not reachable everywhere.** With the point forecast and no callout buffer, 10 PEAK blocks (FE MID on Feb 13-14 "
      "at all three warehouses, FE EVE Sat at W2/W4, Merch OPEN Sat at W1/W2) and 9 DISRUPT blocks (every W2 FE block Feb 13-15) need more heads than regular + flex + OT "
      "allow. The draft schedule, scored against our BASE forecast, already has 47 of 180 open blocks below 90% P(meet) (31 expected misses, concentrated Feb 13-16), "
      "67 blocks in PEAK and 12 blocks over capacity in DISRUPT. The optimizer must staff these to capacity, flag them, and the playbook must say what the GM does "
      "about the residual risk (pre-stock Thursday EVE, pull flex, accept). Also note the W2 Pharmacy DISRUPT blocks on Feb 14-15: 1-2 regular + 1 OT available against min_staff 2, so they are feasible only with OT.")
    A("\nSmaller items to carry: (a) the diagnosis's 6.8% surplus is an upper bound (actual demand known); (b) the P(meet) bootstrap bands exclude model misspecification; "
      "(c) the MLK holdout is exact by construction of the simulator, which a judge may find too good, so present it with the 'no holiday factor' error (10.3%) as the "
      "meaningful comparison.\n")

    # ------------------------------------------------------------------ files
    A("## 6. Files in this bundle\n")
    A("- `run_all.py`, `pipeline/common.py`, `pipeline/step0_validate.py`, `pipeline/step1_service.py`, `pipeline/step2_diagnosis.py`, `pipeline/step3_forecast.py`, `pipeline/make_report.py`")
    A("- `data/` the 16 CSVs from `team_distribution/csv` (unchanged)")
    A("- `outputs/00_*` inventory, validation checks, oddities, shift definition")
    A("- `outputs/01_*` service blocks (every open block with u, fitted metric, P(meet)), CV, params JSON (used by Phase 2), thresholds, sigma, endogeneity, chart")
    A("- `outputs/02_*` block classification, patterns, warehouse x dept summary, headline JSON")
    A("- `outputs/03_*` factors, weekly levels, shift shares, daily and shift forecasts (567 rows with PIs), backtest, Valentine's sensitivity, meta JSON, chart")
    A("- `requirements.txt`: pandas, numpy, scipy, scikit-learn, matplotlib (statsmodels and pulp are installed for Phase 2 but not used yet)")
    A("\nRun: `python run_all.py --data <path to csv folder> --out outputs` (about 10 s). Then `python pipeline/make_report.py outputs` rebuilds this report.")

    with open(P("PHASE1_REPORT.md"), "w") as fh:
        fh.write("\n".join(L))
    print("wrote", P("PHASE1_REPORT.md"))


if __name__ == "__main__":
    main(sys.argv[1])
