import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

import accounts
import copilot
from data import (CROPS, GREY, GREY_LIGHT, HUE, INK, POS, chart, content, crop_group, crop_names, crop_scale, field_picker, footer,
                  FLIGHT_M, PH_LEVEL, from_space, geojson, header, kpis, layer, legend, neighbourhood, ph_levels, plan, planner_weights, pressure, region_test,
                  rank_options, rgb, source_line, strategies, table, takeaway, tip)
from i18n import day, listing, months, num, pct, t, tn
from plain import ci_ten, fraction, level, of_ten, ten, weeks

SOURCES = ("POWER", "IMERG", "DWD")
RECENT, EARLY = (2015, 2024), (1981, 2010)
ind_meta, texts = content("indicators"), content("plain")
names = crop_names()
BEET, WHEAT = names[1402], names[1101]


def smart(v):
    """Small numbers keep one decimal so 0.3 does not read as 0."""
    return num(v, 1) if abs(v) < 10 else num(v)


def tone(m, change):
    """Colour says good or bad, not up or down; no change is grey."""
    if abs(change) < 0.05:
        return None
    return "good" if (change < 0) == (m["better"] == "lower") else "bad"


def now_vs_years(s, days=14):
    """Mean of the last `days` days, and how many earlier years were wetter in the same days (of how many)."""
    end = s.index.max()
    mean = lambda y: s[(s.index > end - pd.DateOffset(years=y) - pd.Timedelta(days=days))
                       & (s.index <= end - pd.DateOffset(years=y))].mean()
    past = pd.Series([mean(y) for y in range(1, end.year - s.index.min().year + 1)]).dropna()
    return end, mean(0), int((past > mean(0)).sum()), len(past)


picker = st.container()
fid, p = field_picker(picker)
place = p["label"].removeprefix("Near ")
all_parcels = [f for f in geojson("parcels")["features"] if f["properties"]["field"] == fid]
years = sorted({f["properties"]["year"] for f in all_parcels})  # FIONA declarations, 2022 → newest
parcels = [f for f in all_parcels if f["properties"]["year"] == years[-1]]
facts = strategies()["fields"][fid]["facts"]
ind = table("indicators")
ind = ind[ind.field == fid]
daily = table("daily")
daily = daily[daily.field == fid]
title, sub = t("field.title", id=fid, place=place), t("field.sub", ha=num(p["area_ha"]), n=len(parcels))
side = header(title, sub)
if accounts.my_parcels():  # parcels this farmer added from the region map: their crop history now, the rest later
    from data import landscape
    par, _, summary = landscape()
    de = crop_names("de")
    fiona = {int(k): v for k, v in summary["legends"].get("fiona", {}).items()}  # NC code -> declared crop (German)
    declared = lambda r, y: fiona.get(int(r[f"f{y}"])) if f"f{y}" in r and r[f"f{y}"] > 0 else None
    with st.container(key="card_parcels"):
        st.markdown(t("field.parcels.title", n=len(accounts.my_parcels())))
        rows = ""
        for pid in accounts.my_parcels():
            if pid not in par.index:
                continue
            r = par.loc[pid]
            chips = "".join(f'<span class="cc-chip" style="--c:{CROPS[crop_group(declared(r, y) or de.get(int(r[f"c{y}"]), ""))]}">'
                            f'<i>{y}</i>{declared(r, y) or names.get(int(r[f"c{y}"]), "–")}</span>' for y in range(2020, 2026))
            rows += f'<tr><td><b>{pid}</b><span class="g">{num(r.area_ha, 1)} ha</span></td><td><div class="cc-chips">{chips}</div></td></tr>'
        st.html(f'<table class="cc-table"><tbody>{rows}</tbody></table>')
        st.caption(t("field.parcels.note"))
report = []  # (heading, paragraphs) for the take-away page

# --- the four risks, in words ------------------------------------------------
nur, beet = plan(2025, FLIGHT_M, 0.2, "balanced", planner_weights())
nb = neighbourhood(fid, nur, FLIGHT_M)
rank = (pressure(2025, FLIGHT_M)[1].pressure < nb["total"]).mean()
ph_level = PH_LEVEL(rank)
levels = set(ph_levels(fid, 2025).values())
order = ["low", "medium", "high"]
lo, hi = min(levels, key=order.index), max(levels, key=order.index)
own = nb["own"] / max(nb["total"], 1e-9)
rt = region_test()  # the region-wide test: nurseries touching this block, and what that meant for beet across the region
edge, eff = rt.get("demo_fields", {}).get(fid), rt.get("index", {}).get("ndre")
edge_text = ("" if not edge else t("field.ph.edge_none", season=edge["season"]) if edge["n"] == 0
             else tn("field.ph.edge", edge["n"], ha=num(edge["ha"], 1), season=edge["season"]))
edge_text += t("field.ph.evidence", x=num(abs(eff["adjacent_coef"]), 2), n=num(eff["n"])) if eff else ""
ph_text = (t("field.ph.main", rank=of_ten(rank), near=num(nb["near_ha"]), km=num(FLIGHT_M / 1000, 1))
           + (t("field.ph.own_none") if own < 0.05 else t("field.ph.own_some", own=pct(own)))
           + edge_text
           + (t("field.ph.range", lo=t("plain.level." + lo), hi=t("plain.level." + hi)) if lo != hi else "")
           + t("field.ph.switch", fraction=fraction(1 - nb["after"] / max(nb["total"], 1e-9))))
slope = p["slope_mean_pct"]
er_text = t("field.erosion", slope=num(slope), drop=num(slope), n=facts["open_rows_rain"]["n"]) + ci_ten(facts["open_rows_rain"]["n"])

june_use = daily[daily.date.dt.month == 6].et0_power.mean() * 1.1  # a closed crop in June uses about 1.1 x ET0 (FAO-56)
store = p.get("nfk_mid_mm") or 140
n_dry = facts["summer_dry"]["n"]
dry_level = "high" if n_dry >= 5 else "medium" if n_dry >= 3 else "low"
dry_text = t("field.dry", store=num(store), weeks=weeks(store / june_use), n=n_dry, cwb=num(facts["summer_dry"]["cwb"])) + ci_ten(n_dry)

hot = ind[(ind.source == "DWD") & (ind.indicator == "heat_days")]
hot_now, hot_then = hot[hot.year.between(*RECENT)].value.mean(), hot[hot.year.between(*EARLY)].value.mean()
n_heat = facts["heat_heading"]["n"]
heat_level = "high" if n_heat >= 8 else "medium" if n_heat >= 5 else "low"  # >= 6 was "high" for every field-year 2011-2025
heat_text = t("field.heat", now=num(hot_now), then=num(hot_then), station=facts["heat_heading"]["station"], n=n_heat) + ci_ten(n_heat)

cards = [("planthopper", ph_level, ph_text, rank * 10), ("erosion", p["erosion_class"], er_text, facts["open_rows_rain"]["n"]),
         ("dry", dry_level, dry_text, n_dry), ("heat", heat_level, heat_text, n_heat)]
for row in (cards[:2], cards[2:]):
    for col, (key, lvl, text, n) in zip(st.columns(2, gap="medium"), row):
        with col.container(key=f"card_risk_{key}"):
            tx = texts[key]
            st.html(f'<div class="cc-risk"><div class="cc-risk-head"><h3>{tx["title"]}</h3><span class="cc-risk-gauge">{ten(n)}{level(lvl)}</span></div>'
                    f'<p class="cc-risk-text">{text}</p><p class="cc-note">{tx["what"]}</p>'
                    f'<p class="cc-risk-help"><b>{t("field.what_helps")}</b> {tx["helps"]}</p>'
                    f'<p class="cc-note" style="margin:0">{t("field.source")} {tx["source"]}</p></div>')
st.caption(t("field.levels_note"))
report.append((t("field.report.risks"), [f"<b>{texts[k]['title']}: {t('plain.level.' + lvl)}.</b> {text} "
                                         f"<i>{t('field.what_helps')}</i> {texts[k]['helps']}" for k, lvl, text, _ in cards]))

# --- what fits best after this year's beet ----------------------------------
order, total, options = rank_options(fid)
best = options[order[0]]
crop_cal, crops = content("crops"), table("crops")
st.space("small")
with st.container(key="card_best"):
    a, b = st.columns([3, 1], vertical_alignment="center")
    seq = " → ".join(crop_cal[c]["label"] for c in best["sequence"])
    a.html(f'<h3 style="margin:0 0 8px">{t("field.best.kicker")}</h3>'
           f'<p style="margin:0"><b>{best["name"]}: {seq}</b> {best["why"]}</p>')
    if b.button(t("field.best.button"), type="primary", width="stretch"):
        st.switch_page("views/strategies.py")
report.append((t("field.best.kicker"), [f"<b>{best['name']}: {seq}</b>", best["why"]]))

# --- the field on the map ---------------------------------------------------
st.space("small")
left, right = st.columns([1.6, 1], gap="large")
with left:
    st.subheader(t("field.map.title"))
    row = st.container(horizontal=True, vertical_alignment="center", gap="medium")
    show_erosion = row.toggle(t("field.map.erosion_toggle"), key="field_erosion", persist_state="session")
    yr = row.segmented_control(t("field.map.year"), years, default=years[-1], required=True, key="map_year",
                               label_visibility="collapsed", width="content")
    parcels_y = [f for f in all_parcels if f["properties"]["year"] == yr]
    for f in parcels_y:
        g = crop_group(f["properties"]["crop"])
        f["properties"] |= {"rgb": rgb(CROPS[g]), "group": t("field.map.group." + g)}
    groups = [g for g in CROPS if any(crop_group(f["properties"]["crop"]) == g for f in parcels_y)]
    layers = [pdk.Layer("BitmapLayer", image=layer("erosion_ks")[0], bounds=layer("erosion_ks")[1]["bounds"],
                        opacity=0.8)] if show_erosion else []
    outline = {"type": "FeatureCollection", "features": [f for f in geojson("fields")["features"] if f["id"] == fid]}
    layers += [pdk.Layer("GeoJsonLayer", data={"type": "FeatureCollection", "features": parcels_y}, pickable=True,
                         filled=not show_erosion, get_fill_color="properties.rgb", stroked=True,
                         get_line_color=[255, 255, 255], line_width_min_pixels=1),
               pdk.Layer("GeoJsonLayer", data=outline, filled=False, stroked=True, get_line_color=[22, 33, 62],
                         line_width_min_pixels=2)]
    st.pydeck_chart(pdk.Deck(map_style=None, layers=layers, tooltip={"text": t("field.map.tooltip", group="{group}", crop="{crop}", ha="{ha}", year=yr)},
                             initial_view_state=pdk.ViewState(latitude=p["lat"], longitude=p["lon"], zoom=14.4)),
                    height=430)
    legend([(CROPS[g], t("field.map.group." + g), False) for g in groups]
           if not show_erosion else [("#c3cad4", t("field.map.slow"), False), ("#7d889c", t("field.map.medium"), False),
                                     ("#16213e", t("field.map.fast"), False)])
    source_line(t("field.map.unit", year=yr), t("field.map.source"), str(yr))
with right:
    st.subheader(t("field.soil.title"))
    kpis([(t("field.soil.silt"), num(p["silt_pct"]), "%", t("field.soil.silt_note"), None, t("field.soil.silt_help")),
          (t("field.soil.water"), num(store), "L/m²", t("field.soil.water_note"), None, tip("nFK"))])
    st.space("small")
    kpis([(t("field.soil.slope"), num(slope, 1), "%", t("field.soil.slope_note", n=num(p["slope_max_pct"])), None,
           "NASADEM."),
          (t("field.soil.erosion"), t("plain.level." + p["erosion_class"]), None,
           t("field.soil.erosion_note", k=p["k_class"]), None, tip("K_factor"))])
    st.caption(t("field.soil.unit", legend=p["dominant_legend"], unit=p["dominant_unit"]))
    c24 = crops[(crops.field == fid) & (crops.year == 2024)].nlargest(3, "share")
    st.markdown(t("field.soil.grown") + "  \n" + ", ".join(f"{names.get(r.code, r.name)} {pct(r.share)}"
                                                           for r in c24.itertuples()))

# --- this season, seen from space (HLS) --------------------------------------
st.space("medium")
st.subheader(t("field.space.title"))
space = from_space() or {"fields": {}}
sp = space["fields"].get(fid)
if sp is None:
    st.caption(t("field.space.pending"))
else:
    season, before = sp["season"], sp["season"] - 1
    # what grows now in the crop colours of the map above; last year's beet that is cereal now is outlined: the nursery
    colour = {"nursery": CROPS["cereal"], "winter": CROPS["cereal"], "beet_now": CROPS["beet"], "switched": POS,
              "other": GREY_LIGHT, "unknown": GREY}
    label = {k: t("field.space.status." + k, season=season, before=before) for k in colour}
    feats = [f for f in geojson("hls_parcels")["features"] if f["properties"]["field"] == fid]
    for f in feats:
        q = f["properties"]
        name = t("field.space.unsure", status=label[q["likely"]]) if q["status"] == "unknown" else label[q["status"]]
        q |= {"rgb": rgb(colour[q["status"]]), "label": name, "pct": pct(q["p"])}
    shown = [k for k in colour if any(f["properties"]["status"] == k for f in feats)]
    left, right = st.columns([1.6, 1], gap="large")
    with left:
        st.pydeck_chart(pdk.Deck(map_style=None, initial_view_state=pdk.ViewState(latitude=p["lat"], longitude=p["lon"], zoom=14.6),
                                 layers=[pdk.Layer("GeoJsonLayer", data={"type": "FeatureCollection", "features": feats},
                                                   pickable=True, get_fill_color="properties.rgb", stroked=True,
                                                   get_line_color=[255, 255, 255], line_width_min_pixels=1),
                                         pdk.Layer("GeoJsonLayer", data={"type": "FeatureCollection", "features": [
                                             f for f in feats if f["properties"]["status"] == "nursery"]},
                                                   filled=False, stroked=True, get_line_color=rgb(HUE, 255),
                                                   line_width_min_pixels=3),
                                         pdk.Layer("GeoJsonLayer", data=outline, filled=False, stroked=True,
                                                   get_line_color=[22, 33, 62], line_width_min_pixels=2)],
                                 tooltip={"text": t("field.space.tooltip", status="{label}", p="{pct}", ha="{ha}")}), height=380)
        legend([(colour[k], label[k], False) + ((HUE,) if k == "nursery" else ()) for k in shown])
    with right:
        st.markdown(t("field.space.intro", n=num(sp["pictures"]), last=day(pd.Timestamp(sp["last"]))))
        b, now, c, m = sp["beet_before"]["n"], sp["beet_now"], sp["check"], space["model"]
        # counts from the probabilities (expected value, 90 % range), not from the map colours: the most likely status
        # undercounts a crop the model is often unsure about (beet)
        nur, rn, rh, n_now = sp["nursery"]["range_n"], now["range_n"], now["range_ha"], round(now["expected_n"])
        nur_range = t("field.space.range_n", lo=nur[0], hi=nur[1]) if nur[0] != nur[1] else ""
        now_range = t("field.space.range", lo=rn[0], hi=rn[1], ha_lo=num(rh[0], 1), ha_hi=num(rh[1], 1)) if rn[1] else ""
        said = [t("field.space.nursery", nursery=sp["nursery"]["n"], total=b, before=before, season=season, range=nur_range) if b
                else t("field.space.no_beet_before", before=before, season=season),
                tn("field.space.beet_now", n_now, ha=num(now["expected_ha"], 1), season=season, range=now_range) if n_now
                else t("field.space.no_beet_now", season=season, range=now_range),
                t("field.space.trust", n=c["after_beet"]["n"], agree=c["after_beet"]["agree"],
                  years=c["after_beet"]["years"].replace("-", "–"), found=c["beet"]["found"], n_beet=c["beet"]["n_beet"],
                  wrong=c["beet"]["n_said"] - c["beet"]["right"], n_said=c["beet"]["n_said"])
                + (" " + t("field.space.trust_fiona", years=sp["declared"]["years"].replace("-", "–"),
                           agree=sp["declared"]["winter"]["agree"], n=sp["declared"]["winter"]["n"],
                           ab_agree=sp["declared"]["after_beet"]["agree"], ab_n=sp["declared"]["after_beet"]["n"],
                           found=sp["declared"]["beet"]["found"], n_beet=sp["declared"]["beet"]["n_beet"])
                   if sp.get("declared", {}).get("winter", {}).get("n") else "")
                + " " + t("field.space.model", right=num(m["right"]), n=num(m["n"]), acc=pct(m["accuracy"]),
                          lo=pct(m["accuracy_95"][0]), hi=pct(m["accuracy_95"][1]), rule=pct(m["rule"]["accuracy"]),
                          said=pct(m["said"]))
                + " " + t("field.space.small", parcels=sp["parcels"])]
        st.markdown(said[0])
        st.markdown(said[1])
        st.caption(said[2])
        report.append((t("field.space.title"), said))
    ser = table("hls_series")
    ser = ser[(ser.field == fid) & (ser.date >= pd.Timestamp(before, 8, 1))]
    ser = ser.assign(status=ser.id.map({f["properties"]["id"]: f["properties"]["status"] for f in feats}))
    keys = [k for k in ("nursery", "switched", "beet_now") if k in shown]
    st.markdown(f"**{t('field.space.curves')}**  \n{t('field.space.curves_note')}")
    index = "ndvi"
    if "ndre" in ser and ser.ndre.notna().any():  # the red-edge index exists once the Sentinel-2 red-edge band is in
        index = st.segmented_control(t("field.space.index"), ["ndvi", "ndre"], default="ndvi", required=True, key="space_index",
                                     format_func=lambda k: t("field.space." + k), persist_state="session", width="content",
                                     help=t("field.space.index_help"))
    green = t("field.space.green") if index == "ndvi" else t("field.space.green_ndre")
    curve = ser[ser.status.isin(keys)].dropna(subset=[index]).groupby(["status", "date"])[index].median().reset_index()
    curve["what"] = curve.status.map(label)
    newest = alt.Chart(pd.DataFrame({"date": [pd.Timestamp(sp["last"])], "label": [t("field.space.newest")]}))
    chart(alt.Chart(curve).mark_line(point=alt.OverlayMarkDef(size=18), strokeWidth=2).encode(
        x=alt.X("date:T", title=None), y=alt.Y(f"{index}:Q", title=green, scale=alt.Scale(domain=[0, 1])),
        color=alt.Color("what:N", scale=alt.Scale(domain=[label[k] for k in keys], range=[(colour | {"nursery": "#c98500"})[k] for k in keys]),
                        legend=alt.Legend(orient="top", title=None, labelLimit=400)),
        tooltip=[alt.Tooltip("date:T", format="%d %b %Y", title=t("field.space.date")), "what:N",
                 alt.Tooltip(f"{index}:Q", format=".2f", title=green)])
          + newest.mark_rule(color=GREY, strokeDash=[3, 3]).encode(x="date:T")
          + newest.mark_text(align="right", baseline="top", dx=-4, dy=2, color=GREY, fontSize=12).encode(x="date:T", y=alt.value(0), text="label:N"),
          width="stretch", height=220)
    source_line(t("field.space.unit"), t("field.space.source"), f"{sp['first'][:4]}–{sp['last'][:4]}")

# --- tabs -----------------------------------------------------------------
st.space("medium")
st.subheader(t("field.numbers"))
t_cond, t_bare, t_hist, t_sm, t_sat, t_scen = st.tabs([t("field.tab." + k) for k in
                                                       ("weather", "bare", "history", "moisture", "satellite", "scenario")])


def period_mean(src, key, years):
    s = ind[(ind.source == src) & (ind.indicator == key) & ind.year.between(*years)]
    return s.value.mean() if len(s) else np.nan


with t_cond:
    src = st.segmented_control(t("field.measured_by"), SOURCES + (("ERA5",) if "t_max_era5" in daily else ()), default="POWER", required=True, key="cond_src",
                               format_func=lambda s: t("field.src." + s), persist_state="session",
                               help=tip("satellite_vs_ground"))
    keys = [k for k in ind_meta if ((ind.source == src) & (ind.indicator == k)).any()]
    early = (2001, 2010) if src == "IMERG" else EARLY
    items = []
    for k in [k for k in ["heat_days", "heavy_rain_days", "dry_spells_summer", "cwb_summer"] if k in keys]:
        m = ind_meta[k]
        sign = -1 if m.get("flip") else 1
        now, then = sign * period_mean(src, k, RECENT), sign * period_mean(src, k, early)
        items.append((m["label"], smart(now), m["unit"], t("field.was", x=smart(then), start=early[0], end=early[1]),
                      tone(m, now - then) if smart(now) != smart(then) else None, m["definition"]))
    kpis(items)
    st.caption(t("field.average_note", start=RECENT[0], end=RECENT[1], early_start=early[0], early_end=early[1]))
    k = st.selectbox(t("field.year_by_year"), keys, format_func=lambda k: ind_meta[k]["label"], key="cond_ind")
    m = ind_meta[k]
    s = ind[(ind.source == src) & (ind.indicator == k)]
    s = s.assign(value=-s.value) if m.get("flip") else s
    slope_k = np.polyfit(s.year, s.value, 1)[0] * 10
    periods = pd.DataFrame({"start": [early[0], RECENT[0]], "end": [early[1], RECENT[1]],
                            "label": [f"{early[0]}–{early[1]}", f"{RECENT[0]}–{RECENT[1]}"]})
    bands = (alt.Chart(periods).mark_rect(color=GREY_LIGHT, opacity=0.3).encode(x="start:O", x2="end:O")
             + alt.Chart(periods).mark_text(align="left", baseline="bottom", dx=2, dy=-3, color=GREY, fontSize=12)
             .encode(x="start:O", y=alt.value(0), text="label:N"))
    bars = alt.Chart(s).mark_bar(color=GREY_LIGHT).encode(
        x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0, values=list(range(1985, 2026, 5)))),
        y=alt.Y("value:Q", title=m["unit"], axis=alt.Axis(tickCount=5)),
        tooltip=[alt.Tooltip("year:O"), alt.Tooltip("value:Q", format=".1f", title=m["unit"])])
    trend = alt.Chart(s).transform_regression("year", "value").mark_line(color=HUE, strokeWidth=2).encode(
        x="year:O", y="value:Q")
    chart((bands + bars + trend).properties(padding={"top": 18, "left": 5, "right": 5, "bottom": 5}), width="stretch", height=240)
    source_line(m["unit"], t("field.src." + src) + (t("field.src.imerg_cwb") if src == "IMERG" and "cwb" in k else ""),
                t("field.complete_years", start=s.year.min(), end=s.year.max()))
    st.markdown(t("field.trend", change=("+" if slope_k > 0 else "") + num(slope_k, 1), unit=m["unit"])
                + f" {m['definition']} {m['meaning']}")
    # warmer than it used to be: monthly means against the 1991–2020 mean of the same month (rain sources use POWER)
    tsrc = src if f"t_mean_{src.lower()}" in daily else "POWER"
    tm = daily.set_index("date")[f"t_mean_{tsrc.lower()}"].resample("MS").mean()
    base = tm["1991":"2020"]
    an = (tm - base.groupby(base.index.month).mean().reindex(tm.index.month).values).dropna()
    yearly = an.groupby(an.index.year).mean()[an.groupby(an.index.year).size() == 12]
    sign = lambda v: ("+" if v > 0 else "") + num(v, 1)
    said = t("field.anom.text", n=int((yearly.iloc[-10:] > 0).sum()), last=sign(an.iloc[-12:].mean()),
             year=int(yearly.idxmax()), max=sign(yearly.max()))
    st.markdown(f"**{t('field.anom.title')}**  \n" + said)
    report.append((t("field.anom.title"), [said]))
    a = pd.DataFrame({"date": an.index, "anomaly": an.values, "roll": an.rolling(12).mean().values})
    chart(alt.Chart(a).mark_bar(size=1.5).encode(
        x=alt.X("date:T", title=None), y=alt.Y("anomaly:Q", title=t("field.anom.axis"), axis=alt.Axis(tickCount=5)),
        color=alt.condition("datum.anomaly > 0", alt.value(HUE), alt.value(GREY)),
        tooltip=[alt.Tooltip("date:T", format="%b %Y"), alt.Tooltip("anomaly:Q", format="+.1f", title="°C")])
          + alt.Chart(a).mark_line(color=INK, strokeWidth=2).encode(x="date:T", y="roll:Q"), width="stretch", height=200)
    source_line(t("field.anom.unit"), t("field.src." + tsrc), f"{an.index.min().year}–{an.index.max().year}")
    # summer green from space (MODIS 250 m, 2001 ->): the dry summers show up as a less green field
    nd = table("ndvi")
    if nd is not None and (nd.field == fid).any():
        nd = nd[nd.field == fid]
        full = nd.date.max().year - (nd.date.max().month < 9)  # complete summers only
        g = nd[nd.date.dt.month.between(6, 8) & (nd.date.dt.year <= full)]
        g = g.groupby(g.date.dt.year.rename("year")).ndvi.mean().reset_index()
        low = sorted(g.nsmallest(4, "ndvi").year)
        cwb = ind[(ind.source == "POWER") & (ind.indicator == "cwb_summer") & (ind.year >= g.year.min())]
        dry = set(cwb.nsmallest(5, "value").year) & set(low)
        said = t("field.green.text", start=g.year.min(), years=listing(map(str, low))) + (" " + tn("field.green.dry", len(dry)) if dry else "")
        st.markdown(f"**{t('field.green.title')}**  \n" + said)
        report.append((t("field.green.title"), [said]))
        chart(alt.Chart(g.assign(low=g.year.isin(low))).mark_bar().encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0, values=list(range(2005, full + 1, 5)))),
            y=alt.Y("ndvi:Q", title=t("field.green.axis"), axis=alt.Axis(tickCount=4)),
            color=alt.condition("datum.low", alt.value(HUE), alt.value(GREY_LIGHT)),
            tooltip=[alt.Tooltip("year:O"), alt.Tooltip("ndvi:Q", format=".2f", title=t("field.green.axis"))]),
            width="stretch", height=200)
        source_line(t("field.green.unit"), t("field.green.source"), f"{g.year.min()}–{full}")
        st.caption(t("field.green.note"))
    # water stress and surface heat from space (ECOSTRESS 70 m, 2018 ->): the summers the plants ran short of water
    eco = table("ecostress")
    if eco is not None and (eco.field == fid).any():
        eco = eco[eco.field == fid]
        full = eco.time.max().year - (eco.time.max().month < 9)
        g = eco[eco.time.dt.month.between(5, 8) & (eco.time.dt.year <= full)].dropna(subset=["esi"])
        g = g.groupby(g.time.dt.year.rename("year")).agg(esi=("esi", "mean"), n=("esi", "size")).reset_index()
        g = g[g.n >= 5]
        low = sorted(g.nsmallest(3, "esi").year)
        hot = eco.loc[eco.lst.idxmax()]
        said = t("field.eco.text", start=g.year.min(), years=listing(map(str, low)), lst=num(hot.lst), date=day(hot.time))
        st.markdown(f"**{t('field.eco.title')}**  \n" + said)
        report.append((t("field.eco.title"), [said]))
        chart(alt.Chart(g.assign(low=g.year.isin(low))).mark_bar().encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("esi:Q", title=t("field.eco.axis"), scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(tickCount=4)),
            color=alt.condition("datum.low", alt.value(HUE), alt.value(GREY_LIGHT)),
            tooltip=[alt.Tooltip("year:O"), alt.Tooltip("esi:Q", format=".2f", title=t("field.eco.axis")),
                     alt.Tooltip("n:Q", title=t("field.eco.passes"))]),
            width="stretch", height=200)
        source_line(t("field.eco.unit"), t("field.eco.source"), f"{g.year.min()}–{full}")
        st.caption(t("field.eco.note"))

with t_bare:
    st.markdown(t("field.bare.intro"))
    dates = strategies()["crop_dates"]
    d0 = pd.Timestamp("2001-01-01")
    on = lambda doy: d0 + pd.Timedelta(days=int(doy) - 1)
    stage = {k: t("field.bare.stage." + k) for k in ("sown", "growing", "covered")}
    rows = []
    for c, d in dates.items():
        lab = crop_cal[c]["label"] + ("" if "dwd" in crop_cal[c] else t("field.bare.estimate"))
        if crop_cal[c]["winter"]:
            rows += [(lab, stage["sown"], on(d["sow"]), on(d["emerge"])), (lab, stage["growing"], on(d["emerge"]), on(365)),
                     (lab, stage["growing"], d0, on(d["canopy"])), (lab, stage["covered"], on(d["canopy"]), on(d["harvest"]))]
        else:
            rows += [(lab, stage["sown"], on(d["sow"]), on(d["emerge"])),
                     (lab, stage["growing"], on(d["emerge"]), on(d["canopy"])),
                     (lab, stage["covered"], on(d["canopy"]), on(d["harvest"]))]
    cal = pd.DataFrame(rows, columns=["crop", "stage", "start", "end"])
    rain = (daily[daily.date.dt.year.between(2001, 2024) & (daily.p_imerg >= 20)]
            .assign(month=lambda x: x.date.dt.month).groupby("month").size().div(24)
            .reindex(range(1, 13), fill_value=0).rename("days").reset_index())
    rain["start"] = pd.to_datetime(dict(year=2001, month=rain.month, day=1))
    rain["end"] = rain.start + pd.offsets.MonthEnd(0)
    x = alt.X("start:T", title=None, axis=alt.Axis(format="%b", tickCount=12), scale=alt.Scale(domain=[d0, on(365)]))
    rain_chart = alt.Chart(rain).mark_bar(color=INK).encode(
        x=x, x2="end:T", y=alt.Y("days:Q", title=t("field.bare.downpours"), axis=alt.Axis(tickCount=3)), y2=alt.datum(0),
        tooltip=[alt.Tooltip("start:T", format="%B", title=t("grow.card.month")),
                 alt.Tooltip("days:Q", format=".1f", title=t("field.bare.downpours"))]).properties(height=90)
    gantt = alt.Chart(cal).mark_bar(height=14).encode(
        x=x, x2="end:T", y=alt.Y("crop:N", title=None, sort=None, axis=alt.Axis(labelLimit=200)),
        color=alt.Color("stage:N", scale=alt.Scale(domain=list(stage.values()), range=[HUE, GREY_LIGHT, GREY]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["crop", "stage", alt.Tooltip("start:T", format="%d %b"), alt.Tooltip("end:T", format="%d %b")])
    chart(alt.vconcat(rain_chart, gantt).resolve_scale(x="shared"), width="stretch")
    source_line(t("field.bare.unit"), t("field.bare.source"), t("field.bare.period"))
    # measured: HLS (30 m) where it has arrived, else MODIS (250 m)
    sat = next((x[x.field == fid] for x in (table("ndvi_hls"), table("ndvi")) if x is not None and (x.field == fid).any()), None)
    if sat is None:
        st.caption(t("field.bare.ndvi_pending"))
    else:
        nd = sat.assign(year=sat.date.dt.year, month=sat.date.dt.month)
        share = nd.groupby(["year", "month"]).bare.mean().reset_index()
        share["mon"] = share.month.map(dict(enumerate(months(), 1)))
        span = f"{nd.year.min()}–{nd.year.max()}"
        st.markdown(t("field.bare.measured", share=pct(share[share.month.between(5, 8)].bare.mean()), period=span))
        chart(alt.Chart(share).mark_rect().encode(
            x=alt.X("mon:O", title=None, sort=months(), axis=alt.Axis(labelAngle=0)), y=alt.Y("year:O", title=None),
            color=alt.Color("bare:Q", title=t("field.bare.ndvi_share"), scale=alt.Scale(domain=[0, 1], range=["#ffffff", INK]),
                            legend=alt.Legend(format=".0%")),
            tooltip=["year", "mon", alt.Tooltip("bare:Q", format=".0%")]), width="stretch")
        src = "hls" if (nd["product"] == "HLS").all() else "modis"
        source_line(t("field.bare.ndvi_unit"), t("field.bare.src." + src), span)
    # the winter gap before spring crops: green with a cover crop, or bare (HLS, November–December)
    hp = table("hls_parcels")
    w = hp[(hp.field == fid) & hp.covered.notna()] if hp is not None and "covered" in hp else []
    if len(w):
        b = w[w.crop == 1402]
        span = f"{w.year.min() - 1}–{w.year.max() - 1}"
        said = t("field.winter.text", green=num(w.covered.sum()), n=num(len(w)), period=span) + (
            " " + t("field.winter.beet", green=num(b.covered.sum()), n=num(len(b)), grow=t("nav.grow")) if len(b) else "")
        st.markdown(f"**{t('field.winter.title')}**  \n" + said)
        report.append((t("field.winter.title"), [said]))
        what = {True: t("field.winter.green"), False: t("field.winter.bare")}
        per = (w.assign(winter=(w.year - 1).astype(str) + "/" + (w.year % 100).astype(str).str.zfill(2),
                        what=w.covered.astype(bool).map(what))
               .groupby(["winter", "what"]).size().rename("n").reset_index())
        chart(alt.Chart(per).mark_bar(width=34).encode(
            x=alt.X("winter:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("n:Q", title=t("field.winter.parcels"), axis=alt.Axis(tickMinStep=1)),
            color=alt.Color("what:N", scale=alt.Scale(domain=list(what.values()), range=[POS, GREY_LIGHT]),
                            legend=alt.Legend(orient="top", title=None)),
            order=alt.Order("what:N", sort="descending"),
            tooltip=["winter", "what", alt.Tooltip("n:Q", title=t("field.winter.parcels"))]), width="stretch", height=200)
        source_line(t("field.winter.unit"), t("field.winter.source"), span)

with t_hist:
    st.markdown(t("field.hist.intro"))
    h = crops[crops.field == fid].copy()
    h["crop"] = np.where(h.share >= 0.03, h.code.map(names).fillna(h.name), t("field.hist.other"))
    h = h.groupby(["year", "source", "crop"], as_index=False).share.sum()
    order_ = sorted(h.crop.unique(), key=lambda c: (c not in (BEET, WHEAT), -h[h.crop == c].share.sum()))
    chart(alt.Chart(h).mark_bar(width=34).encode(
        x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("share:Q", title=t("field.hist.share"), axis=alt.Axis(format="%", tickCount=4)),
        color=alt.Color("crop:N", sort=order_, scale=crop_scale(order_, (BEET, WHEAT)),
                        legend=alt.Legend(title=None, orient="right")),
        order=alt.Order("order:Q"),
        tooltip=["year", "crop", alt.Tooltip("share:Q", format=".0%")]
    ).transform_calculate(order="indexof(" + str(order_) + ", datum.crop)"), width="stretch", height=260)
    source_line(t("field.hist.unit"), t("field.hist.source"), "2017–2025")
    tr = table("crop_transitions")
    en_code = {v: k for k, v in crop_names("en").items()}  # the transitions table stores English names
    after = (tr[(tr.from_name == "Sugar beet") & tr.field.isin([fid, "bbox"])].groupby(["field", "to_name"]).ha.sum()
             .groupby(level=0).transform(lambda s: s / s.sum()).rename("share").reset_index())
    after["to"] = after.to_name.map(lambda n: names.get(en_code.get(n), n))
    after["where"] = after.field.map({fid: t("field.hist.block", id=fid), "bbox": t("field.hist.region")})
    after = after[after.share >= 0.02]
    st.subheader(t("field.hist.after"))
    to_order = sorted(after.to.unique(), key=lambda c: c != WHEAT)
    chart(alt.Chart(after).mark_bar(height=22).encode(
        y=alt.Y("where:N", title=None, axis=alt.Axis(labelLimit=200)),
        x=alt.X("share:Q", stack="normalize", axis=alt.Axis(format="%"), title=None),
        color=alt.Color("to:N", title=t("field.hist.next_year"), legend=alt.Legend(orient="bottom", columns=6),
                        scale=crop_scale(to_order, (BEET, WHEAT))),
        order=alt.Order("order:Q"),
        tooltip=["where", "to", alt.Tooltip("share:Q", format=".0%")]
    ).transform_calculate(order=f"datum.to == '{WHEAT}' ? 0 : 1"), width="stretch", height=150)
    source_line(t("field.hist.after_unit"), t("field.hist.after_source"), "2017–2024")

with t_sm:
    sm = table("soilmoisture")
    sm = sm[sm.field == fid]
    # the soil right now: the last two weeks against the same two weeks in every earlier year
    items = []
    for k, s_, unit in (("top", "SMAP", "m³/m³"), ("root", "POWER GWETROOT", ""), ("era5", "ERA5-Land 0–1 m", "m³/m³")):
        if (sm.source == s_).any():
            end, v, wetter, n = now_vs_years(sm[sm.source == s_].set_index("date").sm)
            items.append((t(f"field.now.{k}", date=day(end)), num(v, 2), unit, t("field.now.vs", k=wetter, n=n), None,
                          t(f"field.now.help_{k}")))
    if items:
        kpis(items)
        st.caption(t("field.now.unit"))
        report.append((t("field.now.title"), [f"<b>{l}:</b> {v} {u} – {d}." for l, v, u, d, _, _ in items]))
    srcs = list(sm.source.unique())
    a, b = st.columns([1.4, 1])
    pick = a.pills(t("field.measured_by"), srcs, default=[s for s in srcs if s in ("POWER GWETROOT", "SMAP", "ERA5-Land 0–1 m")],
                   selection_mode="multi", key="sm_src", help=tip("soil_moisture"))
    y0, y1 = b.slider(t("field.sat.year"), 2001, int(sm.date.dt.year.max()), (2018, int(sm.date.dt.year.max())),
                      key="sm_years")
    s = sm[sm.source.isin(pick) & sm.date.dt.year.between(y0, y1)]
    s = s.groupby(["source", pd.Grouper(key="date", freq="MS")]).anomaly.mean().reset_index()
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=GREY).encode(y="y:Q")
    chart(zero + alt.Chart(s).mark_line(strokeWidth=2).encode(
        x=alt.X("date:T", title=None), y=alt.Y("anomaly:Q", title=t("field.moisture.drier_wetter"), axis=alt.Axis(tickCount=5)),
        color=alt.Color("source:N", title=None, legend=alt.Legend(orient="top"),
                        scale=alt.Scale(domain=srcs, range=[GREY, INK, POS, "#9a6a12", HUE, GREY_LIGHT][:len(srcs)])),
        tooltip=["source", alt.Tooltip("date:T", format="%b %Y"), alt.Tooltip("anomaly:Q", format=".2f")]),
        width="stretch", height=240)
    source_line(t("field.moisture.unit"), t("field.moisture.source"), f"{y0}–{y1}")
    st.caption(tip("anomaly") + ("" if "SMAP" in srcs else t("field.moisture.smap_pending")))

with t_sat:
    st.markdown(content("glossary")["satellite_vs_ground"]["text"])
    yr = st.select_slider(t("field.sat.year"), list(range(2001, 2025)), value=2024, key="sat_year")
    d = daily[daily.date.dt.year == yr]
    station = t("field.sat.station")
    mp = (d.set_index("date")[["p_power", "p_imerg", "p_dwd"]].resample("MS").sum()
          .rename(columns={"p_power": "NASA POWER", "p_imerg": "GPM IMERG", "p_dwd": station})
          .reset_index().melt("date", var_name="source", value_name="mm"))
    chart(alt.Chart(mp).mark_bar().encode(
        x=alt.X("month(date):O", title=None), xOffset="source:N",
        y=alt.Y("mm:Q", title=t("field.sat.per_month"), axis=alt.Axis(tickCount=4)),
        color=alt.Color("source:N", title=None, legend=alt.Legend(orient="top"),
                        scale=alt.Scale(domain=["NASA POWER", "GPM IMERG", station], range=[GREY_LIGHT, HUE, INK])),
        tooltip=["source", alt.Tooltip("date:T", format="%B"), alt.Tooltip("mm:Q", format=".0f")]),
        width="stretch", height=240)
    source_line(t("field.sat.per_month"), f"NASA POWER, GPM IMERG, DWD ({d.dwd_station.mode().iloc[0]})", str(yr))
    r = daily[daily.date.dt.year.between(2001, 2024)]
    rows = [("NASA POWER", r.p_power, r.t_max_power), ("GPM IMERG", r.p_imerg, None), (station, r.p_dwd, r.t_max_dwd)]
    if "p_era5" in r:
        rows.append(("ERA5-Land", r.p_era5, r.t_max_era5))
    body = "".join(f'<tr><td>{name}</td><td class="num">{num(p_.sum() / 24)}</td><td class="num">{num((p_ >= 20).sum() / 24, 1)}</td>'
                   f'<td class="num">{num(p_.corr(r.p_dwd), 2)}</td>'
                   f'<td class="num">{"–" if tm is None else num((tm >= 30).sum() / 24, 1)}</td></tr>' for name, p_, tm in rows)
    head = "".join(f'<th class="{"num" if i else ""}">{t("field.sat.table." + c)}</th>'
                   for i, c in enumerate(("source", "rain", "downpours", "corr", "heat")))
    st.html(f'<table class="cc-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>')
    diff = (r.t_max_power - r.t_max_dwd).mean()
    st.caption(t("field.sat.note", diff=("+" if diff > 0 else "") + num(diff, 1)))

with t_scen:
    st.markdown(t("field.scenario.intro"))
    a, b = st.columns(2)
    dt = a.select_slider(t("field.scenario.warming"), [0, 1, 2], value=1, format_func=lambda v: f"+{v} °C", key="scen_dt")
    ps = b.select_slider(t("field.scenario.spring_rain"), [1.0, 0.9, 0.8], value=0.9,
                         format_func=lambda v: f"{(v - 1) * 100:+.0f} %", key="scen_ps")
    sc = table("scenarios")
    sc = sc[sc.field == fid]
    flip = pd.Series({k: -1 if ind_meta[k].get("flip") else 1 for k in ind_meta})
    base_ = sc[(sc.dT == 0) & (sc.p_spring == 1.0)].set_index("indicator").value
    now = sc[(sc.dT == dt) & (sc.p_spring == ps)].set_index("indicator").value
    base_, now = base_ * flip.reindex(base_.index), now * flip.reindex(now.index)
    show = ["heat_days", "heat_days_heading", "frost_after_emergence", "dry_spells_spring", "cwb_spring", "cwb_summer"]
    for group in (show[:3], show[3:]):
        kpis([(ind_meta[k]["label"], smart(now[k]), ind_meta[k]["unit"], t("field.scenario.today", x=smart(base_[k])),
               tone(ind_meta[k], now[k] - base_[k]), ind_meta[k]["definition"]) for k in group])
        st.space("small")
    source_line(t("field.scenario.unit"), t("field.scenario.source"), "2005–2024")
# --- ask about this field: the model explains the card above, it computes nothing ---------------------------------
st.space("medium")
copilot.panel(fid, report, "field", ("why", "first", "summary"))
side.download_button(t("field.report.button"), takeaway(title, sub + " " + t("field.report.made", date=day(pd.Timestamp.today())),
                                                        report),
                     file_name=f"crop-circles-{fid}.html", mime="text/html", icon=":material/print:", on_click="ignore",
                     help=t("field.report.help"), width="stretch")
footer()
