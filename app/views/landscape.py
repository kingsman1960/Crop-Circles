import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

import accounts

from data import (CROPS, GREY, HUE, INK, MODES, PALE, POS, chart, content, crop_group, crop_names, fields, geojson,
                  landscape, neighbourhood, plan, planner_weights, priority_control, rgb, tip)
from i18n import num, pct, t
from plain import fraction, of_ten
from ui import footer, header, kpis, legend, level, source_line

crops = content("crops")
scope = st.segmented_control(t("region.scope.label"), ["bbox", "bw"], default="bbox", required=True, key="ls_scope",
                             persist_state="session", format_func=lambda k: t("region.scope." + k),
                             label_visibility="collapsed")
par, _, summary = landscape(scope)
names = crop_names()
stats = {s["season"]: s for s in summary["seasons"]}
SHARES = (0.1, 0.2, 0.3, 0.5)
share_word = lambda v: t(f"region.share.{round(v * 100)}")

# containers in reading order; the expert settings at the bottom are read first
title_row, choose_row, numbers_row, map_row, list_row = (st.container() for _ in range(5))
st.space("medium")
with st.expander(t("region.expert.title")):
    a, b, c = st.columns([1.2, 1, 2])
    season = a.select_slider(t("region.expert.season"), list(stats), value=2025, key="ls_season", persist_state="session",
                             help=t("region.expert.season_help"))
    r = b.select_slider(t("region.expert.distance"), [500, 1000, 2000], value=1000, key="ls_r", persist_state="session",
                        format_func=lambda v: f"{num(v / 1000, 1 if v % 1000 else 0)} km", help=tip("flight_distance"))
    mode = c.segmented_control(t("region.expert.mode"), MODES, default="balanced", required=True, key="ls_mode",
                               format_func=lambda m: t("region.mode." + m), persist_state="session", help=tip("coordination"))
    st.markdown(t("region.expert.side_effects"))
    with st.container(horizontal=True, gap="medium"):
        for k in ("erosion", "water", "income"):
            priority_control(k)
    expert = st.container()

with choose_row:
    share = st.segmented_control(t("region.share_question"), SHARES, default=0.2, format_func=share_word, required=True,
                                 key="ls_share_word", persist_state="session")

plans = {m: plan(season, r, share, m, planner_weights(), scope) for m in MODES}
nur, beet = plans[mode]
removed = lambda n: n.impact[n.switch].sum() / n.impact.sum()
sw = nur[nur.switch].copy()
s = stats[season]
src = t("region.src." + s.get("source", "thuenen"))  # where the wheat-after-beet fields come from
q33, q67 = beet.pressure.quantile([1 / 3, 2 / 3])
lvl = lambda v: "high" if v >= q67 else "medium" if v >= q33 else "low"

with title_row:
    header(t("region.title"), t("region.sub", season=season, share=of_ten(s["beet_to_wheat"]), part=share_word(share),
                                less=fraction(removed(plans["balanced"][0])), random=fraction(removed(plans["random"][0]))), step=3)
    if scope == "bw":
        st.caption(t("region.scope.bw_note", n=num(len(par))))

with numbers_row:
    high_before = beet.beet_ha[beet.pressure >= q67].sum() / beet.beet_ha.sum()
    high_after = beet.beet_ha[beet.after >= q67].sum() / beet.beet_ha.sum()
    kpis([
        (t("region.kpi.followed"), of_ten(s["beet_to_wheat"]), None, t("region.kpi.followed_note", year=season - 1), None,
         t("region.kpi.followed_help", beet=num(s["beet_prev_ha"]), prev=season - 1, wheat=num(s["nursery_ha"]), season=season)),
        (t("region.kpi.nurseries"), num(s["nursery_ha"]), "ha", t("region.kpi.nurseries_note", n=num(len(nur)))
         + "; " + t("region.kpi.dlr", ha=num(s["dlr"]["nursery_ha"])), None, tip("nursery")),
        (t("region.kpi.switching"), num(len(sw)), None, f"{num(sw.nursery_ha.sum())} ha", None, None),
        (t("region.kpi.pressure"), "−" + pct(removed(nur)), None, t("region.kpi.pressure_note", fraction=fraction(removed(nur))),
         "good", tip("pressure")),
        (t("region.kpi.high"), t("region.kpi.high_value", n=num(high_after * 100)), None,
         t("region.kpi.high_note", n=num(high_before * 100)), "good" if high_after < high_before else None,
         t("region.kpi.high_help")),
    ], lead=3)

# texts looked up once, not per field: all of BW has ~20,000 dots, and every t() call reads the session
words = ({k: t("region.why." + k) for k in ("steep", "dry", "flat")}
         | {k: t("plain.level." + k).lower() for k in ("low", "medium", "high")})
why = lambda row: ", ".join([x for x in [words["steep"] if row.ks >= 0.55 else "",
                                         words["dry"] if row.nfk_mm < 140 else ""] if x] or [words["flat"]])


def parcel_card(pid):
    """One clicked parcel: what it is in the plan, and every crop since 2017 (the same colours as the crop map)."""
    row, de = par.loc[pid], crop_names("de")
    in_nur, in_beet = nur[nur.id == pid], beet[beet.id == pid]
    lines = []
    if not in_nur.empty:
        n_ = in_nur.iloc[0]
        lines.append(f"<b>{t('region.tip.switch', crop=crops[n_.alt]['label']) if n_.switch else t('region.tip.wheat')}</b>"
                     + (f" ({why(n_)})" if n_.switch else ""))
        lines.append(t("region.parcel.rank", k=num(in_nur.index[0] + 1), n=num(len(nur)), share=pct(n_.impact / nur.impact.sum()))
                     + f"<br/>{t('region.tip.both', src=src) if n_.nursery_ha_dlr > 0 else t('region.tip.one', src=src)}")
    if not in_beet.empty:
        b_ = in_beet.iloc[0]
        lines.append(f"<b>{t('region.tip.beet', season=season, ha=num(b_.beet_ha, 1), level=level_word(b_.pressure)).split(chr(10))[0]}</b>")
        lines.append(t("region.parcel.beet", now=level(lvl(b_.pressure)), after=level(lvl(b_.after)))
                     + f"<br/>{t('region.parcel.less', fraction=fraction(1 - b_.after / max(b_.pressure, 1e-9)))}")
    chips = "".join(f'<span class="cc-chip" style="--c:{CROPS[crop_group(de.get(int(row[f"c{y}"]), ""))]}">'
                    f'<i>{y}</i>{names.get(int(row[f"c{y}"]), "–")}</span>' for y in range(2017, season + 1))
    with st.container(key="card_parcel"):
        st.html(f'<h3 style="margin:0 0 6px">{t("region.parcel.title", id=pid, ha=num(row.area_ha, 1))}</h3>'
                + "".join(f'<p style="margin:0 0 8px">{x}</p>' for x in lines)
                + f'<p class="cc-note" style="margin:8px 0 4px">{t("region.parcel.history", start=2017, end=season)}</p>'
                f'<div class="cc-chips">{chips}</div>')
        # a demo-block parcel opens *My field* for accounts that own that field; any other parcel can be added to a
        # farmer's farm (stored in accounts.py, listed on *My field*)
        if isinstance(row.field, str) and row.field and row.field in accounts.my_fields(list(fields())):
            if st.button(t("region.parcel.open", id=row.field), key="ls_open_field"):
                st.session_state.field = row.field
                st.switch_page("views/field.py")
        elif accounts.user()["role"] == "farmer":  # any other parcel can join the farm
            added = pid in accounts.my_parcels()
            if st.button(t("region.parcel.remove" if added else "region.parcel.add"), key="ls_toggle_parcel"):
                accounts.toggle_parcel(pid)
                st.rerun()
            if added:
                st.caption(t("region.parcel.added"))


# --- map ------------------------------------------------------------------
with map_row:  # title and the now / after switch first; the map itself is drawn into `left` further down
    st.space("small")
    left, right = st.columns([2.1, 1], gap="large")
    with left:
        st.subheader(t("region.map.title", season=season))
        view = st.segmented_control(t("region.kpi.pressure"), ["pressure", "after"], default="after", required=True,
                                    key="ls_view", persist_state="session", label_visibility="collapsed",
                                    format_func=lambda k: t("region.demo." + ("now" if k == "pressure" else "after")))
pale, full = np.array(rgb(PALE)), np.array(rgb(HUE, 235))
v = np.clip(beet[view] / beet.pressure.quantile(0.9), 0, 1).to_numpy()[:, None]
radius = lambda d: np.sqrt(d.area_ha * 1e4 / np.pi).clip(lower=20)
years = [f"c{y}" for y in range(season - 3, season + 1)]
history = lambda d: d[years].apply(lambda col: col.map(names).fillna("–")).agg(" → ".join, axis=1)
level_word = lambda v_: words[lvl(v_)]
ha1 = lambda s: s.round(1).map({x: num(x, 1) for x in s.round(1).unique()})  # Babel once per distinct value
tip_beet, tip_after = t("region.tip.beet", season=season, ha="{ha}", level="{level}"), t("region.tip.beet_after", level="{level}")
beet = beet.assign(color=[[int(x) for x in c] for c in (pale + (full - pale) * v)], radius=radius(beet),  # plain ints for JSON
                   tip=[tip_beet.format(ha=h, level=level_word(p_))
                        + (tip_after.format(level=level_word(a_)) if lvl(a_) != lvl(p_) else "")
                        for h, a_, p_ in zip(ha1(beet.beet_ha), beet.after, beet.pressure)])
tip_switch = {a_: t("region.tip.switch", crop=crops[a_]["label"]) for a_ in nur.alt.unique()}
tip_wheat, tip_both, tip_one = t("region.tip.wheat"), t("region.tip.both", src=src), t("region.tip.one", src=src)
nur = nur.assign(color=[rgb(POS, 245) if x else rgb(GREY, 150) for x in nur.switch], radius=radius(nur),
                 tip=[f"{tip_switch[a_] if x else tip_wheat} · {h} ha\n{hs}\n{tip_both if d_ > 0 else tip_one}"
                      for a_, x, h, hs, d_ in zip(nur.alt, nur.switch, ha1(nur.nursery_ha), history(nur), nur.nursery_ha_dlr)])
cols = ["id", "lon", "lat", "radius", "color", "tip"]
dots = lambda id_, d, **kw: pdk.Layer("ScatterplotLayer", id=id_, data=d[cols], get_position="[lon, lat]",
                                     get_radius="radius", get_fill_color="color", pickable=True, **kw)
layers = [dots("wheat", nur[~nur.switch], radius_min_pixels=1.5), dots("beet", beet, radius_min_pixels=1.5),
          dots("switch", nur[nur.switch], radius_min_pixels=2.5, stroked=True, get_line_color=[255, 255, 255],
               line_width_min_pixels=1),
          pdk.Layer("GeoJsonLayer", data=geojson("fields"), stroked=True, filled=False, get_line_color=[34, 48, 42],
                    line_width_min_pixels=2),
          pdk.Layer("TextLayer", data=[{"id": i, "pos": [p["lon"], p["lat"]]} for i, p in fields().items()],
                    get_position="pos", get_text="id", get_size=15, get_color=[34, 48, 42], get_pixel_offset=[0, -22],
                    outline_width=4, outline_color=[255, 255, 255], font_settings={"sdf": True})]
with map_row:
    with left:
        ev = st.pydeck_chart(pdk.Deck(map_style=None, layers=layers, tooltip={"text": "{tip}"},
                                      initial_view_state=pdk.ViewState(latitude=(par.lat.min() + par.lat.max()) / 2,
                                                                       longitude=(par.lon.min() + par.lon.max()) / 2,
                                                                       zoom=9.6 if scope == "bbox" else 7.4)),
                             height=520, on_select="rerun", selection_mode="single-object", key=f"ls_map_{scope}")
        legend([(GREY, t("region.map.wheat"), True), (POS, t("region.map.switch"), True),
                (PALE, t("region.map.beet_low"), True), (HUE, t("region.map.beet_high"), True)])
        source_line(t("region.map.unit"), t("region.map.source", src=src), t("region.map.period", season=season))
    with right:
        picked = next((o["id"] for objs in ev.selection.objects.values() for o in objs), None)
        if picked is None:
            st.caption(t("region.parcel.hint"))
        else:
            parcel_card(picked)
        st.subheader(t("region.demo.title"))
        rows = ""
        for fid, p in fields().items():
            n = neighbourhood(fid, nur, r)
            rows += (f'<tr><td><b>{fid}</b><span class="g">'
                     f'{t("common.near", place=p["label"].removeprefix("Near "))}</span></td>'
                     f'<td>{level(lvl(n["total"]))}</td><td>{level(lvl(n["after"]))}</td></tr>')
        st.html(f'<table class="cc-table"><thead><tr><th>{t("region.demo.field")}</th><th>{t("region.demo.now")}</th>'
                f'<th>{t("region.demo.after")}</th></tr></thead><tbody>{rows}</tbody></table>')
        st.caption(t("region.demo.note"))
        st.subheader(t("region.mix.title"))
        mix = sw.groupby("alt").nursery_ha.agg(["sum", "size"])
        st.html("".join(f'<div class="cc-score"><span>{crops[a_]["label"]}</span><span class="n">'
                        f'{t("region.mix.row", n=num(m["size"]), ha=num(m["sum"]))}</span></div>' for a_, m in mix.iterrows())
                or f"<p>{t('region.mix.none')}</p>")
        st.caption(t("region.mix.note"))

# --- the list for the meeting -----------------------------------------------
col = lambda k, **kw: t("region.list.col." + k, **kw)
table = pd.DataFrame({
    col("id"): sw.id, col("ha"): sw.nursery_ha.round(1), col("crop"): sw.alt.map(lambda a_: crops[a_]["label"]),
    col("why"): [why(row) for row in sw.itertuples()],
    col("history", start=season - 3, end=season): history(sw).to_numpy(),
    col("maps"): np.where(sw.nursery_ha_dlr > 0, t("region.list.both"), t("region.list.one", src=src)),
    col("share"): sw.impact / nur.impact.sum(), "lat": sw.lat.round(5), "lon": sw.lon.round(5)})
with list_row:
    st.space("small")
    a, b = st.columns([3, 1], vertical_alignment="bottom")
    a.subheader(t("region.list.title"))
    b.download_button(t("region.list.download"), table.to_csv(index=False).encode("utf-8"),
                      f"switch_list_{'bw_' if scope == 'bw' else ''}{season}_{round(share * 100)}.csv", "text/csv", type="primary", width="stretch",
                      disabled=sw.empty)
    st.dataframe(table.drop(columns=["lat", "lon"]).head(200), hide_index=True, height=340, column_config={
        col("share"): st.column_config.NumberColumn(format="percent"),
        col("ha"): st.column_config.NumberColumn(format="%.1f")})
    st.caption(t("region.list.note", n=num(len(table))))

# --- expert view --------------------------------------------------------------
with expert:
    st.markdown(t("region.expert.compare", part=share_word(share)))
    a, b = st.columns([1, 1.25], gap="large")
    with a:
        rows = ""
        for m, (n, _) in plans.items():
            x = n[n.switch]
            area = max(x.nursery_ha.sum(), 1e-9)
            rows += (f'<tr class="{"top" if m == mode else ""}"><td>{t("region.mode." + m)}</td>'
                     f'<td class="num">{pct(removed(n))}</td><td class="num">{pct(x.nursery_ha[x.ks >= 0.55].sum() / area)}</td></tr>')
        st.html(f'<table class="cc-table"><thead><tr><th>{t("region.expert.col.mode")}</th>'
                f'<th class="num">{t("region.expert.col.less")}</th><th class="num">{t("region.expert.col.eroded")}</th>'
                f'</tr></thead><tbody>{rows}</tbody></table>')
        o = [pct(s[f"targeted20_r{x}"]) for x in (500, 1000, 2000)]
        st.caption(t("region.expert.robust", a=o[0], b=o[1], c=o[2]))
        d = s["dlr"]
        st.caption(t("region.expert.dlr", src=src, season=season, ha=num(d["nursery_ha"]), thuenen=num(s["nursery_ha"]),
                     conf=pct(d["confirmed"]), a=pct(d["targeted20_r500"]), b=pct(d["targeted20_r1000"]),
                     c=pct(d["targeted20_r2000"])))
    with b:
        curve = []
        for m, (n, _) in plans.items():
            x, y = np.cumsum(n.nursery_ha) / n.nursery_ha.sum(), np.cumsum(n.impact) / n.impact.sum()
            idx = np.linspace(0, len(n) - 1, 120).astype(int)
            curve.append(pd.DataFrame({"area": x.iloc[idx].to_numpy(), "removed": y.iloc[idx].to_numpy(),
                                       "how": t("region.mode." + m)}))
        labels = [t("region.mode." + m) for m in MODES]
        base = alt.Chart(pd.concat(curve)).mark_line(strokeWidth=2).encode(
            x=alt.X("area:Q", title=t("region.expert.x"), axis=alt.Axis(format="%", tickCount=5)),
            y=alt.Y("removed:Q", title=t("region.expert.y"), axis=alt.Axis(format="%", tickCount=5)),
            color=alt.Color("how:N", title=None, legend=alt.Legend(orient="top", direction="vertical"),
                            scale=alt.Scale(domain=labels, range=[HUE, INK, GREY])),
            tooltip=[alt.Tooltip("area:Q", format=".0%"), alt.Tooltip("removed:Q", format=".0%"), "how"])
        layers_ = [base.transform_filter(alt.datum.how == t("region.mode." + m)) for m in [*[x for x in MODES if x != mode], mode]]
        rule = alt.Chart(pd.DataFrame({"x": [share]})).mark_rule(color=INK, strokeDash=[3, 3]).encode(x="x:Q")
        chart(alt.layer(*layers_) + rule, width="stretch", height=260)
    st.markdown(t("region.expert.method", season=season,
                  status=t("region.expert.preliminary") if season == 2025 else t("region.expert.final")))
footer()
