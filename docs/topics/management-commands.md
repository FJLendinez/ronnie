# Management commands

Commands are the project's operational toolbox: migrations, checks, users,
workers — anything you run from a shell. They live in
`<app>/management/commands/*.py` and are discovered automatically.

## Running commands

```bash
python manage.py <command> [options]      # from the project directory
ronnie <command> [options]                # equivalent, using the CLI entry point
```

Global options work with either form and can appear anywhere in the line:

| Option | Effect |
|---|---|
| `--settings=module.path` | Select the settings module for this run |
| `--pythonpath=/some/dir` | Prepend to `sys.path` |
| `--version` | Print the framework version |

Built-in commands:

`startproject`, `startapp`, `runserver`, `shell`, `check`, `migrate`,
`test`, `diffsettings`, `version`, `generatesecretkey`, `createsuperuser`,
`changepassword`, `clearsessions`, `worker`, `beat`.

## Writing a command

```python
# apps/blog/management/commands/publish_scheduled.py
from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "Publish posts whose scheduled date has passed"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        published = publish_scheduled(dry_run=options["dry_run"])
        self.stdout.write(self.style.SUCCESS(f"{published} posts published"))
```

`add_arguments` receives a plain `argparse.ArgumentParser` — everything
stdlib argparse supports works here. Useful attributes and helpers:

| Member | Purpose |
|---|---|
| `help` | One-liner shown by `ronnie help` |
| `missing_args_message` | Friendlier error for missing positionals |
| `requires_system_checks` | `"__all__"` (default), a tuple of tags, or `()` to skip checks |
| `requires_environment` | `True` (default) boots settings + apps before `handle` |
| `self.stdout` / `self.stderr` | Injectable writers — capture them in tests |
| `self.style.SUCCESS/ERROR/WARNING` | Colorized output helpers |

Raise `CommandError` to fail cleanly (message to stderr, exit code honored):

```python
from ronnie.core.exceptions import CommandError

raise CommandError("Nothing to publish", returncode=2)
```

### Command discovery and overriding

Built-ins are found first, then each installed app's
`management/commands/` directory. Apps **earlier** in `INSTALLED_APPS`
override later ones, so you can replace any built-in by shipping a command
with the same name and listing your app first.

## Calling commands from code

```python
from io import StringIO
from ronnie.core.management import call_command

out = StringIO()
call_command("publish_scheduled", "--dry-run", stdout=out)
```

Keyword arguments override parsed defaults, so options can be passed
programmatically without string round-trips.

## System checks

Checks are small functions that validate configuration and report problems
with stable IDs. `ronnie check` runs them; every command with
`requires_system_checks` runs them first and fails on errors.

```python
from ronnie.core.checks import Error, Warning, register


@register("blog", deploy=True)   # deploy=True: only with `ronnie check --deploy`
def check_api_key(deployment_checks: bool = False):
    from ronnie.conf import settings

    if not settings.BLOG_API_KEY:
        return [Warning("BLOG_API_KEY is empty.",
                        hint="Set it to enable publishing.",
                        id="blog.W001")]
    return []
```

Severity classes: `Debug`, `Info`, `Warning`, `Error`, `Critical`
(`Error` and above fail the run). Run with tag filters or deployment mode:

```bash
ronnie check --tag blog
ronnie check --deploy      # adds security hardening warnings
```

Make `ronnie check --deploy` part of your release pipeline — it flags an
empty `SECRET_KEY`, `DEBUG = True`, missing TLS redirects, HSTS and cookie
hardening before your users do.
