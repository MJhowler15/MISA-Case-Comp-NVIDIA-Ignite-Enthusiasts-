"""
viz.py - charts shared by the Streamlit tool (app.py) and the static HTML backup (step7_static.py).
Style rules (from the brief): no gradients, no pure white, muted single-hue scales, no drop shadows, no rounded
corners, system fonts, no icons or animation. Every chart is built from pipeline output only.
"""
from __future__ import annotations
import io, base64
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

BG = "#f4f3ef"
INK = "#1a1a1a"
BLUE_SCALE = LinearSegmentedColormap.from_list("blue_muted", ["#eef0ea", "#9fb8c8", "#2f5f7e", "#132f44"])
DIVERGE = LinearSegmentedColormap.from_list("div_muted", ["#8c3b2e", "#d9b7a8", "#eceae2", "#9fb8c8", "#2f5f7e"])
RISK = LinearSegmentedColormap.from_list("risk", ["#8c3b2e", "#c99a6b", "#e4dfcf", "#7fa39a", "#2f6b5e"])

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": "#55554f", "axes.labelcolor": INK,
                     "xtick.color": INK, "ytick.color": INK, "text.color": INK, "figure.facecolor": BG, "axes.facecolor": BG,
                     "savefig.facecolor": BG})

DAY_ORDER = ["2026-02-12", "2026-02-13", "2026-02-14", "2026-02-15", "2026-02-16", "2026-02-17", "2026-02-18"]
DAY_LABEL = {"2026-02-12": "Thu 12", "2026-02-13": "Fri 13", "2026-02-14": "Sat 14 Val.", "2026-02-15": "Sun 15",
             "2026-02-16": "Mon 16 Pres.", "2026-02-17": "Tue 17", "2026-02-18": "Wed 18"}
SHIFTS = ["OPEN", "MID", "EVE"]


def grid_matrix(ev: pd.DataFrame, value: str) -> tuple[np.ndarray, list, list]:
    """Rows: warehouse x dept (9); columns: day x shift (21). value column of the evaluated plan."""
    rows = [(s, d) for s in (1, 2, 4) for d in ("FE", "Merch", "Pharm")]
    cols = [(day, sh) for day in DAY_ORDER for sh in SHIFTS]
    M = np.full((len(rows), len(cols)), np.nan)
    e = ev.copy(); e["dstr"] = pd.to_datetime(e.day_date).dt.strftime("%Y-%m-%d")
    idx = {(int(r.store_id), r.dept, r.dstr, r.shift_code): getattr(r, value) for r in e.itertuples()}
    for i, (s, d) in enumerate(rows):
        for j, (day, sh) in enumerate(cols):
            v = idx.get((s, d, day, sh), np.nan)
            M[i, j] = v
    return M, [f"W{s} {d}" for s, d in rows], cols


def heatmap(ev: pd.DataFrame, value: str, title: str, kind: str = "seq", fmt: str = "{:.0f}", figsize=(13, 4.6)):
    M, rlab, cols = grid_matrix(ev, value)
    open_mask = grid_matrix(ev, "is_open")[0] == 1
    fig, ax = plt.subplots(figsize=figsize)
    if kind == "div":
        lim = np.nanmax(np.abs(M[open_mask])) if open_mask.any() else 1
        lim = max(lim, 1)
        im = ax.imshow(np.where(open_mask, M, np.nan), cmap=DIVERGE, norm=TwoSlopeNorm(vcenter=0, vmin=-lim, vmax=lim), aspect="auto")
    elif kind == "risk":
        im = ax.imshow(np.where(open_mask, M, np.nan), cmap=RISK, vmin=0, vmax=1, aspect="auto")
    else:
        im = ax.imshow(np.where(open_mask, M, np.nan), cmap=BLUE_SCALE, aspect="auto")
    ax.set_yticks(range(len(rlab))); ax.set_yticklabels(rlab)
    ax.set_xticks(range(len(cols))); ax.set_xticklabels([sh for _, sh in cols], fontsize=7)
    for j, day in enumerate(DAY_ORDER):
        ax.text(j * 3 + 1, -0.9, DAY_LABEL[day], ha="center", va="bottom", fontsize=8)
        if j > 0:
            ax.axvline(j * 3 - 0.5, color="#55554f", lw=0.8)
    for i in range(1, 3):
        ax.axhline(i * 3 - 0.5, color="#55554f", lw=0.8)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if open_mask[i, j] and not np.isnan(M[i, j]):
                v = M[i, j]
                txt = fmt.format(v)
                dark = (kind == "seq" and v > np.nanpercentile(M[open_mask], 60)) or (kind == "risk" and v < 0.45) or (kind == "div" and abs(v) > 0.6 * (np.nanmax(np.abs(M[open_mask])) or 1))
                ax.text(j, i, txt, ha="center", va="center", fontsize=6.5, color=("#f4f3ef" if dark else INK))
            elif not open_mask[i, j]:
                ax.text(j, i, "closed", ha="center", va="center", fontsize=5.5, color="#8a8a83")
    ax.set_title(title, fontsize=10, loc="left", pad=30)
    cb = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01); cb.ax.tick_params(labelsize=7)
    fig.tight_layout()
    return fig


def fig_to_base64(fig) -> str:
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=130, bbox_inches="tight"); plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def frontier_chart(summary: pd.DataFrame, scenario: str):
    s = summary[summary.scenario == scenario]
    fig, ax = plt.subplots(figsize=(6.2, 4))
    for r in s.itertuples():
        ax.scatter(r.cost / 1000, r.exp_missed_post, s=36, color="#2f5f7e" if r.plan.startswith("Ours") else "#8c3b2e", edgecolor="none")
        ax.annotate(r.plan.replace("Ours, ", ""), (r.cost / 1000, r.exp_missed_post), fontsize=7, xytext=(4, 3), textcoords="offset points")
    ax.set_xlabel("Labor cost, planning week ($000)"); ax.set_ylabel("Expected missed blocks (after callouts)")
    ax.set_title(f"{scenario}: cost vs service for each plan", fontsize=10, loc="left")
    fig.tight_layout()
    return fig
