"""Dataset 14 - thuenen_ctm: Thünen national crop type maps for Germany (10 m raster COGs on Zenodo), clipped to the bbox.

The COGs are read over HTTP range requests (only the bbox window is transferred) and written as GeoTIFF unchanged
(same CRS EPSG:3035, grid, dtype and values). v202 = Blickensdörfer et al. 2022 method (2017-2024, one legend);
v302 = Pham et al. 2024 method (2024, 2025 preliminary "2025_08"), its own legend.
"""
from collections import Counter

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

from common import RAW, http, load_config, log, now_utc

Z = "https://zenodo.org/records/{}/files/{}"
COGS = [("10640528", f"CTM_GER_{y}_rst_v202_COG.tif") for y in range(2017, 2022)] + [
    ("10645427", "CTM_GER_2022_rst_v202_COG.tif"), ("15309479", "CTM_GER_2023_rst_v202_COG.tif"),
    ("17122646", "CTM_GER_2024_rst_v202_COG.tif"),
    ("17197830", "CTM_GER_2024_rst_v302_COG.tif"), ("17197871", "CTM_GER_2025_rst_v302_2025_08_COG.tif")]
DOCS = [("10640528", "CTM_GER_LegendEN_rst_v202.clr"), ("10640528", "CTM_GER_LegendDE_rst_v202.clr"),
        ("10640528", "CTM_GER_2017-21_raster_accuracy_v202.pdf"), ("15309479", "CTM_GER_2023_rst_acc_v202.pdf"),
        ("17197830", "CTM_GER_LegendEN_rst_v302.clr"), ("17197830", "CTM_GER_LegendDE_rst_v302.clr"),
        ("17197830", "CTM_GER_2024_raster_accuracy_v302.pdf")]
OUT = RAW / "thuenen_ctm"
META = dict(source="Thünen Institute crop type maps for Germany (Zenodo)", license="CC BY 4.0",
            attribution="Blickensdörfer, L., et al. (2022) Remote Sensing of Environment 269, 112831; "
                        "Thünen Institute, crop type maps for Germany (Zenodo), CC BY 4.0")


def main():
    cfg = load_config()
    b = cfg["bbox"]
    OUT.mkdir(parents=True, exist_ok=True)
    for rid, key in DOCS:
        when, url = now_utc(), Z.format(rid, key)
        path = OUT / key
        path.write_bytes(http("GET", url).content)
        log(path, "thuenen_ctm", query_or_url=url, spatial="Germany", temporal="-", downloaded_at_utc=when,
            product_version=key.split("_")[-1].split(".")[0], **META)

    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="5"):
        for rid, key in COGS:
            when, url = now_utc(), Z.format(rid, key)
            with rasterio.open("/vsicurl/" + url) as src:
                win = from_bounds(*transform_bounds("EPSG:4326", src.crs, b["min_lon"], b["min_lat"], b["max_lon"],
                                                    b["max_lat"]), src.transform).round_offsets().round_lengths()
                data = src.read(1, window=win)
                prof = src.profile | {"width": win.width, "height": win.height,
                                      "transform": src.window_transform(win), "compress": "deflate",
                                      "tiled": True, "blockxsize": 256, "blockysize": 256}
            path = OUT / key.replace("_COG.tif", "_bbox.tif").replace("_COG_", "_")
            with rasterio.open(path, "w", **prof) as dst:
                dst.write(data, 1)
            log(path, "thuenen_ctm", query_or_url=f"{url} (window {win.col_off},{win.row_off},{win.width}x{win.height})",
                spatial=f"bbox {b['min_lon']},{b['min_lat']},{b['max_lon']},{b['max_lat']} (EPSG:3035 window)",
                temporal=key.split("_")[2], downloaded_at_utc=when, product_version=key.split("_")[4], **META)
            vals = Counter(dict(zip(*np.unique(data, return_counts=True))))
            nod = vals.pop(prof["nodata"], 0)
            print(f"{path.name}: {prof['crs']} {prof['transform'].a:.0f} m, {win.width}x{win.height}, "
                  f"nodata {nod / data.size:.1%}, {len(vals)} classes, top {[(int(k), int(v)) for k, v in vals.most_common(6)]}")


if __name__ == "__main__":
    main()
