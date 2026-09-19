# Password management

Hashing, verifying and validating passwords is easy to get wrong; Ronnie
does it the boring, correct way. Stored hashes use the widely-adopted
`<algorithm>$<parameters>$<salt>$<hash>` text format, so hashes are
portable across systems that speak it.

## Hashing and checking

```python
from ronnie.core.passwords import make_password, check_password

encoded = make_password("s3cret!")      # pbkdf2_sha256$1000000$<salt>$<hash>
check_password("s3cret!", encoded)      # True
check_password("wrong", encoded)        # False
```

- `make_password(None)` produces an *unusable* hash — for accounts without
  credentials — and `check_password` rejects it.
- Hashes are salted per-password; two users with the same password get
  different stored values.
- Verification recognizes **every** hasher listed in `PASSWORD_HASHERS`;
  the first entry is used for new hashes. Bumping PBKDF2 iterations and
  re-saving on next login upgrades old hashes in place.

Default configuration:

```python
PASSWORD_HASHERS = [
    "ronnie.core.passwords.hashers.PBKDF2PasswordHasher",  # encodes new passwords
    "ronnie.core.passwords.hashers.ScryptPasswordHasher",  # verifies, too
]
```

Available hashers:

| Hasher | Algorithm | Notes |
|---|---|---|
| `PBKDF2PasswordHasher` | pbkdf2_sha256 | Default encoder; stdlib only |
| `ScryptPasswordHasher` | scrypt | Memory-hard; verifies out of the box |
| `Argon2PasswordHasher` | argon2 | Requires the `ronnie[argon2]` extra |

To make Argon2 the encoder, list it first (it must also be installable):

```python
PASSWORD_HASHERS = [
    "ronnie.core.passwords.hashers.Argon2PasswordHasher",
    "ronnie.core.passwords.hashers.PBKDF2PasswordHasher",
    "ronnie.core.passwords.hashers.ScryptPasswordHasher",
]
```

## Validation

Validation rejects weak *new* passwords before they are hashed. Configure
it with the format every Ronnie project uses:

```python
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "ronnie.core.passwords.validators.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "ronnie.core.passwords.validators.CommonPasswordValidator"},
    {"NAME": "ronnie.core.passwords.validators.NumericPasswordValidator"},
    {"NAME": "ronnie.core.passwords.validators.UserAttributeSimilarityValidator",
     "OPTIONS": {"user_attributes": ["username", "email"]}},
]
```

Use it wherever users set a password (sign-up, change, reset):

```python
from ronnie.core.passwords import validate_password, password_validators_help_texts

try:
    validate_password(new_password, user=user)
except ValidationError as err:
    show(err.messages)          # ["This password is too common.", …]
```

`password_validators_help_texts()` renders the bullet list to show next to
the password field.

Built-in validators:

| Validator | Rejects |
|---|---|
| `MinimumLengthValidator(min_length=8)` | Passwords shorter than the minimum |
| `CommonPasswordValidator` | A curated list of frequently-used passwords |
| `NumericPasswordValidator` | Entirely numeric passwords |
| `UserAttributeSimilarityValidator(max_similarity=0.7)` | Passwords too close to username/email/first/last name |

Custom validators are any class with
`validate(password, user=None)` (raising `ValidationError`) and
`get_help_text()`.

## In handlers

The full pattern for a password change form:

```python
old_ok = check_password(old_password, user.password)
if old_ok and new1 == new2:
    try:
        validate_password(new1, user=user)
    except ValidationError:
        ...  # show messages
    else:
        user.password = make_password(new1)
        users.update(user)
        update_session_auth_hash(req, user)   # keep this session alive
```

See [authentication](authentication.md) for the session-invalidation rules
that make the last line matter.
