"""
engine.py - the one place where staffing mechanics live. Used by the optimizer (step 4), the scorer
(step 5), the backtest, the playbook (step 6), the Streamlit tool (app.py) and the submission (step 8).

Contents
  fill_block()      official costing rule: regular first, then cross-trained flex from the partner department
                    (FE <-> Merch only, limited to people the partner is not using in that shift), then overtime.
                    docs/ASSUMPTIONS.md s.5, README.md "Filling in the staffing plan".
  worked_dist()     distribution of worked heads given scheduled heads: callouts ~ Binomial(n, p),
                    each callout backfilled with probability q while overtime room remains.
  BlockModel        P(meet | heads) for one block, integrating over forecast uncertainty (lognormal) and,
                    on the post-callout basis, over the worked-heads distribution.
  optimize_trio()   exact enumeration of (FE, Merch) head pairs plus Pharmacy for one warehouse x date x shift.
  build_blocks()    assembles the block table for a scenario from the planning grid + forecast.
  evaluate_plan()   cost split, P(meet) on both bases, flags, for any plan (ours or the draft).
"""
from __future__ import annotations

import os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from scipy.stats import binom, norm
from numpy.polynomial.hermite import hermgauss
from common import DEPT_SHORT

DEPTS = (38, 92, 95)
PARTNER = {38: 92, 92: 38}
TAU_DEFAULT = 0.90
BACKFILL_Q = 0.50          # share of callouts backfilled when OT room allows (history: 0.49)
# stage 2 (target unreachable for the pair): lexicographic service-first rule, see optimize_trio
GH_NODES = 7               # Gauss-Hermite nodes for the lognormal demand integral


# ----------------------------------------------------------------------------- costing rule
def fill_block(n: dict, av: dict) -> dict:
    """Official fill rule for one warehouse x date x shift.
    n  : {dept_id: heads}
    av : {dept_id: dict(A=available_regular, O=max_overtime, F=cross_trained_flex, paid=paid_hours,
                        min_staff=.., open=0/1, rr=loaded_regular_rate, ro=loaded_overtime_rate)}
    Returns per dept: reg, flex, ot, unfilled, cost, infeasible_strict, infeasible_loose, below_min.
    Flex into FE comes from Merch regulars that Merch is not using (and vice versa); each flex head used by
    one department is one fewer regular available to the other (docs/ASSUMPTIONS.md s.4)."""
    out = {}
    reg = {d: min(n.get(d, 0), av[d]["A"]) for d in DEPTS if d in av}
    for d in DEPTS:
        if d not in av:
            continue
        a = av[d]; h = int(n.get(d, 0))
        if a["open"] == 0:
            out[d] = dict(heads=h, reg=0, flex=0, ot=0, unfilled=h, cost=0.0,
                          infeasible_strict=int(h > 0), infeasible_loose=int(h > 0), below_min=0)
            continue
        r = reg[d]
        need = h - r
        p = PARTNER.get(d)
        if p is not None and p in av:
            spare_partner = max(0, av[p]["A"] - reg[p])
            fx = min(need, a["F"], spare_partner)
        else:
            fx = 0
        need -= fx
        ot = min(need, a["O"])
        need -= ot
        cost = (r + fx) * a["paid"] * a["rr"] + ot * a["paid"] * a["ro"]
        out[d] = dict(heads=h, reg=int(r), flex=int(fx), ot=int(ot), unfilled=int(need), cost=float(cost),
                      infeasible_strict=int(need > 0 or h < a["min_staff"]),
                      infeasible_loose=int(h > a["A"] + a["F"] + a["O"] or h < a["min_staff"]),
                      below_min=int(h < a["min_staff"]))
    return out


def capacity(av_d: dict, partner_spare: int | None = None) -> int:
    """Loose capacity (as in sql/05 S06): A + F + O. If partner_spare is given, flex is capped by it (strict)."""
    f = av_d["F"] if partner_spare is None else min(av_d["F"], partner_spare)
    return int(av_d["A"] + f + av_d["O"])


# ----------------------------------------------------------------------------- callouts
def worked_dist(n: int, p: float, q: float, ot_room: int, tol: float = 1e-5) -> list[tuple[int, float]]:
    """P(worked = w) for scheduled heads n: K ~ Bin(n, p) callouts, B | K ~ Bin(K, q) backfills capped at ot_room."""
    if n <= 0:
        return [(0, 1.0)]
    probs = {}
    pk = binom.pmf(np.arange(n + 1), n, p)
    for k in range(n + 1):
        if pk[k] < tol and k > n * p:
            break
        if k == 0:
            probs[n] = probs.get(n, 0.0) + pk[k]; continue
        pb = binom.pmf(np.arange(k + 1), k, q)
        for b in range(k + 1):
            bb = min(b, ot_room)
            w = n - k + bb
            probs[w] = probs.get(w, 0.0) + pk[k] * pb[b]
    s = sum(probs.values())
    return [(w, pr / s) for w, pr in sorted(probs.items())]


# ----------------------------------------------------------------------------- service
def fitted_log_metric(params_d: dict, u, store: int):
    """log of the fitted service metric (minutes) at utilization u; capacity singularity handled by the caller's cap."""
    u = np.asarray(u, float)
    base = params_d["a"] + params_d["b"] / np.clip(1.0 - u / params_d["c"], 1e-3, None)
    lm = np.log(np.clip(base, 1e-6, None))
    if "int_2" in params_d:
        lm = lm + (params_d["int_2"] if store == 2 else 0.0) + (params_d["int_4"] if store == 4 else 0.0)
    return np.where(u >= params_d["c"], np.log(1e6), lm)


def pmeet_u(params_d: dict, u, store: int):
    """P(meet | utilization) from the Step 1 curve (queue form with warehouse intercept, log-normal noise)."""
    u = np.asarray(u, float)
    base = params_d["a"] + params_d["b"] / np.clip(1.0 - u / params_d["c"], 1e-3, None)
    lm = np.log(np.clip(base, 1e-6, None))
    if "int_2" in params_d:
        lm = lm + (params_d["int_2"] if store == 2 else 0.0) + (params_d["int_4"] if store == 4 else 0.0)
    lm = np.where(u >= params_d["c"], np.log(1e6), lm)
    sg = np.clip(params_d["sigma0"] + params_d["sigma1"] * u, 0.05, None)
    return norm.cdf((np.log(params_d["target"]) - lm) / sg)


class BlockModel:
    """P(meet | heads) for one block, with demand ~ lognormal(log point, log_sd) and optional callouts."""
    def __init__(self, point: float, log_sd: float, std_hours: float, paid: float, store: int, params_d: dict,
                 p_callout: float, q_backfill: float = BACKFILL_Q, max_heads: int = 90, demand_quantile: float | None = None):
        self.point, self.log_sd, self.std, self.paid, self.store = point, log_sd, std_hours, paid, store
        self.params_d, self.p_callout, self.q_backfill = params_d, p_callout, q_backfill
        x, w = hermgauss(GH_NODES)
        z = np.sqrt(2.0) * x; wq = w / np.sqrt(np.pi)
        if demand_quantile is not None:        # conservative mode: a single demand quantile instead of the integral
            z = np.array([norm.ppf(demand_quantile)]); wq = np.array([1.0])
        self.D = point * np.exp(log_sd * z); self.wq = wq
        heads = np.arange(0, max_heads + 1)
        M = np.zeros(max_heads + 1); S = np.full(max_heads + 1, np.log(5.0))
        cap_log = np.log(5.0 * params_d["target"])   # the simulator saturates near 5 x target (history max / target: 5.8, 5.2, 4.9)
        for hh in heads[1:]:
            u = self.D * std_hours / (hh * paid)
            M[hh] = float(np.sum(wq * pmeet_u(params_d, u, store)))
            lm = np.minimum(fitted_log_metric(params_d, u, store), cap_log)
            S[hh] = float(np.sum(wq * np.clip(lm - np.log(params_d["target"]), 0.0, None)))
        self.M = M                                  # P(meet | worked heads = h), submitted basis uses M[n]
        self.S = S                                  # expected log overshoot of the target (0 when the wait is within target)

    def p_submitted(self, n: int) -> float:
        return float(self.M[min(n, len(self.M) - 1)]) if n > 0 else 0.0

    def overshoot(self, n: int) -> float:
        """Expected log(wait / target), floored at 0 and capped at log(5): how far past the target the block runs."""
        return float(self.S[min(n, len(self.S) - 1)]) if n > 0 else float(np.log(5.0))

    def p_post_callout(self, n: int, ot_room: int) -> float:
        if n <= 0:
            return 0.0
        return float(sum(pr * self.M[min(w, len(self.M) - 1)] for w, pr in worked_dist(n, self.p_callout, self.q_backfill, ot_room)))

    def utilization(self, n: int) -> float:
        return float(self.point * self.std / (n * self.paid)) if n > 0 else float("inf")


# ----------------------------------------------------------------------------- block table
def build_blocks(grid: pd.DataFrame, forecast_shift: pd.DataFrame, rates: pd.DataFrame, scenario: str,
                 demand_mult: dict | None = None, callout_mult: float = 1.0) -> pd.DataFrame:
    """One row per block for a scenario. grid = planning_grid(tabs); forecast_shift = outputs/03_forecast_shift.csv.
    demand_mult: optional {(store, dept, date, shift): multiplier} overrides on top of the scenario forecast."""
    g = grid[grid.scenario_code == scenario].copy()
    f = forecast_shift[forecast_shift.scenario_code == scenario][["store_id", "dept_id", "day_date", "shift_code", "shift_point", "log_sd"]]
    g = g.merge(f, on=["store_id", "dept_id", "day_date", "shift_code"], how="left")
    g["demand"] = g.shift_point.fillna(0.0)
    if demand_mult:
        for k, m in demand_mult.items():
            mask = (g.store_id == k[0]) & (g.dept_id == k[1]) & (g.day_date == pd.Timestamp(k[2])) & (g.shift_code == k[3])
            g.loc[mask, "demand"] = g.loc[mask, "demand"] * m
    g["cat"] = np.where(g.is_post_holiday_rebound == 1, "post_holiday", np.where(g.day_type == "Weekday", "weekday", "weekend"))
    r = rates.set_index(["dept_id", "cat"]).rate
    g["p_callout"] = [float(r.get((d, c), 0.05)) * callout_mult for d, c in zip(g.dept_id, g.cat)]
    g["p_callout"] = g.p_callout.clip(0, 0.6)
    g = g.rename(columns={"available_regular_employees": "A", "max_overtime_employees": "O", "cross_trained_flex_employees": "F",
                          "paid_hours": "paid", "loaded_regular_hourly_cost": "rr", "loaded_overtime_hourly_cost": "ro",
                          "draft_scheduled_employees": "draft", "labor_hours_per_workload_unit": "std"})
    g["open"] = g.is_open.astype(int)
    return g[["scenario_code", "store_id", "dept_id", "dept", "day_date", "day_name", "day_type", "holiday_window_role", "shift_code", "shift_seq",
              "open", "paid", "min_staff", "A", "O", "F", "rr", "ro", "std", "demand", "log_sd", "p_callout", "draft", "cat",
              "metric_code", "service_target_value"]].sort_values(["store_id", "day_date", "shift_seq", "dept_id"]).reset_index(drop=True)


def av_from_rows(rows: pd.DataFrame) -> dict:
    return {int(r.dept_id): dict(A=int(r.A), O=int(r.O), F=int(r.F), paid=float(r.paid), min_staff=int(r.min_staff),
                                 open=int(r.open), rr=float(r.rr), ro=float(r.ro)) for r in rows.itertuples()}


# ----------------------------------------------------------------------------- optimizer for one trio
def optimize_trio(rows: pd.DataFrame, params: dict, tau: float = TAU_DEFAULT, basis: str = "post_callout",
                  models: dict | None = None, demand_quantile: float | None = None) -> dict:
    """rows: the 3 dept rows of one warehouse x date x shift. Returns {dept_id: heads} plus diagnostics.
    Objective (matching the judging order): stage 1, the cheapest (FE, Merch) pair with both P(meet) >= tau;
    if no pair can, stage 2 is lexicographic and service-first: minimise the expected log overshoot of the target
    (how far past the target the waits run, capped at the simulator's saturation; 0.1-unit bins), then expected
    misses, then cost. A department that is beyond help even at capacity ties on overshoot, and its cross-trained
    people then go where they still change an outcome."""
    av = av_from_rows(rows)
    store = int(rows.store_id.iloc[0])
    byd = {int(r.dept_id): r for r in rows.itertuples()}
    if models is None:
        models = {}
        for d, r in byd.items():
            if r.open:
                models[d] = BlockModel(r.demand, r.log_sd, r.std, r.paid, store, params[DEPT_SHORT[d]], r.p_callout,
                                       demand_quantile=demand_quantile)
    result = {}

    def p_of(d, n, ot_used):
        if basis == "submitted":
            return models[d].p_submitted(n)
        return models[d].p_post_callout(n, max(0, av[d]["O"] - ot_used))

    # Pharmacy: independent
    d = 95
    if d in av:
        if av[d]["open"] == 0:
            result[d] = 0
        else:
            cap = av[d]["A"] + av[d]["O"]
            chosen = None
            for nn in range(av[d]["min_staff"], cap + 1):
                fb = fill_block({d: nn}, {d: av[d]})
                if p_of(d, nn, fb[d]["ot"]) >= tau:
                    chosen = nn; break
            result[d] = chosen if chosen is not None else cap
    # FE + Merch jointly
    fe, me = 38, 92
    if fe in av and me in av:
        if av[fe]["open"] == 0 and av[me]["open"] == 0:
            result[fe] = 0; result[me] = 0
        else:
            best = None
            n_fe_range = range(av[fe]["min_staff"], capacity(av[fe]) + 1) if av[fe]["open"] else [0]
            n_me_range = range(av[me]["min_staff"], capacity(av[me]) + 1) if av[me]["open"] else [0]
            # precompute P per head count per dept for each possible OT usage is expensive; OT used depends on flex,
            # so evaluate inside the loop (cheap: fill is O(1), p_post uses a small callout distribution)
            cache = {}
            for nf in n_fe_range:
                for nm in n_me_range:
                    fb = fill_block({fe: nf, me: nm}, {fe: av[fe], me: av[me]})
                    if fb[fe]["infeasible_strict"] or fb[me]["infeasible_strict"]:
                        continue
                    key_f = (fe, nf, fb[fe]["ot"]); key_m = (me, nm, fb[me]["ot"])
                    if key_f not in cache:
                        cache[key_f] = p_of(fe, nf, fb[fe]["ot"]) if av[fe]["open"] else 1.0
                    if key_m not in cache:
                        cache[key_m] = p_of(me, nm, fb[me]["ot"]) if av[me]["open"] else 1.0
                    pf, pm = cache[key_f], cache[key_m]
                    both = (pf >= tau) and (pm >= tau)
                    cost = fb[fe]["cost"] + fb[me]["cost"]
                    if both:
                        score = (0, cost, 0.0)
                    else:
                        # stage 2: tau unreachable for the pair -> minimise expected misses; the small utilization term
                        # breaks ties on the P = 0 plateau toward more heads (staff to capacity), then cost
                        over = 0.0; u_term = 0.0
                        if av[fe]["open"]:
                            over += models[fe].overshoot(nf); u_term += min(models[fe].utilization(nf), 2.0)
                        if av[me]["open"]:
                            over += models[me].overshoot(nm); u_term += min(models[me].utilization(nm), 2.0)
                        # service first: how far past the target the pair runs (0.1 log-unit bins so quadrature noise cannot flip it),
                        # then expected misses, then cost
                        score = (1, round(over, 1), (2 - pf - pm) + 0.002 * u_term, cost)
                    if best is None or score < best[0]:
                        best = (score, nf, nm, pf, pm)
            result[fe], result[me] = best[1], best[2]
    return dict(heads=result, models=models)


# ----------------------------------------------------------------------------- evaluation
def evaluate_plan(blocks: pd.DataFrame, heads: dict, params: dict, tau: float = TAU_DEFAULT, models_cache: dict | None = None,
                  demand_quantile: float | None = None) -> pd.DataFrame:
    """heads: {(store, date, shift, dept): n}. Returns one row per block with fill, cost, P(meet) both bases, flags."""
    rows = []
    for (store, date, shift), trio in blocks.groupby(["store_id", "day_date", "shift_code"], sort=False):
        av = av_from_rows(trio)
        n = {int(r.dept_id): int(heads.get((store, date, shift, int(r.dept_id)), 0)) for r in trio.itertuples()}
        fb = fill_block(n, av)
        for r in trio.itertuples():
            d = int(r.dept_id); f = fb[d]
            if r.open:
                key = (store, date, shift, d)
                m = models_cache.get(key) if models_cache is not None else None
                if m is None:
                    m = BlockModel(r.demand, r.log_sd, r.std, r.paid, int(store), params[DEPT_SHORT[d]], r.p_callout,
                                   demand_quantile=demand_quantile)
                    if models_cache is not None:
                        models_cache[key] = m
                ps = m.p_submitted(n[d]); pp = m.p_post_callout(n[d], max(0, av[d]["O"] - f["ot"]))
                u = m.utilization(n[d])
                ew = n[d] * (1 - r.p_callout * (1 - BACKFILL_Q))  # expected worked heads ignoring the OT cap
            else:
                ps = pp = np.nan; u = np.nan; ew = 0.0
            rows.append(dict(scenario_code=r.scenario_code, store_id=int(store), dept_id=d, dept=r.dept, day_date=date, day_name=r.day_name,
                             day_type=r.day_type, holiday_window_role=r.holiday_window_role, shift_code=shift, shift_seq=r.shift_seq,
                             is_open=int(r.open), paid_hours=r.paid, min_staff=int(r.min_staff), avail_regular=int(r.A), max_ot=int(r.O),
                             flex_avail=int(r.F), capacity_loose=int(r.A + r.F + r.O) if r.open else 0,
                             forecast_demand=float(r.demand), log_sd=float(r.log_sd), required_hours_100=float(r.demand * r.std),
                             p_callout=float(r.p_callout), heads=n[d], reg=f["reg"], flex=f["flex"], ot=f["ot"], unfilled=f["unfilled"],
                             cost=f["cost"], infeasible_strict=f["infeasible_strict"], infeasible_loose=f["infeasible_loose"],
                             below_min=f["below_min"], utilization=u, expected_worked=ew, p_meet_submitted=ps, p_meet_post_callout=pp,
                             meets_tau_submitted=int(ps >= tau) if r.open else np.nan, meets_tau_post=int(pp >= tau) if r.open else np.nan,
                             draft_heads=int(r.draft)))
    return pd.DataFrame(rows)


def summarize(ev: pd.DataFrame) -> dict:
    o = ev[ev.is_open == 1]
    return dict(blocks_open=int(len(o)), heads=int(o.heads.sum()), labor_hours=float((o.heads * o.paid_hours).sum()),
                cost=float(o.cost.sum()), cost_regular=float((o.reg * o.paid_hours * 0).sum()),  # placeholder replaced below
                reg_heads=int(o.reg.sum()), flex_heads=int(o.flex.sum()), ot_heads=int(o.ot.sum()),
                exp_missed_submitted=float((1 - o.p_meet_submitted).sum()), exp_missed_post=float((1 - o.p_meet_post_callout).sum()),
                avg_p_submitted=float(o.p_meet_submitted.mean()), avg_p_post=float(o.p_meet_post_callout.mean()),
                blocks_below_tau_submitted=int((o.meets_tau_submitted == 0).sum()), blocks_below_tau_post=int((o.meets_tau_post == 0).sum()),
                infeasible_strict=int(o.infeasible_strict.sum()), infeasible_loose=int(o.infeasible_loose.sum()),
                below_min=int(o.below_min.sum()))


def cost_split(ev: pd.DataFrame) -> dict:
    o = ev[ev.is_open == 1]
    # recover rates from cost: cost = (reg+flex)*paid*rr + ot*paid*ro ; we carry rr/ro via blocks in callers; here approximate
    return dict(reg_flex_hours=float(((o.reg + o.flex) * o.paid_hours).sum()), ot_hours=float((o.ot * o.paid_hours).sum()))


def load_rates(out_dir: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(out_dir, "04_callout_rates.csv"))
