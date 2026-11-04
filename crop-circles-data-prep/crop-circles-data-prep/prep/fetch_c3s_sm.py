"""Dataset 16 - c3s_sm: C3S satellite soil moisture (CDS `satellite-soil-moisture`, ESA CCI algorithm), daily COMBINED,
2025-01-01 -> latest, to continue esa_cci_sm (CCI v09.2 ends 2024-12-31).

Needs ~/.cdsapirc (CDS personal access token, set up by the user) and the dataset licence accepted on the CDS website.
CDS has no area subset for this dataset: the zips hold one global NetCDF per day (kept as downloaded); the cells
containing the fields are extracted to a CSV. Versions per CDS constraints (2026-11-04): v202505 icdr covers
2025-01 -> 2026-09, v202505_2 icdr 2026-09 -> 10. CDS notice 2026-10-21: v202505 for 1-20 Sep 2026 has many missing
values (COMBINED included); use v202505_2 from 2026-09-01.
"""
import csv
import math
import re
import zipfile

import cdsapi
import rasterio

from common import RAW, load_config, log, now_utc

DATASET = "satellite-soil-moisture"
REQUESTS = [("2025", "v202505", [f"{m:02d}" for m in range(1, 13)]),
            ("2026", "v202505", [f"{m:02d}" for m in range(1, 9)]),
            ("2026", "v202505_2", ["09", "10"])]
VARS = ["sm", "sm_uncertainty", "flag"]
OUT = RAW / "c3s_sm"
CSV = OUT / "c3s_sm_combined_daily.csv"


def cell(v):  # centre of the 0.25 deg cell containing v
    return math.floor(v / 0.25) * 0.25 + 0.125


def main():
    cfg = load_config()
    cells = sorted({(cell(f["lat"]), cell(f["lon"])) for f in cfg["fields"]})
    OUT.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client()
    zips = []
    for year, version, months in REQUESTS:
        req = {"variable": ["surface_soil_moisture_volumetric"], "type_of_sensor": ["combined"],
               "time_aggregation": ["daily"], "year": [year], "month": months,
               "day": [f"{d:02d}" for d in range(1, 32)], "type_of_record": ["icdr"], "version": [version]}
        target = OUT / f"c3s_sm_combined_daily_{year}_{version}.zip"
        when = now_utc()
        if not target.exists():  # CDS queues each request; re-runs skip finished downloads
            part = target.with_suffix(".part")  # an interrupted download must not look finished
            client.retrieve(DATASET, req, str(part))
            part.replace(target)
        log(target, "c3s_sm", source="Copernicus Climate Data Store, satellite-soil-moisture", product_version=f"{version} icdr",
            query_or_url=f"cdsapi {DATASET} {req}", spatial="global 0.25 deg", temporal=f"{year} months {months[0]}-{months[-1]}",
            downloaded_at_utc=when, license="CC-BY (Licence to use Copernicus Products)",
            attribution="Contains modified Copernicus Climate Change Service information (2026); C3S satellite soil moisture "
                        "(Dorigo et al.), doi:10.24381/cds.d7782f18")
        zips.append(target)

    rows = []
    for z in zips:
        names = sorted(n for n in zipfile.ZipFile(z).namelist() if n.endswith(".nc"))
        for n in names:
            day = re.search(r"(\d{8})\d{6}", n).group(1)
            for var in VARS:
                with rasterio.open(f'netcdf:"/vsizip/{z.as_posix()}/{n}":{var}') as src:
                    a = src.read(1)
                    for la, lo in cells:
                        r, c = src.index(lo, la)
                        rows.append((f"{day[:4]}-{day[4:6]}-{day[6:]}", la, lo, var, float(a[r, c]), z.name))
    # long -> one row per date and cell
    table = {}
    for d, la, lo, var, v, src_zip in rows:
        table.setdefault((d, la, lo), {"date": d, "lat": la, "lon": lo, "source_zip": src_zip})[var] = v
    with CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, ["date", "lat", "lon", *VARS, "source_zip"])
        w.writeheader()
        w.writerows(sorted(table.values(), key=lambda r: (r["date"], r["lat"], r["lon"])))

    for la, lo in cells:
        rs = sorted((r for r in table.values() if (r["lat"], r["lon"]) == (la, lo)), key=lambda r: r["date"])
        valid = [r for r in rs if r["sm"] != -9999.0 and not math.isnan(r["sm"])]
        print(f"cell {la}, {lo}: {len(rs)} days, {rs[0]['date']} -> {rs[-1]['date']}, valid sm {len(valid)} "
              f"({len(valid) / len(rs):.0%})")


if __name__ == "__main__":
    main()
