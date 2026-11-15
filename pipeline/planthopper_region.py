"""Does sugar beet next to a planthopper nursery lose more canopy in late summer? The region-wide test.

Input: prep/fetch_hls_region.py (data/raw/hls_region): every declared beet parcel of 2023-2025 that lies next to a
nursery (wheat after beet, < 50 m) or next to control wheat (< 50 m, >= 200 m from any nursery), with HLS S30 NDVI,
GNDVI and NDRE in the June and late-summer windows. One observation per parcel and season (no grid points), so the
sample size is the honest one.

Output: planthopper_effect/region_summary.json
  per index: OLS  delta ~ nursery_adjacent + june value + C(season), HC3 standard errors, and the plain difference of
  the mean delta between the two roles per season (Welch). A negative coefficient = beet next to a nursery declines
  more between June and late summer than beet next to other wheat.
"""
import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats as sstats

import shapely
from shapely.geometry import shape
from shapely.strtree import STRtree

from pipeline import geo
from pipeline.common import FIELDS, PROC, RAW, out
from pipeline.planthopper_edge_effect import JUNE, LATE, MIN_OBS, fiona_pools

INDICES = ("ndvi", "gndvi", "ndre")
CELL = 2000  # m: standard errors clustered by 2 km cell
BINS = (0, 25, 50, 100, 200, 400, 800, 1600, 3001)  # m: distance to the nearest nursery, for the bar chart
R_GRID = (50, 100, 150, 250, 350, 500, 750, 1000, 1500, 2000, 3000)  # m: candidate flight distances for the decay fit


def windows(series, index):
    """June and late-summer mean of one index per parcel and season, and the delta (MIN_OBS clear pictures each)."""
    day = series.date.dt.month * 100 + series.date.dt.day

    def win(window, name):
        (m0, d0), (m1, d1) = window
        w = series[(day >= m0 * 100 + d0) & (day <= m1 * 100 + d1)]
        return w.groupby(["id", "year"])[index].agg(**{name: "mean", f"n_{name}": "count"})

    df = win(JUNE, "june").join(win(LATE, "late"), how="inner")
    df = df[(df.n_june >= MIN_OBS) & (df.n_late >= MIN_OBS)]
    return df.assign(delta=df.late - df.june)


def soil(parcels):
    """ks (K x slope) and nFK per parcel: the FIONA 2022 parcel under the centroid (ids change between years), from
    landscape_parcels; NaN where the 2022 parcel grew neither beet nor a nursery in any season (not in that file)."""
    lp = pd.read_parquet(PROC / "landscape_parcels.parquet").set_index("id")[["ks", "nfk_mm"]]
    feats = [f for p in sorted((RAW / "fiona").glob("fiona_bbox_p*.json")) for f in json.loads(p.read_text(encoding="utf-8"))["features"]]
    ids22 = np.array([f["properties"]["object_id"] for f in feats])
    tree = STRtree([shape(f["geometry"]) for f in feats])
    pts = shapely.points(parcels.x.values, parcels.y.values)
    qi, ti = tree.query(pts, predicate="within")
    match = pd.Series(ids22[ti], index=qi).groupby(level=0).first().reindex(range(len(parcels)))
    return parcels.assign(id22=match.values).join(lp, on="id22")


def demo_edges(season, within=50):
    """Per demo field: the nurseries of `season` within `within` m of the block outline (count, ha, own share)."""
    pools, _ = fiona_pools((season,))
    nur = np.asarray(pools[season]["source_wheat"], dtype=object)
    out_ = {}
    for f in FIELDS:
        block = geo.reproj(shape(f["polygon"]), 4326, 25832)
        near = nur[shapely.dwithin(nur, block, within)]
        own = shapely.area(shapely.intersection(near, block)).sum() if len(near) else 0.0
        out_[f["id"]] = {"season": season, "within_m": within, "n": int(len(near)), "ha": round(float(shapely.area(near).sum() / 1e4), 1),
                         "own_ha": round(float(own / 1e4), 1)}
    return out_


def distance_bins(d):
    """Mean delta (season mean removed) per distance band to the nearest nursery, with its standard error."""
    x = d.assign(adj=d.delta - d.groupby("year").delta.transform("mean"), band=pd.cut(d.dist_to_source, BINS, right=False))
    g = x.groupby("band", observed=True).adj.agg(["mean", "sem", "size"])
    return [{"lo": int(b.left), "hi": int(b.right), "mean": round(float(r["mean"]), 4), "sem": round(float(r["sem"]), 4), "n": int(r["size"])}
            for b, r in g.iterrows()]


def decay(d):
    """delta ~ e^(-dist to nursery / r) + June + season (+ soil): which flight distance r fits best? Profile over R_GRID."""
    with_soil = d.ks.notna().mean() > 0.5
    base = "delta ~ june + C(year)" + (" + ks + nfk_mm" if with_soil else "")
    d = d.dropna(subset=["ks", "nfk_mm"]) if with_soil else d
    rows = []
    for r in R_GRID:
        dd = d.assign(exposure=np.exp(-d.dist_to_source / r))
        fit = smf.ols(base + " + exposure", data=dd).fit(cov_type="cluster", cov_kwds={"groups": dd.cell})
        rows.append({"r_m": r, "llf": round(float(fit.llf), 2), "exposure_coef": round(float(fit.params["exposure"]), 4),
                     "exposure_se": round(float(fit.bse["exposure"]), 4), "p": round(float(fit.pvalues["exposure"]), 4)})
    best = max(rows, key=lambda x: x["llf"])
    within2 = [x["r_m"] for x in rows if best["llf"] - x["llf"] <= 2]  # about a 95 % profile-likelihood band
    return {"best_r_m": best["r_m"], "r_band_m": [min(within2), max(within2)], "profile": rows}


def main():
    parcels = soil(pd.concat([pd.read_parquet(p) for p in sorted((RAW / "hls_region").glob("parcels_*.parquet"))], ignore_index=True))
    print(f"  soil matched for {parcels.ks.notna().mean():.0%} of the parcels (centroid in a FIONA 2022 parcel of landscape_parcels)")
    series = pd.concat([pd.read_parquet(p).assign(year=lambda d: d.date.dt.year)
                        for p in sorted((RAW / "hls_region").glob("series_*.parquet"))], ignore_index=True)
    res = {"parcels": {str(y): {k: int(v) for k, v in g.role.value_counts().items()} for y, g in parcels.groupby("year")},
           "pictures": {str(y): int(g.granule.nunique()) for y, g in series.groupby("year")}, "index": {}}
    for index in INDICES:
        w = windows(series.dropna(subset=[index]), index)
        d = w.join(parcels.set_index(["id", "year"])[["role", "area_ha", "dist_to_source", "dist_to_control", "x", "y", "ks", "nfk_mm"]], how="inner")
        d = d.reset_index()
        d["adjacent"] = (d.role == "nursery_adjacent").astype(int)
        d_all, d = d, d[d.role != "other"]  # the adjacent-vs-control test keeps its clean contrast; the decay fit uses every parcel
        d["cell"] = (d.x // CELL).astype(int) * 10_000 + (d.y // CELL).astype(int)  # neighbours share weather and farms
        fit = smf.ols("delta ~ adjacent + june + C(year)", data=d).fit(cov_type="cluster", cov_kwds={"groups": d.cell})
        placebo = smf.ols("june ~ adjacent + C(year)", data=d).fit(cov_type="cluster", cov_kwds={"groups": d.cell})
        ds = d.dropna(subset=["ks", "nfk_mm"])
        fit_soil = smf.ols("delta ~ adjacent + june + ks + nfk_mm + C(year)", data=ds).fit(cov_type="cluster", cov_kwds={"groups": ds.cell})
        per_season = {}
        for y, g in d.groupby("year"):
            a, c = g.delta[g.adjacent == 1], g.delta[g.adjacent == 0]
            t = sstats.ttest_ind(a, c, equal_var=False)
            per_season[str(y)] = {"n_adjacent": int(len(a)), "n_control": int(len(c)), "mean_adjacent": round(float(a.mean()), 4),
                                  "june_adjacent": round(float(g.june[g.adjacent == 1].mean()), 4), "june_control": round(float(g.june[g.adjacent == 0].mean()), 4),
                                  "mean_control": round(float(c.mean()), 4), "difference": round(float(a.mean() - c.mean()), 4),
                                  "welch_p": round(float(t.pvalue), 4)}
        res["index"][index] = {"n": int(len(d)), "n_parcels": int(d.id.nunique()),
                               "adjacent_coef": round(float(fit.params["adjacent"]), 4),
                               "adjacent_se": round(float(fit.bse["adjacent"]), 4),
                               "adjacent_p": round(float(fit.pvalues["adjacent"]), 4),
                               "june_coef": round(float(fit.params["june"]), 4), "r2": round(float(fit.rsquared), 3),
                               "n_clusters": int(d.cell.nunique()),
                               "with_soil": {"n": int(len(ds)), "adjacent_coef": round(float(fit_soil.params["adjacent"]), 4),
                                             "adjacent_se": round(float(fit_soil.bse["adjacent"]), 4), "p": round(float(fit_soil.pvalues["adjacent"]), 4),
                                             "ks_coef": round(float(fit_soil.params["ks"]), 4), "nfk_coef": round(float(fit_soil.params["nfk_mm"]), 5)},
                               "decay": decay(d_all.assign(cell=(d_all.x // CELL).astype(int) * 10_000 + (d_all.y // CELL).astype(int))),
                               "bins": distance_bins(d_all),
                               "placebo_june_level": {"adjacent_coef": round(float(placebo.params["adjacent"]), 4),
                                                      "p": round(float(placebo.pvalues["adjacent"]), 4)},
                               "per_season": per_season}
        print(f"  {index}: n {len(d)} parcel-seasons in {d.cell.nunique()} cells, nursery-adjacent effect on the June->late change "
              f"{fit.params['adjacent']:+.4f} (cluster SE {fit.bse['adjacent']:.4f}, p {fit.pvalues['adjacent']:.3f}); "
              f"June level itself {placebo.params['adjacent']:+.4f} (p {placebo.pvalues['adjacent']:.3f}); with soil (n {len(ds)}) "
              f"{fit_soil.params['adjacent']:+.4f} (p {fit_soil.pvalues['adjacent']:.3f}); best flight distance "
              f"{res['index'][index]['decay']['best_r_m']} m (band {res['index'][index]['decay']['r_band_m']}); per season "
              + ", ".join(f"{y}: {v['difference']:+.3f} (p {v['welch_p']:.2f}, n {v['n_adjacent']}/{v['n_control']})"
                          for y, v in per_season.items()))
    res["notes"] = ["one observation per parcel and season; ks / nFK from the FIONA 2022 parcel under the centroid",
                    "decay: delta ~ exp(-distance to the nearest nursery boundary / r) with the same controls, r profiled; "
                    "the adjacent-vs-control test uses the < 50 m and >= 200 m parcels; the decay fit uses every beet parcel",
                    "the June value is in the model: a parcel that is greener in June has more to lose by late summer",
                    f"windows: June {JUNE}, late summer {LATE}; at least {MIN_OBS} clear pictures in each"]
    res["demo_fields"] = demo_edges(max(parcels.year))
    print("  demo fields, nurseries within 50 m: " + ", ".join(f"{k}: {v['n']} ({v['ha']} ha)" for k, v in res["demo_fields"].items()))
    out("planthopper_effect/region_summary.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
