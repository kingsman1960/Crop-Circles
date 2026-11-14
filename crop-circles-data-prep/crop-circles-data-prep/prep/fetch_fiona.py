"""Dataset 12 - fiona: BW agricultural parcels with declared crop (FIONA / InVeKoS, Antragsjahr 2022), WFS, whole study bbox
(--bw: all of Baden-Württemberg, ~1.3 million parcels).

Requested in EPSG:25832 (the GeoJSON output in EPSG:4326 is rounded to 4 decimals, ~10 m). Paged, sorted by object_id.
A year argument (`fetch_fiona.py 2024`) reads Antragsjahr 2023 on from the `_ab2023` WFS (404 on 2026-11-05, answers
again on 2026-11-14) into `fiona_<tag>_<year>_p*.json`; 2022 keeps its file names.
"""
import json
import sys
from collections import Counter

from pyproj import Transformer

from common import MANIFEST, RAW, ROOT, area, http, load_config, log, now_utc
from fetch_fields import inside

YEAR = next((int(a) for a in sys.argv[1:] if a.isdigit()), 2022)
WFS = "https://owsproxy.lgl-bw.de/owsproxy/wfs/WFS_LW-BW_FIONA_Flaecheninformation" + ("" if YEAR == 2022 else "_ab2023")
LAYER = "lw:v_fiona_flaecheninformation" + ("" if YEAR == 2022 else f"_{YEAR}")
NAME = "" if YEAR == 2022 else f"_{YEAR}"  # in the file names
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
    b, tag = area(cfg)
    x0, y0, x1, y1 = TO_UTM.transform_bounds(b["min_lon"], b["min_lat"], b["max_lon"], b["max_lat"])
    base = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": LAYER,
            "SRSNAME": "EPSG:25832", "BBOX": f"{x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f},EPSG:25832"}
    hits = http("GET", WFS, params={**base, "RESULTTYPE": "hits"}).text
    matched = int(hits.split('numberMatched="')[1].split('"')[0])
    print(f"FIONA {YEAR} parcels in {tag}: {matched}")
    OUT.mkdir(parents=True, exist_ok=True)
    # parcels whose first vertex lies inside each demo field (OSM polygon); pages are checked and dropped (BW: ~1 GB)
    demo = {}
    for fld in cfg["fields"]:
        g = fld["polygon"]
        rings = [g["coordinates"][0]] if g["type"] == "Polygon" else [p[0] for p in g["coordinates"]]
        demo[fld["id"]] = ([[TO_UTM.transform(*p) for p in r] for r in rings], Counter())
    ids, years, crops = set(), Counter(), Counter()
    logged = MANIFEST.read_text(encoding="utf-8")  # a re-run keeps the pages already logged (same sort order)
    for i, start in enumerate(range(0, matched, PAGE)):
        path = OUT / f"fiona_{tag}{NAME}_p{i:02d}.json"
        if path.relative_to(ROOT).as_posix() + "," in logged:
            page = json.loads(path.read_bytes())["features"]
            print(f"  {path.name}: {len(page)} features (kept)")
        else:
            when = now_utc()
            r = http("GET", WFS, params={**base, "COUNT": PAGE, "STARTINDEX": start, "SORTBY": "object_id",
                                         "OUTPUTFORMAT": "application/json"}, timeout=600, pause=5)
            path.write_bytes(r.content)
            page = r.json()["features"]
            print(f"  {path.name}: {len(page)} features")
            log(path, "fiona", source="LGL BW WFS FIONA Flaecheninformation (MLR)", product_version=f"Antragsjahr {YEAR}",
                query_or_url=r.url, spatial=f"{tag} EPSG:25832 {base['BBOX']}", temporal=str(YEAR), downloaded_at_utc=when,
                license="dl-de/by-2-0",
                attribution="Datengrundlage: MLR (2026), Datenlizenz Deutschland - Namensnennung - Version 2.0, "
                            "https://mlr.baden-wuerttemberg.de")
        for f in page:
            pr = f["properties"]
            ids.add(pr["object_id"])
            years[pr["Antragsjahr"]] += 1
            crops[pr["Bezeichnung"]] += 1
            for utm, hit in demo.values():
                if any(inside(first_vertex(f["geometry"]), r_) for r_ in utm):
                    hit[pr["Bezeichnung"]] += 1

    print(f"\nfeatures {sum(years.values())} (matched {matched}), unique object_id {len(ids)}, Antragsjahr {dict(years)}")
    print("top crops (parcel count):", crops.most_common(12))
    for fid, (_, hit) in demo.items():
        print(f"{fid}: {sum(hit.values())} parcels inside the OSM polygon: {dict(hit)}")


if __name__ == "__main__":
    main()
