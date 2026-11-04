"""Dataset 2 - nasa_power: daily POWER point data per field (AG community), saved as raw CSV responses."""
import io

import pandas as pd

from common import RAW, http, load_config, log, now_utc

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,WS2M,ALLSKY_SFC_SW_DWN,GWETTOP,GWETROOT"
# verbatim from https://power.larc.nasa.gov/docs/referencing/ (data reference filled in per download)
ATTRIBUTION = ("The data was obtained from National Aeronautics and Space Administration (NASA) Langley Research "
               "Center's Prediction Of Worldwide Energy Resources (POWER) project funded through the NASA Earth "
               "Science Division. The data was obtained from the POWER Project's Daily {version} on {date}.")
OUT = RAW / "nasa_power"


def main():
    cfg = load_config()
    start, end = (cfg["period"][k].replace("-", "") for k in ("start", "end"))
    OUT.mkdir(parents=True, exist_ok=True)
    f0 = cfg["fields"][0]  # the CSV header carries no API version; a 1-day JSON request does
    hdr = http("GET", URL, params={"parameters": "T2M", "community": "AG", "latitude": f0["lat"], "longitude": f0["lon"],
                                   "start": end, "end": end, "format": "JSON"}).json()["header"]["api"]
    version = f"{hdr['name']} {hdr['version']}"
    for f in cfg["fields"]:
        q = {"parameters": PARAMS, "community": "AG", "latitude": f["lat"], "longitude": f["lon"],
             "start": start, "end": end, "format": "CSV", "time-standard": "LST"}
        when = now_utc()
        r = http("GET", URL, params=q, pause=5)
        path = OUT / f"{f['id']}_daily.csv"
        path.write_bytes(r.content)

        text = r.text
        _, body = text.split("-END HEADER-")
        log(path, "nasa_power", source="NASA LaRC POWER API (daily point, community AG)",
            product_version=version, query_or_url=r.url, spatial=f"point {f['lat']},{f['lon']} ({f['id']})",
            temporal=f"{start}-{end}", downloaded_at_utc=when, license="NASA open data (no restrictions)",
            attribution=ATTRIBUTION.format(version=hdr["version"], date=when[:10].replace("-", "/")))

        df = pd.read_csv(io.StringIO(body.lstrip()))
        dates = pd.to_datetime(df["YEAR"].astype(str) + df["DOY"].astype(str).str.zfill(3), format="%Y%j")
        print(f"\n{f['id']} {path.name}: {len(df)} rows, {dates.min().date()} -> {dates.max().date()}, "
              f"expected {(dates.max() - dates.min()).days + 1} days | {version}")
        miss = (df.drop(columns=["YEAR", "DOY"]) == -999).sum()
        print("  -999 count: " + ", ".join(f"{k}={v}" for k, v in miss.items()))
        for col in miss[miss > 0].index:
            ok = dates[df[col] != -999]
            print(f"  {col}: valid {ok.min().date()} -> {ok.max().date()}")


if __name__ == "__main__":
    main()
