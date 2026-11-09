"""Field profiles, crop history and map layers from BK50, NASADEM, SoilGrids, FIONA and Thünen."""
import json
import math
import re
from functools import lru_cache
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import rasterio
import shapely
from PIL import Image
from pyproj import Transformer
from rasterio import features, warp
from rasterio.mask import mask as rmask
from shapely.geometry import MultiPolygon, Polygon, mapping, shape

from .common import RAW, FIELDS, out, check

GML = "{http://www.opengis.net/gml}"
MS = "{http://mapserver.gis.umn.edu/mapserver}"
K_MID = {1: 0.05, 2: 0.15, 3: 0.25, 4: 0.4, 5: 0.6, 6: 0.85}
NFK_MM = {1: (0, 50), 2: (50, 90), 3: (90, 140), 4: (140, 200), 5: (200, None)}
NFK_MID = {1: 35, 2: 70, 3: 115, 4: 170, 5: 220}  # mm, middle of each class (≥200 taken as 220)
CTM = RAW / "thuenen_ctm"
V202_YEARS = range(2017, 2025)
BEET, WHEAT = 1402, 1101
TRANSITION_FROM = {1402, 1101, 1102, 1300}
RAMP = [(0, "#f4f6f8"), (0.3, "#c3cad4"), (0.55, "#7d889c"), (1.0, "#16213e")]  # one ink ramp: the data hue is kept for the planthopper


@lru_cache
def _tf(src, dst):
    return Transformer.from_crs(src, dst, always_xy=True)


def reproj(geom, src, dst):
    """Shapely geometry (or array of them) from EPSG src to dst."""
    t = _tf(src, dst)
    return shapely.transform(geom, lambda xy: np.column_stack(t.transform(xy[:, 0], xy[:, 1])))


def num(x, d=3):
    return None if x is None or math.isnan(float(x)) else round(float(x), d)


def classes(raw):
    """'4,5(6)' -> [4, 5]: classes in () occur only locally and are dropped; '3/1,2' keeps topsoil."""
    return [int(c) for c in re.findall(r"\d", re.sub(r"\(.*?\)", "", raw or "").split("/")[0])]


def k_value(raw):
    c = classes(raw)
    return float(np.mean([K_MID[i] for i in c])) if c else math.nan


def nfk_text(raw):
    c = classes(raw)
    if not c:
        return None
    lo, hi = NFK_MM[min(c)][0], NFK_MM[max(c)][1]
    return f"≥{lo} mm" if hi is None else f"<{hi} mm" if lo == 0 else f"{lo}–{hi} mm"


def ks_class(v):
    return None if v is None or math.isnan(v) else "low" if v < 0.3 else "medium" if v < 0.55 else "high"


# ---------- BK50 ----------
def gml_geom(el):
    ring = lambda r: np.array(r.find(f".//{GML}posList").text.split(), float).reshape(-1, 2)
    polys = [Polygon(ring(p.find(f"{GML}exterior")), [ring(i) for i in p.findall(f"{GML}interior")])
             for p in el.iter(f"{GML}Polygon")]
    g = polys[0] if len(polys) == 1 else MultiPolygon(polys)
    return g if g.is_valid else g.buffer(0)


def bk50(tag="bbox"):
    """(soil-unit polygons, attributes per unit) for the study bbox, or all of BW (tag "bw", in bk50/bw/)."""
    folder = RAW / "bk50" / ("" if tag == "bbox" else tag)
    attrs = {}
    for t, col in [("kfa", "kfa-Wert"), ("nfk", "nfk-Wert"), ("kf", "KF")]:
        for p in sorted(folder.glob(f"geola_bod_ke_{t}*.gml")):  # one file, or pages _p00, _p01, …
            for _, el in ET.iterparse(p):
                if el.tag == f"{MS}geola_bod_ke_{t}":
                    a = attrs.setdefault(el.findtext(f"{MS}Kartiereinheit"), {})
                    a[t] = (el.findtext(f"{MS}{col}") or "").strip()
                    a["legend"] = el.findtext(f"{MS}Legendentext") or a.get("legend", "")
                    a["link"] = el.findtext(f"{MS}Link") or a.get("link", "")
                    el.clear()
    units = []
    for p in sorted(folder.glob("geola_bod_ke_[pt][0-9]*.gml")):  # pages (bbox) or tiles (BW)
        for _, el in ET.iterparse(p):
            if el.tag == f"{MS}geola_bod_ke":
                units.append((el.findtext(f"{MS}Kartiereinheit"), gml_geom(el.find(f"{MS}msGeometry"))))
                el.clear()
    return units, attrs


def soil_profile(field25832, units, attrs):
    area = {}
    for u, g in units:
        if g.intersects(field25832):
            area[u] = area.get(u, 0) + g.intersection(field25832).area
    total = field25832.area
    rows = sorted(({"unit": u, "legend": attrs.get(u, {}).get("legend", ""), "share": round(a / total, 3),
                    **{t: attrs.get(u, {}).get(t, "") for t in ("kfa", "nfk", "kf", "link")}}
                   for u, a in area.items()), key=lambda r: -r["share"])
    kv = [(k_value(r["kfa"]), r["share"]) for r in rows]
    kv = [(k, s) for k, s in kv if not math.isnan(k)]
    k = sum(k * s for k, s in kv) / sum(s for _, s in kv) if kv else math.nan
    d = rows[0]
    return {"soil_units": rows, "dominant_unit": d["unit"], "dominant_legend": d["legend"],
            "k_class": d["kfa"].replace(",", "–"), "k_factor": num(k), "nfk_class": d["nfk"],
            "nfk_mm": nfk_text(d["nfk"]), "kf_class": d["kf"],
            "nfk_mid_mm": num(np.mean([NFK_MID[i] for i in classes(d["nfk"])]), 0) if classes(d["nfk"]) else None}


# ---------- DEM ----------
def dem_slope(tag="bbox"):
    with rasterio.open(RAW / "dem" / f"dem_{tag}.tif") as src:
        dem, T = src.read(1).astype(float), src.transform
    lat = T.f + (np.arange(dem.shape[0]) + 0.5) * T.e
    gy, gx = np.gradient(dem)
    tan = np.hypot(gx / (T.a * 111320 * np.cos(np.radians(lat))[:, None]), gy / (abs(T.e) * 110540))
    sin = np.sin(np.arctan(tan))
    return dem, T, tan * 100, 65.41 * sin**2 + 4.56 * sin + 0.065


def soilgrids(fid):
    names = {"clay": "clay_pct", "silt": "silt_pct", "sand": "sand_pct", "soc": "soc_gkg",
             "phh2o": "ph", "bdod": "bdod", "cec": "cec"}
    res = {}
    for lyr in json.loads((RAW / "soilgrids" / f"{fid}.json").read_text())["properties"]["layers"]:
        d = [x for x in lyr["depths"] if x["range"]["bottom_depth"] <= 30]
        w = [x["range"]["bottom_depth"] - x["range"]["top_depth"] for x in d]
        v = sum(x["values"]["mean"] * wi for x, wi in zip(d, w)) / sum(w) / lyr["unit_measure"]["d_factor"]
        res[names[lyr["name"]]] = round(v, 2)
    return res


# ---------- FIONA ----------
def fiona_features():
    """(year, feature): FIONA 2022 (WFS, whole bbox) and 2023 on (WMS answers around the demo fields, once per parcel)."""
    for p in sorted((RAW / "fiona").glob("fiona_bbox_p*.json")):
        for f in json.loads(p.read_text(encoding="utf-8"))["features"]:
            yield 2022, f
    seen = set()
    for p in sorted((RAW / "fiona" / "wms_ab2023").glob("F*_20*.geojson")):
        for f in json.loads(p.read_text(encoding="utf-8"))["features"]:
            if f["id"] not in seen:
                seen.add(f["id"])
                yield f["properties"]["Antragsjahr"], f


def fiona_parcels(fields25832):
    hits = []
    for year, f in fiona_features():
        g = None
        x0, y0, x1, y1 = f.get("bbox") or (g := shape(f["geometry"])).bounds
        for fid, fg in fields25832.items():
            fx0, fy0, fx1, fy1 = fg.bounds
            if x1 < fx0 or x0 > fx1 or y1 < fy0 or y0 > fy1:
                continue
            g = g or shape(f["geometry"])
            inter = g.intersection(fg).area
            if inter >= 0.5 * g.area or inter >= 2000:
                pr = f["properties"]
                hits.append({"field": fid, "year": year, "crop": pr["Bezeichnung"], "group": pr["Kulturartengruppe"],
                             "nc": pr["NC"], "ha": round(g.area / 1e4, 2), "geom": g})
    return hits


# ---------- Thünen ----------
def legend():
    leg = {}
    for line in (CTM / "CTM_GER_LegendEN_rst_v202.clr").read_text(encoding="utf-8").splitlines():
        p = line.split()
        if p:
            leg[int(p[0])] = (" ".join(p[5:]), "#%02x%02x%02x" % tuple(map(int, p[1:4])))
    return leg


def ctm_path(year, tag="bbox"):
    return CTM / (f"CTM_GER_{year}_rst_v202_{tag}.tif" if year < 2025 else f"CTM_GER_2025_rst_v302_2025_08_{tag}.tif")


def crop_history(fields3035, leg):
    rows = []
    for year in [*V202_YEARS, 2025]:
        with rasterio.open(ctm_path(year)) as src:
            for fid, g in fields3035.items():
                a, _ = rmask(src, [mapping(g)], crop=True, filled=True, nodata=-9999)
                codes, n = np.unique(a[a > 0], return_counts=True)  # nodata is -9999 or 0 depending on year
                for c, k in zip(codes, n):
                    rows.append({"field": fid, "year": year, "source": "thuenen_v202" if year < 2025 else
                                 "thuenen_v302_prelim", "code": int(c), "name": leg.get(int(c), (str(c),))[0],
                                 "share": k / n.sum(), "ha": k * 0.01})
    return pd.DataFrame(rows)


def transitions(fields3035, leg):
    with rasterio.open(ctm_path(2017)) as src:
        shp, T = src.shape, src.transform
    zones = {fid: features.geometry_mask([mapping(g)], shp, T, invert=True) for fid, g in fields3035.items()}
    zones["bbox"] = np.ones(shp, bool)
    rows, prev = [], None
    for year in V202_YEARS:
        with rasterio.open(ctm_path(year)) as src:
            cur = src.read(1)
        if prev is not None:
            ok = np.isin(prev, list(TRANSITION_FROM)) & (cur > 0)
            for z, m in zones.items():
                pair, n = np.unique(prev[ok & m].astype(np.int64) * 10000 + cur[ok & m], return_counts=True)
                for p, k in zip(pair, n):
                    rows.append({"field": z, "year_from": year - 1, "from": int(p // 10000), "to": int(p % 10000), "px": k})
        prev = cur
    df = pd.DataFrame(rows)
    df["share_of_from"] = df.px / df.groupby(["field", "year_from", "from"]).px.transform("sum")
    df["ha"], df["from_name"], df["to_name"] = df.px * 0.01, df["from"].map(lambda c: leg[c][0]), df.to.map(lambda c: leg[c][0])
    return df


# ---------- layers ----------
def save_layer(name, rgba, bounds, meta):
    Image.fromarray(rgba, "RGBA").save(out(f"layers/{name}.png"), optimize=True)
    out(f"layers/{name}.json").write_text(json.dumps({"bounds": bounds, **meta}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  layers/{name}.png: {rgba.shape[1]} x {rgba.shape[0]} px")


def ramp(v):
    xs = [s for s, _ in RAMP]
    rgb = [[int(h[i:i + 2], 16) for h in (c for _, c in RAMP)] for i in (1, 3, 5)]
    img = np.zeros((*v.shape, 4), np.uint8)
    for i in range(3):
        img[..., i] = np.interp(np.nan_to_num(v), xs, rgb[i])
    img[..., 3] = np.where(np.isnan(v), 0, 255)
    return img


def main():
    print("geo: BK50, NASADEM, SoilGrids, FIONA, Thuenen")
    f4326 = {f["id"]: shape(f["polygon"]) for f in FIELDS}
    f25832 = {k: reproj(g, 4326, 25832) for k, g in f4326.items()}
    f3035 = {k: reproj(g, 4326, 3035) for k, g in f4326.items()}
    units, attrs = bk50()
    dem, T, slope_pct, s_fac = dem_slope()
    leg = legend()

    crops = crop_history(f3035, leg)
    crops.to_parquet(out("crops.parquet"), index=False)
    check("crops.parquet", crops, "year")
    tr = transitions(f3035, leg)
    tr[["field", "year_from", "from_name", "to_name", "ha", "share_of_from"]].to_parquet(out("crop_transitions.parquet"), index=False)
    check("crop_transitions.parquet", tr, "year_from")

    def b2w(z):
        b = tr[(tr.field == z) & (tr["from"] == BEET)]
        return b[b.to == WHEAT].px.sum() / b.px.sum() if b.px.sum() else math.nan

    beet = crops[(crops.code == BEET) & (crops.source == "thuenen_v202")]
    all_years = crops[crops.source == "thuenen_v202"][["field", "year"]].drop_duplicates()
    beet_share = all_years.merge(beet, how="left").fillna({"share": 0}).groupby("field").share.mean()
    bbox_beet = []
    for y in V202_YEARS:
        with rasterio.open(ctm_path(y)) as src:
            a = src.read(1)
        bbox_beet.append((a == BEET).sum() / (a > 0).sum())

    parcels = fiona_parcels(f25832)
    feats = []
    for f in FIELDS:
        fid = f["id"]
        m = features.geometry_mask([mapping(f4326[fid])], dem.shape, T, invert=True)
        sp = slope_pct[m]
        p = {"id": fid, "label": f["label"], "lat": f["lat"], "lon": f["lon"], "area_ha": num(f25832[fid].area / 1e4, 1),
             "elev_mean_m": num(dem[m].mean(), 0), "slope_mean_pct": num(sp.mean(), 1),
             "slope_p90_pct": num(np.percentile(sp, 90), 1), "slope_max_pct": num(sp.max(), 1),
             "s_factor": num(s_fac[m].mean()), **soil_profile(f25832[fid], units, attrs)}
        ks = p["k_factor"] * p["s_factor"] if p["k_factor"] is not None else math.nan
        crops_f = pd.DataFrame([h for h in parcels if h["field"] == fid and h["year"] == 2022])
        p |= {"erosion_ks": num(ks), "erosion_class": ks_class(ks),
              "erosion_note": "screening classes on K·S; thresholds to verify against GAPKondV/DIN 19708",
              **soilgrids(fid),
              "fiona_2022": crops_f.groupby(["crop", "group"]).ha.sum().round(2).reset_index()
              .sort_values("ha", ascending=False).to_dict("records") if len(crops_f) else [],
              "beet_share_mean": num(beet_share.get(fid, 0)), "beet_to_wheat": num(b2w(fid)),
              "bbox_beet_share_mean": num(np.mean(bbox_beet)), "bbox_beet_to_wheat": num(b2w("bbox"))}
        feats.append({"type": "Feature", "id": fid, "properties": p, "geometry": mapping(f4326[fid])})
    out("fields.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")
    print(f"  fields.geojson: {len(feats)} fields")

    pf = [{"type": "Feature", "properties": {k: h[k] for k in ("field", "year", "crop", "group", "nc", "ha")},
           "geometry": mapping(shapely.set_precision(reproj(h["geom"], 25832, 4326), 1e-6))} for h in parcels]
    out("parcels.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": pf}, ensure_ascii=False), encoding="utf-8")
    print(f"  parcels.geojson: {len(pf)} parcels")

    # map layers on the DEM grid (EPSG:4326), downsampled x2
    h, w = dem.shape[0] // 2, dem.shape[1] // 2
    bounds = [T.c, T.f + T.e * 2 * h, T.c + T.a * 2 * w, T.f]
    g4326 = reproj(np.array([g for _, g in units], dtype=object), 25832, 4326)
    kr = features.rasterize(((mapping(g), k_value(attrs.get(u, {}).get("kfa")))
                             for (u, _), g in zip(units, g4326)), dem.shape, transform=T, fill=np.nan, dtype="float32")
    save_layer("erosion_ks", ramp((kr * s_fac)[:2 * h:2, :2 * w:2]), bounds, {
        "title": "Erosion screening: K factor × slope factor", "unit": "K·S (–)", "stops": RAMP,
        "source": "BK50 LGRB (K factor) × NASADEM slope (S, Wischmeier–Smith)",
        "note": "Simplified ABAG without R, L and C; screening only. Transparent: settlement, forest, no soil data."})
    dst = np.full((h, w), -9999, np.int32)
    with rasterio.open(ctm_path(2024)) as src:
        warp.reproject(rasterio.band(src, 1), dst, dst_transform=T * T.scale(2), dst_crs="EPSG:4326",
                       dst_nodata=-9999, resampling=warp.Resampling.nearest)
    rgba = np.zeros((*dst.shape, 4), np.uint8)
    present = [int(c) for c in np.unique(dst) if c in leg]
    for c in present:
        rgba[dst == c] = [*(int(leg[c][1][i:i + 2], 16) for i in (1, 3, 5)), 255]
    save_layer("crops_2024", rgba, bounds, {"title": "Crop types 2024", "source": "Thünen crop type map 2024 (v202), CC BY 4.0",
                                            "legend": [list(leg[c]) for c in present]})


if __name__ == "__main__":
    main()
