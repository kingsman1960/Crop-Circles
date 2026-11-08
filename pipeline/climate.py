"""Weather, soil moisture and NDVI per field.

Outputs: daily.parquet, indicators.parquet, scenarios.parquet, soilmoisture.parquet, ndvi.parquet (when MODIS is downloaded).
Indicator definitions follow PRD §7; thresholds are screening values (see content/indicators.toml).
"""
import io

import numpy as np
import pandas as pd

from pipeline.common import CONFIG, FIELDS, PROC, RAW, check, out

START, END = CONFIG["period"]["start"], CONFIG["period"]["end"]
SCENARIO_YEARS = (2005, 2024)  # recent 20 full years for the scenario means


def read_power(fid):
    txt = (RAW / "nasa_power" / f"{fid}_daily.csv").read_text()
    df = pd.read_csv(io.StringIO(txt.split("-END HEADER-")[1]), na_values=[-999])
    date = pd.to_datetime(df.YEAR.astype(str)) + pd.to_timedelta(df.DOY - 1, unit="D")
    return pd.DataFrame({
        "t_max_power": df.T2M_MAX.values, "t_min_power": df.T2M_MIN.values, "t_mean_power": df.T2M.values,
        "p_power": df.PRECTOTCORR.values, "rad_power": df.ALLSKY_SFC_SW_DWN.values,
        "gwettop": df.GWETTOP.values, "gwetroot": df.GWETROOT.values}, index=date)


def read_imerg(fid):
    lines = (RAW / "gpm_imerg" / f"{fid}_daily.csv").read_text().splitlines()
    head = lines.index("") + 1  # two Giovanni header styles; both end with a blank line
    df = pd.read_csv(io.StringIO("\n".join(lines[head:])), na_values=[-9999.9])
    return pd.Series(df.iloc[:, 1].values, index=pd.to_datetime(df.iloc[:, 0]), name="p_imerg")


def read_dwd(sid):
    files = sorted((RAW / "dwd_climate" / sid).glob("produkt_klima_tag_*.txt"))  # historical file sorts first
    df = pd.concat(pd.read_csv(f, sep=";", skipinitialspace=True, na_values=[-999]) for f in files)
    df.columns = df.columns.str.strip()
    df = df.drop_duplicates("MESS_DATUM")  # historical (quality-controlled) wins over recent
    return df.set_index(pd.to_datetime(df.MESS_DATUM.astype(str), format="%Y%m%d"))[["TXK", "TNK", "TMK", "RSK"]]


def et0_hargreaves(tmax, tmin, tmean, lat):
    """FAO-56 eq. 52 with extraterrestrial radiation Ra from eq. 21 (mm/day)."""
    j = tmax.index.day_of_year.values
    phi = np.radians(lat)
    dr = 1 + 0.033 * np.cos(2 * np.pi * j / 365)
    dec = 0.409 * np.sin(2 * np.pi * j / 365 - 1.39)
    ws = np.arccos(-np.tan(phi) * np.tan(dec))
    ra = 24 * 60 / np.pi * 0.082 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
    return 0.0023 * 0.408 * ra * (tmean + 17.8) * np.sqrt((tmax - tmin).clip(lower=0))


def phase_windows():
    """Per-year DOY of the phenology windows used by the indicators (regional median, overall median if missing)."""
    ph = pd.read_parquet(PROC / "phenology.parquet")
    years = range(int(START[:4]), int(END[:4]) + 1)

    def doy(crop, phase_id):
        s = ph[(ph.crop == crop) & (ph.phase_id == phase_id)].set_index("year").doy
        return s.reindex(years).fillna(s.median())

    return pd.DataFrame({"heading": doy("winter_wheat", 18), "milk": doy("winter_wheat", 19),
                         "beet_emergence": doy("sugar_beet", 12), "beet_closed": doy("sugar_beet", 13)})


def dry_spells(p, min_len=14):
    """Runs of >= min_len days with P < 1 mm -> DataFrame(start, length)."""
    dry = p < 1
    run = (dry != dry.shift()).cumsum()[dry]
    runs = pd.DataFrame({"start": run.index.to_series().groupby(run.values).min(), "length": run.groupby(run.values).size()})
    return runs[runs.length >= min_len]


def indicators(d, win):
    """Yearly indicators from a daily frame with columns tmax/tmin/tmean (optional), p, et0 (optional)."""
    y, m, j = d.index.year, d.index.month, d.index.day_of_year
    res = {}
    if "tmax" in d:
        w = win.reindex(y)
        hot = d.tmax >= 30
        res["heat_days"] = hot.groupby(y).sum()
        res["heat_days_heading"] = (hot & (j >= w.heading.values) & (j <= w.milk.values)).groupby(y).sum()
        res["frost_after_emergence"] = ((d.tmin <= -2) & (j >= w.beet_emergence.values) & (j <= w.beet_closed.values)).groupby(y).sum()
        res["t_mean"] = d.tmean.groupby(y).mean()
    runs = dry_spells(d.p)
    ry, rm = runs.start.dt.year, runs.start.dt.month
    res["dry_spells_spring"] = runs[rm.between(3, 5)].groupby(ry).size()
    res["dry_spells_summer"] = runs[rm.between(6, 8)].groupby(ry).size()
    res["heavy_rain_days"] = ((d.p >= 20) & m.isin([5, 6, 7])).groupby(y).sum()
    res["precip"] = d.p.groupby(y).sum()
    if "et0" in d:
        cwb = d.p - d.et0
        res["cwb_year"] = cwb.groupby(y).sum()
        res["cwb_spring"] = cwb[m.isin([3, 4, 5])].groupby(y[m.isin([3, 4, 5])]).sum()
        res["cwb_summer"] = cwb[m.isin([6, 7, 8])].groupby(y[m.isin([6, 7, 8])]).sum()
    full = d.notna().all(axis=1).groupby(y).sum() >= 360  # complete years only
    out_ = pd.DataFrame(res).reindex(full.index)
    out_[["dry_spells_spring", "dry_spells_summer"]] = out_[["dry_spells_spring", "dry_spells_summer"]].fillna(0)
    return out_[full]


SOURCES = {  # source -> column mapping onto tmax/tmin/tmean/p/et0
    "POWER": dict(tmax="t_max_power", tmin="t_min_power", tmean="t_mean_power", p="p_power", et0="et0_power"),
    "IMERG": dict(p="p_imerg", et0="et0_power"),
    "DWD": dict(tmax="t_max_dwd", tmin="t_min_dwd", tmean="t_mean_dwd", p="p_dwd", et0="et0_dwd"),
}


def as_source(daily, src):
    cols = SOURCES[src]
    return daily[list(cols.values())].rename(columns={v: k for k, v in cols.items()})


def anomaly(s):
    """z-score against a 31-day smoothed day-of-year climatology of the same series."""
    s = s.dropna()
    j = np.minimum(s.index.day_of_year.values, 365)
    clim = s.groupby(j).agg(["mean", "std"]).reindex(range(1, 366))
    clim = pd.concat([clim.iloc[-15:], clim, clim.iloc[:15]]).rolling(31, center=True, min_periods=5).mean().iloc[15:-15]
    return pd.Series((s.values - clim["mean"].values[j - 1]) / clim["std"].values[j - 1], index=s.index)


def soil_moisture(fid, f, daily):
    series = {("POWER GWETTOP", "0–1"): daily.gwettop, ("POWER GWETROOT", "0–1"): daily.gwetroot}
    # C3S (2025 ->) continues CCI v09.2 (-> 2024) with the same algorithm; joined so the anomaly has one climatology.
    # ponytail: version step at 2024/2025 not corrected – compare the two once an overlap year is available.
    sat = [pd.read_csv(p, parse_dates=["date"]) for p in (RAW / "esa_cci_sm" / "cci_sm_combined_v09.2_daily.csv",
                                                           RAW / "c3s_sm" / "c3s_sm_combined_daily.csv") if p.exists()]
    if sat:
        df = pd.concat(sat)
        df = df[(abs(df.lat - f["lat"]) <= 0.125) & (abs(df.lon - f["lon"]) <= 0.125) & (df.flag == 0) & (df.sm > -9999)]
        series[("ESA CCI + C3S" if len(sat) == 2 else "ESA CCI", "m³/m³")] = df.set_index("date").sm
    smap = RAW / "smap" / f"{fid}.csv"
    if smap.exists():
        df = pd.read_csv(smap, parse_dates=["date"]).set_index("date")
        am = df.sm_am.where((df.qual_am == 0) & (df.sm_am > -9999))
        pm = df.sm_pm.where((df.qual_pm == 0) & (df.sm_pm > -9999))
        series[("SMAP", "m³/m³")] = pd.concat([am, pm], axis=1).mean(axis=1)
    rows = [pd.DataFrame({"field": fid, "source": src, "unit": unit, "sm": s.dropna(), "anomaly": anomaly(s)})
            for (src, unit), s in series.items()]
    return pd.concat(rows).rename_axis("date").reset_index()


def ndvi(fid):
    frames = []
    for prod in ["MOD13Q1", "MYD13Q1"]:
        path = RAW / "modis_ndvi" / f"{fid}_{prod}.csv"
        if path.exists():
            df = pd.read_csv(path, parse_dates=["date"])
            df = df[df.reliability.isin([0, 1])]  # good + marginal
            frames.append(df.groupby("date").agg(ndvi=("ndvi", "mean"), bare=("ndvi", lambda v: (v < 0.3).mean()),
                                                  n_pixels=("pixel_id", "nunique"))
                            .reset_index().assign(field=fid, product=prod))
    return pd.concat(frames) if frames else None


def ecostress(fid):
    """ECOSTRESS at the field centroid (70 m): surface temperature (°C) and evaporative stress index, clear daytime passes.
    The ISS passes at changing hours; the Date column carries the acquisition time, so night passes are dropped."""
    path = RAW / "ecostress" / f"{fid}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    when = pd.to_datetime(df.Date, utc=True, errors="coerce").dt.tz_localize(None)  # "2018-07-30 17:58:26 UTC"
    col = lambda name: df[name] if name in df else pd.Series(np.nan, index=df.index)
    lst = col("ECO_L2T_LSTE_002_LST").where((col("ECO_L2T_LSTE_002_cloud").fillna(0) == 0) & (col("ECO_L2T_LSTE_002_LST") > 0)) - 273.15
    esi = col("ECO_L4T_ESI_002_ESI").where((col("ECO_L4T_ESI_002_cloud").fillna(0) == 0) & col("ECO_L4T_ESI_002_ESI").between(0, 1))
    out = pd.DataFrame({"field": fid, "time": when, "lst": lst, "esi": esi}).dropna(subset=["time"])
    out = out.dropna(subset=["lst", "esi"], how="all")
    out = out.groupby(["field", "time"], as_index=False).mean()  # a pass can sit on two UTM tiles: one row per pass
    hour = (out.time + pd.Timedelta(hours=1)).dt.hour  # UTC -> CET; enough for a day / night split
    return out[hour.between(9, 17)]


def main():
    stations = pd.read_csv(RAW / "dwd_climate" / "stations_selected.csv", dtype={"station_id": str})
    dwd = {sid: read_dwd(sid) for sid in stations.station_id}
    names = dict(zip(stations.station_id, stations.name))
    win = phase_windows()
    daily_all, ind_all, scen_all, sm_all, ndvi_all, eco_all = [], [], [], [], [], []
    for f in FIELDS:
        fid = f["id"]
        d = read_power(fid).join(read_imerg(fid))
        # DWD: per variable, the nearest station with a valid value that day
        order = stations.sort_values(f"dist_{fid}_km").station_id
        for var, col in [("TXK", "t_max_dwd"), ("TNK", "t_min_dwd"), ("TMK", "t_mean_dwd"), ("RSK", "p_dwd")]:
            wide = pd.concat({sid: dwd[sid][var] for sid in order}, axis=1, sort=True).reindex(d.index)
            d[col] = wide.bfill(axis=1).iloc[:, 0]
            if var == "TXK":
                d["dwd_station"] = wide.notna().idxmax(axis=1).map(names).where(wide.notna().any(axis=1))
        d["et0_power"] = et0_hargreaves(d.t_max_power, d.t_min_power, d.t_mean_power, f["lat"])
        d["et0_dwd"] = et0_hargreaves(d.t_max_dwd, d.t_min_dwd, d.t_mean_dwd, f["lat"])
        d = d.loc[START:END]
        daily_all.append(d.rename_axis("date").reset_index().assign(field=fid))

        for src in SOURCES:
            ind = indicators(as_source(d, src), win)
            ind_all.append(ind.rename_axis("year").reset_index()
                           .melt(id_vars="year", var_name="indicator").dropna().assign(field=fid, source=src))

        base = as_source(d, "POWER").loc[str(SCENARIO_YEARS[0]):str(SCENARIO_YEARS[1])]
        spring = base.index.month.isin([3, 4, 5])
        for dt in (0, 1, 2):
            for ps in (1.0, 0.9, 0.8):
                s = base.copy()
                s[["tmax", "tmin", "tmean"]] += dt
                s.loc[spring, "p"] *= ps
                s["et0"] = et0_hargreaves(s.tmax, s.tmin, s.tmean, f["lat"])
                mean = indicators(s, win).mean()
                scen_all.append(pd.DataFrame({"field": fid, "dT": dt, "p_spring": ps,
                                              "indicator": mean.index, "value": mean.values}))

        sm_all.append(soil_moisture(fid, f, d))
        if (n := ndvi(fid)) is not None:
            ndvi_all.append(n)
        if (e := ecostress(fid)) is not None:
            eco_all.append(e)

    for name, frames, date_col in [("daily.parquet", daily_all, "date"), ("indicators.parquet", ind_all, "year"),
                                   ("scenarios.parquet", scen_all, None), ("soilmoisture.parquet", sm_all, "date"),
                                   ("ndvi.parquet", ndvi_all, "date"), ("ecostress.parquet", eco_all, "time")]:
        if not frames:
            print(f"  {name}: skipped (not downloaded yet)")
            continue
        df = pd.concat(frames, ignore_index=True)
        df.to_parquet(out(name), index=False)
        check(name, df, date_col)


if __name__ == "__main__":
    main()
