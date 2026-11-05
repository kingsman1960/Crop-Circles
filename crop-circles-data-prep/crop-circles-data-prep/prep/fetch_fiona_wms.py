"""Dataset 12b - fiona_wms: declared crops 2023-2025 of the parcels around each demo field (FIONA ab 2023, WMS).

The bulk WFS for 2023 on (WFS_LW-BW_FIONA_Flaecheninformation_ab2023, as listed in the Geoportal BW metadata) answers
404 on 2026-11-05, and the 2022 WFS does not serve the newer layers. The WMS of the same open data answers
GetFeatureInfo with the parcel's polygon and attributes, so: one query per FIONA 2022 parcel in the HLS box of each
field (at a point inside it) and year - like clicking each parcel once. Parcels that no such point hits (split or
redrawn since 2022) are found by asking a point in every uncovered piece of the demo block.
Output per field and year: the answers as GeoJSON in EPSG:25832, each feature with `query_id` = the FIONA 2022
object_id it was asked for (None for the gap queries). Files already on disk are kept; only the gaps are re-asked.
"""
import json

import numpy as np
import rasterio
import shapely
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import unary_union

from common import RAW, http, load_config, log, now_utc

WMS = "https://owsproxy.lgl-bw.de/owsproxy/ows/WMS_LW-BW_FIONA_Flaecheninformation_ab2023"
YEARS = (2023, 2024, 2025)
OUT = RAW / "fiona" / "wms_ab2023"
HALF = 5          # m: the query window is 10 m around the point, 11 x 11 pixels, asked at the centre pixel
MIN_GAP = 2000    # m²: smaller uncovered pieces are field margins, not parcels
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True).transform


def hls_box(fid):
    tif = next((RAW / "hls_ndvi" / fid).glob("appeears_*/*/*_Fmask_*.tif"))
    with rasterio.open(tif) as src:
        return box(*src.bounds)  # EPSG:32632, the same grid as EPSG:25832 within a metre


def ask(layer, pt, query_id):
    q = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetFeatureInfo", "LAYERS": layer, "QUERY_LAYERS": layer,
         "STYLES": "", "FORMAT": "image/png", "CRS": "EPSG:25832", "WIDTH": 11, "HEIGHT": 11, "I": 5, "J": 5,
         "BBOX": f"{pt.x - HALF},{pt.y - HALF},{pt.x + HALF},{pt.y + HALF}", "INFO_FORMAT": "application/json"}
    feats = http("GET", WMS, params=q, pause=0.5, timeout=60).json()["features"]
    for f in feats:
        f["properties"]["query_id"] = query_id
    return feats


def fill_gaps(block, feats, layer, rounds=3):
    """Ask a point in every uncovered piece of the block (a road or a yard answers nothing and is not asked again)."""
    tried = []
    for _ in range(rounds):
        rest = block.difference(unary_union([shape(f["geometry"]) for f in feats]))
        pts = [g.representative_point() for g in shapely.get_parts(rest)
               if g.geom_type == "Polygon" and g.area >= MIN_GAP and not any(g.contains(t) for t in tried)]
        if not pts:
            break
        for pt in pts:
            tried.append(pt)
            feats += ask(layer, pt, None)
    return feats, len(tried)


def main():
    blocks = {f["id"]: shapely.transform(shape(f["polygon"]), lambda xy: np.column_stack(TO_UTM(*xy.T)))
              for f in load_config()["fields"]}
    parcels = [(f["properties"]["object_id"], shape(f["geometry"]))
               for p in sorted((RAW / "fiona").glob("fiona_bbox_p*.json"))
               for f in json.loads(p.read_text(encoding="utf-8"))["features"]]
    OUT.mkdir(parents=True, exist_ok=True)
    for fid, block in blocks.items():
        frame = hls_box(fid)
        points = [(i, g.representative_point()) for i, g in parcels if g.intersects(frame)]
        for y in YEARS:
            path, layer, when = OUT / f"{fid}_{y}.geojson", f"lw:v_fiona_flaecheninformation_{y}", now_utc()
            feats = (json.loads(path.read_text(encoding="utf-8"))["features"] if path.exists()
                     else [f for i, pt in points for f in ask(layer, pt, i)])
            feats, n_gaps = fill_gaps(block, feats, layer)
            path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False),
                            encoding="utf-8")
            print(f"  {path.name}: {len(points)} points + {n_gaps} gap points, {len({f['id'] for f in feats})} parcels")
            log(path, "fiona_wms", source="LGL BW WMS FIONA Flaecheninformation ab 2023 (MLR), GetFeatureInfo",
                product_version=f"Antragsjahr {y}",
                query_or_url=f"{WMS} GetFeatureInfo {layer}, one point inside each FIONA 2022 parcel + uncovered pieces",
                spatial=f"HLS box of {fid}, EPSG:25832 {tuple(round(v) for v in frame.bounds)}", temporal=str(y),
                downloaded_at_utc=when, license="dl-de/by-2-0",
                attribution="Datengrundlage: MLR (2026), Datenlizenz Deutschland - Namensnennung - Version 2.0, "
                            "https://mlr.baden-wuerttemberg.de")


if __name__ == "__main__":
    main()
