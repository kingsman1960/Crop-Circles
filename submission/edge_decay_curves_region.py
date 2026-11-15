"""The two-panel edge figure of pipeline/planthopper_edge_effect.py, redrawn on the region data (python submission/edge_decay_curves_region.py): one point per parcel-season (not grid points), partial
residuals of the region model (June value, season, soil), nearest wheat of either kind on the x axis, log1p fit per
panel plus binned means. Writes submission/edge_decay_curves_region.png."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the repo root, for `pipeline`
from pipeline.common import RAW
from pipeline.planthopper_region import soil, windows

parcels = soil(pd.concat([pd.read_parquet(p) for p in sorted((RAW / "hls_region").glob("parcels_*.parquet"))], ignore_index=True))
series = pd.concat([pd.read_parquet(p).assign(year=lambda d: d.date.dt.year) for p in sorted((RAW / "hls_region").glob("series_*.parquet"))], ignore_index=True)
d = windows(series.dropna(subset=["ndre"]), "ndre").join(parcels.set_index(["id", "year"])[["role", "dist_to_source", "dist_to_control", "ks", "nfk_mm"]], how="inner").reset_index()
d = d.dropna(subset=["ks", "nfk_mm"])
d["adj_delta"] = smf.ols("delta ~ june + ks + nfk_mm + C(year)", data=d).fit().resid  # partial residual: distance terms left out
d["d_any"] = d[["dist_to_source", "dist_to_control"]].min(axis=1)
near_src = d.dist_to_source <= d.dist_to_control

PINK, GREY, INK = "#b03a72", "#7a8496", "#16213e"
fig, axes = plt.subplots(1, 2, figsize=(12.8, 6.4), sharey=True, sharex=True)
for ax, (mask, colour, lab) in zip(axes, ((near_src, PINK, "nearest wheat is a nursery (after beet)"),
                                          (~near_src, GREY, "nearest wheat is control wheat (reference)"))):
    ok = d[mask & (d.d_any <= 500)]
    x, y = ok.d_any.values, ok.adj_delta.values
    ax.scatter(x, y, s=9, alpha=0.35, color=colour, label=f"n = {len(x)} parcel-seasons")
    b = np.polyfit(np.log1p(x), y, 1)
    pred = b[0] * np.log1p(x) + b[1]
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    xs = np.linspace(1, 500, 200)
    ax.plot(xs, b[0] * np.log1p(xs) + b[1], color=colour, lw=2.2, label=f"log1p fit: {b[0]:+.4f} per log1p(d), r² = {r2:.2f}")
    bins = [0, 25, 50, 100, 200, 350, 501]
    g = ok.assign(band=pd.cut(ok.d_any, bins, right=False)).groupby("band", observed=True).adj_delta.agg(["mean", "sem"])
    mids = [(b_.left + min(b_.right, 500)) / 2 for b_ in g.index]
    ax.errorbar(mids, g["mean"], yerr=1.96 * g["sem"], fmt="s", color=INK, ms=5, capsize=3, label="band mean ± 95 % CI")
    ax.axhline(0, lw=0.8, color="#999999"); ax.grid(alpha=0.3); ax.set_title(lab); ax.legend(frameon=False, fontsize=8, loc="lower right")
axes[0].set_ylabel("adjusted canopy delta (late summer − June NDRE), season / June / soil removed")
axes[0].set_ylim(-0.35, 0.35)
fig.supxlabel("distance to the nearest wheat boundary (m)")
fig.suptitle("Late-summer canopy decline vs distance to winter wheat – region data 2023–2025\n"
             "(one point per parcel and season; partial residuals; more negative = worse than expected)")
fig.tight_layout()
out = Path(__file__).with_suffix(".png")
fig.savefig(out, dpi=150)
print(out, "nursery-nearest", int(near_src.sum()), "control-nearest", int((~near_src).sum()))
