"""Under the planner map: your plan against the best match, both scored by engine.py as the same three years.

The best match grows its rotation on each plot; your plan grows what you painted in the first year and then the best
match's rotation from that crop; plots you have not painted follow the best match. So both columns are three years on
the same plots, with the same planthopper pressure from the neighbours, and they start out equal.
"""
from __future__ import annotations

import streamlit as st

import engine
from data import model_note
from i18n import num
from plain import compare, dots

TEXT = {
    "en": {"title": "Your plan against the best match", "best": "Best match: {name}", "plan": "Your custom plan",
           "sub": "{a}–{b} on your plots", "overall": "Overall, with your priorities",
           "years": "What each plan grows per plot, {a}–{b}", "plot": "Plot", "first": "{a} is what you painted; "
           "{a2} and {b} continue the best match's rotation from it. Bold: where your plan differs.",
           "shared": "{n} plots of other farmers' shared plans count with their real crops.", "method":
           "Both columns are {a}–{b} on your plots, scored the same way: the best match grows its rotation, your plan "
           "grows what you painted in {a} and then the best match's rotation from that crop; unpainted plots follow the "
           "best match. Planthopper and income include the pressure from neighbouring nurseries (flight range {km} km). "
           "{painted} of {total} ha painted."},
    "de": {"title": "Ihr Plan im Vergleich zur besten Option", "best": "Beste Option: {name}", "plan": "Ihr eigener Plan",
           "sub": "{a}–{b} auf Ihren Schlägen", "overall": "Gesamt, nach Ihren Prioritäten",
           "years": "Was jeder Plan je Schlag anbaut, {a}–{b}", "plot": "Schlag", "first": "{a} ist Ihre gemalte Kultur; "
           "{a2} und {b} setzen die Fruchtfolge der besten Option fort. Fett: wo Ihr Plan abweicht.",
           "shared": "{n} Schläge aus geteilten Plänen anderer Betriebe zählen mit ihren echten Kulturen.", "method":
           "Beide Spalten zeigen {a}–{b} auf Ihren Schlägen, gleich bewertet: die beste Option baut ihre Fruchtfolge an, "
           "Ihr Plan {a} das Gemalte und danach die Fruchtfolge der besten Option ab dieser Kultur; ungemalte Schläge "
           "folgen der besten Option. Zikade und Einkommen enthalten den Druck aus benachbarten Kinderstuben "
           "(Flugweite {km} km). {painted} von {total} ha bemalt."},
}


def plan_metrics(fid: str, p: dict, features: list[dict], year: int, lang: str = "en", others=()) -> None:
    tx = TEXT[lang]
    best, res = engine.compare_custom(fid, features, optional=st.session_state.get("show_s4", False), year=year,
                                      others=others)
    crit, w = engine.criteria(), res["weights"]
    a, b = res["first_year"], res["first_year"] + engine.HORIZON - 1
    B, C = res["best"]["scores"], res["custom"]["scores"]
    name = {s["id"]: s["name"] for s in engine.content("strategies")["strategy"]}[best]

    def note(k):
        s = C[k]
        text = model_note(k, s) if s["basis"] == "model" else ""
        return " ".join(x for x in (text, s.get("detail", "")) if x)

    rows = "".join(f'<tr><td><b>{c["label"]}</b><span class="g">{note(k)}</span></td>'
                   f'<td>{dots(B[k]["score"])}<span class="g">{num(B[k]["score"], 1)}</span></td>'
                   f'<td>{_change(B[k]["score"], C[k]["score"])}</td></tr>' for k, c in crit.items())
    ob, oc = round(engine.total(B, w), 1), round(engine.total(C, w), 1)
    rows += (f'<tr class="top"><td><b>{tx["overall"]}</b></td><td>{dots(ob)}<span class="g">{num(ob, 1)}</span></td>'
             f'<td>{_change(ob, oc)}</td></tr>')
    sub = f'<span class="g">{tx["sub"].format(a=a, b=b)}</span>'
    head = f'<th></th><th>{tx["best"].format(name=name)}{sub}</th><th>{tx["plan"]}{sub}</th>'
    st.subheader(tx["title"])
    st.html(f'<div style="overflow-x:auto"><table class="cc-table cc-compare"><thead><tr>{head}</tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')

    painted = sum(float(f["properties"].get("ha") or 0) for f in features if f["properties"].get("plan"))
    total = sum(float(f["properties"].get("ha") or 0) for f in features)
    _sequences(features, res, tx, a, b, lang)
    st.caption(tx["method"].format(a=a, b=b, km=num(st.session_state.get("ls_r", 1000) / 1000, 1),
                                   painted=num(painted, 1), total=num(total, 1))
               + (" " + tx["shared"].format(n=res["collab_plots"]) if res.get("collab_plots") else ""))


def _sequences(features, res, tx, a, b, lang):
    """A small table of what each plan grows per plot, so the three years are visible, not only scored."""
    import rotation
    label = lambda c: rotation.label(engine.PLANNER[c], lang) if c in engine.PLANNER else c.replace("_", " ").capitalize()
    rows = ""
    for n, f in enumerate(features, 1):
        pid = f["properties"]["id"]
        pb, pc = res["best"]["plans"].get(pid), res["custom"]["plans"].get(pid)
        if not pb:
            continue
        cells = lambda seq, other: " → ".join(f"<b>{label(c)}</b>" if c != o else label(c) for c, o in zip(seq, other))
        ha = float(f["properties"].get("ha") or 0)
        rows += (f'<tr><td>{tx["plot"]} {n} <span class="g">{num(ha, 2 if ha < 1 else 1)} ha</span></td>'
                 f'<td>{" → ".join(label(c) for c in pb)}</td><td>{cells(pc, pb)}</td></tr>')
    head = (f'<thead><tr><th>{tx["plot"]}</th><th>{tx["best"].format(name="").rstrip(": ")}</th>'
            f'<th>{tx["plan"]}</th></tr></thead>')
    with st.expander(tx["years"].format(a=a, b=b)):
        st.html(f'<table class="cc-table">{head}<tbody>{rows}</tbody></table>')
        st.caption(tx["first"].format(a=a, a2=a + 1, b=b))


def _change(t0, t1):
    word, tone = compare(t1 - t0)
    delta = f" ({'+' if t1 > t0 else '−'}{num(abs(t1 - t0), 1)})" if abs(t1 - t0) >= 0.05 else ""
    return f'{dots(t1)}<span class="g {tone}">{num(t1, 1)} · {word}{delta}</span>'
