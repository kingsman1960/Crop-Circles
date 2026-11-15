"""Crop rotation rules for the planner, hardcoded for six crops until the crop table exists.

fit(crop, history, year) says how well a crop suits a plot next year, from what grew there before:
"bad" (red), "warn" (light red), "ok", "good" (green) or "unknown", each with the reasons in plain words.
history is {year: {crop_key: share of the plot}}, worked out from the FIONA declarations (see plot_history).
"""
from __future__ import annotations

import re

# family and gap: the crop should not come back within `gap` years (repeat = how bad it is if it does)
CROPS = {
    "potato": {"label": {"en": "Potatoes", "de": "Kartoffeln"}, "family": "Solanaceae", "leaf": True,
               "rgb": [123, 74, 38], "gap": 3, "repeat": "bad",
               "repeat_why": {"en": "nematodes and soil-borne diseases build up",
                              "de": "Nematoden und bodenbürtige Krankheiten reichern sich an"},
               "match": r"kartoffel|potato"},
    "wheat": {"label": {"en": "Winter wheat", "de": "Winterweizen"}, "family": "Poaceae", "leaf": False,
              "rgb": [227, 173, 66], "gap": 1, "repeat": "warn",
              "repeat_why": {"en": "take-all and leaf diseases build up", "de": "Schwarzbeinigkeit und Blattkrankheiten nehmen zu"},
              "match": r"weizen|wheat"},
    "maize": {"label": {"en": "Maize", "de": "Mais"}, "family": "Poaceae", "leaf": False,
              "rgb": [74, 127, 209], "gap": 1, "repeat": "warn",
              "repeat_why": {"en": "corn rootworm and Fusarium build up", "de": "Maiswurzelbohrer und Fusarium nehmen zu"},
              "match": r"mais|maize|corn"},
    "pea": {"label": {"en": "Peas", "de": "Erbsen"}, "family": "Fabaceae", "leaf": True,
            "rgb": [106, 168, 79], "gap": 5, "repeat": "bad",
            "repeat_why": {"en": "foot and root rot stay in the soil for years", "de": "Fuß- und Wurzelkrankheiten bleiben jahrelang im Boden"},
            "match": r"erbse|\bpeas?\b"},
    "beet": {"label": {"en": "Sugar beet", "de": "Zuckerrüben"}, "family": "Amaranthaceae", "leaf": True,
             "rgb": [168, 80, 127], "gap": 2, "repeat": "bad",  # beet every third year, as S0, is the regional standard
             "repeat_why": {"en": "beet cyst nematodes build up", "de": "Rübenzystennematoden reichern sich an"},
             "match": r"r(ü|ue)be|beet"},
    "barley": {"label": {"en": "Barley", "de": "Gerste"}, "family": "Poaceae", "leaf": False,
               "rgb": [239, 201, 112], "gap": 1, "repeat": "warn",
               "repeat_why": {"en": "net blotch and other leaf diseases build up", "de": "Netzflecken und andere Blattkrankheiten nehmen zu"},
               "match": r"gerste|barley"},
}
OTHER_RGB = [200, 204, 212]
PRESENT = 0.2   # a crop counts as "grown here" when it covered at least this share of the plot
MOSTLY = 0.5
LEVELS = ["unknown", "good", "ok", "warn", "bad"]  # later = worse; the worst rule wins

TEXT = {
    "en": {
        "gap": "{crop} grew here in {year} ({share}). It needs {gap} years away, because {why}.",
        "repeat": "{crop} grew here last year ({share}): {why}.",
        "planthopper": "Wheat right after sugar beet ({share} beet in {year}) becomes a winter nursery for the reed "
                       "planthopper, which spreads SBR and Stolbur to beet nearby.",
        "planthopper_barley": "Winter barley after sugar beet ({share} beet in {year}) may also shelter planthopper nymphs. "
                              "Our sources name wheat, so check with your advisor.",
        "fusarium": "Wheat after maize ({share} in {year}) raises the Fusarium and mycotoxin risk, more so without ploughing.",
        "cereals": "This would be the third cereal in a row: grass weeds and cereal diseases build up.",
        "after_leaf": "Good fit: {prev} last year breaks cereal diseases and leaves the soil loose.",
        "after_pea": "Peas last year leave nitrogen behind for this crop.",
        "after_cereal": "Good fit: a leaf crop after cereals breaks cereal diseases and grass weeds.",
        "nothing": "No rotation rule speaks against it.",
        "no_data": "No declared crops found for this plot.",
    },
    "de": {
        "gap": "{crop} stand hier {year} ({share}). Sie braucht {gap} Jahre Pause, weil {why}.",
        "repeat": "{crop} stand hier letztes Jahr ({share}): {why}.",
        "planthopper": "Weizen direkt nach Zuckerrüben ({share} Rübe {year}) wird zur Winter-Kinderstube der "
                       "Schilf-Glasflügelzikade, die SBR und Stolbur in nahe Rüben trägt.",
        "planthopper_barley": "Wintergerste nach Zuckerrüben ({share} Rübe {year}) kann ebenfalls Zikadenlarven beherbergen. "
                              "Unsere Quellen nennen Weizen, bitte mit der Beratung klären.",
        "fusarium": "Weizen nach Mais ({share} in {year}) erhöht das Fusarium- und Mykotoxinrisiko, vor allem ohne Pflug.",
        "cereals": "Das wäre das dritte Getreide in Folge: Ungräser und Getreidekrankheiten nehmen zu.",
        "after_leaf": "Passt gut: {prev} im Vorjahr unterbricht Getreidekrankheiten und hinterlässt lockeren Boden.",
        "after_pea": "Erbsen im Vorjahr hinterlassen Stickstoff für diese Kultur.",
        "after_cereal": "Passt gut: eine Blattfrucht nach Getreide unterbricht Getreidekrankheiten und Ungräser.",
        "nothing": "Keine Fruchtfolgeregel spricht dagegen.",
        "no_data": "Für diese Fläche sind keine Kulturen gemeldet.",
    },
}


def classify(name) -> str:
    """Map a declared crop name (German or English) to one of the six crop keys, else "other"."""
    s = str(name or "").lower()
    for key, c in CROPS.items():
        if re.search(c["match"], s):
            return key
    return "other"


def label(key, lang="en"):
    return CROPS[key]["label"][lang] if key in CROPS else ("Other" if lang == "en" else "Sonstige")


def fit(crop: str, history: dict[int, dict[str, float]], year: int, lang: str = "en") -> dict:
    """How well `crop` suits a plot in `year`, given its history. Returns {"level", "why": [sentences]}."""
    tx, c = TEXT[lang], CROPS[crop]
    if not any(history.values()):
        return {"level": "unknown", "why": [tx["no_data"]], "health": "unknown"}
    share = lambda y, k: history.get(y, {}).get(k, 0.0)
    pct = lambda v: f"{v:.0%}"
    found = []  # (level, sentence, rule)
    last = year - 1

    for y in range(year - c["gap"], year):  # 1. the crop's own break
        if share(y, crop) >= PRESENT:
            why = c["repeat_why"][lang]
            found.append((c["repeat"], tx["repeat"].format(crop=label(crop, lang), share=pct(share(y, crop)), why=why)
                          if c["gap"] == 1 else
                          tx["gap"].format(crop=label(crop, lang), year=y, share=pct(share(y, crop)), gap=c["gap"], why=why),
                          "gap"))
            break
    if share(last, "beet") >= PRESENT:  # 2. the planthopper nursery
        if crop == "wheat":
            found.append(("bad", tx["planthopper"].format(share=pct(share(last, "beet")), year=last), "planthopper"))
        elif crop == "barley":
            found.append(("warn", tx["planthopper_barley"].format(share=pct(share(last, "beet")), year=last), "planthopper"))
    if crop == "wheat" and share(last, "maize") >= PRESENT:  # 3. Fusarium
        found.append(("warn", tx["fusarium"].format(share=pct(share(last, "maize")), year=last), "fusarium"))
    cereal = lambda y: sum(share(y, k) for k in ("wheat", "barley", "maize")) >= MOSTLY
    if crop in ("wheat", "barley") and cereal(last) and cereal(last - 1):  # 4. cereal after cereal after cereal
        found.append(("warn", tx["cereals"], "cereals"))

    if not any(lvl in ("bad", "warn") for lvl, _, _ in found):  # 5. what speaks for it
        leaf_last = max((k for k in CROPS if CROPS[k]["leaf"]), key=lambda k: share(last, k))
        if not c["leaf"] and share(last, leaf_last) >= MOSTLY:
            found.append(("good", tx["after_leaf"].format(prev=label(leaf_last, lang)), "good"))
            if leaf_last == "pea":
                found.append(("good", tx["after_pea"], "good"))
        elif c["leaf"] and cereal(last):
            found.append(("good", tx["after_cereal"], "good"))
    if not found:
        return {"level": "ok", "why": [tx["nothing"]], "health": "ok"}
    worst = lambda items: max((lvl for lvl, _, _ in items), key=LEVELS.index) if items else "ok"
    # "health": the same verdict without the planthopper rule, which the metrics score in its own row
    return {"level": worst(found), "why": [s for lvl, s, _ in sorted(found, key=lambda x: -LEVELS.index(x[0]))],
            "health": worst([f for f in found if f[2] != "planthopper"])}
