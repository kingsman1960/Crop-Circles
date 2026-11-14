"""The crop planner at the bottom of the grow page.

Start from this year's FIONA plots, cut and merge them into next year's layout, then pick a crop and paint it on.
Each plot's history is worked out from the area it covers in every FIONA year, so it stays right after a cut.
"""
from __future__ import annotations

import html

import streamlit as st

import rotation
from data import geojson
from i18n import num, t
from plan_metrics import plan_metrics
from plot_editor import metric, plot_editor

TEXT = {
    "en": {"title": "Plan {year} on your fields", "intro": "Split or merge the plots for next year, then pick a crop to "
           "see where it fits the rotation. Red plots break a rule; hover over one to see why.",
           "none": "No FIONA plots for this block yet.", "source": "History: crops declared by the farmers (FIONA), "
           "worked out for the area of each plot.", "plan": "Plan {year}", "nothing": "No crops planned yet.",
           "broken": "{n} planned plot(s) break a rotation rule.", "risky": "{n} carry a risk.",
           "faded": "Faded colours: last year's crop. Solid: your plan."},
    "de": {"title": "{year} auf Ihren Flächen planen", "intro": "Teilen oder verbinden Sie die Schläge fürs nächste Jahr "
           "und wählen Sie eine Kultur, um zu sehen, wo sie in die Fruchtfolge passt. Rote Schläge verletzen eine Regel; "
           "fahren Sie darüber, um den Grund zu sehen.", "none": "Für diesen Block gibt es noch keine FIONA-Schläge.",
           "source": "Vorgeschichte: von den Landwirten gemeldete Kulturen (FIONA), für die Fläche jedes Schlags berechnet.",
           "plan": "Plan {year}", "nothing": "Noch keine Kulturen geplant.",
           "broken": "{n} geplante(r) Schlag/Schläge verletzt eine Fruchtfolgeregel.", "risky": "{n} mit Risiko.",
           "faded": "Blasse Farben: Kultur des Vorjahres. Kräftig: Ihr Plan."},
}
EDITOR_DE = {
    "select": "Auswählen", "cut": "Teilen", "merge": "Verbinden", "undo": "Rückgängig", "finish": "Schnitt fertig",
    "working": "Wird berechnet…", "hint_select": "Schlag anklicken zum Auswählen, mit Umschalt weitere dazu.",
    "hint_cut": "Klicken Sie eine Linie quer über die Schläge. Doppelklick oder Enter teilt, Esc bricht ab.",
    "err_adjacent": "Nur Schläge, die sich berühren, lassen sich verbinden.",
    "err_cut": "Die Linie muss einen Schlag von Rand zu Rand queren.",
    "err_small": "Der Schnitt würde ein Stück unter {ha} ha übrig lassen und wurde ausgelassen.",
    "crop": "Kultur…", "no_crop": "Keine Kultur (nur ansehen)", "plan": "Plan", "not_planned": "Noch nicht geplant",
    "hint_paint": "Rot: verletzt eine Fruchtfolgeregel. Grün: passt gut. Schlag anklicken, um die Kultur dort zu planen, "
                  "nochmal klicken nimmt sie zurück.",
    "level_bad": "Verletzt eine Regel", "level_warn": "Möglich, mit Risiko", "level_ok": "In Ordnung",
    "level_good": "Passt gut", "level_unknown": "Keine Vorgeschichte",
}


@st.fragment
def crop_planner(fid: str, p: dict, height: int = 620) -> None:
    """The planner for one block. A fragment, so painting and cutting only rerun this part of the page."""
    lang = "en" if t("app.language") == "Language" else "de"
    tx = TEXT[lang]
    parcels = [f for f in geojson("parcels")["features"] if f["properties"]["field"] == fid]
    years = sorted({f["properties"]["year"] for f in parcels})
    if not years:
        st.caption(tx["none"])
        return
    target = years[-1] + 1
    st.subheader(tx["title"].format(year=target))
    st.markdown(tx["intro"])

    past = [(f["properties"]["year"], _key(f["properties"].get("crop")), metric(f)) for f in parcels]
    outline = {"type": "FeatureCollection", "features": [f for f in geojson("fields")["features"] if f["id"] == fid]}
    palette = [{"key": k, "label": rotation.label(k, lang), "rgb": c["rgb"], "family": c["family"]}
               for k, c in rotation.CROPS.items()]
    res = plot_editor([f for f in parcels if f["properties"]["year"] == years[-1]], key=f"planner_{fid}",
                      outline=outline, view={"lat": p["lat"], "lon": p["lon"], "zoom": 14.6}, height=height,
                      palette=palette, tooltip=None,
                      labels=(EDITOR_DE if lang == "de" else {}) | {"plan": tx["plan"].format(year=target)},
                      annotate=lambda feats: _annotate(feats, past, years, target, lang))
    _summary(res["features"], target, lang)
    st.caption(tx["faded"] + " " + tx["source"])
    st.space("small")
    plan_metrics(fid, p, res["features"], years, lang)


def _key(name):
    """One of the six crop keys, or "other:<declared name>" so the tooltip can still name it."""
    k = rotation.classify(name)
    return k if k != "other" else f"other:{name or '?'}"


def _label(k, lang):
    return k.split(":", 1)[1] if k.startswith("other:") else rotation.label(k, lang)


def _annotate(feats, past, years, target, lang):
    """For each plot: the crops under it in every FIONA year (by area), its colour, its tooltip and the crop fits."""
    for f in feats:
        g = metric(f)
        area = g.area or 1.0
        hist: dict[int, dict[str, float]] = {}
        for y, k, pg in past:
            if g.intersects(pg):
                share = g.intersection(pg).area / area
                if share > 0.005:
                    hist.setdefault(y, {})
                    hist[y][k] = hist[y].get(k, 0.0) + share
        props = f["properties"]
        props["hist"] = {str(y): v for y, v in hist.items()}  # for the metrics under the map
        props["fit"] = {k: rotation.fit(k, hist, target, lang) for k in rotation.CROPS}
        last = hist.get(years[-1], {})
        top = max(last, key=last.get) if last else "other"
        props["rgb"] = rotation.CROPS[top]["rgb"] if top in rotation.CROPS else rotation.OTHER_RGB
        lines = [f"<b>{y}</b>: " + ", ".join(f"{html.escape(_label(k, lang))} {v:.0%}"
                                             for k, v in sorted(hist[y].items(), key=lambda x: -x[1]) if v >= 0.05)
                 for y in sorted(hist, reverse=True)[:4]]
        props["tip"] = "<br>".join(lines) + "<br><span style='opacity:.7'>FIONA</span>" if lines else ""


def _summary(feats, target, lang):
    """One line under the map: what is planned, and how many planned plots break a rule."""
    tx = TEXT[lang]
    ha: dict[str, float] = {}
    bad = warn = 0
    for f in feats:
        props = f["properties"]
        crop = props.get("plan")
        if not crop:
            continue
        ha[crop] = ha.get(crop, 0.0) + props.get("ha", 0.0)
        level = props.get("fit", {}).get(crop, {}).get("level")
        bad += level == "bad"
        warn += level == "warn"
    if not ha:
        st.markdown(f"**{tx['plan'].format(year=target)}:** {tx['nothing']}")
        return
    planned = ", ".join(f"{rotation.label(k, lang)} {num(v, 1)} ha" for k, v in sorted(ha.items(), key=lambda x: -x[1]))
    issues = (" " + tx["broken"].format(n=bad) if bad else "") + (" " + tx["risky"].format(n=warn) if warn else "")
    st.markdown(f"**{tx['plan'].format(year=target)}:** {planned}." + issues)
