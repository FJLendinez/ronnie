# Testing

Ronnie's test tools make HTTP-level testing of your handlers trivial: an
ergonomic client, per-test throwaway databases, settings overrides and
plain-unittest integration — with pytest as the runner.

## Running tests

```bash
python manage.py test                # delegates to pytest
python manage.py test apps/blog -x   # args pass through; -x = fail fast
ronnie test                          # same thing
```

## The test client

```python
from ronnie.testing import RonnieTestClient

client = RonnieTestClient()
response = client.get("/blog/")
assert response.status_code == 200
assert "hello" in response.text

response = client.post("/blog/save", data={"title": "hi"})
response = client.json_request("GET", "/api/stats")     # JSON body/parse
response = client.htmx("GET", "/fragment/")             # sends HX-Request
```

- Cookies persist across requests on the same client; use a second client
  to act as another visitor.
- Redirects are **not** followed by default; pass `follow_redirects=True`
  (then `response.history` holds the chain) or build the client with it.
- The ASGI app is built lazily on first use, so a client created in a
  fixture picks up settings configured inside the test.
- `client.cookies` exposes the jar for direct inspection.

### Logging in

For full login flows, POST the built-in form with its
[CSRF](security.md#csrf-protection) token. For quick setup, seed the
session directly:

```python
from ronnie.contrib.auth import User, login

user = create_user("alice", "wonderland-1")
# then, inside a request handler or via the login page…
```

The `/accounts/login` flow with the token is the end-to-end-faithful way
and takes three lines with a regex.

## RonnieTestCase

```python
from ronnie.testing import RonnieTestCase

class PostTests(RonnieTestCase):
    def test_publish(self):
        posts.insert(title="hi")
        response = self.client.get("/blog/")
        self.assertContains(response, "hi")
```

- `SimpleTestCase` — fresh client per test, no database machinery.
- `RonnieTestCase` — additionally gives every test a **throwaway sqlite
  database** with all app tables installed; nothing leaks between tests.
- Class-level `settings_overrides = override_settings(...)` applies for
  the whole class; `with self.settings(DEBUG=True):` for a block.

### Assertions

| Assertion | Checks |
|---|---|
| `assertContains(r, "text", count=None, status_code=200)` | Status and body text (exact `count` if given) |
| `assertNotContains(r, "text", status_code=200)` | Status and absence |
| `assertRedirects(r, "/x/", status_code=(302, 303), target_status_code=200)` | Redirect chain and final status |
| `self.fail(msg)` | Unconditional failure |

## Overriding settings

```python
from ronnie.testing import override_settings

# Context manager
with override_settings(DEBUG=True):
    ...

# Function/method decorator
@override_settings(TIME_ZONE="Atlantic/Canary")
def test_zone(self): ...

# List surgery: append / prepend / remove
from ronnie.testing.utils import modify_settings

with modify_settings(MIDDLEWARE={"append": ["myproject.middleware.X"]}):
    ...
```

Every override emits `setting_changed`, so caches you build with
`@register` on that signal rebuild automatically.

## pytest style

The bundled plugin provides fixtures to any pytest project:

```python
def test_index(client):                     # RonnieTestClient against settings
    assert client.get("/blog/").status_code == 200

def test_queries(db):                       # throwaway database + tables
    posts.insert(title="hi")
    assert len(posts()) == 1

def test_flag(ronnie_settings):             # override factory
    with ronnie_settings(DEBUG=True):
        ...
```

Settings must be configured (via `RONNIE_SETTINGS_MODULE` or
`settings.configure`) before the `client`/`db` fixtures build the app —
set the env in an early fixture if in doubt.

## Testing commands

```python
from io import StringIO
from ronnie.core.management import call_command

out = StringIO()
call_command("publish_scheduled", "--dry-run", stdout=out)
assert "0 posts" in out.getvalue()
```

Inject `stdout`/`stderr` and assert on the captured text; pass options as
keyword arguments instead of strings when convenient.

## What to test

- **Handlers via the client** — status, body, redirects, session state.
- **CSRF is on by default**: POSTs without a token get 403; test that your
  forms include `CsrfToken(req)` by posting without one and expecting
  failure.
- **Commands** with `call_command`.
- **Tasks** with the inline broker (`.delay()` runs synchronously), so
  request-level tests exercise the real code path.
