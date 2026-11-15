"""Climate fit of each crop on a field, from content/ecocrop_south_germany.csv (FAO EcoCrop, adapted to south Germany).

The EcoCrop method: a crop fits fully inside its optimal range, not at all outside its absolute range, linearly in
between. Here, per field, from its daily weather (data/processed/daily.parquet):
- temperature: mean daily temperature over the crop's own active season (sowing to harvest, from the crop calendar;
  winter crops from 1 March, as they rest hardened over winter);
- rainfall: mean yearly rain;
- frost: share of years in which the coldest day falls below the crop's killing temperature while it can be killed:
  spring crops from emergence to a month before harvest, winter cereals from heading (hardened plants survive earlier);
- texture: the field's soil (silt-rich loess = medium) against the textures the crop takes.
Fit = min(temperature, rainfall) x (1 - frost share) x texture factor, 0..1. pH is in the table but not yet used:
the app has no pH per field.
`crop_requirements` links each row to the crop keys of the rotation model (e.g. "winter_barley spring_barley").
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from data import CONTENT, fields, strategies, table

CSV = CONTENT / "ecocrop_south_germany.csv"
TEXTURE_MISS = 0.8  # a texture the crop does not list: fit x 0.8
RIPE_DAYS = 30      # the last weeks before harvest: a frost no longer kills the crop


@st.cache_data(show_spinner=False)
def crops_table() -> pd.DataFrame | None:
    return pd.read_csv(CSV) if CSV.exists() else None


def row_for(crop_key):
    """The EcoCrop row that serves one model crop key, or None."""
    t = crops_table()
    if t is None:
        return None
    hit = t[t.crop_requirements.fillna("").str.split().apply(lambda keys: crop_key in keys)]
    return hit.iloc[0] if len(hit) else None


def _trap(x, lo, olo, ohi, hi):
    if any(pd.isna(v) for v in (x, lo, olo, ohi, hi)):
        return 1.0
    if x < lo or x > hi:
        return 0.0
    if olo <= x <= ohi:
        return 1.0
    return float((x - lo) / (olo - lo)) if x < olo else float((hi - x) / (hi - ohi))


SPRING = 60  # 1 March: winter crops grow actively from here; before that they rest hardened, so EcoCrop's growth
             # temperatures and killing temperature apply from spring to harvest only


def _season_days(d, winter):
    """Day-of-year mask of a crop's active season: sowing to harvest; for winter crops 1 March to harvest."""
    doy = np.arange(1, 366)
    return (doy >= SPRING) & (doy <= d["harvest"]) if winter else (doy >= d["sow"]) & (doy <= d["harvest"])


@st.cache_data(show_spinner=False)
def fit(fid: str, crop_key: str, winter: bool) -> dict:
    """{"fit": 0..1, "temp", "rain", "frost", "texture", "name"} for one crop on one field (fit 1 when no row)."""
    row = row_for(crop_key)
    dates = strategies()["crop_dates"].get(crop_key) or {"sow": 105, "emerge": 130, "canopy": 165, "harvest": 255}
    if row is None:
        return {"fit": 1.0, "name": None}
    d = table("daily")
    d = d[(d.field == fid) & d.date.dt.year.between(1991, 2024)]
    tcol = next((c for c in ("t_mean_power", "t_mean_dwd", "t_mean_era5") if c in d), None)
    pcol = next((c for c in ("p_power", "p_imerg", "p_dwd") if c in d), None)
    mask = _season_days(dates, winter)[d.date.dt.day_of_year.clip(upper=365).to_numpy() - 1]
    season = d[mask]
    temp = float(season[tcol].mean()) if tcol else np.nan
    rain = float(d.groupby(d.date.dt.year)[pcol].sum().mean()) if pcol else np.nan
    cold_col = next((c for c in ("t_min_power", "t_min_dwd") if c in d), tcol)  # daily minimum where we have it
    # frost harms winter cereals from heading on (the calendar's canopy date), hardened plants survive earlier frosts
    doy = d.date.dt.day_of_year.clip(upper=365)
    # spring crops: from emergence to a month before harvest (frost before emergence or on the ripe crop kills nothing)
    in_frost = ((doy >= dates["canopy"]) & (doy <= dates["harvest"]) if winter
                else (doy >= dates["emerge"]) & (doy <= dates["harvest"] - RIPE_DAYS))
    frost_days = d[in_frost]
    coldest = frost_days.groupby(frost_days.date.dt.year)[cold_col].min() if cold_col else pd.Series(dtype=float)
    frost = float((coldest < row.kill_temp).mean()) if len(coldest) and not pd.isna(row.kill_temp) else 0.0
    silt = fields()[fid].get("silt_pct")
    soil = "medium" if silt is None or silt >= 40 else "light"
    texture = 1.0 if pd.isna(row.texture) or soil in str(row.texture) else TEXTURE_MISS
    t_fit = _trap(temp, row.t_min, row.t_opt_min, row.t_opt_max, row.t_max)
    r_fit = _trap(rain, row.rain_min, row.rain_opt_min, row.rain_opt_max, row.rain_max)
    return {"fit": round(min(t_fit, r_fit) * (1 - frost) * texture, 2), "temp": round(temp, 1), "rain": round(rain),
            "frost": round(frost, 2), "texture": texture, "t_fit": round(t_fit, 2), "r_fit": round(r_fit, 2),
            "name": row["name"], "name_de": row.get("name_de")}
