"""Crop Circles design system, Python side. The markup here pairs with assets/tokens.css + assets/app.css.

The visual language, in three rules:
  colour  magenta is the planthopper (pressure), green is what helps, gold is wheat sown after beet;
  line    solid is yours, dashed is shared with neighbours or the flight range;
  number  the landing page's chapters are numbered with a ring; the platform pages are not steps and carry no number.

Page header, numbers, legends, source lines, footer, the score marks (dots, ten, level) and the story pieces
of the landing page live here. Story texts that are new in this design are kept in STORY below (en + de);
move them into the locale files whenever you like and swap s() for t()."""
import html
from pathlib import Path

import streamlit as st

from i18n import lang, t

ASSETS = Path(__file__).parent / "assets"
LEVEL_TONE = {"high": "bad", "medium": "mid", "low": "good"}

STORY = {
    "en": {
        "step": "Step {n} of 4",
        "source": "Source: {source}.",
        "help": "What this means",
        "hero.title": "Your beet field depends on your neighbour's wheat.",
        "hero.sub": "The planthopper that carries SBR and stolbur into sugar beet spends the winter in wheat sown "
                    "after beet. In early summer it flies a few hundred metres to the nearest beet field. No farm can "
                    "stop it alone. Crop Circles shows every farm in the Kraichgau which of its fields matter most "
                    "to everyone around it.",
        "hero.how": "How it works",
        "legend.beet": "Sugar beet this year",
        "legend.nursery": "Wheat after last year's beet, where planthoppers spend the winter",
        "legend.switch": "Switched to another crop",
        "legend.ring": "How far they fly: about 500 m around each farm",
        "cycle.title": "How the planthopper reaches your beet",
        "cycle.1.when": "Summer",
        "cycle.1.text": "Adults lay their eggs at the beet. The young feed on its roots.",
        "cycle.2.when": "Autumn",
        "cycle.2.text": "The beet is lifted and wheat is sown. The young stay in the soil.",
        "cycle.3.when": "Winter to spring",
        "cycle.3.text": "They live on the roots of the wheat. The field is now a nursery.",
        "cycle.4.when": "Early summer",
        "cycle.4.text": "New adults fly out to the nearest beet field. Often it belongs to a neighbour.",
        "cycle.turn": "So the fix is shared too. When some of the wheat-after-beet fields grow something else, "
                      "chosen where they matter most, the whole ring gets fewer planthoppers.",
        "chapters.title": "From your field to the whole region",
        "chapter.neighbours.title": "Agree on it with your neighbours",
        "chapter.neighbours.text": "Post a note, ask a question, or send an alert to the plant-protection office. "
                                   "A post about a field links straight to that field.",
        "footer.made": "Crop Circles is made for the farms of the Kraichgau, for the NASA Space Apps Challenge "
                       "2026 (Field Shift).",
        "footer.data": "Built on NASA Earth observations, DWD weather stations and official crop maps.",
        "footer.know": "Where the numbers come from",
    },
    "de": {
        "step": "Schritt {n} von 4",
        "source": "Quelle: {source}.",
        "help": "Was das heißt",
        "hero.title": "Ihr Rübenfeld hängt am Weizen Ihres Nachbarn.",
        "hero.sub": "Die Schilf-Glasflügelzikade, die SBR und Stolbur in die Zuckerrübe trägt, überwintert im "
                    "Weizen nach Rüben. Im Frühsommer fliegt sie einige hundert Meter weit zum nächsten Rübenfeld. "
                    "Kein Betrieb kann sie allein aufhalten. Crop Circles zeigt jedem Betrieb im Kraichgau, welche "
                    "seiner Flächen für alle ringsum am meisten zählen.",
        "hero.how": "So funktioniert es",
        "legend.beet": "Zuckerrüben in diesem Jahr",
        "legend.nursery": "Weizen nach Rüben vom Vorjahr: hier überwintern die Zikaden",
        "legend.switch": "Auf eine andere Kultur umgestellt",
        "legend.ring": "So weit fliegen sie: rund 500 m um jeden Betrieb",
        "cycle.title": "Wie die Zikade an Ihre Rüben kommt",
        "cycle.1.when": "Sommer",
        "cycle.1.text": "Die Zikaden legen ihre Eier an die Rübe. Die Larven saugen an den Wurzeln.",
        "cycle.2.when": "Herbst",
        "cycle.2.text": "Die Rübe wird gerodet, Weizen wird gesät. Die Larven bleiben im Boden.",
        "cycle.3.when": "Winter bis Frühjahr",
        "cycle.3.text": "Sie leben von den Weizenwurzeln. Das Feld ist jetzt eine Kinderstube.",
        "cycle.4.when": "Frühsommer",
        "cycle.4.text": "Die neuen Zikaden fliegen zum nächsten Rübenfeld. Oft gehört es dem Nachbarn.",
        "cycle.turn": "Darum ist auch die Lösung gemeinsam. Wenn ein Teil der Weizenflächen nach Rüben etwas "
                      "anderes trägt, dort wo es am meisten bringt, hat der ganze Ring weniger Zikaden.",
        "chapters.title": "Vom eigenen Feld zur ganzen Region",
        "chapter.neighbours.title": "Mit den Nachbarn abstimmen",
        "chapter.neighbours.text": "Schreiben Sie eine Notiz, stellen Sie eine Frage oder melden Sie dem "
                                   "Pflanzenschutzdienst einen Befund. Ein Beitrag zu einem Feld führt direkt dorthin.",
        "footer.made": "Crop Circles ist für die Betriebe im Kraichgau gemacht, für die NASA Space Apps Challenge "
                       "2026 (Field Shift).",
        "footer.data": "Grundlage sind NASA-Erdbeobachtung, DWD-Wetterstationen und amtliche Kulturkarten.",
        "footer.know": "Woher die Zahlen kommen",
    },
}


def s(key, **kw):
    """A story text in the reader's language (English when the language or the key is missing)."""
    text = STORY.get(lang(), {}).get(key) or STORY["en"][key]
    return text.format(**kw) if kw else text


def ring(n, size="md"):
    """A numbered ring, for the landing page's chapters."""
    return f'<span class="cc-ring cc-ring-{size}" aria-label="{html.escape(s("step", n=n))}">{n}</span>'


# --- page furniture --------------------------------------------------------------------------------------------------
def header(title, sub=""):
    """Page title and one plain sentence under it.
    Returns the narrow right-hand column for a page action, such as the field report download."""
    left, right = st.columns([5, 1.4], vertical_alignment="bottom", gap="large")
    left.html(f'<header class="cc-head"><div><h1 class="cc-title">{title}</h1>{f"<p class=cc-sub>{sub}</p>" if sub else ""}</div></header>')
    return right


def kpis(items, lead=0):
    """A row of numbers read like a field record. Each item: (label, value, unit, note, tone, help).
    tone is "good", "bad" or None (colour says good or bad, never up or down). The first `lead` items are
    the headline numbers and print larger."""
    cells = []
    for i, (label, value, unit, note, tone, help_) in enumerate(items):
        q = (f'<details class="cc-help"><summary aria-label="{html.escape(s("help"))}">?</summary>'
             f'<p>{help_}</p></details>') if help_ else ""
        cells.append(f'<div class="cc-kpi{" lead" if i < lead else ""}{f" tone-{tone}" if tone else ""}">'
                     f'<div class="cc-kpi-l"><span>{label}</span>{q}</div>'
                     f'<p class="cc-kpi-v">{value}{f"<small>{unit}</small>" if unit else ""}</p>'
                     f'{f"<p class=cc-kpi-n>{note}</p>" if note else ""}</div>')
    st.html(f'<div class="cc-kpis" style="--n:{len(items)}">{"".join(cells)}</div>')


def legend(items):
    """Items: (colour, label, round) or (colour, label, round, outline). Round = a dot (points on a map);
    otherwise a swatch (areas). The outline colour draws a ring around the swatch, as on the map."""
    out = []
    for it in items:
        colour, label, round_ = it[:3]
        outline = f";box-shadow:0 0 0 2px {it[3]}" if len(it) > 3 else ""
        out.append(f'<span><i class="{"dot" if round_ else "sq"}" style="background:{colour}{outline}"></i>{label}</span>')
    st.html(f'<div class="cc-legend">{"".join(out)}</div>')


def source_line(unit, source, period):
    """Under every chart and map: what the numbers are, for which years, and where they come from."""
    st.html(f'<p class="cc-source">{unit}, {period}. {s("source", source=source)}</p>')


def footer():
    st.space("large")
    with st.container(key="footer"):
        st.markdown(f'<footer class="cc-foot">{_rings_mark()}<div><p>{s("footer.made")}</p>'
                    f'<p class="cc-quiet">{s("footer.data")}</p></div></footer>', unsafe_allow_html=True)
        st.page_link("views/sources.py", label=s("footer.know"))


def _rings_mark():
    return ('<svg class="cc-mark" viewBox="0 0 64 44" aria-hidden="true"><g fill="none" stroke="currentColor" '
            'stroke-width="1.6" stroke-dasharray="4 3"><circle cx="22" cy="22" r="18"/><circle cx="42" cy="22" r="18"/>'
            '</g><circle cx="22" cy="22" r="3.5" fill="currentColor"/><circle cx="42" cy="22" r="3.5" fill="currentColor"/></svg>')


# --- score marks (replace plain.dots / plain.ten / plain.level) -------------------------------------------------------
def dots(score):
    """A 0-5 score as five small discs, filled to the nearest half."""
    v = max(0.0, min(5.0, round(float(score) * 2) / 2))
    fills = "".join(f'<i style="--f:{max(0.0, min(1.0, v - k)) * 100:.0f}%"></i>' for k in range(5))
    return f'<span class="cc-dots" role="img" aria-label="{v:g} / 5">{fills}</span>'


def ten(n):
    """'n in 10': ten cells, n of them filled. Farmers count years, so most risks are written this way."""
    k = max(0, min(10, round(float(n))))
    return (f'<span class="cc-ten" role="img" aria-label="{k} / 10">'
            + "".join(f'<i class="{"on" if i < k else ""}"></i>' for i in range(10)) + "</span>")


def level(lvl):
    """high / medium / low as a coloured word: high is magenta (bad), low is green."""
    return f'<b class="cc-level {lvl} tone-{LEVEL_TONE.get(lvl, "mid")}">{t("plain.level." + lvl)}</b>'


# --- the landing page story ---------------------------------------------------------------------------------------------
def hero_map():
    """Strip fields with flight rings (assets/hero_map.svg) and the key to its colours and lines."""
    svg = (ASSETS / "hero_map.svg").read_text(encoding="utf-8")
    keys = [("sq", "var(--beet)", s("legend.beet")), ("sq", "var(--loess)", s("legend.nursery")),
            ("sq", "var(--hedge)", s("legend.switch")), ("ring", "", s("legend.ring"))]
    key = "".join(f'<li><i class="{k}" style="background:{c}"></i>{label}</li>' if k == "sq"
                  else f'<li><i class="ring"></i>{label}</li>' for k, c, label in keys)
    # st.markdown, not st.html: st.html strips inline SVG
    st.markdown(f'<figure class="cc-hero-fig">{svg}<figcaption><ul class="cc-key">{key}</ul></figcaption></figure>',
                unsafe_allow_html=True)


def cycle():
    """The planthopper's year as four steps along one line, ending at the neighbour's beet."""
    steps = "".join(f'<li><span class="cc-cycle-when">{s(f"cycle.{n}.when")}</span><p>{s(f"cycle.{n}.text")}</p></li>'
                    for n in range(1, 5))
    st.html(f'<section class="cc-cycle"><h2 class="cc-h2">{s("cycle.title")}</h2><ol>{steps}</ol>'
            f'<p class="cc-cycle-turn">{s("cycle.turn")}</p></section>')


# --- charts ---------------------------------------------------------------------------------------------------------------
def register_chart_theme():
    """Altair defaults in the same type and ink. Streamlit's own chart theme (theme="streamlit") takes its font and
    colours from .streamlit/config.toml, so both paths look the same."""
    import altair as alt

    ink, quiet, line = "#22302A", "#5E665C", "#E4E1D6"

    def theme():
        axis = {"labelColor": quiet, "titleColor": quiet, "labelFontSize": 13, "titleFontSize": 13,
                "titleFontWeight": 500, "gridColor": line, "domainColor": line, "tickColor": line}
        return {"config": {"font": "Archivo, sans-serif", "background": "transparent", "view": {"stroke": None},
                           "axis": axis, "legend": {"labelColor": ink, "labelFontSize": 13, "titleColor": quiet},
                           "title": {"color": ink, "fontSize": 16, "fontWeight": 650, "anchor": "start"},
                           "range": {"category": ["#2E6A4E", "#A8336A", "#D6A93C", "#22302A", "#8E9688", "#6B8FA3"]}}}

    try:
        alt.theme.register("cropcircles", enable=True)(theme)
    except AttributeError:  # Altair < 5.5
        alt.themes.register("cropcircles", theme)
        alt.themes.enable("cropcircles")
