"""Dataset 17 - dlr_croptypes: DLR CropTypes v2.1 (Sentinel-1 + Sentinel-2, 10 m, Germany, 2017-2025), study bbox
(--bw: all of Baden-Württemberg).

A second crop type map, made independently of the Thünen maps (other method, other training), to check the regional
nursery numbers. Each year is one Cloud Optimized GeoTIFF of all Germany (~460 MB); only the bbox window is read over
HTTP range requests and saved, like the Thünen bbox files. Legend and class accuracies are kept next to them.
"""
import rasterio
from pyproj import Transformer
from rasterio import windows

from common import MANIFEST, RAW, ROOT, area, http, load_config, log, now_utc

BASE = "https://download.geoservice.dlr.de/CROPTYPES/files"
YEARS = range(2017, 2026)
OUT = RAW / "dlr_croptypes"
META = dict(source="DLR EOC Geoservice, CropTypes v2.1 (CROPTYPES_DE_P1Y)", license="CC-BY-4.0",
            attribution="DLR CropTypes v2.1 – Gessner et al. 2025, IEEE GRSL 22, 2504805; Asam et al. 2022, "
                        "Remote Sens. 14, 2981")


def main():
    b, tag = area(load_config())
    bounds = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True).transform_bounds(
        b["min_lon"], b["min_lat"], b["max_lon"], b["max_lat"])
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("LEGEND_CropTypes_v21.txt", "ACCURACIES_CropTypes_Germany.txt", "README_CropTypes_v21.txt"):
        when, path = now_utc(), OUT / name
        r = http("GET", f"{BASE}/{name}")
        path.write_bytes(r.content)
        log(path, "dlr_croptypes", product_version="v2.1", query_or_url=r.url, spatial="Germany", temporal="2017-2025",
            downloaded_at_utc=when, **META)
    logged = MANIFEST.read_text(encoding="utf-8")  # a re-run keeps the years already logged
    for y in YEARS:
        when, url, path = now_utc(), f"{BASE}/CROPTYPES_DE_P1Y_{y}_V021/CROPTYPES_DE_P1Y_{y}_V021.tif", \
            OUT / f"CROPTYPES_DE_P1Y_{y}_V021_{tag}.tif"
        if path.relative_to(ROOT).as_posix() + "," in logged:
            continue
        for attempt in range(3):  # BW window: a range read sometimes comes back short ("TIFFFillTile: Read error")
            try:
                with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="5",
                                  GDAL_HTTP_RETRY_DELAY="5"), rasterio.open("/vsicurl/" + url) as src:
                    win = windows.from_bounds(*bounds, src.transform).round_offsets().round_lengths()
                    a = src.read(1, window=win)
                    prof = {"driver": "GTiff", "dtype": a.dtype, "count": 1, "width": a.shape[1], "height": a.shape[0],
                            "crs": src.crs, "transform": src.window_transform(win), "nodata": src.nodata,
                            "compress": "deflate", "tiled": True}
                break
            except rasterio.errors.RasterioIOError as e:
                if attempt == 2:
                    raise
                print(f"  {y}: {e}; retrying")
        with rasterio.open(path, "w", **prof) as dst:
            dst.write(a, 1)
        print(f"  {path.name}: {a.shape[1]} x {a.shape[0]} px")
        log(path, "dlr_croptypes", product_version="v2.1", query_or_url=f"{url} (HTTP range read of the bbox window)",
            spatial=f"{tag} EPSG:32632 {tuple(round(v) for v in bounds)}", temporal=str(y), downloaded_at_utc=when, **META)


if __name__ == "__main__":
    main()
