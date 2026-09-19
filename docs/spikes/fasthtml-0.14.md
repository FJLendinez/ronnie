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
