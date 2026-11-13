"""Dataset 18 - era5_land: ERA5-Land hourly time series at each field centre (CDS `reanalysis-era5-land-timeseries`,
0.1 deg, 1950 -> present), 1981-01-01 -> period end: 2 m temperature, total precipitation and the four volumetric
soil-water layers (0-7, 7-28, 28-100, 100-289 cm). One zip per field (CDS packs the CSV per variable group), kept as
downloaded.

Needs ~/.cdsapirc (CDS personal access token, set up by the user) and the dataset licence accepted on the CDS website.
Request form checked against the CDS catalogue (form.json, 2026-11-13): variable, location {longitude, latitude}, date
"start/end", data_format csv. Notes for the pipeline: temperatures in K; `tp` is accumulated since 00 UTC of the same
day, so the value at 00 UTC holds the previous day's total (m); swvl in m³/m³.
"""
import zipfile

import cdsapi

from common import RAW, load_config, log, now_utc

DATASET = "reanalysis-era5-land-timeseries"
VARS = ["2m_temperature", "total_precipitation", "volumetric_soil_water_level_1", "volumetric_soil_water_level_2",
        "volumetric_soil_water_level_3", "volumetric_soil_water_level_4"]
OUT = RAW / "era5_land"


def main():
    cfg = load_config()
    start, end = cfg["period"]["start"], cfg["period"]["end"]
    OUT.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client()
    for f in cfg["fields"]:
        target = OUT / f"{f['id']}_hourly.zip"
        req = {"variable": VARS, "location": {"longitude": f["lon"], "latitude": f["lat"]},
               "date": [f"{start}/{end}"], "data_format": "csv"}
        when = now_utc()
        if not target.exists():  # CDS queues each request; re-runs skip finished downloads
            part = target.with_suffix(".part")  # an interrupted download must not look finished
            client.retrieve(DATASET, req, str(part))
            part.replace(target)
        log(target, "era5_land", source="Copernicus Climate Data Store, reanalysis-era5-land-timeseries",
            product_version="ERA5-Land hourly time series", query_or_url=f"cdsapi {DATASET} {req}",
            spatial=f"0.1 deg cell at {f['lat']}, {f['lon']}", temporal=f"{start} -> {end} hourly", downloaded_at_utc=when,
            license="CC-BY (Licence to use Copernicus Products)",
            attribution="Contains modified Copernicus Climate Change Service information (2026); ERA5-Land hourly data "
                        "(Muñoz Sabater, 2019), doi:10.24381/cds.e2161bac")
        with zipfile.ZipFile(target) as zf:
            for n in zf.namelist():
                lines = zf.read(n).decode("utf-8").splitlines()
                print(f"{f['id']} {n}: {len(lines) - 1} rows, {lines[1][:19]} -> {lines[-1][:19]}; header: {lines[0][:120]}")


if __name__ == "__main__":
    main()
