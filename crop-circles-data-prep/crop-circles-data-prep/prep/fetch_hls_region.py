"""Dataset 10b - hls_region: HLS S30 v2.0 canopy indices of every declared sugar-beet parcel in the Kraichgau bbox,
seasons 2023-2025, with its role: next to a planthopper nursery (< 50 m from wheat after beet), control (< 50 m from
other wheat, >= 200 m from any nursery) or other (in between; added 2026-11-15 for the distance-decay fit), in the June and late-summer windows of pipeline/planthopper_edge_effect.py.

No AppEEARS queue: the granules come from the CMR search and the band COGs are read straight from LP DAAC over HTTPS
(Earthdata login from ~/.netrc, cookies in a temp file), only the window that covers the parcels, so nothing but the
parcel statistics lands on disk (the same rules as pipeline/hls.py: pure 30 m pixels, 4 pixels at least, 60 % clear).

  data/raw/hls_region/parcels_<year>.parquet  the parcels: FIONA object_id, role, area, distances, declared crop
  data/raw/hls_region/series_<year>.parquet   per parcel and clear picture: NDVI, GNDVI, NDRE, clear pixels, granule
Re-running skips the granules already in series_<year>.parquet. `--test` reads two granules of 2023 and stops.
"""
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio import features
from rasterio.windows import Window, from_bounds
from shapely.strtree import STRtree

from common import MANIFEST, RAW, http, load_config, manifest_row, now_utc, write_manifest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # the repo root: the pools of planthopper_edge_effect
from pipeline.planthopper_edge_effect import JUNE, LATE, NC_BEET, fiona_pools  # noqa: E402

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
BANDS = {"B04": "red", "B8A": "nir", "B05": "re", "B03": "green", "Fmask": "qa"}
YEARS = (2023, 2024, 2025)
ADJ, FAR, MAX_D = 50, 200, 3000           # m: next to a wheat boundary / clear of any nursery / no neighbour beyond
MAX_CLOUD = 70                            # % cloud in the granule (its own parcels are masked pixel by pixel anyway)
CLEAR, MIN_PIXELS, MIN_CLEAR, CORE = 0b11110, 4, 0.6, 15   # as pipeline/hls.py
OUT = RAW / "hls_region"
COOKIES = os.path.join(tempfile.gettempdir(), "gdal_urs_cookies.txt")
GDAL = dict(GDAL_HTTP_NETRC="YES", GDAL_HTTP_COOKIEFILE=COOKIES, GDAL_HTTP_COOKIEJAR=COOKIES,
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
            GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="5")


def parcels(year, pools, data):
    """Beet parcels of the season with their role and the distance to the nearest nursery / control wheat boundary."""
    beet = data[year][data[year].nc == NC_BEET].reset_index(drop=True)
    g = beet.geom.values

    def nearest(geoms):
        tree = STRtree(shapely.boundary(np.asarray(geoms, dtype=object)))
        d = np.full(len(g), np.inf)
        (pi, _), dist = tree.query_nearest(g, return_distance=True, max_distance=MAX_D)
        d[pi] = dist
        return d

    ds, dc = nearest(pools[year]["source_wheat"]), nearest(pools[year]["control_wheat"])
    role = np.select([ds < ADJ, (dc < ADJ) & (ds >= FAR)], ["nursery_adjacent", "control"], "other")  # other: in between
    c = shapely.centroid(g)
    df = pd.DataFrame({"id": beet.id.values, "year": year, "role": role, "crop": beet.crop.values,
                       "x": shapely.get_x(c), "y": shapely.get_y(c),
                       "area_ha": shapely.area(g) / 1e4, "dist_to_source": ds, "dist_to_control": dc})
    return df, g  # every beet parcel: the decay fit needs the whole distance range


def granules(year, bbox):
    """CMR: HLS S30 granules over the bbox in the two canopy windows, cloud cover <= MAX_CLOUD, oldest first."""
    out = []
    for (m0, d0), (m1, d1) in (JUNE, LATE):
        q = {"short_name": "HLSS30", "version": "2.0", "page_size": 500,
             "bounding_box": f"{bbox['min_lon']},{bbox['min_lat']},{bbox['max_lon']},{bbox['max_lat']}",
             "temporal": f"{year}-{m0:02d}-{d0:02d}T00:00:00Z,{year}-{m1:02d}-{d1:02d}T23:59:59Z"}
        for e in http("GET", CMR, params=q, pause=0.5).json()["feed"]["entry"]:
            if float(e.get("cloud_cover", 100)) > MAX_CLOUD:
                continue
            urls = {b: next(l["href"] for l in e["links"] if l["href"].endswith(f".{b}.tif") and l["href"].startswith("https"))
                    for b in BANDS}
            out.append({"granule": e["title"], "tile": e["title"].split(".")[2], "cloud": float(e.get("cloud_cover", -1)),
                        "date": datetime.strptime(e["title"].split(".")[3][:7], "%Y%j"), "urls": urls})
    return sorted(out, key=lambda x: (x["date"], x["tile"]))


class TileGrid:
    """The parcels burnt once onto one tile's grid (ids per pixel, pixels per parcel), for the window that covers them."""

    def __init__(self, src, geoms):
        x0, y0, x1, y1 = shapely.total_bounds(geoms)
        b = src.bounds
        w = from_bounds(max(x0, b.left) - 60, max(y0, b.bottom) - 60, min(x1, b.right) + 60, min(y1, b.top) + 60, src.transform)
        c0, r0 = max(int(w.col_off), 0), max(int(w.row_off), 0)
        c1, r1 = min(int(np.ceil(w.col_off + w.width)) + 1, src.width), min(int(np.ceil(w.row_off + w.height)) + 1, src.height)
        self.window = Window(c0, r0, c1 - c0, r1 - r0)  # inside the tile: the read must return exactly this shape
        self.transform = src.window_transform(self.window)
        shape = (self.window.height, self.window.width)
        cores = shapely.buffer(geoms, -CORE)
        self.ids = features.rasterize(((c, k) for k, c in enumerate(cores, 1) if not c.is_empty), shape,
                                      transform=self.transform, fill=0, dtype="int32")
        self.n = len(geoms) + 1
        self.npx = np.bincount(self.ids.ravel(), minlength=self.n)


def parcel_means(grid, bands):
    """Mean NDVI / GNDVI / NDRE per parcel on the clear pixels; NaN unless MIN_CLEAR of its pure pixels are clear."""
    qa, red, nir = bands["qa"], bands["red"].astype("float32"), bands["nir"].astype("float32")
    ok = (qa != 255) & ((qa & CLEAR) == 0) & (red > 0) & (nir > 0)
    out = {}
    for name, other in (("ndvi", red), ("gndvi", bands["green"].astype("float32")), ("ndre", bands["re"].astype("float32"))):
        good = ok & (other > 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            v = np.where(good, (nir - other) / (nir + other), np.nan)
        cnt = np.bincount(grid.ids[good & (grid.ids > 0)], minlength=grid.n)
        s = np.bincount(grid.ids[good & (grid.ids > 0)], v[good & (grid.ids > 0)], minlength=grid.n)
        mean = np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)
        out[name] = np.where((grid.npx >= MIN_PIXELS) & (cnt >= MIN_CLEAR * np.maximum(grid.npx, 1)), mean, np.nan)
        out[f"n_{name}"] = cnt
    return out


def read_granule(g, grids, geoms, ids):
    """One granule: the five bands in the parcels' window, parcel means -> rows."""
    bands = {}
    with rasterio.Env(**GDAL):
        for band, key in BANDS.items():
            with rasterio.open(g["urls"][band]) as src:
                if g["tile"] not in grids:
                    grids[g["tile"]] = TileGrid(src, geoms)
                bands[key] = src.read(1, window=grids[g["tile"]].window)
    grid = grids[g["tile"]]
    m = parcel_means(grid, bands)
    k = np.flatnonzero(np.isfinite(m["ndvi"][1:])) + 1
    return pd.DataFrame({"id": ids[k - 1], "date": g["date"], "tile": g["tile"], "granule": g["granule"],
                         "ndvi": m["ndvi"][k], "gndvi": m["gndvi"][k], "ndre": m["ndre"][k], "n_pixels": m["n_ndvi"][k]})


def main():
    test = "--test" in sys.argv
    cfg = load_config()
    OUT.mkdir(parents=True, exist_ok=True)
    pools, data = fiona_pools(YEARS)
    for year in YEARS[:1] if test else YEARS:
        df, geoms = parcels(year, pools, data)
        df.to_parquet(OUT / f"parcels_{year}.parquet", index=False)
        print(f"{year}: {len(df)} beet parcels, {dict(df.role.value_counts())}")
        path = OUT / f"series_{year}.parquet"
        done = pd.read_parquet(path) if path.exists() else pd.DataFrame()
        seen = set(done.granule) if len(done) else set()
        todo = [g for g in granules(year, cfg["bbox"]) if g["granule"] not in seen]
        print(f"  {len(todo)} granules to read ({len(seen)} already in {path.name})")
        grids, frames, t0 = {}, [done] if len(done) else [], time.time()
        for i, g in enumerate(todo[:2] if test else todo, 1):
            t = time.time()
            rows = read_granule(g, grids, geoms, df.id.values)
            frames.append(rows)
            print(f"  {i}/{len(todo)} {g['granule']} cloud {g['cloud']:.0f} %: {len(rows)} parcels, {time.time() - t:.0f} s")
            if i % 10 == 0 or i == len(todo) or test:
                pd.concat(frames, ignore_index=True).to_parquet(path, index=False)  # resume point
            time.sleep(0.5)
        series = pd.concat(frames, ignore_index=True) if frames else done
        series.to_parquet(path, index=False)
        print(f"  series_{year}: {len(series)} rows, {series.granule.nunique()} granules, {series.id.nunique()} parcels, "
              f"{(time.time() - t0) / 60:.0f} min")
        if not test:
            write_manifest([manifest_row(p, "hls_region", source="NASA LP DAAC HLSS30 v2.0 COGs over HTTPS (CMR search)",
                                         product_version="HLSS30.020 B04 B8A B05 B03 Fmask", query_or_url=CMR,
                                         spatial="bbox, beet parcels next to nursery or control wheat (FIONA)",
                                         temporal=f"{year} Jun 1-25, Aug 15-Sep 10", downloaded_at_utc=now_utc(),
                                         license="NASA open data (no restrictions)",
                                         attribution="Masek, J., et al. HLS Operational Land Surface Reflectance and TOA "
                                                     "Brightness Daily Global 30m v2.0 (HLSS30). NASA LP DAAC")
                            for p in (OUT / f"parcels_{year}.parquet", path)])


if __name__ == "__main__":
    main()
