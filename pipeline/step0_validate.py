"""
step0_validate.py - Inventory and validation (Phase 1, Step 0).

Writes:
  outputs/00_file_inventory.csv      one row per file: rows, columns
  outputs/00_validation_checks.csv   PASS/FAIL/INFO checks (mirrors sql/05_Validation_Checks.sql
                                     plus the extra oddity checks asked for in the prompt)
  outputs/00_oddities.csv            every row-level oddity found (nothing is fixed)
"""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from common import load_all, hist_frame, planning_grid, KEY, day_type_of


def run(data_dir: str, out_dir: str) -> dict:
    tabs = load_all(data_dir)
    checks, odd = [], []

    def chk(cid, area, name, expected, actual, status):
        checks.append(dict(check_id=cid, area=area, check=name, expected=expected,
                           actual=actual, status=status))

    # ---------------- inventory
    inv = []
    for k, df in tabs.items():
        inv.append(dict(file=k + ".csv", rows=len(df), n_cols=df.shape[1], columns="|".join(df.columns)))
    inv = pd.DataFrame(inv)
    inv.to_csv(os.path.join(out_dir, "00_file_inventory.csv"), index=False)

    dem = tabs["comp_FactShiftDemand"]; sch = tabs["comp_FactShiftSchedule"]
    av = tabs["comp_FactShiftAvailability"]; sl = tabs["comp_FactShiftServiceLevel"]
    sda = tabs["comp_ScenarioDemandAdjustment"]; sd = tabs["comp_ShiftDefinition"]
    tpl = tabs["TEAM_SUBMISSION_TEMPLATE"]; grid = tabs["v_PlanningWeekGrid"]
    hist = tabs["v_ShiftHistory"]; bench = tabs["PlanningWeek_BenchmarkForecast"]
    lc = tabs["comp_LaborCostAssumption"]

    # ---------------- completeness (C01-C09 analogues)
    chk("C01", "Completeness", "Historical shift-demand grid = 3 x 3 x 42 x 3", 1134, len(dem),
        "PASS" if len(dem) == 1134 else "FAIL")
    a = (sch.schedule_type == "Actual").sum(); d = (sch.schedule_type == "Draft").sum()
    chk("C03", "Completeness", "Schedules: Actual / Draft rows", "1134 / 189", f"{a} / {d}",
        "PASS" if (a, d) == (1134, 189) else "FAIL")
    cnt = av.scenario_id.value_counts().to_dict()
    chk("C04", "Completeness", "Availability rows HIST/BASE/PEAK/DISRUPT", "1134/189/189/189",
        "/".join(str(cnt.get(i, 0)) for i in (0, 1, 2, 3)),
        "PASS" if [cnt.get(i, 0) for i in (0, 1, 2, 3)] == [1134, 189, 189, 189] else "FAIL")
    chk("C05", "Completeness", "Service rows / scenario demand adjustments", "1134 / 567", f"{len(sl)} / {len(sda)}",
        "PASS" if (len(sl), len(sda)) == (1134, 567) else "FAIL")
    chk("C06", "Completeness", "Reference tables: shifts/shift defs/standards/metrics/cost rows/scenarios", "3/27/3/3/9/4",
        f"{len(tabs['comp_DimShift'])}/{len(sd)}/{len(tabs['comp_LaborStandard'])}/{len(tabs['comp_ServiceMetricDefinition'])}/{len(lc)}/{len(tabs['comp_Scenario'])}",
        "PASS" if (len(tabs['comp_DimShift']), len(sd), len(tabs['comp_LaborStandard']),
                   len(tabs['comp_ServiceMetricDefinition']), len(lc), len(tabs['comp_Scenario'])) == (3, 27, 3, 3, 9, 4) else "FAIL")
    chk("C08", "Completeness", "Views: v_ShiftHistory / v_PlanningWeekGrid rows", "1134 / 567", f"{len(hist)} / {len(grid)}",
        "PASS" if (len(hist), len(grid)) == (1134, 567) else "FAIL")
    nb = (bench.model_run_id == 2026021101).sum()
    chk("C09", "Completeness", "Benchmark rows with model_run_id 2026021101", 63, int(nb), "PASS" if nb == 63 else "FAIL")
    chk("C10", "Completeness", "Template rows = 3 scenarios x 189 blocks", 567, len(tpl), "PASS" if len(tpl) == 567 else "FAIL")
    blocks_per_scn = tpl.groupby("scenario_code").size().to_dict()
    chk("C11", "Completeness", "Template blocks per scenario", "189 each", str(blocks_per_scn),
        "PASS" if all(v == 189 for v in blocks_per_scn.values()) else "FAIL")
    # template keys match grid keys
    tk = set(map(tuple, tpl[["scenario_id", "store_id", "dept_id", "day_date", "shift_code"]].astype(str).values))
    gk = set(map(tuple, grid[["scenario_id", "store_id", "dept_id", "day_date", "shift_code"]].astype(str).values))
    chk("C12", "Completeness", "Template keys == PlanningWeekGrid keys", "identical", f"{len(tk & gk)} shared / {len(tk ^ gk)} differ",
        "PASS" if tk == gk else "FAIL")

    # ---------------- duplicates / nulls
    for name, df, keys in [("FactShiftDemand", dem, KEY), ("FactShiftSchedule", sch, KEY + ["schedule_type"]),
                           ("FactShiftAvailability", av, ["scenario_id"] + KEY), ("FactShiftServiceLevel", sl, KEY),
                           ("ScenarioDemandAdjustment", sda, ["scenario_id"] + KEY),
                           ("v_ShiftHistory", hist, KEY), ("v_PlanningWeekGrid", grid, ["scenario_id"] + KEY),
                           ("TEAM_SUBMISSION_TEMPLATE", tpl, ["scenario_id"] + KEY)]:
        ndup = int(df.duplicated(keys).sum())
        chk("K-" + name, "Keys", f"Duplicate keys in {name}", 0, ndup, "PASS" if ndup == 0 else "FAIL")
    # nulls in numeric columns that should be populated
    for name, df in tabs.items():
        for c in df.columns:
            nn = int(df[c].isna().sum())
            if nn and c not in ("availability_note", "notes", "holiday_name", "submitted_employees", "metric_value",
                                "met_target", "shift_start_time", "shift_end_time", "callout_employees",
                                "backfill_employees", "worked_employees", "worked_regular_employees",
                                "worked_overtime_employees", "worked_labor_hours", "worked_regular_hours",
                                "worked_overtime_hours"):
                odd.append(dict(table=name, issue="nulls in column", column=c, n=nn, detail=""))

    # ---------------- demand consistency
    daily = hist.groupby(["store_id", "dept_id", "day_date"]).agg(daily=("daily_demand_units", "max"),
                                                                 shifts=("shift_demand_units", "sum")).reset_index()
    mism = daily[(daily.daily - daily.shifts).abs() > 0.001]
    chk("D01", "Demand", "Shift demand sums to daily demand (tol 0.001)", "0 mismatched days", len(mism),
        "PASS" if len(mism) == 0 else "FAIL")
    for _, r in mism.iterrows():
        odd.append(dict(table="v_ShiftHistory", issue="shift demand != daily demand", column="shift_demand_units",
                        n=1, detail=f"store {r.store_id} dept {r.dept_id} {r.day_date.date()} daily={r.daily:.4f} shifts={r.shifts:.4f}"))
    # share_of_day consistency
    h2 = hist[hist.is_open == 1]
    sh_err = h2[(h2.shift_share_of_day - h2.shift_demand_units / h2.daily_demand_units).abs() > 0.00051]
    chk("D01b", "Demand", "share_of_day == shift/daily (tol 5e-4, rounding)", 0, len(sh_err), "PASS" if len(sh_err) == 0 else "FAIL")
    # is_open vs ShiftDefinition and closures
    hd = hist.merge(sd[["dept_id", "day_type", "shift_code", "is_open"]].rename(columns={"is_open": "sd_open"}),
                    on=["dept_id", "day_type", "shift_code"], how="left")
    exp_open = np.where(hd.is_costco_closed == 1, 0, hd.sd_open)
    v = int((hd.is_open != exp_open).sum())
    chk("D02", "Demand", "is_open matches ShiftDefinition and warehouse closures", 0, v, "PASS" if v == 0 else "FAIL")
    # day_type vs calendar
    v = int((hist.day_type != hist.day_date.map(day_type_of)).sum())
    chk("D03", "Demand", "day_type matches calendar weekday", 0, v, "PASS" if v == 0 else "FAIL")
    closed = hist[hist.is_open == 0]
    v = int(((closed.shift_demand_units != 0) | (closed.scheduled_employees != 0) | closed.metric_value.notna()).sum())
    chk("D04", "Demand", "Closed blocks have zero demand, zero staff, no service value", 0, v, "PASS" if v == 0 else "FAIL")
    chk("D05", "Demand", "No planning-week demand in history (max date)", "2026-02-11", str(hist.day_date.max().date()),
        "PASS" if hist.day_date.max() <= pd.Timestamp("2026-02-11") else "FAIL")
    neg = int((dem.demand_units < 0).sum())
    chk("D06", "Demand", "Negative demand values", 0, neg, "PASS" if neg == 0 else "FAIL")
    zero_open = int(((hist.is_open == 1) & (hist.shift_demand_units <= 0)).sum())
    chk("D07", "Demand", "Open blocks with zero demand", 0, zero_open, "PASS" if zero_open == 0 else "FAIL")

    # ---------------- staffing consistency
    act = sch[sch.schedule_type == "Actual"]
    v = int(((act.worked_employees != act.scheduled_employees - act.callout_employees + act.backfill_employees)
             | (act.worked_regular_employees + act.worked_overtime_employees != act.worked_employees)).sum())
    chk("S01", "Staffing", "worked = scheduled - callouts + backfill; regular + OT = worked", 0, v, "PASS" if v == 0 else "FAIL")
    v = int(((sch.scheduled_labor_hours - sch.scheduled_employees * sch.paid_hours_per_employee).abs() > 1e-6).sum())
    v += int(((act.worked_labor_hours - act.worked_employees * act.paid_hours_per_employee).abs() > 1e-6).sum())
    chk("S02", "Staffing", "Labor hours = employees x paid hours", 0, v, "PASS" if v == 0 else "FAIL")
    # paid hours vs ShiftDefinition
    sch2 = sch.copy(); sch2["day_type"] = sch2.day_date.map(day_type_of)
    sch2 = sch2.merge(sd[["dept_id", "day_type", "shift_code", "paid_hours"]], on=["dept_id", "day_type", "shift_code"], how="left")
    v = int(((sch2.paid_hours_per_employee - sch2.paid_hours).abs() > 1e-6).sum())
    chk("S03", "Staffing", "Paid hours on schedules match ShiftDefinition", 0, v, "PASS" if v == 0 else "FAIL")
    v = int(((hist.scheduled_employees > hist.available_regular_employees + hist.max_overtime_employees)
             | (hist.worked_regular_employees > hist.available_regular_employees)
             | (hist.worked_overtime_employees > hist.max_overtime_employees)).sum())
    chk("S04", "Staffing", "Historical: scheduled <= reg+OT cap; reg worked <= reg avail; OT worked <= OT cap", 0, v,
        "PASS" if v == 0 else "FAIL")
    ho = hist[hist.is_open == 1]
    v = int(((ho.worked_employees < 1) | (ho.scheduled_employees < ho.min_staff)).sum())
    chk("S05", "Staffing", "Open historical blocks: >=1 worker and scheduled >= min_staff", 0, v, "PASS" if v == 0 else "FAIL")
    # worked below min_staff (after callouts) - informational oddity
    wb = ho[ho.worked_employees < ho.min_staff]
    chk("S05b", "Staffing", "INFO: open historical blocks where WORKED heads < min_staff (after callouts)", "info", len(wb), "INFO")
    gb = grid[(grid.scenario_code == "BASE") & (grid.is_open == 1)]
    cap = gb.available_regular_employees + gb.max_overtime_employees + gb.cross_trained_flex_employees
    v = int(((gb.draft_scheduled_employees > cap) | (gb.draft_scheduled_employees < gb.min_staff)).sum())
    chk("S06", "Staffing", "Draft fits BASE capacity (reg+OT+flex) and >= min_staff", 0, v, "PASS" if v == 0 else "FAIL")
    gd = grid[grid.scenario_code == "DISRUPT"]
    capd = gd.available_regular_employees + gd.max_overtime_employees + gd.cross_trained_flex_employees
    v = int((gd.draft_scheduled_employees > capd).sum())
    chk("S07", "Staffing", "INFO (intended): draft blocks exceeding DISRUPT capacity", "> 0", v, "INFO" if v > 0 else "FAIL")
    v = int((av[av.dept_id == 95].cross_trained_flex_employees != 0).sum())
    v += int(((grid.is_open == 0) & (grid.available_regular_employees + grid.max_overtime_employees > 0)).sum())
    chk("S08", "Staffing", "Pharmacy flex == 0; closed planning blocks have zero availability", 0, v, "PASS" if v == 0 else "FAIL")
    # draft on closed blocks
    v = int(((grid.is_open == 0) & (grid.draft_scheduled_employees != 0)).sum())
    chk("S09", "Staffing", "Draft schedule is 0 on closed planning blocks", 0, v, "PASS" if v == 0 else "FAIL")
    # draft identical across scenarios?
    piv = grid.pivot_table(index=KEY, columns="scenario_code", values="draft_scheduled_employees")
    v = int(((piv["BASE"] != piv["PEAK"]) | (piv["BASE"] != piv["DISRUPT"])).sum())
    chk("S10", "Staffing", "Draft schedule identical across BASE/PEAK/DISRUPT", 0, v, "PASS" if v == 0 else "FAIL")

    # ---------------- cost
    v = int((((lc.loaded_regular_hourly_cost - lc.base_hourly_wage * (1 + lc.regular_burden_pct)).abs() > 0.01)
             | ((lc.loaded_overtime_hourly_cost - lc.base_hourly_wage * lc.overtime_multiplier * (1 + lc.overtime_burden_pct)).abs() > 0.01)
             | (lc.loaded_overtime_hourly_cost <= lc.loaded_regular_hourly_cost)).sum())
    chk("K01", "Cost", "Loaded rates follow documented formulas; OT > regular", 0, v, "PASS" if v == 0 else "FAIL")
    hc = hist.merge(lc[["store_id", "dept_id", "loaded_regular_hourly_cost", "loaded_overtime_hourly_cost"]], on=["store_id", "dept_id"])
    recomputed = hc.worked_regular_hours * hc.loaded_regular_hourly_cost + hc.worked_overtime_hours * hc.loaded_overtime_hourly_cost
    v = int(((recomputed - hc.labor_cost).abs() > 0.011).sum())
    chk("K02", "Cost", "v_ShiftHistory.labor_cost == reg hrs x reg rate + OT hrs x OT rate", 0, v, "PASS" if v == 0 else "FAIL")
    chk("K03", "Cost", "INFO: total historical labor cost (6 weeks, 3 warehouses)", "info", round(float(hist.labor_cost.sum()), 2), "INFO")
    ot_ratio = (lc.loaded_overtime_hourly_cost / lc.loaded_regular_hourly_cost).round(4).unique().tolist()
    chk("K04", "Cost", "OT / regular loaded-rate ratio", "~1.32", str(ot_ratio), "INFO")

    # ---------------- service
    sm = tabs["comp_ServiceMetricDefinition"]
    s2 = sl.merge(dem[KEY + ["is_open"]], on=KEY).merge(sm[["metric_code", "dept_id", "target_value"]].rename(
        columns={"dept_id": "m_dept", "target_value": "m_target"}), on="metric_code")
    v = int((((s2.is_open == 1) & s2.metric_value.isna()) | (s2.m_dept != s2.dept_id) | (s2.target_value != s2.m_target)
             | (s2.metric_value.notna() & (s2.met_target != (s2.metric_value <= s2.target_value).astype(int)))).sum())
    chk("V01", "Service", "Open blocks have a metric; met_target consistent; metric matches dept", 0, v, "PASS" if v == 0 else "FAIL")
    rate = sl.met_target.mean()
    chk("V03", "Service", "Share of open blocks meeting target", "60%-90%", f"{100*rate:.1f}%", "PASS" if 0.6 <= rate <= 0.9 else "FAIL")
    by_dept = sl.groupby("dept_id").met_target.mean().round(3).to_dict()
    chk("V04", "Service", "INFO: hit rate by dept (prompt says ~77% FE, 70% Merch, 88% Pharm)", "info", str(by_dept), "INFO")

    # ---------------- scenarios
    v = int((((sda.scenario_id.isin([1, 3])) & (sda.demand_multiplier != 1.0)) | ((sda.scenario_id == 2) & (sda.demand_multiplier < 1.0))).sum())
    p = int(((sda.scenario_id == 2) & (sda.demand_multiplier > 1.0)).sum())
    chk("X01", "Scenario", "BASE/DISRUPT multipliers all 1.00; PEAK has increases only", "0 viol / PEAK>1 rows>0", f"{v} / {p}",
        "PASS" if v == 0 and p > 0 else "FAIL")
    b = av[av.scenario_id == 1].set_index(KEY); pk = av[av.scenario_id == 2].set_index(KEY); ds = av[av.scenario_id == 3].set_index(KEY)
    v = int(((pk.available_regular_employees != b.available_regular_employees) | (pk.max_overtime_employees != b.max_overtime_employees)).sum())
    v += int(((ds.available_regular_employees > b.available_regular_employees) | (ds.max_overtime_employees > b.max_overtime_employees)).sum())
    chk("X02", "Scenario", "PEAK availability == BASE; DISRUPT never above BASE", 0, v, "PASS" if v == 0 else "FAIL")
    vflex = int((pk.cross_trained_flex_employees != b.cross_trained_flex_employees).sum())
    chk("X03", "Scenario", "PEAK flex == BASE flex", 0, vflex, "PASS" if vflex == 0 else "FAIL")

    # ---------------- utilization oddities
    hf = hist_frame(tabs)
    opn = hf[hf.is_open == 1]
    over1 = opn[opn.utilization > 1]
    chk("U01", "Utilization", "INFO: open blocks with worked-hours utilization > 1.0", "info", len(over1), "INFO")
    chk("U02", "Utilization", "INFO: open blocks with worked-hours utilization > 0.95", "info", int((opn.utilization > 0.95).sum()), "INFO")
    for _, r in over1.iterrows():
        odd.append(dict(table="v_ShiftHistory", issue="utilization > 1 (demand hours exceed worked hours)", column="utilization", n=1,
                        detail=f"store {r.store_id} {r.dept} {r.day_date.date()} {r.shift_code} u={r.utilization:.3f} metric={r.metric_value} met={r.met_target}"))
    chk("U03", "Utilization", "INFO: utilization range (min / median / max) open blocks", "info",
        f"{opn.utilization.min():.3f} / {opn.utilization.median():.3f} / {opn.utilization.max():.3f}", "INFO")

    # callouts > scheduled, backfill > callouts
    v = int(((act.callout_employees > act.scheduled_employees) | (act.backfill_employees > act.callout_employees)).sum())
    chk("S11", "Staffing", "callouts <= scheduled and backfill <= callouts", 0, v, "PASS" if v == 0 else "FAIL")
    # worked below min_staff rows into oddities
    for _, r in wb.iterrows():
        odd.append(dict(table="v_ShiftHistory", issue="worked heads < min_staff after callouts (schedule met min_staff)",
                        column="worked_employees", n=1,
                        detail=f"store {r.store_id} dept {r.dept_id} {r.day_date.date()} {r.shift_code} sched={r.scheduled_employees} callouts={r.callout_employees} worked={r.worked_employees} min={r.min_staff}"))
    # availability notes
    chk("A01", "Availability", "INFO: historical availability_note values", "info",
        str(hist.availability_note.fillna("(none)").value_counts().to_dict()), "INFO")
    chk("A02", "Availability", "INFO: planning-week availability_note values by scenario", "info",
        str(grid.groupby("scenario_code").availability_note.apply(lambda s: s.fillna("(none)").value_counts().to_dict()).to_dict()), "INFO")

    # ---------------- shift lengths & min staff summary
    sdd = sd.copy(); sdd["shift_seq"] = sdd.shift_code.map({"OPEN": 1, "MID": 2, "EVE": 3})
    sdd = sdd.sort_values(["dept_id", "day_type", "shift_seq"])
    sdd.to_csv(os.path.join(out_dir, "00_shift_definition.csv"), index=False)
    closed_defs = sdd[sdd.is_open == 0][["dept_id", "day_type", "shift_code", "notes"]]
    chk("Z01", "Closures", "Closed blocks per ShiftDefinition", "Pharmacy Sat EVE, Sun OPEN, Sun EVE",
        "; ".join(f"dept {r.dept_id} {r.day_type} {r.shift_code}" for _, r in closed_defs.iterrows()), "INFO")
    chk("Z02", "Closures", "Closed planning blocks (grid is_open=0) per scenario", "info",
        str(grid[grid.is_open == 0].groupby("scenario_code").size().to_dict()), "INFO")
    chk("Z03", "Closures", "Closed historical blocks (is_open=0)", "info",
        f"{int((hist.is_open==0).sum())} = New Year's Day 27 + pharmacy weekend closures {int(((hist.is_open==0)&(hist.is_costco_closed==0)).sum())}", "INFO")

    # ---------------- weekly / daily structure facts used later
    chk("W01", "Calendar", "Weeks in history (Thu-Wed)", 6, int(hist.week_of_year.nunique()), "PASS" if hist.week_of_year.nunique() == 6 else "FAIL")
    chk("W02", "Calendar", "Holiday window roles in history", "info", str(hist.groupby("holiday_window_role").day_date.nunique().to_dict()), "INFO")
    chk("W03", "Calendar", "Planning-week holiday roles", "info",
        str(grid[grid.scenario_code == "BASE"].groupby("holiday_window_role").day_date.nunique().to_dict()), "INFO")
    chk("W04", "Calendar", "has_promotion pattern in history (by weekday x window)", "info",
        str(hist.groupby(["day_name", "holiday_window_role"]).has_promotion.mean().round(2).to_dict()), "INFO")

    checks_df = pd.DataFrame(checks)
    checks_df.to_csv(os.path.join(out_dir, "00_validation_checks.csv"), index=False)
    odd_df = pd.DataFrame(odd) if odd else pd.DataFrame(columns=["table", "issue", "column", "n", "detail"])
    odd_df.to_csv(os.path.join(out_dir, "00_oddities.csv"), index=False)
    return dict(inventory=inv, checks=checks_df, oddities=odd_df, tabs=tabs)


if __name__ == "__main__":
    import sys
    res = run(sys.argv[1], sys.argv[2])
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 120); pd.set_option("display.max_rows", 500)
    print(res["inventory"][["file", "rows", "n_cols"]].to_string(index=False))
    print(res["checks"].to_string(index=False))
    print("\nODDITIES:", len(res["oddities"]))
    print(res["oddities"].to_string(index=False))
