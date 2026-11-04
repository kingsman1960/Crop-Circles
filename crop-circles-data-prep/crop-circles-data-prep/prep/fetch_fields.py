"""Dataset 1 - fields: OSM landuse=farmland polygons in the study bbox.

  python prep/fetch_fields.py                      # download + list candidates per placeholder
  python prep/fetch_fields.py --pick F1=way/123 F2=way/456 F3=way/789
                                                   # write chosen polygons + centroids into the config
"""
import argparse
import json
import math

from common import CONFIG, R_EARTH, RAW as RAW_DIR, ROOT, dist_km, http, load_config, log, now_utc

OUT = RAW_DIR / "fields"
RAW = OUT / "overpass_response.json"
GEOJSON = OUT / "osm_farmland.geojson"
OVERPASS = "https://overpass-api.de/api/interpreter"
ATTRIBUTION = "© OpenStreetMap contributors"
LICENSE = "ODbL 1.0"


def query(bbox):
    b = f'{bbox["min_lat"]},{bbox["min_lon"]},{bbox["max_lat"]},{bbox["max_lon"]}'
    return f'[out:json][timeout:300];\n(way["landuse"="farmland"]({b});\n relation["landuse"="farmland"]({b}););\nout geom;'


def stitch(segments):
    """Join open way segments of a multipolygon relation into closed rings (by shared end nodes)."""
    segs = [s[:] for s in segments if len(s) > 1]
    rings = []
    while segs:
        ring = segs.pop(0)
        while ring[0] != ring[-1]:
            for i, s in enumerate(segs):
                if s[0] == ring[-1]:
                    ring += s[1:]
                elif s[-1] == ring[-1]:
                    ring += s[::-1][1:]
                elif s[-1] == ring[0]:
                    ring = s[:-1] + ring
                elif s[0] == ring[0]:
                    ring = s[::-1][:-1] + ring
                else:
                    continue
                segs.pop(i)
                break
            else:
                break  # cannot close: drop below
        if len(ring) >= 4 and ring[0] == ring[-1]:
            rings.append(ring)
    return rings


def to_features(osm):
    feats, dropped = [], []
    for el in osm["elements"]:
        if el["type"] == "way":
            ring = [[p["lon"], p["lat"]] for p in el["geometry"]]
            if len(ring) < 4 or ring[0] != ring[-1]:
                dropped.append(f"way/{el['id']}")
                continue
            geom = {"type": "Polygon", "coordinates": [ring]}
        else:
            role = lambda r: [[[p["lon"], p["lat"]] for p in m["geometry"]]
                              for m in el["members"] if m["type"] == "way" and m["role"] == r and "geometry" in m]
            outers, inners = stitch(role("outer")), stitch(role("inner"))
            if not outers:
                dropped.append(f"relation/{el['id']}")
                continue
            # holes are attached to the outer ring that contains their first vertex
            polys = [[o] for o in outers]
            for h in inners:
                for p in polys:
                    if inside(h[0], p[0]):
                        p.append(h)
                        break
            geom = {"type": "MultiPolygon", "coordinates": polys}
        feats.append({"type": "Feature", "id": f"{el['type']}/{el['id']}",
                      "properties": {"osm_id": f"{el['type']}/{el['id']}", **el.get("tags", {})}, "geometry": geom})
    return feats, dropped


def inside(pt, ring):
    x, y, c = pt[0], pt[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def ring_stats(ring, lat0):
    """Signed area (m²) and centroid (lon, lat) via shoelace on a local equirectangular projection."""
    kx, ky = math.radians(1) * R_EARTH * math.cos(math.radians(lat0)), math.radians(1) * R_EARTH
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        x1, y1, x2, y2 = x1 * kx, y1 * ky, x2 * kx, y2 * ky
        f = x1 * y2 - x2 * y1
        a, cx, cy = a + f, cx + (x1 + x2) * f, cy + (y1 + y2) * f
    a /= 2
    return a, (cx / (6 * a) / kx, cy / (6 * a) / ky) if a else ring[0]


def area_centroid(geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    lat0 = polys[0][0][0][1]
    total = sx = sy = 0.0
    for poly in polys:
        for k, ring in enumerate(poly):
            a, (x, y) = ring_stats(ring, lat0)
            a = abs(a) * (1 if k == 0 else -1)  # outer adds, holes subtract
            total, sx, sy = total + a, sx + a * x, sy + a * y
    return total, (sx / total, sy / total)


def fetch(cfg):
    q = query(cfg["bbox"])
    OUT.mkdir(parents=True, exist_ok=True)
    when = now_utc()
    RAW.write_bytes(http("POST", OVERPASS, data={"data": q}, timeout=360).content)
    osm = json.loads(RAW.read_bytes())
    feats, dropped = to_features(osm)
    GEOJSON.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")

    b = cfg["bbox"]
    meta = dict(license=LICENSE, attribution=ATTRIBUTION, product_version=f'OSM snapshot {osm["osm3s"]["timestamp_osm_base"]}', query_or_url=f"{OVERPASS} | {q}",
                  spatial=f'bbox {b["min_lon"]},{b["min_lat"]},{b["max_lon"]},{b["max_lat"]}',
                  temporal=osm["osm3s"]["timestamp_osm_base"], downloaded_at_utc=when)
    log(RAW, "fields", source="OpenStreetMap via Overpass API (raw response)", **meta)
    log(GEOJSON, "fields", source="OpenStreetMap via Overpass API (converted to GeoJSON from overpass_response.json)", **meta)

    n_way = sum(e["type"] == "way" for e in osm["elements"])
    print(f"OSM snapshot: {osm['osm3s']['timestamp_osm_base']}")
    print(f"elements: {len(osm['elements'])} ({n_way} ways, {len(osm['elements']) - n_way} relations)")
    print(f"features written: {len(feats)}, dropped (unclosed geometry): {len(dropped)} {dropped[:10]}")
    for p in (RAW, GEOJSON):
        print(f"{p.relative_to(ROOT).as_posix()}: {p.stat().st_size / 1e6:.1f} MB")
    return feats


def candidates(cfg, feats, n=6, radius_km=4):
    stats = []
    for f in feats:
        a, (lon, lat) = area_centroid(f["geometry"])
        stats.append((f, a / 1e4, lon, lat))
    areas = sorted(s[1] for s in stats)
    print(f"\npolygon area (ha): min {areas[0]:.2f}, median {areas[len(areas) // 2]:.2f}, max {areas[-1]:.1f}")
    for fld in cfg["fields"]:
        near = sorted((dist_km(fld["lon"], fld["lat"], lon, lat), f, ha, lon, lat) for f, ha, lon, lat in stats
                      if ha >= 5 and dist_km(fld["lon"], fld["lat"], lon, lat) <= radius_km)
        print(f"\n{fld['id']} {fld['label']} ({fld['lat']}, {fld['lon']}): {len(near)} polygons >= 5 ha within {radius_km} km")
        print(f"  {'osm_id':<20}{'area_ha':>9}{'dist_km':>9}  {'centroid lat, lon':<20}  tags")
        for d, f, ha, lon, lat in near[:n]:
            tags = {k: v for k, v in f["properties"].items() if k not in ("osm_id", "landuse")}
            print(f"  {f['id']:<20}{ha:>9.1f}{d:>9.2f}  {lat:.5f}, {lon:.5f}  {tags or ''}")


def pick(cfg, choices):
    by_id = {f["id"]: f for f in json.loads(GEOJSON.read_text(encoding="utf-8"))["features"]}
    for c in choices:
        fid, osm_id = c.split("=")
        f, fld = by_id[osm_id], next(x for x in cfg["fields"] if x["id"] == fid)
        ha, (lon, lat) = area_centroid(f["geometry"])
        fld.update(label=fld["label"].split(" (placeholder")[0], lat=round(lat, 6), lon=round(lon, 6),
                   polygon=f["geometry"], osm_id=osm_id, area_ha=round(ha / 1e4, 2))
        print(f"{fid} <- {osm_id}: {ha / 1e4:.1f} ha, centroid {lat:.6f}, {lon:.6f}")
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pick", nargs="+", metavar="FIELD=OSM_ID")
    args = ap.parse_args()
    cfg = load_config()
    if args.pick:
        pick(cfg, args.pick)
    else:
        candidates(cfg, fetch(cfg))
