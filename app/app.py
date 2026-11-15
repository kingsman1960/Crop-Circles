"""Crop Circles – Field Shift Kraichgau. Run from the repo root: streamlit run app/app.py"""
import streamlit as st

import accounts
import i18n
import ui
from data import ASSETS
from i18n import t

i18n.init()
st.set_page_config(page_title=t("app.title"), page_icon=str(ASSETS / "symbol.png"), layout="wide")
st.logo(str(ASSETS / "logo_bar.png"), size="large")
# The survey-map design: white paper, ink lines, three story colours (see assets/tokens.css for the rules).
# Theme and font come from .streamlit/config.toml; Streamlit takes the two stylesheets as one style block.
st.html("<style>" + "".join((ASSETS / f).read_text(encoding="utf-8") for f in ("tokens.css", "app.css")) + "</style>")
ui.register_chart_theme()

# The landing page tells the story; the platform pages are four sections (plus the sources), sharing one bar.
home = st.Page("views/home.py", title=t("home.nav_about"), default=True)
steps = [
    st.Page("views/field.py", title=t("nav.field"), url_path="field"),
    st.Page("views/strategies.py", title=t("nav.grow"), url_path="grow"),
    st.Page("views/landscape.py", title=t("nav.region"), url_path="region"),
    st.Page("views/community.py", title=t("nav.community"), url_path="neighbours"),
]
know = st.Page("views/sources.py", title=t("nav.know"), url_path="know")
page = st.navigation([home, *steps, know], position="hidden")
if page.url_path:  # inside the platform
    # The bar: the four pages as pills (only once signed in; the current one is filled), then the sources and the
    # landing page; on the right the account with a sign-out button and the language switch, in one flex row so
    # a long name wraps instead of running into the switch.
    # accounts.gate() below shows the sign-in card and stops the script when nobody is signed in.
    with st.container(key="appbar"):
        links, right = st.columns([5, 3], vertical_alignment="center")
        me = accounts.user()
        with links.container(horizontal=True, gap="medium", vertical_alignment="center"):
            if me:
                with st.container(horizontal=True, key="steps", width="content", vertical_alignment="center"):
                    for pg in steps:
                        if pg.url_path == page.url_path:
                            st.markdown(f"**{pg.title}**")
                        else:
                            st.page_link(pg, label=pg.title)
                if page.url_path == know.url_path:
                    st.markdown(f"**{know.title}**")
                else:
                    st.page_link(know, label=know.title)
            st.page_link(home, label=t("home.nav_about"))
        with right.container(horizontal=True, gap="small", vertical_alignment="center", horizontal_alignment="right"):
            if me:
                st.markdown(f'<span class="cc-note">{me["display"]}, {t("community.role." + me["role"])}</span>',
                            unsafe_allow_html=True)
                if st.button(t("login.out"), key="sign_out", type="tertiary"):
                    accounts.sign_out()
                    st.rerun()
            i18n.picker(st)
    accounts.gate()
page.run()
