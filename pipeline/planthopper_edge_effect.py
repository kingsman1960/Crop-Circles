"""Isolate the reed-glasswing planthopper (SBR / Stolbur) edge-damage signal in sugar beet.

The adults emerge in May-June (t2m > 20 degC) from winter wheat that followed sugar beet (the nursery,
beet in t-1 -> winter wheat in t), fly into the neighbouring beet parcels and transmit SBR, which yellows
and wilts the canopy late in summer. The analysis separates that edge signal from soil drought and the
generic field-edge effect:

  planthopper_effect/parcel_classification.parquet  per season 2020-2025 and FIONA parcel in the window:
                                                    target beet, nursery (source) wheat, control wheat, from the
                                                    Thunen majority codes with the DLR CropTypes maps as a
                                                    second opinion
  planthopper_effect/target_beet_observations.parquet  one row per 30 m grid point in a target beet parcel with
                                                    a known outline: distance to the nearest source- and
                                                    control-wheat boundary (capped at 3 km), HLS June and
                                                    late-summer NDVI, the canopy delta, ECOSTRESS Jul-Aug
                                                    stress, nFK, erosion
  planthopper_effect/regression_summary.json | .txt  OLS with season fixed effects and cluster-robust SEs per
                                                    parcel: delta_ndvi ~ log1p(dist to source) + log1p(dist
                                                    to control) + June NDVI + nFK + erosion + C(season), plus the
                                                    adjacent-edge comparison (< 50 m, Welch)
  planthopper_effect/edge_decay_curves.png          adjusted canopy delta vs the distance to the nearest wheat
                                                    boundary: two panels (nursery or control nearest) with a
                                                    shared y axis, the same linear x scale and a regression
                                                    line per type
  planthopper_effect/edges_fiona.geojson            the demo-field grid points: observed canopy delta and the
                                                    model's predicted edge component (EPSG:4326)

Parcel outlines: the raw FIONA declarations (data/raw/fiona, catalog #12) carry the whole bbox for 2022-2025.
For the seasons where the season and the one before are both declared (2023-2025) the wheat pools are the
declared winter-wheat parcels, split by whether the same ground (largest-overlap match across seasons, ids
are not stable) declared sugar beet the year before; a target only counts when its ground is declared beet.
For 2020-2022 (no FIONA before 2022) the Thunen classification on the demo-block outlines from
data/processed/hls_parcels.geojson stands in; the summary records which pools each season used. NDVI still
exists for the demo-field parcels only (hls_series), so those are the observations. nFK per parcel is
the BK50 class mean already in landscape_parcels; slope is sampled from the raw NASADEM when present,
else the K*S erosion factor stands in. The ERA5-Land request carries no 10 m wind components, so
is_downwind stays unset unless a fresh request adds u10/v10 (flight_wind checks and reads them).
"""
import json
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
import statsmodels.formula.api as smf
from scipy import stats as sstats
from shapely.geometry import mapping, shape
from shapely.strtree import STRtree

from pipeline import geo
from pipeline.common import PROC, RAW, check, out

BEET, WHEAT = 1402, 1101                    # Thunen v202 codes: sugar beet, winter wheat
DLR_BEET, DLR_WHEAT = 60, (11, 14)          # DLR v2.1: sugar beet; winter wheat + spelt, triticale
YEARS = range(2020, 2026)
STEP, CORE = 30, 15                         # grid spacing = the HLS pixel size; half a pixel inside the outline
MAX_D = 3000                                # wheat further away than 3 km is no neighbour for an edge effect
JUNE, LATE = ((6, 1), (6, 25)), ((8, 15), (9, 15))  # healthy canopy before SBR yellowing / peak of it
MIN_OBS = 2                                 # a window counts from two clear pictures
FORMULA = "delta_ndvi ~ log_source + log_control + ndvi_june + nfk_mm + ks + C(season)"


NC_BEET, NC_WHEAT = "603", "115"            # FIONA declared codes: sugar beet, winter wheat

# ---------- Step 1: parcel classification, 2020-2025 ----------
def classify(lp):
    """Per season and parcel: target beet, nursery wheat (after beet) and control wheat (after anything else),
    from the Thunen majority codes; the DLR map classifies the same parcels independently."""
    frames, dlr_ok, dlr_n = [], {}, {}
    for y in YEARS:
        beet, wheat = lp[f"c{y}"] == BEET, lp[f"c{y}"] == WHEAT
        beet_d, wheat_d = lp[f"d{y}"] == DLR_BEET, np.isin(lp[f"d{y}"], DLR_WHEAT)
        prev, prev_d = lp[f"c{y - 1}"], lp[f"d{y - 1}"]
        role = np.select([beet, wheat & (prev == BEET), wheat & (prev > 0) & (prev != BEET)],
                         ["target_beet", "source_wheat", "control_wheat"], "")
        role_d = np.select([beet_d, wheat_d & (prev_d == DLR_BEET),
                            wheat_d & (prev_d > 0) & ~np.isin(prev_d, [DLR_BEET])],
                           ["target_beet", "source_wheat", "control_wheat"], "")
        f = pd.DataFrame({"season": y, "id": lp.id, "ha": lp.area_ha, "field": lp.field,
                          "role": role, "role_dlr": role_d})
        f = f[f.role != ""].reset_index(drop=True)
        both = f[f.role_dlr != ""]
        dlr_ok[y], dlr_n[y] = float(both.role_dlr.eq(both.role).mean()), len(both)
        frames.append(f)
    return pd.concat(frames, ignore_index=True), dlr_ok, dlr_n


# ---------- Step 2: outlines, 30 m grid, boundary distances ----------
def parcel_geoms():
    """Parcel outlines in EPSG:25832: the raw FIONA WFS pages when downloaded, else the demo-field outlines."""
    pages = sorted(RAW.glob("fiona/fiona_bbox_p*.json")) if RAW.is_dir() else []
    if pages:
        geoms = {f["properties"]["object_id"]: shapely.make_valid(shape(f["geometry"]))
                 for p in pages for f in json.loads(p.read_text(encoding="utf-8"))["features"]}
        return geoms, f"raw FIONA 2022 outlines ({len(geoms)} parcels, whole bbox)"
    feats = json.loads(out("hls_parcels.geojson").read_text(encoding="utf-8"))["features"]
    geoms = {f["properties"]["id"]: geo.reproj(shape(f["geometry"]), 4326, 25832) for f in feats}
    return geoms, f"demo-field outlines from hls_parcels.geojson ({len(geoms)} parcels around F1-F3)"


def grid_points(g):
    """Grid points on the 30 m UTM grid, half a pixel inside the outline (= pure pixels, as hls.py)."""
    core = shapely.buffer(g, -CORE)
    if core.is_empty:
        return np.empty(0), np.empty(0)
    x0, y0, x1, y1 = core.bounds
    xs = np.arange(np.floor(x0 / STEP) * STEP + STEP / 2, x1, STEP)
    ys = np.arange(np.floor(y0 / STEP) * STEP + STEP / 2, y1, STEP)
    x, y = map(np.ravel, np.meshgrid(xs, ys))
    keep = shapely.contains_xy(core, x, y)
    return x[keep], y[keep]


def dist_tree(geoms):
    """STRtree of the parcel boundaries, or None without neighbours."""
    if geoms is None or not len(geoms):
        return None
    return STRtree(shapely.boundary(np.asarray(geoms, dtype=object)))


def nearest_bound_dist(pts, tree):
    """Distance from grid points to the nearest parcel boundary (m; +inf beyond MAX_D)."""
    if tree is None:
        return np.full(len(pts), np.inf)
    (pi, gi), d = tree.query_nearest(pts, return_distance=True, max_distance=MAX_D)
    dist = np.full(len(pts), np.inf)
    dist[pi] = d
    return dist


def nearest_azimuth(pts, tree):
    """Bearing (deg from north) from each point to the nearest boundary in the tree (for the downwind flag)."""
    if tree is None:
        return np.full(len(pts), np.nan)
    (pi, gi), _ = tree.query_nearest(pts, return_distance=True, max_distance=MAX_D)
    az = np.full(len(pts), np.nan)
    near = shapely.points(tree.geometries[gi])
    dx = shapely.get_x(near) - shapely.get_x(pts[pi])
    dy = shapely.get_y(near) - shapely.get_y(pts[pi])
    az[pi] = np.degrees(np.arctan2(dx, dy)) % 360
    return az


def flight_wind():
    """Prevailing wind (bearing it blows towards, deg from north, and mean m/s) over the flight window
    May 15 - Jun 30 with t2m > 20 degC, from the raw ERA5-Land hourly zips at the field centres; or None."""
    zips = sorted(RAW.glob("era5_land/*_hourly.zip")) if RAW.is_dir() else []
    if not zips:
        return None, "raw ERA5-Land hourly zips are not in data/raw/"
    u_all, v_all = [], []
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for name in zf.namelist():
                df = pd.read_csv(zf.open(name))
                if not {"valid_time", "t2m", "u10", "v10"} <= set(df.columns):
                    continue
                t = pd.to_datetime(df.valid_time, format="mixed", utc=True)
                hot = (((t.dt.month == 5) & (t.dt.day >= 15)) | ((t.dt.month == 6) & (t.dt.day <= 30))) & \
                      (df.t2m - 273.15 > 20)
                u_all.append(df.u10[hot].astype(float))
                v_all.append(df.v10[hot].astype(float))
    if not u_all:
        return None, "the ERA5-Land request has no u10/v10 (t2m, tp, swvl only)"
    u, v = pd.concat(u_all).values, pd.concat(v_all).values
    return (float(np.degrees(np.arctan2(u.mean(), v.mean()))) % 360, float(np.hypot(u.mean(), v.mean()))), ""


def downwind(pts, src_tree, wind):
    """Whether the flight vector source boundary -> pixel points into the wind sector (45 deg each side)."""
    if wind is None:
        return np.full(len(pts), np.nan)
    az = nearest_azimuth(pts, src_tree)
    return np.where(np.isnan(az), np.nan, (np.abs(((az - wind[0] + 180) % 360) - 180) < 45)).astype(float)


# ---------- FIONA declared crops: per-season wheat pools and beet checks ----------
def fiona_pages(year):
    """The FIONA pages of one season: no year in the file name before 2023."""
    return sorted(RAW.glob(f"fiona/fiona_bbox{'' if year == 2022 else f'_{year}'}_p*.json"))


def fiona_year(year):
    """Declared parcels of one season in EPSG:25832: object_id, NC code and geometry (ids are not stable
    across seasons - anything across years is matched by the largest geometry overlap)."""
    feats = [f for p in fiona_pages(year) for f in json.loads(p.read_text(encoding="utf-8"))["features"]]
    df = pd.DataFrame({"id": [f["properties"]["object_id"] for f in feats],
                       "nc": [f["properties"]["NC"] for f in feats],
                       "crop": [f["properties"]["Bezeichnung"] for f in feats],
                       "geom": shapely.make_valid(shapely.from_geojson(
                           np.array([json.dumps(f["geometry"]) for f in feats], dtype=object)))})
    return df.dropna(subset=["geom"])


def max_overlap(g, geom, nc):
    """NC code of the largest-overlap parcel in `geom`/`nc` (or None where the ground has no declared parcel)."""
    hits = np.atleast_1d(STRtree(geom).query(g, predicate="intersects")) if len(geom) else []
    if not len(hits):
        return None
    a = shapely.area(shapely.intersection(geom[hits], g))
    return nc[hits[int(np.argmax(a))]]


def fiona_pools(years=YEARS):
    """Per season with FIONA for the season and the one before: the declared winter-wheat parcels split by
    whether the same ground carried declared sugar beet the year before (nursery) or not (control)."""
    pools, data = {}, {}
    for y in sorted(set(years) | {min(years) - 1}):
        if fiona_pages(y):
            data[y] = fiona_year(y)
    for y in years:
        if y - 1 not in data:
            continue
        prev = data[y - 1]
        wheat = data[y][data[y].nc == NC_WHEAT].reset_index(drop=True)
        tree = STRtree(prev.geom.values)
        pairs = tree.query(wheat.geom.values, predicate="intersects")
        a = shapely.area(shapely.intersection(wheat.geom.values[pairs[0]], prev.geom.values[pairs[1]]))
        best = pd.DataFrame({"w": pairs[0], "p": pairs[1], "a": a}).sort_values("a") \
                 .groupby("w").p.last().reindex(range(len(wheat)))
        pos = best.fillna(-1).astype(int).values
        after = np.where(pos >= 0, prev.nc.values[np.clip(pos, 0, len(prev) - 1)] == NC_BEET, np.nan)
        pools[y] = {"source_wheat": wheat.geom.values[after == 1.0],
                    "control_wheat": wheat.geom.values[after == 0.0],
                    "unmatched": int(np.isnan(after).sum())}
    return pools, data


# ---------- Step 3: canopy windows and thermal stress ----------
def ndvi_windows(series):
    """June baseline, late-summer canopy and the delta per parcel and season (mean NDVI per window)."""
    series = series.assign(year=series.date.dt.year, day=series.date.dt.month * 100 + series.date.dt.day)

    def mean_count(window):
        (m0, d0), (m1, d1) = window
        day = series.day
        w = series[(day >= m0 * 100 + d0) & (day <= m1 * 100 + d1)]
        return w.groupby(["id", "year"]).ndvi.agg(v="mean", n="count")

    def win(window, suffix):
        return mean_count(window).rename(columns={"v": f"ndvi_{suffix}", "n": f"n_{suffix}"})

    df = win(JUNE, "june").join(win(LATE, "late"), how="inner")
    df = df[(df.n_june >= MIN_OBS) & (df.n_late >= MIN_OBS)]
    df["delta_ndvi"] = df.ndvi_late - df.ndvi_june
    return df


def ecostress_aug(ec):
    """Mean ECOSTRESS LST and ESI over July-August per field and year (the demo fields only)."""
    ja = ec[ec.time.dt.month.isin([7, 8])]
    g = ja.groupby(["field", ja.time.dt.year]).agg(lst_aug=("lst", "mean"), esi_aug=("esi", "mean"))
    return g.reset_index().rename(columns={"time": "season"})


def slope_sampler():
    """Slope (%) sampled on the raw NASADEM grid at 30 m points; None when the raw DEM is not downloaded."""
    if not (RAW / "dem").is_dir():
        return None
    dem, T, slope_pct, _ = geo.dem_slope()

    def at(x, y):
        col, row = ~T * (x, y)
        ok = (row >= 0) & (row <= dem.shape[0] - 1) & (col >= 0) & (col <= dem.shape[1] - 1)
        v = np.full(len(x), np.nan)
        v[ok] = slope_pct[row[ok].astype(int), col[ok].astype(int)]
        return v

    return at


# ---------- Steps 2-3 across the classified seasons ----------
def observations(clf, meta, geoms, pools, fdata, ndvi, eco, slope_at, wind):
    """One row per 30 m grid point in every target beet parcel with NDVI: distances, downwind flag, the
    canopy windows joined per parcel and season, ECOSTRESS per field and season, nFK and erosion. The
    wheat pools come from the FIONA declarations for the seasons where the season and the one before are
    both declared (with a beet check on the target ground); before that the Thunen classes on the
    demo-block outlines stand in."""
    rows = []
    has_ndvi = set(ndvi.index.get_level_values(0))
    for season, same in clf.groupby("season"):
        declared = bool(pools.get(season))
        if declared:
            src_geoms, ctl_geoms = pools[season]["source_wheat"], pools[season]["control_wheat"]
            cur = fdata.get(season, None)
            cur_tree = STRtree(cur.geom.values) if cur is not None else None
        else:
            src_geoms = [geoms[i] for i in same.id[same.role == "source_wheat"] if i in geoms]
            ctl_geoms = [geoms[i] for i in same.id[same.role == "control_wheat"] if i in geoms]
        src_tree, ctl_tree = dist_tree(src_geoms), dist_tree(ctl_geoms)
        kept = skipped = 0
        for rec in same[same.role == "target_beet"].itertuples():
            if rec.id not in geoms or rec.id not in has_ndvi:
                continue
            if declared and max_overlap(geoms[rec.id], cur.geom.values, cur.nc.values) != NC_BEET:
                skipped += 1
                continue
            kept += 1
            x, y = grid_points(geoms[rec.id])
            if not len(x):
                continue
            pts = shapely.points(x, y)
            w = ndvi.loc[(rec.id, season)]
            rows.append(pd.DataFrame({
                "season": season, "id": rec.id, "field": meta.field.get(rec.id, ""), "x": x, "y": y,
                "dist_to_source": nearest_bound_dist(pts, src_tree),
                "dist_to_control": nearest_bound_dist(pts, ctl_tree),
                "is_downwind": downwind(pts, src_tree, wind),
                "dist_declared": declared,
                "ndvi_june": w.ndvi_june, "ndvi_late": w.ndvi_late, "delta_ndvi": w.delta_ndvi,
                "n_june": int(w.n_june), "n_late": int(w.n_late)}))
        if declared:
            print(f"  season {season} (declared FIONA): pools source {len(src_geoms)} / control "
                  f"{len(ctl_geoms)} wheat parcels ({pools[season]['unmatched']} unmatched); "
                  f"target beet kept {kept}, not declared beet {skipped}")
    if not rows:
        return pd.DataFrame()
    o = pd.concat(rows, ignore_index=True)
    for col in ("nfk_mm", "ks", "lon", "lat"):
        o[col] = o.id.map(meta[col])
    o = o.merge(eco[eco.season.isin(YEARS)], on=["season", "field"], how="left")
    cap = lambda c: c.mask(np.isinf(c) | c.isna(), MAX_D)
    o["dist_to_source"], o["dist_to_control"] = cap(o.dist_to_source), cap(o.dist_to_control)
    o["dist_capped"] = o.dist_to_source.eq(MAX_D) | o.dist_to_control.eq(MAX_D)
    if slope_at is not None:
        o["slope_pct"] = slope_at(o.x.values, o.y.values)
    return o


# ---------- Step 4: regression, adjacent-edge comparison, curves, demo layer ----------
def fit(dm):
    """delta_ndvi ~ log1p(dist to source) + log1p(dist to control) + June NDVI + nFK + erosion + season FE;
    SEs clustered by parcel (the logs are precomputed: patsy has no log1p)."""
    dm = dm.assign(log_source=np.log1p(dm.dist_to_source), log_control=np.log1p(dm.dist_to_control))
    res = smf.ols(FORMULA, data=dm).fit(cov_type="cluster", cov_kwds={"groups": dm.id})
    coef = lambda n: {"coef": round(float(res.params[n]), 4), "se": round(float(res.bse[n]), 4),
                      "p": round(float(res.pvalues[n]), 4)}
    model = {"n_obs": len(dm), "n_parcels": int(dm.id.nunique()), "r2": round(float(res.rsquared), 3),
             "r2_adj": round(float(res.rsquared_adj), 3),
             "coef": {n: coef(n) for n in ("Intercept", "log_source", "log_control", "ndvi_june",
                                           "nfk_mm", "ks")},
             "season_fe": {n: coef(n) for n in res.params.index if n.startswith("C(season)[T.")}}
    same = FORMULA.replace("log_source + log_control + ", "")
    dm = dm.assign(adj_delta=smf.ols(same, data=dm).fit().resid.values)
    return dm, res, model


def edge_test(dm):
    """Source-vs-control wheat near the edge (< 50 m, Welch test on the mean adjusted canopy delta)."""
    s = dm.adj_delta[dm.dist_to_source < 50]
    c = dm.adj_delta[dm.dist_to_control < 50]
    t = sstats.ttest_ind(s, c, equal_var=False)
    return {"source_adjacent_n": int(len(s)), "control_adjacent_n": int(len(c)),
            "mean_source_adjacent": round(float(s.mean()), 4) if len(s) else None,
            "mean_control_adjacent": round(float(c.mean()), 4) if len(c) else None,
            "mean_source_minus_control": round(float(s.mean() - c.mean()), 4) if len(s) and len(c) else None,
            "welch_t": None if np.isnan(t.statistic) else round(float(t.statistic), 3),
            "p": None if np.isnan(t.pvalue) else round(float(t.pvalue), 4)}


def curves_png(dm):
    """Adjusted canopy delta against the distance to the nearest wheat boundary (any kind): two panels,
    one per wheat type that is nearest (nursery = after beet, control = every other winter wheat), shared
    y axis and x limits, a linear distance scale and a regression line per type."""
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 7.2), sharey=True, sharex=True)
    d_any = dm[["dist_to_source", "dist_to_control"]].min(axis=1)
    for ax, (near, colour, lab) in zip(axes, ((dm.dist_to_source <= dm.dist_to_control,
                                               "#b03a72", "nearest wheat is a nursery (after beet)"),
                                              (dm.dist_to_source > dm.dist_to_control,
                                               "#7a8496", "nearest wheat is control wheat (reference)"))):
        ok = dm[near].assign(d=d_any[near]).dropna(subset=["d", "adj_delta"])
        x, y = ok.d.values, ok.adj_delta.values
        ax.scatter(x, y, s=5, alpha=0.18, color=colour, label=f"n = {len(x)}")
        if len(set(x)) >= 2:
            b = np.polyfit(np.log1p(x), y, 1)
            pred = b[0] * np.log1p(x) + b[1]
            r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
            xs = np.linspace(max(min(x), 1), max(x), 200)
            ax.plot(xs, b[0] * np.log1p(xs) + b[1], color=colour, lw=2,
                    label=f"regression: {b[0]:+.4f} per log1p(d), r2 = {r2:.2f}")
        ax.axhline(0, lw=0.8, color="#999999")
        ax.grid(True)
        ax.set(title=lab)
        ax.legend(frameon=False, fontsize=8, loc="lower right")
    axes[0].set(ylabel="adjusted canopy delta (late - June NDVI)")
    fig.supxlabel("distance to the nearest wheat boundary (m)")
    fig.suptitle("Late-summer canopy decline vs distance to winter wheat\n"
                 "(partial residuals; more negative = worse than expected)")
    fig.tight_layout()
    fig.savefig(out("planthopper_effect/edge_decay_curves.png"), dpi=150)
    plt.close(fig)


def edges_geojson(dm, meta, beta_src, beta_ctl):
    """The demo-field grid points: the observed canopy delta and the model's centred edge component (EPSG:4326)."""
    demo = dm.dropna(subset=["delta_ndvi", "dist_to_source"])
    if not len(demo):
        return 0
    edge = beta_src * np.log1p(demo.dist_to_source) + beta_ctl * np.log1p(demo.dist_to_control)
    edge = edge - edge.mean()
    pts = geo.reproj(shapely.points(demo.x.values, demo.y.values), 25832, 4326)
    feats = [{"type": "Feature", "properties": {
        "id": int(r.id), "season": int(r.season), "field": r.field,
        "dist_to_source_m": round(float(r.dist_to_source), 1),
        "dist_to_control_m": round(float(r.dist_to_control), 1),
        "is_downwind": None if pd.isna(r.is_downwind) else bool(r.is_downwind),
        "delta_ndvi_observed": round(float(r.delta_ndvi), 4), "edge_component": round(float(e), 4),
        "nfk_mm": round(float(v), 1) if pd.notna(v := meta.nfk_mm.get(r.id)) else None},
        "geometry": mapping(p)} for r, e, p in zip(demo.itertuples(), edge, pts)]
    out("planthopper_effect/edges_fiona.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, indent=1), encoding="utf-8")
    return len(feats)


def main():
    print("planthopper: isolating the SBR edge-damage signal in sugar beet")
    lp = pd.read_parquet(PROC / "landscape_parcels.parquet")
    series = pd.read_parquet(PROC / "hls_series.parquet")
    eco = pd.read_parquet(PROC / "ecostress.parquet")
    seasons = pd.read_parquet(PROC / "landscape_seasons.parquet")

    clf, dlr_ok, dlr_n = classify(lp)
    clf.to_parquet(out("planthopper_effect/parcel_classification.parquet"), index=False)
    check("parcel_classification.parquet", clf, "season")
    for y, g in clf.groupby("season"):
        print(f"  season {y}: beet {int((g.role == 'target_beet').sum())} / source wheat "
              f"{int((g.role == 'source_wheat').sum())} / control wheat {int((g.role == 'control_wheat').sum())} "
              f"parcels, DLR agrees {dlr_ok[y]:.0%} of {dlr_n[y]}; nursery "
              f"{g.loc[g.role == 'source_wheat', 'ha'].sum():.0f} ha per parcel vs "
              f"{seasons.loc[seasons.season == y, 'nursery_ha'].sum():.0f} ha in landscape_seasons")

    geoms, geom_src = parcel_geoms()
    meta = lp.drop_duplicates("id").set_index("id").fillna({"field": ""})
    pools, fdata = fiona_pools()
    wind, wind_why = flight_wind()
    o = observations(clf, meta, geoms, pools, fdata, ndvi_windows(series), ecostress_aug(eco),
                     slope_sampler(), wind)
    if not len(o):
        print("  no target beet parcel with a known outline and NDVI - nothing to fit")
        return
    o.to_parquet(out("planthopper_effect/target_beet_observations.parquet"), index=False)
    check("target_beet_observations.parquet", o, "season")

    dm = o.dropna(subset=["delta_ndvi", "ndvi_june", "nfk_mm"]).copy()
    dm["ks"] = dm.ks.fillna(dm.ks.median())
    dm, res, model = fit(dm)
    model["edge_test"] = edge_test(dm)
    model["geometry_source"] = geom_src
    model["wind"] = wind_why or {"bearing_to_deg": wind[0], "mean_ms": wind[1]}
    model["wheat_pools"] = {y: {"declared": bool(pools.get(y)),
                                "n_source": int(len(pools[y]["source_wheat"])),
                                "n_control": int(len(pools[y]["control_wheat"]))}
                            for y in YEARS if pools.get(y)}
    if dm.dist_declared.any():
        dmd = dm[dm.dist_declared]
        res_d = smf.ols(FORMULA, data=dmd).fit(cov_type="cluster", cov_kwds={"groups": dmd.id})
        model["coef_declared_years"] = {n: {"coef": round(float(res_d.params[n]), 4),
                                            "se": round(float(res_d.bse[n]), 4),
                                            "p": round(float(res_d.pvalues[n]), 4)}
                                        for n in ("log_source", "log_control")}
    model["notes"] = ["SEs clustered by parcel; season fixed effects absorb the season mean.",
                      "slope_pct only with the raw NASADEM; the K*S erosion factor is always included.",
                      "is_downwind needs u10/v10 in the ERA5-Land hourly download.",
                      f"canopy windows need >= {MIN_OBS} clear pictures (June {JUNE}, late summer {LATE}).",
                      "distances use the declared FIONA crops where the season and the one before are both "
                      "declared (2023-2025, targets must be declared beet); in 2020-2022 the nearest wheat "
                      "is known inside the demo blocks only, so those distances run against the cap.",
                      "coef_declared_years repeats the fit on the declared seasons only."]
    out("planthopper_effect/regression_summary.json").write_text(json.dumps(model, indent=1), encoding="utf-8")
    with open(out("planthopper_effect/regression_summary.txt"), "w", encoding="utf-8") as f:
        f.write(res.summary().as_text() + "\n\nAdjacent-edge comparison (mean adjusted canopy delta, < 50 m):\n")
        f.write(f"  source adjacent vs control adjacent: {json.dumps(model['edge_test'])}\n")

    curves_png(dm)
    n = edges_geojson(dm, meta, model["coef"]["log_source"]["coef"],
                      model["coef"]["log_control"]["coef"])
    print(f"  regression: r2 {model['r2']}, beta_source {model['coef']['log_source']}, "
          f"beta_control {model['coef']['log_control']}")
    print(f"  edges_fiona.geojson: {n} grid points, edge_decay_curves.png")


if __name__ == "__main__":
    main()
