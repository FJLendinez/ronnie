# Spike: puntos de integración FastHTML 0.14.13 (riesgo R1)

Verificado el 2026-09-19 contra `python-fasthtml==0.14.13` (Python 3.14).

## Integración elegida

1. **Crear la app**: `FastHTML(**kwargs)` directamente (no `fast_app()`): da
   control total sobre `middleware`, `routes`, `exception_handlers`, `before`
   y mantiene HTMX/Pico defaults (`default_hdrs=True`).
2. **Montar rutas**: `APIRouter(prefix="blog")` guarda tuplas
   `(func, path, methods, name, include_in_schema, body_wrap)`; se montan con
   `router.to_app(app)` → `app._add_route(*args)`. `app._add_route` es el único
   punto de acoplamiento privado → todo pasa por `ronnie.core.routing`.
3. **Sesiones pluggables**: `FastHTML(sess_cls=...)` construye
   `Middleware(sess_cls, secret_key=..., session_cookie=..., max_age=..., path=...,
   same_site=..., https_only=..., domain=...)`. El middleware de sesiones de
   Ronnie debe aceptar esos kwargs (lee el resto de settings por su cuenta).
   `sess_cls=None` desactiva sesiones.
4. **Exception handlers**: dict `{404: fn, 500: fn, Exception: fn}`; FastHTML
   los envuelve para renderizar con headers/footers de la app.
5. **Middlewares**: lista de `starlette.middleware.Middleware` en
   `FastHTML(middleware=[...])`; se añade siempre el de sesión al final (orden
   interno de FastHTML).
6. **`Redirect`** existe en `fasthtml.common` (HTMX-aware, usa `HX-Redirect`).

## Restricciones conocidas

- `APIRouter` no soporta handlers llamados `get/post/...` accesibles vía
  `router.<name>` (RouteFuncs los excluye). Documentar: nombres semánticos.
- `app._add_route` es privado: cubrir con contract tests que fallen ruidoso
  al subir de versión de FastHTML.


## Derivation contract (mirror architecture)

Ronnie mirrors the FT package module by module; user code imports only from
`ronnie.*`:

- **`ronnie.<name>` mirrors** (one per submodule: `components`, `svg`,
  `pico`, `xtend`, `oauth`, `jupyter`, `live_reload`, `toaster`, `js`, `ft`,
  `cli`, `basics`, `authmw`, `fastapp`, `starlette`, optional
  `stripe_otp`): copy every public attribute of `fasthtml.<name>` into the
  mirror (its `__all__` order first, then the remaining public namespace)
  **and** define a PEP 562 `__getattr__` falling back to the source — the
  source itself resolves some names lazily (e.g. `Titled` via
  `fasthtml.components.__getattr__`), which `dir()` never shows.
- **`ronnie.core`** merges the `fasthtml.core` derivation with Ronnie's own
  submodules (`management`, `routing`, `checks`, `signing`, `passwords`,
  `asgi`, `signals`) — no name collisions.
- **`ronnie.common`** is curated, composed from Ronnie's own mirrors in the
  source's composition order (starlette, fastcore.utils/xml, basics, authmw,
  live_reload, toaster, js, fastapp) + `dataclass` parity, NOT a dump of the
  whole package: `Card` lives in `ronnie.pico`, `Circle` in `ronnie.svg`.
- Ronnie's `Router` shadows the ASGI `Router` the curated surface
  re-exports (bottom import). Ronnie additions (`CsrfToken`, `csrf_exempt`,
  `Alerts`, `HumanTime`) resolve lazily via PEP 562.
- Contract tests (`tests/test_common.py`) pin: per-mirror parity for every
  importable submodule (dir-level + lazy names), curated-common parity with
  `fasthtml.common`, curated scope (no mirror-only names in common),
  no contrib imports at load time, and e2e handlers using only Ronnie
  imports (including SVG routes and Pico pages).
