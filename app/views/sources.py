import pandas as pd
import streamlit as st

import altair as alt

from data import GREY, INK, POS, chart, content, region_test, strategies
from i18n import num, t
from ui import footer, header, source_line

src = content("sources")
ds = pd.DataFrame(src["dataset"])
header(t("know.title"), t("know.sub", n=len(ds), nasa=int(ds.nasa.sum())))
words, data_tab, method_tab, lit, ai = st.tabs([t("know.tab." + k) for k in ("words", "data", "method", "literature", "ai")])
with words:
    q = st.text_input(t("know.search"), placeholder=t("know.search_placeholder"), key="gloss_q").lower()
    terms = [g for g in content("glossary").values() if q in (g["term"] + g["text"]).lower()]
    for col, g in zip(st.columns(2, gap="large") * len(terms), terms):
        col.markdown(f"**{g['term']}**  \n{g['text']}")
    if not terms:
        st.caption(t("know.no_match", q=q))
    st.subheader(t("know.numbers_title"))
    rows = "".join(f"<tr><td><b>{m['label']}</b><span class='g'>{m['unit']}</span></td><td>{m['definition']} "
                   f"<span class='g'>{m['meaning']}</span></td></tr>" for m in content("indicators").values())
    st.html(f'<table class="cc-table"><thead><tr><th>{t("know.col.number")}</th><th>{t("know.col.meaning")}</th></tr>'
            f'</thead><tbody>{rows}</tbody></table>')
with data_tab:
    rows = "".join(
        f"<tr><td><b>{d.name}</b><span class='g'>{'NASA, ' if d.nasa else ''}{t('know.status.' + d.status)}</span></td>"
        f"<td>{d.period}<span class='g'>{d.resolution}</span></td><td>{d.used_for}<span class='g'>{d.licence}</span></td></tr>"
        for d in ds.itertuples())
    st.html(f'<div style="overflow-x:auto"><table class="cc-table"><thead><tr><th>{t("know.col.dataset")}</th>'
            f'<th>{t("know.col.years")}</th><th>{t("know.col.use")}</th></tr></thead><tbody>{rows}</tbody></table></div>')
with method_tab:
    st.caption(t("know.method_note"))
    st.markdown(t("know.method", last=strategies()["recent_years"][1]))
    if rt := region_test():  # the region-wide planthopper edge test, in three charts
        ix, PINK = rt["index"], "#b03a72"
        st.subheader(t("know.evidence.title"))
        st.markdown(t("know.evidence.intro", n=num(ix["ndre"]["n"]), x=num(abs(ix["ndre"]["adjacent_coef"]), 3),
                      r=ix["ndre"]["decay"]["best_r_m"], lo=ix["ndre"]["decay"]["r_band_m"][0], hi=ix["ndre"]["decay"]["r_band_m"][1]))
        names = {"ndvi": "NDVI", "gndvi": "GNDVI", "ndre": "NDRE"}
        roles = {"adjacent": t("know.evidence.adjacent"), "control": t("know.evidence.control")}
        seasons = pd.DataFrame([{"season": str(y), "index": names[k], "role": roles[r], "delta": v[f"mean_{r}"]}
                                for k in names for y, v in ix[k]["per_season"].items() for r in roles])
        a, b = st.columns(2, gap="large")
        with a:
            st.markdown(f"**{t('know.evidence.fig1')}**")
            chart(alt.Chart(seasons).mark_bar().encode(
                x=alt.X("role:N", title=None, axis=None), y=alt.Y("delta:Q", title=t("know.evidence.delta")),
                color=alt.Color("role:N", scale=alt.Scale(domain=list(roles.values()), range=[PINK, GREY]), legend=alt.Legend(orient="bottom", title=None)),
                column=alt.Column("season:N", title=None), row=alt.Row("index:N", title=None),
                tooltip=["season:N", "index:N", "role:N", alt.Tooltip("delta:Q", format="+.3f")]).properties(width=70, height=80), width="content")
        with b:
            st.markdown(f"**{t('know.evidence.fig2')}**")
            bins = pd.DataFrame(ix["ndre"]["bins"]).assign(band=lambda d: d.lo.astype(str) + "–" + d.hi.astype(str) + " m",
                                                          lo_ci=lambda d: d["mean"] - 1.96 * d["sem"], hi_ci=lambda d: d["mean"] + 1.96 * d["sem"],
                                                          near=lambda d: d.hi <= 50)
            base = alt.Chart(bins).encode(x=alt.X("band:N", title=t("know.evidence.distance"), sort=None, axis=alt.Axis(labelAngle=0, labelFontSize=9)))
            chart(base.mark_bar().encode(y=alt.Y("mean:Q", title=t("know.evidence.delta_adj")),
                                         color=alt.Color("near:N", scale=alt.Scale(domain=[True, False], range=[PINK, GREY]), legend=None),
                                         tooltip=["band:N", alt.Tooltip("mean:Q", format="+.3f"), alt.Tooltip("n:Q", title="n")])
                  + base.mark_rule(color=INK).encode(y="lo_ci:Q", y2="hi_ci:Q"), width="stretch", height=260)
        st.markdown(f"**{t('know.evidence.fig3')}**")
        prof = pd.DataFrame([{"r": p["r_m"], "index": names[k], "rel": p["llf"] - max(q["llf"] for q in ix[k]["decay"]["profile"])}
                             for k in names for p in ix[k]["decay"]["profile"]])
        chart(alt.Chart(prof).mark_line(point=True).encode(
            x=alt.X("r:Q", title=t("know.evidence.r"), scale=alt.Scale(type="log"), axis=alt.Axis(values=[50, 100, 250, 500, 1000, 2000, 3000])),
            y=alt.Y("rel:Q", title=t("know.evidence.llf")),
            color=alt.Color("index:N", scale=alt.Scale(domain=list(names.values()), range=[GREY, POS, PINK]), legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["index:N", alt.Tooltip("r:Q", title="r (m)"), alt.Tooltip("rel:Q", format=".1f")])
              + alt.Chart(pd.DataFrame({"y": [-2]})).mark_rule(strokeDash=[4, 4], color=GREY).encode(y="y:Q"), width="stretch", height=240)
        source_line(t("know.evidence.unit"), t("know.evidence.source"), "2023–2025")
        st.caption(t("know.evidence.caveat"))
with lit:
    for r in src["refs"].values():
        st.markdown(f"- [{r['title']}]({r['url']}) – {r['who']}")
with ai:
    st.markdown(t("know.ai"))
footer()
