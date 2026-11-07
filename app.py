"""
app.py - Warehouse staffing planner (proof of concept). Single-file Streamlit app.

Run:  streamlit run app.py          (from the folder that holds app.py, data/, outputs/ and pipeline/)
Reads only pipeline outputs (outputs/01_service_params.json, 03_forecast_shift.csv, 04_callout_rates.csv,
04_plan_recommended.csv) and the competition CSVs in data/. All staffing mechanics come from pipeline/engine.py,
the same code that produced the submission, so the live plan and the submitted plan cannot disagree.
"""
from __future__ import annotations
import os, sys, json, io
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "pipeline"))
import numpy as np
import pandas as pd
import streamlit as st
from common import load_all, planning_grid, DEPT_SHORT
from engine import build_blocks, optimize_trio, evaluate_plan, fill_block, av_from_rows, BlockModel
from viz import heatmap, DAY_LABEL

DATA = os.path.join(HERE, "data"); OUT = os.path.join(HERE, "outputs")

st.set_page_config(page_title="Warehouse staffing planner", layout="wide")
st.markdown("""
<style>
html, body, [class*="css"] { font-family: Helvetica, Arial, sans-serif; }
.stApp { background-color: #f4f3ef; }
div[data-testid="stMetric"] { border: 1px solid #55554f; padding: 6px 10px; border-radius: 0; background: #ece9e1; }
div[data-testid="stMetric"] label { color: #1a1a1a; }
table { border-collapse: collapse; }
th, td { border: 1px solid #b9b6ad; padding: 4px 8px; font-size: 13px; }
h1, h2, h3 { font-weight: 600; letter-spacing: 0; }
button, .stButton>button, .stDownloadButton>button { border-radius: 0 !important; border: 1px solid #1a1a1a !important; background: #e3e0d6 !important; color: #1a1a1a !important; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def load_static():
    tabs = load_all(DATA); grid = planning_grid(tabs)
    params = json.load(open(os.path.join(OUT, "01_service_params.json")))
    fc = pd.read_csv(os.path.join(OUT, "03_forecast_shift.csv"), parse_dates=["day_date"])
    rates = pd.read_csv(os.path.join(OUT, "04_callout_rates.csv")); rates = rates[rates.cat.isin(["weekday", "weekend", "post_holiday"])]
    rec = pd.read_csv(os.path.join(OUT, "04_plan_recommended.csv"), parse_dates=["day_date"])
    tpl = pd.read_csv(os.path.join(DATA, "TEAM_SUBMISSION_TEMPLATE.csv"))
    th = pd.read_csv(os.path.join(OUT, "01_service_thresholds.csv"))
    params["_u90"] = {(r.dept, int(r.store_id)): float(r.u_threshold) for r in th[th.p_meet_level == 0.90].itertuples()}
    return tabs, grid, params, fc, rates, rec, tpl


@st.cache_data(show_spinner="Recomputing the plan with the same optimizer that built the submission")
def compute_plan(scenario: str, tau: float, basis: str, callout_mult: float, mult_json: str):
    tabs, grid, params, fc, rates, rec, tpl = load_static()
    mult = {}
    for k, v in json.loads(mult_json).items():
        s, d, day = k.split("|")
        for sh in ("OPEN", "MID", "EVE"):
            mult[(int(s), int(d), pd.Timestamp(day), sh)] = float(v)
    blocks = build_blocks(grid, fc, rates, scenario, demand_mult=mult, callout_mult=callout_mult)
    heads, models = {}, {}
    for (store, date, shift), trio in blocks.groupby(["store_id", "day_date", "shift_code"], sort=False):
        res = optimize_trio(trio, params, tau=tau, basis=basis)
        for d, n in res["heads"].items():
            heads[(store, date, shift, d)] = int(n)
        for d, m in res["models"].items():
            models[(store, date, shift, d)] = m
    ev = evaluate_plan(blocks, heads, params, tau=tau, models_cache=models)
    draft_heads = {(r.store_id, r.day_date, r.shift_code, int(r.dept_id)): int(r.draft) for r in blocks.itertuples()}
    evd = evaluate_plan(blocks, draft_heads, params, tau=tau, models_cache=models)
    ev["draft_cost"] = evd.cost.values; ev["draft_p_post"] = evd.p_meet_post_callout.values; ev["draft_p_sub"] = evd.p_meet_submitted.values
    ev["draft_infeasible"] = evd.infeasible_strict.values
    ev["delta_vs_draft"] = ev.heads - ev.draft_heads
    return blocks, ev


def kpis(ev: pd.DataFrame, tau: float) -> dict:
    o = ev[ev.is_open == 1]
    return dict(heads=int(o.heads.sum()), cost=float(o.cost.sum()), draft_cost=float(o.draft_cost.sum()), ot=int(o.ot.sum()),
                flex=int(o.flex.sum()), exp_missed_sub=float((1 - o.p_meet_submitted).sum()), exp_missed_post=float((1 - o.p_meet_post_callout).sum()),
                draft_missed_sub=float((1 - o.draft_p_sub).sum()), draft_missed_post=float((1 - o.draft_p_post).sum()),
                below=int((o.p_meet_post_callout < tau).sum()), infeasible=int(o.infeasible_strict.sum()), draft_infeasible=int(o.draft_infeasible.sum()))


def main():
    tabs, grid, params, fc, rates, rec, tpl = load_static()
    st.title("Warehouse staffing planner, week of Feb 12-18, 2026")
    st.caption("Forecast, service curve, callout model and costing rule are the pipeline's. Change a setting and the plan is re-optimized.")

    with st.sidebar:
        st.header("Scenario and settings")
        scenario = st.selectbox("Scenario", ["BASE", "PEAK", "DISRUPT"], index=0)
        tau = st.slider("Service confidence target (P(meet) per block)", 0.70, 0.97, 0.90, 0.01)
        basis = st.radio("Evaluate service on", ["post_callout", "submitted"], index=0,
                         format_func=lambda x: "heads after expected callouts (recommended)" if x == "post_callout" else "submitted heads only")
        callout_mult = st.slider("Callout rate multiplier (1.0 = history)", 0.0, 2.5, 1.0, 0.1)
        st.subheader("Demand multipliers (on top of the scenario)")
        days = sorted(fc.day_date.dt.strftime("%Y-%m-%d").unique())
        default = pd.DataFrame([dict(warehouse=s, dept=DEPT_SHORT[d], **{DAY_LABEL[day]: 1.0 for day in days})
                                for s in (1, 2, 4) for d in (38, 92, 95)])
        edited = st.data_editor(default, hide_index=True, num_rows="fixed", key="mult_editor")
        mult = {}
        inv = {v: k for k, v in DEPT_SHORT.items()}
        for i in range(len(edited)):
            rr = edited.iloc[i]
            for day in days:
                v = float(rr[DAY_LABEL[day]])
                if abs(v - 1.0) > 1e-9:
                    mult[f"{int(rr['warehouse'])}|{inv[rr['dept']]}|{day}"] = v
        mult_json = json.dumps(mult, sort_keys=True)

    blocks, ev = compute_plan(scenario, tau, basis, callout_mult, mult_json)
    k = kpis(ev, tau)

    st.subheader(f"{scenario}: plan summary")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Heads (week)", f"{k['heads']:,}", f"{k['heads'] - int(ev[ev.is_open==1].draft_heads.sum()):+,} vs draft")
    c2.metric("Labor cost", f"${k['cost']:,.0f}", f"{k['cost'] - k['draft_cost']:+,.0f} vs draft")
    c3.metric("Overtime heads", f"{k['ot']:,}", f"flex {k['flex']}")
    c4.metric("Expected missed blocks (after callouts)", f"{k['exp_missed_post']:.1f}", f"draft {k['draft_missed_post']:.1f}", delta_color="inverse")
    c5.metric("Expected missed (submitted heads)", f"{k['exp_missed_sub']:.1f}", f"draft {k['draft_missed_sub']:.1f}", delta_color="inverse")
    c6.metric(f"Blocks below {int(tau*100)}%", f"{k['below']}", f"infeasible {k['infeasible']} (draft {k['draft_infeasible']})", delta_color="off")

    view = st.radio("Heatmap", ["Recommended heads", "Change vs draft", "P(meet) after callouts", "P(meet) submitted heads", "Utilization", "Cost ($)"], horizontal=True)
    cfg = {"Recommended heads": ("heads", "seq", "{:.0f}"), "Change vs draft": ("delta_vs_draft", "div", "{:+.0f}"),
           "P(meet) after callouts": ("p_meet_post_callout", "risk", "{:.2f}"), "P(meet) submitted heads": ("p_meet_submitted", "risk", "{:.2f}"),
           "Utilization": ("utilization", "seq", "{:.2f}"), "Cost ($)": ("cost", "seq", "{:.0f}")}
    col, kind, fmt = cfg[view]
    st.pyplot(heatmap(ev, col, f"{scenario}: {view} by warehouse x department (rows) and day x shift (columns)", kind=kind, fmt=fmt))

    st.subheader("Why this block?")
    o = ev[ev.is_open == 1]
    b1, b2, b3, b4 = st.columns(4)
    wsel = b1.selectbox("Warehouse", [1, 2, 4]); dsel = b2.selectbox("Date", days, format_func=lambda d: DAY_LABEL[d])
    ssel = b3.selectbox("Shift", ["OPEN", "MID", "EVE"]); psel = b4.selectbox("Department", ["FE", "Merch", "Pharm"])
    row = o[(o.store_id == wsel) & (o.day_date == pd.Timestamp(dsel)) & (o.shift_code == ssel) & (o.dept == psel)]
    if len(row) == 0:
        st.write("This block is closed.")
    else:
        r = row.iloc[0]
        trio = blocks[(blocks.store_id == wsel) & (blocks.day_date == pd.Timestamp(dsel)) & (blocks.shift_code == ssel)]
        av = av_from_rows(trio); br = trio[trio.dept == psel].iloc[0]
        m = BlockModel(br["demand"], br["log_sd"], br["std"], br["paid"], int(wsel), params[psel], br["p_callout"])
        n0 = {int(t.dept_id): int(o[(o.store_id == wsel) & (o.day_date == pd.Timestamp(dsel)) & (o.shift_code == ssel) & (o.dept_id == t.dept_id)].heads.iloc[0]) for t in trio.itertuples()}
        f0 = fill_block(n0, av)
        d_id = int(br.dept_id)
        lo, hi = br.demand * np.exp(-1.2816 * br.log_sd), br.demand * np.exp(1.2816 * br.log_sd)
        what_if = []
        for delta in (-2, -1, 1, 2):
            n1 = dict(n0); n1[d_id] = n0[d_id] + delta
            if n1[d_id] < 1:
                continue
            f1 = fill_block(n1, av)
            feas = "no (over capacity)" if f1[d_id]["infeasible_strict"] else ("below min_staff" if n1[d_id] < av[d_id]["min_staff"] else "yes")
            what_if.append(dict(change=f"{delta:+d} head", heads=n1[d_id], feasible=feas, utilization=round(m.utilization(n1[d_id]), 3),
                                p_meet_submitted=round(m.p_submitted(n1[d_id]), 3),
                                p_meet_after_callouts=round(m.p_post_callout(n1[d_id], max(0, av[d_id]["O"] - f1[d_id]["ot"])), 3),
                                cost_change=round(sum(f1[d]["cost"] for d in f1) - sum(f0[d]["cost"] for d in f0), 0)))
        need90 = next((nn for nn in range(1, 120) if m.p_submitted(nn) >= 0.90), None)
        cap = int(br.A + br.F + br.O)
        notes = []
        if need90 is not None and need90 > cap:
            notes.append(f"At the point forecast this block needs {need90} heads for a 90% chance of meeting target; its capacity (regular + cross-trained + overtime) is {cap}. It cannot be saved by scheduling, so the plan uses its people where they change an outcome and flags the block for the playbook.")
        if r.reg < r.avail_regular and r.heads < cap:
            partner = "Merch" if psel == "FE" else ("FE" if psel == "Merch" else None)
            if partner:
                pr = o[(o.store_id == wsel) & (o.day_date == pd.Timestamp(dsel)) & (o.shift_code == ssel) & (o.dept == partner)]
                if len(pr) and pr.iloc[0].flex > 0:
                    notes.append(f"{int(r.avail_regular - r.reg)} of this department's regulars are released as cross-trained cover to {partner} ({int(pr.iloc[0].flex)} used there), which lifts {partner}'s P(meet) after callouts to {pr.iloc[0].p_meet_post_callout:.2f}.")
        u90 = params["_u90"].get((psel, int(wsel)), float("nan"))
        left, right = st.columns([1, 1])
        with left:
            st.markdown(f"""
| | |
|---|---|
| Forecast demand (units) | {br.demand:.1f} (80% interval {lo:.1f} to {hi:.1f}) |
| Required hours at 100% productive | {br["demand"] * br["std"]:.1f} h (standard {br["std"]} h/unit) |
| Paid hours per head | {br.paid} h, min_staff {int(br.min_staff)} |
| Expected callouts | {r.heads * br.p_callout:.2f} of {int(r.heads)} (rate {100*br.p_callout:.1f}%, about half backfilled) |
| **Chosen heads** | **{int(r.heads)}** (draft {int(r.draft_heads)}) |
| Fill: regular / cross-trained / overtime | {int(r.reg)} / {int(r.flex)} / {int(r.ot)} of {int(r.avail_regular)} / {int(r.flex_avail)} / {int(r.max_ot)} available |
| Utilization at forecast | {r.utilization:.3f} (P(meet) falls below 90% above u = {u90:.3f} for this warehouse and department) |
| P(meet target), submitted heads | {r.p_meet_submitted:.3f} (draft {r.draft_p_sub:.3f}) |
| P(meet target), after callouts | {r.p_meet_post_callout:.3f} (draft {r.draft_p_post:.3f}) |
| Block cost | ${r.cost:,.0f} (draft ${r.draft_cost:,.0f}) |
| Feasible under the strict fill rule | {"no" if r.infeasible_strict else "yes"} (draft {"no" if r.draft_infeasible else "yes"}) |
""")
        with right:
            st.write("What one or two heads more or fewer would do:")
            st.table(pd.DataFrame(what_if))
            if r.p_meet_post_callout < tau:
                st.write(f"This block does not reach the {int(tau*100)}% target within its capacity on the chosen basis; it is flagged in the playbook.")
            for ntxt in notes:
                st.write(ntxt)

    st.subheader("Export")
    sub = tpl.copy()
    live = {(r.store_id, r.day_date.strftime("%Y-%m-%d"), r.shift_code, int(r.dept_id)): int(r.heads) for r in ev.itertuples()}
    recm = {(r.scenario_code, r.store_id, r.day_date.strftime("%Y-%m-%d"), r.shift_code, int(r.dept_id)): int(r.heads) for r in rec.itertuples()}
    vals = []
    for t in sub.itertuples():
        key = (t.store_id, str(t.day_date)[:10], t.shift_code, int(t.dept_id))
        if t.scenario_code == scenario:
            vals.append(live.get(key, 0))
        else:
            vals.append(recm.get((t.scenario_code,) + key, 0))
    sub["submitted_employees"] = vals
    st.write(f"The current {scenario} plan plus the recommended plan for the other two scenarios, in the competition template (567 rows).")
    st.download_button("Download submission CSV", sub.to_csv(index=False).encode(), file_name="TEAM_SUBMISSION.csv", mime="text/csv")
    st.download_button("Download this plan with diagnostics (CSV)", ev.to_csv(index=False).encode(), file_name=f"plan_{scenario}.csv", mime="text/csv")


if __name__ == "__main__":
    main()
