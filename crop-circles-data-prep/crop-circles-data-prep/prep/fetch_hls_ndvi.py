"""Dataset 10 - hls_ndvi: HLS v2.0 red/NIR + Fmask around each field (AppEEARS area request per field, GeoTIFF, native UTM).

L30: B04 red, B05 NIR; S30: B04 red, B8A NIR narrow (HLS v2.0 user guide). Box = field bbox, at least 1 km per side, + 60 m.
One task per field and date chunk: one task for all three fields would cover the whole 25 km extent, and AppEEARS
refuses a single 2019 -> now task per field (too many output files). Re-running resumes the tasks;
`--submit-only` submits and exits.
"""
import math
import sys
from collections import Counter
from datetime import date

import rasterio

from common import RAW, appeears_download, appeears_login, appeears_logout, appeears_task, appeears_wait, load_config, log, now_utc

LAYERS = {"HLSL30.020": ["B04", "B05", "Fmask"], "HLSS30.020": ["B04", "B8A", "Fmask"]}
START = "2019-01-01"
CHUNKS = [("2019-01-01", "2021-12-31"), ("2022-01-01", "2023-12-31"), ("2024-01-01", None)]  # None = today
MIN_SIDE_M, MARGIN_M = 1000, 60
OUT = RAW / "hls_ndvi"


def box(polygon):
    rings = [polygon["coordinates"][0]] if polygon["type"] == "Polygon" else [p[0] for p in polygon["coordinates"]]
    xs, ys = [p[0] for r in rings for p in r], [p[1] for r in rings for p in r]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    my, mx = 111320, 111320 * math.cos(math.radians(cy))  # metres per degree
    hx = max(MIN_SIDE_M / 2, (max(xs) - min(xs)) * mx / 2 + MARGIN_M) / mx
    hy = max(MIN_SIDE_M / 2, (max(ys) - min(ys)) * my / 2 + MARGIN_M) / my
    return [[cx - hx, cy - hy], [cx + hx, cy - hy], [cx + hx, cy + hy], [cx - hx, cy + hy], [cx - hx, cy - hy]]


def main():
    cfg = load_config()
    token = appeears_login()
    try:
        tasks = {}
        for f, (d0, c1) in ((f, c) for f in cfg["fields"] for c in CHUNKS):
            ring = box(f["polygon"])
            d1 = c1 or date.today().isoformat()
            label = f"{d0[:4]}-{c1[:4] if c1 else 'now'}"  # stable across days, so re-runs find the task
            mdy = lambda d: f"{d[5:7]}-{d[8:10]}-{d[:4]}"
            task = {"task_type": "area", "task_name": f"crop-circles-hls-{f['id']}-{d0[:4]}",
                    "params": {"dates": [{"startDate": mdy(d0), "endDate": mdy(d1)}],
                               "layers": [{"product": p, "layer": l} for p, ls in LAYERS.items() for l in ls],
                               "geo": {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
                                       "geometry": {"type": "Polygon", "coordinates": [ring]}}]},
                               "output": {"format": {"type": "geotiff"}, "projection": "native"}}}
            key = (f["id"], d0, d1, label)
            tasks[key] = (appeears_task(token, task, OUT / f["id"] / f"appeears_task_{label}.json"), ring)
            print(f"{f['id']} {d0} -> {d1}: AppEEARS task {tasks[key][0]}")
        if "--submit-only" in sys.argv:
            return
        files_by_field = {}
        for (fid, d0, d1, label), (task_id, ring) in tasks.items():
            appeears_wait(token, task_id)
            when = now_utc()
            files = appeears_download(token, task_id, OUT / fid / f"appeears_{label}")
            files_by_field.setdefault(fid, []).extend(files)
            for path, url in files:
                log(path, "hls_ndvi", source="NASA AppEEARS area subset (LP DAAC)", product_version=", ".join(LAYERS),
                    query_or_url=f"{url} (task {task_id})", spatial=f"{fid} box {ring[0]} - {ring[2]}",
                    temporal=f"{d0} -> {d1}", downloaded_at_utc=when, license="NASA open data (no restrictions)",
                    attribution="Masek, J., et al. HLS Operational Land Surface Reflectance and TOA Brightness Daily "
                                "Global 30m v2.0 (HLSL30/HLSS30). NASA LP DAAC, retrieved via AppEEARS")
        for fid, files in files_by_field.items():
            tifs = [p for p, _ in files if p.suffix == ".tif"]
            print(f"\n{fid}: {len(files)} files, {len(tifs)} GeoTIFF, {sum(p.stat().st_size for p, _ in files) / 1e6:.1f} MB")
            # AppEEARS names: <product>.<version>_<layer>_doy<YYYYDDD>..._aid0001.tif (cf. the NASADEM output)
            for prod, layers in LAYERS.items():
                for layer in layers:
                    ds = sorted(p.name.split("_doy")[1][:7] for p in tifs if p.name.startswith(f"{prod.split('.')[0]}.") and f"_{layer}_doy" in p.name)
                    years = Counter(d[:4] for d in ds)
                    print(f"  {prod} {layer}: {len(ds)} scenes, {ds[0] if ds else '-'} -> {ds[-1] if ds else '-'}, per year {dict(sorted(years.items()))}")
            if tifs:
                with rasterio.open(tifs[0]) as src:
                    print(f"  sample {tifs[0].name}: CRS {src.crs}, res {src.res}, size {src.width}x{src.height}, nodata {src.nodata}")
    finally:
        appeears_logout(token)


if __name__ == "__main__":
    main()
