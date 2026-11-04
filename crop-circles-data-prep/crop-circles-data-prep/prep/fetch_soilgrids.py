"""Dataset 6 - soilgrids: ISRIC SoilGrids 2.0 point query per field centroid (raw JSON response)."""
import json

from common import RAW, http, load_config, log, now_utc

URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPS = ["clay", "sand", "silt", "soc", "bdod", "phh2o", "cec"]
DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm"]
VALUES = ["mean", "Q0.05", "Q0.95"]
OUT = RAW / "soilgrids"


def main():
    cfg = load_config()
    OUT.mkdir(parents=True, exist_ok=True)
    for f in cfg["fields"]:
        when = now_utc()
        # fair use: ISRIC asks for at most 5 requests per minute
        r = http("GET", URL, params={"lon": f["lon"], "lat": f["lat"], "property": PROPS, "depth": DEPTHS,
                                     "value": VALUES}, pause=15, timeout=120)
        path = OUT / f"{f['id']}.json"
        path.write_bytes(r.content)
        log(path, "soilgrids", source="ISRIC SoilGrids 2.0 REST properties/query", product_version="SoilGrids 2.0",
            query_or_url=r.url, spatial=f"point {f['lat']},{f['lon']} ({f['id']})", temporal="static",
            downloaded_at_utc=when, license="CC BY 4.0",
            attribution="SoilGrids 2.0, ISRIC - World Soil Information (Poggio et al. 2021, SOIL 7, 217-240), CC BY 4.0")

        layers = json.loads(r.content)["properties"]["layers"]
        print(f"\n{f['id']} {path.name}: {len(layers)} properties")
        for l in layers:
            vals = {d["label"]: tuple(d["values"].get(v) for v in VALUES) for d in l["depths"]}
            nulls = sum(v is None for t in vals.values() for v in t)
            print(f"  {l['name']:<6} [{l['unit_measure']['mapped_units']}, /{l['unit_measure']['d_factor']}] "
                  f"nulls {nulls}  mean/Q05/Q95: {vals}")


if __name__ == "__main__":
    main()
