"""Dataset 13 - bk50: LGRB BW soil map 1:50 000 (GeoLa BK50) for the study bbox (--bw: all of BW, into bk50/bw/),
via the LGRB MapServer WFS.

Same service family as the GeoAX project (services.lgrb-bw.de/ms/lgrb_geola_*), but WFS instead of WMS GetFeatureInfo.
Soil-unit polygons (geola_bod_ke) are fetched once with geometry; the thematic layers (K factor, field capacity, ...)
are attribute tables without geometry, joined later by `Kartiereinheit`.
"""
import re
from collections import defaultdict

import requests
from pyproj import Transformer

from common import MANIFEST, RAW, ROOT, area, http, load_config, log, now_utc

WFS = "https://services.lgrb-bw.de/ms/lgrb_geola_bod"
README = "https://media.lgrb-bw.de/geoportal/docs/readme_dBK50.pdf"
GEOMETRY_LAYER = "geola_bod_ke"
THEMES = {"geola_bod_ke_kfa": "erodibility K factor", "geola_bod_ke_fk": "field capacity",
          "geola_bod_ke_nfk": "usable field capacity", "geola_bod_ke_lk": "air capacity",
          "geola_bod_ke_kf": "hydraulic conductivity", "geola_bod_ke_kak": "potential CEC",
          "geola_bod_ke_natbod": "natural soil fertility", "geola_bod_ke_akiwas_ln": "water-cycle function (farmland)",
          "geola_bod_ke_gesbew_ln": "overall soil-function rating (farmland)", "geola_bod_ke_gruustawr": "ground/perched water"}
OUT = RAW / "bk50"
PAGE = 3000
META = dict(source="LGRB BW GeoLa BK50 WFS (services.lgrb-bw.de/ms/lgrb_geola_bod)", product_version="GeoLa BK50",
            temporal="static", license="dl-de/by-2-0",
            attribution="Datenquelle: Regierungspräsidium Freiburg - LGRB, https://www.lgrb-bw.de")


def main():
    cfg = load_config()
    b, tag = area(cfg)
    out = OUT if tag == "bbox" else OUT / tag  # the bbox files keep their first names
    bbox = Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True).transform_bounds(
        b["min_lon"], b["min_lat"], b["max_lon"], b["max_lat"])
    base = {"SERVICE": "WFS", "VERSION": "1.1.0", "REQUEST": "GetFeature", "SRSNAME": "EPSG:25832",
            "BBOX": ",".join(f"{v:.0f}" for v in bbox) + ",EPSG:25832"}
    out.mkdir(parents=True, exist_ok=True)

    when = now_utc()
    readme = out / "readme_dBK50.pdf"
    readme.write_bytes(http("GET", README).content)
    log(readme, "bk50", query_or_url=README, spatial="BW", downloaded_at_utc=when, **META)

    def pages(layer, name, **params):
        """Every feature of `layer` in the bbox, page by page (one 14k-feature response times out at the proxy with
        HTTP 502); yields each page's text. A single page keeps the plain name `name`.gml."""
        hits = http("GET", WFS, params={**base, "TYPENAME": f"ms:{layer}", "RESULTTYPE": "hits"}).text
        total = int(re.search(r'numberOfFeatures="(\d+)"', hits).group(1))
        logged = MANIFEST.read_text(encoding="utf-8")  # a re-run keeps the pages already logged
        for i, start in enumerate(range(0, total, PAGE)):
            path = out / (f"{name}.gml" if total <= PAGE else f"{name}_p{i:02d}.gml")
            if path.relative_to(ROOT).as_posix() + "," in logged:
                yield path.read_bytes().decode("utf-8", "replace")
                continue
            when = now_utc()
            r = http("GET", WFS, params={**base, **params, "TYPENAME": f"ms:{layer}", "MAXFEATURES": PAGE,
                                         "STARTINDEX": start}, timeout=900, pause=3)
            path.write_bytes(r.content)
            log(path, "bk50", query_or_url=r.url, spatial=f"{tag} EPSG:25832 {base['BBOX']}", downloaded_at_utc=when,
                **META)
            print(f"{path.name}: {r.text.count('<gml:featureMember>')} features, {len(r.content) / 1e6:.1f} MB")
            yield r.text
        print(f"{layer}: server feature count {total}")

    quarters = lambda x0, y0, x1, y1: [(x0, y0, (x0 + x1) / 2, (y0 + y1) / 2), ((x0 + x1) / 2, y0, x1, (y0 + y1) / 2),
                                       (x0, (y0 + y1) / 2, (x0 + x1) / 2, y1), ((x0 + x1) / 2, (y0 + y1) / 2, x1, y1)]

    def tiles(box):
        """Boxes (EPSG:25832) with at most PAGE soil polygons each, so every box comes back in one response. Paging
        has no unique sort key here: on all of BW the pages overlapped (a third of the polygons twice, as many missing)."""
        q = {**base, "BBOX": ",".join(f"{v:.0f}" for v in box) + ",EPSG:25832"}
        hits = http("GET", WFS, params={**q, "TYPENAME": f"ms:{GEOMETRY_LAYER}", "RESULTTYPE": "hits"}).text
        n = int(re.search(r'numberOfFeatures="(\d+)"', hits).group(1))
        if n <= PAGE:
            return [box] if n else []
        return [t for bx in quarters(*box) for t in tiles(bx)]

    logged = MANIFEST.read_text(encoding="utf-8")  # a re-run keeps the tiles already logged

    def fetch(box, name):
        """The polygons in `box` as [GML text]; a box the proxy cannot serve in time (HTTP 502, detailed polygons)
        is fetched as four quarters `name`_0 … _3."""
        path = out / f"{name}.gml"
        if path.relative_to(ROOT).as_posix() + "," in logged:
            return [path.read_bytes().decode("utf-8", "replace")]
        q = {**base, "BBOX": ",".join(f"{v:.0f}" for v in box) + ",EPSG:25832", "TYPENAME": f"ms:{GEOMETRY_LAYER}"}
        when = now_utc()
        try:
            r = http("GET", WFS, params=q, timeout=900, pause=3, tries=2)
        except requests.HTTPError:
            print(f"{name}: no answer in time, fetching it as four quarters")
            return [t for j, bx in enumerate(quarters(*box)) for t in fetch(bx, f"{name}_{j}")]
        path.write_bytes(r.content)
        log(path, "bk50", query_or_url=r.url, spatial=f"{tag} tile EPSG:25832 {q['BBOX']}", downloaded_at_utc=when, **META)
        print(f"{path.name}: {r.text.count('<gml:featureMember>')} features, {len(r.content) / 1e6:.1f} MB")
        return [r.text]

    # geometry layer, tile by tile; a polygon across a tile edge comes back once per tile (harmless when burnt)
    feats = set()
    for i, box in enumerate(tiles(bbox)):
        for text in fetch(box, f"{GEOMETRY_LAYER}_t{i:03d}"):
            feats.update(hash(f.split("</gml:featureMember>")[0]) for f in text.split("<gml:featureMember>")[1:])
    print(f"{GEOMETRY_LAYER}: {len(feats)} distinct polygons in the tiles")

    # BW: only the tables the pipeline reads (pipeline/geo.py bk50), ~70 pages each
    themes = THEMES if tag == "bbox" else [f"geola_bod_ke_{t}" for t in ("kfa", "nfk", "kf")]
    for layer in themes:
        # attribute table only: every property except the geometry
        schema = http("GET", WFS, params={"SERVICE": "WFS", "VERSION": "1.1.0", "REQUEST": "DescribeFeatureType",
                                          "TYPENAME": f"ms:{layer}"}).text
        props = [n for n in re.findall(r'element name="([^"]+)"', schema)[1:] if n != "msGeometry"]
        units, vals = [], defaultdict(list)
        # sorted by soil unit: pages may still overlap within one unit's rows, but every unit is on some page
        # (unsorted, the BW pages missed ~1,500 of 4,100 units)
        for text in pages(layer, layer, PROPERTYNAME=",".join(props), SORTBY="Kartiereinheit"):
            units += re.findall(r"<ms:Kartiereinheit>([^<]*)</ms:Kartiereinheit>", text)
            for prop in props:
                vals[prop] += re.findall(rf"<ms:{re.escape(prop)}>([^<]*)</ms:{re.escape(prop)}>", text)
        line = f"{layer}: {len(units)} features, {len(set(units))} soil units"
        # the value per soil unit must be unique for the join by Kartiereinheit
        for prop in [p for p in props if p not in ("Kartiereinheit", "Legendentext", "Link")]:
            per_unit = defaultdict(set)
            for u, v in zip(units, vals[prop]):
                per_unit[u].add(v)
            line += (f"\n    {prop} ({THEMES[layer]}): {len(vals[prop])} values, "
                     f"{sum(len(s) > 1 for s in per_unit.values())} units with >1 value, "
                     f"classes {sorted(set(vals[prop]))[:12]}")
        print(line)


if __name__ == "__main__":
    main()
