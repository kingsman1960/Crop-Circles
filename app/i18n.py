"""Internationalisation.

- Languages are BCP 47 tags ("en", "de", later "fr", "de-AT" …). English is the source and the fallback.
- UI text: one message catalog per language, app/locales/<tag>.toml, read as dotted keys ("field.title").
  Placeholders are named ("{n} of 10"); plural forms use CLDR categories ("x.one" / "x.other").
- Content (strategy cards, glossary …): content/<name>.toml in English, with content/<tag>/<name>.toml overlays that
  hold only the translated text (merged by key; arrays of tables by `id`).
- Numbers, percentages and month names come from Unicode CLDR via Babel, in the active locale.

Adding a language: copy app/locales/en.toml to <tag>.toml and translate it (plus content/<tag>/ if wanted). It shows up
in the language switch by itself; anything left out falls back to English.
"""
import tomllib
from pathlib import Path

import streamlit as st
from babel import Locale
from babel.dates import format_date, get_day_names, get_month_names
from babel.lists import format_list
from babel.numbers import format_decimal, format_percent

LOCALES = Path(__file__).parent / "locales"
DEFAULT = "en"


def available():
    return sorted(p.stem for p in LOCALES.glob("*.toml"))


def _flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        out.update(_flatten(v, f"{prefix}{k}.") if isinstance(v, dict) else {f"{prefix}{k}": v})
    return out


@st.cache_resource  # not cache_data: t() runs thousands of times per page, and cache_data would unpickle a copy each time
def catalog(tag):
    return _flatten(tomllib.loads((LOCALES / f"{tag}.toml").read_text(encoding="utf-8")))


def _match(tag, tags):
    """Best available tag for a requested one: exact, then its language ("de-AT" -> "de")."""
    tag = (tag or "").replace("_", "-")
    return tag if tag in tags else tag.split("-")[0].lower() if tag.split("-")[0].lower() in tags else None


def init():
    """Pick the language: the URL (?lang=de), else the browser's, else English."""
    tags = available()
    qp = _match(st.query_params.get("lang"), tags)
    if qp and qp != st.session_state.get("_lang_qp"):
        st.session_state.lang = qp
    if st.session_state.get("lang") not in tags:
        st.session_state.lang = _match(st.context.locale, tags) or DEFAULT


def lang():
    return st.session_state.get("lang", DEFAULT)


def picker(where):
    """The language switch; kept in the session and the URL."""
    where.segmented_control("Language / Sprache", available(), key="lang", required=True, persist_state="session",
                            format_func=lambda c: Locale.parse(c.replace("-", "_")).get_display_name(c.replace("-", "_")).capitalize(),
                            label_visibility="collapsed")
    st.query_params["lang"] = st.session_state._lang_qp = lang()


def t(key, **params):
    """Translated text for a key, with named placeholders filled; falls back to English, then to the key."""
    text = catalog(lang()).get(key) or catalog(DEFAULT).get(key, key)
    return text.format(**params) if params else text


def tn(key, n, **params):
    """Plural-aware text: picks key.one / key.other by the CLDR plural rule of the language."""
    form = Locale.parse(lang().replace("-", "_")).plural_form(n)
    k = f"{key}.{form}" if f"{key}.{form}" in catalog(lang()) | catalog(DEFAULT) else f"{key}.other"
    return t(k, n=num(n), **params)


def num(x, digits=0):
    """A number in the reader's format (4,231.5 / 4.231,5); small values keep `digits` decimals."""
    return format_decimal(x, format="#,##0" + ("." + "0" * digits if digits else ""), locale=lang().replace("-", "_"))


def pct(x, digits=0):
    """A share in the reader's format: 23% / 23 % (the locale's own pattern, so German gets its space)."""
    loc = Locale.parse(lang().replace("-", "_"))
    pattern = loc.percent_formats[None].pattern.replace("#,##0", "#,##0" + ("." + "0" * digits if digits else ""), 1)
    return format_percent(x, format=pattern, locale=loc)


def listing(items):
    """A list in words: 2003, 2015 and 2018 / 2003, 2015 und 2018."""
    return format_list(list(items), locale=lang().replace("-", "_"))


def day(d):
    """A date in words: 1 November 2026 / 1. November 2026."""
    return format_date(d, "long", locale=lang().replace("-", "_"))


def months(width="abbreviated"):
    names = get_month_names(width, locale=lang().replace("-", "_"))
    return [names[i] for i in range(1, 13)]


def chart_locale():
    """Vega number and time locale, so chart axes use the reader's separators and month names."""
    loc = Locale.parse(lang().replace("-", "_"))
    sym = loc.number_symbols.get("latn", loc.number_symbols)
    days = get_day_names("wide", locale=loc)
    short_days = get_day_names("abbreviated", locale=loc)
    order = [6, 0, 1, 2, 3, 4, 5]  # d3 starts the week on Sunday
    return {"number": {"decimal": sym["decimal"], "thousands": sym["group"], "grouping": [3], "currency": ["", " €"]},
            "time": {"dateTime": "%x, %X", "date": "%d.%m.%Y", "time": "%H:%M:%S", "periods": ["AM", "PM"],
                     "days": [days[i] for i in order], "shortDays": [short_days[i] for i in order],
                     "months": months("wide"), "shortMonths": months("abbreviated")}}


if __name__ == "__main__":  # self-check of the pure helpers
    assert _match("de-AT", ["de", "en"]) == "de" and _match("fr", ["de", "en"]) is None
    assert _flatten({"a": {"b": "x"}, "c": "y"}) == {"a.b": "x", "c": "y"}
    print("i18n.py ok")
