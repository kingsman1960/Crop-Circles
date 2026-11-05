"""i18n check: every literal key used in the app exists in en.toml, and every catalog has the same placeholders as en.
Run from the repo root: python app/check_i18n.py  (prints keys a translation still misses; English fills those in)."""
import re
import string
import sys
import tomllib
from pathlib import Path

APP = Path(__file__).parent
sys.path.insert(0, str(APP))
from i18n import _flatten  # noqa: E402

cats = {p.stem: _flatten(tomllib.loads(p.read_text(encoding="utf-8"))) for p in (APP / "locales").glob("*.toml")}
en = cats["en"]
used = {m for f in APP.rglob("*.py") for m in re.findall(r"""\bt[n]?\(\s*["']([a-z_.0-9]+)["']""", f.read_text(encoding="utf-8"))}
missing = sorted(k for k in used if k not in en and not any(k2.startswith(k if k.endswith(".") else k + ".") for k2 in en))
fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}
problems = [f"{tag}:{k} placeholders {fields(v)} != {fields(en[k])}"
            for tag, cat in cats.items() for k, v in cat.items() if k in en and fields(v) != fields(en[k])]
extra = [f"{tag}:{k}" for tag, cat in cats.items() for k in cat if k not in en]
for tag, cat in cats.items():
    print(f"{tag}: {len(cat)}/{len(en)} keys" + ("" if tag == "en" else f", {len(set(en) - set(cat))} fall back to English"))
assert not missing, f"keys used in code but missing in en.toml: {missing}"
assert not problems, "\n".join(problems)
assert not extra, f"keys not in en.toml: {extra}"
print("i18n ok")
