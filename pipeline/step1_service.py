"""
step1_service.py - Service-response model (Phase 1, Step 1).

Utilization per historical block = shift_demand x labor standard / WORKED labor hours
(docs/DATA_DICTIONARY.md: worked_employees "drives the service outcome").

Per department we fit metric_value vs utilization with three forms and choose by
leave-one-week-out cross-validation:
  (a) queueing   m = a + b / (1 - u/c), c fitted
  (b) exponential m = a * exp(b u)   (fit as log m = log a + b u)
  (c) binned / isotonic (monotone step curve)
plus variants with warehouse (store) terms.  Noise is modelled on the log scale,
with the residual sd allowed to grow linearly with utilization.
P(meet | u, store, dept) = Phi( (log target - log m_hat(u)) / sigma(u) ).

Writes:
  outputs/01_service_blocks.csv        every open historical block with utilization, fitted value, P(meet)
  outputs/01_service_cv.csv            CV results (all candidate models, per dept)
  outputs/01_service_params.json       chosen model parameters per dept (used by later steps)
  outputs/01_service_thresholds.csv    utilization where P(meet) crosses 95/90/80% by dept x store, with 90% bootstrap bands
  outputs/01_service_sigma.csv         residual sd by utilization band and the fitted sigma(u)
  outputs/01_service_endogeneity.csv   callout-shock check (residuals in blocks with vs without callouts)
  outputs/01_service_curve.png         slide chart
"""
from __future__ import annotations

import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.stats import norm
from sklearn.isotonic import IsotonicRegression
from common import load_all, hist_frame, DEPT_SHORT, SEED

U_FIT_MAX = 0.97   # the simulator saturates above ~0.95-1.0; the decision range is below this
TARGET = {38: 5.0, 92: 60.0, 95: 20.0}


# ----------------------------------------------------------------------------- model forms
def fit_exp(u, logm, store=None, slope_by_store=False):
    """log m = a + b u (+ store intercepts) via least squares. Returns dict of params."""
    X = [np.ones_like(u), u]
    names = ["a", "b"]
    if store is not None:
        for s in (2, 4):
            X.append((store == s).astype(float)); names.append(f"int_{s}")
            if slope_by_store:
                X.append((store == s).astype(float) * u); names.append(f"slope_{s}")
    X = np.column_stack(X)
    beta, *_ = np.linalg.lstsq(X, logm, rcond=None)
    return dict(zip(names, beta))


def pred_exp(p, u, store=None):
    out = p["a"] + p["b"] * u
    if store is not None:
        for s in (2, 4):
            if f"int_{s}" in p:
                out = out + p[f"int_{s}"] * (store == s)
            if f"slope_{s}" in p:
                out = out + p[f"slope_{s}"] * (store == s) * u
    return out  # log scale


def fit_queue(u, logm, store=None):
    """log( a + b/(1 - u/c) ) fitted to log m by nonlinear LS; optional multiplicative store factors."""
    def model(theta, u, store):
        a, b, c = theta[0], theta[1], theta[2]
        base = a + b / np.clip(1.0 - u / c, 1e-3, None)
        f = np.log(np.clip(base, 1e-6, None))
        if store is not None:
            f = f + theta[3] * (store == 2) + theta[4] * (store == 4)
        return f
    def resid(theta):
        return model(theta, u, store) - logm
    x0 = [0.5, 0.2, 1.05] + ([0.0, 0.0] if store is not None else [])
    lb = [0.0, 1e-4, 0.90] + ([-2, -2] if store is not None else [])
    ub = [50.0, 50.0, 1.60] + ([2, 2] if store is not None else [])
    r = least_squares(resid, x0, bounds=(lb, ub), loss="linear", max_nfev=20000)
    th = r.x
    p = dict(a=th[0], b=th[1], c=th[2])
    if store is not None:
        p["int_2"], p["int_4"] = th[3], th[4]
    return p


def pred_queue(p, u, store=None):
    base = p["a"] + p["b"] / np.clip(1.0 - u / p["c"], 1e-3, None)
    f = np.log(np.clip(base, 1e-6, None))
    if store is not None and "int_2" in p:
        f = f + p["int_2"] * (store == 2) + p["int_4"] * (store == 4)
    f = np.where(u >= p["c"], np.log(1e6), f)  # at/above capacity: service collapses
    return f


class IsoModel:
    def __init__(self, u, logm):
        self.ir = IsotonicRegression(increasing=True, out_of_bounds="clip").fit(u, logm)
    def predict(self, u):
        return self.ir.predict(u)


def fit_sigma(u, resid):
    """Residual sd as a linear function of utilization: sigma(u) = s0 + s1 * u, fitted on |resid|
    (E|e| = sigma * sqrt(2/pi) for normal errors)."""
    X = np.column_stack([np.ones_like(u), u])
    beta, *_ = np.linalg.lstsq(X, np.abs(resid) * np.sqrt(np.pi / 2), rcond=None)
    s0, s1 = beta
    return float(s0), float(s1)


def sigma_of(s0, s1, u, floor=0.05):
    return np.clip(s0 + s1 * np.asarray(u, float), floor, None)


def p_meet(logm_hat, sigma, target):
    return norm.cdf((np.log(target) - logm_hat) / sigma)


# ----------------------------------------------------------------------------- CV harness
def cv_dept(x: pd.DataFrame):
    """Leave-one-week-out CV for all candidate models on one department. Returns rows."""
    rows = []
    weeks = sorted(x.week_idx.unique())
    cands = ["queue", "queue+store", "exp", "exp+store", "exp+store_slope", "isotonic"]
    preds = {c: np.full(len(x), np.nan) for c in cands}
    sig = {c: np.full(len(x), np.nan) for c in cands}
    for w in weeks:
        tr = x.week_idx != w; te = ~tr
        u_tr, m_tr, s_tr = x.utilization.values[tr], np.log(x.metric_value.values[tr]), x.store_id.values[tr]
        u_te, s_te = x.utilization.values[te], x.store_id.values[te]
        fits = {}
        p = fit_queue(u_tr, m_tr); fits["queue"] = (lambda u, s, p=p: pred_queue(p, u))
        p = fit_queue(u_tr, m_tr, s_tr); fits["queue+store"] = (lambda u, s, p=p: pred_queue(p, u, s))
        p = fit_exp(u_tr, m_tr); fits["exp"] = (lambda u, s, p=p: pred_exp(p, u))
        p = fit_exp(u_tr, m_tr, s_tr); fits["exp+store"] = (lambda u, s, p=p: pred_exp(p, u, s))
        p = fit_exp(u_tr, m_tr, s_tr, True); fits["exp+store_slope"] = (lambda u, s, p=p: pred_exp(p, u, s))
        iso = IsoModel(u_tr, m_tr); fits["isotonic"] = (lambda u, s, iso=iso: iso.predict(u))
        for c, f in fits.items():
            fhat_tr = f(u_tr, s_tr)
            s0, s1 = fit_sigma(u_tr, m_tr - fhat_tr)
            preds[c][te] = f(u_te, s_te)
            sig[c][te] = sigma_of(s0, s1, u_te)
    logm = np.log(x.metric_value.values); target = TARGET[int(x.dept_id.iloc[0])]
    met = x.met_target.values.astype(float)
    for c in cands:
        e = preds[c] - logm
        pm = p_meet(preds[c], sig[c], target)
        pm_c = np.clip(pm, 1e-6, 1 - 1e-6)
        rows.append(dict(dept=x.dept.iloc[0], model=c,
                         rmse_log=float(np.sqrt(np.mean(e ** 2))),
                         mae_minutes=float(np.mean(np.abs(np.exp(preds[c]) - x.metric_value.values))),
                         brier_pmeet=float(np.mean((pm - met) ** 2)),
                         logloss_pmeet=float(-np.mean(met * np.log(pm_c) + (1 - met) * np.log(1 - pm_c))),
                         n=int(len(x))))
    return rows, preds, sig


def fit_final(x: pd.DataFrame, model: str):
    u, logm, s = x.utilization.values, np.log(x.metric_value.values), x.store_id.values
    if model == "queue":
        p = fit_queue(u, logm); f = lambda uu, ss, p=p: pred_queue(p, uu)
    elif model == "queue+store":
        p = fit_queue(u, logm, s); f = lambda uu, ss, p=p: pred_queue(p, uu, ss)
    elif model == "exp":
        p = fit_exp(u, logm); f = lambda uu, ss, p=p: pred_exp(p, uu)
    elif model == "exp+store":
        p = fit_exp(u, logm, s); f = lambda uu, ss, p=p: pred_exp(p, uu, ss)
    elif model == "exp+store_slope":
        p = fit_exp(u, logm, s, True); f = lambda uu, ss, p=p: pred_exp(p, uu, ss)
    else:
        raise ValueError(model)
    s0, s1 = fit_sigma(u, logm - f(u, s))
    p = {k: float(v) for k, v in p.items()}
    p["sigma0"], p["sigma1"], p["model"] = s0, s1, model
    return p, f


def predict_logm(p: dict, u, store):
    u = np.asarray(u, float); store = np.asarray(store)
    if p["model"].startswith("queue"):
        return pred_queue(p, u, store if "int_2" in p else None)
    return pred_exp(p, u, store if "int_2" in p else None)


def pmeet_from_params(p: dict, u, store, target):
    lm = predict_logm(p, u, store)
    sg = sigma_of(p["sigma0"], p["sigma1"], u)
    return p_meet(lm, sg, target)


def threshold_u(p: dict, store: int, target: float, level: float, lo=0.3, hi=1.2):
    """Smallest utilization at which P(meet) falls below `level` (bisection on a monotone curve)."""
    grid = np.linspace(lo, hi, 1801)
    pm = pmeet_from_params(p, grid, np.full_like(grid, store), target)
    below = np.where(pm < level)[0]
    return float(grid[below[0]]) if len(below) else np.nan


# ----------------------------------------------------------------------------- main
def run(data_dir: str, out_dir: str, make_chart: bool = True) -> dict:
    rng = np.random.default_rng(SEED)
    tabs = load_all(data_dir); h = hist_frame(tabs)
    o = h[(h.is_open == 1) & h.metric_value.notna()].copy()
    fit_set = o[o.utilization <= U_FIT_MAX].copy()

    # sanity: does WORKED-hours utilization explain service better than SCHEDULED-hours utilization?
    chk = []
    for d, x in fit_set.groupby("dept"):
        for col in ["utilization", "sched_utilization"]:
            p = fit_exp(x[col].values, np.log(x.metric_value.values))
            e = np.log(x.metric_value.values) - pred_exp(p, x[col].values)
            chk.append(dict(dept=d, utilization_basis=col, rmse_log=float(np.sqrt(np.mean(e ** 2)))))
    pd.DataFrame(chk).to_csv(os.path.join(out_dir, "01_service_worked_vs_scheduled.csv"), index=False)

    # CV
    cv_rows, chosen, params = [], {}, {}
    for dept_id, x in fit_set.groupby("dept_id"):
        rows, preds, sig = cv_dept(x.reset_index(drop=True))
        cv_rows += rows
    cv = pd.DataFrame(cv_rows)
    # choose by CV log-loss of P(meet) (the quantity we act on), tie-break by rmse_log
    for d, g in cv.groupby("dept"):
        g = g.sort_values(["logloss_pmeet", "rmse_log"])
        chosen[d] = g.model.iloc[0]
    cv["chosen"] = cv.apply(lambda r: r.model == chosen[r.dept], axis=1)
    cv.to_csv(os.path.join(out_dir, "01_service_cv.csv"), index=False)

    # final fits (parametric only; if isotonic wins we still need a parametric curve to extrapolate, so we
    # record it and fall back to the best parametric model)
    final = {}
    for dept_id, x in fit_set.groupby("dept_id"):
        d = DEPT_SHORT[dept_id]
        m = chosen[d]
        if m == "isotonic":
            g = cv[(cv.dept == d) & (cv.model != "isotonic")].sort_values(["logloss_pmeet", "rmse_log"])
            m = g.model.iloc[0]
        p, f = fit_final(x, m)
        p["dept_id"] = int(dept_id); p["target"] = TARGET[dept_id]; p["cv_choice"] = chosen[d]
        p["u_fit_max"] = U_FIT_MAX; p["n_fit"] = int(len(x))
        final[d] = p
    with open(os.path.join(out_dir, "01_service_params.json"), "w") as fh:
        json.dump(final, fh, indent=2)

    # fitted values & P(meet) for every open block
    o["logm_hat"] = np.nan; o["sigma_u"] = np.nan; o["p_meet"] = np.nan
    for d, p in final.items():
        m = o.dept == d
        o.loc[m, "logm_hat"] = predict_logm(p, o.loc[m, "utilization"].values, o.loc[m, "store_id"].values)
        o.loc[m, "sigma_u"] = sigma_of(p["sigma0"], p["sigma1"], o.loc[m, "utilization"].values)
        o.loc[m, "p_meet"] = p_meet(o.loc[m, "logm_hat"].values, o.loc[m, "sigma_u"].values, p["target"])
    o["metric_hat"] = np.exp(o.logm_hat)
    o["log_resid"] = np.log(o.metric_value) - o.logm_hat
    keep = ["store_id", "dept_id", "dept", "day_date", "day_name", "day_type", "holiday_window_role", "shift_code", "week_idx",
            "shift_demand_units", "required_hours_100", "paid_hours", "scheduled_employees", "callout_employees",
            "backfill_employees", "worked_employees", "worked_labor_hours", "utilization", "sched_utilization",
            "metric_value", "target_value", "met_target", "metric_hat", "sigma_u", "p_meet", "log_resid", "labor_cost"]
    o[keep].to_csv(os.path.join(out_dir, "01_service_blocks.csv"), index=False)

    # residual spread by utilization band + the fitted sigma(u)
    fs = o[o.utilization <= U_FIT_MAX].copy()
    fs["u_band"] = (np.floor(fs.utilization * 20) / 20).round(2)
    sg = fs.groupby(["dept", "u_band"]).agg(n=("log_resid", "size"), resid_sd=("log_resid", "std"),
                                            resid_mean=("log_resid", "mean")).reset_index()
    sg["sigma_fitted"] = [sigma_of(final[d]["sigma0"], final[d]["sigma1"], u)[()] if False else
                          float(sigma_of(final[d]["sigma0"], final[d]["sigma1"], np.array([u]))[0]) for d, u in zip(sg.dept, sg.u_band)]
    # slope test: does |resid| grow with u?
    for d in final:
        x = fs[fs.dept == d]
        r = np.corrcoef(x.utilization, np.abs(x.log_resid))[0, 1]
        final[d]["corr_absresid_u"] = float(r)
    sg.to_csv(os.path.join(out_dir, "01_service_sigma.csv"), index=False)
    with open(os.path.join(out_dir, "01_service_params.json"), "w") as fh:
        json.dump(final, fh, indent=2)

    # thresholds with bootstrap bands (resample blocks within dept, refit chosen model)
    rows = []
    B = 400
    for dept_id, x in fit_set.groupby("dept_id"):
        d = DEPT_SHORT[dept_id]; p = final[d]; model = p["model"]
        boots = {s: {lv: [] for lv in (0.95, 0.90, 0.80)} for s in (1, 2, 4)}
        xv = x.reset_index(drop=True)
        for b in range(B):
            idx = rng.integers(0, len(xv), len(xv))
            pb, _ = fit_final(xv.iloc[idx], model)
            for s in (1, 2, 4):
                for lv in (0.95, 0.90, 0.80):
                    boots[s][lv].append(threshold_u(pb, s, TARGET[dept_id], lv))
        for s in (1, 2, 4):
            for lv in (0.95, 0.90, 0.80):
                arr = np.array(boots[s][lv]); arr = arr[~np.isnan(arr)]
                rows.append(dict(dept=d, dept_id=int(dept_id), store_id=s, p_meet_level=lv,
                                 u_threshold=threshold_u(p, s, TARGET[dept_id], lv),
                                 ci90_lo=float(np.percentile(arr, 5)), ci90_hi=float(np.percentile(arr, 95)),
                                 n_boot=int(len(arr))))
    th = pd.DataFrame(rows)
    th.to_csv(os.path.join(out_dir, "01_service_thresholds.csv"), index=False)

    # endogeneity check: callouts are unplanned shocks to worked hours. If the curve is causal, blocks hit by callouts
    # (utilization pushed up by chance) should sit on the same curve as blocks that were not.
    e = fs.copy(); e["had_callout"] = (e.callout_employees > 0).astype(int)
    e["net_shock"] = e.callout_employees - e.backfill_employees
    endo = e.groupby(["dept", "had_callout"]).agg(n=("log_resid", "size"), mean_log_resid=("log_resid", "mean"),
                                                   sd=("log_resid", "std"), mean_u=("utilization", "mean")).reset_index()
    # t-stat of the difference in mean residual
    tstats = []
    for d, g in e.groupby("dept"):
        a = g[g.had_callout == 1].log_resid; b = g[g.had_callout == 0].log_resid
        se = np.sqrt(a.var() / len(a) + b.var() / len(b))
        tstats.append(dict(dept=d, diff_mean_log_resid=float(a.mean() - b.mean()), t_stat=float((a.mean() - b.mean()) / se),
                           corr_resid_netshock=float(np.corrcoef(g.net_shock, g.log_resid)[0, 1]),
                           corr_resid_schedUtil_given_u=float(np.corrcoef(g.sched_utilization - g.utilization, g.log_resid)[0, 1])))
    endo = endo.merge(pd.DataFrame(tstats), on="dept", how="left")
    endo.to_csv(os.path.join(out_dir, "01_service_endogeneity.csv"), index=False)

    if make_chart:
        chart(o, final, th, out_dir)
    return dict(cv=cv, params=final, thresholds=th, blocks=o, sigma=sg, endo=endo)


def chart(o: pd.DataFrame, final: dict, th: pd.DataFrame, out_dir: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.2), gridspec_kw=dict(height_ratios=[1.15, 1]))
    grid = np.linspace(0.45, 1.05, 400)
    colors = {1: "#1f5f8b", 2: "#c0504d", 4: "#4e8542"}
    for j, d in enumerate(["FE", "Merch", "Pharm"]):
        p = final[d]; x = o[o.dept == d]
        ax = axes[0, j]
        for s in (1, 2, 4):
            pm = pmeet_from_params(p, grid, np.full_like(grid, s), p["target"])
            ax.plot(grid, pm, color=colors[s], lw=2, label=f"Warehouse {s}")
            t90 = th[(th.dept == d) & (th.store_id == s) & (th.p_meet_level == 0.90)].u_threshold.iloc[0]
            ax.axvline(t90, color=colors[s], lw=0.8, ls=":")
        # historical blocks as dots: y = met_target jittered
        jit = (np.random.default_rng(1).uniform(-0.03, 0.03, len(x)))
        ax.scatter(x.utilization, x.met_target + jit, s=9, alpha=0.45,
                   c=[colors[s] for s in x.store_id], edgecolor="none")
        ax.axhline(0.90, color="black", lw=0.8, ls="--")
        ax.set_xlim(0.45, 1.05); ax.set_ylim(-0.08, 1.08)
        ax.set_title(f"{d}: P(meet target) vs utilization", fontsize=11)
        ax.set_xlabel("Utilization = demand hours / worked hours"); ax.set_ylabel("P(meet)")
        if j == 0:
            ax.legend(loc="lower left", fontsize=8, frameon=False)
        ax.text(0.47, 0.93, "dots: historical blocks (1 = met, 0 = missed)\ndotted: 90% threshold per warehouse", fontsize=7.5, va="top")
        ax2 = axes[1, j]
        for s in (1, 2, 4):
            lm = predict_logm(p, grid, np.full_like(grid, s))
            ax2.plot(grid, np.exp(lm), color=colors[s], lw=1.8)
        ax2.scatter(x.utilization, x.metric_value, s=9, alpha=0.45, c=[colors[s] for s in x.store_id], edgecolor="none")
        ax2.axhline(p["target"], color="black", lw=0.9, ls="--")
        ax2.set_yscale("log"); ax2.set_xlim(0.45, 1.05)
        ax2.set_ylim(0.8 * x.metric_value.min(), 2.0 * x.metric_value.max())
        ax2.axvspan(0.85, 0.90, color="#f4c7c3", alpha=0.35, lw=0)
        ax2.text(0.875, 0.9 * x.metric_value.min(), "cliff", ha="center", fontsize=8, color="#8b1a1a")
        ax2.set_xlabel("Utilization"); ax2.set_ylabel("service metric (minutes, log scale)")
        ax2.set_title(f"{d}: fitted curve ({p['model']}), target = {p['target']:g} min", fontsize=10)
    fig.suptitle("Service degrades gradually, then falls off a cliff near 85-90% utilization", fontsize=13, y=0.995)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "01_service_curve.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    res = run(sys.argv[1], sys.argv[2])
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
    print(res["cv"].round(4).to_string(index=False))
    print(json.dumps(res["params"], indent=1))
    print(res["thresholds"].round(3).to_string(index=False))
    print(res["sigma"].round(3).to_string(index=False))
    print(res["endo"].round(3).to_string(index=False))
