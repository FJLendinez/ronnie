# Background tasks

Some work must not run inside a request: sending mail, rebuilding indexes,
processing uploads. Ronnie's task framework runs registered functions
outside the request cycle, with retries, results and a scheduler.

## Defining and calling tasks

```python
# apps/blog/tasks.py  (auto-imported at startup)
from ronnie.tasks import task

@task(max_retries=3, retry_backoff=True)
def rebuild_index(post_id: int):
    ...

rebuild_index.call(post_id=42)               # run synchronously, right now
rebuild_index.delay(post_id=42)              # enqueue via the broker
rebuild_index.apply_async(args=(42,), countdown=60, queue="indexing")
```

Arguments must be JSON-serializable — they cross process boundaries.

## Results

`delay`/`apply_async` return a handle you can poll or block on:

```python
result = rebuild_index.delay(post_id=42)
result.status       # PENDING → STARTED → SUCCESS | FAILED | RETRY
result.get(timeout=10)     # return value; raises on failure/timeout
result.traceback    # stored traceback when status is FAILED
```

Results live in the [cache](cache.md) framework
(`TASKS_RESULT_BACKEND = "cache:default"`), so they survive the worker and
die with the cache's TTL.

## Brokers

`TASKS_BROKER` selects the transport:

| Broker | Behaviour | Best for |
|---|---|---|
| `ronnie.tasks.brokers.inline.InlineBroker` *(default)* | Runs on `.delay()`, synchronously | Tests, `DEBUG` |
| `ronnie.tasks.brokers.thread.ThreadBroker` | Background thread pool | Local development |
| `ronnie.tasks.brokers.redis.RedisBroker` | Redis queues (`ronnie[redis]`) | Production |

```python
TASKS_BROKER = "ronnie.tasks.brokers.redis.RedisBroker"
TASKS_BROKER_URL = "redis://127.0.0.1:6379/2"
```

A custom broker implements `enqueue(queue, message)` and
`dequeue(queues, timeout)`.

## Workers

```bash
python manage.py worker                     # consume the default queue
python manage.py worker --queues default,indexing --concurrency 4
```

Workers boot the full environment (settings, apps, database) and consume
until `SIGTERM`/`SIGINT`, finishing the task in flight. Failures retry up
to `max_retries` with exponential backoff (`retry_backoff=True`; the
per-task argument wins over `TASKS_RETRY_BACKOFF`):

```
attempt 1 → wait 2s → attempt 2 → wait 4s → attempt 3 → FAILED (traceback stored)
```

## Periodic tasks (beat)

```python
TASKS_SCHEDULE = {
    "nightly-cleanup": {"task": "apps.blog.tasks.cleanup", "every": 86_400},
    "fast-metrics":    {"task": "apps.stats.tasks.rollup", "every": 60},
}
```

```bash
python manage.py beat      # fires entries on their intervals, drift-corrected
```

Run **one** beat process (a cron-style singleton) and as many workers as
you like; entries dispatch through the broker like any other task.
Interval-only schedules are supported today; cron expressions are on the
roadmap.

## Signals

```python
from ronnie.core.signals import task_failure

@task_failure.connect
def alert(sender, task_id, traceback, **kw):
    page_on_call(f"{sender.name} failed")
```

See [signals](signals.md) for the full receiver contract.

## Guidance

- Keep tasks **idempotent**: retries mean a task may run twice.
- Pass IDs, not model objects — re-read inside the task so you act on
  fresh data.
- Respect `max_retries` for flaky externals; use 0 for "fail loudly".
- During development, the inline broker makes `.delay()` behave like
  `.call()`, so request paths are exercised without infrastructure.
