# Authentication

The `ronnie.contrib.auth` app provides users, password login, access-control
decorators and ready-made `/accounts/*` pages — wired on top of
[sessions](sessions.md) and the [password tooling](passwords.md).

## Setup

```python
INSTALLED_APPS = [
    "ronnie.contrib.sessions",
    "ronnie.contrib.auth",
    ...
]
LOGIN_URL = "/accounts/login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
```

`python manage.py migrate` creates the user table. Create your first
account non-interactively:

```bash
python manage.py createsuperuser --noinput   # env: RONNIE_SUPERUSER_USERNAME/PASSWORD
python manage.py createsuperuser             # interactive prompts
```

## Users

```python
from ronnie.contrib.auth import User, create_user, create_superuser, get_user_model
```

| Member | Purpose |
|---|---|
| `User` | Row dataclass: `username`, `email`, `password` (hash), `first_name`, `last_name`, `is_active`, `is_staff`, `is_superuser`, `date_joined`, `user_permissions` |
| `create_user(username, password, email=…)` | Hashes the password and inserts |
| `create_superuser(...)` | Same, with `is_staff`/`is_superuser` |
| `get_user_model()` | The active user class (`AUTH_USER_MODEL`) |
| `AnonymousUser` | The logged-out user; falsy, no permissions |

### Custom users

Point `AUTH_USER_MODEL` at your own dataclass when you need extra fields:

```python
# apps/members/models.py
@dataclass
class Member:
    id: int | None = None
    username: str = ""
    password: str = ""
    is_active: bool = True
    is_staff: bool = False
    is_superuser: bool = False
    plan: str = "free"

    def get_session_auth_hash(self) -> str:   # required by the session check
        ...
```

```python
AUTH_USER_MODEL = "apps.members.models.Member"
```

## Logging in and out

```python
from ronnie.contrib.auth import authenticate, login, logout

user = authenticate(request, username=name, password=pw)
if user is not None:
    login(request, user)     # rotates the session key, stores id + hash
else:
    ...                      # bad credentials
```

`login()` stores the user's id plus an HMAC of their password hash. Change
the password and every other session dies instantly — unless the handler
that changed it calls:

```python
from ronnie.contrib.auth import update_session_auth_hash
update_session_auth_hash(request, user)
```

`logout(request)` flushes the session and never raises.

### Authentication backends

`authenticate()` walks `AUTHENTICATION_BACKENDS` (default: the model
backend checking username + password). A backend is any object with:

```python
class HeaderBackend:
    def authenticate(self, request=None, **credentials):
        token = ...  # verify a bearer token
        return user_or_None

    def get_user(self, user_id):
        return user_or_None
```

Raising `PermissionDenied` inside `authenticate` stops the chain and fails
the login outright.

## Access control in handlers

```python
from ronnie.contrib.auth import login_required, permission_required, user_passes_test

@rt
@login_required
def dashboard(req):
    ...

@rt
@permission_required("blog.publish_post", raise_exception=True)
def publish(req, post: PostForm):
    ...

@rt
@user_passes_test(lambda user: user.plan == "pro")
def pro_reports(req):
    ...
```

The decorators redirect anonymous users to `LOGIN_URL` with `?next=`; they
need the handler to declare `req` (or `auth`) so the user is reachable.
Inside any handler, the special `auth` parameter is truthy when logged in:

```python
@rt
def feed(auth):
    return personalized() if auth else public()
```

### Permissions

`user.has_perm("app_label.codename")` resolves:

1. superusers: always `True`;
2. `user.user_permissions` — a comma-separated list of
   `"app.codename"` / `"app.*"` entries;
3. staff users get `view*` codenames for free.

Groups with database-backed many-to-many permissions are intentionally out
of scope; model your own linkage if you need hierarchies.

## Built-in pages

Installing the app mounts these routes (FT + Pico, CSRF-protected):

| Route | Behaviour |
|---|---|
| `GET/POST /accounts/login` | Sign-in form; honours `?next=` |
| `POST /accounts/logout` | Ends the session (POST-only, by design) |
| `GET/POST /accounts/password_change` | Current + new password; keeps the current session alive, invalidates others |

## Password change, the safe way

```python
if check_password(old, user.password):
    user.password = make_password(new)
    get_table(get_user_model()).update(user)
    update_session_auth_hash(request, user)
```

The `changepassword` management command does the same from the CLI:

```bash
python manage.py changepassword alice
```
