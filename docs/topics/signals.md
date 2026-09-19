# Signals

Signals are a lightweight in-process pub/sub: senders broadcast events,
any number of receivers react. They decouple apps from each other — a
billing app can react to "post published" without the blog app knowing
billing exists.

## Sending and receiving

```python
from ronnie.core.signals import Signal

post_published = Signal()


# The receiver (any callable accepting sender + keyword arguments)
def notify_subscribers(sender, **kwargs):
    send_email(kwargs["post"].title)

post_published.connect(notify_subscribers, dispatch_uid="notify")


# Anywhere in the blog app:
post_published.send(sender=post, post=post)
```

API summary:

| Method | Behaviour |
|---|---|
| `connect(receiver, dispatch_uid=None, weak=True)` | Register; `dispatch_uid` de-duplicates registrations |
| `disconnect(receiver=None, dispatch_uid=None)` | Unregister; returns `True` if something was removed |
| `send(sender=None, **kwargs)` | Invoke receivers; the first exception propagates |
| `send_robust(sender=None, **kwargs)` | Collect exceptions as per-receiver results instead |
| `has_listeners()` | Cheap check before doing work |

Receivers are stored as **weak references** by default — module-level
functions survive, but closures and short-lived objects may disappear. Pass
`weak=False` for lambdas or dynamically created receivers.

## Built-in signals

| Signal | Sent when | Payload |
|---|---|---|
| `request_started` | A request enters the app | `sender=app` |
| `request_finished` | The response ships | `sender=app` |
| `setting_changed` | A test overrides a setting | `setting=`, `value=`, `enter=` |
| `task_prerun` | A task starts executing | `task_id=`, `retries=` |
| `task_postrun` | A task succeeds | `task_id=`, `result=` |
| `task_failure` | A task raises | `task_id=`, `retries=`, `traceback=` |

```python
from ronnie.core.signals import task_failure

def alert_on_failure(sender, task_id, traceback, **kwargs):
    metrics.count("task.failure", tags=[f"task:{sender.name}"])

task_failure.connect(alert_on_failure, dispatch_uid="metrics")
```

## Where to connect

Register receivers in your app's `AppConfig.ready()` so they are bound
exactly once, after every app has loaded:

```python
# apps/billing/apps.py
class BillingConfig(AppConfig):
    name = "apps.billing"

    def ready(self):
        from apps.blog.signals import post_published   # import lazily!
        from .handlers import charge_on_publish

        post_published.connect(charge_on_publish, dispatch_uid="billing-charge")
```

## Guidelines

- Give every receiver a `dispatch_uid` — it makes double-registration
  impossible and disconnects explicit.
- Accept `**kwargs` in receivers so new payload keys don't break them.
- Signals are synchronous and in-process. For cross-process work, use the
  [tasks framework](tasks.md).
- Don't use signals as a way to hide control flow that belongs in a function
  you can read and test.
