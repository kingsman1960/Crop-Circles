"""Dataset 13 - bk50: LGRB BW soil map 1:50 000 (GeoLa BK50) for the study bbox, via the LGRB MapServer WFS.

Same service family as the GeoAX project (services.lgrb-bw.de/ms/lgrb_geola_*), but WFS instead of WMS GetFeatureInfo.
Soil-unit polygons (geola_bod_ke) are fetched once with geometry; the thematic layers (K factor, field capacity, ...)
are attribute tables without geometry, joined later by `Kartiereinheit`.
"""
import re
from collections import defaultdict

from pyproj import Transformer

from common import RAW, http, load_config, log, now_utc

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
    b = cfg["bbox"]
    bbox = Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True).transform_bounds(
        b["min_lon"], b["min_lat"], b["max_lon"], b["max_lat"])
    base = {"SERVICE": "WFS", "VERSION": "1.1.0", "REQUEST": "GetFeature", "SRSNAME": "EPSG:25832",
            "BBOX": ",".join(f"{v:.0f}" for v in bbox) + ",EPSG:25832"}
    OUT.mkdir(parents=True, exist_ok=True)

    when = now_utc()
    readme = OUT / "readme_dBK50.pdf"
    readme.write_bytes(http("GET", README).content)
    log(readme, "bk50", query_or_url=README, spatial="BW", downloaded_at_utc=when, **META)

    # geometry layer: paged (one 14k-feature response times out at the proxy with HTTP 502)
    hits = http("GET", WFS, params={**base, "TYPENAME": f"ms:{GEOMETRY_LAYER}", "RESULTTYPE": "hits"}).text
    total = int(re.search(r'numberOfFeatures="(\d+)"', hits).group(1))
    ids = []
    for i, start in enumerate(range(0, total, PAGE)):
        when = now_utc()
        r = http("GET", WFS, params={**base, "TYPENAME": f"ms:{GEOMETRY_LAYER}", "MAXFEATURES": PAGE,
                                     "STARTINDEX": start}, timeout=900, pause=3)
        path = OUT / f"{GEOMETRY_LAYER}_p{i:02d}.gml"
        path.write_bytes(r.content)
        log(path, "bk50", query_or_url=r.url, spatial=f"bbox EPSG:25832 {base['BBOX']}", downloaded_at_utc=when, **META)
        # features carry no gml:id; the start of each polygon's coordinate list identifies it
        page = re.findall(r"<gml:posList[^>]*>([^<]{0,80})", r.text.split("<gml:featureMember>", 1)[-1])
        ids += page
        print(f"{path.name}: {r.text.count('<gml:featureMember>')} features, {len(r.content) / 1e6:.1f} MB")
    print(f"{GEOMETRY_LAYER}: {len(ids)} rings in pages, {len(set(ids))} unique, server feature count {total}")

    for layer in THEMES:
        # attribute table only: every property except the geometry
        schema = http("GET", WFS, params={"SERVICE": "WFS", "VERSION": "1.1.0", "REQUEST": "DescribeFeatureType",
                                          "TYPENAME": f"ms:{layer}"}).text
        props = [n for n in re.findall(r'element name="([^"]+)"', schema)[1:] if n != "msGeometry"]
        params = {**base, "TYPENAME": f"ms:{layer}", "PROPERTYNAME": ",".join(props)}
        when = now_utc()
        r = http("GET", WFS, params=params, timeout=900, pause=3)
        path = OUT / f"{layer}.gml"
        path.write_bytes(r.content)
        log(path, "bk50", query_or_url=r.url, spatial=f"bbox EPSG:25832 {base['BBOX']}", downloaded_at_utc=when, **META)

        units = re.findall(r"<ms:Kartiereinheit>([^<]*)</ms:Kartiereinheit>", r.text)
        line = f"{path.name}: {len(units)} features, {len(set(units))} soil units, {len(r.content) / 1e6:.1f} MB"
        # the value per soil unit must be unique for the join by Kartiereinheit
        for prop in [p for p in props if p not in ("Kartiereinheit", "Legendentext", "Link")]:
            vals = re.findall(rf"<ms:{re.escape(prop)}>([^<]*)</ms:{re.escape(prop)}>", r.text)
            per_unit = defaultdict(set)
            for u, v in zip(units, vals):
                per_unit[u].add(v)
            line += (f"\n    {prop} ({THEMES[layer]}): {len(vals)} values, "
                     f"{sum(len(s) > 1 for s in per_unit.values())} units with >1 value, "
                     f"classes {sorted(set(vals))[:12]}")
        print(line)


if __name__ == "__main__":
    main()
