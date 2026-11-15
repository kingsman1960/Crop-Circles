"""The crop planner at the bottom of the grow page.

Start from this year's FIONA plots, cut and merge them into next year's layout, then pick a crop and paint it on.
Each plot's history is worked out from the area it covers in every FIONA year, so it stays right after a cut.
"""
from __future__ import annotations

import html

import streamlit as st

import rotation
import ecocrop
import engine
import plans_store
from data import CROPS, HUE, INK, geojson, landscape, legend
from i18n import num, t
from neighbours import collab_features, neighbour_context
from plan_metrics import plan_metrics
from plot_editor import edited, metric, plot_editor

TEXT = {
    "en": {"title": "Plan {year} on your fields", "intro": "Split or merge the plots for next year, then pick a crop to "
           "see where it fits the rotation. Red plots break a rule; hover over one to see why.",
           "none": "No FIONA plots for this block yet.", "source": "History: crops declared by the farmers (FIONA), "
           "worked out for the area of each plot.", "plan": "Plan {year}", "nothing": "No crops planned yet.",
           "broken": "{n} planned plot(s) break a rotation rule.", "risky": "{n} carry a risk.",
           "faded": "Faded colours: last year's crop. Solid: your plan.",
           "lg_neighbours": "Neighbours' crops in {season} (circle = parcel area)",
           "lg_unknown": "Neighbours: crops in {year} not known yet", "lg_likely": "Likely nursery in {year} (beet in {prev})",
           "lg_shared": "Shared plans of other farmers", "lg_ring": "Planthopper flight range ({km} km)",
           "likely": "**{n} likely nurseries** ({ha} ha) within {km} km: they grew sugar beet in {prev}, and {btw} of such "
                     "fields grow winter wheat in {year}.",
           "later": "Neighbours' crops for {year} are not known yet: the pressure uses their history, unless they share a plan.",
           "n_shared": "**{n} plots** of other farmers' plans for {year} are on the map and count with their real crops.",
           "year": "Plan year", "save": "Save {year} plan", "saved": "Your {year} plan is saved.",
           "not_saved": "Your {year} plan is not saved yet.", "saved_toast": "{year} plan saved.",
           "save_failed": "Could not save: {msg}", "login": "Saving is off: no logged-in account found (accounts.user() has no id or e-mail). Log in to save and share your plan.",
           "privacy": "Saved plans are shared with other planners without your name: outlines and crops only, for the "
                      "planthopper maths.", "no_store": "Saving is off: SUPABASE_URL and SUPABASE_SECRET_KEY were not found. Streamlit reads "
                       ".streamlit/secrets.toml in the folder where you run `streamlit run`.",
           "save_first": "Plan {prev} first (pick {prev} above): it is what grows before {year}, for the rotation rules "
                         "and the pressure.",
           "hist_src": "FIONA, then your saved plans", "fit": "climate fit {pct}"},
    "de": {"title": "{year} auf Ihren Flächen planen", "intro": "Teilen oder verbinden Sie die Schläge fürs nächste Jahr "
           "und wählen Sie eine Kultur, um zu sehen, wo sie in die Fruchtfolge passt. Rote Schläge verletzen eine Regel; "
           "fahren Sie darüber, um den Grund zu sehen.", "none": "Für diesen Block gibt es noch keine FIONA-Schläge.",
           "source": "Vorgeschichte: von den Landwirten gemeldete Kulturen (FIONA), für die Fläche jedes Schlags berechnet.",
           "plan": "Plan {year}", "nothing": "Noch keine Kulturen geplant.",
           "broken": "{n} geplante(r) Schlag/Schläge verletzt eine Fruchtfolgeregel.", "risky": "{n} mit Risiko.",
           "faded": "Blasse Farben: Kultur des Vorjahres. Kräftig: Ihr Plan.",
           "lg_neighbours": "Kulturen der Nachbarn {season} (Kreis = Schlagfläche)",
           "lg_unknown": "Nachbarn: Kulturen {year} noch unbekannt", "lg_likely": "Wahrscheinliche Kinderstube {year} (Rüben {prev})",
           "lg_shared": "Geteilte Pläne anderer Betriebe", "lg_ring": "Flugweite der Zikade ({km} km)",
           "likely": "**{n} wahrscheinliche Kinderstuben** ({ha} ha) im Umkreis von {km} km: dort standen {prev} Zuckerrüben, "
                     "und {btw} solcher Schläge tragen {year} Winterweizen.",
           "later": "Die Kulturen der Nachbarn für {year} sind noch unbekannt: der Druck nutzt ihre Vorgeschichte, außer sie teilen einen Plan.",
           "n_shared": "**{n} Schläge** aus Plänen anderer Betriebe für {year} sind auf der Karte und zählen mit ihren echten Kulturen.",
           "year": "Planjahr", "save": "Plan {year} speichern", "saved": "Ihr Plan für {year} ist gespeichert.",
           "not_saved": "Ihr Plan für {year} ist noch nicht gespeichert.", "saved_toast": "Plan {year} gespeichert.",
           "save_failed": "Speichern fehlgeschlagen: {msg}", "login": "Speichern ist aus: kein angemeldetes Konto gefunden (accounts.user() ohne id oder E-Mail). Bitte anmelden.",
           "privacy": "Gespeicherte Pläne werden ohne Ihren Namen mit anderen Planenden geteilt: nur Umrisse und Kulturen, "
                      "für die Zikadenberechnung.", "no_store": "Speichern ist aus: SUPABASE_URL und SUPABASE_SECRET_KEY nicht gefunden. Streamlit liest "
                       ".streamlit/secrets.toml im Ordner, in dem Sie `streamlit run` starten.",
           "save_first": "Planen Sie zuerst {prev} (oben {prev} wählen): das ist die Vorfrucht für {year}, für "
                         "Fruchtfolgeregeln und Druck.",
           "hist_src": "FIONA, danach Ihre gespeicherten Pläne", "fit": "Klimaeignung {pct}"},
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
    """The planner for one block and one plan year. A fragment: painting and cutting only rerun this part of the page."""
    lang = "en" if t("app.language") == "Language" else "de"
    tx = TEXT[lang]
    parcels = [f for f in geojson("parcels")["features"] if f["properties"]["field"] == fid]
    years = sorted({f["properties"]["year"] for f in parcels})
    if not years:
        st.caption(tx["none"])
        return
    seasons = sorted(landscape()[1].season.unique())
    season = int(years[-1] if years[-1] in seasons else seasons[-1])
    r = int(st.session_state.get("ls_r", 1000))  # the flight range set on the region page
    shared_ok = plans_store.available()
    plan_years = plans_store.plan_years()
    saved = plans_store.mine(fid, plan_years) if shared_ok else {}

    year = st.segmented_control(tx["year"], plan_years, default=plan_years[0], required=True, key=f"plan_year_{fid}",
                                format_func=lambda y: f"{y} ✓" if y in saved else str(y))
    st.subheader(tx["title"].format(year=year))
    st.markdown(tx["intro"])
    # every plan year: what you painted in this session (also unsaved), else what you saved
    layers = {y: edited(f"planner_{fid}_{y}") or saved.get(y) for y in plan_years}
    layers = {y: v for y, v in layers.items() if v}
    painted = lambda y: any(f["properties"].get("plan") for f in layers.get(y, []))
    if year - 1 > season and not painted(year - 1):
        st.info(tx["save_first"].format(prev=year - 1, year=year))

    # history: the FIONA declarations, then your plans for the years before this one
    past = [(f["properties"]["year"], _key(f["properties"].get("crop")), metric(f)) for f in parcels]
    past += [(y, f["properties"]["plan"], metric(f)) for y, plots in layers.items() if y < year
             for f in plots if f["properties"].get("plan")]
    # the starting layout: your saved plan for this year, else your latest earlier layout, else this year's FIONA plots
    earlier = [y for y in layers if y < year]
    if year in saved:
        start = saved[year]
    elif earlier:
        start = [{**f, "properties": {"id": f["properties"]["id"], "ha": f["properties"].get("ha"), "plan": None}}
                 for f in layers[max(earlier)]]
    else:
        start = [f for f in parcels if f["properties"]["year"] == years[-1]]

    others = plans_store.others(fid, range(year - 1, year + 3)) if shared_ok else []
    ctx = neighbour_context(fid, season, r, lang, year)
    shared = collab_features(others, year, season, lang) if others else []
    outline = {"type": "FeatureCollection", "features": [f for f in geojson("fields")["features"] if f["id"] == fid]}
    res = plot_editor(start, key=f"planner_{fid}_{year}", outline=outline,
                      view={"lat": p["lat"], "lon": p["lon"], "zoom": 14.0}, height=height,
                      palette=_palette(fid, lang), tooltip=None, context=ctx["features"] + shared,
                      labels=(EDITOR_DE if lang == "de" else {}) | {"plan": tx["plan"].format(year=year)},
                      annotate=lambda feats: _annotate(feats, past, year, lang))

    keys = [(CROPS["cereal"] + "59", tx["lg_neighbours"].format(season=season) if year == season + 1
             else tx["lg_unknown"].format(year=year), True)]
    if year == season + 1:
        keys.append(("#ffffff", tx["lg_likely"].format(year=year, prev=season), True, HUE))
    if shared:
        keys.append((CROPS["cereal"], tx["lg_shared"], False))
    keys.append(("#ffffff00", tx["lg_ring"].format(km=num(r / 1000, 1)), True, INK))
    legend(keys)
    sm = ctx["summary"]
    if year == season + 1:
        st.markdown(tx["likely"].format(n=sm["likely_n"], ha=num(sm["likely_ha"], 1), km=num(r / 1000, 1),
                                        prev=season, year=year, btw=f"{sm['btw']:.0%}"))
    else:
        st.markdown(tx["later"].format(year=year))
    if shared:
        st.markdown(tx["n_shared"].format(n=len(shared), year=year))
    _summary(res["features"], year, lang)

    a, b = st.columns([3, 1], vertical_alignment="center")
    why = plans_store.status()
    if why == "ok":
        a.caption((tx["saved"] if year in saved else tx["not_saved"]).format(year=year) + " " + tx["privacy"])
    else:
        a.warning(tx["no_store"] if why == "no_secrets" else tx["login"], icon=":material/cloud_off:")
    if b.button(tx["save"].format(year=year), type="primary", width="stretch", key=f"save_{fid}_{year}",
                disabled=why != "ok"):
        ok, msg = plans_store.save(fid, year, res["features"])
        st.toast(tx["saved_toast"].format(year=year) if ok else tx["save_failed"].format(msg=msg))
        if ok:
            st.rerun(scope="fragment")
    st.caption(tx["faded"] + " " + tx["source"])
    st.space("small")
    future = {y: layers[y] for y in range(year + 1, year + engine.HORIZON) if painted(y)}
    plan_metrics(fid, p, res["features"], year, lang, others, future)


def _palette(fid, lang):
    """The crops to paint, each with its family and its climate fit on this field (EcoCrop)."""
    out = []
    for k, c in rotation.CROPS.items():
        fam = c["family"]
        try:
            m = engine.MODEL[k]
            f = ecocrop.fit(fid, m, bool(engine.model.CROPS.get(m, {}).get("winter", False)))
            if f.get("name"):
                fam += " · " + TEXT[lang]["fit"].format(pct=f"{f['fit']:.0%}")
        except Exception:
            pass
        out.append({"key": k, "label": rotation.label(k, lang), "rgb": c["rgb"], "family": fam})
    return out


def _key(name):
    """One of the six crop keys, or "other:<declared name>" so the tooltip can still name it."""
    k = rotation.classify(name)
    return k if k != "other" else f"other:{name or '?'}"


def _label(k, lang):
    return k.split(":", 1)[1] if k.startswith("other:") else rotation.label(k, lang)


def _annotate(feats, past, target, lang):
    """For each plot: the crops under it in every earlier year (by area), its colour, its tooltip and the crop fits."""
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
        last = hist.get(target - 1) or hist.get(max(hist), {}) if hist else {}
        top = max(last, key=last.get) if last else "other"
        props["rgb"] = rotation.CROPS[top]["rgb"] if top in rotation.CROPS else rotation.OTHER_RGB
        lines = [f"<b>{y}</b>: " + ", ".join(f"{html.escape(_label(k, lang))} {v:.0%}"
                                             for k, v in sorted(hist[y].items(), key=lambda x: -x[1]) if v >= 0.05)
                 for y in sorted(hist, reverse=True)[:4]]
        props["tip"] = "<br>".join(lines) + f"<br><span style='opacity:.7'>{TEXT[lang]['hist_src']}</span>" if lines else ""


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
