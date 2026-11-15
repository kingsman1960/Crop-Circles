"""Loaders and small UI helpers shared by the pages. The app reads only data/processed/ and content/."""
import base64
import html
import json
import re
import sys
import tomllib
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "crop-circles-data-prep" / "crop-circles-data-prep" / "data" / "processed"
CONTENT = ROOT / "content"
ASSETS = Path(__file__).parent / "assets"
sys.path.insert(0, str(ROOT))  # pipeline/pressure.py: the same pressure maths as the pipeline
from pipeline.pressure import impacts  # noqa: E402

from i18n import lang, t  # noqa: E402

# Achromatic ledger: ink for chrome and most data, HUE only for the planthopper story, POS only where a field switches.
INK, HUE, POS, GREY, GREY_LIGHT = "#16213e", "#b03a72", "#2f6a3f", "#8a94a6", "#c3cad4"
PALE = "#e7bfd2"  # sugar beet that is not (yet) under pressure
UNCERTAINTY = {"low": POS, "medium": "#9a6a12", "high": HUE}
# crops on the maps: one hue per group, all pairs checked for colour-blind readers (dataviz validator); the rest grey
CROPS = {"beet": HUE, "cereal": "#eda100", "maize": "#2a78d6", "legume": "#008300", "veg": "#7f3b08", "grass": "#1baf7a",
         "other": GREY_LIGHT}
CROP_WORDS = (("beet", ("rübe",)), ("legume", ("erbse", "bohne", "soja", "lupine", "luzerne", "klee", "wicke")),
              ("maize", ("mais",)), ("cereal", ("weizen", "dinkel", "emmer", "einkorn", "gerste", "hafer", "roggen", "triticale")),
              ("veg", ("kartoffel", "gemüse", "lauch", "zwiebel", "kürbis", "zucchini", "kohl", "möhre", "spargel", "salat")),
              ("grass", ("wiese", "weide", "gras", "brache", "blüh", "feldrand", "randstreifen", "puffer", "erzeugung")))


def crop_group(name):
    """FIONA crop name (German) -> map group; legumes before grass so that clover grass counts as a legume."""
    n = name.lower()
    return next((g for g, words in CROP_WORDS if any(w in n for w in words)), "other")


def crop_scale(names, focus):
    """Crops in greys, except the planthopper step: `focus` = (sugar-beet name, winter-wheat name) in this language."""
    greys = iter(["#8a94a6", "#c3cad4", "#a7b0be", "#dde2e8", "#6f7a8e", "#b5bdc9"] * 4)
    named = dict(zip(focus, [HUE, INK]))
    return alt.Scale(domain=list(names), range=[named.get(n) or next(greys) for n in names])


def crop_names(tag=None):
    """Thünen crop code -> name in the reader's language (English when the legend has no such language)."""
    legends = json.loads((PROC / "landscape_summary.json").read_text(encoding="utf-8"))["legends"]
    return {int(k): v for k, v in legends.get((tag or lang()).split("-")[0], legends["en"]).items()}


def _merge(base, over):
    """Overlay translated text on the English content: by key; arrays of tables by `id`."""
    if isinstance(base, dict) and isinstance(over, dict):
        return {k: _merge(base[k], over[k]) if k in base and k in over else over.get(k, base.get(k))
                for k in dict.fromkeys([*base, *over])}
    if isinstance(base, list) and isinstance(over, list) and base and isinstance(base[0], dict) and "id" in base[0]:
        by_id = {o["id"]: o for o in over}
        return [_merge(b, by_id[b["id"]]) if b["id"] in by_id else b for b in base]
    return over


@st.cache_data
def _content(name, tag):
    base = tomllib.loads((CONTENT / f"{name}.toml").read_text(encoding="utf-8"))
    for part in dict.fromkeys([tag.split("-")[0], tag]):  # "de" first, then "de-AT"
        over = CONTENT / part / f"{name}.toml"
        if part != "en" and over.exists():
            base = _merge(base, tomllib.loads(over.read_text(encoding="utf-8")))
    return base


def content(name):
    """A content file (strategy cards, glossary …) in the reader's language, English where not translated."""
    return _content(name, lang())


@st.cache_data
def table(name):
    """A parquet table from data/processed, or None while it has not been produced yet (e.g. NDVI)."""
    p = PROC / f"{name}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def rgb(h, a=220):
    """#rrggbb -> [r, g, b, a] for deck.gl (plain ints: numpy ints do not serialise)."""
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)] + [a]


@st.cache_data
def from_space():
    """The HLS season check per field (hls_check.json), or None before the pipeline has made it."""
    p = PROC / "hls_check.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


@st.cache_data
def geojson(name):
    return json.loads((PROC / f"{name}.geojson").read_text(encoding="utf-8"))


@st.cache_data
def strategies():
    return json.loads((PROC / "strategies.json").read_text(encoding="utf-8"))


@st.cache_data
def layer(name):
    """Map overlay as (data URI, metadata with bounds and legend)."""
    meta = json.loads((PROC / "layers" / f"{name}.json").read_text(encoding="utf-8"))
    png = (PROC / "layers" / f"{name}.png").read_bytes()
    return pdk.types.String("data:image/png;base64," + base64.b64encode(png).decode()), meta  # literal, not a deck.gl expression


def fields():
    return {f["id"]: f["properties"] for f in geojson("fields")["features"]}


def field_picker(where=st):
    """F1/F2/F3 switch shared by the pages; kept in the session and in the URL (?field=F2), so links can set it."""
    import accounts  # here, not at the top: accounts reads nothing from data, the pages import both
    ids = accounts.my_fields(list(fields()))
    qp = st.query_params.get("field")
    if qp in ids and qp != st.session_state.get("_field_qp"):  # the URL changed: a link or a reload
        st.session_state.field = qp
    if st.session_state.get("field") not in ids:
        st.session_state.field = ids[0]
    if len(ids) > 1:  # one field: nothing to switch
        where.segmented_control("Field", ids, key="field", required=True, persist_state="session",
                                format_func=field_name, label_visibility="collapsed")
    st.query_params["field"] = st.session_state._field_qp = st.session_state.field
    return st.session_state.field, fields()[st.session_state.field]


def field_name(fid):
    """'F1 · near Eppingen' in the reader's language (the config labels are 'Near <town>')."""
    return t("common.field_name", id=fid, place=fields()[fid]["label"].removeprefix("Near "))


def header(title, sub=None, right=(3, 1)):
    """Title row: h1 (24px), the finding in one sentence under it; returns the right-hand column for the action."""
    left, side = st.columns(right, vertical_alignment="bottom")
    left.title(title)
    if sub:
        left.html(f'<p class="cc-sub">{sub}</p>')
    return side


def kpis(items, lead=None):
    """One container split by 1px dividers: (label, value, unit, delta, tone, help); tone 'good' / 'bad' / None."""
    cells = []
    for i, (label, value, unit, delta, tone, help_) in enumerate(items):
        unit = f"<small>{unit}</small>" if unit else ""
        delta = f'<div class="d {tone or ""}">{delta}</div>' if delta else ""
        cells.append(f'<div class="cc-kpi{" lead" if i == lead else ""}" title="{html.escape(help_ or "")}">'
                     f'<div class="l">{label}</div><div class="v">{value}{unit}</div>{delta}</div>')
    st.html(f'<div class="cc-kpis" style="--n:{len(items)}">{"".join(cells)}</div>')


def legend(keys):
    """Swatches that are the marks they explain: (colour, label, round?[, outline colour])."""
    st.html("".join(f'<span class="cc-key"><i class="{"round" if r else ""}" style="background:{c}'
                    f'{f";box-shadow:inset 0 0 0 2px {o[0]}" if o else ""}"></i>{l}</span>' for c, l, r, *o in keys))


def tip(key):
    """Glossary text for a help= tooltip."""
    g = content("glossary")[key]
    return f"**{g['term']}** – {g['text']}"


def source_line(unit, source, period):
    st.caption(t("common.source_line", unit=unit, source=source, period=period))


def uncertainty(level):
    return f'<span class="cc-note">{t("common.uncertainty." + level)}</span>'


def takeaway(title, sub, sections):
    """The field page as one printable HTML page to take to the advisor: sections are (heading, [paragraphs])."""
    md = lambda s: re.sub(r"\*(.+?)\*", r"<i>\1</i>", re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s))
    body = "".join(f"<h2>{h}</h2>" + "".join(f"<p>{md(p)}</p>" for p in ps) for h, ps in sections)
    logo = base64.b64encode((ASSETS / "symbol.png").read_bytes()).decode()
    return (f'<!doctype html><html lang="{lang()}"><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>'
            "body{font:15px/1.55 system-ui,sans-serif;color:#16213e;background:#fff;max-width:46rem;margin:2rem auto;"
            "padding:0 1rem}h1,h2{font-family:Newsreader,Georgia,serif;font-weight:600}h1{font-size:1.6rem;margin:.4rem 0}"
            "h2{font-size:1.15rem;margin:1.6rem 0 .4rem;padding-top:1rem;border-top:1px solid #c3cad4}p{margin:.45rem 0}"
            ".sub,footer{color:#5b6475}footer{margin-top:2rem;font-size:.8rem}@media print{body{margin:0}h2{break-after:avoid}}"
            f'</style></head><body><img src="data:image/png;base64,{logo}" width="44" alt="Crop Circles"><h1>{title}</h1>'
            f'<p class="sub">{md(sub)}</p>{body}<footer>{md(t("common.footer"))}</footer></body></html>')


def footer():
    with st.container(key="footer"):
        a, b = st.columns([1, 2.2], vertical_alignment="center")
        a.image(str(ASSETS / "logo_bar.png"), width=220)
        b.markdown(t("common.footer"))


# --- landscape planner -------------------------------------------------------
ALTERNATIVES = {"grain_maize": "S1", "soybean": "S2", "field_pea": "S4"}  # crop instead of wheat after beet -> its card
MODES = ("balanced", "pests", "random")  # labels: region.mode.<key>


@st.cache_data
def landscape(scope="bbox"):
    """(parcels indexed by FIONA id, seasons table, summary) for the study bbox, or all of BW (scope "bw")."""
    sfx = "" if scope == "bbox" else f"_{scope}"
    par = table("landscape_parcels" + sfx).set_index("id")
    par["ks"], par["nfk_mm"] = par.ks.fillna(par.ks.median()), par.nfk_mm.fillna(par.nfk_mm.median())
    return par, table("landscape_seasons" + sfx), json.loads((PROC / f"landscape_summary{sfx}.json").read_text(encoding="utf-8"))


@st.cache_data
def pressure(season, r, scope="bbox", src=""):
    """Nurseries with their impact, beet parcels with their pressure, for one season and flight distance r (m).
    `src` picks the crop source: "" (the planner's), "_dlr" or "_thuenen"; nursery_ha / beet_ha then hold that source."""
    par, seasons, _ = landscape(scope)
    s = seasons[seasons.season == season]
    if src:
        s = s.assign(nursery_ha=s["nursery_ha" + src], beet_ha=s["beet_ha" + src]).dropna(subset=["nursery_ha", "beet_ha"])
    nur, beet = s[s.nursery_ha > 0].copy(), s[s.beet_ha > 0].copy()
    xy = lambda d: par.loc[d.id, ["x", "y"]].to_numpy("float32")
    nur["impact"], beet["pressure"] = impacts(xy(nur), nur.nursery_ha.to_numpy("float32"),
                                              xy(beet), beet.beet_ha.to_numpy("float32"), r)
    return nur.join(par, on="id").reset_index(drop=True), beet.join(par, on="id").reset_index(drop=True)


@st.cache_data
def region_test():
    """The region-wide planthopper edge test (planthopper_effect/region_summary.json), or {} before it has run."""
    p = PROC / "planthopper_effect" / "region_summary.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


FLIGHT_M, FLIGHTS = 500, (250, 500, 1000)  # the planthopper's flight distance: 350 m fits the region test best (band 250-500 m)
PH_LEVEL = lambda rank: "high" if rank >= 0.67 else "medium" if rank >= 0.33 else "low"  # rank among the region's beet


@st.cache_data
def ph_levels(fid, season):
    """The planthopper level of a demo field for every flight distance (0.5 / 1 / 2 km) and crop source that has
    the season (planner, DLR, Thünen): {(r, src): level}. Shows how much the level hangs on the unknowns."""
    par, seasons, _ = landscape()
    fx, fy = par.loc[par.field == fid, ["x", "y"]].mean()
    out = {}
    for src in ("", "_dlr", "_thuenen"):
        if f"nursery_ha{src}" not in seasons or not (seasons.loc[seasons.season == season, f"nursery_ha{src}"].fillna(0) > 0).any():
            continue
        for r in FLIGHTS:
            nur, beet = pressure(season, r, "bbox", src)
            total = (nur.nursery_ha * np.exp(-np.hypot(nur.x - fx, nur.y - fy) / r)).sum()
            out[(r, src)] = PH_LEVEL((beet.pressure < total).mean())
    return out


def side_effects(nur, weights):
    """Best crop instead of wheat per nursery, and its side-effect cost (0 = none) under the user's priorities.

    Erosion and water effects are the S1/S2/S4 model results relative to S0, scaled by the parcel's K·S (NASADEM,
    BK50) and plant-available water (BK50); income is the rule score from the strategy cards.
    """
    res = strategies()["fields"].values()
    cards = {s["id"]: s for s in content("strategies")["strategy"]}
    ero = {c: np.mean([f["strategies"][s]["erosion_rel"] for f in res]) - 1 for c, s in ALTERNATIVES.items()}
    wat = {c: np.mean([f["strategies"][s]["water_rel"] for f in res]) - 1 for c, s in ALTERNATIVES.items()}
    inc = {c: cards[s]["scores"]["income"]["score"] for c, s in ALTERNATIVES.items()}
    ks, dry = nur.ks / 0.55, (140 / nur.nfk_mm).clip(0.5, 2)
    we, ww, wi = (weights[k] for k in ("erosion", "water", "income"))
    cost = pd.DataFrame({c: (we * ero[c] / max(ero.values()) * ks + ww * wat[c] / max(wat.values()) * dry
                             + wi * (max(inc.values()) - inc[c]) / (max(inc.values()) - min(inc.values())))
                            / max(we + ww + wi, 1e-9) for c in ALTERNATIVES})
    return cost.idxmin(axis=1), cost.min(axis=1)


def plan(season, r, share, mode, weights, scope="bbox"):
    """Nurseries ranked and marked `switch` until `share` of the nursery area changes crop; beet with pressure after."""
    nur, beet = pressure(season, r, scope)
    nur["alt"], nur["cost"] = side_effects(nur, weights)
    per_ha = nur.impact / nur.nursery_ha
    key = {"pests": per_ha, "balanced": per_ha / (1 + nur.cost),
           "random": pd.Series(np.random.default_rng(season).random(len(nur)))}[mode]
    nur = nur.assign(key=key).sort_values("key", ascending=False, ignore_index=True)
    nur["switch"] = nur.nursery_ha.cumsum() <= share * nur.nursery_ha.sum()
    sw = nur[nur.switch]
    beet["after"] = beet.pressure - impacts(sw[["x", "y"]].to_numpy("float32"), sw.nursery_ha.to_numpy("float32"),
                                            beet[["x", "y"]].to_numpy("float32"), beet.beet_ha.to_numpy("float32"), r)[1]
    return nur, beet


def neighbourhood(fid, nur, r):
    """Pressure on a demo field block: total, from its own nurseries, and what is left after the plan."""
    par = landscape()[0]
    fx, fy = par.loc[par.field == fid, ["x", "y"]].mean()
    k = nur.nursery_ha * np.exp(-np.hypot(nur.x - fx, nur.y - fy) / r)
    return {"total": k.sum(), "own": k[nur.field == fid].sum(), "after": k[~nur.switch].sum(),
            "near_ha": nur.nursery_ha[np.hypot(nur.x - fx, nur.y - fy) <= r].sum()}


def planner_weights():  # the side effects only
    """Side-effect priorities shared with the strategies page (same session keys, 0..10 sliders)."""
    from engine import default_weight
    return {k: st.session_state.get(f"w_{k}", default_weight(k)) for k in ("erosion", "water", "income")}


# --- priorities and ranking (shared by My field, What to grow, Our region) --------------------------
PRIORITY = {0: "not", 2: "important", 4: "very"}  # labels: common.priority.<key>


def priority_control(k):
    """How important one criterion is: a 0..10 slider; the same session key on every page (engine.priority_slider)."""
    from engine import priority_slider
    priority_slider(k, width=260)


def weights():
    """The user's priorities for all criteria, 0..10 (engine.weights)."""
    from engine import weights as w
    return w()


def rank_options(fid, w=None, optional=False):
    """Options for one field, best match first: (ids in order, weighted score per id, card per id).

    Scored by engine.py: every strategy as the next three years on the block's plots, with planthopper pressure.
    """
    from engine import rank
    return rank(fid, w, optional)


def chart(c, **kw):
    """st.altair_chart with axes in the reader's number and month format."""
    from i18n import chart_locale
    st.altair_chart(c.configure(locale=chart_locale()), **kw)


def _nfk_words(text):
    """'≥140 mm' -> 'more than 140', '<50 mm' -> 'less than 50', '90–140 mm' -> '90–140' (in the reader's language)."""
    value = text.replace(" mm", "")
    if value.startswith("≥"):
        return t("plain.more_than", n=value[1:])
    if value.startswith("<"):
        return t("plain.less_than", n=value[1:])
    return value


def fact_text(key, f):
    """A field fact from the pipeline (numbers only) as a sentence and its source, in the reader's language."""
    from i18n import num
    params = {"beet_wheat": lambda: dict(share=num(f["share"] * 100), region=num(f["region"] * 100)),
              "soil": lambda: dict(k_class=f["k_class"], slope=num(f["slope"], 1), drop=num(f["slope"]),
                                   nfk=_nfk_words(f["nfk"])),
              "heat_heading": lambda: dict(n=f["n"], trend=num(f["trend"])),
              "summer_dry": lambda: dict(n=f["n"], cwb=num(f["cwb"]))}.get(key, lambda: dict(n=f["n"]))()
    return t(f"fact.{key}", **params), t(f"fact.source.{f['source']}", station=f.get("station", ""))


def model_note(kind, s):
    """The erosion / water note for a modelled score, from its ratio to today's rotation."""
    from i18n import months, pct
    rel = s["rel"]
    change = "same" if abs(rel - 1) < 0.02 else "more" if rel > 1 else "less"
    names = months("wide")
    return t(f"note.{kind}.{change}", pct=pct(abs(rel - 1)), months=", ".join(names[m - 1] for m in s.get("months", [])))
