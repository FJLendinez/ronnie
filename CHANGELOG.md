# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-09-20

### Added

- **Mirror import surfaces**: Ronnie mirrors the FT package module by
  module — `ronnie.components`, `ronnie.svg`, `ronnie.pico`,
  `ronnie.xtend`, `ronnie.oauth`, `ronnie.jupyter`, `ronnie.live_reload`,
  `ronnie.toaster`, `ronnie.js`, `ronnie.ft`, `ronnie.cli`, `ronnie.basics`,
  `ronnie.authmw`, `ronnie.fastapp`, `ronnie.starlette` and the optional
  `ronnie.stripe_otp` — each a direct derivation exposing every public
  attribute (including lazily-resolved names). `ronnie.core` merges the
  engine derivation with Ronnie's own primitives. `ronnie.common` stays
  **curated** (the everyday surface plus Ronnie's `Router`, `CsrfToken`,
  `csrf_exempt`, `Alerts`, `HumanTime`). Framework modules and generated
  projects import exclusively from the Ronnie namespace; user code never
  imports fasthtml.
- **Core**: LazySettings (`RONNIE_SETTINGS_MODULE`, callables, `override_settings`),
  app registry (`AppConfig`, 3-phase populate, per-app routes/tasks autodiscovery),
  system checks (`ronnie check [--deploy]`), signals.
- **CLI**: `ronnie`/`manage.py` with `startproject`, `startapp`, `runserver`,
  `shell`, `check`, `migrate`, `test`, `diffsettings`, `version`,
  `generatesecretkey`, `createsuperuser`, `changepassword`, `clearsessions`,
  `worker`, `beat`.
- **ASGI factory**: `get_asgi_application()` (FastHTML + Ronnie middleware
  stack, static files, custom 404/500, LOGGING dict-config).
- **Security**: `Signer`/`TimestampSigner` (Django-format), security headers,
  host validation, CSRF (session token, form/header, Origin checks), X-Frame-Options,
  PBKDF2/scrypt/argon2 hashers, 4 password validators.
- **contrib.sessions**: engines cookie (signed) / db / cache; `flush`,
  `cycle_key`, `clearsessions`; TrackingSession saves-on-modify.
- **contrib.auth**: User/AnonymousUser, ModelBackend, `authenticate/login/logout`,
  `@login_required`/`@user_passes_test`/`@permission_required`, built-in
  /accounts views (login/logout/password_change), session-hash invalidation.
- **contrib.messages**: Django levels/tags, session/cookie/fallback storages,
  `Alerts()` FT component, MessagesMiddleware.
- **contrib.admin**: AdminSite/ModelAdmin (`list_display`, `search_fields`,
  `list_filter`, `ordering`, pagination, `delete_selected`), introspected
  forms, autodiscover, staff-only.
- **contrib.humanize**: apnumber/intcomma/intword/naturalday/naturaltime/ordinal
  with es/en locales; `HumanTime()`.
- **contrib.redirects**: db-backed 404 fallback (301/302/410) + admin integration.
- **Cache**: `CACHES`/`caches`/`cache`, backends locmem/filebased/redis/dummy,
  `cache_page`, per-site `CacheMiddleware`, fragment caching.
- **Testing**: `RonnieTestClient` (lazy, HTMX helper), `SimpleTestCase`/
  `RonnieTestCase`, `override_settings`/`modify_settings`, assert helpers,
  pytest plugin (`client`, `db` fixtures), `ronnie test` (pytest).
- **Tasks**: `@task`/`.delay()`/`.call()`, brokers inline/thread/redis,
  `AsyncResult` (cache-backed), retries with backoff, `ronnie worker`/`beat`,
  TASKS_SCHEDULE intervals.

[Unreleased]: https://github.com/fjlendinez/ronnie/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/fjlendinez/ronnie/releases/tag/v0.1.0
