# Ronnie — Plan de construcción

> **Ronnie** es una capa sobre FastHTML que trae los beneficios de Django a aplicaciones FastHTML a gran escala: settings, aplicaciones, commands, seguridad built-in, contrib packages (admin, auth, humanize, messages, redirects, sessions), cache framework, test framework y tasks framework — sin renunciar a nada de lo que hace FastHTML genial (FT components, HTMX, MiniDataAPI, firma basada en tipos).

*Documento de planificación · Septiembre 2026 · Basado en Django 6.1 (docs.djangoproject.com) y python-fasthtml 0.14.x*

---

## Índice

1. [Visión y principios](#1-visión-y-principios)
2. [Decisiones de diseño (bloqueadas)](#2-decisiones-de-diseño-bloqueadas)
3. [Arquitectura general](#3-arquitectura-general)
4. [Estructura del repositorio](#4-estructura-del-repositorio)
5. [API pública objetivo (por subsistema)](#5-api-pública-objetivo-por-subsistema)
6. [Tabla de equivalencias Django ↔ Ronnie](#6-tabla-de-equivalencias-django--ronnie)
7. [Referencia de settings](#7-referencia-de-settings)
8. [Fases de construcción paso a paso](#8-fases-de-construcción-paso-a-paso)
9. [Estrategia de calidad: testing del framework, CI y tooling](#9-estrategia-de-calidad-testing-del-framework-ci-y-tooling)
10. [Versionado, publicación y documentación](#10-versionado-publicación-y-documentación)
11. [Riesgos y mitigaciones](#11-riesgos-y-mitigaciones)
12. [Hoja de ruta a 1.0](#12-hoja-de-ruta-a-10)

---

## 1. Visión y principios

**Problema.** FastHTML es excepcional para apps pequeñas y medianas, pero no ofrece convenciones para proyectos grandes: no hay settings estructurados, registro de aplicaciones, commands, capa de seguridad, ni frameworks de cache/test/tasks. Django resuelve todo esto con 20 años de diseño maduro.

**Solución.** Ronnie copia *los patrones de diseño* de Django (no su implementación) y los implementa de forma idiomática sobre FastHTML + Starlette, con Python moderno.

**Principios rectores:**

1. **Composición, no fork.** Ronnie nunca parchea FastHTML: lo importa y lo configura. Si FastHTML cambia, la integración vive en un adaptador delgado (`ronnie.core`).
2. **El contrato es la firma.** Los handlers siguen siendo funciones planas con anotaciones; Ronnie nunca añade decoradores que oculten firmas (regla de oro de FastHTML).
3. **Convención sobre configuración, con escape.** Defaults sensibles para empezar en 5 minutos (`ronnie startproject`), settings con el mismo estilo que Django para escalar.
4. **Baterías incluidas, extraíbles.** Cada contrib package es opcional y desactivable desde `INSTALLED_APPS`/`MIDDLEWARE`.
5. **Zero-config en dev, seguro en prod.** En desarrollo todo funciona sin configurar; `ronnie check --deploy` avisa de todo lo que falta para producción.
6. **Python moderno.** Type hints en todo el código público, `typing.Protocol` para los contratos de backends, dataclasses para datos, `py.typed` desde el día 1.
7. **HTML-first.** No hay motor de plantillas: la UI del propio admin/messages se construye con FT components + HTMX + Pico CSS.

---

## 2. Decisiones de diseño (bloqueadas)

| # | Decisión | Justificación |
|---|----------|---------------|
| D1 | **Distribución PyPI: `python-ronnie`**, import `ronnie`, CLI `ronnie` | El nombre `ronnie` está **ocupado en PyPI** (paquete de deep-learning abandonado desde 2018; los nombres PyPI son únicos). Mismo patrón que `python-fasthtml` → `import fasthtml`. Alternativa: `ronnie-framework`. |
| D2 | **Python ≥ 3.10**, impuesto por FastHTML 0.14.x | Testeado en 3.10–3.14. |
| D3 | **Dependencias core: solo `python-fasthtml`** (trae starlette, uvicorn, itsdangerous, fastcore, fastlite…) | Redis (`redis-py`), argon2 (`argon2-cffi`) y postgres (`fastsql`) son extras opcionales: `ronnie[redis]`, `ronnie[argon2]`, `ronnie[postgres]`. |
| D4 | **Sin ORM.** Base de datos = **MiniDataAPI** (fastlite/fastsql) | Django ORM está fuera de alcance. Ronnie define `DATABASES` → factory de conexión y convenciones de `models.py` (dataclasses + `db.create(Table, transform=True)`). |
| D5 | **`MIDDLEWARE` = lista de strings estilo Django** que se resuelve a middlewares Starlette | Permite override desde settings como en Django; Ronnie expone un protocolo propio simple (`async __call__(request, call_next)`) y middlewares ASGI puros para rendimiento. |
| D6 | **Sesiones pluggables manteniendo `sess`/`session` como parámetro especial de handler** | El middleware de sesiones de Ronnie escribe en `scope["session"]` igual que el de Starlette, así todo handler FastHTML existente funciona sin cambios. |
| D7 | **pytest como runner de tests** (`ronnie test` ejecuta pytest debajo) | Mejor práctica actual frente al unittest-runner de Django; `RonnieTestCase` se mantiene para quien venga de `unittest`. |
| D8 | **Interfaz de cache calcada a Django** (`caches["alias"]`, `BaseCache`, `CACHES`) | Es la API más madura y conocida; facilita migrar mentalidad (y código) desde Django. |
| D9 | **Tasks = colas de mensajes con brokers pluggables** (inline/thread/redis), workers con `multiprocessing` | Cobra/Celery/RQ no son dependencias: Ronnie define el protocolo e implementa brokers livianos; redis es el backend serio vía extra. |
| D10 | **Templates NO: todo FT.** Admin, auth views y messages se renderizan con funciones FT + HTMX | Coherente con el punto 7 de los principios; cero Jinja2. |
| D11 | **Licencia MIT o Apache-2.0** (decidir en Fase 0; recomendado Apache-2.0 por compatibilidad con fasthtml) | — |
| D12 | **Compat con `manage.py`**: los proyectos generados incluyen `manage.py` que delega en `ronnie.core.management.execute_from_command_line` | Ergonomía idéntica a Django; también funciona `ronnie <comando>` directo. |

---

## 3. Arquitectura general

### 3.1 Capas

```
┌──────────────────────────────────────────────────────────────┐
│  TU PROYECTO                                                 │
│  manage.py · config/settings.py · apps/<app>/{routes,models} │
├──────────────────────────────────────────────────────────────┤
│  RONNIE                                                      │
│  ┌────────────┐ ┌──────────┐ ┌─────────┐ ┌─────────────────┐ │
│  │ core       │ │ contrib  │ │ cache   │ │ tasks           │ │
│  │ settings   │ │ admin    │ │ locmem  │ │ registry        │ │
│  │ apps       │ │ auth     │ │ filebased│ │ brokers         │ │
│  │ commands   │ │ sessions │ │ redis   │ │ worker / beat   │ │
│  │ checks     │ │ messages │ │ dummy   │ │ results         │ │
│  │ middleware │ │ humanize │ └─────────┘ └─────────────────┘ │
│  │ routing    │ │ redirects│ ┌─────────────────────────────┐ │
│  │ db · signing│ └──────────┘ │ testing (client, override, │ │
│  └────────────┘               │ assert, pytest plugin)     │ │
│                               └─────────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│  FASTHTML (fast_app, FT components, HTMX) sobre STARLETTE    │
├──────────────────────────────────────────────────────────────┤
│  uvicorn · MiniDataAPI: fastlite (sqlite) / fastsql (pg)     │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Flujo de arranque (copiado de Django, adaptado)

```
manage.py / asgi.py
  └─ os.environ.setdefault("RONNIE_SETTINGS_MODULE", "config.settings")
  └─ ronnie.setup()                        # equivalente a django.setup()
       ├─ 1. settings.configure() implícito: LazySettings envuelve el módulo
       │     (defaults de global_settings.py ← pisados por tu settings.py)
       ├─ 2. apps.populate(INSTALLED_APPS) # 3 fases, en orden:
       │     a) importar cada app → crear AppConfig (sin tocar modelos)
       │     b) importar cada <app>.models (registra tablas MiniDataAPI)
       │     c) ejecutar todos los AppConfig.ready()  (señales, registros)
       └─ 3. checks.run()                  # system checks (W00x/E00x)
  └─ get_asgi_application()                # crea la app FastHTML
       ├─ fast_app(...) con middlewares resueltos desde MIDDLEWARE
       ├─ autodiscovery de rutas: <app>.routes / <app>.views → include
       ├─ exception handlers (404/500 como FT components)
       ├─ mount de /static y de admin (si está instalado)
       └─ lifespan: arranque de tasks broker, cierre graceful
```

### 3.3 Pipeline de una petición

```
Request → uvicorn → Starlette
  → [Ronnie SecurityMiddleware]      headers: HSTS, nosniff, Referrer-Policy, COOP…
  → [HostValidationMiddleware]       ALLOWED_HOSTS
  → [SessionMiddleware (engine X)]   scope["session"] (compatible con `sess`)
  → [CsrfMiddleware]                 POST/PUT/PATCH/DELETE con token
  → [MessagesMiddleware]             voltea storage → request
  → [AuthBeforeware]                 scope["auth"] = request.user (compatible `auth`)
  → CacheMiddleware (per-site, opcional)
  → Router (rutas de las apps, prefijadas por app)
  → handler FastHTML (función con firma tipada) → FT | Redirect | Response
  ← response: se guardan sesión/mensajes, se parchean headers/cache-control
```

---

## 4. Estructura del repositorio

```
ronnie/                              # repo (git init en Fase 0)
├── pyproject.toml                  # hatchling + extras [redis,argon2,postgres,dev]
├── uv.lock                         # uv como gestor
├── README.md · CHANGELOG.md · LICENSE
├── .github/workflows/ci.yml
├── src/
│   └── ronnie/
│       ├── __init__.py             # __version__, setup(), export de settings/apps
│       ├── py.typed
│       ├── global_settings.py      # defaults de todos los settings (estilo Django)
│       ├── conf.py                 # LazySettings, SettingsReference, settings
│       ├── apps.py                 # AppConfig, Apps (registro), populate()
│       ├── core/
│       │   ├── asgi.py             # get_asgi_application()
│       │   ├── routing.py          # Router, include_router, autodiscovery
│       │   ├── exceptions.py       # ImproperlyConfigured, CommandError, PermissionDenied…
│       │   ├── signals.py          # Signal minimal (observer)
│       │   ├── checks/             # registry de checks + checks built-in
│       │   ├── signing/            # Signer, TimestampSigner, dumps/loads
│       │   ├── management/
│       │   │   ├── __init__.py     # BaseCommand, call_command, find_commands, estilos
│       │   │   └── commands/       # startproject, startapp, runserver, shell, check,
│       │   │                       # migrate, test, diffsettings, version, worker, beat…
│       │   └── templates/          # plantillas de código para startproject/startapp
│       ├── middleware/             # security, host, csrf, clickjacking, session-mount
│       ├── db.py                   # DATABASES → conexión MiniDataAPI, convención models
│       ├── cache/
│       │   ├── __init__.py         # caches, cache (default), InvalidCacheBackendError
│       │   ├── base.py             # BaseCache (protocolo + implementación base)
│       │   └── backends/           # locmem, filebased, redis, dummy
│       ├── tasks/
│       │   ├── __init__.py         # @task, registry, current_app
│       │   ├── brokers/            # base (Protocol), inline, thread, redis
│       │   ├── results.py          # estados: PENDING/STARTED/SUCCESS/FAILED/RETRY
│       │   ├── worker.py           # pool multiproceso, graceful shutdown, reintentos
│       │   └── beat.py             # scheduler cron/interval desde settings
│       ├── testing/
│       │   ├── client.py           # RonnieTestClient (httpx/TestClient + sesiones)
│       │   ├── testcase.py         # RonnieTestCase, SimpleTestCase
│       │   ├── utils.py            # override_settings, modify_settings, isolate_apps
│       │   ├── assertions.py       # assertRedirects, assertContains, assertMessages…
│       │   └── pytest_plugin.py    # fixtures: client, db, settings_override
│       └── contrib/
│           ├── auth/               # models, hashers, validators, backends, views,
│           │                       # decorators, middleware, management(createsuperuser…)
│           ├── sessions/           # engines/{signed_cookie,db,cache}, middleware,
│           │                       # models, management(clearsessions)
│           ├── messages/           # api, storage/{session,cookie,fallback}, components(Alerts)
│           ├── admin/              # site, ModelAdmin, views (list/add/change/delete),
│           │                       # components (tabla, filtros, formularios introspectados)
│           ├── humanize/           # apnumber, intcomma, intword, naturalday,
│           │                       # naturaltime, ordinal · locales es/en
│           └── redirects/          # models (tabla redirects), middleware fallback 404
├── tests/                          # unit + integration + contract tests del framework
├── docs/                           # mkdocs-material: tutorial, topics (espejo de Django), ref
└── examples/
    └── blog/                       # app ejemplo completa ("el polls de Ronnie")
```

### Proyecto generado por `ronnie startproject mysite`

```
mysite/
├── manage.py                       # shim → execute_from_command_line
├── config/
│   ├── __init__.py
│   ├── settings.py                 # genera SECRET_KEY, DEBUG, INSTALLED_APPS, DB…
│   └── asgi.py                     # application = get_asgi_application()
└── apps/
    └── blog/                       # creado por `ronnie startapp blog`
        ├── __init__.py
        ├── apps.py                 # class BlogConfig(AppConfig): label = "blog"
        ├── routes.py               # rt = Router("blog"); handlers
        ├── models.py               # dataclasses + TABLES = [...] (convenio)
        ├── services.py             # lógica de negocio (sin imports de fasthtml)
        ├── admin.py                # registro en admin (opcional)
        ├── tests/test_routes.py
        └── management/commands/    # vacío, listo para tus comandos
```

---

## 5. API pública objetivo (por subsistema)

> Bloquear estas firmas antes de implementar (son el "contrato" del framework). Los snippets muestran la experiencia de usuario final.

### 5.1 Settings y arranque

```python
# config/settings.py — módulo Python plano, MAYÚSCULAS, con lógica si hace falta
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = True
SECRET_KEY = "django-incompatible-…cambiame"      # startproject genera una real
INSTALLED_APPS = [
    "ronnie.contrib.sessions",
    "ronnie.contrib.messages",
    "ronnie.contrib.auth",
    "ronnie.contrib.admin",
    "apps.blog",
]
ALLOWED_HOSTS = []
DATABASES = {"default": {"ENGINE": "sqlite", "NAME": BASE_DIR / "db.sqlite3"}}

# desde cualquier parte del código:
from ronnie.conf import settings
if settings.DEBUG: ...
```

```python
# cualquier consumidor standalone (tests, scripts):
import ronnie
ronnie.setup(settings_module="config.settings")   # o RONNIE_SETTINGS_MODULE en env
```

### 5.2 Apps

```python
# apps/blog/apps.py
from ronnie.apps import AppConfig

class BlogConfig(AppConfig):
    label = "blog"                     # default: último componente de name
    verbose_name = "Blog"

    def ready(self):                   # idempotente; sin BD; importar modelos aquí
        from . import signals          # conectar señales, registrar tareas, etc.
```

```python
# apps/blog/routes.py — handlers FastHTML 100% normales
from ronnie.core.routing import Router
from .models import Post
from . import services

rt = Router("blog")                    # prefijo /blog

@rt
def index():
    return Ul(*[Li(p.title) for p in services.published_posts()])

@rt
def save(post: PostForm):              # dataclass tipado → binding de FastHTML
    services.create_post(post)
    from fasthtml.common import Redirect
    return Redirect(index)
```

### 5.3 Commands

```python
# apps/blog/management/commands/publish_scheduled.py
from ronnie.core.management import BaseCommand

class Command(BaseCommand):
    help = "Publica los posts programados cuya fecha ya pasó"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        n = services.publish_scheduled(dry_run=options["dry_run"])
        self.stdout.write(self.style.SUCCESS(f"{n} posts publicados"))

# uso:  python manage.py publish_scheduled --dry-run
# test: call_command("publish_scheduled", dry_run=True, stdout=StringIO())
```

### 5.4 Seguridad

```python
from ronnie.core.signing import TimestampSigner       # para tokens de reset, etc.
s = TimestampSigner(salt="password-reset")
token = s.sign_object({"uid": 42})

from ronnie.contrib.auth import make_password, validate_password
hashed = make_password("secreto")          # pbkdf2_sha256$1_000_000$salt$hash
validate_password("1234")                   # lanza ValidationError (validadores)
```

### 5.5 Sessions (motor cookie firmado por defecto; db/cache como extras)

```python
@rt
def contador(sess):          # `sess` sigue siendo el dict especial de FastHTML
    sess["n"] = sess.get("n", 0) + 1
    return P(f"visitas: {sess['n']}")
```

### 5.6 Messages

```python
from ronnie.contrib.messages import messages, Alerts

@rt
def save(req, post: PostForm):
    services.create_post(post)
    messages.success(req, "Post creado")
    from fasthtml.common import Redirect
    return Redirect(index)

def base_layout(req, *children):
    return Titled("Blog", Alerts(req), Main(*children))   # render de flashes
```

### 5.7 Cache

```python
from ronnie.cache import cache, caches

cache.set("sidebar:hits", 42, timeout=300)
hits = cache.get("sidebar:hits", 0)
cache.get_or_set("lock:export", "owner-1", timeout=60)
local = caches["local"]                       # alias de CACHES

from ronnie.cache import cache_page, cache_fragment

@cache_page(60)
@rt
def home(): ...

def sidebar(user):
    return cache_fragment(f"sidebar:{user.id}", 300, lambda: render_sidebar(user))
```

### 5.8 Admin

```python
# apps/blog/admin.py
from ronnie.contrib.admin import site, ModelAdmin, register
from .models import Post

@register(Post)
class PostAdmin(ModelAdmin):
    list_display = ("title", "author", "published_at", "is_published")
    list_filter = ("is_published", "author")
    search_fields = ("title", "summary")
    ordering = ("-published_at",)
    list_per_page = 25

# disponible en /admin/ · login con usuario staff · CRUD completo con HTMX
```

### 5.9 Testing

```python
from ronnie.testing import RonnieTestCase, override_settings

class BlogTests(RonnieTestCase):
    def test_create_post(self):
        self.client.login(username="fj", password="secreto")
        resp = self.client.post(save.to(), data={"title": "Hola", "body": "…"})
        self.assertRedirects(resp, index)
        self.assertMessages(resp, [("success", "Post creado")])

@override_settings(DEBUG=True)
def test_algo(client):        # fixture pytest
    assert client.get(index).status_code == 200
```

### 5.10 Tasks

```python
# apps/blog/tasks.py
from ronnie.tasks import task

@task(bind=True, max_retries=5, retry_backoff=True)
def rebuild_search_index(self, post_id: int):
    ...                                        # reintentos con backoff exponencial

# en un handler o servicio:
rebuild_search_index.delay(post_id=post.pk)    # enqueue
result = rebuild_search_index.apply_async(post_id=post.pk, countdown=60)
result.status   # PENDING | STARTED | SUCCESS | FAILED | RETRY

# CLI:  ronnie worker --queues default,search --concurrency 4
#       ronnie beat            # TASKS_SCHEDULE: cron/intervals desde settings
```

### 5.11 Redirects y humanize

```python
# redirects: tabla gestionable desde el admin; middleware actúa solo ante 404:
#   old_path match + new_path → 301 (o 302 según response_code) · new_path vacío → 410

from ronnie.contrib.humanize import naturaltime, intcomma, ordinal
naturaltime(now - timedelta(minutes=4))   # "hace 4 minutos" (locale es)
intcomma(4_500_000)                       # "4.500.000"
ordinal(3)                                # "3.º" (es) / "3rd" (en)
```

---

## 6. Tabla de equivalencias Django ↔ Ronnie

| Django 6.1 | Ronnie | Notas |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `RONNIE_SETTINGS_MODULE` | mismo mecanismo LazySettings |
| `django.conf.settings` | `ronnie.conf.settings` | objeto perezoso, no módulo |
| `django.setup()` | `ronnie.setup()` | populate apps + checks |
| `INSTALLED_APPS` | `INSTALLED_APPS` | rutas de paquetes o `apps.X` |
| `AppConfig` / `apps.py` / `ready()` | idéntico | 3 fases de carga copiadas |
| `manage.py <cmd>` | idéntico (+ CLI `ronnie`) | autodiscovery `<app>/management/commands/` |
| `BaseCommand` / `call_command` | idéntico | argparse puro, `CommandError(returncode)` |
| `system checks` (`check --deploy`) | idéntico | registry `register_check`, tags W/E |
| ORM / migraciones | **MiniDataAPI** + `transform=True` | `ronnie migrate` ejecuta `db.create()` |
| `MIDDLEWARE` (strings) | idéntico → middlewares Starlette | protocolo Ronnie sobre ASGI |
| `SessionMiddleware` + engines | idéntico (cookie firmada por defecto) | escribe `scope["session"]` (compat `sess`) |
| `django.contrib.auth` | `ronnie.contrib.auth` | hashers pbkdf2/argon2, backends, `login()`/`logout()`, `login_required` |
| `django.contrib.messages` | `ronnie.contrib.messages` | niveles 10/20/25/30/40, FallbackStorage |
| `django.contrib.admin` | `ronnie.contrib.admin` | ModelAdmin + HTMX, sin jQuery ni plantillas |
| `django.core.cache` / `CACHES` | idéntico | locmem/filebased/redis/dummy |
| `django.core.signing` | `ronnie.core.signing` | Signer/TimestampSigner (sha256, fallback keys) |
| `django.contrib.humanize` | `ronnie.contrib.humanize` | 6 filtros + locales es/en |
| `django.contrib.redirects` | `ronnie.contrib.redirects` | sin sites framework; 301/302/410 |
| `django.test.*` | `ronnie.testing.*` | client, override_settings, assertions; runner = pytest |
| Celery (no Django, pero habitual) | `ronnie.tasks` | brokers inline/thread/redis + worker/beat CLI |

---

## 7. Referencia de settings

> Defaults viven en `src/ronnie/global_settings.py` (como `django/conf/global_settings.py`); el módulo del usuario los pisa. `ronnie diffsettings` muestra las diferencias.

### Core

| Setting | Default | Fase |
|---|---|---|
| `DEBUG` | `False` | F1 |
| `SECRET_KEY` / `SECRET_KEY_FALLBACKS` | `""` / `[]` (check W si vacío en prod; efímera en dev con warning) | F6 |
| `ALLOWED_HOSTS` | `[]` (en DEBUG acepta `localhost`/`127.0.0.1`/`[::1]`) | F6 |
| `INSTALLED_APPS` | `[]` | F2 |
| `MIDDLEWARE` | `[security, host, sessions, messages, auth, clickjacking]` | F4 |
| `BASE_DIR` | — (lo define el proyecto) | F1 |
| `TIME_ZONE` / `USE_TZ` | `"UTC"` / `True` | F1 |
| `LOGGING` | DEFAULT_LOGGING (console + rotación errores) | F4 |

### Base de datos

| Setting | Default | Fase |
|---|---|---|
| `DATABASES` | `{"default": {"ENGINE": "sqlite", "NAME": BASE_DIR / "db.sqlite3"}}` | F4 |

### Seguridad (nombres y defaults calcados de Django 6.1)

| Setting | Default | Fase |
|---|---|---|
| `SECURE_HSTS_SECONDS` / `_INCLUDE_SUBDOMAINS` / `_PRELOAD` | `0` / `False` / `False` | F6 |
| `SECURE_SSL_REDIRECT` / `SECURE_SSL_HOST` / `SECURE_REDIRECT_EXEMPT` | `False` / `None` / `[]` | F6 |
| `SECURE_REFERRER_POLICY` | `"same-origin"` | F6 |
| `SECURE_CROSS_ORIGIN_OPENER_POLICY` | `"same-origin"` | F6 |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` | F6 |
| `X_FRAME_OPTIONS` | `"DENY"` | F6 |
| `CSRF_COOKIE_NAME` / `CSRF_COOKIE_SAMESITE` / `CSRF_COOKIE_SECURE` / `CSRF_COOKIE_HTTPONLY` | `"csrftoken"` / `"Lax"` / `False` / `False` | F6 |
| `CSRF_HEADER_NAME` / `CSRF_FAILURE_VIEW` | `"X-CSRFToken"` / builtin | F6 |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` | `2_621_440` (2.5 MB) | F6 |

### Sesiones

| Setting | Default | Fase |
|---|---|---|
| `SESSION_ENGINE` | `ronnie.contrib.sessions.engines.signed_cookie` | F7 |
| `SESSION_COOKIE_NAME` | `"ronnie_session"` | F7 |
| `SESSION_COOKIE_AGE` | `1209600` (2 semanas) | F7 |
| `SESSION_COOKIE_HTTPONLY` / `SAMESITE` / `SECURE` / `DOMAIN` / `PATH` | `True` / `"Lax"` / `False` / `None` / `"/"` | F7 |
| `SESSION_FILE_PATH` | `None` → tempfile | F7 (roadmap engine file) |
| `SESSION_SERIALIZER` | JSON (nunca pickle) | F7 |

### Auth

| Setting | Default | Fase |
|---|---|---|
| `AUTH_USER_MODEL` | `"ronnie.contrib.auth.User"` (dotted path a dataclass custom permitido) | F8 |
| `AUTHENTICATION_BACKENDS` | `["ronnie.contrib.auth.backends.ModelBackend"]` | F8 |
| `AUTH_PASSWORD_HASHERS` | `[pbkdf2_sha256, argon2?]` (argon2 solo si extra instalado; primero = para guardar) | F8 |
| `AUTH_PASSWORD_VALIDATORS` | `[MinimumLength(8), CommonPassword, NumericPassword, UserAttributeSimilarity]` | F8 |
| `LOGIN_URL` / `LOGIN_REDIRECT_URL` / `LOGOUT_REDIRECT_URL` | `"/accounts/login/"` / `"/"` / `"/"` | F8 |

### Messages

| Setting | Default | Fase |
|---|---|---|
| `MESSAGE_STORAGE` | `ronnie.contrib.messages.storage.fallback.FallbackStorage` | F9 |
| `MESSAGE_LEVEL` / `MESSAGE_TAGS` | `20 (INFO)` / `{}` | F9 |

### Cache

| Setting | Default | Fase |
|---|---|---|
| `CACHES` | `{"default": {"BACKEND": "…locmem.LocMemCache", "LOCATION": "ronnie", "TIMEOUT": 300, "OPTIONS": {"MAX_ENTRIES": 300, "CULL_FREQUENCY": 3}, "KEY_PREFIX": "ronnie"}}` | F10 |
| `CACHE_MIDDLEWARE_ALIAS` / `CACHE_MIDDLEWARE_SECONDS` / `CACHE_MIDDLEWARE_KEY_PREFIX` | `"default"` / `600` / `""` | F10 |

### Tasks

| Setting | Default | Fase |
|---|---|---|
| `TASKS_BROKER` | `"ronnie.tasks.brokers.inline.InlineBroker"` (dev/test) | F13 |
| `TASKS_RESULT_BACKEND` | `"cache:default"` | F13 |
| `TASKS_DEFAULT_QUEUE` / `TASKS_QUEUES` | `"default"` / `{}` | F13 |
| `TASKS_MAX_RETRIES` / `TASKS_RETRY_BACKOFF` | `3` / `True` | F13 |
| `TASKS_SCHEDULE` | `{}` (nombre → task + cron/interval) | F13 |
| `TASKS_BROKER_URL` | `None` (redis://… al usar RedisBroker) | F13 |

### Admin

| Setting | Default | Fase |
|---|---|---|
| `ADMIN_URL` / `ADMIN_SITE_HEADER` | `"/admin/"` / `"Ronnie Administration"` | F11 |

---

## 8. Fases de construcción paso a paso

> Cada fase termina en **verde**: código + tests + docs del tema + entrada en CHANGELOG + ejemplo actualizado. Tamaños: S ≤ 1 semana · M = 1–3 semanas · L = 3–6 semanas (referencia para 1 dev a tiempo parcial).

---

### Fase 0 — Fundaciones del repositorio · **S**

**Objetivo:** infraestructura de desarrollo profesional lista antes de escribir una línea del framework.

1. `git init`; crear `pyproject.toml` (hatchling, `src` layout, `requires-python = ">=3.10"`, extras: `dev`, `redis`, `argon2`, `postgres`).
2. Instalar con `uv`; añadir `python-fasthtml` (pin `>=0.14,<0.15`).
3. Tooling: **ruff** (lint + format), **mypy** (modo `strict` en `src/ronnie`, gradual), **pytest** + **coverage** (gate 90 % en core), **pre-commit** (ruff, ruff-format, mypy, end-of-file-fixer).
4. CI GitHub Actions: matrix Python 3.10/3.12/3.14, lint + type + tests + coverage en PR; Dependabot/Renovate.
5. `LICENSE` (Apache-2.0, D11), `README.md` mínimo, `CHANGELOG.md` (Keep a Changelog), ramas: `main` protegida + conventional commits.
6. Estructura `src/ronnie/` vacía con `__init__.py` (`__version__ = "0.1.0.dev0"`) y `py.typed`.

**Criterios de aceptación:** ✅ `uv run pytest`, `ruff check`, `mypy` verdes en CI desde el primer commit; badge de CI funcionando.

---

### Fase 1 — Core: settings · **M**

**Objetivo:** sistema de configuración idéntico en espíritu a `django.conf` (síntesis §1).

1. `global_settings.py` con los defaults de la [§7](#7-referencia-de-settings) (solo los de Fase 1: `DEBUG`, `BASE_DIR`…).
2. `conf.py`:
   - `LazySettings`: `__getattr__` perezoso → primero mira el módulo del usuario, luego `global_settings`; `__setattr__` bloqueado en runtime (`RuntimeError`); soporte de **valores callables** (se resuelven al primer acceso).
   - Resolución del módulo: `settings_module=` en `setup()` o env `RONNIE_SETTINGS_MODULE`; si ninguno → `ImproperlyConfigured`.
   - `settings.configured`, `settings.configure(default_settings=...)` (para standalone/tests), `UserSettingsHolder` (base de `override_settings` de Fase 5).
3. Cargar `.env` opcionalmente (`RONNIE_DOTENV=True` o existencia de `.env`): implementación propia de 30 líneas (KEY=VALUE) — sin dependencia extra.
4. Excepciones base en `core/exceptions.py`: `RonnieException`, `ImproperlyConfigured`, `AppRegistryNotReady`.
5. Tests: precedencia defaults ← módulo, env var, error sin módulo, callables, inmutabilidad, namespacing (`RONNIE_` prefijo documentado para terceros).

**Criterios de aceptación:** ✅ cobertura ≥ 90 % del módulo; ✅ doc topic *Settings* escrita.

---

### Fase 2 — Core: registro de aplicaciones · **M**

**Objetivo:** replicar `django.apps` (síntesis §2): configuración declarativa y ciclo de vida por app.

1. `apps.py`:
   - `AppConfig`: `name`, `label` (default último componente, único, identificador válido), `verbose_name`, `path`, `module`, `default=True` para autodetección cuando hay varias subclases en `apps.py`.
   - `Apps` (singleton `ronnie.apps.apps`): `populate(instances)` en **3 fases** (crear configs → importar `models` → ejecutar `ready()`), `get_app_config(label)`, `get_app_configs()`, `is_installed(name)`, `app_configs` ordenado por `INSTALLED_APPS`, flag `apps.ready`.
   - Reglas: `label` duplicado → error claro; `ready()` idempotente; `RuntimeWarning` si se toca BD en `ready()`.
2. `ronnie.setup()` (en `__init__.py`): configura settings (si no hechos) + `apps.populate(settings.INSTALLED_APPS)` + corre checks (Fase 3); solo una vez (`RonnieException` si se repite).
3. `core/signals.py`: `Signal` minimal — `connect(receiver, dispatch_uid=)`, `send(sender, **kwargs)`, referencias débiles, `ReceiversDisconnected`. Señales iniciales: `request_started`, `request_finished`, `setting_changed` (necesaria para `override_settings`).
4. Tests: 3 fases de carga, orden determinista, labels duplicados, autodetección `default=True`, `ready()` con imports perezosos.

**Criterios de aceptación:** ✅ registro pasa suite de contratos equivalente a la de Django para apps; ✅ doc topic *Applications*.

---

### Fase 3 — CLI y management commands + checks · **M**

**Objetivo:** ergonomía `manage.py` completa (síntesis §3).

1. `core/management/__init__.py`:
   - `BaseCommand`: `help`, `add_arguments(parser)`, `handle(*args, **options)` (puede devolver `str`), `self.stdout`/`self.stderr` inyectables (testeables), `self.style.SUCCESS/WARNING/ERROR` (colores, `--no-color`), `requires_system_checks`, `get_version()`.
   - `CommandError(returncode=1)` → stderr + exit code.
   - `find_commands()`: autodiscovery en `<app>/management/commands/*.py` (no `_`-prefixed); built-ins de `ronnie` siempre cargados; apps posteriores en `INSTALLED_APPS` **pisan** built-ins (override).
   - `call_command(name, *args, stdout=StringIO(), **options)`.
   - `execute_from_command_line(argv)` + CLI directa `ronnie` (entry point del pyproject) con opciones globales `--settings`, `--pythonpath`, `--verbosity`, `--no-color`, `--traceback`.
2. `core/checks/`: `register_check(fn, tag)`; tags `models`/`security`/`settings`/`compat`; severidad DEBUG/INFO/WARNING/ERROR con IDs (`W001`…); se ejecutan en `setup()` (si `requires_system_checks`) y en `ronnie check [--deploy] [--tag security]`.
3. Comandos built-in v1: `startproject`, `startapp`, `check`, `version`, `diffsettings`, `shell` (IPython si está, fallback código), `runserver` (uvicorn con `--reload`, `--host/--port`, inyección de `SECRET_KEY` efímera en DEBUG).
4. `core/templates/`: plantillas de archivos para startproject/startapp (ver §4), con `{{ project_name }}`/`{{ app_name }}` (str.format sobre strings, sin Jinja).
5. Tests: cada comando (`call_command` + salida capturada), override de built-ins, argparse, exit codes.

**Criterios de aceptación:** ✅ `uv run ronnie startproject demo && cd demo && python manage.py runserver` levanta una app FastHTML "Hola Ronnie" en < 1 min; ✅ `ronnie check` lista checks vacíos en verde.

---

### Fase 4 — Fábrica de la aplicación (integración FastHTML) · **M**

**Objetivo:** `get_asgi_application()` — de settings a app FastHTML funcionando.

1. `core/asgi.py`:
   - `ronnie.setup()` → construir `fast_app()` con: `secret_key=settings.SECRET_KEY`, `middleware=[...]` resuelto desde `MIDDLEWARE` (strings → import), exception handlers, static mount (`STATIC_URL`/`STATIC_ROOT`), lifespan (señales `startup`/`shutdown`, arranque del task broker).
   - **Spike primero** (½ día): verificar el mecanismo exacto de inclusión de rutas de FastHTML 0.14 (`APIRouter`/`include_router`). `core/routing.py` expone `Router` como adaptador delgado para aislar cambios de FastHTML (riesgo R1).
2. Autodiscovery de rutas: por cada app instalada, importar `<app>.routes` (o `<app>.views`) y montar su `Router` con prefijo opcional del `AppConfig` (`app.label` si el router no declara prefijo). Colisión de rutas → check error.
3. `db.py`: `DATABASES` → `database()` (fastlite sqlite / fastsql postgres si extra); helper `get_db(alias="default")`; convención `models.py`: dataclasses + `TABLES: list[type]`, `ronnie migrate` hace `db.create(T, transform=True)` por app (comando `migrate` en esta fase).
4. Error handlers: 404/500 como FT components (`DEBUG=True` → traceback rico de Starlette/uvicorn; `DEBUG=False` → página sobria). Logging `LOGGING` estilo Django dict-config con DEFAULT_LOGGING.
5. Middleware stack mínimo para cerrar el loop (se completan en F6/F7/F8): `SecurityHeadersMiddleware` (solo nosniff), `HostValidationMiddleware` (permissivo en DEBUG), `SessionMiddleware` (delegación al de Starlette vía `secret_key`).
6. Tests de integración: app ejemplo montada con 2 apps registradas, rutas prefijadas, static, 404/500, `migrate` crea tablas sqlite en tmp_path.

**Criterios de aceptación:** ✅ la app ejemplo `examples/blog` (solo índice) sirve con `runserver`; ✅ test de humo e2e con `httpx.AsyncClient` sobre la ASGI app; ✅ doc *Writing apps* + *Routing*.

---

### Fase 5 — Testing framework v1 · **M**

**Objetivo:** las utilidades de `django.test` esenciales, sobre pytest (síntesis §9, D7).

1. `testing/client.py` — `RonnieTestClient`:
   - wrapper de `starlette.testclient`/httpx con cookies persistentes, `follow_redirects=` (+`response.redirect_chain`), `headers=` dict, helpers `htmx=True` (envía `HX-Request: true`) y `json=True`.
   - `client.login(**credentials)` → backends auth; `client.force_login(user)` (escribe sesión directamente); `client.logout()`. (Se completan en F8; el contrato existe ya.)
   - Response enriquecido: `.status_code`, `.text`, `.content`, `.json()`, `.request`, `.context` (datos expuestos por handlers para tests), `.messages`.
2. `testing/utils.py`: `override_settings` (decorador de clase/función + context manager; implementa `setting_changed`), `modify_settings` (append/prepend/remove), `isolate_apps`.
3. `testing/testcase.py`: `SimpleTestCase` (sin BD; `ronnie.setup()` garantizado), `RonnieTestCase` (BD en sqlite temporal por test: override de `DATABASES` a tmp, tablas recreadas).
4. `testing/assertions.py`: `assertRedirects(resp, expected, status_code=303, target_status_code=200, fetch_redirect=True)`, `assertContains`/`assertNotContains` (texto y también **FT component** serializado), `assertMessages`, `assertNumQueries` (contador del engine sqlite).
5. `testing/pytest_plugin.py`: entry-point `pytest11`; fixtures `client`, `db`, `rf` (RequestFactory), `settings` (override contextual). Comando `ronnie test` → delega en `pytest` (args passthrough, `--failfast`→`-x`, `--tag`→`-m`).
6. Tests: probar el framework de testing con tests reales sobre la app ejemplo (dogfooding desde el día 1).

**Criterios de aceptación:** ✅ `ronnie test` ejecuta la suite del proyecto ejemplo; ✅ `override_settings` funciona decorando clase, método y como context manager; ✅ doc topic *Testing*.

---

### Fase 6 — Seguridad built-in · **L**

**Objetivo:** la pila de seguridad de Django 6.1 (síntesis §4) sin que el usuario configure nada.

1. `core/signing/`: `Signer(key=SECRET_KEY, sep=":", salt=, algorithm="sha256", fallback_keys=SECRET_KEY_FALLBACKS)`, `TimestampSigner` (`SignatureExpired < BadSignature`), `sign_object/unsign_object` (JSON serializer, nunca pickle), `dumps/loads`. Reutilizar `itsdangerous` (ya dependencia transitiva) para la primitiva HMAC.
2. `middleware/security.py` (`SecurityMiddleware`): HSTS (`SECURE_HSTS_*`), SSL redirect 301 con `SECURE_REDIRECT_EXEMPT` (regexes), `Referrer-Policy`, `COOP`, `X-Content-Type-Options: nosniff`.
3. `middleware/host.py`: validación de `Host` contra `ALLOWED_HOSTS` (wildcards `*.example.com`, `*` solo con warning en check); `USE_X_FORWARDED_HOST` opt-in. Error 400 clara.
4. `middleware/csrf.py`:
   - Token en sesión (`_csrf_token`, secreto por sesión); rotación en login.
   - Validación en POST/PUT/PATCH/DELETE: form field `csrfmiddlewaretoken` **o** header `X-CSRFToken`; sobre HTTPS, verificación extra same-origin de `Origin`/`Referer`.
   - Helpers FT: `CsrfToken()` (hidden input), `hx_csrf_headers()` (para `hx-headers` en HTMX); `@csrf_exempt` decorator (marca en `scope`).
   - `CSRF_FAILURE_VIEW` → página 403 FT explicativa.
5. `middleware/clickjacking.py`: `X-Frame-Options: DENY` (`X_FRAME_OPTIONS`), decoradores `xframe_options_deny/sameorigin/exempt`, no sobrescribir header existente.
6. Password hashing (independiente de auth, en `core/` para reuso): formato `algoritmo$iter$salt$hash`; `pbkdf2_sha256` (stdlib, ~1 M iteraciones), `scrypt` (stdlib), `argon2id` (extra); `make_password/check_password/is_password_usable`, upgrade automático de hash al verificar, `harden_runtime`.
7. Password validators: `MinimumLengthValidator`, `CommonPasswordValidator` (lista top-20k incluida), `NumericPasswordValidator`, `UserAttributeSimilarityValidator`; API `validate_password(pw, user=None)`, `password_validators_help_texts()`.
8. Checks `--deploy`: SECRET_KEY vacía/DEBUG=True/ALLOWED_HOSTS vacía/cookies no SECURE/HSTS off/CSRF off… (espejo de `django check --deploy`).
9. `ronnie generatesecretkey` (comando, ~50 chars `secrets.token_urlsafe`).
10. Tests adversariales: tokens manipulados, tokens caducados, replay cross-salt, hosts maliciosos, CSRF sin token/otra sesión/otro origen, timing (harden_runtime), headers presentes y ausentes.

**Criterios de aceptación:** ✅ suite de seguridad con ≥ 40 tests adversariales en verde; ✅ `ronnie check --deploy` sobre el proyecto ejemplo reporta todos los ajustes de prod; ✅ doc topic *Security in Ronnie*.

---

### Fase 7 — contrib.sessions · **M**

**Objetivo:** sesiones pluggables sin romper `sess` (síntesis §5, D6).

1. `contrib/sessions/engines/` con `SessionStore` protocol: dict-like + `cycle_key()`, `flush()`, `set_expiry()/get_expiry_age()/get_expiry_date()`, `clear_expired()`, `session_key`, `modified/accessed`.
   - `signed_cookie` (default): firma con `itsdangerous` sobre JSON — comportamiento actual de Starlette, ahora configurable (age, name, flags).
   - `db`: tabla `ronnie_session(session_key pk char(32), data text JSON, expire_date)` vía MiniDataAPI; purga con `clearsessions`.
   - `cache`: delega en el alias de `CACHES` indicado en `LOCATION` (requiere Fase 10 → **esta parte se entrega tras F10**).
2. `contrib/sessions/middleware.py`: reemplaza al de Starlette — carga engine → `scope["session"]` → tras response, guarda si `modified` (nunca en status 500), setea cookie solo al crear/modificar; aplica `SESSION_COOKIE_*`; rotación de clave en login (anti-fixation).
3. `AUTH`-ready: reserva claves `_`-prefijadas (`_auth_user_id`, `_auth_user_hash`, `_csrf_token`).
4. Comando `clearsessions`; check: engine db sin `default` DB → error.
5. Tests: expiración (edad absoluta y "al cerrar navegador"), flush, cycle_key conserva datos, modified-flag (incluye el gotcha de mutación anidada), serializador JSON rechaza pickle, cookies flags.

**Criterios de aceptación:** ✅ cambiar `SESSION_ENGINE` de cookie→db no requiere tocar ningún handler; ✅ doc topic *Sessions*.

---

### Fase 8 — contrib.auth · **L**

**Objetivo:** auth completo estilo Django sobre MiniDataAPI (síntesis §6).

1. `models.py`: dataclass `User(id pk, username unique, email, password, first_name, last_name, is_active, is_staff, is_superuser, date_joined)`; `get_session_auth_hash()` = HMAC(SECRET_KEY, password-hash); usuarios anónimos `AnonymousUser`. `AUTH_USER_MODEL` permite dataclass propia (contrato: campos mínimos + `get_session_auth_hash`); `get_user_model()`.
2. `backends.py`: `ModelBackend.authenticate(request, username=, password=)` + `get_user(user_id)`; setting `AUTHENTICATION_BACKENDS`; `PermissionDenied` corta la cadena.
3. API: `authenticate()/login(request, user)` (rota sesión, conserva datos anónimos), `logout()`, `update_session_auth_hash()`, `login_required()` (decorator que **preserva la firma** del handler — devuelve wrapper con `functools.wraps` y mismas anotaciones), `user_passes_test()`, `permission_required("blog.add_post")`, `LoginRequiredMiddleware` global con `@login_not_required`.
4. Permisos v1 (sin tablas M2M): `user.has_perm("app_label.codename")` calculado: superuser → todo; staff → view; granular vía set en usuario (`user.permissions: set[str]` serializado como JSON/CSV) — documentado como simplificación consciente; groups en roadmap.
5. Vistas + rutas (montadas con `Router("accounts")` por la app): login/logout (POST), password_change, password_reset (token firmado con `TimestampSigner(salt="pw-reset")`, max_age 3 días; respuesta silenciosa si el email no existe). Render FT + Pico.
6. Beforeware de auth: `scope["auth"]`/`request.user`; compat con el parámetro especial `auth` de FastHTML.
7. Comandos: `createsuperuser` (interactivo + `--noinput` + env vars), `changepassword <username>`.
8. Integración admin (si instalado): requiere `is_staff`; login redirect a `?next=`.
9. Tests: hashers (formato, upgrade, is_usable), validadores, login fija `_auth_user_id` + `_auth_user_hash`, cambio de password invalida sesiones (y `update_session_auth_hash` las conserva), fixation (rotación), brute-force timing, vistas (éxito/errores/redirects), reset token (válido/expirado/manipulado).

**Criterios de aceptación:** ✅ flujo e2e: registro → login → página protegida → cambio de password → sesión vieja invalidada; ✅ doc topics *User authentication* (2 páginas: uso + referencia).

---

### Fase 9 — contrib.messages · **S/M**

**Objetivo:** flash messages (síntesis §7).

1. Niveles `DEBUG=10, INFO=20, SUCCESS=25, WARNING=30, ERROR=40`; `MESSAGE_TAGS` override; `MESSAGE_LEVEL` filtro mínimo.
2. `storage/`: `BaseStorage` (`_get`/`_store`), `SessionStorage` (default), `CookieStorage` (firmada, límite 2048 bytes → descarta y loguea), `FallbackStorage` (cookie→sesión).
3. API: `messages.add_message(request, level, msg, extra_tags="")` + atajos `.debug/.info/.success/.warning/.error`; `fail_silently` para apps reutilizables; `get_messages(request)`; se limpian al iterar (semántica Django, documentada).
4. Componente `Alerts(request, extra="")` → FT: `<div role="alert" class="alert success">…` con clases Pico/aria; middleware mapea storage→request.
5. Helpers de test: `assertMessages(resp, [(level_tag, text), …])`; fixture `messages` en pytest plugin.
6. Tests: niveles filtrados, storages (cookie llena → fallback), limpieza al iterar, extra_tags, render FT accesible.

**Criterios de aceptación:** ✅ ejemplo blog usa `messages` en el CRUD completo; ✅ doc topic *Messages*.

---

### Fase 10 — Cache framework · **L**

**Objetivo:** port fiel del diseño de caché de Django (síntesis §8, D8).

1. `cache/base.py`: `BaseCache` completo — `get/set/add/get_or_set/touch/get_many/set_many/delete/delete_many/clear/incr/decr/close`, `DEFAULT_TIMEOUT=300`, versionado de claves (`VERSION`, `incr_version`), `validate_key` (longitud ≤ 250, caracteres), `make_key` con `KEY_PREFIX` (`"{prefix}:{version}:{key}"`), serialización pickle (documentando el modelo de confianza: claves y valores son del desarrollador).
2. Backends:
   - `LocMemCache`: thread-safe (locks), expiración perezosa + poda al acceso, `MAX_ENTRIES=300`/`CULL_FREQUENCY=3` (expulsa 1/3).
   - `FileBasedCache`: filename = md5(key); pickle + expiración en el propio payload; escritura atómica (tmp+rename); cull periódico.
   - `RedisCache` (extra `ronnie[redis]`): `redis-py`, `LOCATION` URL, `incr/decr` atómicos nativos, `set_many` via pipeline.
   - `DummyCache`.
3. `caches` handler (thread-safe, alias→instancia, `InvalidCacheBackendError`) + `cache = caches["default"]`.
4. Integración HTTP:
   - `cache_page(timeout, cache=None, key_prefix=None)` decorator que preserva firma del handler.
   - `CacheMiddleware` per-site (Update/Fetch en una pasada): GET/HEAD 200, clave = método+host+path+query+`Vary` (respeta `Authorization` y cookies si `vary_on_*`).
   - Helpers response: `patch_cache_control`, `never_cache`, `vary_on_headers`, `vary_on_cookie`, `patch_vary_headers`.
5. Fragment caching para FT: `cache_fragment(key, timeout, builder)` — renderiza FT a string y guarda; `make_fragment_key(name, vary_on=)`. Invalidación documentada.
6. Completar `SESSION_ENGINE=cache` de Fase 7 (cuando ambos mergeados).
7. Tests: cada backend contra el mismo **suite de contratos** (parametrizada — mismo comportamiento garantizado), expiración con `time-machine`-style freeze (monkeypatch de `time.time`), concurrencia locmem (threads), atomicidad filebased, atómica redis (docker-service en CI o fakeredis).

**Criterios de aceptación:** ✅ suite de contratos compartida verde para los 4 backends; ✅ doc topic *Cache* completa (uso, backends, patrones de invalidación, upstream/downstream).

---

### Fase 11 — contrib.admin v1 · **L**

**Objetivo:** el admin generado, joya de la corona, 100 % FT+HTMX (síntesis §12).

1. `site.py`: `AdminSite` (registrable: `default_site` setting para sitios custom) + autodiscover `admin.py` de cada app en `AppConfig.ready()` del admin; `site.register(Table, ModelAdmin)` y decorator `@register(Table)`.
2. `ModelAdmin` v1:
   - `list_display` (campos, propiedades, callables; `@display(description=, ordering=, boolean=)`), `list_display_links`, `list_filter` (valores de campo → sidebar de enlaces), `search_fields` (icontains sobre los campos declarados), `ordering`, `list_per_page`, `empty_value_display`, `readonly_fields`, `fields/exclude`, `actions` (v1: `delete_selected` + custom con checkbox + confirm modal HTMX).
   - Hooks: `get_queryset(request)` (por defecto all()), `save_model(request, obj, change)`, `has_add/change/delete/view_permission()`.
   - Queryset MiniDataAPI: paginación server-side (`limit/offset`), orden (`?o=`), filtro (`?f=field:value`), búsqueda (`?q=`) — convención documentada para tablas grandes.
3. Formularios introspectados: de las anotaciones de la dataclass → `Input/Textarea/CheckboxX/Select` con tipos correctos (`int|str|bool|date|datetime|float|None` opcional); validación básica de tipos; `__ft__` del objeto en la lista si existe.
4. Vistas HTMX: tabla con orden por click de cabecera, búsqueda con `hx-get` + `hx-trigger: keyup changed delay:300ms`, delete con confirm inline, `HX-Push-Url` para filtros compartibles; sin JS custom más allá de HTMX.
5. UI: Pico CSS + layout propio mínimo (`AdminLayout`), nav lateral con apps registradas, `ADMIN_SITE_HEADER`; `message_user()` tras acciones (usa Fase 9).
6. Seguridad: envuelve todas las rutas en `admin_view()` → login_required + `is_staff` + CSRF ya activo (F6).
7. `Redirects` y `Session` (si engine db) se registran en el admin por defecto.
8. Tests: permisos (anónimo→login, staff sí, user normal no), CRUD completo de una tabla de ejemplo, search/filter/order/pagination, actions, formularios por tipo de campo, un `ModelAdmin` custom.

**Criterios de aceptación:** ✅ el admin del ejemplo blog gestiona Posts con búsqueda y filtros sin escribir UI; ✅ doc topic *Admin* + referencia `ModelAdmin`.

---

### Fase 12 — contrib.humanize + contrib.redirects · **S**

**Objetivo:** dos contrib rápidos (síntesis §10–11).

1. `humanize/`: funciones puras `apnumber, intcomma, intword, naturalday, naturaltime, ordinal` con **locale es/en** (`HUMANIZE_LANGUAGE`, default `"es"`; español primero, decisión del proyecto) — todas testeadas contra tablas de casos; helpers FT triviales (`HumanTime(dt)` → `<time>` con title ISO).
2. `redirects/`: tabla `ronnie_redirect(old_path unique, new_path, response_code default 302)`; `RedirectFallbackMiddleware` (último en la pila): solo ante 404 → lookup exacto → 301/302 (según `response_code`) o **410 Gone** si `new_path` vacío; usa `Redirect` de FastHTML para responder; cache opcional de la tabla (`Vary`); registro en admin.
3. Tests: códigos 301/302/410, no interfiere con 200/500, colisiones de path, locale es/en de humanize.

**Criterios de aceptación:** ✅ docs de ambos contribs; ✅ redirects gestionable vía admin.

---

### Fase 13 — Tasks framework · **L**

**Objetivo:** tareas en background con workers (síntesis §D9, diseño propio inspirado en Celery/RQ pero minimal).

1. `tasks/registry.py`: `@task(bind=False, name=None, max_retries=None, retry_backoff=True)` → `Task` con `.delay(*a, **kw)` (sync enqueue), `.apply_async(countdown=, eta=, queue=)`, `.call()` (ejecución directa); nombres por defecto `app_label:func_name`; payload JSON `{id, name, args, kwargs, retries, eta, queue}` (args serializables JSON — documentado).
2. `brokers/` (Protocol: `enqueue(queue, message)`, `dequeue(queues, timeout)`):
   - `InlineBroker` (ejecuta sync — ideal tests y DEBUG).
   - `ThreadBroker` (cola `queue.Queue` + `ThreadPoolExecutor` — dev sin redis).
   - `RedisBroker` (extra): `LPUSH/BRPOP` por cola; ack implícito; dead-letter queue `queue:dead` tras agotar reintentos.
3. `results.py`: estados `PENDING/STARTED/SUCCESS/FAILED/RETRY`; backend en `cache:<alias>` (por defecto) o tabla `ronnie_task_result`; `AsyncResult.get(timeout=)` / `.status` / `.traceback`.
4. `worker.py`: comando `ronnie worker --queues --concurrency N` — `multiprocessing` pool, warmup (importa la app con `ronnie.setup()`), captura SIGTERM/SIGINT (gracia configurable: termina en curso, descarta pendientes), reintentos con backoff exponencial + jitter, heartbeats con logging estructurado, `--pidfile`.
5. `beat.py`: comando `ronnie beat` — lee `TASKS_SCHEDULE` (cron 5 campos o `every: seconds`) con drift-correction; en RedisBroker opcional **redis lock** para singleton.
6. Señales: `task_prerun`, `task_postrun`, `task_failure` (con `signals` de Fase 2).
7. Integración dev: `DEBUG=True` + InlineBroker → todo funciona sin infra; check avisa si broker no-inline en DEBUG sin redis.
8. Tests: InlineBroker determinista en suite; contratos de broker compartidos con RedisBroker (CI service redis-container); worker multiproceso con tareas de prueba (sleep/raise), reintentos y dead-letter verificados, beat dispara según cron con reloj simulado.

**Criterios de aceptación:** ✅ ejemplo blog reconstruye el índice de búsqueda con `rebuild_search_index.delay()` y un `ronnie worker` local lo procesa; ✅ doc topic *Background tasks*.

---

### Fase 14 — Documentación, ejemplos y 1.0 · **M**

1. Docs `mkdocs-material` (publicadas en GitHub Pages): `Tutorial: tu primera app Ronnie` (estilo polls — proyecto completo con admin+auth+tasks), topics espejo de Django (settings, apps, commands, security, sessions, auth, messages, cache, testing, tasks, admin, humanize, redirects), referencia de API (mkdocstrings), página de settings completa.
2. `examples/blog` pulido como referencia canónica (es usado por la CI como test e2e).
3. Limpieza 1.0: deprecación de APIs internas, `ronnie check --deploy` completo, guía de despliegue (uvicorn+gunicorn, Docker, statics con whitenoise-style middleware o CDN), guía de migración mental desde Django (la tabla §6 expandida).
4. Release process automatizado (tag → build → publish PyPI `python-ronnie` + GitHub Release con notas del CHANGELOG).

---

## 9. Estrategia de calidad: testing del framework, CI y tooling

### 9.1 Pirámide de tests del propio Ronnie

| Nivel | Qué | Herramientas |
|---|---|---|
| Unit | settings, apps, signing, hashers, humanize, cache locmem/filebased | pytest, hypothesis (propiedad: claves, firmas) |
| Contrato | suites parametrizadas compartidas por implementación (cache backends, session engines, task brokers) — *mismo comportamiento garantizado* | pytest parametrize |
| Integración | app de ejemplo real en memoria: request→handler→response con toda la pila | RonnieTestClient (dogfooding) |
| E2E/seguridad | flujos auth/CSRF/sessions adversariales; redis real como service de CI | httpx ASGI, testcontainers/service containers |
| Humo | `startproject` → `runserver` → petición OK en cada PR | script CI |

### 9.2 Reglas de código (best practices Python)

- Type hints en el 100 % del código público; `mypy --strict` verde en `src/ronnie` (check en CI).
- `typing.Protocol` para todos los contratos de backends (cache, brokers, storages, backends auth) — test con `runtime_checkable` + suites de contrato.
- Dataclasses para todos los valores (Message, TaskMessage, AppConfig data); sin herencia donde baste un Protocol.
- `__all__` explícito en cada módulo público; API estable = lo documentado en docs/ (semver: nada fuera de docs cuenta).
- Import perezoso de extras (`redis`, `argon2`) con errores claros: *"instala ronnie[redis]"*.
- Sin estado global oculto: los singletons (`apps`, `caches`, `settings`) son explícitos y reseteables en tests (fixtures `autouse` en la suite).
- Cobertura: gate 90 % en `src/ronnie/core` + `cache`; ≥ 85 % global.
- pre-commit + ruff (lint+format) + conventional commits + CHANGELOG automatizable (git-cliff).

### 9.3 CI (resumen)

```
PR → lint (ruff) → types (mypy) → tests (3.10/3.12/3.14, sqlite) 
   → tests redis (service container) → coverage gate → smoke startproject
main → todo lo anterior + build sdist/wheel + mkdocs deploy (docs branch)
tag  → publish PyPI (trusted publishing) + GitHub Release
```

---

## 10. Versionado, publicación y documentación

| Versión | Contenido | Estado |
|---|---|---|
| `0.1.0` | Fases 0–4: core (settings, apps, commands, fábrica ASGI, runserver) | alpha usable |
| `0.2.0` | Fase 5: testing framework | |
| `0.3.0` | Fase 6: seguridad built-in | |
| `0.4.0` | Fases 7–9: sessions + auth + messages | beta: proyecto real viable |
| `0.5.0` | Fase 10: cache framework | |
| `0.6.0` | Fase 11: admin | |
| `0.7.0` | Fases 12–13: humanize + redirects + tasks | feature-complete |
| `1.0.0` | Fase 14: docs completas + estabilización API | GA |

- **SemVer estricto** desde `0.1.0` con `CHANGELOG.md` (Keep a Changelog). Durante 0.x: solo el docs/ reference surface es estable.
- Publicación: **Trusted Publishing** de PyPI desde GitHub Actions (sin tokens), distribución `python-ronnie` (D1).
- Docs versionadas con mkdocs `mike`; cada release menor congela una versión de docs.

---

## 11. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|--------|-------|---------|-----------|
| R1 | FastHTML está en 0.x: cambios de API (`fast_app`, routers, middleware hooks) rompen la integración | Alta | Alto | Adaptador delgado en `ronnie.core.routing/asgi`; pin `>=0.14,<0.15`; **contract tests contra FastHTML** que fallen ruidosamente en CI cuando suba la dependencia |
| R2 | MiniDataAPI insuficiente para el admin (introspección de tipos, orden/filtrado server-side) | Media | Alto | Spike en la primera semana de F11; fallback: contract `TableProtocol` (queryset mínimo documentado) + limitar `search/filter` a lo soportado por el backend |
| R3 | CSRF + HTMX: fricción en flujos hx-post | Media | Medio | Helper `hx_csrf_headers()` + documentación prominente + tests e2e de formularios HTMX en el ejemplo |
| R4 | Scope creep (querer TODO Django: ORM, i18n, forms, views genéricas…) | Alta | Alto | Este documento es el scope; todo lo demás → sección explícita *Non-goals* (ORM, migraciones reales, i18n framework, forms declarativos, templates, GEODjango… lol) y roadmap post-1.0 |
| R5 | Nombre PyPI ocupado (`ronnie`) | Cierta | Bajo | Ya resuelto: distribución `python-ronnie`, import `ronnie` (D1); verificar disponibilidad antes de Fase 14 |
| R6 | Workers multiproceso: complejidad de depurar/comportamiento en contenedores | Media | Medio | InlineBroker por defecto en dev; worker con logging estructurado, `--verbosity`, guía de troubleshooting |
| R7 | Seguridad sutil (firmas, CSRF, sesiones) | Media | Alto | Portar los *tests conceptuales* de Django (casos límite conocidos: mutación anidada de sesión, hardened timing, fixation) + revisión externa antes de 1.0 |
| R8 | Mantenimiento de 4 backends cache + 3 brokers | Media | Medio | Suites de contrato compartidas: un comportamiento se testea una vez para todos |

### Non-goals explícitos (post-1.0 posible, fuera de scope ahora)

ORM propio · sistema de migraciones versionadas (nos vale `transform=True`) · i18n/translations framework (humanize es/locale no es i18n) · forms declarativos · class-based views · template engine · soporte WSGI (solo ASGI) · multi-database routing (solo alias `default`) · realtime/sockets (ya cubierto por FastHTML ws).

---

## 12. Hoja de ruta a 1.0

```
2026-Q4   F0–F2   fundaciones + settings + apps            → 0.1.0.dev
2027-Q1   F3–F4   commands + fábrica ASGI (runserver)      → 0.1.0
2027-Q1   F5      testing framework                         → 0.2.0
2027-Q2   F6      seguridad                                 → 0.3.0
2027-Q2   F7–F9   sessions · auth · messages                → 0.4.0 (beta)
2027-Q3   F10     cache                                     → 0.5.0
2027-Q3   F11     admin                                     → 0.6.0
2027-Q4   F12–F13 humanize · redirects · tasks              → 0.7.0
2028-Q1   F14     docs + estabilización                     → 1.0.0 🚀
```

*(Referencia para 1 dev a tiempo parcial; las fases 5–13 son paralelizables por parejas: p.ej. cache ∥ seguridad, humanize/redirects ∥ admin.)*

### Primeras 5 acciones concretas (si empiezas hoy)

1. `git init` + Fase 0 completa (pyproject, uv, ruff, mypy, pytest, CI) — medio día.
2. `conf.py` + `global_settings.py` con tests (Fase 1) — el corazón de todo lo demás.
3. Spike de ½ día sobre FastHTML 0.14: `fast_app(middleware=…)` + `APIRouter` + `include` — eliminar R1 temprano.
4. `apps.py` con las 3 fases de `populate()` (Fase 2).
5. `BaseCommand` + `startproject`/`startapp`/`runserver` mínimos (Fase 3) — desde ahí, el framework se puede usar para construirse a sí mismo (dogfooding).
