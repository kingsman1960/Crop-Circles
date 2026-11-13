"""The copilot: a language model that explains the page's own numbers and never computes new ones.

The page hands it a fact card (the sentences and figures it already shows, in the reader's language); the model answers
from that card only. Every number in an answer that is not on the card is listed under the answer as "check". Without
a key in .streamlit/secrets.toml the pages show the rule-based words alone (see .streamlit/secrets.example.toml).
Any OpenAI-compatible chat endpoint works: Qwen on DashScope, a local Ollama or vLLM, Claude's compatibility API.
"""
import html
import json
import re
import urllib.error
import urllib.request

import streamlit as st
from babel import Locale

from data import ASSETS, PRIORITY, content, fact_text, fields, model_note, rank_options, strategies, weights
from i18n import lang, num, t

SYSTEM = """You are the explainer inside Crop Circles, a decision-support tool for sugar-beet farms in the Kraichgau \
(Baden-Württemberg). A farmer or advisor asks about ONE field. Answer from the FACT CARD below and nothing else.
Rules: never invent or compute a number, a date, a price or a yield; quote figures exactly as the card gives them; \
when the card does not answer, say so in one sentence and name what would (the advisor, a soil sample, a look at the \
field). Plain words, short sentences, no headings or bullet lists, at most 120 words; a summary for the advisor may \
run to 300 words with the four risks, the best option and its trade-offs, each with its figure. The tool supports the \
decision, it does not make it. Answer in {language}."""
DEFAULT_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
_NUM = re.compile(r"(?<![\w.,])[-+]?(?:\d{1,3}(?:[ .,]\d{3})+|\d+)(?:[.,]\d+)?(?![\w])")


def config():
    """[copilot] base_url, api_key, model (and an optional [copilot.extra] table merged into the request), or None."""
    try:
        c = st.secrets.get("copilot", {})
    except Exception:  # no secrets file at all
        return None
    return c if c.get("api_key") else None


def _plain(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).replace("**", "").strip()


def card(fid, sections=()):
    """The fact card: what the pages show for this field, as plain text in the reader's language."""
    f, res = fields()[fid], strategies()["fields"][fid]
    crit, crops = content("strategies")["criteria"], content("crops")
    order, total, cards = rank_options(fid)
    w = weights()
    lines = [t("field.title", id=fid, place=f["label"].removeprefix("Near ")),
             f'{t("field.soil.slope")}: {num(f["slope_mean_pct"], 1)} %. {t("field.soil.silt")}: {num(f["silt_pct"])} %. '
             f'{t("field.soil.water")}: {num(f.get("nfk_mid_mm") or 140)} L/m². {t("field.soil.erosion")}: '
             f'{t("plain.level." + f["erosion_class"])}.', ""]
    for heading, paragraphs in sections:
        lines += [_plain(heading).upper(), *(_plain(p) for p in paragraphs), ""]
    lines += [t("grow.card.data").upper(), *(f"{text} ({source})" for text, source in (fact_text(k, v) for k, v in res["facts"].items())), ""]
    lines += [t("grow.priorities").split("\n")[0].upper()] + [f'{c["label"]}: {t("common.priority." + PRIORITY[w[k]])}' for k, c in crit.items()] + [""]
    lines.append(t("grow.option").upper())
    for rank, sid in enumerate(order, 1):
        s = cards[sid]
        seq = " → ".join(crops[c]["label"] for c in s["sequence"])
        lines.append(f'{rank}. {s["name"]} ({seq}): {num(total[sid], 1)} / 5. {_plain(s["why"])}')
        for k, c in crit.items():
            sc = res["strategies"][sid]["scores"][k]
            note = model_note(k, sc) if sc["basis"] == "model" else s["scores"][k]["note"]
            lines.append(f'   {c["label"]}: {num(sc["score"], 1)} / 5, {t("common.uncertainty." + sc["uncertainty"])}. {_plain(note)}')
    lines += ["", t("know.col.dataset").upper() + ": " + ", ".join(d["name"] for d in content("sources")["dataset"])]
    return "\n".join(lines)


def unverified(answer, card_text):
    """Numbers in the answer that are not on the card (years and figures); small counts up to 10 are let through."""
    # ponytail: a text check, not a semantic one – "22 days" on the card passes "22 %" in the answer; good enough to catch invented figures
    norm = lambda s: list(dict.fromkeys(re.sub(r"[ .,](?=\d{3}(?!\d))", "", n).replace(",", ".").lstrip("+") for n in _NUM.findall(s)))
    ok = set(norm(card_text))
    return [n for n in norm(answer) if n not in ok and not abs(float(n)) <= 10]


def ask(card_text, messages):
    """(answer, numbers to check) from the configured model, or (None, error text)."""
    c = config()
    body = {"model": c.get("model", "qwen-flash"), "temperature": 0.2,
            "messages": [{"role": "system", "content": SYSTEM.format(language=Locale.parse(lang().replace("-", "_")).get_display_name("en"))
                          + "\n\nFACT CARD\n" + card_text}, *messages]} | dict(c.get("extra", {}))
    req = urllib.request.Request(c.get("base_url", DEFAULT_URL).rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {c['api_key']}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            out = json.load(r)["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}"
    except (OSError, KeyError, ValueError, IndexError) as e:
        return None, str(e)
    return out, unverified(out, card_text)


def panel(fid, sections, key, presets):
    """Questions about this field under the page: preset questions as buttons, a chat box, answers with their checks."""
    with st.container(key=f"card_copilot_{key}"):
        st.subheader(t("copilot.title"))
        if not config():
            st.caption(t("copilot.off"))
            return
        st.caption(t("copilot.intro"))
        hist = st.session_state.setdefault(f"chat_{key}_{fid}_{lang()}", [])
        box = st.container()
        show = lambda m: (box.chat_message(m["role"], avatar=str(ASSETS / "symbol.png") if m["role"] == "assistant" else ":material/person:")
                          .markdown(m["content"] + (f'\n\n<span class="cc-note">{t("copilot.check", numbers=", ".join(m["flag"]))}</span>'
                                                    if m.get("flag") else ""), unsafe_allow_html=True))
        for m in hist:
            show(m)
        with st.container(horizontal=True, gap="small"):
            clicks = [st.button(t("copilot.q." + p), key=f"chat_{key}_{p}") for p in presets]
        q = st.chat_input(t("copilot.placeholder"), key=f"chat_in_{key}") or next((t("copilot.q." + p) for p, c in zip(presets, clicks) if c), None)
        if not q:
            return
        hist.append({"role": "user", "content": q})
        show(hist[-1])
        with box, st.spinner(t("copilot.thinking")):
            out, flag = ask(card(fid, sections), [{"role": m["role"], "content": m["content"]} for m in hist[-8:]])
        if out is None:
            hist.pop()
            box.warning(t("copilot.error", error=flag))
            return
        hist.append({"role": "assistant", "content": out, "flag": flag})
        show(hist[-1])


if __name__ == "__main__":  # self-check of the number guard and the card
    c = "Heat: 22 days a year (was 9). Rank 7 of 10. Water 4,231 L. Soil 1,5 %. 2015–2024."
    assert unverified("22 days, up from 9; 7 of 10 years; 4231 L; 1.5 %; since 2015.", c) == []
    assert unverified("About 35 days and 12.000 L in 2019.", c) == ["35", "12000", "2019"]
    assert "F1" in card("F1") and t("grow.option").upper() in card("F1")
    print("copilot.py ok")
