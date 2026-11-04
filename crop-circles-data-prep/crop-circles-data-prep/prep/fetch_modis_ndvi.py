"""Dataset 5 - modis_ndvi: MOD13Q1/MYD13Q1 v061 NDVI per MODIS pixel inside each field, via an AppEEARS point request.

One point per 250 m MODIS pixel whose centre lies inside the field polygon (pixel_id = global grid row_col).
Re-running resumes the submitted task (data/raw/modis_ndvi/appeears_task.json); delete that file to resubmit.
"""
import math
from datetime import date

import pandas as pd

from common import RAW, appeears_download, appeears_login, appeears_logout, appeears_task, appeears_wait, load_config, log, now_utc
from fetch_fields import inside

PRODUCTS = ["MOD13Q1.061", "MYD13Q1.061"]
LAYERS = ["_250m_16_days_NDVI", "_250m_16_days_pixel_reliability", "_250m_16_days_VI_Quality"]
START = "2001-01-01"
OUT = RAW / "modis_ndvi"
# MODIS sinusoidal grid (MODLAND): sphere radius, grid origin and 250 m pixel size
R, X0, Y0, PIX = 6371007.181, -20015109.354, 10007554.677, 1111950.5197665 / 4800


def pixels_in(polygon):
    """(row, col, lat, lon) of every MODIS 250 m pixel whose centre is inside the polygon's outer ring(s)."""
    rings = [polygon["coordinates"][0]] if polygon["type"] == "Polygon" else [p[0] for p in polygon["coordinates"]]
    fwd = lambda lon, lat: (R * math.radians(lon) * math.cos(math.radians(lat)), R * math.radians(lat))
    out = []
    for ring in rings:
        xs, ys = zip(*(fwd(*p) for p in ring))
        for row in range(int((Y0 - max(ys)) // PIX), int((Y0 - min(ys)) // PIX) + 1):
            for col in range(int((min(xs) - X0) // PIX), int((max(xs) - X0) // PIX) + 1):
                y = Y0 - (row + 0.5) * PIX
                lat = math.degrees(y / R)
                lon = math.degrees((X0 + (col + 0.5) * PIX) / (R * math.cos(math.radians(lat))))
                if inside((lon, lat), ring):
                    out.append((row, col, lat, lon))
    return out


def main():
    cfg = load_config()
    coords = []
    for f in cfg["fields"]:
        px = pixels_in(f["polygon"])
        print(f"{f['id']}: {len(px)} MODIS pixel centres inside the polygon")
        coords += [{"id": f"{f['id']}_{r}_{c}", "category": f["id"], "latitude": round(la, 6), "longitude": round(lo, 6)}
                   for r, c, la, lo in px]
    task = {"task_type": "point", "task_name": "crop-circles-modis-ndvi",
            "params": {"dates": [{"startDate": pd.Timestamp(START).strftime("%m-%d-%Y"),
                                  "endDate": date.today().strftime("%m-%d-%Y")}],
                       "layers": [{"product": p, "layer": l} for p in PRODUCTS for l in LAYERS],
                       "coordinates": coords}}

    token = appeears_login()
    try:
        task_id = appeears_task(token, task, OUT / "appeears_task.json")
        print(f"AppEEARS task {task_id}")
        appeears_wait(token, task_id)
        when = now_utc()
        files = appeears_download(token, task_id, OUT / "appeears")
    finally:
        appeears_logout(token)

    for path, url in files:
        log(path, "modis_ndvi", source="NASA AppEEARS point sample (LP DAAC)", product_version=", ".join(PRODUCTS),
            query_or_url=f"{url} (task {task_id})", spatial=f"{len(coords)} MODIS pixel centres in fields",
            temporal=f"{START} -> latest", downloaded_at_utc=when, license="NASA open data (no restrictions)",
            attribution="MODIS MOD13Q1/MYD13Q1 v061 (Didan, K., NASA LP DAAC), retrieved via AppEEARS")

    for product in PRODUCTS:
        src = next(p for p, _ in files if p.name.endswith("results.csv") and product.split(".")[0] in p.name)
        df = pd.read_csv(src)
        pre = product.replace(".", "_") + "_"
        long = pd.DataFrame({"field_id": df.Category, "date": df.Date, "pixel_id": df.ID, "lat": df.Latitude,
                             "lon": df.Longitude, "ndvi": df[pre + LAYERS[0]], "reliability": df[pre + LAYERS[1]],
                             "vi_quality": df[pre + LAYERS[2]]})
        dates = pd.to_datetime(long.date)
        for fid, g in long.groupby("field_id"):
            out = OUT / f"{fid}_{product.split('.')[0]}.csv"
            g.drop(columns="field_id").to_csv(out, index=False)
            d = pd.to_datetime(g.date)
            per_year = d.drop_duplicates().dt.year.value_counts().sort_index()
            print(f"\n{out.name}: {len(g)} rows, {g.pixel_id.nunique()} pixels, {d.nunique()} composites, "
                  f"{d.min().date()} -> {d.max().date()}")
            print(f"  composites/year: min {per_year.min()} ({per_year.idxmin()}), max {per_year.max()}, "
                  f"median {per_year.median():.0f}")
            print(f"  ndvi fill/NaN: {int((g.ndvi.isna() | (g.ndvi == -0.3)).sum())}, "
                  f"reliability counts: {g.reliability.value_counts().sort_index().to_dict()}")
        print(f"{product}: {dates.nunique()} composites in total")


if __name__ == "__main__":
    main()
