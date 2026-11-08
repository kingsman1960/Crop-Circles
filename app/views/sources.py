import pandas as pd
import streamlit as st

from data import content, footer, header, strategies
from i18n import t

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
with lit:
    for r in src["refs"].values():
        st.markdown(f"- [{r['title']}]({r['url']}) – {r['who']}")
with ai:
    st.markdown(t("know.ai"))
footer()
