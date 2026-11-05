"""Crop Circles – Field Shift Kraichgau. Run from the repo root: streamlit run app/app.py"""
import streamlit as st

import i18n
from data import ASSETS, HUE, INK
from i18n import t

i18n.init()
st.set_page_config(page_title=t("app.title"), page_icon=str(ASSETS / "symbol.png"), layout="wide")
st.logo(str(ASSETS / "logo_bar.png"), size="large")
# Field journal (see .streamlit/config.toml): sage page, white rounded cards, serif titles, plain words, big type.
st.html(f"""<style>
:root {{ --ink: {INK}; --muted: #4f5a6b; --border: #dbe2d6; --rule: #e9eee5; --surface: #ffffff; --soft: #e6ebe2;
        --hue: {HUE}; --pos: #2f6a3f; --ground: #f1f4ee; --radius: 20px; }}
.block-container {{ max-width: 1180px; padding: 3.5rem 2rem 0; }}
.st-key-appbar {{ border-bottom: 1px solid var(--border); padding-bottom: 6px; margin-bottom: 8px; }}
.st-key-appbar [data-testid=\"stPageLink\"] p, .st-key-appbar p {{ font-size: 16px; }}
.st-key-appbar [data-testid=\"stPageLink\"] a {{ text-decoration: none; }}
.st-key-hero {{ background: var(--ink); border-radius: var(--radius); padding: 40px 44px; }}
.st-key-hero h1, .st-key-hero p {{ color: #f1f4ee; }}
.st-key-hero h1 {{ font-size: 48px !important; line-height: 1.08 !important; }}
.st-key-hero .cc-sub {{ color: #cdd6e3; font-size: 19px; max-width: 58ch; }}
.st-key-hero a {{ color: #f1f4ee !important; }}
[data-testid="stButtonGroup"] button {{ padding-left: 10px; padding-right: 10px; }}
[class*="st-key-shot_"] img {{ border-radius: 14px; border: 1px solid var(--border); box-shadow: 0 12px 32px rgba(22,33,62,.10); }}
.st-key-final {{ background: var(--soft); border-radius: var(--radius); padding: 36px 40px; }}
@media (max-width: 640px) {{ .st-key-hero {{ padding: 24px 20px; }} .st-key-hero h1 {{ font-size: 30px !important; }} }}
/* tabular figures only where digits line up: Inter's tnum also widens hyphens */
.cc-table td.num {{ font-variant-numeric: tabular-nums; }}
h3, .cc-risk-head h3 {{ font-family: "Newsreader", Georgia, serif; font-weight: 600; }}
/* risk cards in one row end level: the wrapper grows to the row height */
[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-card_risk"]) {{ flex-grow: 1; }}
div[class*="st-key-card_risk"] > [data-testid="stElementContainer"] {{ flex-grow: 1; }}
div[class*="st-key-card_risk"] [data-testid="stHtml"], .cc-risk {{ height: 100%; }}
.cc-risk {{ display: flex; flex-direction: column; }}
.cc-risk .cc-risk-help {{ margin-top: auto; }}
header[data-testid="stHeader"] {{ background: var(--ground); border-bottom: 1px solid var(--border); }}
[data-testid="stAppDeployButton"] {{ display: none; }}
img.stLogo {{ height: 30px; max-width: none; }}
[data-testid="stTopNavLink"] p {{ font-size: 15px; font-weight: 500; color: var(--muted); }}
[data-testid="stTopNavLink"][aria-current="page"] p, [data-testid="stTopNavLink"]:hover p {{ color: var(--ink); }}
@media (max-width: 900px) {{ img.stLogo {{ height: 22px; }} [data-testid="stTopNavLink"] p {{ font-size: 14px; }} }}
h1 {{ letter-spacing: -0.015em; line-height: 1.15 !important; padding-bottom: 0 !important; }}
h2, h3 {{ letter-spacing: -0.005em; }}
p, li {{ line-height: 1.55; }}
.cc-sub {{ font-size: 18px; line-height: 1.55; max-width: 64ch; margin: 6px 0 4px; }}
.cc-sub b {{ font-weight: 600; }}
.cc-note {{ font-size: 14px; color: var(--muted); }}
[data-testid="stCaptionContainer"] p {{ font-size: 14px; color: var(--muted); }}
div[class*="st-key-card"] {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
                            padding: 24px 26px; }}
div[class*="st-key-card_priorities"] {{ background: var(--soft); border-color: transparent; }}
div[class*="st-key-card_best"] {{ background: var(--ink); border-color: var(--ink); }}
div[class*="st-key-card_best"] h3, div[class*="st-key-card_best"] p {{ color: #f1f4ee; }}
div[class*="st-key-card_best"] .cc-note {{ color: #b8c3d6; }}
/* risk cards */
.cc-risk-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; }}
.cc-risk-head h3 {{ margin: 0; padding: 0; font-size: 22px; }}
.cc-risk-text {{ font-size: 17px; margin: 0 0 10px; }}
.cc-risk-help {{ margin: 10px 0 4px; padding: 12px 14px; background: var(--ground); border-radius: 12px; }}
.cc-level {{ display: inline-flex; align-items: center; gap: 8px; padding: 4px 12px 4px 10px; border-radius: 999px;
            background: var(--ground); font-weight: 600; font-size: 14px; white-space: nowrap; }}
.cc-level i {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
/* numbers in one strip */
.cc-kpis {{ display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); background: var(--surface);
           border: 1px solid var(--border); border-radius: var(--radius); }}
.cc-kpi {{ padding: 18px 20px 16px; border-left: 1px solid var(--rule); min-width: 0; }}
.cc-kpi:first-child {{ border-left: 0; }}
.cc-kpi .l {{ font-size: 14px; color: var(--muted); }}
.cc-kpi .v {{ font-size: 26px; line-height: 1.25; margin-top: 6px; font-weight: 500; white-space: nowrap; overflow: hidden;
             text-overflow: ellipsis; }}
.cc-kpi .v small {{ font-size: 15px; color: var(--muted); margin-left: 4px; font-weight: 400; }}
.cc-kpi .d {{ font-size: 14px; color: var(--muted); margin-top: 2px; }}
.cc-kpi .d.good {{ color: var(--pos); }} .cc-kpi .d.bad {{ color: var(--hue); }}
.cc-kpi.lead .v {{ font-size: 32px; }}
@media (max-width: 640px) {{
  .cc-kpis {{ grid-template-columns: 1fr 1fr; }}
  .cc-kpi {{ border-left: 0; border-top: 1px solid var(--rule); }}
  .cc-kpi:nth-child(even) {{ border-left: 1px solid var(--rule); }}
  .cc-kpi:nth-child(-n+2) {{ border-top: 0; }}
  .cc-kpi:last-child:nth-child(odd) {{ grid-column: 1 / -1; }}
  .cc-risk-head {{ flex-wrap: wrap; }}
  h1 {{ font-size: 26px !important; }}
  .cc-sub {{ font-size: 16px; }}
}}
/* tables */
.cc-table {{ width: 100%; border-collapse: collapse; font-size: 15px; }}
.cc-table th {{ text-align: left; font-weight: 500; font-size: 14px; color: var(--muted); padding: 0 12px 10px;
               border-bottom: 1px solid var(--border); }}
.cc-table td {{ padding: 14px 12px; border-bottom: 1px solid var(--rule); vertical-align: top; }}
.cc-table tr:last-child td {{ border-bottom: 0; }}
.cc-table .num {{ text-align: right; white-space: nowrap; }}
.cc-table tr.top td {{ background: #f5f8f2; }}
.cc-table tr.top td:first-child {{ box-shadow: inset 4px 0 0 var(--pos); }}
.cc-table .g {{ color: var(--muted); font-size: 14px; display: block; margin-top: 2px; }}
.cc-table .g.good {{ color: var(--pos); font-weight: 500; }} .cc-table .g.bad {{ color: var(--hue); font-weight: 500; }}
.cc-dots {{ display: inline-flex; gap: 4px; vertical-align: middle; }}
.cc-dots i {{ width: 9px; height: 9px; border-radius: 50%; background: #d3dacf; display: inline-block; }}
.cc-dots i.on {{ background: var(--ink); }}
.cc-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin: 0 2px 1px 6px; vertical-align: middle; }}
.cc-key {{ display: inline-flex; align-items: center; gap: 6px; margin: 0 18px 4px 0; font-size: 14px; color: var(--muted); }}
.cc-key i {{ display: inline-block; width: 11px; height: 11px; border-radius: 3px; }}
.cc-key i.round {{ border-radius: 50%; }}
.cc-seq {{ font-size: 16px; }} .cc-seq i {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; }}
.cc-list {{ margin: 0 0 8px; padding-left: 20px; }} .cc-list li {{ margin-bottom: 8px; }}
.cc-score {{ display: grid; grid-template-columns: 1fr auto; gap: 2px 12px; padding: 12px 0; border-bottom: 1px solid var(--rule); }}
.cc-score:last-child {{ border-bottom: 0; }}
.cc-score .n {{ text-align: right; }}
.cc-score .g {{ grid-column: 1 / -1; font-size: 14px; color: var(--muted); }}
/* the close */
.st-key-footer {{ background: var(--ink); border-radius: var(--radius); padding: 32px 36px; margin: 64px 0 32px; }}
.st-key-footer p, .st-key-footer li {{ color: #c9d1dc; font-size: 14px; }}
.st-key-footer strong {{ color: #ffffff; font-weight: 500; }}
.st-key-footer a {{ color: #ffffff; }}
[data-testid="stTab"] p {{ font-size: 15px; }}
[data-testid="stExpander"] details {{ border-radius: var(--radius); background: var(--surface); }}
[data-testid="stExpander"] summary p {{ font-weight: 500; }}
</style>""")

# The landing page explains the platform; the platform pages share their own bar (page links + language).
home = st.Page("views/home.py", title=t("home.nav_about"), default=True)
app_pages = [
    st.Page("views/field.py", title=t("nav.field"), url_path="field"),
    st.Page("views/strategies.py", title=t("nav.grow"), url_path="grow"),
    st.Page("views/landscape.py", title=t("nav.region"), url_path="region"),
    st.Page("views/sources.py", title=t("nav.know"), url_path="know"),
]
page = st.navigation([home, *app_pages], position="hidden")
if page.url_path:  # inside the platform
    with st.container(key="appbar"):
        links, lang_col = st.columns([5, 1], vertical_alignment="center")
        with links.container(horizontal=True, gap="medium", vertical_alignment="center"):
            for pg in app_pages:
                if pg.url_path == page.url_path:
                    st.markdown(f"**{pg.title}**")
                else:
                    st.page_link(pg, label=pg.title)
            st.page_link(home, label=t("home.nav_about"))
        i18n.picker(lang_col)
page.run()
