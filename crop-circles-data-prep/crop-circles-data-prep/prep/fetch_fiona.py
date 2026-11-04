"""Dataset 12 - fiona: BW agricultural parcels with declared crop (FIONA / InVeKoS, Antragsjahr 2022), WFS, whole study bbox.

Requested in EPSG:25832 (the GeoJSON output in EPSG:4326 is rounded to 4 decimals, ~10 m). Paged, sorted by object_id.
"""
from collections import Counter

from pyproj import Transformer

from common import RAW, http, load_config, log, now_utc
from fetch_fields import inside

WFS = "https://owsproxy.lgl-bw.de/owsproxy/wfs/WFS_LW-BW_FIONA_Flaecheninformation"
LAYER = "lw:v_fiona_flaecheninformation"
PAGE = 20000
OUT = RAW / "fiona"
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)


def first_vertex(geom):
    c = geom["coordinates"]
    while isinstance(c[0], list):
        c = c[0]
    return c


def main():
    cfg = load_config()
    b = cfg["bbox"]
    x0, y0, x1, y1 = TO_UTM.transform_bounds(b["min_lon"], b["min_lat"], b["max_lon"], b["max_lat"])
    base = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": LAYER,
            "SRSNAME": "EPSG:25832", "BBOX": f"{x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f},EPSG:25832"}
    hits = http("GET", WFS, params={**base, "RESULTTYPE": "hits"}).text
    matched = int(hits.split('numberMatched="')[1].split('"')[0])
    print(f"FIONA parcels in bbox: {matched}")
    OUT.mkdir(parents=True, exist_ok=True)
    feats = []
    for i, start in enumerate(range(0, matched, PAGE)):
        when = now_utc()
        r = http("GET", WFS, params={**base, "COUNT": PAGE, "STARTINDEX": start, "SORTBY": "object_id",
                                     "OUTPUTFORMAT": "application/json"}, timeout=600, pause=5)
        path = OUT / f"fiona_bbox_p{i:02d}.json"
        path.write_bytes(r.content)
        page = r.json()["features"]
        feats += page
        print(f"  {path.name}: {len(page)} features")
        log(path, "fiona", source="LGL BW WFS FIONA Flaecheninformation (MLR)", product_version="Antragsjahr 2022",
            query_or_url=r.url, spatial=f"bbox EPSG:25832 {base['BBOX']}", temporal="2022", downloaded_at_utc=when,
            license="dl-de/by-2-0",
            attribution="Datengrundlage: MLR (2026), Datenlizenz Deutschland - Namensnennung - Version 2.0, "
                        "https://mlr.baden-wuerttemberg.de")

    ids = [f["properties"]["object_id"] for f in feats]
    print(f"\nfeatures {len(feats)} (matched {matched}), unique object_id {len(set(ids))}, "
          f"Antragsjahr {dict(Counter(f['properties']['Antragsjahr'] for f in feats))}")
    print("top crops (parcel count):", Counter(f["properties"]["Bezeichnung"] for f in feats).most_common(12))
    # parcels whose first vertex lies inside each demo field (OSM polygon)
    for fld in cfg["fields"]:
        g = fld["polygon"]
        rings = [g["coordinates"][0]] if g["type"] == "Polygon" else [p[0] for p in g["coordinates"]]
        utm = [[TO_UTM.transform(*p) for p in r] for r in rings]
        hit = [f for f in feats if any(inside(first_vertex(f["geometry"]), r) for r in utm)]
        print(f"{fld['id']}: {len(hit)} parcels inside the OSM polygon: "
              f"{dict(Counter(f['properties']['Bezeichnung'] for f in hit))}")


if __name__ == "__main__":
    main()
