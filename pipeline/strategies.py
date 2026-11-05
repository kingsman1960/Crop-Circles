"""Rotation strategies S0-S4 -> strategies.json: per-field scores, field facts and a monthly bare-soil calendar.

Erosion and water scores come from a daily rotation model (content/crops.toml) and are relative to S0 on the
same field; planthopper, nitrogen and income are rule scores from content/strategies.toml.
"""
import json
import tomllib
from datetime import date

import numpy as np
import pandas as pd

from pipeline.common import CONTENT, FIELDS, PROC, out

RECENT = (2015, 2024)  # last 10 full years with IMERG
CROPS = tomllib.loads((CONTENT / "crops.toml").read_text(encoding="utf-8"))
STRATS = tomllib.loads((CONTENT / "strategies.toml").read_text(encoding="utf-8"))
M, COVER = CROPS["model"], CROPS["cover_crop"]


def crop_dates(ph):
    """crop key -> {sow, emerge, canopy, harvest} DOY: DWD regional median, else the literature value."""
    res = {}
    for key, c in CROPS.items():
        if "dwd" in c or "doy" in c:
            d = dict(c.get("doy", {}))
            for phase, pid in c.get("dwd", {}).items():
                d[phase] = int(round(ph[(ph.crop == c["dwd_crop"]) & (ph.phase_id == pid)].doy.median()))
            res[key] = d
    return res


def rotation(s, dates):
    """Daily bareness (0 covered .. 1 bare), Kc and state label over one rotation cycle of n x 365 days."""
    seq = s["sequence"]
    L = len(seq) * 365
    bare, kc, state = np.full(L, M["bare"]), np.full(L, M["kc_bare"]), np.full(L, "bare", dtype=object)
    span = lambda a, b: np.arange(a, b) % L  # cyclic day indexes
    t = []  # absolute sow/emerge/canopy/harvest per crop; winter crops are sown in the previous year
    for k, key in enumerate(seq):
        d, prev = dates[key], k - 1 if CROPS[key]["winter"] else k
        t.append({"key": key, "sow": prev * 365 + d["sow"], "emerge": prev * 365 + d["emerge"],
                  "canopy": k * 365 + d["canopy"], "harvest": k * 365 + d["harvest"]})
    for k, c in enumerate(t):
        prev_h = t[k - 1]["harvest"] - (L if k == 0 else 0)
        if (late := prev_h + 7 - c["sow"]) > 0:  # sowing waits for the previous harvest (e.g. wheat after maize)
            c["sow"] += late
            c["emerge"] += late
        stubble = CROPS[t[k - 1]["key"]].get("stubble", M["bare"])
        bare[span(prev_h, c["sow"])] = stubble
        covered = False
        if c["key"] in s["cover_before"]:
            cs = prev_h + COVER["delay_days"]
            ce = cs + COVER["establish_days"]
            if ce < c["sow"]:
                covered = True
                bare[span(cs, ce)] = np.linspace(stubble, COVER["bareness"], ce - cs)
                bare[span(ce, c["sow"])] = COVER["bareness"]
                kc[span(cs, c["sow"])] = COVER["kc"]
                state[span(cs, c["sow"])] = "cover_crop"
        b0 = M["mulch_bareness"] if s["mulch"] and covered and not CROPS[c["key"]]["winter"] else M["bare"]
        crop = CROPS[c["key"]]
        bare[span(c["sow"], c["emerge"])] = b0
        frac = np.linspace(0, 1, c["canopy"] - c["emerge"])  # crop cover from emergence to canopy closure
        bare[span(c["emerge"], c["canopy"])] = b0 + (M["canopy_bareness"] - b0) * frac
        kc[span(c["emerge"], c["canopy"])] = M["kc_bare"] + (crop["kc_mid"] - M["kc_bare"]) * frac
        bare[span(c["canopy"], c["harvest"])] = M["canopy_bareness"]
        kc[span(c["canopy"], c["harvest"])] = crop["kc_mid"]
        sen = min(M["senescence_days"], c["harvest"] - c["canopy"])
        kc[span(c["harvest"] - sen, c["harvest"])] = np.linspace(crop["kc_mid"], crop["kc_end"], sen)
        state[span(c["sow"], c["harvest"])] = c["key"]
    return bare, kc, state


def climate_weights(d):
    """Per day of year: erosive rain (heavy-rain days in the storm season, IMERG), ET0 and P (mm/day), 2001-2024 means."""
    d = d[(d.date.dt.year >= 2001) & (d.date.dt.year <= RECENT[1])]
    m = d.date.dt.month
    days = d.groupby(m).date.count()
    monthly = pd.DataFrame({
        "erosive": d.p_imerg.where((d.p_imerg >= M["erosive_mm"]) & m.isin(M["erosive_months"]), 0).groupby(m).sum() / days,
        "et0": d.et0_power.groupby(m).mean(), "p": d.p_imerg.groupby(m).mean()})
    doy_month = pd.date_range("2001-01-01", periods=365).month  # non-leap year
    return monthly.reindex(doy_month).reset_index(drop=True), monthly


def months_table(bare, state, n):
    """Monthly summary per rotation year: dominant state and mean bareness."""
    month = np.tile(pd.date_range("2001-01-01", periods=365).month, n)
    year = np.repeat(np.arange(1, n + 1), 365)
    df = pd.DataFrame({"year": year, "month": month, "bare": bare, "state": state})
    g = df.groupby(["year", "month"])
    return (g.bare.mean().round(2).to_frame().join(g.state.agg(lambda x: x.mode()[0]))
            .reset_index().to_dict(orient="records"))


def field_facts(fid, props, ind, daily, ph):
    lo, hi = RECENT
    r = ind[(ind.field == fid) & ind.year.between(lo, hi)]
    val = lambda src, key: r[(r.source == src) & (r.indicator == key)].set_index("year").value
    d = daily[(daily.field == fid) & daily.date.dt.year.between(lo, hi)]
    yr = d.date.dt.year
    win = lambda pid: ph[(ph.crop == "sugar_beet") & (ph.phase_id == pid)].set_index("year").doy.reindex(yr).values
    open_rows = (d.date.dt.day_of_year.values >= win(10)) & (d.date.dt.day_of_year.values <= win(13))
    k_rain = int((d.p_imerg.where(open_rows) >= 20).groupby(yr).any().sum())
    heat = ind[(ind.field == fid) & (ind.source == "DWD") & (ind.indicator == "heat_days")]
    trend = np.polyfit(heat.year, heat.value, 1)[0] * 10
    station = d.dwd_station.mode()[0]
    n_heat = int((val("DWD", "heat_days_heading") > 0).sum())
    n_dry = int((val("IMERG", "dry_spells_summer") > 0).sum())
    n_frost = int((val("DWD", "frost_after_emergence") > 0).sum())
    cwb = -val("IMERG", "cwb_summer").mean()
    # numbers only: the app turns them into sentences in the reader's language (app/locales/*.toml, "fact.*")
    return {
        "beet_wheat": {"source": "thuenen", "share": props["beet_to_wheat"], "region": props["bbox_beet_to_wheat"]},
        "open_rows_rain": {"source": "imerg_phenology", "n": k_rain},
        "heat_heading": {"source": "dwd_phenology", "station": station, "n": n_heat, "trend": round(float(trend), 1)},
        "summer_dry": {"source": "imerg_power", "n": n_dry, "cwb": round(float(cwb))},
        "frost": {"source": "dwd_phenology", "station": station, "n": n_frost},
        "soil": {"source": "bk50_nasadem", "k_class": props["k_class"], "slope": props["slope_mean_pct"],
                 "nfk": props["nfk_mm"]},
    }


def main():
    ph = pd.read_parquet(PROC / "phenology.parquet")
    daily = pd.read_parquet(PROC / "daily.parquet")
    ind = pd.read_parquet(PROC / "indicators.parquet")
    props = {f["id"]: f["properties"] for f in json.loads((PROC / "fields.geojson").read_text(encoding="utf-8"))["features"]}
    dates = crop_dates(ph)
    result = {"generated": date.today().isoformat(), "recent_years": RECENT, "crop_dates": dates, "fields": {}}
    for f in FIELDS:
        fid, p = f["id"], props[f["id"]]
        w, monthly = climate_weights(daily[daily.field == fid])
        deficit = monthly.index[monthly.p < monthly.et0].tolist()
        dry_day = w.index.isin([i for i, m in enumerate(pd.date_range("2001-01-01", periods=365).month) if m in deficit])
        res = {}
        for s in STRATS["strategy"]:
            n = len(s["sequence"])
            bare, kc, state = rotation(s, dates)
            res[s["id"]] = {
                "erosion_index": float(p["erosion_ks"] * (bare * np.tile(w.erosive, n)).sum() / n),
                "water_mm": float((kc * np.tile(w.et0, n) * np.tile(dry_day, n)).sum() / n),
                "months": months_table(bare, state, n),
                "literature_dates": [c for c in s["sequence"] if "dwd" not in CROPS[c]],
            }
        base = res["S0"]
        f_scale = min(p["erosion_ks"] / 0.55, 1)  # differences matter less on flat, less erodible fields
        for s in STRATS["strategy"]:
            r = res[s["id"]]
            r["erosion_rel"] = r["erosion_index"] / base["erosion_index"]
            r["water_rel"] = r["water_mm"] / base["water_mm"]
            est = "high" if r["literature_dates"] else "medium"
            r["scores"] = {
                "erosion": {"score": round(float(np.clip(3 + 4 * f_scale * (1 - r["erosion_rel"]), 1, 5)), 1),
                            "uncertainty": est, "basis": "model",
                            "rel": round(r["erosion_rel"], 3)},
                "water": {"score": round(float(np.clip(3 - 10 * (r["water_rel"] - 1), 1, 5)), 1),
                          "uncertainty": est, "basis": "model",
                          "rel": round(r["water_rel"], 3), "months": deficit},
                **{k: {"score": v["score"], "uncertainty": v["uncertainty"], "basis": "rule"}  # note: from content
                   for k, v in s["scores"].items()},
            }
        result["fields"][fid] = {"deficit_months": deficit, "strategies": res,
                                 "facts": field_facts(fid, p, ind, daily, ph)}
        print(f"  {fid}: " + ", ".join(f"{k} ero {v['erosion_rel']:.2f} wat {v['water_rel']:.2f}" for k, v in res.items()))
    out("strategies.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  strategies.json: {len(result['fields'])} fields x {len(STRATS['strategy'])} strategies")


if __name__ == "__main__":
    main()
