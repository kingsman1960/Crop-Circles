"""Crop sequences of every FIONA parcel in the Kraichgau window (--bw: all of Baden-Württemberg), for the landscape planner.

Outputs:
  landscape_parcels.parquet  parcels that grew sugar beet or were a planthopper nursery in any season:
                             position, area, erosion (K·S) and plant-available water, crop code per year 2017–2025
  landscape_seasons.parquet  per season y (2018–2025): nursery ha (beet in y-1 -> winter wheat in y) and beet ha.
                             Seasons 2023–2025 (`source` = "fiona"): from the farmers' declarations, with the Thünen
                             map as `_thuenen`; earlier seasons (`source` = "thuenen"): from the Thünen map
                             (`_thuenen` = NaN). The DLR map (`_dlr`) is the check in every season.
  landscape_summary.json     regional numbers per season, incl. targeted vs. random switching (see pressure.py),
                             the same from the DLR map (and Thünen where FIONA is the source), and how much of the
                             nursery area each confirms
Parcels are the FIONA 2022 outlines (the only parcel map for the whole window); crops per year come from the Thünen
10 m maps (c<year>); the DLR CropTypes 10 m maps (d<year>) are a second, independently made opinion; the FIONA
declarations of each year (f<year>, NC code), burnt onto the Thünen grid, are the ground truth both maps are trained on.
--bw writes the same three files with the suffix _bw. Its window also covers parts of the neighbouring states, where
FIONA has no parcels, so the regional hectares are counted inside FIONA parcels there, not over all map pixels.
"""
import json
import sys

import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio import features
from shapely.geometry import shape

from pipeline import geo
from pipeline.common import FIELDS, RAW, check, out
from pipeline.landscape_geo import write_parcels_geo
from pipeline.pressure import impacts

YEARS = range(2017, 2026)
BEET, WHEAT = 1402, 1101
# DLR: sugar beet; winter wheat + other winter cereals (spelt, triticale), which Thünen has no own class for
DLR_BEET, DLR_WHEAT = 60, (11, 14)
dlr_path = lambda y, tag: RAW / "dlr_croptypes" / f"CROPTYPES_DE_P1Y_{y}_V021_{tag}.tif"
# FIONA NC codes: sugar beet; winter wheat incl. durum, spelt, emmer/einkorn, triticale (the scope of DLR 11 + 14)
FIONA_BEET, FIONA_WHEAT = 603, (112, 114, 115, 118, 156)
fiona_pages = lambda y, tag: sorted((RAW / "fiona").glob(f"fiona_{tag}{'' if y == 2022 else f'_{y}'}_p*.json"))
AREA = ["nursery_ha", "beet_ha", "nursery_ha_dlr", "beet_ha_dlr", "nursery_ha_thuenen", "beet_ha_thuenen"]
MIN_HA = 0.1  # less than 10 pixels in a parcel = edge noise between map and parcel outline
NFK_MID = {1: 35, 2: 70, 3: 115, 4: 170, 5: 220}  # mm, middle of the BK50 nFK classes


def nfk_mm(raw):
    c = geo.classes(raw)
    return float(np.mean([NFK_MID[i] for i in c])) if c else np.nan


def zonal_mean(ids, values, n):
    """Mean of `values` per parcel id (0 = no parcel); NaN where a parcel has no valid pixel."""
    ok = (ids > 0) & ~np.isnan(values)
    s = np.bincount(ids[ok], values[ok], minlength=n)
    c = np.bincount(ids[ok], minlength=n)
    return np.where(c > 0, s / np.maximum(c, 1), np.nan)


def majority(ids, a, n):
    """Most frequent class per parcel (raster value i = row i-1; 0 = no class pixel; nodata is 0 or -9999)."""
    valid = (a > 0) & (ids > 0)
    codes, inv = np.unique(a[valid], return_inverse=True)
    cnt = np.bincount(ids[valid] * len(codes) + inv, minlength=n * len(codes)).reshape(n, -1)[1:]
    return np.where(cnt.sum(1) > 0, codes[cnt.argmax(1)], 0).astype("int16")


def fiona_raster(y, tag, shp, transform):
    """Declared crop (NC code) per pixel of the Thünen grid from the FIONA polygons of Antragsjahr y."""
    feats = [f for p in fiona_pages(y, tag) for f in json.loads(p.read_text(encoding="utf-8"))["features"]]
    g = geo.reproj(np.array([shape(f["geometry"]) for f in feats], dtype=object), 25832, 3035)
    return features.rasterize(zip(g, (int(f["properties"]["NC"]) for f in feats)), shp, transform=transform, fill=0,
                              dtype="int16")


def targeted(cur, xy, n_col, b_col):
    """Share of the pressure removed when the 20 % of the nursery area that removes most per ha switches."""
    nur, beet = cur[cur[n_col] > 0], cur[cur[b_col] > 0]
    res = {}
    for r in (500, 1000, 2000):
        imp, _ = impacts(xy.loc[nur.id].values.astype("float32"), nur[n_col].values.astype("float32"),
                         xy.loc[beet.id].values.astype("float32"), beet[b_col].values.astype("float32"), r)
        order = np.argsort(-imp / nur[n_col].values)  # most pressure removed per ha switched
        top = order[: np.searchsorted(np.cumsum(nur[n_col].values[order]), 0.2 * nur[n_col].sum())]
        res[f"targeted20_r{r}"] = round(float(imp[top].sum() / imp.sum()), 3)
    return res


def legends():
    """Crop names per language from the Thünen legend files (CTM_GER_Legend<EN|DE>_rst_v202.clr)."""
    fix = {"gruen": "grün", "ruebe": "rübe", "Gehoelz": "Gehölz", "Flaechen": "Flächen"}  # the DE file spells umlauts out
    out = {}
    for f in sorted(geo.CTM.glob("CTM_GER_Legend*_rst_v202.clr")):
        lang = f.stem.split("_")[2].removeprefix("Legend").lower()
        names = {}
        for line in f.read_text(encoding="utf-8").splitlines():
            if parts := line.split():
                name = " ".join(parts[5:])
                for a, b in fix.items():
                    name = name.replace(a, b)
                names[int(parts[0])] = name
        out[lang] = names
    return out


def main(tag="bbox"):
    sfx = "" if tag == "bbox" else f"_{tag}"
    fiona = [(f["properties"]["object_id"], f["properties"]["Bezeichnung"], shape(f["geometry"]))
             for p in sorted((RAW / "fiona").glob(f"fiona_{tag}_p*.json"))
             for f in json.loads(p.read_text(encoding="utf-8"))["features"]]
    df = pd.DataFrame(fiona, columns=["id", "crop2022", "geom"])
    n = len(df) + 1  # raster value i+1 = row i
    g3035 = geo.reproj(df.geom.values, 25832, 3035)
    g4326 = geo.reproj(df.geom.values, 25832, 4326)
    df["area_ha"] = [g.area / 1e4 for g in df.geom]
    c3035 = np.array([[g.centroid.x, g.centroid.y] for g in g3035])
    c4326 = np.array([[g.centroid.x, g.centroid.y] for g in g4326])
    df["x"], df["y"], df["lon"], df["lat"] = c3035[:, 0], c3035[:, 1], c4326[:, 0], c4326[:, 1]

    # erosion and water per parcel on the NASADEM grid: K (BK50) x S (slope), nFK (BK50)
    units, attrs = geo.bk50(tag)
    dem, T, _, s_fac = geo.dem_slope(tag)
    u4326 = geo.reproj(np.array([g for _, g in units], dtype=object), 25832, 4326)
    burn = lambda key, fn: features.rasterize(((g, fn(attrs.get(u, {}).get(key))) for (u, _), g in zip(units, u4326)),
                                              dem.shape, transform=T, fill=np.nan, dtype="float32")
    k_r, nfk_r = burn("kfa", geo.k_value), burn("nfk", nfk_mm)
    ids = features.rasterize(zip(g4326, range(1, n)), dem.shape, transform=T, fill=0, dtype="int32")
    df["ks"] = zonal_mean(ids, k_r * s_fac, n)[1:]
    df["nfk_mm"] = zonal_mean(ids, nfk_r, n)[1:]
    # parcels smaller than a DEM pixel: value at the centroid
    col, row = ~T * (df.lon.values, df.lat.values)
    row, col = np.clip(row.astype(int), 0, dem.shape[0] - 1), np.clip(col.astype(int), 0, dem.shape[1] - 1)
    df["ks"] = df.ks.fillna(pd.Series((k_r * s_fac)[row, col]))
    df["nfk_mm"] = df.nfk_mm.fillna(pd.Series(nfk_r[row, col]))
    del units, u4326, dem, k_r, nfk_r, s_fac, ids  # BW: several GB, not needed below

    # crops per parcel and year: Thünen (EPSG:3035) and DLR (EPSG:32632, FIONA's EPSG:25832 within a metre), both 10 m
    with rasterio.open(geo.ctm_path(2017, tag)) as src:
        ids = features.rasterize(zip(g3035, range(1, n)), src.shape, transform=src.transform, fill=0, dtype="int32")
        grid = src.shape, src.transform
    # FIONA only where a year after 2022 was fetched (bbox 2022-2025; BW has 2022 only)
    fiona_years = {y for y in YEARS if fiona_pages(y, tag)} if any(fiona_pages(y, tag) for y in YEARS if y > 2022) else set()
    with rasterio.open(dlr_path(2017, tag)) as src:
        ids_d = features.rasterize(zip(df.geom.values, range(1, n)), src.shape, transform=src.transform, fill=0,
                                   dtype="int32")
        px_d = abs(src.res[0] * src.res[1]) / 1e4
    per_parcel = lambda ids_, mask, px: np.bincount(ids_[mask & (ids_ > 0)], minlength=n)[1:] * px  # ha
    # regional hectares: all map pixels in the bbox; BW: inside FIONA parcels (the window reaches into other states)
    ha = (lambda m: m.sum() / 100) if tag == "bbox" else (lambda m: per_parcel(ids, m, 0.01).sum())
    ha_d = (lambda m: m.sum() * px_d) if tag == "bbox" else (lambda m: per_parcel(ids_d, m, px_d).sum())
    seasons, summary, prev, prev_d, prev_f = [], [], None, None, None
    for y in YEARS:
        with rasterio.open(geo.ctm_path(y, tag)) as src:
            a = src.read(1)
        with rasterio.open(dlr_path(y, tag)) as src:
            d = src.read(1)
        df[f"c{y}"], df[f"d{y}"] = majority(ids, a, n), majority(ids_d, d, n)
        f = fiona_raster(y, tag, *grid) if y in fiona_years else None
        if f is not None:
            df[f"f{y}"] = majority(ids, f, n)
        if prev is not None:
            nursery, nursery_d = (prev == BEET) & (a == WHEAT), (prev_d == DLR_BEET) & np.isin(d, DLR_WHEAT)
            s = pd.DataFrame({"season": y, "id": df.id, "nursery_ha": per_parcel(ids, nursery, 0.01),
                              "beet_ha": per_parcel(ids, a == BEET, 0.01),
                              "nursery_ha_dlr": per_parcel(ids_d, nursery_d, px_d),
                              "beet_ha_dlr": per_parcel(ids_d, d == DLR_BEET, px_d)})
            regional = lambda prev_, cur_, beet_, nursery_: {
                "beet_prev_ha": round(ha(prev_ == beet_)), "nursery_ha": round(ha(nursery_)), "beet_ha": round(ha(cur_ == beet_)),
                "beet_to_wheat": round(ha(nursery_) / max(ha(prev_ == beet_), 0.01), 3)}
            sm = {"season": y, "source": "thuenen", "map": "v302 preliminary" if y == 2025 else "v202",
                  "dlr": {"beet_prev_ha": round(ha_d(prev_d == DLR_BEET)), "nursery_ha": round(ha_d(nursery_d)),
                          "beet_ha": round(ha_d(d == DLR_BEET)),
                          "beet_to_wheat": round(ha_d(nursery_d) / max(ha_d(prev_d == DLR_BEET), 0.01), 3)}}
            if f is not None and prev_f is not None:  # the farmers' declarations are the source, Thünen the check
                nursery_f = (prev_f == FIONA_BEET) & np.isin(f, FIONA_WHEAT)
                s["nursery_ha_thuenen"], s["beet_ha_thuenen"] = s.nursery_ha, s.beet_ha
                s["nursery_ha"], s["beet_ha"] = per_parcel(ids, nursery_f, 0.01), per_parcel(ids, f == FIONA_BEET, 0.01)
                sm |= regional(prev_f, f, FIONA_BEET, nursery_f) | {"source": "fiona", "thuenen": regional(prev, a, BEET, nursery)}
                nursery = nursery_f
            else:
                sm |= regional(prev, a, BEET, nursery)
            area = [c for c in AREA if c in s]
            s[area] = s[area].where(s[area] >= MIN_HA, 0)
            seasons.append(s[(s[area] > 0).any(axis=1)])
            sm["nursery_in_parcels"] = round(float(s.nursery_ha.sum() / ha(nursery)), 3)
            summary.append(sm)
        prev, prev_d, prev_f = a, d, f

    seasons = pd.concat(seasons, ignore_index=True)
    keep = df.id.isin(seasons.id)
    fields = {f["id"]: geo.reproj(shape(f["polygon"]), 4326, 3035) for f in FIELDS}
    df["field"] = ""
    for fid, g in fields.items():
        df.loc[shapely.contains_xy(g, df.x, df.y), "field"] = fid
    df = df[keep]
    write_parcels_geo(df.id, list(df.geom), sfx)  # same geometries the parcels above were rasterised with
    df = df.drop(columns="geom")
    df.to_parquet(out(f"landscape_parcels{sfx}.parquet"), index=False)
    seasons.to_parquet(out(f"landscape_seasons{sfx}.parquet"), index=False)
    check(f"landscape_parcels{sfx}.parquet", df)
    check(f"landscape_seasons{sfx}.parquet", seasons, "season")

    # targeted vs. random switching of 20 % of the nursery area, for three flight distances, on both maps
    xy = df.set_index("id")[["x", "y"]]
    for s in summary:
        cur = seasons[seasons.season == s["season"]]
        s |= targeted(cur, xy, "nursery_ha", "beet_ha")
        s["dlr"] |= targeted(cur, xy, "nursery_ha_dlr", "beet_ha_dlr")
        s["dlr"]["confirmed"] = round(float(cur.nursery_ha[cur.nursery_ha_dlr > 0].sum() / cur.nursery_ha.sum()), 3)
        thu = ""
        if "thuenen" in s:
            s["thuenen"] |= targeted(cur, xy, "nursery_ha_thuenen", "beet_ha_thuenen")
            s["thuenen"]["confirmed"] = round(float(cur.nursery_ha[cur.nursery_ha_thuenen > 0].sum() / cur.nursery_ha.sum()), 3)
            thu = (f" | Thünen: nursery {s['thuenen']['nursery_ha']} ha, removes {s['thuenen']['targeted20_r1000']:.0%} at 1 km; "
                   f"{s['thuenen']['confirmed']:.0%} of the declared nursery area confirmed")
        print(f"  season {s['season']} ({s['source']}): beet->wheat {s['beet_to_wheat']:.0%}, nursery {s['nursery_ha']} ha, "
              f"20 % targeted removes {s['targeted20_r500']:.0%} / {s['targeted20_r1000']:.0%} / {s['targeted20_r2000']:.0%} "
              f"(r = 0.5 / 1 / 2 km; random ~20 %) | DLR: nursery {s['dlr']['nursery_ha']} ha, removes "
              f"{s['dlr']['targeted20_r1000']:.0%} at 1 km; {s['dlr']['confirmed']:.0%} of the nursery area confirmed{thu}")
    out(f"landscape_summary{sfx}.json").write_text(json.dumps(
        {"seasons": summary, "legends": legends()}, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main("bw" if "--bw" in sys.argv else "bbox")
