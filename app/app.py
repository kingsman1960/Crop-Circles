"""Crop Circles – Field Shift Kraichgau. Run from the repo root: streamlit run app/app.py"""
import streamlit as st

import accounts
import i18n
from data import ASSETS
from i18n import t

i18n.init()
st.set_page_config(page_title=t("app.title"), page_icon=str(ASSETS / "symbol.png"), layout="wide")
st.logo(str(ASSETS / "logo_bar.png"), size="large")
# Field journal: sage page, hairlines and tinted wells instead of white cards, serif titles, plain words, big type.
# The system is app/assets/tokens.css + app.css (Hallmark stamp in app.css); Streamlit takes them as one style block.
st.html("<style>" + "".join((ASSETS / f).read_text(encoding="utf-8") for f in ("tokens.css", "app.css")) + "</style>")

# The landing page explains the platform; the platform pages share their own bar (page links + language).
home = st.Page("views/home.py", title=t("home.nav_about"), default=True)
app_pages = [
    st.Page("views/field.py", title=t("nav.field"), url_path="field"),
    st.Page("views/strategies.py", title=t("nav.grow"), url_path="grow"),
    st.Page("views/landscape.py", title=t("nav.region"), url_path="region"),
    st.Page("views/community.py", title=t("nav.community"), url_path="neighbours"),
    st.Page("views/sources.py", title=t("nav.know"), url_path="know"),
]
page = st.navigation([home, *app_pages], position="hidden")
if page.url_path:  # inside the platform
    # The bar: page links (only once signed in), the account with a sign-out button, the language switch.
    # accounts.gate() below shows the sign-in card and stops the script when nobody is signed in.
    with st.container(key="appbar"):
        links, who, lang_col = st.columns([4.4, 1.8, 1.4], vertical_alignment="center")
        me = accounts.user()
        with links.container(horizontal=True, gap="medium", vertical_alignment="center"):
            for pg in app_pages if me else []:
                if pg.url_path == page.url_path:
                    st.markdown(f"**{pg.title}**")
                else:
                    st.page_link(pg, label=pg.title)
            st.page_link(home, label=t("home.nav_about"))
        if me:
            with who.container(horizontal=True, gap="small", vertical_alignment="center", horizontal_alignment="right"):
                st.markdown(f'<span class="cc-note">{me["display"]} · {t("community.role." + me["role"])}</span>', unsafe_allow_html=True)
                if st.button(t("login.out"), key="sign_out", type="tertiary"):
                    accounts.sign_out()
                    st.rerun()
        i18n.picker(lang_col)
    accounts.gate()
page.run()
