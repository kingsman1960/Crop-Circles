"""Landing page: the story (one field cannot stop the planthopper, a ring of neighbours can), the planthopper's
year, why now, the four steps of the platform, and the way in."""
import streamlit as st

import i18n
from data import ASSETS, landscape, strategies, table
from i18n import lang, num, t
from plain import fraction, of_ten
from ui import cycle, footer, hero_map, kpis, ring, s

# the language switch, right-aligned at its own width (a narrow column clipped it)
with st.container(horizontal=True, horizontal_alignment="right"):
    i18n.picker(st)


def open_platform(where, key):
    if where.button(t("home.cta"), type="primary", key=key):
        st.switch_page("views/field.py")


def shot(page):
    """A real screenshot of the platform page in the reader's language (English if there is none)."""
    for tag in (lang(), "en"):
        f = ASSETS / "screens" / tag / f"{page}.png"
        if f.exists():
            return str(f)


# --- hero: the claim on the left, the map that proves it on the right ------------------------------------------------
with st.container(key="hero"):
    text, pic = st.columns([1, 1.15], gap="large", vertical_alignment="center")
    with text:
        st.image(str(ASSETS / "logo_bar.png"), width=220)
        st.html(f'<h1 class="cc-hero-title">{s("hero.title")}</h1><p class="cc-hero-sub">{s("hero.sub")}</p>')
        row = st.container(horizontal=True, vertical_alignment="center", gap="large")
        with row:
            open_platform(row, "cta_top")
            st.markdown(f"[{t('home.how_link')}](#how)", width="content")
        st.caption(t("home.demo_note"))
    with pic:
        hero_map()

# --- the planthopper's year, and the turn: the fix is shared ---------------------------------------------------------
cycle()

# --- why now: four numbers from the data ---------------------------------------------------------------------------------
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

# --- the four steps of the platform, shown as they are ------------------------------------------------------------------
st.space("large")
st.html(f'<h2 class="cc-h2">{s("chapters.title")}</h2>')
chapters = [(page, t(f"home.feature_{page}_title"), t(f"home.feature_{page}_text")) for page in ("field", "grow", "region")]
chapters.append(("community", s("chapter.neighbours.title"), s("chapter.neighbours.text")))
for i, (page, title, body) in enumerate(chapters):
    st.space("small")
    f = shot(page)
    if not f:  # no screenshot yet: the text takes the full width
        text_col, img_col = st.container(), None
    elif i % 2:  # alternate sides; the picture always gets the wider column
        img_col, text_col = st.columns([1.4, 1], gap="large", vertical_alignment="center")
    else:
        text_col, img_col = st.columns([1, 1.4], gap="large", vertical_alignment="center")
    text_col.html(f'<div class="cc-chapter">{ring(i + 1, "md")}<div><h3>{title}</h3></div></div>')
    text_col.markdown(body)
    if img_col is not None:
        img_col.container(key=f"shot_{page}").image(f, width="stretch", caption=t("home.shot", page=t("nav." + page)))

# --- how to use it ------------------------------------------------------------------------------------------------------
st.space("large")
st.subheader(t("home.steps_title"), anchor="how")
st.markdown("\n".join(f"{n}. {t(f'home.step_{n}')}" for n in range(1, 5)))

# --- who it is for, and the data behind it --------------------------------------------------------------------------------
st.space("medium")
a, b = st.columns(2, gap="large")
with a:
    st.subheader(t("home.users_title"))
    st.markdown(f"- {t('home.users_farmer')}\n- {t('home.users_advisor')}")
with b:
    st.subheader(t("home.data_title"))
    st.markdown(t("home.data_text"))

# --- the way in --------------------------------------------------------------------------------------------------------------
st.space("large")
with st.container(key="final"):
    a, b = st.columns([3, 1], vertical_alignment="center")
    a.markdown(f"### {t('home.final_title')}\n{t('home.final_text')}")
    open_platform(b, "cta_bottom")
footer()
