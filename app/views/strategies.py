import altair as alt
import pandas as pd
import streamlit as st

import copilot
from data import (HUE, chart, content, fact_text, field_picker, model_note, neighbourhood, plan, planner_weights,
                  rank_options, strategies)
from engine import criteria, field_scores, priority_sliders
from i18n import num, pct, t
from plain import compare, fraction
from planner import crop_planner
from ui import dots, footer, header, source_line

picker = st.container()
fid, p = field_picker(picker)
title_row = st.container()  # written once the ranking is known
res = strategies()["fields"][fid]  # the pipeline's rotation calendars and field facts
ev = field_scores(fid)              # the engine's scores: three years on this block's plots, with planthopper pressure
crit, crops, refs = criteria(), content("crops"), content("sources")["refs"]
who = lambda k: refs[k]["who"].split(" – ")[0]
score = lambda sid, k: ev[sid]["scores"][k]

with st.container(key="card_priorities"):
    st.markdown(t("grow.priorities"))
    priority_sliders(list(crit))
    show_opt = st.toggle(t("grow.show_pea"), value=False, key="show_s4", persist_state="session")

order, total, cards = rank_options(fid, optional=show_opt)


def note(sid, k):
    """Model notes are worked out per field; rule notes come from the cards; the engine adds its numbers."""
    s = score(sid, k)
    text = model_note(k, s) if s["basis"] == "model" else cards[sid].get("scores", {}).get(k, {}).get("note", "")
    return " ".join(x for x in (text, s.get("detail", "")) if x)


best = order[0]
with title_row:
    if best == "S0":
        sub = t("grow.sub.s0")
    else:
        lower = lambda k: crit[k]["label"][:1].lower() + crit[k]["label"][1:] if t("app.language") == "Language" else crit[k]["label"]
        gains = [lower(k) for k in crit if score(best, k)["score"] - score("S0", k)["score"] >= 0.3]
        losses = [lower(k) for k in crit if score(best, k)["score"] - score("S0", k)["score"] <= -0.3]
        sub = (t("grow.sub.best", name=cards[best]["name"], gains=t("common.and").join(gains[:2]) or "–")
               + (t("grow.sub.worse", losses=t("common.and").join(losses[:2])) if losses else "") + ".")
    header(t("grow.title", id=fid), sub)

# --- the comparison, in words ---------------------------------------------------
head = "".join(f'<th title="{c["help"]}">{c["label"]}</th>' for c in crit.values())
rows = ""
for rank, sid in enumerate(order, 1):
    seq = " → ".join(crops[c]["label"] for c in cards[sid]["sequence"])
    if sid == "S0":
        cells = "".join(f'<td>{dots(score(sid, k)["score"])}<span class="g">{num(score(sid, k)["score"], 1)} · {t("grow.now")}</span></td>'
                        for k in crit)
    else:
        cells = ""
        for k in crit:
            word, tone = compare(score(sid, k)["score"] - score("S0", k)["score"])
            cells += f'<td>{dots(score(sid, k)["score"])}<span class="g {tone}">{num(score(sid, k)["score"], 1)} · {word}</span></td>'
    tag = t("grow.best") if rank == 1 else t("grow.rank", n=rank)
    rows += (f'<tr class="{"top" if rank == 1 else ""}"><td><span class="cc-note">{tag}</span><br><b>{cards[sid]["name"]}</b>'
             f'<span class="g">{seq}</span></td>{cells}</tr>')
st.html(f'<div style="overflow-x:auto"><table class="cc-table cc-compare"><thead><tr><th>{t("grow.option")}</th>{head}</tr>'
        f'</thead><tbody>{rows}</tbody></table></div>'
        f'<p class="cc-note" style="margin-top:6px">{t("grow.table_note", id=fid)}</p>')

# --- the planthopper depends on the neighbours ------------------------------------
n = neighbourhood(fid, plan(2025, 1000, 0.2, "balanced", planner_weights())[0], 1000)
st.space("small")
with st.container(key="card_neighbours"):
    a, b = st.columns([3, 1], vertical_alignment="center")
    own = (t("grow.neighbours_none") if n["own"] < 0.05 * n["total"]
           else t("grow.neighbours_some", pct=pct(n["own"] / n["total"])))
    a.markdown(t("grow.neighbours", own=own, id=fid, fraction=fraction(1 - n["after"] / max(n["total"], 1e-9))))
    if b.button(t("grow.see_region"), width="stretch"):
        st.switch_page("views/landscape.py")

# --- one card per option -------------------------------------------------------------
for rank, sid in enumerate(order, 1):
    s, r_ = cards[sid], res["strategies"][sid]
    st.space("small")
    title = t("grow.card.best", name=s["name"]) if rank == 1 else t("grow.card.option", n=rank, name=s["name"])
    with st.expander(f"**{title}**  ({num(total[sid], 1)} / 5)", key=f"card_{sid}"):
        extra = [t("grow.card.cover", crops=", ".join(crops[c]["label"] for c in s["cover_before"]))] + \
                ([t("grow.card.mulch")] if s["mulch"] else [])
        st.html('<div class="cc-seq">'
                + " → ".join(f'<span style="white-space:nowrap"><i style="background:{crops[c]["color"]}"></i>'
                             f'{crops[c]["label"]}</span>' for c in s["sequence"])
                + f' <span class="cc-note">+ {", ".join(extra)}</span></div>')
        left, right = st.columns([1.15, 1], gap="large")
        with left:
            st.markdown(f"{t('grow.card.why')} {s['why']}")
            st.markdown(t("grow.card.data"))
            st.html('<ul class="cc-list">' + "".join(
                f'<li>{text} <span class="cc-note">({source})</span></li>'
                for text, source in (fact_text(k, res["facts"][k]) for k in s["facts"])) + "</ul>")
            st.markdown(t("grow.card.gain"))
            st.html('<ul class="cc-list">' + "".join(f"<li>{i}</li>" for i in s["benefits"]) + "</ul>")
        with right:
            st.markdown(t("grow.card.scores"))
            st.html("".join(
                f'<div class="cc-score"><span>{c["label"]}</span><span class="n">{dots(score(sid, k)["score"])} {num(score(sid, k)["score"], 1)}</span>'
                f'<span class="g">{note(sid, k)} {t("grow.card.how_sure", x=t("common.uncertainty." + score(sid, k)["uncertainty"]))}'
                + (" " + t("grow.card.sources", x=", ".join(who(x) for x in s["scores"][k]["ref"]))
                   if k in s.get("scores", {}) and s["scores"][k].get("ref") else "")
                + "</span></div>" for k, c in crit.items()))
        c1, c2 = st.columns([1.15, 1], gap="large")
        for col, title, items in [(c1, t("grow.card.unknown"), s["gaps"]), (c2, t("grow.card.advisor"), s["risks"])]:
            col.markdown(title)
            col.html('<ul class="cc-list">' + "".join(f"<li>{i}</li>" for i in items) + "</ul>")

        st.markdown(t("grow.card.bare"))
        m = pd.DataFrame(r_["months"])
        m["what"] = m.state.map(lambda x: crops[x]["label"] if x in crops else t("grow.state." + x))
        m["year"] = m.year.map(lambda y: t("grow.year", n=y))
        m["start"] = pd.to_datetime(dict(year=2001, month=m.month, day=1))
        m["end"] = m.start + pd.offsets.MonthBegin(1)
        chart(alt.Chart(m).mark_bar(stroke="#ffffff", strokeWidth=2).encode(
            x=alt.X("start:T", title=None, axis=alt.Axis(format="%b", tickCount=12)), x2="end:T",
            y=alt.Y("year:N", title=None),
            color=alt.Color("bare:Q", legend=None, scale=alt.Scale(domain=[0, 1], range=["#f1f3f6", HUE], interpolate="rgb")),
            tooltip=["year", alt.Tooltip("start:T", format="%B", title=t("grow.card.month")),
                     alt.Tooltip("what:N", title=t("grow.card.on_field")),
                     alt.Tooltip("bare:Q", format=".0%", title=t("grow.card.bare_share"))]),
            width="stretch", height=40 + 30 * m.year.nunique())
        source_line(t("grow.card.bare_unit"),
                    t("grow.card.bare_source") + (t("grow.card.bare_lit", crops=", ".join(
                        crops[c]["label"] for c in r_["literature_dates"])) if r_["literature_dates"] else ""),
                    t("grow.card.bare_period", ero=pct(r_["erosion_rel"]), wat=pct(r_["water_rel"])))
st.space("medium")
crop_planner(fid, p)
st.space("medium")
copilot.panel(fid, [(t("grow.title", id=fid), [sub])], "grow", ("ranking", "tradeoff", "summary"))
footer()
