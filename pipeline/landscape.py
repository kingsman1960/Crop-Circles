"""Crop sequences of every FIONA parcel in the Kraichgau window, for the landscape planner.

Outputs:
  landscape_parcels.parquet  parcels that grew sugar beet or were a planthopper nursery in any season:
                             position, area, erosion (K·S) and plant-available water, crop code per year 2017–2025
  landscape_seasons.parquet  per season y (2018–2025): nursery ha (beet in y-1 -> winter wheat in y) and beet ha
  landscape_summary.json     regional numbers per season, incl. targeted vs. random switching (see pressure.py)
Parcels are the FIONA 2022 outlines (the only parcel map); crops per year come from the Thünen 10 m maps.
"""
import json

import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio import features
from shapely.geometry import shape

from pipeline import geo
from pipeline.common import FIELDS, RAW, check, out
from pipeline.pressure import impacts

YEARS = range(2017, 2026)
BEET, WHEAT = 1402, 1101
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


def main():
    fiona = [(f["properties"]["object_id"], f["properties"]["Bezeichnung"], shape(f["geometry"]))
             for p in sorted((RAW / "fiona").glob("fiona_bbox_p*.json"))
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
    units, attrs = geo.bk50()
    dem, T, _, s_fac = geo.dem_slope()
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

    # crops per parcel and year from the Thünen maps
    with rasterio.open(geo.ctm_path(2017)) as src:
        shp, T3035 = src.shape, src.transform
    ids = features.rasterize(zip(g3035, range(1, n)), shp, transform=T3035, fill=0, dtype="int32")
    leg = geo.legend()
    codes = np.array(sorted(leg))
    lut = np.zeros(codes.max() + 1, np.int64)
    lut[codes] = np.arange(1, len(codes) + 1)
    per_parcel = lambda mask: np.bincount(ids[mask & (ids > 0)], minlength=n)[1:] * 0.01  # ha (10 m pixels)
    seasons, summary, prev = [], [], None
    for y in YEARS:
        with rasterio.open(geo.ctm_path(y)) as src:
            a = src.read(1)
        valid = (a > 0) & (ids > 0)  # nodata is -9999 or 0 depending on the year
        cnt = np.bincount(ids[valid] * (len(codes) + 1) + lut[np.minimum(a[valid], len(lut) - 1)], minlength=n * (len(codes) + 1))
        cnt = cnt.reshape(n, -1)[1:, 1:]
        df[f"c{y}"] = np.where(cnt.sum(1) > 0, codes[cnt.argmax(1)], 0).astype("int16")
        if prev is not None:
            nursery = (prev == BEET) & (a == WHEAT)
            s = pd.DataFrame({"season": y, "id": df.id, "nursery_ha": per_parcel(nursery), "beet_ha": per_parcel(a == BEET)})
            s[["nursery_ha", "beet_ha"]] = s[["nursery_ha", "beet_ha"]].where(s[["nursery_ha", "beet_ha"]] >= MIN_HA, 0)
            seasons.append(s[(s.nursery_ha > 0) | (s.beet_ha > 0)])
            summary.append({"season": y, "beet_prev_ha": round((prev == BEET).sum() / 100),
                            "nursery_ha": round(nursery.sum() / 100), "beet_ha": round((a == BEET).sum() / 100),
                            "beet_to_wheat": round(nursery.sum() / max((prev == BEET).sum(), 1), 3),
                            "nursery_in_parcels": round(float(s.nursery_ha.sum() / (nursery.sum() / 100)), 3),
                            "map": "v302 preliminary" if y == 2025 else "v202"})
        prev = a

    seasons = pd.concat(seasons, ignore_index=True)
    keep = df.id.isin(seasons.id)
    fields = {f["id"]: geo.reproj(shape(f["polygon"]), 4326, 3035) for f in FIELDS}
    df["field"] = ""
    for fid, g in fields.items():
        df.loc[shapely.contains_xy(g, df.x, df.y), "field"] = fid
    df = df[keep].drop(columns="geom")
    df.to_parquet(out("landscape_parcels.parquet"), index=False)
    seasons.to_parquet(out("landscape_seasons.parquet"), index=False)
    check("landscape_parcels.parquet", df)
    check("landscape_seasons.parquet", seasons, "season")

    # targeted vs. random switching of 20 % of the nursery area, for three flight distances
    xy = df.set_index("id")[["x", "y"]]
    for s in summary:
        cur = seasons[seasons.season == s["season"]]
        nur, beet = cur[cur.nursery_ha > 0], cur[cur.beet_ha > 0]
        for r in (500, 1000, 2000):
            imp, pres = impacts(xy.loc[nur.id].values.astype("float32"), nur.nursery_ha.values.astype("float32"),
                                xy.loc[beet.id].values.astype("float32"), beet.beet_ha.values.astype("float32"), r)
            order = np.argsort(-imp / nur.nursery_ha.values)  # most pressure removed per ha switched
            top = order[: np.searchsorted(np.cumsum(nur.nursery_ha.values[order]), 0.2 * nur.nursery_ha.sum())]
            s[f"targeted20_r{r}"] = round(float(imp[top].sum() / imp.sum()), 3)
        print(f"  season {s['season']}: beet->wheat {s['beet_to_wheat']:.0%}, nursery {s['nursery_ha']} ha, "
              f"20 % targeted removes {s['targeted20_r500']:.0%} / {s['targeted20_r1000']:.0%} / {s['targeted20_r2000']:.0%} "
              f"(r = 0.5 / 1 / 2 km; random ~20 %)")
    out("landscape_summary.json").write_text(json.dumps(
        {"seasons": summary, "legends": legends()}, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
