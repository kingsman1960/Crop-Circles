"""Dataset 7 - dem: NASADEM 30 m elevation clipped to the study bbox (--bw: all of BW) (AppEEARS area request, GeoTIFF, geographic).

Re-running resumes the submitted task (data/raw/dem/appeears_task[_bw].json); delete that file to resubmit.
"""
import shutil

import rasterio

from common import (RAW, appeears_download, appeears_login, appeears_logout, appeears_task, appeears_wait, area, load_config,
                    log, now_utc)

OUT = RAW / "dem"


def main():
    cfg = load_config()
    b, tag = area(cfg)
    sfx = "" if tag == "bbox" else f"_{tag}"  # the bbox files keep their first names
    ring = [[b["min_lon"], b["min_lat"]], [b["max_lon"], b["min_lat"]], [b["max_lon"], b["max_lat"]],
            [b["min_lon"], b["max_lat"]], [b["min_lon"], b["min_lat"]]]
    task = {"task_type": "area", "task_name": f"crop-circles-dem{sfx}",
            "params": {"dates": [{"startDate": "02-11-2000", "endDate": "02-21-2000"}],
                       "layers": [{"product": "NASADEM_NC.001", "layer": "NASADEM_HGT"}],
                       "geo": {"type": "FeatureCollection", "features": [
                           {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}]},
                       "output": {"format": {"type": "geotiff"}, "projection": "geographic"}}}
    token = appeears_login()
    try:
        task_id = appeears_task(token, task, OUT / f"appeears_task{sfx}.json")
        print(f"AppEEARS task {task_id}")
        appeears_wait(token, task_id, every=30)
        when = now_utc()
        files = appeears_download(token, task_id, OUT / f"appeears{sfx}")
    finally:
        appeears_logout(token)

    for path, url in files:
        log(path, "dem", source="NASA AppEEARS area subset (LP DAAC)", product_version="NASADEM_NC.001",
            query_or_url=f"{url} (task {task_id})", spatial=f"{tag} {b['min_lon']},{b['min_lat']},{b['max_lon']},{b['max_lat']}",
            temporal="2000-02-11 -> 2000-02-21 (SRTM mission)", downloaded_at_utc=when,
            license="NASA open data (no restrictions)",
            attribution="NASA JPL (2020). NASADEM Merged DEM Global 1 arc second V001. NASA LP DAAC, retrieved via AppEEARS")

    tif = next(p for p, _ in files if p.suffix == ".tif")
    shutil.copyfile(tif, OUT / f"dem_{tag}.tif")  # stable name for later steps; identical bytes
    with rasterio.open(OUT / f"dem_{tag}.tif") as src:
        a = src.read(1, masked=True)
        bb = src.bounds
        covered = bb.left <= b["min_lon"] and bb.bottom <= b["min_lat"] and bb.right >= b["max_lon"] and bb.top >= b["max_lat"]
        print(f"dem_{tag}.tif <- {tif.name}\n  CRS {src.crs}, res {src.res[0] * 3600:.3f}\" x {src.res[1] * 3600:.3f}\", "
              f"size {src.width}x{src.height}, nodata {src.nodata}, dtype {src.dtypes[0]}")
        print(f"  bounds {tuple(round(v, 5) for v in bb)}, bbox fully covered: {covered}")
        print(f"  nodata pixels {int(a.mask.sum())}, elevation {a.min()} -> {a.max()} m")


if __name__ == "__main__":
    main()
