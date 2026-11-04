"""Dataset 8 - gpm_imerg: IMERG Final daily V07 at each field (0.1 deg grid cell), Giovanni in the Cloud time-series API.

Point series = the grid cell containing the field centroid. End date = latest granule listed in CMR.
"""
import io
import netrc

import pandas as pd

from common import RAW, http, load_config, log, now_utc

API = "https://api.giovanni.earthdata.nasa.gov/timeseries"
DATA = "GPM_3IMERGDF_07_precipitation"
COLLECTION = "C2723754864-GES_DISC"  # GPM_3IMERGDF.07 in CMR
START = "2001-01-01"
OUT = RAW / "gpm_imerg"


def main():
    cfg = load_config()
    latest = http("GET", "https://cmr.earthdata.nasa.gov/search/granules.json",
                  params={"collection_concept_id": COLLECTION, "sort_key": "-start_date", "page_size": 1}
                  ).json()["feed"]["entry"][0]["time_start"][:10]
    print(f"latest IMERG Final daily granule in CMR: {latest}")
    user, _, password = netrc.netrc().authenticators("urs.earthdata.nasa.gov")
    token = http("POST", "https://urs.earthdata.nasa.gov/api/users/find_or_create_token",
                 auth=(user, password)).json()["access_token"]
    OUT.mkdir(parents=True, exist_ok=True)
    for f in cfg["fields"]:
        when = now_utc()
        r = http("GET", API, params={"data": DATA, "location": f"[{f['lat']},{f['lon']}]",
                                     "time": f"{START}T00:00:00/{latest}T23:59:59"},
                 headers={"Authorization": f"Bearer {token}"}, timeout=1800, pause=10)
        path = OUT / f"{f['id']}_daily.csv"
        path.write_bytes(r.content)
        log(path, "gpm_imerg", source="GES DISC Giovanni in the Cloud time-series API", product_version="GPM_3IMERGDF.07",
            query_or_url=r.url, spatial=f"0.1 deg cell containing {f['lat']},{f['lon']} ({f['id']})",
            temporal=f"{START} -> {latest}", downloaded_at_utc=when, license="NASA open data (no restrictions)",
            attribution="Huffman, G.J., et al. (2023), GPM IMERG Final Precipitation L3 1 day 0.1 degree x 0.1 degree "
                        "V07, GES DISC, doi:10.5067/GPM/IMERGDF/DAY/07")

        meta, body = r.text.split("\n\n", 1)  # key,value header block, blank line, then "Timestamp (UTC),Data"
        head = dict(l.split(",", 1) for l in meta.splitlines())
        df = pd.read_csv(io.StringIO(body))
        df.columns = ["time", "precipitation"]
        t = pd.to_datetime(df.time)
        undef = float(head["undef"])
        print(f"\n{f['id']} {path.name}: cell centre {head['lat']}, {head['lon']}; {len(df)} rows, "
              f"{t.min().date()} -> {t.max().date()}, expected {(t.max() - t.min()).days + 1} days")
        print(f"  undef ({undef}): {int((df.precipitation == undef).sum())}, NaN: {int(df.precipitation.isna().sum())}, "
              f"unit {head['unit']}")


if __name__ == "__main__":
    main()
