"""contrib.humanize: human-friendly values (Django's 6 filters, es/en locales).

Pure functions plus an FT ``HumanTime`` helper. ``HUMANIZE_LANGUAGE`` picks
the locale (default ``"es"``); every function also accepts ``language=``.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

__all__ = [
    "HumanTime",
    "apnumber",
    "intcomma",
    "intword",
    "naturalday",
    "naturaltime",
    "ordinal",
]

_WORDS = {
    "en": ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"],
    "es": ["uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"],
}

# (power of 10, singular, plural)
_BIG_WORDS = {
    "en": [
        (12, "trillion", "trillions"),
        (9, "billion", "billions"),
        (6, "million", "millions"),
        (3, "thousand", "thousands"),
    ],
    "es": [
        (12, "billón", "billones"),
        (9, "mil millones", "mil millones"),
        (6, "millón", "millones"),
        (3, "mil", "mil"),
    ],
}


def _language(language: str | None) -> str:
    if language:
        return language
    from ..conf import settings

    return str(getattr(settings._wrapped, "HUMANIZE_LANGUAGE", None) or "es")


def apnumber(value: float, language: str | None = None) -> str:
    """1-9 as AP-style words; other numbers unchanged."""
    words = _WORDS[_language(language)]
    return words[int(value) - 1] if 1 <= value <= 9 and value == int(value) else str(value)


def intcomma(value: float | int | str, language: str | None = None) -> str:
    """4500000 → '4.500.000' (es) / '4,500,000' (en)."""
    lang = _language(language)
    thousands = "," if lang == "en" else "."
    decimal_point = "." if lang == "en" else ","
    if isinstance(value, int):
        return f"{value:,}".replace(",", thousands)
    text = f"{float(value):,.2f}"
    whole, _, frac = text.partition(".")
    return f"{whole.replace(',', thousands)}{decimal_point}{frac}"


def intword(value: float, language: str | None = None) -> str:
    """1200000000 → '1,2 mil millones' (es) / '1.2 billion' (en)."""
    lang = _language(language)
    decimal_point = "." if lang == "en" else ","
    for power, singular, plural in _BIG_WORDS[lang]:
        if abs(value) >= 10**power:
            amount = value / 10**power
            whole = int(abs(amount))
            if lang == "en":
                unit = singular if whole == 1 else plural  # "1.2 billion"
            else:
                unit = singular if abs(amount) == 1 else plural  # "1,2 millones"
            quantity = f"{amount:.1f}".replace(".", decimal_point)
            return f"{quantity} {unit}"
    return str(value)


_SUFFIXES_EN = {1: "st", 2: "nd", 3: "rd"}


def ordinal(value: int, language: str | None = None) -> str:
    """1 → '1.º' (es) / '1st' (en). Negative values are left unchanged."""
    if value < 0:
        return str(value)
    if _language(language) == "es":
        return f"{value}.º"
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = _SUFFIXES_EN.get(value % 10, "th")
    return f"{value}{suffix}"


def naturalday(value: dt.date | dt.datetime, language: str | None = None) -> str:
    """Today/tomorrow/yesterday (localized), else an ISO-ish date."""
    lang = _language(language)
    if not isinstance(value, dt.datetime):
        value = dt.datetime(value.year, value.month, value.day)
    today = dt.datetime.now().date()
    day = value.date()
    if day == today:
        return "hoy" if lang == "es" else "today"
    if day == today + dt.timedelta(days=1):
        return "mañana" if lang == "es" else "tomorrow"
    if day == today - dt.timedelta(days=1):
        return "ayer" if lang == "es" else "yesterday"
    return day.strftime("%d %b %Y")


def naturaltime(
    value: dt.datetime | dt.timedelta, language: str | None = None, now: dt.datetime | None = None
) -> str:
    """'hace 4 minutos' / 'dentro de 2 horas' / '4 minutes ago'."""
    lang = _language(language)
    now = now or dt.datetime.now()
    delta = value if isinstance(value, dt.timedelta) else value - now
    seconds = delta.total_seconds()
    past = seconds < 0
    seconds = abs(seconds)

    def phrase(unit_es: str, unit_en: str, count: int | float) -> str:
        if lang == "es":
            unit = unit_es
            if count == 1 and unit_es.endswith(("a", "e", "o")):
                unit = unit_es[:-1] if unit_es.endswith("s") else unit_es
            else:
                unit = unit_es if count == 1 else unit_es + "s"
            return f"hace {count} {unit}" if past else f"en {count} {unit}"
        unit = unit_en if count == 1 else unit_en + "s"
        return f"{count} {unit} ago" if past else f"in {count} {unit}"

    if seconds < 10:
        return "ahora mismo" if lang == "es" else "now"
    if seconds < 60:
        count = int(seconds)
        return phrase("segundo", "second", count)
    if seconds < 3600:
        count = int(seconds // 60)
        return phrase("minuto", "minute", count)
    if seconds < 86400:
        count = int(seconds // 3600)
        return phrase("hora", "hour", count)
    days = seconds // 86400
    if days < 31:
        return phrase("día", "day", int(days))
    value_dt = (now - delta) if isinstance(value, dt.timedelta) else value
    return naturalday(value_dt, language=lang)


def HumanTime(value: dt.datetime | dt.timedelta, language: str | None = None) -> Any:
    """FT ``<time>`` element with a natural rendering and ISO title."""
    from ..common import Time

    iso = value.isoformat() if isinstance(value, dt.datetime) else ""
    return (
        Time(naturaltime(value, language=language), title=iso)
        if iso
        else Time(naturaltime(value, language=language))
    )
