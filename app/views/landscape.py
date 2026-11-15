import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

import accounts

from data import (CROPS, FLIGHT_M, FLIGHTS, GREY, GREY_LIGHT, HUE, INK, PALE, chart, crop_group, crop_names, fields, geojson,
                  landscape, parcel_geo, partners, pressure, region_series, rgb, tip)
from i18n import num, pct, t
from ui import footer, header, kpis, legend, source_line

scope = st.segmented_control(t("region.scope.label"), ["bbox", "bw"], default="bbox", required=True, key="ls_scope",
                             persist_state="session", format_func=lambda k: t("region.scope." + k),
                             label_visibility="collapsed")
par, seasons, summary = landscape(scope)
names, names_de = crop_names(), crop_names("de")
stats = {s["season"]: s for s in summary["seasons"]}
years = sorted(stats)  # 2018–2025
first, last = years[0], years[-1]
shapes = parcel_geo(scope)
gids = pd.Index(shapes["ids"], dtype="int64")
last_nur = seasons[(seasons.season == last) & (seasons.nursery_ha > 0)]

# containers in reading order; the expert settings at the bottom are read first
title_row, numbers_row, trend_row, map_row = (st.container() for _ in range(4))
st.space("medium")
with st.expander(t("region.expert.title")):
    r = st.select_slider(t("region.expert.distance"), list(FLIGHTS), value=FLIGHT_M, key="ls_r", persist_state="session",
                         format_func=lambda v: f"{num(v / 1000, 1 if v % 1000 else 0)} km", help=tip("flight_distance"))
    o = [pct(stats[last][f"targeted20_r{x}"]) for x in FLIGHTS]
    st.markdown(t("region.expert.robust", a=o[0], b=o[1], c=o[2]))
    d = stats[last]["dlr"]
    st.markdown(t("region.expert.dlr", season=last, ha=num(d["nursery_ha"]), thuenen=num(stats[last]["nursery_ha"]),
                  conf=pct(d["confirmed"]), a=pct(d[f"targeted20_r{FLIGHTS[0]}"]), b=pct(d[f"targeted20_r{FLIGHTS[1]}"]),
                  c=pct(d[f"targeted20_r{FLIGHTS[2]}"])))
    st.markdown(t("region.expert.method", season=last,
                  status=t("region.expert.preliminary") if stats[last]["map"] == "v302 preliminary" else t("region.expert.final")))

trend, acc = region_series(scope, r)
trend["potential"] = trend.pressure * pd.Series({y: stats[y][f"targeted20_r{FLIGHT_M}"] for y in trend.index})
change = 1 - trend.per_100_ha.iloc[-1] / trend.per_100_ha.iloc[0]

with title_row:
    header(t("region.title"), t("region.sub", first=first, last=last, share=pct(stats[last]["beet_to_wheat"])))
    if scope == "bw":
        st.caption(t("region.scope.bw_note", n=num(len(par))))

with numbers_row:
    kpis([
        (t("region.kpi.followed"), pct(stats[last]["beet_to_wheat"]), None, t("region.kpi.followed_note", year=last - 1),
         None, t("region.kpi.followed_help", beet=num(stats[last]["beet_prev_ha"]), prev=last - 1,
                 wheat=num(stats[last]["nursery_ha"]), season=last)),
        (t("region.kpi.nurseries"), num(stats[last]["nursery_ha"]), "ha", t("region.kpi.fields", n=num(len(last_nur))),
         None, tip("nursery")),
        (t("region.kpi.trend"), ("−" if change > 0 else "+") + pct(abs(change)), None,
         t("region.kpi.trend_note", start=first), "good" if change > 0 else None, tip("pressure")),
        (t("region.kpi.potential"), pct(stats[last][f"targeted20_r{FLIGHT_M}"]), None, t("region.kpi.potential_note"),
         None, tip("coordination")),
    ])

with trend_row:
    st.space("small")
    st.subheader(t("region.trend.title"))
    what = (t("region.trend.total"), t("region.trend.normed"), t("region.trend.potential"))
    long = pd.DataFrame({"season": years, what[0]: trend.rel_total, what[1]: trend.rel_normed,
                         what[2]: trend.potential / trend.potential.iloc[0] * 100}).melt("season",
                                                                                         var_name="what", value_name="v")
    pick = alt.selection_point(fields=["what", "season"], on="click", name="region_pick")
    lines = alt.Chart(long).mark_line(point=True).encode(
        x=alt.X("season:O", title=t("region.trend.x"), axis=alt.Axis(labelAngle=0)),
        y=alt.Y("v:Q", title=t("region.trend.y"), axis=alt.Axis(format=".0f"), scale=alt.Scale(zero=False)),
        color=alt.Color("what:N", scale=alt.Scale(domain=list(what), range=[INK, HUE, GREY]), legend=None),
        strokeDash=alt.StrokeDash("what:N", scale=alt.Scale(domain=list(what), range=[[0], [6, 4], [0]])),
        tooltip=[alt.Tooltip("season:O", title=t("region.trend.x")), "what", alt.Tooltip("v:Q", format=".0f",
                                                                                         title=t("region.trend.y"))])
    y0 = int(st.session_state.get("ls_year", last))
    rule = alt.Chart(pd.DataFrame({"season": [y0]})).mark_rule(color=INK, strokeDash=[2, 3]).encode(x="season:O")
    ev = chart(alt.layer(lines.add_params(pick), rule), on_select="rerun", key="ls_trend")
    sel_state = getattr(ev, "selection", None)  # a testing run returns None: nothing was clicked
    for p_ in ((sel_state or {}).get("region_pick") or {}).get("points", []):
        if "season" in p_:
            st.session_state["ls_year"] = int(p_["season"])
            if st.session_state.get("ls_var", "spread") != "crops":
                st.session_state["ls_agg"] = "single"
    legend([(INK, what[0], False), (HUE, what[1], False), (GREY, what[2], False)])

with map_row:
    st.space("small")
    left, right = st.columns([2.3, 1], gap="large")
    with left:
        var = st.segmented_control(t("region.var.label"), ["spread", "received", "crops"], default="spread", required=True,
                                   key="ls_var", persist_state="session", format_func=lambda k: t("region.var." + k))
        if var == "crops":
            yr = st.select_slider(t("region.expert.season"), years, value=last, key="ls_year", persist_state="session",
                                  help=t("region.year_help"))
        else:
            agg = st.segmented_control(t("region.agg.label"), ["single", "all"], default="single", required=True,
                                       key="ls_agg", persist_state="session", format_func=lambda k: t("region.agg." + k))
            yr = None if agg == "all" else st.select_slider(t("region.expert.season"), years, value=last, key="ls_year",
                                                            persist_state="session", help=t("region.year_help"))
        st.subheader(t("region.map.title"))

        # what the parcel polygons are filled with: the pressure a parcel sends or receives (this season, or summed
        # over all seasons to find the systematic sources and victims), or what grew on it in one year
        val = None
        if var == "spread":
            if yr is None:
                val, reach, years_of = acc.sent, acc.reach, acc.years
            else:
                nur0 = pressure(yr, r, scope)[0]
                val = nur0.set_index("id").impact
                reach = pd.Series(nur0.impact.to_numpy() / nur0.nursery_ha.to_numpy(), index=nur0.id)  # per nursery ha
        elif var == "received":
            if yr is None:
                val, years_of = acc.got, acc.recv_years
            else:
                val = pressure(yr, r, scope)[1].set_index("id").pressure  # kernel-weighted nursery ha around it
                reach = val  # the figure the tooltip shows is the value the parcel is coloured by
        else:
            codes = par[f"c{yr}"]
            c_by_code = {int(c): rgb(CROPS[crop_group(names_de.get(int(c), ""))], 235) for c in codes.unique()
                         if int(c) in names_de}
            tip_by_code = {int(c): t("region.tip.crop", crop=names_de.get(int(c), "–")) for c in codes.unique()
                           if int(c) in names_de}
        pale, full = np.array(rgb(PALE)), np.array(rgb(HUE, 245))
        faint = rgb(GREY_LIGHT, 60)
        tip_by_gid = {}
        if val is not None:
            act = val[val > 0]
            duty = ((act / max(float(act.quantile(0.9)) if len(act) else 1.0, 1e-9)).clip(0, 1) * 255).astype(int)
            c_by_v = {p_: [int(x) for x in (pale + (full - pale) * (p_ / 255))] for p_ in duty.unique()}
            if yr is None:  # accumulated: per-season averages over the parcels' own active years
                reach = (reach if var == "spread" else val) / years_of.reindex(act.index).replace(0, np.nan)
                years_of = years_of.reindex(act.index)
            if yr is None:
                n_ = num(len(years))
                tip_f = lambda s_, h_: t("region.tip.sent_all" if var == "spread" else "region.tip.recv_all",
                                         seasons=num(s_), n=n_, ha=num(h_))
            else:
                tip_f = lambda s_, h_: t("region.tip.sent" if var == "spread" else "region.tip.recv", ha=num(h_))
            memo = {}
            for gid in act.index:  # the same tip text per distinct (seasons, ha) pair, looked up once, not per parcel
                key = (int(years_of[gid]) if yr is None else 0, round(float(reach[gid])))
                if key not in memo:
                    memo[key] = tip_f(key[0], key[1])
                tip_by_gid[gid] = memo[key]
            # grey parcels get their own tip: an empty string makes the map show the previous feature's text
            if var == "spread":
                off_tip = (t("region.tip.off_spread", season=yr) if yr is not None
                           else t("region.tip.off_spread_all", start=first, end=last))
            else:
                off_tip = (t("region.tip.off_recv", season=yr) if yr is not None
                           else t("region.tip.off_recv_all", start=first, end=last))
        else:
            off_tip = t("region.tip.crop_off", season=yr)

        def paint(gid):
            """Fill colour and tooltip of one parcel, the same whether it is drawn as a polygon or as a dot."""
            if val is not None:
                v_ = int(duty.get(gid, 0))
                return (c_by_v[v_], tip_by_gid.get(gid, "")) if v_ else (faint, off_tip)
            code = int(codes.get(gid, 0))
            return (c_by_code[code], tip_by_code[code]) if code in c_by_code else (faint, off_tip)

        fe = []
        for gid, g in zip(gids, shapes["geoms"]):
            c, tip_ = paint(gid)
            fe.append({"type": "Feature", "geometry": g, "properties": {"fill": c, "tip": tip_, "id": int(gid)}})
        # pipeline/landscape_geo.py has not covered every parcel (all of BW: 91,000 outlines would be ~15 MB a render):
        # dots take the leftovers, with the same colour and tip as a polygon would carry
        missing = par.index[~par.index.isin(gids)]
        painted = [paint(gid) for gid in missing]
        dots = pdk.Layer("ScatterplotLayer", id="parcels", data=pd.DataFrame({
            "id": missing, "lon": par.loc[missing, "lon"], "lat": par.loc[missing, "lat"],
            "radius": (np.sqrt(par.loc[missing, "area_ha"] * 1e4 / np.pi)).clip(lower=20),
            "color": [c for c, _ in painted], "tip": [tp for _, tp in painted]}, index=None),
            get_position="[lon, lat]", get_radius="radius", get_fill_color="color", pickable=True, radius_min_pixels=1.5)

        layers = [pdk.Layer("GeoJsonLayer", id="parcels_poly", data=fe, pickable=True, stroked=True,
                            get_fill_color="properties.fill", get_line_color=[250, 251, 252, 90],
                            line_width_min_pixels=0.5),
                  pdk.Layer("GeoJsonLayer", data=geojson("fields"), stroked=True, filled=False,
                            get_line_color=[22, 33, 62], line_width_min_pixels=2),
                  pdk.Layer("TextLayer", data=[{"id": i, "pos": [p["lon"], p["lat"]]} for i, p in fields().items()],
                            get_position="pos", get_text="id", get_size=15, get_color=[22, 33, 62],
                            get_pixel_offset=[0, -22], outline_width=4, outline_color=[255, 255, 255],
                            font_settings={"sdf": True})]
        if len(missing):
            layers.insert(1, dots)
        ev = st.pydeck_chart(pdk.Deck(map_style=None, layers=layers, tooltip={"text": "{tip}"},
                                      initial_view_state=pdk.ViewState(latitude=(par.lat.min() + par.lat.max()) / 2,
                                                                       longitude=(par.lon.min() + par.lon.max()) / 2,
                                                                       zoom=9.6 if scope == "bbox" else 7.4)),
                             height=560, on_select="rerun", selection_mode="single-object", key=f"ls_map_{scope}")
        if var != "crops":
            legend([(PALE, t("region.map.legend_low"), True), (HUE, t("region.map.legend_high"), True),
                    (GREY_LIGHT, t("region.map.legend_off"), True)])
        else:
            legend([(CROPS[g_], t("region.crop." + g_), False)
                    for g_ in ("beet", "cereal", "maize", "legume", "veg", "grass")]
                   + [(GREY_LIGHT, t("region.crop.other"), False)])
        source_line(t("region.map.unit"), t("region.map.source"), t("region.map.period", start=first, end=last))

    def parcel_card(pid):
        """One clicked parcel: what it sent or received, and every crop since 2017 (the same colours as the crop map)."""
        pid = int(pid)
        row = par.loc[pid]
        lines = []
        if var == "spread":
            if yr is None:
                lines.append(t("region.parcel.spread_acc", seasons=num(int(acc.years.get(pid, 0))),
                               ha=num(float(acc.reach.get(pid, 0.0)) / max(int(acc.years.get(pid, 0)), 1))))
            else:
                nur = pressure(yr, r, scope)[0].set_index("id")
                pos = nur.impact.rank(ascending=False, method="min").get(pid)
                if pos:
                    lines.append(t("region.parcel.rank", k=num(int(pos)), n=num(len(nur)),
                                   ha=num(float(nur.impact.get(pid, 0.0)) / max(float(nur.nursery_ha.get(pid, 0.0)), 1e-9))))
        elif var == "received":
            if yr is None:
                lines.append(t("region.parcel.recv_acc", seasons=num(int(acc.recv_years.get(pid, 0))),
                               ha=num(float(acc.got.get(pid, 0.0)) / max(int(acc.recv_years.get(pid, 0)), 1))))
            else:
                beet = pressure(yr, r, scope)[1].set_index("id")
                pos = beet.pressure.rank(ascending=False, method="min").get(pid)
                if pos:
                    lines.append(t("region.parcel.recv_rank", k=num(int(pos)), n=num(len(beet)),
                                   ha=num(float(beet.pressure.get(pid, 0.0)))))
        chips = "".join(f'<span class="cc-chip" style="--c:{CROPS[crop_group(names_de.get(int(row[f"c{y_}"]), ""))]}">'
                        f'<i>{y_}</i>{names.get(int(row[f"c{y_}"]), "–")}</span>' for y_ in range(2017, last + 1))
        with st.container(key="card_parcel"):
            st.html(f'<h3 style="margin:0 0 6px">{t("region.parcel.title", id=pid, ha=num(row.area_ha, 1))}</h3>'
                    + "".join(f'<p style="margin:0 0 8px">{x}</p>' for x in lines))
            if var != "crops" and (ps := partners(scope, pid, var, yr, r)):
                st.html(f'<p class="cc-note" style="margin:8px 0 4px">{t("region.parcel." + ("victims" if var == "spread" else "sources"))}</p>'
                        + '<table class="cc-table">' + "".join(
                            f'<tr><td><b>{t("region.parcel.pid", id=num(a_))}</b></td><td>{pct(b_)}</td>'
                            f'<td>{num(c_, 1)} km</td></tr>' for a_, b_, c_ in ps) + "</table>")
            st.html(f'<p class="cc-note" style="margin:8px 0 4px">{t("region.parcel.history", start=2017, end=last)}</p>'
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

    with right:
        picked = next((o["properties"]["id"] for objs in ev.selection.objects.values() for o in objs), None)
        if picked is None:
            st.caption(t("region.parcel.hint"))
        else:
            parcel_card(picked)

footer()
