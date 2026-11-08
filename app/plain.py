"""Numbers into words a farmer reads at a glance – in the reader's language (keys under "plain." in app/locales)."""
from i18n import num, t

FRACTIONS = [(0.1, "tenth"), (0.2, "fifth"), (0.25, "quarter"), (1 / 3, "third"), (0.4, "two_fifths"), (0.5, "half"),
             (2 / 3, "two_thirds"), (0.75, "three_quarters"), (0.9, "nine_tenths")]


def level(name):
    return f'<span class="cc-level {name}">{t("plain.level." + name)}</span>'


def of_ten(share):
    return t("plain.of_ten", n=round(share * 10))


def fraction(x):
    """0.32 -> 'about a third'."""
    if x < 0.05:
        return t("plain.fraction.none")
    return t("plain.fraction." + min(FRACTIONS, key=lambda f: abs(f[0] - x))[1])


def weeks(days):
    return t("plain.weeks", n=num(days / 7)) if days >= 10 else t("plain.days", n=num(days))


def dots(score):
    """A 1-5 score as five dots."""
    n = int(round(score))
    return (f'<span class="cc-dots" role="img" aria-label="{t("plain.dots", n=n)}" title="{num(score, 1)} / 5">'
            + '<i class="on"></i>' * n + "<i></i>" * (5 - n) + "</span>")


def ten(n):
    """'7 of the last 10 years' as ten dots, next to the level."""
    n = int(round(n))
    return (f'<span class="cc-dots" role="img" aria-label="{of_ten(n / 10)}" title="{of_ten(n / 10)}">'
            + '<i class="on"></i>' * n + "<i></i>" * (10 - n) + "</span>")


def compare(diff):
    """A change of score against today's rotation, in words, with a good/bad tone."""
    size = abs(diff)
    if size < 0.3:
        return t("plain.compare.same"), ""
    step = "little" if size < 0.8 else "clear" if size < 1.5 else "much"
    good = diff > 0
    return t(f"plain.compare.{step}_{'better' if good else 'worse'}"), "good" if good else "bad"
