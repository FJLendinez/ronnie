# Signing

When you need to hand data to the outside world and get it back untampered —
password-reset links, "remember this choice" tokens, unguessable IDs — sign
it. A signature is a keyed hash: change one character of the value and
verification fails.

## Signer

```python
from ronnie.core.signing import Signer

signer = Signer()
signed = signer.sign("hello")        # "hello:<signature>"
original = signer.unsign(signed)     # "hello" — or raises BadSignature
```

`Signer` derives its key from `SECRET_KEY` (or take control with
`key=`/`fallback_keys=`). The salt is a namespace: two signers with
different salts produce incompatible signatures, so a token minted for
email confirmation can never be replayed as a password reset:

```python
Signer(salt="password-reset")
Signer(salt="email-confirm")
```

Options:

| Argument | Default | Meaning |
|---|---|---|
| `key` | `SECRET_KEY` | Primary signing key |
| `fallback_keys` | `[]` | Verify-only keys (key rotation) |
| `salt` | `"ronnie.core.signing"` | Namespace isolating signatures |
| `sep` | `":"` | Separator between value and signature |
| `algorithm` | `"sha256"` | HMAC hash name |

## TimestampSigner

Adds a timestamp so values can expire:

```python
from datetime import timedelta
from ronnie.core.signing import TimestampSigner, SignatureExpired

signer = TimestampSigner(salt="pw-reset")
token = signer.sign("user-42")

try:
    value = signer.unsign(token, max_age=timedelta(days=3))
except SignatureExpired:
    ...  # too old — treat as invalid
```

## Signing whole objects

```python
from ronnie.core.signing import dumps, loads

token = dumps({"uid": 42, "op": "reset"}, salt="pw-reset")
data = loads(token, salt="pw-reset", max_age=7200)
```

The payload is JSON (never pickle — a stolen `SECRET_KEY` must never become
remote code execution) and base64url-encoded, so tokens are safe in URLs
and cookies.

## Practical patterns

A password-reset link that needs no server-side state:

```python
def make_reset_link(user):
    token = dumps({"uid": user.id}, salt="pw-reset")
    return f"https://example.com/reset?token={token}"

def consume_reset_link(token, user):
    data = loads(token, salt="pw-reset", max_age=3600)
    if data["uid"] != user.id:
        raise Tampered
```

Guidelines:

- **Every use of `dumps` gets its own salt.** A salt is a purpose, not a
  secret.
- Always pass `max_age` for anything security-relevant.
- Keep `SECRET_KEY_FALLBACKS` aligned with key rotation so outstanding
  tokens survive a key change.
- Signing proves *integrity*, not *confidentiality* — the payload is
  readable by anyone. Don't put secrets in it.
