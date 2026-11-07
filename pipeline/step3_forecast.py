"""
step3_forecast.py - Planning-week demand forecast (Phase 1, Step 3).

Daily model (warehouse x dept x date), multiplicative and transparent:
    demand = level(warehouse, dept)  x  weekday profile(dept, weekday)  x  holiday factor(dept, window role)
             x  Valentine's factor (explicit assumption)
estimated by log-linear least squares with a separate level for every warehouse x dept x week
(so the weekday profile and holiday factors come from WITHIN-week contrasts only). The planning-week
level is the mean of the six weekly levels (a trend is tested and used only if significant).
Analogs: Pre_MLK_Weekend (Fri-Sun) -> Pre_Presidents_Day_Weekend (Fri-Sun); MLK_Holiday (Mon) ->
Presidents_Day_Holiday (Mon); the Tuesday after MLK (flagged is_post_holiday_rebound) -> Tue Feb 17.
Shift split: learned shares by dept x day type x (holiday window or not).
80% prediction intervals by simulation of (weekly level noise) x (holiday-transfer uncertainty) x (shift-share noise).

Writes:
  outputs/03_factors.csv                weekday profile and holiday factors (with SE)
  outputs/03_weekly_levels.csv          estimated level per warehouse x dept x week, trend test
  outputs/03_shift_shares.csv           learned shift shares (mean, sd, n)
  outputs/03_forecast_daily.csv         planning-week daily forecast, BASE and PEAK, point + 80% PI
  outputs/03_forecast_shift.csv         planning-week shift forecast, all scenarios, point + 80% PI
  outputs/03_backtest.csv               rolling-origin + holdout results vs naive benchmark
  outputs/03_valentine_sensitivity.csv  low/mid/high Valentine's assumption, daily demand impact
  outputs/03_forecast.png               chart
"""
from __future__ import annotations

import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from scipy import stats
from common import load_all, hist_frame, planning_grid, DEPT_SHORT, SEED, wape, mape, day_type_of

DOW_NAMES = ["Thursday", "Friday", "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday"]
ROLES = ["Post_New_Year_Rebound", "Pre_MLK_Weekend", "MLK_Holiday"]
ANALOG = {"Pre_Presidents_Day_Weekend": "Pre_MLK_Weekend", "Presidents_Day_Holiday": "MLK_Holiday", "Normal": None}

# ---- explicit assumptions (see assumptions table) ----
VALENTINE = {  # multiplicative lift on top of the pre-holiday-weekend factor; dept -> {date: factor}
    "low":  {38: {"2026-02-13": 1.00, "2026-02-14": 1.00}, 92: {"2026-02-14": 1.00}, 95: {}},
    "mid":  {38: {"2026-02-13": 1.02, "2026-02-14": 1.05}, 92: {"2026-02-14": 1.03}, 95: {}},
    "high": {38: {"2026-02-13": 1.04, "2026-02-14": 1.10}, 92: {"2026-02-14": 1.06}, 95: {}},
}
HOLIDAY_TRANSFER_SD = 0.05   # log-sd on holiday-window days for "Presidents' Day may differ from MLK"
N_SIM = 20000


# ----------------------------------------------------------------------------- daily data
def daily_history(h: pd.DataFrame) -> pd.DataFrame:
    d = h[h.shift_seq == 1][["store_id", "dept_id", "dept", "day_date", "day_name", "day_of_week", "week_idx",
                             "holiday_window_role", "is_costco_closed", "temperature", "has_promotion",
                             "daily_demand_units"]].copy()
    d = d.rename(columns={"daily_demand_units": "demand"})
    d["post_mlk_tue"] = (d.day_date == pd.Timestamp("2026-01-20")).astype(int)
    d["series"] = d.store_id.astype(str) + "-" + d.dept_id.astype(str)
    d["swk"] = d.series + "-w" + d.week_idx.astype(str)
    return d.sort_values(["store_id", "dept_id", "day_date"]).reset_index(drop=True)


def design(d: pd.DataFrame, swk_levels, with_temp=False):
    """Design matrix: series-week levels + dept x weekday (Thu ref) + dept x holiday role + dept x post-MLK-Tue."""
    cols, names = [], []
    for s in swk_levels:
        cols.append((d.swk == s).astype(float).values); names.append("lvl|" + s)
    for dept in (38, 92, 95):
        m = (d.dept_id == dept).values.astype(float)
        for dn in DOW_NAMES[1:]:
            cols.append(m * (d.day_name == dn).values); names.append(f"dow|{dept}|{dn}")
        for r in ROLES:
            cols.append(m * (d.holiday_window_role == r).values); names.append(f"role|{dept}|{r}")
        cols.append(m * d.post_mlk_tue.values); names.append(f"postmlk|{dept}")
        if with_temp:
            cols.append(m * (d.temperature.values - 50.0)); names.append(f"temp|{dept}")
    X = np.column_stack(cols)
    return X, names


def fit_daily(d: pd.DataFrame, with_temp=False):
    d = d[d.is_costco_closed == 0].copy()
    swk_levels = sorted(d.swk.unique())
    X, names = design(d, swk_levels, with_temp)
    y = np.log(d.demand.values)
    beta, res, rank, sv = np.linalg.lstsq(X, y, rcond=None)
    fitted = X @ beta
    resid = y - fitted
    n, k = X.shape
    dof = max(n - rank, 1)
    s2 = float(resid @ resid / dof)
    XtX_inv = np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.clip(np.diag(XtX_inv) * s2, 0, None))
    coef = pd.DataFrame(dict(name=names, coef=beta, se=se))
    coef["kind"] = coef.name.str.split("|").str[0]
    return dict(coef=coef, resid=resid, fitted=fitted, y=y, data=d, s2=s2, rank=rank, n=n, dof=dof)


def coef_lookup(coef: pd.DataFrame):
    return dict(zip(coef.name, coef.coef))


def weekly_levels(fit) -> pd.DataFrame:
    c = fit["coef"]; lv = c[c.kind == "lvl"].copy()
    parts = lv.name.str.split("|").str[1].str.split("-", expand=True)
    lv["store_id"] = parts[0].astype(int); lv["dept_id"] = parts[1].astype(int)
    lv["week_idx"] = parts[2].str[1:].astype(int)
    lv["dept"] = lv.dept_id.map(DEPT_SHORT)
    lv = lv[["store_id", "dept_id", "dept", "week_idx", "coef"]].rename(columns={"coef": "log_level"})
    lv["series_mean"] = lv.groupby(["store_id", "dept_id"]).log_level.transform("mean")
    lv["dev"] = lv.log_level - lv.series_mean
    lv["level_index"] = np.exp(lv.dev)
    return lv.sort_values(["store_id", "dept_id", "week_idx"]).reset_index(drop=True)


def trend_test(lv: pd.DataFrame):
    """Regress weekly deviation on week index (series fixed effects already removed)."""
    x = lv.week_idx.values.astype(float); y = lv.dev.values
    sl, ic, r, p, se = stats.linregress(x, y)
    # also on the 6 cross-series mean deviations (the honest df)
    m = lv.groupby("week_idx").dev.mean()
    sl2, ic2, r2, p2, se2 = stats.linregress(m.index.values.astype(float), m.values)
    return dict(slope_per_week=float(sl), se=float(se), p_value=float(p),
                slope_per_week_weekmeans=float(sl2), se_weekmeans=float(se2), p_value_weekmeans=float(p2),
                sd_week_dev_all=float(lv.dev.std(ddof=1)),
                sd_week_dev_common=float(m.std(ddof=1)))


def shift_shares(h: pd.DataFrame) -> pd.DataFrame:
    o = h[h.is_open == 1].copy()
    o["window"] = np.where(o.holiday_window_role == "Normal", "Normal", "HolWin")
    g = o.groupby(["dept_id", "dept", "day_type", "window", "shift_code"]).shift_share_of_day.agg(
        ["mean", "std", "count"]).reset_index().rename(columns={"mean": "share", "std": "share_sd", "count": "n"})
    g["share_sd"] = g.share_sd.fillna(0.0)
    return g


# ----------------------------------------------------------------------------- forecasting core
def predict_daily(fit, lv: pd.DataFrame, rows: pd.DataFrame, level_mode="mean", valentine="mid",
                  trend=None, role_fallback: dict | None = None) -> pd.DataFrame:
    """rows: store_id, dept_id, day_date, day_name, holiday_window_role, is_post_holiday_rebound.
    Returns log point forecast decomposition."""
    cl = coef_lookup(fit["coef"])
    out = []
    for r in rows.itertuples(index=False):
        s = lv[(lv.store_id == r.store_id) & (lv.dept_id == r.dept_id)]
        if level_mode == "mean":
            lvl = s.log_level.mean()
        elif level_mode == "last4":
            lvl = s.sort_values("week_idx").log_level.tail(4).mean()
        elif level_mode == "trend":
            lvl = s.log_level.mean() + trend * (r.week_idx - s.week_idx.mean())
        else:
            raise ValueError(level_mode)
        dow = cl.get(f"dow|{r.dept_id}|{r.day_name}", 0.0)
        role_src = ANALOG.get(r.holiday_window_role, r.holiday_window_role)
        if role_src and f"role|{r.dept_id}|{role_src}" not in cl and role_fallback and role_src in role_fallback:
            role_src = role_fallback[role_src]      # backtest: the held-out week holds the only example of this role
        hol = cl.get(f"role|{r.dept_id}|{role_src}", 0.0) if role_src else 0.0
        post = cl.get(f"postmlk|{r.dept_id}", 0.0) if getattr(r, "is_post_holiday_rebound", 0) == 1 and r.holiday_window_role == "Normal" else 0.0
        val = np.log(VALENTINE[valentine][r.dept_id].get(str(pd.Timestamp(r.day_date).date()), 1.0))
        out.append(dict(store_id=r.store_id, dept_id=r.dept_id, day_date=r.day_date, day_name=r.day_name,
                        holiday_window_role=r.holiday_window_role, log_level=lvl, dow_effect=dow, holiday_effect=hol,
                        post_holiday_effect=post, valentine_effect=val,
                        log_point=lvl + dow + hol + post + val))
    o = pd.DataFrame(out); o["point"] = np.exp(o.log_point)
    return o


def naive_same_weekday(train: pd.DataFrame, rows: pd.DataFrame, n_weeks=4, exclude_closed=True) -> np.ndarray:
    """Organizers' benchmark recipe: mean of the same weekday over the last n_weeks training weeks, no holiday logic."""
    wk = sorted(train.week_idx.unique())[-n_weeks:]
    t = train[train.week_idx.isin(wk)]
    if exclude_closed:
        t = t[t.is_costco_closed == 0]
    m = t.groupby(["store_id", "dept_id", "day_name"]).demand.mean()
    return np.array([m.get((r.store_id, r.dept_id, r.day_name), np.nan) for r in rows.itertuples(index=False)])


def split_to_shifts(daily: pd.DataFrame, shares: pd.DataFrame, grid_rows: pd.DataFrame) -> pd.DataFrame:
    """grid_rows: one row per block (store, dept, date, shift, day_type, holiday_window_role, is_open)."""
    g = grid_rows.copy()
    g["window"] = np.where(g.holiday_window_role == "Normal", "Normal", "HolWin")
    g = g.merge(shares[["dept_id", "day_type", "window", "shift_code", "share", "share_sd"]],
                on=["dept_id", "day_type", "window", "shift_code"], how="left")
    g["share"] = np.where(g.is_open == 1, g.share.fillna(0.0), 0.0)
    g["share_sd"] = np.where(g.is_open == 1, g.share_sd.fillna(0.0), 0.0)
    g = g.merge(daily[["store_id", "dept_id", "day_date", "point"]].rename(columns={"point": "daily_point"}),
                on=["store_id", "dept_id", "day_date"], how="left")
    g["shift_point"] = g.daily_point * g.share
    return g


# ----------------------------------------------------------------------------- main
def run(data_dir: str, out_dir: str, make_chart=True) -> dict:
    rng = np.random.default_rng(SEED)
    tabs = load_all(data_dir); h = hist_frame(tabs); grid = planning_grid(tabs)
    d = daily_history(h)

    # ---- fit on all six weeks
    fit = fit_daily(d)
    fit_t = fit_daily(d, with_temp=True)
    coef = fit["coef"].copy()
    coef["factor"] = np.exp(coef.coef)
    coef_out = coef[coef.kind != "lvl"].copy()
    tcoef = fit_t["coef"]; tcoef = tcoef[tcoef.kind == "temp"].copy()
    temp_identified = fit_t["rank"] > fit["rank"]
    tcoef["note"] = ("tested only; not used" if temp_identified else
                     "NOT identified: temperature is an exact linear function of weekday within each week (collinear)")
    if not temp_identified:
        tcoef["coef"] = np.nan; tcoef["se"] = np.nan
    coef_out = pd.concat([coef_out, tcoef.assign(factor=np.exp(tcoef.coef))], ignore_index=True)
    coef_out["dept"] = coef_out.name.str.split("|").str[1].astype(int).map(DEPT_SHORT)
    coef_out["term"] = coef_out.name.str.split("|").str[2].fillna("")
    coef_out["t_stat"] = coef_out.coef / coef_out.se.replace(0, np.nan)
    coef_out.to_csv(os.path.join(out_dir, "03_factors.csv"), index=False)
    fit_stats = dict(n_obs=int(fit["n"]), n_params=int(fit["rank"]), temp_identified=bool(temp_identified),
                     rank_with_temp=int(fit_t["rank"]), resid_sd_log=float(np.sqrt(fit["s2"])),
                     resid_max_abs=float(np.abs(fit["resid"]).max()),
                     r2_within=float(1 - fit["resid"].var() / fit["y"].var()))

    lv = weekly_levels(fit)
    tt = trend_test(lv)
    lv.to_csv(os.path.join(out_dir, "03_weekly_levels.csv"), index=False)
    shares = shift_shares(h)
    shares.to_csv(os.path.join(out_dir, "03_shift_shares.csv"), index=False)

    # ---- planning-week daily forecast (BASE)
    gb = grid[grid.scenario_code == "BASE"]
    rows = gb[gb.shift_seq == 1][["store_id", "dept_id", "day_date", "day_name", "holiday_window_role",
                                  "is_post_holiday_rebound"]].copy()
    rows["week_idx"] = 7
    level_mode = "trend" if tt["p_value_weekmeans"] < 0.10 else "mean"
    daily = predict_daily(fit, lv, rows, level_mode=level_mode, valentine="mid", trend=tt["slope_per_week_weekmeans"])
    daily["dept"] = daily.dept_id.map(DEPT_SHORT)
    daily["level_mode"] = level_mode

    # benchmark for comparison
    bench = tabs["PlanningWeek_BenchmarkForecast"][["store_id", "dept_id", "day_date", "predicted_transaction_count_proxy"]]
    daily = daily.merge(bench.rename(columns={"predicted_transaction_count_proxy": "benchmark"}), on=["store_id", "dept_id", "day_date"], how="left")
    daily["ratio_to_benchmark"] = daily.point / daily.benchmark

    # ---- simulation for PIs (daily and shift), BASE
    blocks = gb[["store_id", "dept_id", "day_date", "day_name", "day_type", "holiday_window_role", "shift_code", "shift_seq",
                 "is_open", "paid_hours", "min_staff"]].copy()
    sp = split_to_shifts(daily, shares, blocks)
    sd_week = tt["sd_week_dev_all"]
    # simulate: per (store,dept) weekly level draw; holiday transfer draw per dept x role; share noise per block
    nb = len(sp)
    series_idx = (sp.store_id.astype(str) + "-" + sp.dept_id.astype(str)).astype("category").cat.codes.values
    n_series = series_idx.max() + 1
    is_hol = (sp.holiday_window_role != "Normal").values
    dept_role_key = (sp.dept_id.astype(str) + "|" + sp.holiday_window_role.astype(str)).astype("category").cat.codes.values
    n_dr = dept_role_key.max() + 1
    lvl_draw = rng.normal(0, sd_week, size=(N_SIM, n_series))[:, series_idx]
    hol_draw = rng.normal(0, HOLIDAY_TRANSFER_SD, size=(N_SIM, n_dr))[:, dept_role_key] * is_hol
    share_mean = sp.share.values; share_sd = sp.share_sd.values
    share_draw = share_mean + rng.normal(0, 1, size=(N_SIM, nb)) * share_sd
    share_draw = np.clip(share_draw, 0.02, None) * (share_mean > 0)
    # renormalise shares within each store-dept-date
    key_day = (sp.store_id.astype(str) + "-" + sp.dept_id.astype(str) + "-" + sp.day_date.astype(str)).astype("category").cat.codes.values
    sums = np.zeros((N_SIM, key_day.max() + 1))
    np.add.at(sums.T, key_day, share_draw.T)
    share_draw = share_draw / np.where(sums[:, key_day] > 0, sums[:, key_day], 1.0)
    daily_sim = sp.daily_point.values[None, :] * np.exp(lvl_draw + hol_draw)
    shift_sim = daily_sim * share_draw
    sp["pi80_lo"] = np.percentile(shift_sim, 10, axis=0); sp["pi80_hi"] = np.percentile(shift_sim, 90, axis=0)
    sp["sim_mean"] = shift_sim.mean(axis=0); sp["sim_sd"] = shift_sim.std(axis=0)
    sp["log_sd"] = np.where(sp.shift_point > 0, np.log(np.clip(shift_sim, 1e-6, None)).std(axis=0), 0.0)
    # daily PIs
    dkey = sp.groupby(["store_id", "dept_id", "day_date"]).ngroup().values
    dsim = np.zeros((N_SIM, dkey.max() + 1)); np.add.at(dsim.T, dkey, shift_sim.T)
    dd = sp.groupby(["store_id", "dept_id", "day_date"]).ngroup()
    dmap = sp.assign(dk=dkey).drop_duplicates(["store_id", "dept_id", "day_date"])[["store_id", "dept_id", "day_date", "dk"]]
    dmap["pi80_lo"] = np.percentile(dsim, 10, axis=0)[dmap.dk.values]; dmap["pi80_hi"] = np.percentile(dsim, 90, axis=0)[dmap.dk.values]
    daily = daily.merge(dmap.drop(columns="dk"), on=["store_id", "dept_id", "day_date"], how="left")
    daily_out = daily[["store_id", "dept_id", "dept", "day_date", "day_name", "holiday_window_role", "log_level", "dow_effect",
                       "holiday_effect", "post_holiday_effect", "valentine_effect", "point", "pi80_lo", "pi80_hi", "benchmark",
                       "ratio_to_benchmark", "level_mode"]].copy()
    daily_out["scenario_code"] = "BASE"
    daily_out.to_csv(os.path.join(out_dir, "03_forecast_daily.csv"), index=False)

    # ---- shift-level forecast for all scenarios (BASE x multiplier)
    mult = grid[["scenario_code", "store_id", "dept_id", "day_date", "shift_code", "demand_multiplier"]]
    sp_all = mult.merge(sp.drop(columns=["share_sd"]), on=["store_id", "dept_id", "day_date", "shift_code"], how="left")
    for c in ["shift_point", "pi80_lo", "pi80_hi", "sim_mean", "sim_sd"]:
        sp_all[c] = sp_all[c] * sp_all.demand_multiplier
    sp_all["dept"] = sp_all.dept_id.map(DEPT_SHORT)
    sp_all = sp_all.sort_values(["scenario_code", "store_id", "dept_id", "day_date", "shift_seq"])
    cols = ["scenario_code", "store_id", "dept_id", "dept", "day_date", "day_name", "day_type", "holiday_window_role", "shift_code",
            "is_open", "paid_hours", "min_staff", "share", "daily_point", "demand_multiplier", "shift_point", "pi80_lo", "pi80_hi",
            "sim_mean", "sim_sd", "log_sd"]
    sp_all[cols].to_csv(os.path.join(out_dir, "03_forecast_shift.csv"), index=False)

    # ---- Valentine's sensitivity (daily, FE/Merch, Feb 13-14) and overall effect on the week
    vs = []
    for v in ("low", "mid", "high"):
        dv = predict_daily(fit, lv, rows, level_mode=level_mode, valentine=v, trend=tt["slope_per_week_weekmeans"])
        dv["scn"] = v
        vs.append(dv)
    vs = pd.concat(vs)
    vs_piv = vs.pivot_table(index=["store_id", "dept_id", "day_date"], columns="scn", values="point").reset_index()
    vs_piv = vs_piv[vs_piv.day_date.isin([pd.Timestamp("2026-02-13"), pd.Timestamp("2026-02-14")]) & vs_piv.dept_id.isin([38, 92])]
    vs_piv["dept"] = vs_piv.dept_id.map(DEPT_SHORT)
    vs_piv["high_vs_low_pct"] = vs_piv.high / vs_piv.low - 1
    vs_piv.to_csv(os.path.join(out_dir, "03_valentine_sensitivity.csv"), index=False)

    # ---- backtests
    bt = []
    def eval_rows(label, horizon, test, pred_ours, pred_naive, pred_naive_incl_closed):
        for dept in (38, 92, 95):
            m = (test.dept_id == dept).values
            bt.append(dict(test=label, horizon=horizon, level="daily", dept=DEPT_SHORT[dept], n=int(m.sum()),
                           wape_ours=wape(test.demand.values[m], pred_ours[m]), mape_ours=mape(test.demand.values[m], pred_ours[m]),
                           wape_naive=wape(test.demand.values[m], pred_naive[m]), mape_naive=mape(test.demand.values[m], pred_naive[m]),
                           wape_naive_incl_closed=wape(test.demand.values[m], pred_naive_incl_closed[m])))
        m = np.ones(len(test), bool)
        bt.append(dict(test=label, horizon=horizon, level="daily", dept="ALL", n=int(m.sum()),
                       wape_ours=wape(test.demand.values, pred_ours), mape_ours=mape(test.demand.values, pred_ours),
                       wape_naive=wape(test.demand.values, pred_naive), mape_naive=mape(test.demand.values, pred_naive),
                       wape_naive_incl_closed=wape(test.demand.values, pred_naive_incl_closed)))

    def eval_shift(label, horizon, test_blocks, daily_pred_ours, daily_pred_naive, shares_tr):
        tb = test_blocks.copy()
        tb["window"] = np.where(tb.holiday_window_role == "Normal", "Normal", "HolWin")
        tb = tb.merge(shares_tr[["dept_id", "day_type", "window", "shift_code", "share"]], on=["dept_id", "day_type", "window", "shift_code"], how="left")
        tb["share"] = tb.share.fillna(0.0)
        tb = tb.merge(daily_pred_ours, on=["store_id", "dept_id", "day_date"], how="left").merge(daily_pred_naive, on=["store_id", "dept_id", "day_date"], how="left")
        tb["ours"] = tb.d_ours * tb.share; tb["naive"] = tb.d_naive * tb.share
        for dept in (38, 92, 95):
            m = tb.dept_id == dept
            bt.append(dict(test=label, horizon=horizon, level="shift", dept=DEPT_SHORT[dept], n=int(m.sum()),
                           wape_ours=wape(tb.shift_demand_units[m], tb.ours[m]), mape_ours=mape(tb.shift_demand_units[m], tb.ours[m]),
                           wape_naive=wape(tb.shift_demand_units[m], tb.naive[m]), mape_naive=mape(tb.shift_demand_units[m], tb.naive[m]),
                           wape_naive_incl_closed=np.nan))
        bt.append(dict(test=label, horizon=horizon, level="shift", dept="ALL", n=int(len(tb)),
                       wape_ours=wape(tb.shift_demand_units, tb.ours), mape_ours=mape(tb.shift_demand_units, tb.ours),
                       wape_naive=wape(tb.shift_demand_units, tb.naive), mape_naive=mape(tb.shift_demand_units, tb.naive),
                       wape_naive_incl_closed=np.nan))

    open_blocks = h[h.is_open == 1][["store_id", "dept_id", "day_date", "day_type", "holiday_window_role", "shift_code", "shift_demand_units"]]
    for train_w, test_w in [((1, 2, 3, 4), 5), ((1, 2, 3, 4, 5), 6)]:
        tr = d[d.week_idx.isin(train_w)]; te = d[(d.week_idx == test_w) & (d.is_costco_closed == 0)].copy()
        f = fit_daily(tr); lvw = weekly_levels(f)
        rows_te = te[["store_id", "dept_id", "day_date", "day_name", "holiday_window_role", "week_idx"]].copy()
        rows_te["is_post_holiday_rebound"] = 0
        for mode in ("mean", "last4"):
            po = predict_daily(f, lvw, rows_te, level_mode=mode)
            pn = naive_same_weekday(tr, te, 4, True); pn_c = naive_same_weekday(tr, te, 4, False)
            eval_rows(f"rolling_origin_level={mode}", f"train w{train_w[0]}-{train_w[-1]} -> w{test_w}", te, po.point.values, pn, pn_c)
            if mode == "mean":
                htr = h[h.week_idx.isin(train_w)]; sh_tr = shift_shares(htr)
                d_ours = po[["store_id", "dept_id", "day_date", "point"]].rename(columns={"point": "d_ours"})
                d_naive = te[["store_id", "dept_id", "day_date"]].assign(d_naive=pn)
                eval_shift("rolling_origin_level=mean", f"train w{train_w[0]}-{train_w[-1]} -> w{test_w}",
                           open_blocks[open_blocks.day_date.isin(te.day_date.unique())], d_ours, d_naive, sh_tr)

    # MLK holdout: (a) no-holiday model (what the benchmark logic does) vs (b) factors transferred from the other two warehouses
    mlk_days = pd.date_range("2026-01-16", "2026-01-19")
    te = d[d.day_date.isin(mlk_days)].copy()
    pred_a, pred_b, pred_n, pred_nc = np.zeros(len(te)), np.zeros(len(te)), np.zeros(len(te)), np.zeros(len(te))
    for s in (1, 2, 4):
        m_te = (te.store_id == s).values
        tr_b = d[~((d.store_id == s) & d.day_date.isin(mlk_days))]           # drop this warehouse's MLK window
        f_b = fit_daily(tr_b); lv_b = weekly_levels(f_b)
        rows_s = te[m_te][["store_id", "dept_id", "day_date", "day_name", "holiday_window_role", "week_idx"]].copy(); rows_s["is_post_holiday_rebound"] = 0
        pb = predict_daily(f_b, lv_b, rows_s, level_mode="mean")
        # level for this warehouse in week 3 is unknown without those days -> use that warehouse's own week-3 level from the fit
        # (week 3 still has Thu Jan 15 and Tue/Wed Jan 20-21 for the level); predict_daily used the series mean, so swap in w3 level
        lv3 = lv_b[(lv_b.store_id == s) & (lv_b.week_idx == 3)].set_index("dept_id").log_level
        lvm = lv_b[(lv_b.store_id == s)].groupby("dept_id").log_level.mean()
        pb["point"] = np.exp(pb.log_point - pb.dept_id.map(lvm).values + pb.dept_id.map(lv3).values)
        pred_b[m_te] = pb.point.values
        pa = pb.copy(); pa["point"] = np.exp(pa.log_point - pa.holiday_effect - pa.dept_id.map(lvm).values + pa.dept_id.map(lv3).values)
        pred_a[m_te] = pa.point.values
        pred_n[m_te] = naive_same_weekday(d[d.week_idx.isin([1, 2])], te[m_te], 2, True)
        pred_nc[m_te] = naive_same_weekday(d[d.week_idx.isin([1, 2])], te[m_te], 2, False)
    eval_rows("MLK_holdout_no_holiday_factor", "Jan 16-19, same-week level, factor=1", te, pred_a, pred_n, pred_nc)
    eval_rows("MLK_holdout_factor_from_other_2_warehouses", "Jan 16-19, same-week level", te, pred_b, pred_n, pred_nc)
    bt_df = pd.DataFrame(bt)
    bt_df.to_csv(os.path.join(out_dir, "03_backtest.csv"), index=False)

    meta = dict(fit_stats=fit_stats, trend=tt, level_mode=level_mode, sd_week=sd_week, holiday_transfer_sd=HOLIDAY_TRANSFER_SD,
                valentine=VALENTINE, n_sim=N_SIM)
    with open(os.path.join(out_dir, "03_forecast_meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2, default=str)

    if make_chart:
        chart(daily_out, sp_all, d, out_dir)
    return dict(daily=daily_out, shift=sp_all, factors=coef_out, levels=lv, trend=tt, backtest=bt_df, shares=shares,
                valentine=vs_piv, meta=meta)


def chart(daily_out, sp_all, d, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 3, figsize=(15, 9), sharex=False)
    colors = {"BASE": "#1f5f8b", "PEAK": "#c0504d"}
    for i, s in enumerate((1, 2, 4)):
        for j, dept in enumerate((38, 92, 95)):
            ax = axes[i, j]
            hh = d[(d.store_id == s) & (d.dept_id == dept)]
            ax.plot(hh.day_date, hh.demand, color="#555", lw=1.2, label="history")
            f = daily_out[(daily_out.store_id == s) & (daily_out.dept_id == dept)]
            ax.plot(f.day_date, f.point, color=colors["BASE"], lw=1.8, marker="o", ms=3, label="BASE forecast")
            ax.fill_between(f.day_date, f.pi80_lo, f.pi80_hi, color=colors["BASE"], alpha=0.18, lw=0, label="80% PI")
            ax.plot(f.day_date, f.benchmark, color="#999", lw=1.2, ls="--", label="naive benchmark")
            pk = sp_all[(sp_all.scenario_code == "PEAK") & (sp_all.store_id == s) & (sp_all.dept_id == dept)].groupby("day_date").shift_point.sum()
            ax.plot(pk.index, pk.values, color=colors["PEAK"], lw=1.2, ls=":", label="PEAK")
            ax.axvspan(pd.Timestamp("2026-02-13"), pd.Timestamp("2026-02-16"), color="#f4e3a1", alpha=0.35, lw=0)
            ax.set_title(f"Warehouse {s} - {DEPT_SHORT[dept]}", fontsize=10)
            ax.tick_params(axis="x", labelrotation=30, labelsize=7); ax.tick_params(axis="y", labelsize=8)
            if i == 0 and j == 0:
                ax.legend(fontsize=7, frameon=False, loc="upper left")
    fig.suptitle("Daily demand: six weeks of history and the planning-week forecast (shaded = Presidents' Day window)", fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "03_forecast.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    res = run(sys.argv[1], sys.argv[2])
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    print(json.dumps(res["meta"]["fit_stats"], indent=1)); print(json.dumps(res["trend"], indent=1))
    print(res["factors"][["dept", "kind", "term", "coef", "se", "factor", "t_stat"]].round(4).to_string(index=False))
    print(res["levels"].pivot_table(index=["store_id", "dept"], columns="week_idx", values="level_index").round(3))
    print(res["backtest"].round(4).to_string(index=False))
    print(res["daily"].round(2).to_string(index=False))
    print(res["valentine"].round(2).to_string(index=False))
