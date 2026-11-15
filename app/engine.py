"""The recommendation engine: one way of scoring every option, so strategies and your own plan compare fairly.

Every option is scored as the next HORIZON years (2026-2028) on the plots of the block, plot by plot, year by year,
weighted 50 / 30 / 20 % (next year is decided now, the later years can still change):
- a strategy card: each plot continues the strategy's rotation from where its history left it (if that would break a
  rotation rule there, the plot starts the rotation at another point);
- your plan: what you painted on each year's map (first year: green fallow where nothing is painted); a later year
  you have not painted is filled in with the best match's next crop, or another of its crops where that breaks a rule.
So a one-year plan is never compared with a three-year average: both are three years on the same plots.

Criteria (1 worst .. 5 best):
- erosion, water: the daily rotation model of pipeline/strategies.py (bare soil x heavy rain; Kc x ET0 in dry months),
  relative to today's rotation (S0) on the same plots, which scores 3.
- planthopper: nurseries you create (winter wheat on last year's beet; winter barley counts half), weighted by how much
  beet they reach within flight range compared with a typical nursery in the region. Pressure uses the pipeline's own
  formula, pipeline.pressure.impacts (nursery ha x beet ha x e^(-distance / flight range)), unchanged.
- income: per-crop values from the strategy cards' notes; sugar beet loses yield to SBR/Stolbur in proportion to the
  planthopper pressure it receives (your nurseries and the neighbours' expected ones). Fallow scores 0 (below the 1..5
  scale), weighted by its share, so leaving land unplanted always costs income.
- nitrogen: legumes leave nitrogen for the next crop, cover crops hold it over winter.
- rotation: the rotation rules of the planner map (rotation.py), without the planthopper rule: per plot and year
  a rule broken 1, a risk 2.5, fine 4, a good fit 5.
Neighbours' future crops are unknown: they enter as expected values from their own history (how often they grew beet
since 2017) and the region's share of beet followed by wheat.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
import streamlit as st

import rotation
from data import content, crop_group, fields, geojson, landscape, pressure, strategies, table
from i18n import lang as _lang_tag
from pipeline import strategies as model
from pipeline.pressure import impacts
from plot_editor import metric

HORIZON = 3
YEAR_WEIGHTS = (0.5, 0.3, 0.2)  # next year is decided now; the later years can still change
SCALE = 10                     # sliders run 0..SCALE; the cards' defaults (0, 2, 4) are multiplied by SCALE / 4
MODEL = {"beet": "sugar_beet", "wheat": "winter_wheat", "barley": "winter_barley", "maize": "grain_maize",
         "pea": "field_pea", "potato": "potato"}
PLANNER = {v: k for k, v in MODEL.items()}
FIT_AS = {"soybean": "pea"}    # crops without rotation rules of their own are judged like their nearest crop
PROXY = {"cereal": "wheat", "legume": "pea", "veg": "potato", "maize": "maize", "beet": "beet"}  # other declared crops
UNKNOWN_AS = "winter_barley"   # a last-year crop the model does not know (rapeseed, grass): harvested in summer like barley
BEET_CODE = 1402               # Thünen code of sugar beet in landscape_parcels
# Potatoes are on no card and not in crops.toml yet: literature estimate (general agronomy), FAO-56 Kc.
POTATO = {"label": "Potatoes", "winter": False, "kc_mid": 1.15, "kc_end": 0.75,
          "doy": {"sow": 105, "emerge": 130, "canopy": 165, "harvest": 255}}
model.CROPS.setdefault("potato", POTATO)
# An unpainted plot in your plan: green fallow (self-greening or a sown cover, mulched in autumn), not bare soil.
# Covered most of the year, so little erosion; it transpires like a cover crop; earns nothing; hosts no nursery.
FALLOW = {"label": "Green fallow", "winter": False, "kc_mid": 0.70, "kc_end": 0.60, "stubble": 0.15,
          "doy": {"sow": 75, "emerge": 90, "canopy": 130, "harvest": 300}}
model.CROPS.setdefault("fallow", FALLOW)

# income per crop-year, read from the cards: beet has the best margin when healthy (S0 note), maize and cereals are
# established (S0, S1), soybean and pea have thinner regional markets (S2: 2.5, S4: 2 for the whole rotation)
INCOME = {"fallow": 0.0, "sugar_beet": 3.5, "winter_wheat": 3.0, "winter_barley": 3.0, "grain_maize": 3.0, "potato": 3.0,
          "soybean": 1.75, "field_pea": 1.25}
LOSS_MAX = 0.30                # SBR/Stolbur yield and sugar loss on beet at high pressure (assumption to calibrate)
LEGUME_N = {"field_pea": 7.5, "soybean": 6.0}  # one legume year in three: +2.5 (pea) / +2.0 (soy), as cards S4 / S2
COVER_N = 1.5                  # cover crops in every gap instead of before beet only: +1, as card S3
NURSERY = {"winter_wheat": 1.0, "winter_barley": 0.5}  # barley on beet: our sources name wheat (see rotation.py)
HEALTH = {"bad": 1, "warn": 2.5, "ok": 4, "good": 5, "unknown": 3.5}  # per plot-year; no rule broken = 4 or more
SHOW = 3                       # neighbours up to this many flight ranges away enter the pressure sums

EXTRA = {"rotation": {"label": {"en": "Following the rotation rules", "de": "Fruchtfolgeregeln einhalten"},
                      "help": {"en": "Breaks between the same crops, so pests and soil diseases cannot build up.",
                               "de": "Anbaupausen, damit sich Schädlinge und Bodenkrankheiten nicht aufbauen."},
                      "default": 3}}
TEXT = {
    "en": {"ph": "{ha} ha a year of nurseries, reaching {rel} of the beet a typical nursery reaches.",
           "ph0": "No nurseries: no winter cereal right after beet.",
           "loss": "Beet would lose about {loss} to SBR/Stolbur at the pressure around your block.",
           "n": "{ha} ha a year of legumes.", "rot": "{bad} ha a year break a rotation rule, {warn} ha carry a risk.",
           "rot0": "No rotation rule broken.", "climate": "Climate fit (EcoCrop): {crops}.",
           "fallow": "{ha} ha lie fallow in {year} and earn nothing there; the later years follow the rotation."},
    "de": {"ph": "{ha} ha Kinderstuben pro Jahr, mit {rel} der Rüben, die eine typische Kinderstube erreicht.",
           "ph0": "Keine Kinderstuben: kein Wintergetreide direkt nach Rüben.",
           "loss": "Rüben würden beim Druck um Ihren Block etwa {loss} an SBR/Stolbur verlieren.",
           "n": "{ha} ha Leguminosen pro Jahr.", "rot": "{bad} ha pro Jahr verletzen eine Fruchtfolgeregel, {warn} ha mit Risiko.",
           "rot0": "Keine Fruchtfolgeregel verletzt.", "climate": "Klimaeignung (EcoCrop): {crops}.",
           "fallow": "{ha} ha liegen {year} brach und bringen dort nichts ein; die Folgejahre folgen der Fruchtfolge."},
}


def _crop_label(c, lg):
    if c == "fallow":
        return "Brache" if lg == "de" else "Green fallow"
    return rotation.label(PLANNER[c], lg) if c in PLANNER else c.replace("_", " ").capitalize()


def lang():
    return "de" if _lang_tag().startswith("de") else "en"


# --- priorities -----------------------------------------------------------------------------------------------------

def criteria() -> dict:
    """The criteria in display order: the five of the strategy cards, then the rotation rules."""
    crit = dict(content("strategies")["criteria"])
    lg = lang()
    for k, c in EXTRA.items():
        crit[k] = {"label": c["label"][lg], "help": c["help"][lg], "default": c["default"]}
    return crit


def default_weight(k):
    return round(criteria()[k]["default"] * SCALE / 4)


def weights() -> dict:
    return {k: st.session_state.get(f"w_{k}", default_weight(k)) for k in criteria()}


def priority_slider(k, where=st, width="stretch"):
    """How important a criterion is, 0..10; the same session key on every page."""
    c = criteria()[k]
    where.slider(c["label"], 0, SCALE, value=default_weight(k), step=1, key=f"w_{k}", help=c["help"],
                 persist_state="session", width=width)


def priority_sliders(keys=None, n_cols=3):
    keys = keys or list(criteria())
    for i in range(0, len(keys), n_cols):
        for col, k in zip(st.columns(n_cols, gap="large"), keys[i:i + n_cols]):
            priority_slider(k, col)


# --- field data -------------------------------------------------------------------------------------------------------

def placed(h):
    """{crop: share} in planner crops: the six as they are, other declared crops through their map group."""
    out = {}
    for k, v in (h or {}).items():
        k = PROXY.get(crop_group(k[6:]), k) if k.startswith("other:") else k
        out[k] = out.get(k, 0.0) + v
    return out


def _key(name):
    k = rotation.classify(name)
    return k if k != "other" else f"other:{name or '?'}"


def history(g, past):
    """{year: {crop key: share}} of the area under geometry g (metres) in every FIONA year."""
    area, hist = g.area or 1.0, {}
    for y, k, pg in past:
        if g.intersects(pg):
            share = g.intersection(pg).area / area
            if share > 0.005:
                hist.setdefault(y, {})
                hist[y][k] = hist[y].get(k, 0.0) + share
    return hist


@st.cache_data(show_spinner=False)
def base_plots(fid):
    """This year's FIONA plots of the block, each with its crop history."""
    parcels = [f for f in geojson("parcels")["features"] if f["properties"]["field"] == fid]
    years = sorted({f["properties"]["year"] for f in parcels})
    past = [(f["properties"]["year"], _key(f["properties"].get("crop")), metric(f)) for f in parcels]
    out = []
    for i, f in enumerate(f for f in parcels if f["properties"]["year"] == years[-1]):
        g = metric(f)
        c = _centroid(f)
        out.append({"id": str(f["properties"].get("id") or f.get("id") or f"p{i + 1}"), "ha": g.area / 1e4,
                    "lon": c[0], "lat": c[1], "hist": history(g, past)})
    return out, years


def plots_from(features):
    """Planner features (after cuts, merges and painting) as engine plots."""
    out = []
    for f in features:
        props = f["properties"]
        c = _centroid(f)
        out.append({"id": props["id"], "ha": float(props.get("ha") or 0), "lon": c[0], "lat": c[1],
                    "hist": {int(y): v for y, v in (props.get("hist") or {}).items()},
                    "plan": MODEL.get(props.get("plan"))})
    return out


def _centroid(f):
    from shapely.geometry import shape
    c = shape(f["geometry"]).centroid
    return float(c.x), float(c.y)


@st.cache_data(show_spinner=False)
def surroundings(fid, season, r):
    """Neighbours as expected beet and nurseries per future year, and the region's yardsticks for impact and pressure."""
    par, _, summary = landscape()
    own = par[par.field == fid]
    fx, fy = own[["x", "y"]].mean()
    lon0, lat0 = own[["lon", "lat"]].mean()
    near = par[(np.hypot(par.x - fx, par.y - fy) <= SHOW * r) & (par.field != fid)]
    years = [c for c in (f"c{y}" for y in range(2017, season + 1)) if c in par]
    freq = (near[years] == BEET_CODE).mean(axis=1).to_numpy()
    beet_last = (near[f"c{season}"] == BEET_CODE).to_numpy() if f"c{season}" in near else np.zeros(len(near), bool)
    s = {x["season"]: x for x in summary["seasons"]}
    btw = float(s.get(season, s[max(s)])["beet_to_wheat"])
    nur, beet = pressure(season, r)
    return {"lon0": float(lon0), "lat0": float(lat0), "lon": near.lon.to_numpy(), "lat": near.lat.to_numpy(),
            "ha": near.area_ha.to_numpy(), "beet_freq": freq, "beet_last": beet_last, "btw": btw,
            "impact_ref": float(np.median(nur.impact / nur.nursery_ha)) or 1.0,
            "pressure_ref": float(beet.pressure.quantile(0.9)) or 1.0,
            "erosion_ks": float(fields()[fid]["erosion_ks"]), "nfk": float(own.nfk_mm.mean())}


def _xy(lon, lat, S):
    """Local metres around the block centre, from lon/lat (no assumption about the table's projection)."""
    k = 111_320
    return np.column_stack([(np.asarray(lon) - S["lon0"]) * k * np.cos(np.radians(S["lat0"])),
                            (np.asarray(lat) - S["lat0"]) * k]).astype("float32")


# --- the rotation model -----------------------------------------------------------------------------------------------

def _dates():
    d = dict(strategies()["crop_dates"])
    d.setdefault("potato", POTATO["doy"])
    d.setdefault("fallow", FALLOW["doy"])
    return d


@st.cache_data(show_spinner=False)
def _climate(fid):
    daily = table("daily")
    w, monthly = model.climate_weights(daily[daily.field == fid])
    deficit = monthly.index[monthly.p < monthly.et0].tolist()
    dry = np.isin(pd.date_range("2001-01-01", periods=365).month, deficit)
    return w.erosive.to_numpy(), w.et0.to_numpy(), dry, deficit


@lru_cache(maxsize=4096)
def _season(a, b, fid, cover, mulch):
    """(bare soil x heavy rain, water mm) of the calendar year in which crop b grows after crop a."""
    bare, kc, _ = model.rotation({"sequence": [a, b], "cover_before": list(cover), "mulch": mulch}, _dates())
    erosive, et0, dry, _ = _climate(fid)
    year = slice(365, 730)
    return float((bare[year] * erosive).sum()), float((kc[year] * et0 * dry).sum())


def _fit_key(c):
    return PLANNER.get(c, FIT_AS.get(c, "pea"))


def _last(plot, year):
    """Last year's crops of a plot as model crops with shares (unknown crops as UNKNOWN_AS)."""
    h = placed(plot["hist"].get(year, {}))
    known = {MODEL[k]: v for k, v in h.items() if k in MODEL}
    rest = max(0.0, 1.0 - sum(known.values()))
    if rest > 0.05 or not known:
        known[UNKNOWN_AS] = known.get(UNKNOWN_AS, 0.0) + (rest or 1.0)
    s = sum(known.values())
    return {k: v / s for k, v in known.items()}


def _continue(plot, seq, first_year, lg, start=None):
    """The years of a rotation `seq` on one plot: its natural next crop, unless that breaks a rule there."""
    L, n = len(seq), HORIZON - (1 if start else 0)
    hist = {y: placed(v) for y, v in plot["hist"].items()}
    prev = start or MODEL.get(max(placed(plot["hist"].get(first_year - 1, {})).items(),
                                  key=lambda kv: kv[1], default=("", 0))[0])
    if start:
        hist[first_year] = _hist_entry(start)
    y0 = first_year + (1 if start else 0)
    natural = (seq.index(prev) + 1) % L if prev in seq else 0
    best, best_merit = None, -1e9
    for o in range(L):
        crops, h, merit = [seq[(o + i) % L] for i in range(n)], dict(hist), (2.5 if o == natural else 0.0)
        for i, c in enumerate(crops):
            merit += HEALTH[_health(c, h, y0 + i, lg)]
            h[y0 + i] = _hist_entry(c)
        if merit > best_merit:
            best, best_merit = crops, merit
    return ([start] if start else []) + best


def plans_for(plots, card, first_year, lg):
    return {p["id"]: _continue(p, card["sequence"], first_year, lg) for p in plots}


def custom_plans(plots, card, first_year, lg, fixed=None):
    """Your rotation, year by year: what you painted (first year: green fallow where nothing is painted; later years:
    what you painted on those years' maps), and where a later year is not painted, filled in automatically."""
    out, seq = {}, card["sequence"]
    for p in plots:
        f = (fixed or {}).get(p["id"]) or [None] * HORIZON
        hist = {y: placed(v) for y, v in p["hist"].items()}
        crops = []
        for i in range(HORIZON):
            year = first_year + i
            c = (p.get("plan") or "fallow") if i == 0 else (f[i] or _auto_next(crops[-1], seq, hist, year, lg))
            crops.append(c)
            hist[year] = _hist_entry(c)
        out[p["id"]] = crops
    return out


def _auto_next(prev, seq, hist, year, lg):
    """A year you have not painted: the best match's next crop after `prev`, unless that breaks a rotation rule here;
    then the crop of the best match that fits best."""
    natural = seq[(seq.index(prev) + 1) % len(seq)] if prev in seq else seq[0]
    return max(dict.fromkeys(seq), key=lambda c: HEALTH[_health(c, hist, year, lg)] + (1.6 if c == natural else 0))


def fixed_future(features, future, first_year):
    """{plot id: [None, crop or None, crop or None]}: the crop painted on most of each plot's area on the later years'
    maps (they may be split differently), as model crops."""
    out = {f["properties"]["id"]: [None] * HORIZON for f in features}
    geoms = {f["properties"]["id"]: metric(f) for f in features}
    for i in range(1, HORIZON):
        layer = [(MODEL[g["properties"]["plan"]], metric(g)) for g in (future or {}).get(first_year + i, [])
                 if g["properties"].get("plan") in MODEL]
        for pid, g in geoms.items():
            area = {}
            for c, fg in layer:
                if g.intersects(fg):
                    area[c] = area.get(c, 0.0) + g.intersection(fg).area
            if area and max(area.values()) >= 0.5 * (g.area or 1):
                out[pid][i] = max(area, key=area.get)
    return out


def _hist_entry(c):
    """What a planned year adds to a plot's history for the rotation rules (a fallow year adds no crop)."""
    return {"other:fallow": 1.0} if c == "fallow" else {_fit_key(c): 1.0}


def _health(c, hist, year, lg):
    """The rotation-rule verdict of growing c; a fallow year breaks every crop's cycle."""
    return "good" if c == "fallow" else rotation.fit(_fit_key(c), hist, year, lg)["health"]


@lru_cache(maxsize=256)
def _climate_factor(fid, crop):
    """Yield factor from the EcoCrop climate fit: 1 at a full fit, 0.5 where the crop does not fit at all."""
    try:
        import ecocrop
        return 0.5 + 0.5 * ecocrop.fit(fid, crop, bool(model.CROPS.get(crop, {}).get("winter", False)))["fit"]
    except Exception:  # no EcoCrop table yet, or a crop it does not list
        return 1.0


# --- scoring ------------------------------------------------------------------------------------------------------------

def _p_beet(S, year, season):
    """Each neighbour's chance of growing beet in `year`: known for the last season, from its history after that."""
    if year <= season:
        return S["beet_last"].astype(float)
    if year == season + 1:
        return np.where(S["beet_last"], 0.0, S["beet_freq"])  # beet rarely follows beet
    return S["beet_freq"]


def collab_layer(rows, S, season, first_year):
    """Other farmers' saved plans as known crops per year; the neighbours they cover leave the expected sums."""
    from shapely.geometry import Point, shape
    plots = {}
    for row in rows:
        for f in row["plots"]:
            key = (row["user_id"], row["field_id"], f["properties"]["id"])
            g = shape(f["geometry"])
            pl = plots.setdefault(key, {"geom": g, "ha": float(f["properties"].get("ha") or g.area * 0), "crops": {}})
            if f["properties"].get("plan"):
                pl["crops"][int(row["year"])] = MODEL.get(f["properties"]["plan"])
    plots = [p for p in plots.values() if p["ha"] > 0]
    if not plots:
        return None
    nxy = _xy(S["lon"], S["lat"], S)
    cxy = _xy([p["geom"].centroid.x for p in plots], [p["geom"].centroid.y for p in plots], S)
    covered = np.zeros(len(S["lon"]), bool)
    for p in plots:
        minx, miny, maxx, maxy = p["geom"].bounds
        box = (S["lon"] >= minx) & (S["lon"] <= maxx) & (S["lat"] >= miny) & (S["lat"] <= maxy)
        for i in np.flatnonzero(box):
            covered[i] |= p["geom"].contains(Point(S["lon"][i], S["lat"][i]))
    near = [int(np.argmin(np.hypot(*(nxy - c).T))) if len(nxy) else -1 for c in cxy]
    return {"xy": cxy, "ha": np.array([p["ha"] for p in plots]), "crops": [p["crops"] for p in plots],
            "near": near, "covered": covered}


def _collab_year(C, S, year, season):
    """(nursery ha, beet ha) of the collaborators' plots in one year: saved crops where known, expected otherwise."""
    if C is None:
        return np.zeros(0), np.zeros(0)
    nur, beet = np.zeros(len(C["ha"])), np.zeros(len(C["ha"]))
    for j, (crops, n, ha) in enumerate(zip(C["crops"], C["near"], C["ha"])):
        exp_prev = _p_beet(S, year - 1, season)[n] if n >= 0 else float(np.mean(S["beet_freq"]))
        exp_now = _p_beet(S, year, season)[n] if n >= 0 else float(np.mean(S["beet_freq"]))
        beet_prev = float(crops[year - 1] == "sugar_beet") if year - 1 in crops else exp_prev
        if year in crops:
            beet[j] = ha * (crops[year] == "sugar_beet")
            nur[j] = ha * NURSERY.get(crops[year], 0.0) * beet_prev
        else:
            beet[j] = ha * exp_now
            nur[j] = ha * beet_prev * S["btw"]
    return nur, beet


def evaluate(fid, plots, plans, card, first_year, r, lg, collab=None):
    """Raw sums of one option: plans {plot id: [crop per year]} on plots, with the card's cover crops and mulch.

    collab: other farmers' saved plans (collab_layer), used instead of the expected crops of the parcels they cover.
    """
    season = _setting(fid)[0]
    S = surroundings(fid, season, r)
    cover, mulch = tuple(card.get("cover_before", ["sugar_beet"])), bool(card.get("mulch", False))
    xy = _xy([p["lon"] for p in plots], [p["lat"] for p in plots], S)
    keep = ~collab["covered"] if collab else np.ones(len(S["lon"]), bool)
    nxy = _xy(S["lon"], S["lat"], S)[keep]
    cxy = collab["xy"] if collab else np.zeros((0, 2), "float32")
    A = sum(p["ha"] for p in plots) or 1.0
    acc = dict.fromkeys(("ero", "wat", "income", "rotation", "legume", "cover", "nursery", "reach", "beet", "loss",
                         "bad", "warn", "fallow", "fallow_first"), 0.0)
    cover = cover + ("fallow",)  # a fallow year greens up after the previous harvest
    for i in range(HORIZON):
        year, f = first_year + i, HORIZON * YEAR_WEIGHTS[i]  # f: this year's weight; sums stay "per year" on average
        nur_ha, beet_ha = np.zeros(len(plots)), np.zeros(len(plots))
        for j, p in enumerate(plots):
            c = plans[p["id"]][i]
            prev = _last(p, year - 1) if i == 0 else {plans[p["id"]][i - 1]: 1.0}
            for a, share in prev.items():
                e, w = _season(a, c, fid, cover, mulch)
                acc["ero"] += f * p["ha"] * share * e
                acc["wat"] += f * p["ha"] * share * w
            beet_before = prev.get("sugar_beet", 0.0)
            nur_ha[j] = p["ha"] * NURSERY.get(c, 0.0) * beet_before
            beet_ha[j] = p["ha"] * (c == "sugar_beet")
            hist = {y: placed(v) for y, v in p["hist"].items()}
            for k in range(i):
                hist[first_year + k] = _hist_entry(plans[p["id"]][k])
            health = _health(c, hist, year, lg)
            acc["rotation"] += f * p["ha"] * HEALTH[health]
            acc["bad"] += f * p["ha"] * (health == "bad")
            acc["warn"] += f * p["ha"] * (health == "warn")
            acc["legume"] += f * p["ha"] * LEGUME_N.get(c, 0.0)
            acc["cover"] += f * p["ha"] * (c in cover)
            acc["income"] += f * p["ha"] * INCOME.get(c, 3.0) * _climate_factor(fid, c)  # beet losses come off below
            acc["fallow"] += f * p["ha"] * (c == "fallow")
            acc["fallow_first"] += p["ha"] * (c == "fallow" and i == 0)
        # neighbours: expected beet and nurseries this year; collaborators: their saved crops
        p_nur = _p_beet(S, year - 1, season)[keep] * S["btw"]
        p_beet = _p_beet(S, year, season)[keep]
        c_nur, c_beet = _collab_year(collab, S, year, season)
        all_xy = np.vstack([xy, nxy, cxy]).astype("float32")
        all_nur_ha = np.concatenate([nur_ha, S["ha"][keep] * p_nur, c_nur]).astype("float32")
        all_beet_ha = np.concatenate([beet_ha, S["ha"][keep] * p_beet, c_beet]).astype("float32")
        all_nur_xy = all_beet_xy = all_xy
        if all_nur_ha.sum() > 0 and all_beet_ha.sum() > 0:
            imp, prs = impacts(all_nur_xy, all_nur_ha, all_beet_xy, all_beet_ha, r)  # the pipeline's formula
            imp, prs = np.asarray(imp)[:len(plots)], np.asarray(prs)[:len(plots)]
        else:
            imp, prs = np.zeros(len(plots)), np.zeros(len(plots))
        with np.errstate(divide="ignore", invalid="ignore"):
            reach = np.where(nur_ha > 0, imp / nur_ha / S["impact_ref"], 0.0)
        loss = LOSS_MAX * np.clip(prs / S["pressure_ref"], 0, 1)
        acc["nursery"] += f * nur_ha.sum()
        acc["reach"] += f * float((nur_ha * reach).sum())
        acc["beet"] += f * beet_ha.sum()
        acc["loss"] += f * float((beet_ha * loss).sum())
        acc["income"] -= f * float((beet_ha * loss).sum()) * INCOME["sugar_beet"]
    acc["area"], acc["plans"], acc["first_year"] = A, plans, first_year
    acc["climate"] = {c: _climate_factor(fid, c) for c in {c for p in plots for c in plans[p["id"]]}}
    return acc


def scores(acc, base, S, deficit, lg):
    """Raw sums -> scores 1..5 in the shape the pages use: {criterion: {score, basis, uncertainty, rel, note}}."""
    tx, A, n = TEXT[lg], acc["area"], HORIZON
    f_ero = min(S["erosion_ks"] / 0.55, 1)                      # flat, less erodible fields: differences matter less
    f_wat = float(np.clip(140 / max(S["nfk"], 1), 0.5, 2))      # little plant-available water: differences matter more
    rel_e = acc["ero"] / base["ero"] if base["ero"] else 1.0
    rel_w = acc["wat"] / base["wat"] if base["wat"] else 1.0
    X = acc["reach"] / A                                          # S0 everywhere: about 1 nursery-ha per ha in 3 years
    legume = acc["legume"] / (A * n)
    cover = acc["cover"] / (A * n)
    loss = acc["loss"] / acc["beet"] if acc["beet"] else 0.0
    out = {
        "erosion": {"score": float(np.clip(3 + 4 * f_ero * (1 - rel_e), 1, 5)), "basis": "model", "rel": rel_e},
        "water": {"score": float(np.clip(3 + 4 * f_wat * (1 - rel_w), 1, 5)), "basis": "model", "rel": rel_w,
                  "months": deficit},
        "planthopper": {"score": float(np.clip(4 - 3 * X, 1, 4)), "basis": "rule",
                        "detail": tx["ph"].format(ha=f"{acc['nursery'] / n:.1f}", rel=f"{acc['reach'] / acc['nursery']:.0%}")
                        if acc["nursery"] else tx["ph0"]},
        "nitrogen": {"score": float(np.clip(2 + legume + COVER_N * max(0.0, cover - 1 / 3), 1, 5)), "basis": "rule",
                     "detail": tx["n"].format(ha=f"{acc.get('legume_ha', 0.0) / n:.1f}")},
        # cropped land scores 1..5; fallow land earns nothing and scores 0, so unplanted land can never look like income
        "income": {"score": float(np.clip(acc["income"] / max(A * n - acc["fallow"], 1e-9), 1, 5)
                                  * (1 - acc["fallow"] / (A * n))), "basis": "rule",
                   "detail": " ".join(x for x in (
                       tx["fallow"].format(ha=f"{acc['fallow_first']:.1f}", year=acc["first_year"])
                       if acc["fallow_first"] else "",
                       tx["loss"].format(loss=f"{loss:.0%}") if acc["beet"] else "",
                       tx["climate"].format(crops=", ".join(f"{_crop_label(c, lg)} {2 * v - 1:.0%}"
                                                            for c, v in acc.get("climate", {}).items() if v < 0.9))
                       if any(v < 0.9 for v in acc.get("climate", {}).values()) else "") if x)},
        "rotation": {"score": float(acc["rotation"] / (A * n)), "basis": "rule",
                     "detail": tx["rot"].format(bad=f"{acc['bad'] / n:.1f}", warn=f"{acc['warn'] / n:.1f}")
                     if acc["bad"] or acc["warn"] else tx["rot0"]},
    }
    for k, v in out.items():
        v["score"] = round(v["score"], 1)
        v.setdefault("uncertainty", "medium" if k in ("rotation", "nitrogen") else "high")
    return out


def _cards(optional=True):
    return {s["id"]: s for s in content("strategies")["strategy"] if optional or not s.get("optional")}


def _setting(fid):
    years = base_plots(fid)[1]
    seasons = sorted(landscape()[1].season.unique())
    season = years[-1] if years[-1] in seasons else int(seasons[-1])
    return int(season), int(st.session_state.get("ls_r", 1000))


@st.cache_data(show_spinner="Scoring the options on your plots…")
def strategy_scores(fid, r, lg) -> dict:
    """Scores of every strategy card on this block's plots: {sid: {"scores": ..., "plans": ...}}."""
    plots, _ = base_plots(fid)
    season, _ = _setting(fid)
    return _score_cards(fid, plots, season, r, lg)


def _score_cards(fid, plots, season, r, lg, extra=None, first_year=None, collab=None):
    cards = _cards()
    first_year = first_year or season + 1
    S = surroundings(fid, season, r)
    deficit = _climate(fid)[3]
    raw = {sid: evaluate(fid, plots, plans_for(plots, c, first_year, lg), c, first_year, r, lg, collab)
           for sid, c in cards.items()}
    if extra:
        raw |= {k: evaluate(fid, plots, plans, cards[sid], first_year, r, lg, collab) for k, (plans, sid) in extra.items()}
    out = {}
    for k, acc in raw.items():
        acc["legume_ha"] = sum(HORIZON * YEAR_WEIGHTS[i] * p["ha"] for p in plots
                               for i, c in enumerate(acc["plans"][p["id"]]) if c in LEGUME_N)
        out[k] = {"scores": scores(acc, raw["S0"], S, deficit, lg), "plans": acc["plans"],
                  "fallow_ha_first": sum(p["ha"] for p in plots if acc["plans"][p["id"]][0] == "fallow")}
    return out


def total(sc, w):
    w = w if sum(w.values()) else dict.fromkeys(w, 1)
    return sum(w[k] * sc[k]["score"] for k in w) / sum(w.values())


def rank(fid, w=None, optional=False):
    """(ids best first, weighted score per id, card per id), like data.rank_options always returned."""
    w = w or weights()
    season, r = _setting(fid)
    res = strategy_scores(fid, r, lang())
    cards = _cards(optional)
    tot = {sid: total(res[sid]["scores"], w) for sid in cards}
    return sorted(cards, key=tot.get, reverse=True), tot, cards


def compare_custom(fid, features, optional=False, year=None, others=(), future=None):
    """Best match and your painted plan on the planner's plots, both as the same three years from `year`.

    others: other farmers' saved plans (plans_store), whose crops replace the expected ones around the block.
    """
    lg, w = lang(), weights()
    season, r = _setting(fid)
    year = year or season + 1
    plots = plots_from(features)
    collab = collab_layer(list(others), surroundings(fid, season, r), season, year) if others else None
    cards = _cards(optional)
    res = _score_cards(fid, plots, season, r, lg, first_year=year, collab=collab)
    best = max(cards, key=lambda sid: total(res[sid]["scores"], w))  # the best match for this year, on these plots
    fixed = fixed_future(features, future, year)
    res = _score_cards(fid, plots, season, r, lg, first_year=year, collab=collab,
                       extra={"custom": (custom_plans(plots, cards[best], year, lg, fixed), best)})
    n_collab = len(collab["ha"]) if collab else 0
    painted = {p["id"]: [bool(p.get("plan"))] + [c is not None for c in fixed[p["id"]][1:]] for p in plots}
    return best, {"best": res[best], "custom": res["custom"], "weights": w, "first_year": year, "collab_plots": n_collab,
                  "painted": painted}


def field_scores(fid):
    """Every strategy's scores on this block (cached per flight range and language): {sid: {"scores", "plans"}}."""
    _, r = _setting(fid)
    return strategy_scores(fid, r, lang())
