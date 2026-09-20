# Humanize

A module of small functions that turn machine values into people-friendly
text — localized, dependency-free and usable in pure Python or as FT
components.

```python
from ronnie.contrib.humanize import (
    apnumber, intcomma, intword, naturalday, naturaltime, ordinal,
)
```

The locale comes from `HUMANIZE_LANGUAGE` (`"es"` by default, `"en"`
available); every function also accepts `language=` to override per call.

## The six helpers

| Function | Example (`es`) | Example (`en`) |
|---|---|---|
| `apnumber(value)` | `1 → "uno"`, `10 → "10"` | `1 → "one"` |
| `intcomma(value)` | `4500000 → "4.500.000"` | `4,500,000` |
| `intword(value)` | `1200000000 → "1,2 mil millones"` | `"1.2 billion"` |
| `ordinal(value)` | `3 → "3.º"` | `"3rd"` |
| `naturalday(date)` | hoy / mañana / ayer | today / tomorrow / yesterday |
| `naturaltime(dt)` | `"hace 4 minutos"`, `"dentro de 2 horas"` | `"4 minutes ago"`, `"in 2 hours"` |

Details worth knowing:

- `apnumber` only words the numbers 1–9; everything else passes through.
- `intcomma` formats floats with the locale decimal separator too
  (`1234.5 → "1.234,50"` in Spanish).
- `intword` scales up to `10¹²` ("billón"/"trillion"); beyond that the
  plain number is returned.
- `ordinal` leaves negative numbers unchanged.
- `naturaltime` measures in seconds → minutes → hours → days, then defers
  to `naturalday` for older values. Both accept an explicit `now=` for
  deterministic tests.

## In handlers

```python
from ronnie.common import Li
from ronnie.contrib.humanize import HumanTime, intcomma, ordinal  # HumanTime also in ronnie.common

@rt
def stats(req):
    return Ul(
        Li(f"{intcomma(view_count)} views"),
        Li(f"{ordinal(rank)} place"),
        Li("updated ", HumanTime(last_change)),   # <time> with ISO title
    )
```

`HumanTime(value)` renders `naturaltime` inside a `<time>` element whose
`title` attribute carries the ISO timestamp — hover for the exact moment.

## Choosing the language

```python
HUMANIZE_LANGUAGE = "es"          # project-wide (default)
naturaltime(dt, language="en")    # per call
```
