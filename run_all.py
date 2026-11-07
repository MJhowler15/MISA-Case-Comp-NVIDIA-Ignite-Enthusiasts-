"""
run_all.py - MISA Costco case pipeline (Phase 1 + Phase 2).

Usage:
    python run_all.py [--data DIR] [--out DIR] [--phase 1|2|all] [--team TEAM_ID]

Defaults: --data ./data (the csv/ folder of team_distribution), --out ./outputs, --phase all, --team TEAM_NAME.
Phase 1: Step 0 validation -> Step 1 service curve -> Step 2 diagnosis -> Step 3 forecast
Phase 2: Step 4 optimizer -> Step 5 scoring + backtest -> Step 6 playbook -> Step 7 static tool page
         -> Step 8 submission CSV -> Step 9 sensitivity -> reports
Fixed seed (common.SEED). No manual steps. About 6 minutes end to end on a laptop.
"""
from __future__ import annotations

import os, sys, json, argparse, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "pipeline"))

import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--out", default=os.path.join(HERE, "outputs"))
    ap.add_argument("--phase", default="all", choices=["1", "2", "all"])
    ap.add_argument("--team", default="TEAM_NAME")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()

    if a.phase in ("1", "all"):
        import step0_validate, step1_service, step2_diagnosis, step3_forecast, make_report
        print("== Step 0: inventory & validation")
        r0 = step0_validate.run(a.data, a.out)
        fails = r0["checks"][r0["checks"].status == "FAIL"]
        print(f"   checks: {len(r0['checks'])}  FAIL: {len(fails)}  oddities: {len(r0['oddities'])}")
        if len(fails):
            print(fails.to_string(index=False))
        print("== Step 1: service-response model")
        r1 = step1_service.run(a.data, a.out)
        print("   chosen:", {d: p["model"] for d, p in r1["params"].items()})
        print("== Step 2: diagnosis")
        r2 = step2_diagnosis.run(a.data, a.out, params=r1["params"])
        hd = r2["headline"]
        print(f"   surplus ${hd['surplus_cost']:,.0f} ({100*hd['surplus_pct_of_cost']:.1f}% of labor), deficit ${hd['deficit_cost']:,.0f}, "
              f"missed blocks {hd['missed_blocks']} (understaffed {hd['missed_understaffed']})")
        print("== Step 3: forecast")
        r3 = step3_forecast.run(a.data, a.out)
        bt = r3["backtest"]
        print(bt[(bt.dept == "ALL")][["test", "horizon", "level", "wape_ours", "wape_naive"]].round(4).to_string(index=False))
        make_report.main(a.out)
        print(f"   phase 1 done at {time.time() - t0:.0f}s")

    if a.phase in ("2", "all"):
        import step4_optimize, step5_score, step6_playbook, step7_static, step8_submission, step9_sensitivity, make_final_report
        print("== Step 4: optimizer")
        step4_optimize.run(a.data, a.out)
        print("== Step 5: scoring vs draft, stress test, six-week backtest")
        step5_score.run(a.data, a.out)
        print("== Step 6: playbook")
        step6_playbook.run(a.data, a.out)
        print("== Step 7: static tool page")
        step7_static.run(a.data, a.out)
        print("== Step 8: submission CSV")
        cdf = step8_submission.run(a.data, a.out, team_id=a.team)
        print(cdf[["check", "actual", "status"]].to_string(index=False))
        print("== Step 9: sensitivity")
        step9_sensitivity.run(a.data, a.out)
        make_final_report.main(a.out)
        print(f"   phase 2 done at {time.time() - t0:.0f}s")

    print(f"== done in {time.time() - t0:.0f}s; outputs in {a.out}")


if __name__ == "__main__":
    main()
