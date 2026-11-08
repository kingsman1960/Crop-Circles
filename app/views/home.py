"""Landing page: what the platform does and how to use it; the button opens the platform."""
import streamlit as st

import i18n
from data import ASSETS, footer, kpis, landscape, strategies, table
from i18n import lang, num, t
from plain import fraction, of_ten

_, lang_col = st.columns([5, 1], vertical_alignment="center")
i18n.picker(lang_col)


def open_platform(where, key):
    if where.button(t("home.cta"), type="primary", key=key):
        st.switch_page("views/field.py")


def shot(page):
    """A real screenshot of the platform page in the reader's language (English if there is none)."""
    for tag in (lang(), "en"):
        f = ASSETS / "screens" / tag / f"{page}.png"
        if f.exists():
            return str(f)


# --- hero -------------------------------------------------------------------
with st.container(key="hero"):
    st.image(str(ASSETS / "logo_bar.png"), width=260)
    st.title(t("home.hero_title"))
    st.html(f'<p class="cc-sub">{t("home.hero_sub")}</p>')
    row = st.container(horizontal=True, vertical_alignment="center", gap="large")
    with row:
        open_platform(row, "cta_top")
        st.markdown(f"[{t('home.how_link')}](#how)", width="content")
st.caption(t("home.demo_note"))

# --- why now: four numbers from the data ---------------------------------------
summary = landscape()[2]["seasons"][-1]
facts = strategies()["fields"]["F1"]["facts"]
ind = table("indicators")
hot = ind[(ind.field == "F1") & (ind.source == "DWD") & (ind.indicator == "heat_days")]
st.space("medium")
st.subheader(t("home.why_title"))
kpis([(t("home.kpi_beet", season=summary["season"]), of_ten(summary["beet_to_wheat"]), None, t("home.kpi_beet_note"),
       None, None),
      (t("home.kpi_heat"), num(hot[hot.year.between(2015, 2024)].value.mean()), None,
       t("home.kpi_heat_note", then=num(hot[hot.year.between(1981, 2010)].value.mean())), "bad", None),
      (t("home.kpi_dry"), of_ten(facts["summer_dry"]["n"] / 10), None, t("home.kpi_dry_note"), None, None),
      (t("home.kpi_switch"), fraction(summary["targeted20_r1000"]), None, t("home.kpi_switch_note"), "good", None)],
     lead=0)

# --- what it does: the three parts of the platform, shown as they are ------------
st.space("medium")
st.subheader(t("home.features_title"))
for i, page in enumerate(("field", "grow", "region")):
    st.space("small")
    if i % 2:  # alternate sides; the picture always gets the wider column
        img_col, text_col = st.columns([1.4, 1], gap="large", vertical_alignment="center")
    else:
        text_col, img_col = st.columns([1, 1.4], gap="large", vertical_alignment="center")
    text_col.markdown(f"### {t(f'home.feature_{page}_title')}")
    text_col.markdown(t(f"home.feature_{page}_text"))
    if f := shot(page):
        img_col.container(key=f"shot_{page}").image(f, width="stretch", caption=t("home.shot", page=t("nav." + page)))

# --- how to use it ------------------------------------------------------------
st.space("medium")
st.subheader(t("home.steps_title"), anchor="how")
st.markdown("\n".join(f"{n}. {t(f'home.step_{n}')}" for n in range(1, 5)))

# --- who it is for, and the data behind it ----------------------------------------
st.space("medium")
a, b = st.columns(2, gap="large")
with a:
    st.subheader(t("home.users_title"))
    st.markdown(f"- {t('home.users_farmer')}\n- {t('home.users_advisor')}")
with b:
    st.subheader(t("home.data_title"))
    st.markdown(t("home.data_text"))

# --- the way in -------------------------------------------------------------------
st.space("medium")
with st.container(key="final"):
    a, b = st.columns([3, 1], vertical_alignment="center")
    a.markdown(f"### {t('home.final_title')}\n{t('home.final_text')}")
    open_platform(b, "cta_bottom")
footer()
