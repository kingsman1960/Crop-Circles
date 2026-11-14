"""Neighbours: the feed of the region (notes, questions, alerts to the plant-protection office) and, for the office,
the advisor and the administrator, their inbox and the accounts.

Flow: the signed-in account (accounts.user()) writes a post with a kind and, optionally, one of its fields; everyone in
the region reads it in "Everything"; alerts also appear under "Alerts" and, until the office has replied, in the
officials' "Inbox". A post about a field links to *My field* for accounts that own that field. The alert's author gets
a mailto button whose body carries the copilot fact card (the page's own figures), so the office receives the data
with the question. All storage is in accounts.py; this file only renders and calls it."""
import urllib.parse
from datetime import datetime

import streamlit as st

import accounts
import copilot
from data import fields, footer, header
from i18n import day, lang, t

KINDS = ("note", "question", "alert")  # labels: community.kind.<key> in the locales
u = accounts.user()  # never None here: app.py gates every platform page
region = u["region"]
mine = accounts.my_fields(list(fields()))
official = u["role"] in ("advisor", "authority", "admin")
posts = accounts.feed(region)
alerts = [p for p in posts if p["kind"] == "alert"]
# an alert is open until someone from the plant-protection office has replied in its thread
open_alerts = [p for p in alerts if not any(accounts.display(r["author"])[1] == "authority" for r in p["replies"])]
header(t("community.title", region=region),
       t("community.sub", n=len(posts), alerts=len(alerts), open=len(open_alerts)))


def when(iso):
    """UTC timestamp from the database -> the reader's local date and time, in the reader's language."""
    d = datetime.fromisoformat(iso).astimezone()
    return f"{day(d)}, {d:%H:%M}"


def show(p, pane):
    """One post with its replies and a reply box; `pane` keeps widget keys unique when a post is in several tabs."""
    name, role = accounts.display(p["author"])
    with st.container(key=f"card_post_{pane}_{p['id']}"):
        tag = f'<span class="cc-note">{t("community.role." + role)}</span>'
        kind = f' · <b class="cc-level {"high" if p["kind"] == "alert" else "low"}">{t("community.kind." + p["kind"])}</b>' if p["kind"] != "note" else ""
        where = f' · {t("community.about", id=p["field"])}' if p["field"] else ""
        st.html(f'<p style="margin:0 0 4px"><b>{name}</b> {tag}{kind}{where}<span class="cc-note"> · {when(p["created"])}</span></p>'
                f'<p style="margin:0 0 8px">{p["text"]}</p>')
        if p["field"] and p["field"] in mine:  # a link to the field page, only for accounts that may open it
            st.page_link("views/field.py", label=t("community.open", id=p["field"]), query_params={"field": p["field"], "lang": lang()})
        for r in p["replies"]:
            rn, rr = accounts.display(r["author"])
            st.html(f'<p class="cc-reply"><b>{rn}</b> <span class="cc-note">{t("community.role." + rr)} · {when(r["created"])}</span>'
                    f'<br>{r["text"]}</p>')
        if p["kind"] == "alert" and p["author"] == u["name"]:  # the author can forward the alert by e-mail, data attached
            body = t("community.mail_body", id=p["field"], text=p["text"]) + ("\n\n" + copilot.card(p["field"])[:1500] if p["field"] else "")
            st.link_button(t("community.mail"), "mailto:?" + urllib.parse.urlencode(
                {"subject": t("community.mail_subject", id=p["field"] or region), "body": body}, quote_via=urllib.parse.quote))
        # a form, so typing does not rerun the page; keys carry the pane because a post can be in several tabs
        with st.form(f"reply_{pane}_{p['id']}", border=False, clear_on_submit=True):
            a, b = st.columns([5, 1], vertical_alignment="bottom")
            text = a.text_input(t("community.reply"), key=f"reply_text_{pane}_{p['id']}", label_visibility="collapsed",
                                placeholder=t("community.reply"))
            if b.form_submit_button(t("community.send"), width="stretch") and text.strip():
                accounts.reply(p["id"], text)
                st.rerun()
        if u["role"] == "admin" and st.button(t("community.delete"), key=f"del_{pane}_{p['id']}"):
            accounts.delete_post(p["id"])
            st.rerun()


# --- write: one form for every kind of post ------------------------------------------------------------------------------
with st.container(key="card_compose"):
    st.markdown(t("community.compose"))
    with st.form("compose", border=False, clear_on_submit=True):
        a, b = st.columns([1, 1])
        kind = a.segmented_control(t("community.kind.label"), KINDS, default="note", format_func=lambda k: t("community.kind." + k), key="post_kind")
        field = b.selectbox(t("community.field"), [t("community.no_field"), *mine], key="post_field")
        field = field if field in mine else ""  # the first option is "no particular field"
        text = st.text_area(t("community.text"), key="post_text", height=90, placeholder=t("community.placeholder"))
        if st.form_submit_button(t("community.post"), type="primary") and text.strip():
            accounts.post(kind or "note", field, text)
            st.rerun()
    st.caption(t("community.alert_note"))

# --- read: tabs per audience (everyone / alerts / officials' inbox / administrator's accounts) ---------------------------------------------------------------------------------
tabs = [t("community.tab.all"), t("community.tab.alerts")] + ([t("community.tab.inbox")] if official else []) \
    + ([t("community.tab.accounts")] if u["role"] == "admin" else [])
panes = st.tabs(tabs)
with panes[0]:
    if not posts:
        st.caption(t("community.empty"))
    for p in posts:
        show(p, "all")
with panes[1]:
    st.caption(t("community.alerts_intro"))
    for p in alerts:
        show(p, "alerts")
if official:
    with panes[2]:
        st.caption(t("community.inbox_intro", n=len(open_alerts)))
        for p in open_alerts:
            show(p, "inbox")
if u["role"] == "admin":
    with panes[-1]:
        rows = "".join(f'<tr><td><b>{a["name"]}</b><span class="g">{a["display"]}</span></td><td>{t("community.role." + a["role"])}</td>'
                       f'<td>{a["fields"] or "–"}</td><td>{a["posts"]}</td></tr>' for a in accounts.accounts())
        st.html(f'<table class="cc-table"><thead><tr><th>{t("community.col.account")}</th><th>{t("community.col.role")}</th>'
                f'<th>{t("community.col.fields")}</th><th>{t("community.col.posts")}</th></tr></thead><tbody>{rows}</tbody></table>')
        st.caption(t("community.accounts_note", path=str(accounts.DB)))
footer()
