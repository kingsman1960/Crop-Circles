"""HLS 30 m NDVI on and around each demo field: what grows on every parcel this season, and when the field is bare.

The Thünen crop maps end with 2025 and come out about a year late; HLS (Landsat 8/9 + Sentinel-2) runs to last week.
A parcel's green month by month tells winter cereal, sugar beet and the rest apart: croptype.py turns it into a
probability per parcel, tested year by year on 2019–2025 (FIONA declarations, Thünen maps) before it is used for 2026.
The old threshold rule (RULE) is kept as the baseline the model is compared with.

Outputs:
  ndvi_hls.parquet     per field and clear picture: mean NDVI and the share of the field that is bare (NDVI < 0.3);
                       mean GNDVI and NDRE (NDRE from Sentinel-2 pictures only, else NaN)
  hls_series.parquet   per parcel and clear picture: mean NDVI, GNDVI, NDRE
  hls_parcels.parquet  per parcel and year: monthly median NDVI / GNDVI / NDRE, the rule's windows and answer, Thünen
                       crop, FIONA declaration, P(winter cereal / sugar beet / other) and the most likely answer;
                       NDVI in the November–December before and whether a spring crop had a green cover there
  hls_parcels.geojson  outlines with the newest season's status and its probability (EPSG:4326), for the map
  hls_check.json       the model's year-by-year test (and the rule's), per field the check against Thünen and FIONA
                       and the newest season with expected numbers and 90 % ranges
Fields whose HLS download has not arrived yet are skipped.
"""
import json
import re
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio import features, windows
from rasterio.transform import array_bounds
from shapely.geometry import box, mapping, shape

from pipeline import croptype, geo
from pipeline.common import FIELDS, RAW, check, out
from pipeline.croptype import DECLARED_BEET, DECLARED_WINTER, MONTHS
from pipeline.landscape import BEET, zonal_mean

BARE = 0.3                       # NDVI below = bare soil (PRD §7)
WINTER = {1101, 1102, 1103}      # winter wheat, barley, rye: green in March–April
# winter cereals are green by late winter, or by April when sown late after beet; spring barley only from May;
# beet closes its rows in early June (DWD: 8 June) when maize and soy have just come up, and is still green in autumn
# when cereals are harvested and maize, soy and peas ripen (0.45, not higher: the beet lifting starts mid-September)
# before a spring crop the soil has a winter gap: a cover crop is green in November–December, stubble or ploughed land
# is not (bare and green parcels fall apart at 0.4 / 0.6 on the three demo fields)
RULE = {"late_winter_green": 0.45, "april_green": 0.55, "may_low": 0.4, "june_green": 0.5, "autumn_green": 0.45,
        "cover_green": 0.5}
WINDOWS = {"late_winter": ((2, 1), (3, 31)), "april": ((4, 1), (4, 30)), "may": ((5, 1), (5, 31)),
           "june": ((6, 1), (6, 20)), "autumn": ((9, 15), (10, 20))}
COVER = ((11, 1), (12, 31))      # of the year before the crop
SPRING = {1201, 1202, 1300, 1401, 1402, 1502, 1603, 1611, 1613, 1614}  # spring cereals, maize, potato, beet, sunflower,
                                                                       # vegetables, pea, lupin, soy
CLEAR = 0b11110                  # Fmask bits 1-4: cloud, next to cloud or shadow, cloud shadow, snow/ice (HLS v2.0 guide)
MIN_PIXELS, MIN_CLEAR = 4, 0.6   # parcels need 4 pure 30 m pixels; a picture counts when 60 % of them are clear
INDICES = ("ndvi", "gndvi", "ndre")
THUENEN = range(2018, 2026)      # 2018 only for the crop before 2019
UNSURE = 0.6                     # the map shows a parcel's most likely status only when it is at least this likely
# vines, meadows, orchards, lucerne and clover, set-aside: green every spring, outside the arable check
PERMANENT = r"(?i)reb|wiese|weide|obst|luzerne|klee|brache|aus der erzeugung|grünland|gehölz|feldrand|puffer"


def read(path):
    with rasterio.open(path) as src:
        return src.read(1), src.transform, src.crs.to_epsg()


def scenes(fid):
    """NDVI, GNDVI and NDRE of the clear pixels per day on the box grid: ({date: {index: array}}, transform, EPSG).
    GNDVI = (NIR - green) / (NIR + green), B03 on both sensors; NDRE = (NIR - red edge 1) / (NIR + red edge 1), S30 B05
    only (L30 has no red-edge band). An index is all NaN on a day whose extra band has not been downloaded."""
    bands = defaultdict(dict)
    for f in (RAW / "hls_ndvi" / fid).glob("appeears_*/*/*.tif"):
        sensor, band, doy = re.match(r"HLS([LS])30\.020_(\w+?)_doy(\d{7})_", f.name).groups()
        bands[(doy, sensor)][band] = f
    days, T, epsg = {}, None, None
    for (doy, sensor), b in sorted(bands.items()):
        nir_band = "B05" if sensor == "L" else "B8A"
        if not {"B04", nir_band, "Fmask"} <= b.keys():
            continue
        (red, T, epsg), (qa, _, _) = read(b["B04"]), read(b["Fmask"])
        band = lambda k: read(b[k])[0].astype("float32") if k in b else None
        red, nir = red.astype("float32"), band(nir_band)
        ok = (qa != 255) & ((qa & CLEAR) == 0) & (red > 0) & (nir > 0)

        def nd(other):  # normalised difference of NIR and `other` on the clear pixels
            if other is None:
                return np.full(red.shape, np.nan, "float32")
            with np.errstate(divide="ignore", invalid="ignore"):
                return np.where(ok & (other > 0), (nir - other) / (nir + other), np.nan)

        index = {"ndvi": nd(red), "gndvi": nd(band("B03")), "ndre": nd(band("B05") if sensor == "S" else None)}
        best = days.setdefault(datetime.strptime(doy, "%Y%j"), {})
        for k, a in index.items():  # Landsat and Sentinel-2 on the same day: per index the one with more clear pixels
            if k not in best or np.isfinite(a).sum() > np.isfinite(best[k]).sum():
                best[k] = a
    return days, T, epsg


def thuenen(geoms3035, years):
    """Majority Thünen crop code per parcel and year (0 = no map pixel)."""
    xmin, ymin, xmax, ymax = shapely.total_bounds(geoms3035) + np.array([-20, -20, 20, 20])
    codes = {}
    for y in years:
        with rasterio.open(geo.ctm_path(y)) as src:
            win = windows.from_bounds(xmin, ymin, xmax, ymax, src.transform).round_offsets().round_lengths()
            a, T = src.read(1, window=win), src.window_transform(win)
        ids = features.rasterize(zip(geoms3035, range(1, len(geoms3035) + 1)), a.shape, transform=T, fill=0, dtype="int32")
        ok = (ids > 0) & (a > 0)
        maj = pd.DataFrame({"i": ids[ok], "c": a[ok]}).groupby("i").c.agg(lambda s: s.mode().iloc[0])
        codes[y] = maj.reindex(range(1, len(geoms3035) + 1), fill_value=0).values
    return codes


def window_median(series, year, win):
    (m0, d0), (m1, d1) = win
    s = series[(series.date >= pd.Timestamp(year, m0, d0)) & (series.date <= pd.Timestamp(year, m1, d1))]
    return s.groupby("id").ndvi.median()


def classify(df):
    """The threshold rule (baseline for croptype.py) per parcel and year: winter cereal, sugar beet, or something else
    (NaN = too few pictures)."""
    green = (df.late_winter >= RULE["late_winter_green"]) | (df.april >= RULE["april_green"])
    winter = green.where(df[["late_winter", "april"]].notna().any(axis=1))
    beet = ~green & (df.may < RULE["may_low"]) & (df.june >= RULE["june_green"]) & (df.autumn >= RULE["autumn_green"])
    return winter, beet.where(winter.notna() & df[["may", "june", "autumn"]].notna().all(axis=1))


def field(fid, parcels, tree):
    days, T, epsg = scenes(fid)
    if not days:
        return None
    assert epsg == 32632, epsg  # FIONA is ETRS89 / UTM 32N (EPSG:25832): the same grid within a metre
    shp = next(iter(days.values()))["ndvi"].shape
    frame = box(*array_bounds(*shp, T))
    pick = [parcels[i] for i in tree.query(frame, predicate="intersects")]
    cores = [g.buffer(-15) for _, g in pick]  # pixel centres at least half a pixel inside = pure pixels
    ids = features.rasterize(((c, k) for k, c in enumerate(cores, 1) if not c.is_empty), shp, transform=T, fill=0,
                             dtype="int32")
    n = len(pick) + 1
    npx = np.bincount(ids.ravel(), minlength=n)
    own = features.rasterize([geo.reproj(shape(next(f for f in FIELDS if f["id"] == fid)["polygon"]), 4326, 32632)],
                             shp, transform=T, fill=0, dtype="uint8").astype(bool)

    def parcel_mean(a):  # per parcel, NaN unless MIN_CLEAR of its pure pixels are clear for this index
        cnt = np.bincount(ids[np.isfinite(a) & (ids > 0)], minlength=n)
        return np.where((npx >= MIN_PIXELS) & (cnt >= MIN_CLEAR * np.maximum(npx, 1)), zonal_mean(ids, a, n), np.nan)

    def own_mean(a):  # the same on the demo field itself
        v = a[own]
        return float(np.nanmean(v)) if np.isfinite(v).mean() >= MIN_CLEAR else np.nan

    rows, block = [], []
    for day, ix in sorted(days.items()):
        nd = ix["ndvi"]
        mean = {k: parcel_mean(a) for k, a in ix.items()}
        rows += [(pick[k - 1][0], day, *(float(mean[i][k]) for i in INDICES))
                 for k in np.flatnonzero(np.isfinite(mean["ndvi"][1:])) + 1]
        clear = np.isfinite(nd)
        if clear[own].mean() >= MIN_CLEAR:
            v = nd[own & clear]
            block.append((fid, day, float(v.mean()), float((v < BARE).mean()), int(v.size), own_mean(ix["gndvi"]),
                          own_mean(ix["ndre"])))
    series = pd.DataFrame(rows, columns=["id", "date", *INDICES]).assign(field=fid)
    block = pd.DataFrame(block, columns=["field", "date", "ndvi", "bare", "n_pixels", "gndvi", "ndre"]).assign(product="HLS")

    used = sorted(series.id.unique())
    geoms = dict(pick)
    crops = thuenen(geo.reproj(np.array([geoms[i] for i in used], dtype=object), 25832, 3035), THUENEN)
    years = range(2019, max(days).year + 1)
    s = series[series.date.dt.month.isin(MONTHS)]
    monthly = s.groupby(["id", s.date.dt.year.rename("year"), s.date.dt.month.rename("m")])[list(INDICES)].median().unstack("m")
    monthly.columns = [f"{i}_{m:02d}" for i, m in monthly.columns]
    per_year = []
    for y in years:
        f = pd.DataFrame({k: window_median(series, y, w) for k, w in WINDOWS.items()}).reindex(used)
        f["cover"] = window_median(series, y - 1, COVER)
        f["crop"], f["crop_before"] = (crops[x] if x in crops else 0 for x in (y, y - 1))
        per_year.append(f.rename_axis("id").reset_index().assign(year=y))
    py = pd.concat(per_year, ignore_index=True).merge(monthly.reset_index(), on=["id", "year"], how="left")
    py["rule_winter"], py["rule_beet"] = classify(py)
    py["covered"] = (py.cover >= RULE["cover_green"]).where(py.cover.notna() & py.crop.isin(SPRING))
    py["field"] = fid
    py["area_ha"] = py.id.map({i: geoms[i].area / 1e4 for i in used})
    return series, block, py, {i: geoms[i] for i in used}, (min(days), max(days), len(days))


def agreement(py):
    """How often the model said what the Thünen map says (each year predicted without having seen it)."""
    after_beet = py[(py.crop_before == BEET) & py.winter.notna() & (py.crop > 0)]
    lab = py[py.beet.notna() & (py.crop > 0)]
    is_beet, said_beet = lab.crop == BEET, lab.beet.astype(bool)
    return {"after_beet": {"n": len(after_beet),
                           "agree": int((after_beet.winter.astype(bool) == after_beet.crop.isin(WINTER)).sum()),
                           "years": f"{after_beet.year.min()}-{after_beet.year.max()}" if len(after_beet) else ""},
            "beet": {"n_beet": int(is_beet.sum()), "found": int((is_beet & said_beet).sum()),
                     "n_said": int(said_beet.sum()), "right": int((is_beet & said_beet).sum())}}


def declared(fid, fiona22):
    """The crop the farmer declared per parcel (FIONA 2022 object_id) and year: 2022 from the WFS, 2023 on from the
    WMS answers asked at a point inside each 2022 parcel (prep/fetch_fiona_wms.py)."""
    rows = [(i, 2022, name) for i, name in fiona22.items()]
    for p in (RAW / "fiona" / "wms_ab2023").glob(f"{fid}_20*.geojson"):
        rows += [(f["properties"]["query_id"], f["properties"]["Antragsjahr"], f["properties"]["Bezeichnung"])
                 for f in json.loads(p.read_text(encoding="utf-8"))["features"] if f["properties"]["query_id"] is not None]
    return pd.DataFrame(rows, columns=["id", "year", "declared"]).drop_duplicates(["id", "year"])


def check_declared(py):
    """How often the model said what the farmers declared in FIONA (the ground truth the Thünen maps are trained on)."""
    lab = py[py.declared.notna()]
    w = lab[lab.winter.notna() & ~lab.declared.str.contains(PERMANENT)]
    prev = lab.assign(year=lab.year + 1)[["id", "year", "declared"]].rename(columns={"declared": "before"})
    ab = w.merge(prev, on=["id", "year"])
    ab = ab[ab.before.str.contains(DECLARED_BEET)]
    b = lab[lab.beet.notna()]
    is_beet, said = b.declared.str.contains(DECLARED_BEET), b.beet.astype(bool)
    agree = lambda x: int((x.winter.astype(bool) == x.declared.str.contains(DECLARED_WINTER)).sum())
    return {"years": f"{lab.year.min()}-{lab.year.max()}" if len(lab) else "",
            "winter": {"n": len(w), "agree": agree(w)}, "after_beet": {"n": len(ab), "agree": agree(ab)},
            "beet": {"n_beet": int(is_beet.sum()), "found": int((is_beet & said).sum()), "n_said": int(said.sum()),
                     "right": int((is_beet & said).sum())}}


def season(py, geoms, last, sd):
    """The newest season: last year's beet parcels (FIONA where declared, else Thünen) -> winter cereal now (nursery)
    or not; beet this year. Each parcel gets its most likely status and how likely that is ("unknown" below UNSURE);
    nursery and beet also as expected number and 90 % range from the probabilities (sd: croptype.year_sd)."""
    y = last.year
    before = py[py.year == y - 1].set_index("id")
    now = py[py.year == y].set_index("id")
    beet_before = [i for i in geoms if before.group.get(i) == 1]
    status, prob = {}, {}
    for i in geoms:
        r = now.loc[i]
        if i in beet_before:
            s, p = ("nursery", r.p_winter) if r.p_winter >= 0.5 else ("switched", 1 - r.p_winter)
        else:
            s, p = max((("winter", r.p_winter), ("beet_now", r.p_beet), ("other", r.p_other)), key=lambda x: x[1])
        status[i], prob[i] = "unknown" if p < UNSURE else s, (s, round(float(p), 3))
    ha = lambda s: round(sum(geoms[i].area for i, v in status.items() if v == s) / 1e4, 1)
    cnt = lambda s: sum(v == s for v in status.values())
    area = lambda ids: [geoms[i].area / 1e4 for i in ids]
    rest = [i for i in geoms if i not in beet_before]
    summary = {"season": y, "beet_before": {"n": len(beet_before), "ha": round(sum(area(beet_before)), 1)}}
    summary |= {s: {"n": cnt(s), "ha": ha(s)} for s in ("nursery", "switched", "unknown", "beet_now")}
    summary["nursery"] |= croptype.spread(now.p_winter[beet_before], area(beet_before), sd["winter"])
    summary["beet_now"] |= croptype.spread(now.p_beet[rest], area(rest), sd["beet"])
    return status, prob, summary


def main():
    feats22 = [f for p in sorted((RAW / "fiona").glob("fiona_bbox_p*.json"))
               for f in json.loads(p.read_text(encoding="utf-8"))["features"]]
    parcels = [(f["properties"]["object_id"], shape(f["geometry"])) for f in feats22]
    fiona22 = {f["properties"]["object_id"]: f["properties"]["Bezeichnung"] for f in feats22}
    tree = shapely.STRtree([g for _, g in parcels])
    all_series, all_block, all_py, feats, summary = [], [], [], [], {"rule": RULE | {"bare": BARE}, "fields": {}}
    done = {}
    for f in FIELDS:
        res = field(f["id"], parcels, tree)
        if res is None:
            print(f"  {f['id']}: no HLS download yet, skipped")
            continue
        series, block, py, geoms, span = res
        all_series.append(series), all_block.append(block)
        all_py.append(py.merge(declared(f["id"], fiona22), on=["id", "year"], how="left"))
        done[f["id"]] = geoms, span
    if not done:
        return
    # one model for the parcels of all three fields: what one field's parcels teach holds for the others
    pooled, summary["model"] = croptype.run(pd.concat(all_py, ignore_index=True))
    m = summary["model"]
    print(f"  model ({m['indices']}): year by year {m['years']} right {m['right']}/{m['n']} ({m['accuracy']:.0%}, 95 % "
          f"{m['accuracy_95'][0]:.0%}-{m['accuracy_95'][1]:.0%}), mean confidence {m['said']:.0%}, log loss {m['log_loss']}, "
          f"Brier {m['brier']}; the rule {m['rule']['accuracy']:.0%} (in-sample), Brier {m['rule']['brier']}")
    for fid, (geoms, (first, last, n)) in done.items():
        py = pooled[pooled.field == fid]
        status, prob, season_summary = season(py, geoms, last, m["year_sd"])
        check_, fiona = agreement(py), check_declared(py)
        summary["fields"][fid] = {"pictures": n, "first": first.date().isoformat(), "last": last.date().isoformat(),
                                  "parcels": len(geoms), "check": check_, "declared": fiona} | season_summary
        print(f"  {fid}: against FIONA {fiona['years']}: winter cereal or not {fiona['winter']['agree']}/"
              f"{fiona['winter']['n']}, after beet {fiona['after_beet']['agree']}/{fiona['after_beet']['n']}; beet found "
              f"{fiona['beet']['found']}/{fiona['beet']['n_beet']}, right {fiona['beet']['right']}/{fiona['beet']['n_said']}")
        crop_before = py[py.year == last.year - 1].set_index("id").crop
        feats += [{"type": "Feature", "properties": {"id": int(i), "field": fid, "status": status[i],
                                                     "likely": prob[i][0], "p": prob[i][1],
                                                     "crop_before": int(crop_before.get(i, 0)), "ha": round(g.area / 1e4, 2)},
                   "geometry": mapping(shapely.set_precision(geo.reproj(g, 25832, 4326), 1e-6))} for i, g in geoms.items()]
        a, c = check_["after_beet"], py[py.covered.notna()]
        print(f"  {fid}: winter cover before spring crops {int(c.covered.sum())}/{len(c)}, before beet "
              f"{int(c[c.crop == BEET].covered.sum())}/{(c.crop == BEET).sum()}")
        print(f"  {fid}: {n} pictures {first.date()} -> {last.date()}, {len(geoms)} parcels; after beet the model agreed "
              f"with Thünen {a['agree']}/{a['n']} ({a['years']}); beet found {check_['beet']['found']}/{check_['beet']['n_beet']}, "
              f"right {check_['beet']['right']}/{check_['beet']['n_said']}; {last.year}: {season_summary}")
    for name, frames in (("ndvi_hls.parquet", all_block), ("hls_series.parquet", all_series), ("hls_parcels.parquet", [pooled])):
        df = pd.concat(frames, ignore_index=True)
        df.to_parquet(out(name), index=False)
        check(name, df, "date" if "date" in df else None)
    out("hls_parcels.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    out("hls_check.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
