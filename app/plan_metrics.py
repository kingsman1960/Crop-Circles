"""Under the planner map: your plan against the best match, both scored by engine.py as the same three years.

The best match grows its rotation on each plot; your plan grows what you painted in the first year and then the best
match's rotation from that crop; plots you have not painted follow the best match. So both columns are three years on
the same plots, with the same planthopper pressure from the neighbours, and they start out equal.
"""
from __future__ import annotations

import streamlit as st

import engine
from data import FLIGHT_M, model_note
from i18n import num
from plain import compare, dots

TEXT = {
    "en": {"title": "Your plan against the best match", "best": "Best match: {name}", "plan": "Your custom plan",
           "sub": "{a}–{b} on your plots", "overall": "Overall, with your priorities",
           "years": "What each plan grows per plot, {a}–{b}", "plot": "Plot", "auto": "auto",
           "first": "Your rotation is what you painted on the maps of {a}, {a2} and {b} (pick the year above the map). "
           "{a} unpainted counts as green fallow. A later year you have not painted is filled in (grey, auto): the best "
           "match's next crop, or another of its crops where that would break a rotation rule. Bold: where you differ.",
           "shared": "{n} plots of other farmers' shared plans count with their real crops.",
           "empty": "Your plan is empty: every plot counts as green fallow in {a}. Paint a crop on the map to build your plan.",
           "some_fallow": "{ha} of {total} ha have no crop in {a} and count as green fallow: no income, but covered soil, "
                          "some water use and no planthopper nursery. Paint every plot for a full plan.",
           "fallow_wins": "Your plan scores as well as the best match or better only because fallow land keeps soil, water "
                          "and the planthopper in check. It earns nothing in {a}: leaving land unplanted is not a real "
                          "strategy unless you mean to (for example an eco-scheme fallow).", "method":
           "Both columns are {a}–{b} on your plots, scored the same way: the best match grows its rotation, your plan grows "
           "what you painted on each year's map (unpainted {a}: green fallow; unpainted later years: filled in from the best "
           "match). Planthopper and income include the pressure from neighbouring nurseries (flight range {km} km). "
           "{painted} of {total} ha painted in {a}."},
    "de": {"title": "Ihr Plan im Vergleich zur besten Option", "best": "Beste Option: {name}", "plan": "Ihr eigener Plan",
           "sub": "{a}–{b} auf Ihren Schlägen", "overall": "Gesamt, nach Ihren Prioritäten",
           "years": "Was jeder Plan je Schlag anbaut, {a}–{b}", "plot": "Schlag", "auto": "auto",
           "first": "Ihre Fruchtfolge ist, was Sie auf den Karten {a}, {a2} und {b} gemalt haben (Jahr über der Karte wählen). "
           "{a} ungemalt zählt als Brache. Ein späteres Jahr ohne Bemalung wird ergänzt (grau, auto): die nächste Kultur "
           "der besten Option, oder eine andere ihrer Kulturen, wo jene eine Regel verletzt. Fett: wo Sie abweichen.",
           "shared": "{n} Schläge aus geteilten Plänen anderer Betriebe zählen mit ihren echten Kulturen.",
           "empty": "Ihr Plan ist leer: jeder Schlag zählt {a} als Brache. Malen Sie Kulturen auf die Karte, um Ihren Plan aufzubauen.",
           "some_fallow": "{ha} von {total} ha haben {a} keine Kultur und zählen als Brache: kein Einkommen, aber bedeckter "
                          "Boden, etwas Wasserverbrauch und keine Zikaden-Kinderstube. Bemalen Sie alle Schläge für einen vollständigen Plan.",
           "fallow_wins": "Ihr Plan schneidet nur so gut wie die beste Option oder besser ab, weil Brache Boden, Wasser und "
                          "Zikade schont. Sie bringt {a} nichts ein: Flächen unbestellt zu lassen ist keine echte Strategie, "
                          "außer Sie wollen das (zum Beispiel eine Öko-Regelungs-Brache).", "method":
           "Beide Spalten zeigen {a}–{b} auf Ihren Schlägen, gleich bewertet: die beste Option baut ihre Fruchtfolge an, "
           "Ihr Plan das, was Sie auf der Karte jedes Jahres gemalt haben (ungemalt {a}: Brache; ungemalte Folgejahre: aus "
           "der besten Option ergänzt). Zikade und Einkommen enthalten den Druck aus benachbarten Kinderstuben "
           "(Flugweite {km} km). {painted} von {total} ha {a} bemalt."},
}


def plan_metrics(fid: str, p: dict, features: list[dict], year: int, lang: str = "en", others=(), future=None) -> None:
    tx = TEXT[lang]
    best, res = engine.compare_custom(fid, features, optional=st.session_state.get("show_s4", False), year=year,
                                      others=others, future=future)
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
    fallow = res["custom"].get("fallow_ha_first", 0.0)
    if painted < 0.01:
        st.info(tx["empty"].format(a=a), icon=":material/edit:")
    elif fallow >= 0.05:
        st.warning(tx["some_fallow"].format(ha=num(fallow, 1), total=num(total, 1), a=a), icon=":material/grass:")
    if fallow >= 0.05 and oc >= ob:
        st.warning(tx["fallow_wins"].format(a=a), icon=":material/warning:")
    _sequences(features, res, tx, a, b, lang)
    st.caption(tx["method"].format(a=a, b=b, km=num(st.session_state.get("ls_r", FLIGHT_M) / 1000, 1),
                                   painted=num(painted, 1), total=num(total, 1))
               + (" " + tx["shared"].format(n=res["collab_plots"]) if res.get("collab_plots") else ""))


def _sequences(features, res, tx, a, b, lang):
    """A small table of what each plan grows per plot, so the three years are visible, not only scored."""
    import rotation
    label = lambda c: engine._crop_label(c, lang)
    rows = ""
    for n, f in enumerate(features, 1):
        pid = f["properties"]["id"]
        pb, pc = res["best"]["plans"].get(pid), res["custom"]["plans"].get(pid)
        if not pb:
            continue
        mine = res["painted"].get(pid, [True] * len(pc))
        cells = lambda seq, other: " → ".join(
            (f"<b>{label(c)}</b>" if c != o else label(c)) if own
            else f'<i style="opacity:.6">{label(c)} ({tx["auto"]})</i>' for c, o, own in zip(seq, other, mine))
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
