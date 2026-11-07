"""
step8_submission.py - fill TEAM_SUBMISSION_TEMPLATE.csv with the recommended plan and print the checks.

Writes:
  outputs/TEAM_SUBMISSION.csv          the template, all 567 rows, same columns and order, submitted_employees filled
  outputs/08_submission_checks.csv     check results
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from common import load_all, planning_grid


def run(data_dir: str, out_dir: str, team_id: str = "TEAM_NAME", setting_file: str = "04_plan_recommended.csv") -> pd.DataFrame:
    tpl = pd.read_csv(os.path.join(data_dir, "TEAM_SUBMISSION_TEMPLATE.csv"), dtype=str)
    orig_cols = list(tpl.columns)
    rec = pd.read_csv(os.path.join(out_dir, setting_file))
    rec["day_date"] = pd.to_datetime(rec.day_date).dt.strftime("%Y-%m-%d")
    key = ["scenario_code", "store_id", "dept_id", "day_date", "shift_code"]
    heads = {(r.scenario_code, str(r.store_id), str(r.dept_id), r.day_date, r.shift_code): int(r.heads) for r in rec.itertuples()}
    out = tpl.copy()
    out["submitted_employees"] = [heads.get((r.scenario_code, r.store_id, r.dept_id, r.day_date, r.shift_code), np.nan) for r in out.itertuples()]
    out["team_id"] = team_id
    out = out[orig_cols]
    out["submitted_employees"] = out.submitted_employees.astype("Int64")
    path = os.path.join(out_dir, "TEAM_SUBMISSION.csv")
    out.to_csv(path, index=False)

    # ---- checks, re-reading the written file
    sub = pd.read_csv(path, dtype={"submitted_employees": str})
    tabs = load_all(data_dir); grid = planning_grid(tabs)
    grid["day_date"] = grid.day_date.dt.strftime("%Y-%m-%d")
    g = grid.set_index(key)
    checks = []
    def chk(name, expected, actual, ok):
        checks.append(dict(check=name, expected=expected, actual=actual, status="PASS" if ok else "FAIL"))
    chk("row count", 567, len(sub), len(sub) == 567)
    chk("columns identical to template (names and order)", "|".join(orig_cols), "|".join(sub.columns), list(sub.columns) == orig_cols)
    blanks = int(sub.submitted_employees.isna().sum() + (sub.submitted_employees.astype(str).str.strip() == "").sum())
    chk("no blanks in submitted_employees", 0, blanks, blanks == 0)
    is_int = sub.submitted_employees.astype(str).str.fullmatch(r"-?\d+")
    chk("integers only", 567, int(is_int.sum()), bool(is_int.all()))
    v = pd.to_numeric(sub.submitted_employees, errors="coerce")
    sub["v"] = v
    sub["k"] = list(zip(sub.scenario_code, sub.store_id.astype(str), sub.dept_id.astype(str), sub.day_date, sub.shift_code))
    gk = {(r.scenario_code, str(r.store_id), str(r.dept_id), r.day_date, r.shift_code): r for r in grid.itertuples()}
    is_open = np.array([gk[k].is_open for k in sub.k]); mins = np.array([gk[k].min_staff for k in sub.k])
    cap = np.array([gk[k].available_regular_employees + gk[k].max_overtime_employees + gk[k].cross_trained_flex_employees for k in sub.k])
    chk("0 when closed", 0, int(((is_open == 0) & (v != 0)).sum()), bool(((is_open == 0) & (v != 0)).sum() == 0))
    chk(">= min_staff when open", 0, int(((is_open == 1) & (v < mins)).sum()), bool(((is_open == 1) & (v < mins)).sum() == 0))
    chk("<= capacity (regular + flex + OT) when open", 0, int(((is_open == 1) & (v > cap)).sum()), bool(((is_open == 1) & (v > cap)).sum() == 0))
    chk("no negative values", 0, int((v < 0).sum()), bool((v < 0).sum() == 0))
    tk = set(sub.k); gkeys = set(gk.keys())
    chk("keys match template / planning grid", 567, len(tk & gkeys), tk == gkeys)
    chk("template is_open / min_staff / draft columns unchanged", "unchanged",
        "unchanged" if (tpl[["is_open", "min_staff", "draft_scheduled_employees"]].values == sub[["is_open", "min_staff", "draft_scheduled_employees"]].astype(str).values).all() else "CHANGED",
        bool((tpl[["is_open", "min_staff", "draft_scheduled_employees"]].values == sub[["is_open", "min_staff", "draft_scheduled_employees"]].astype(str).values).all()))
    per = sub.groupby("scenario_code").v.sum().to_dict()
    chk("INFO: total heads per scenario", "info", str({k: int(x) for k, x in per.items()}), True)
    chk("INFO: team_id placeholder", "replace before submitting", sub.team_id.iloc[0], True)
    cdf = pd.DataFrame(checks)
    cdf.to_csv(os.path.join(out_dir, "08_submission_checks.csv"), index=False)
    return cdf


if __name__ == "__main__":
    cdf = run(sys.argv[1], sys.argv[2], team_id=(sys.argv[3] if len(sys.argv) > 3 else "TEAM_NAME"))
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 120)
    print(cdf.to_string(index=False))
