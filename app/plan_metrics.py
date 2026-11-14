"""Your plan against the best-matching strategy, both as next year on your own plots, scored the same way.

Both columns run through one function (_score), so they can only differ where the crops differ:
- best match: what the top strategy card would grow on each plot next year: the next crop of its sequence after last
  year's crop, unless that breaks a rotation rule or makes a planthopper nursery there; then its best-fitting crop.
- your plan: the crop you painted; plots you have not painted follow the best match, so both columns start equal.
Per plot, weighted by area:
- erosion and water: the daily model of pipeline/strategies.py (rotation, climate_weights) for next year after last
  year's crop, against S0's model values on this field (strategies.json), with the cards' score formulas.
- planthopper, nitrogen and income: the rule scores on the strategy cards, per crop. Winter wheat on last year's beet
  scores like S0 (1), a crop that is not a winter cereal like S1/S4 (4), winter barley on beet 2 (see rotation.py).
- rotation rules: the red/amber/green rules of the map (rotation.py) without the planthopper rule, which has its own row.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
import streamlit as st

import rotation
from data import content, crop_group, model_note, rank_options, strategies, table, weights
from i18n import num
from plain import compare, dots

from pipeline import strategies as model  # noqa: E402  (data.py puts the project root on the path)

# planner crop (rotation.py) <-> crop of the rotation model (content/crops.toml)
MODEL = {"beet": "sugar_beet", "wheat": "winter_wheat", "barley": "winter_barley", "maize": "grain_maize",
         "pea": "field_pea", "potato": "potato"}
PLANNER = {v: k for k, v in MODEL.items()}
# declared crops outside the six, by their map group (data.crop_group): spelt, rye, triticale -> wheat, beans -> pea ...
PROXY = {"cereal": "wheat", "legume": "pea", "veg": "potato", "maize": "maize", "beet": "beet"}
CARD = {"sugar_beet": "S0", "winter_wheat": "S0", "winter_barley": "S0", "grain_maize": "S1", "soybean": "S2",
        "field_pea": "S4"}  # model crop -> the card its rule scores come from
# Potatoes are on no card and not in crops.toml yet: a literature estimate (general agronomy) until the content lead adds
# [potato] to content/crops.toml, which then wins. Kc from FAO-56 Table 12 (Allen et al. 1998).
POTATO = {"label": "Potatoes", "winter": False, "kc_mid": 1.15, "kc_end": 0.75,
          "doy": {"sow": 105, "emerge": 130, "canopy": 165, "harvest": 255}}
POTATO_RULES = {"nitrogen": 2, "income": 3}  # like S0's crops: no legume, an established crop (estimate)
BARLEY_ON_BEET = 2
COVER_BEFORE = ["sugar_beet"]  # as in S0, the rotation every card is compared with
MIN_KNOWN = 0.5                # a plot counts when known crops covered at least half of it last year
FIT_AS = {"soybean": "pea"}  # crops without rotation rules of their own are judged like their nearest crop
HEALTH = {"bad": 1, "warn": 2, "ok": 3, "good": 4, "unknown": 3}  # rotation-rule verdict -> score
ROTATION_WEIGHT = 4            # "very important" in the overall score: breaking a rotation rule must cost
model.CROPS.setdefault("potato", POTATO)

TEXT = {
    "en": {"title": "Your plan against the best match", "best": "Best match: {name}", "plan": "Your custom plan",
           "sub": "next year on your plots", "rotation": "Rotation rules", "overall": "Overall, with your priorities",
           "rot_note": "{plan} ha break a rotation rule, {warn} ha carry a risk (best match: {best} ha break one).",
           "nursery": "{plan} ha of winter cereals right after beet (best match: {best} ha).",
           "legume": "{plan} ha of legumes (best match: {best} ha).", "income_note": "Rule scores from the strategy cards.",
           "potato": " Potatoes are on no card yet: estimate.",
           "method": "Both columns are {target} on your plots, worked out the same way: the best match grows, on each plot, "
                     "the next crop of its rotation, or another of its crops where that would break a rule, your plan grows what you painted, and plots you have not painted "
                     "follow the best match. Erosion and water: the strategy cards' daily model against today's rotation (S0). "
                     "Planthopper, nitrogen, income: the cards' rule scores. Rotation rules: the map's colours. {planned} of "
                     "{total} ha painted.",
           "unknown": " {ha} ha with crops we cannot place (e.g. rapeseed, grassland) are left out.",
           "proxy": " Spelt, rye or triticale count as winter wheat, other pulses as peas, vegetables as potatoes."},
    "de": {"title": "Ihr Plan im Vergleich zur besten Option", "best": "Beste Option: {name}", "plan": "Ihr eigener Plan",
           "sub": "nächstes Jahr auf Ihren Schlägen", "rotation": "Fruchtfolgeregeln", "overall": "Gesamt, nach Ihren Prioritäten",
           "rot_note": "{plan} ha verletzen eine Fruchtfolgeregel, {warn} ha mit Risiko (beste Option: {best} ha).",
           "nursery": "{plan} ha Wintergetreide direkt nach Rüben (beste Option: {best} ha).",
           "legume": "{plan} ha Leguminosen (beste Option: {best} ha).", "income_note": "Regelwerte der Strategiekarten.",
           "potato": " Kartoffeln stehen noch auf keiner Karte: Schätzung.",
           "method": "Beide Spalten zeigen {target} auf Ihren Schlägen, gleich berechnet: die beste Option baut auf jedem "
                     "Schlag die nächste Kultur ihrer Fruchtfolge an, oder eine andere ihrer Kulturen, wo jene eine Regel verletzt, Ihr Plan das Gemalte, und ungemalte Schläge "
                     "folgen der besten Option. Erosion und Wasser: das Tagesmodell der Strategiekarten gegen die heutige "
                     "Fruchtfolge (S0). Zikade, Stickstoff, Einkommen: die Regelwerte der Karten. Fruchtfolgeregeln: die "
                     "Farben der Karte. {planned} von {total} ha bemalt.",
           "unknown": " {ha} ha mit Kulturen, die wir nicht zuordnen können (z. B. Raps, Grünland), fehlen.",
           "proxy": " Dinkel, Roggen oder Triticale zählen als Winterweizen, andere Leguminosen als Erbsen, Gemüse als Kartoffeln."},
}


def _dates():
    d = dict(strategies()["crop_dates"])
    d.setdefault("potato", POTATO["doy"])
    return d


@st.cache_data
def _climate(fid):
    """Per day of year: erosive rain, ET0 and the dry-month mask, exactly as pipeline/strategies.py main() builds them."""
    daily = table("daily")
    w, monthly = model.climate_weights(daily[daily.field == fid])
    deficit = monthly.index[monthly.p < monthly.et0].tolist()
    dry = np.isin(pd.date_range("2001-01-01", periods=365).month, deficit)
    return w.erosive.to_numpy(), w.et0.to_numpy(), dry, deficit


@lru_cache(maxsize=512)
def _season(a, b, fid, ks):
    """(erosion index, water mm) of the calendar year in which crop b grows after crop a, with the cards' model."""
    bare, kc, _ = model.rotation({"sequence": [a, b], "cover_before": COVER_BEFORE, "mulch": False}, _dates())
    erosive, et0, dry, _ = _climate(fid)
    year = slice(365, 730)  # the second year of the two-crop cycle: the year crop b is harvested
    return ks * float((bare[year] * erosive).sum()), float((kc[year] * et0 * dry).sum())


def _placed(h):
    """A year's {crop: share} in planner crops: the six as they are, other declared crops through their map group."""
    out = {}
    for k, v in (h or {}).items():
        k = PROXY.get(crop_group(k[6:]), k) if k.startswith("other:") else k
        if k in MODEL:
            out[k] = out.get(k, 0.0) + v
    return out


def _rule(crit, crop, cards):
    return cards[CARD[crop]]["scores"][crit]["score"] if crop in CARD else POTATO_RULES[crit]


def _successor(crop, seq):
    """The crop a strategy grows after `crop`: the next one in its sequence, else its first crop."""
    return seq[(seq.index(crop) + 1) % len(seq)] if crop in seq else seq[0]


def _score(plots, choose, fid, ks, target, cards, lang):
    """Five card criteria plus rotation rules for one set of choices. choose(plot, last) -> {model crop: share}."""
    acc = {k: 0.0 for k in ("ero", "wat", "planthopper", "nitrogen", "income", "rotation", "ha",
                            "nursery", "legume", "bad", "warn")}
    nursery, safe = cards["S0"]["scores"]["planthopper"]["score"], cards["S1"]["scores"]["planthopper"]["score"]
    for plot in plots:
        ha, last, hist = plot["ha"], plot["last"], plot["hist"]
        dist = choose(plot, last)
        beet = hist.get(target - 1, {}).get("beet", 0.0)
        acc["ha"] += ha
        for c, share in dist.items():
            w = ha * share
            acc["ero"] += w * sum(sn * _season(MODEL[n], c, fid, ks)[0] for n, sn in last.items())
            acc["wat"] += w * sum(sn * _season(MODEL[n], c, fid, ks)[1] for n, sn in last.items())
            for k in ("nitrogen", "income"):
                acc[k] += w * _rule(k, c, cards)
            on_beet = {"winter_wheat": nursery, "winter_barley": BARLEY_ON_BEET}.get(c, safe)
            acc["planthopper"] += w * (beet * on_beet + (1 - beet) * safe)
            acc["nursery"] += w * beet * (c in ("winter_wheat", "winter_barley"))
            acc["legume"] += w * (c in ("field_pea", "soybean"))
            health = rotation.fit(PLANNER.get(c, FIT_AS.get(c, "pea")), hist, target, lang)["health"]
            acc["rotation"] += w * HEALTH[health]
            acc["bad"] += w * (health == "bad")
            acc["warn"] += w * (health == "warn")
    return acc


def plan_metrics(fid: str, p: dict, features: list[dict], years: list[int], lang: str = "en") -> None:
    """The comparison table under the planner map. `features` are the planner plots with properties hist, plan, ha."""
    tx = TEXT[lang]
    crit = content("strategies")["criteria"]
    cards = {s["id"]: s for s in content("strategies")["strategy"]}
    res = strategies()["fields"][fid]["strategies"]
    order, _, _ = rank_options(fid, optional=st.session_state.get("show_s4", False))  # the same order as the table above
    best = order[0]
    seq = cards[best]["sequence"]
    last_year, target = years[-1], years[-1] + 1
    ks = float(p["erosion_ks"])
    _, _, _, deficit = _climate(fid)

    plots, total_ha, painted_ha, unknown_ha, proxied, potato = [], 0.0, 0.0, 0.0, False, False
    for f in features:
        props = f["properties"]
        ha = float(props.get("ha") or 0)
        total_ha += ha
        hist = {int(y): _placed(v) for y, v in (props.get("hist") or {}).items()}
        raw_last = (props.get("hist") or {}).get(str(last_year), {})
        proxied |= any(k.startswith("other:") and PROXY.get(crop_group(k[6:])) for k in raw_last)
        last = hist.get(last_year, {})
        if sum(last.values()) < MIN_KNOWN:
            unknown_ha += ha
            continue
        s = sum(last.values())
        plan = props.get("plan")
        painted_ha += ha if plan else 0
        potato |= plan == "potato"
        plots.append({"ha": ha, "hist": hist, "last": {k: v / s for k, v in last.items()},
                      "plan": MODEL[plan] if plan in MODEL else None})

    def best_choice(plot, last):
        """The strategy's next crop here, unless that breaks a rotation rule or makes a nursery: then its best-fitting crop."""
        top = max(last, key=last.get)
        beet = plot["hist"].get(last_year, {}).get("beet", 0.0)

        def merit(c):
            fit = rotation.fit(PLANNER.get(c, FIT_AS.get(c, "pea")), plot["hist"], target, lang)
            nursery_risk = beet if c in ("winter_wheat", "winter_barley") else 0.0
            return HEALTH[fit["health"]] - 3 * nursery_risk + (2.5 if c == _successor(MODEL[top], seq) else 0)  # keep its rotation unless that breaks a rule

        return {max(dict.fromkeys(seq), key=merit): 1.0}

    yours = lambda plot, last: {plot["plan"]: 1.0} if plot["plan"] else best_choice(plot, last)
    cols = [_score(plots, best_choice, fid, ks, target, cards, lang), _score(plots, yours, fid, ks, target, cards, lang)]

    # the same score formulas as pipeline/strategies.py, against S0's model values on this field
    f_scale = min(ks / 0.55, 1)
    base = {"ero": res["S0"]["erosion_index"], "wat": res["S0"]["water_mm"]}
    scores, notes = {}, {}
    for k, kind in (("erosion", "ero"), ("water", "wat")):
        rels = [(c[kind] / c["ha"]) / base[kind] if c["ha"] and base[kind] else 1.0 for c in cols]
        fn = (lambda r: np.clip(3 + 4 * f_scale * (1 - r), 1, 5)) if k == "erosion" else (lambda r: np.clip(3 - 10 * (r - 1), 1, 5))
        scores[k] = tuple(round(float(fn(r)), 1) for r in rels)
        notes[k] = model_note(k, {"rel": rels[1], "months": deficit})
    for k in ("planthopper", "nitrogen", "income", "rotation"):
        scores[k] = tuple(round(c[k] / c["ha"], 1) if c["ha"] else 3.0 for c in cols)
    notes["planthopper"] = tx["nursery"].format(plan=num(cols[1]["nursery"], 1), best=num(cols[0]["nursery"], 1))
    notes["nitrogen"] = tx["legume"].format(plan=num(cols[1]["legume"], 1), best=num(cols[0]["legume"], 1))
    notes["income"] = tx["income_note"] + (tx["potato"] if potato else "")
    notes["rotation"] = tx["rot_note"].format(plan=num(cols[1]["bad"], 1), warn=num(cols[1]["warn"], 1),
                                              best=num(cols[0]["bad"], 1))

    w = weights()
    w = w if sum(w.values()) else dict.fromkeys(w, 1)
    w = {**w, "rotation": ROTATION_WEIGHT}
    rows_keys = list(crit) + ["rotation"]
    overall = [round(sum(w[k] * scores[k][i] for k in rows_keys) / sum(w[k] for k in rows_keys), 1) for i in (0, 1)]

    label = {k: c["label"] for k, c in crit.items()} | {"rotation": tx["rotation"]}
    rows = "".join(f'<tr><td><b>{label[k]}</b><span class="g">{notes[k]}</span></td>'
                   f'<td>{dots(scores[k][0])}<span class="g">{num(scores[k][0], 1)}</span></td>'
                   f'<td>{_change(*scores[k])}</td></tr>' for k in rows_keys)
    rows += (f'<tr class="top"><td><b>{tx["overall"]}</b></td><td>{dots(overall[0])}<span class="g">{num(overall[0], 1)}</span></td>'
             f'<td>{_change(*overall)}</td></tr>')
    name = cards[best]["name"]
    head = (f'<th></th><th>{tx["best"].format(name=name)}<span class="g">{tx["sub"]}</span></th>'
            f'<th>{tx["plan"]}<span class="g">{tx["sub"]}</span></th>')
    st.subheader(tx["title"])
    st.html(f'<div style="overflow-x:auto"><table class="cc-table cc-compare"><thead><tr>{head}</tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')
    st.caption(tx["method"].format(target=target, planned=num(painted_ha, 1), total=num(total_ha, 1))
               + (tx["unknown"].format(ha=num(unknown_ha, 1)) if unknown_ha >= 0.05 else "")
               + (tx["proxy"] if proxied else ""))


def _change(t0, t1):
    """Dots for the plan, the cards' better/same/worse word, and the number, so small changes still show."""
    word, tone = compare(t1 - t0)
    delta = f" ({'+' if t1 > t0 else '−'}{num(abs(t1 - t0), 1)})" if abs(t1 - t0) >= 0.05 else ""
    return f'{dots(t1)}<span class="g {tone}">{num(t1, 1)} · {word}{delta}</span>'
