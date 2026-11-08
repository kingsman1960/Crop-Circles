"""Dataset 17 - ecostress: ECOSTRESS 70 m land-surface temperature (L2T LSTE) and evaporative stress index (L4T ESI)
at each field centroid, one AppEEARS point request (2018-07-09 -> today). ECOSTRESS flies on the ISS: a few
daytime passes a week in summer, at changing hours, so the output is instantaneous readings, not daily values.

Re-running resumes the submitted task (data/raw/ecostress/appeears_task.json); delete that file to resubmit.
`--submit-only` submits and exits.
"""
import sys
from datetime import date

import pandas as pd

from common import RAW, appeears_download, appeears_login, appeears_logout, appeears_task, appeears_wait, load_config, log, now_utc

LAYERS = {"ECO_L2T_LSTE.002": ["LST", "LST_err", "QC", "cloud"], "ECO_L4T_ESI.002": ["ESI", "PET", "cloud"]}
START = "2018-07-09"  # mission start
OUT = RAW / "ecostress"


def main():
    cfg = load_config()
    task = {"task_type": "point", "task_name": "crop-circles-ecostress",
            "params": {"dates": [{"startDate": pd.Timestamp(START).strftime("%m-%d-%Y"),
                                  "endDate": date.today().strftime("%m-%d-%Y")}],
                       "layers": [{"product": p, "layer": l} for p, ls in LAYERS.items() for l in ls],
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
        log(path, "ecostress", source="NASA AppEEARS point sample (LP DAAC)", product_version=", ".join(LAYERS),
            query_or_url=f"{url} (task {task_id})", spatial="field centroids F1-F3", temporal=f"{START} -> latest",
            downloaded_at_utc=when, license="NASA open data (no restrictions)",
            attribution="Hook, S., Hulley, G. ECOSTRESS Tiled Land Surface Temperature and Emissivity (ECO_L2T_LSTE) and "
                        "Evaporative Stress Index PT-JPL (ECO_L4T_ESI), v002. NASA LP DAAC, retrieved via AppEEARS")

    # one results CSV per product; joined on field and acquisition
    frames = [pd.read_csv(p) for p, _ in files if p.name.endswith("results.csv")]
    keys = ["ID", "Latitude", "Longitude", "Date"] + [c for c in ("Time",) if all(c in f for f in frames)]
    df = frames[0]
    for f in frames[1:]:
        df = df.merge(f, on=keys, how="outer", suffixes=("", "_dup"))
    for fid, g in df.groupby("ID"):
        g.to_csv(OUT / f"{fid}.csv", index=False)
        print(f"\n{fid}.csv: {len(g)} rows, {g.Date.min()} -> {g.Date.max()}; columns {list(g.columns)}")


if __name__ == "__main__":
    main()
