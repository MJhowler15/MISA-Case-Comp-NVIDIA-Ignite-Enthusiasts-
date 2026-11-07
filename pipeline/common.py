"""
common.py - shared loaders, constants and helpers for the MISA Costco pipeline.

Source of truth: the CSV exports in team_distribution/csv (the SQL scripts in
team_distribution/sql define the same tables; see docs/ASSUMPTIONS.md).
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

SEED = 20260212  # fixed seed for anything stochastic (planning week start date)

DEPT_NAME = {38: "Front End", 92: "Merchandising", 95: "Pharmacy"}
DEPT_SHORT = {38: "FE", 92: "Merch", 95: "Pharm"}
STORE_SIZE = {1: "Medium", 2: "Large", 4: "Large"}
SHIFT_ORDER = {"OPEN": 1, "MID": 2, "EVE": 3}
KEY = ["store_id", "dept_id", "day_date", "shift_code"]


def load_all(data_dir: str) -> dict[str, pd.DataFrame]:
    """Load every CSV in data_dir into a dict keyed by file stem."""
    out = {}
    for f in sorted(os.listdir(data_dir)):
        if f.lower().endswith(".csv"):
            df = pd.read_csv(os.path.join(data_dir, f))
            for c in df.columns:
                if c in ("day_date", "week_start_date", "period_start", "period_end", "effective_start_date"):
                    df[c] = pd.to_datetime(df[c])
            out[f[:-4]] = df
    return out


def hist_frame(tabs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Historical block-level frame (v_ShiftHistory) with labor standard, cost rates
    and utilization attached. Utilization uses WORKED hours (after callouts/backfill)."""
    h = tabs["v_ShiftHistory"].copy()
    ls = tabs["comp_LaborStandard"][["dept_id", "labor_hours_per_workload_unit"]]
    h = h.merge(ls, on="dept_id", how="left")
    lc = tabs["comp_LaborCostAssumption"][["store_id", "dept_id", "loaded_regular_hourly_cost",
                                            "loaded_overtime_hourly_cost"]]
    h = h.merge(lc, on=["store_id", "dept_id"], how="left")
    h["required_hours_100"] = h["shift_demand_units"] * h["labor_hours_per_workload_unit"]
    with np.errstate(divide="ignore", invalid="ignore"):
        h["utilization"] = np.where(h["worked_labor_hours"] > 0,
                                    h["required_hours_100"] / h["worked_labor_hours"], np.nan)
        h["sched_utilization"] = np.where(h["scheduled_labor_hours"] > 0,
                                          h["required_hours_100"] / h["scheduled_labor_hours"], np.nan)
    h["week_idx"] = ((h["day_date"] - pd.Timestamp("2026-01-01")).dt.days // 7) + 1
    h["shift_seq"] = h["shift_code"].map(SHIFT_ORDER)
    h["dept"] = h["dept_id"].map(DEPT_SHORT)
    h = h.sort_values(["store_id", "dept_id", "day_date", "shift_seq"]).reset_index(drop=True)
    return h


def planning_grid(tabs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    g = tabs["v_PlanningWeekGrid"].copy()
    ls = tabs["comp_LaborStandard"][["dept_id", "labor_hours_per_workload_unit"]]
    g = g.merge(ls, on="dept_id", how="left")
    g["shift_seq"] = g["shift_code"].map(SHIFT_ORDER)
    g["dept"] = g["dept_id"].map(DEPT_SHORT)
    g = g.sort_values(["scenario_id", "store_id", "dept_id", "day_date", "shift_seq"]).reset_index(drop=True)
    return g


def day_type_of(d: pd.Timestamp) -> str:
    return {5: "Saturday", 6: "Sunday"}.get(d.weekday(), "Weekday")


def wape(actual: np.ndarray, pred: np.ndarray) -> float:
    actual = np.asarray(actual, float); pred = np.asarray(pred, float)
    return float(np.abs(actual - pred).sum() / np.abs(actual).sum())


def mape(actual: np.ndarray, pred: np.ndarray) -> float:
    actual = np.asarray(actual, float); pred = np.asarray(pred, float)
    m = actual != 0
    return float(np.mean(np.abs(actual[m] - pred[m]) / np.abs(actual[m])))
