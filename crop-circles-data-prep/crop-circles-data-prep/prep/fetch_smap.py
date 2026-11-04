"""Dataset 9 - smap: SMAP enhanced L3 radiometer soil moisture (9 km, daily AM/PM) at each field centroid, AppEEARS point request.

Re-running resumes the submitted task (data/raw/smap/appeears_task.json); delete that file to resubmit.
`--submit-only` submits and exits.
"""
import sys
from datetime import date

import pandas as pd

from common import RAW, appeears_download, appeears_login, appeears_logout, appeears_task, appeears_wait, load_config, log, now_utc

PRODUCT = "SPL3SMP_E.006"
LAYERS = ["Soil_Moisture_Retrieval_Data_AM_soil_moisture", "Soil_Moisture_Retrieval_Data_AM_retrieval_qual_flag",
          "Soil_Moisture_Retrieval_Data_PM_soil_moisture_pm", "Soil_Moisture_Retrieval_Data_PM_retrieval_qual_flag_pm"]
START = "2015-03-31"  # product start
FILL = -9999
OUT = RAW / "smap"


def main():
    cfg = load_config()
    task = {"task_type": "point", "task_name": "crop-circles-smap",
            "params": {"dates": [{"startDate": pd.Timestamp(START).strftime("%m-%d-%Y"),
                                  "endDate": date.today().strftime("%m-%d-%Y")}],
                       "layers": [{"product": PRODUCT, "layer": l} for l in LAYERS],
                       "coordinates": [{"id": f["id"], "category": f["id"], "latitude": f["lat"], "longitude": f["lon"]}
                                       for f in cfg["fields"]]}}
    token = appeears_login()
    try:
        task_id = appeears_task(token, task, OUT / "appeears_task.json")
        print(f"AppEEARS task {task_id}")
        if "--submit-only" in sys.argv:
            return
        appeears_wait(token, task_id)
        when = now_utc()
        files = appeears_download(token, task_id, OUT / "appeears")
    finally:
        appeears_logout(token)

    for path, url in files:
        log(path, "smap", source="NASA AppEEARS point sample (NSIDC DAAC)", product_version=PRODUCT,
            query_or_url=f"{url} (task {task_id})", spatial="field centroids F1-F3", temporal=f"{START} -> latest",
            downloaded_at_utc=when, license="NASA open data (no restrictions)",
            attribution="O'Neill, P. E., et al. SMAP Enhanced L3 Radiometer Global and Polar Grid Daily 9 km EASE-Grid "
                        "Soil Moisture, Version 6. NASA NSIDC DAAC, retrieved via AppEEARS")

    src = next(p for p, _ in files if p.name.endswith("results.csv"))  # one product in this task
    df = pd.read_csv(src)
    pre = PRODUCT.replace(".", "_") + "_"
    for fid, g in df.groupby("ID"):
        out = g[["Date", "Latitude", "Longitude"] + [pre + l for l in LAYERS]]
        out.columns = ["date", "lat", "lon", "sm_am", "qual_am", "sm_pm", "qual_pm"]
        out.to_csv(OUT / f"{fid}.csv", index=False)
        d = pd.to_datetime(out.date)
        print(f"\n{fid}.csv: {len(out)} rows, {d.min().date()} -> {d.max().date()}")
        for c in ("sm_am", "sm_pm"):
            print(f"  {c}: valid {int((out[c] != FILL).sum())}, fill {int((out[c] == FILL).sum())}, NaN {int(out[c].isna().sum())}")


if __name__ == "__main__":
    main()
