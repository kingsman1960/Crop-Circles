"""Dataset 15 - esa_cci_sm: ESA CCI Soil Moisture COMBINED v09.2 (0.25 deg, daily) for the grid cells containing the fields.

CEDA serves one global NetCDF per day (~1.4 MB); OPeNDAP returns just our cells, so this is one small request per day.
Values are written as returned (no scaling). Resumable: days already in the CSV are skipped.
  python prep/fetch_esa_cci_sm.py [START END]     # default 2020-01-01 2024-12-31 (auxiliary: recent years only;
                                                 # v09.2 covers 1978-11-01 -> 2024-12-31, ~0.65 s per day)
"""
import csv
import math
import sys
from datetime import date, timedelta

import requests

from common import RAW, http, load_config, log, now_utc

VERSION = "v09.2"
DAP = ("https://dap.ceda.ac.uk/thredds/dodsC/neodc/esacci/soil_moisture/data/daily_files/COMBINED/{v}/{y}/"
       "ESACCI-SOILMOISTURE-L3S-SSMV-COMBINED-{d}000000-f{v}.nc.ascii?{q}")
VARS = ["sm", "sm_uncertainty", "flag", "freqbandID"]
OUT = RAW / "esa_cci_sm"
CSV = OUT / f"cci_sm_combined_{VERSION}_daily.csv"


def cell(v):  # index and centre of the 0.25 deg cell containing v
    return math.floor(v / 0.25) * 0.25 + 0.125


def parse(text, var):
    """Values of `var` from an OPeNDAP .ascii response ("var.var[1][1][n]" then "[0][0], v1, v2, ...")."""
    lines = text.splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith(f"{var}.{var}["))
    return [float(x) for x in lines[i + 1].split(",")[1:]]


def main():
    cfg = load_config()
    start, end = (date.fromisoformat(a) for a in (sys.argv[1:3] or ["2020-01-01", "2024-12-31"]))
    lat = sorted({cell(f["lat"]) for f in cfg["fields"]})
    lon = sorted({cell(f["lon"]) for f in cfg["fields"]})
    i0, i1 = (round((89.875 - v) / 0.25) for v in (lat[-1], lat[0]))  # lat axis runs north -> south
    j0, j1 = (round((v + 179.875) / 0.25) for v in (lon[0], lon[-1]))
    q = ",".join(f"{v}[0:0][{i0}:{i1}][{j0}:{j1}]" for v in VARS)
    lats = [89.875 - 0.25 * i for i in range(i0, i1 + 1)]
    lons = [-179.875 + 0.25 * j for j in range(j0, j1 + 1)]
    print(f"cells: lat {lats}, lon {lons}; fields -> " +
          ", ".join(f"{f['id']} ({cell(f['lat'])}, {cell(f['lon'])})" for f in cfg["fields"]))

    OUT.mkdir(parents=True, exist_ok=True)
    done = set()
    if CSV.exists():
        with CSV.open(newline="") as fh:
            done = {r["date"] for r in csv.DictReader(fh)}
    new = not CSV.exists()
    first = now_utc()
    missing = []
    with CSV.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["date", "lat", "lon", *VARS])
        d = start
        while d <= end:
            if d.isoformat() not in done:
                try:
                    r = http("GET", DAP.format(v=VERSION, y=d.year, d=d.strftime("%Y%m%d"), q=q), pause=0.2, timeout=120)
                except requests.HTTPError as e:
                    if e.response.status_code != 404:
                        raise
                    missing.append(d.isoformat())  # no file for that day
                    d += timedelta(days=1)
                    continue
                vals = {v: parse(r.text, v) for v in VARS}
                for k, (la, lo) in enumerate((la, lo) for la in lats for lo in lons):
                    w.writerow([d.isoformat(), la, lo, *(vals[v][k] for v in VARS)])
                if d.day == 1 and d.month == 1:
                    fh.flush()
                    print(f"  {d.year} ...")
            d += timedelta(days=1)
    log(CSV, "esa_cci_sm", source="ESA CCI Soil Moisture via CEDA OPeNDAP (dap.ceda.ac.uk)",
        product_version=f"COMBINED {VERSION}", query_or_url=DAP.format(v=VERSION, y="YYYY", d="YYYYMMDD", q=q),
        spatial=f"0.25 deg cells lat {lats} lon {lons}", temporal=f"{start} -> {end}", downloaded_at_utc=first,
        license="CC BY 4.0",
        attribution="ESA CCI Soil Moisture COMBINED v09.2 (Dorigo et al. 2017, Gruber et al. 2019, Preimesberger et al. "
                    "2021), ESA Climate Change Initiative, via CEDA")
    print(f"days without a file on CEDA: {len(missing)} {missing[:10]}")

    with CSV.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    for la in lats:
        for lo in lons:
            rs = sorted((r for r in rows if float(r["lat"]) == la and float(r["lon"]) == lo), key=lambda r: r["date"])
            valid = [r for r in rs if float(r["sm"]) != -9999.0]
            print(f"cell {la}, {lo}: {len(rs)} days, {rs[0]['date']} -> {rs[-1]['date']}, valid sm {len(valid)} "
                  f"({len(valid) / len(rs):.0%}), flags {sorted(set(r['flag'] for r in rs))}")


if __name__ == "__main__":
    main()
