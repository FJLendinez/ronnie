"""Management commands — a compact ``django.core.management``.

Commands are discovered in two layers:

1. built-ins shipped with Ronnie (``ronnie.core.management.commands``),
2. per-app commands in ``<app>/management/commands/*.py``.

Apps earlier in ``INSTALLED_APPS`` override later apps (and built-ins).

Write one::

    # <app>/management/commands/echo.py
    from ronnie.core.management import BaseCommand

    class Command(BaseCommand):
        help = "Echo a message"

        def add_arguments(self, parser):
            parser.add_argument("msg")

        def handle(self, *args, **options):
            self.stdout.write(self.style.SUCCESS(options["msg"]))

Then: ``python manage.py echo hello`` / ``ronnie echo hello``.
"""

from __future__ import annotations

import argparse
import importlib
import os
import pkgutil
import sys
from collections.abc import Callable
from typing import Any, ClassVar

from ... import __version__
from .. import checks as checks_module
from ..exceptions import AppRegistryNotReady, CommandError

__all__ = [
    "BaseCommand",
    "OutputWrapper",
    "Style",
    "call_command",
    "execute_from_command_line",
    "find_commands",
    "get_commands",
    "load_command_class",
    "main",
]

BUILTIN_COMMANDS_PACKAGE = "ronnie.core.management.commands"


# -- output helpers -----------------------------------------------------------------


def _supports_color(stream: Any) -> bool:
    return (
        hasattr(stream, "isatty")
        and stream.isatty()
        and os.environ.get("NO_COLOR") is None
        and sys.platform != "win32"
    )


class Style:
    """Colorized strings (ANSI), mirroring BaseCommand.style helpers."""

    RESET, RED, GREEN, YELLOW, MAGENTA, BOLD = (
        "\033[0m",
        "\033[31m",
        "\033[32m",
        "\033[33m",
        "\033[35m",
        "\033[1m",
    )

    def __init__(self, color: bool = True) -> None:
        self._color = color

    def _wrap(self, code: str, text: str) -> str:
        return f"{code}{text}{self.RESET}" if self._color else text

    def SUCCESS(self, msg: str) -> str:
        return self._wrap(self.GREEN, msg)

    def WARNING(self, msg: str) -> str:
        return self._wrap(self.YELLOW, msg)

    def ERROR(self, msg: str) -> str:
        return self._wrap(self.RED, msg)

    def NOTICE(self, msg: str) -> str:
        return self._wrap(self.MAGENTA, msg)

    def MIGRATE_HEADING(self, msg: str) -> str:
        return self._wrap(self.BOLD, msg)


class OutputWrapper:
    """A thin wrapper around a writable stream, injectable for tests."""

    def __init__(self, out: Any, style_func: Callable[[str], str] | None = None) -> None:
        self.out = out
        self.style_func = style_func

    def write(
        self, msg: str = "", *, style_func: Callable[[str], str] | None = None, ending: str = "\n"
    ) -> None:
        if ending and not msg.endswith(ending):
            msg += ending
        style_func = style_func or self.style_func
        self.out.write(style_func(msg) if style_func else msg)

    def flush(self) -> None:
        if hasattr(self.out, "flush"):
            self.out.flush()


# -- BaseCommand ---------------------------------------------------------------------


class CommandParser(argparse.ArgumentParser):
    """ArgumentParser that raises CommandError instead of calling sys.exit."""

    def __init__(self, *, missing_args_message: str | None = None, **kwargs: Any) -> None:
        self.missing_args_message = missing_args_message
        super().__init__(**kwargs)

    def error(self, message: str) -> None:  # type: ignore[override]
        if self.missing_args_message and not message:
            raise CommandError(self.missing_args_message)
        raise CommandError(f"Error: {message}", returncode=2)


class BaseCommand:
    """Base class for management commands (argparse-based, like Django's)."""

    help: str = ""
    missing_args_message: str = ""

    # "__all__" runs every registered check; a tuple restricts to tags; () skips.
    requires_system_checks: ClassVar[str | tuple[str, ...]] = "__all__"

    # False for commands that must run without settings/apps (startproject...).
    requires_environment = True

    def __init__(
        self, stdout: Any = None, stderr: Any = None, no_color: bool = False, force_color: bool = False
    ) -> None:
        color = force_color or (not no_color and _supports_color(stdout or sys.stdout))
        self.style = Style(color)
        self.stdout = OutputWrapper(stdout or sys.stdout)
        self.stderr = OutputWrapper(stderr or sys.stderr, self.style.ERROR)

    # -- parser -----------------------------------------------------------------

    def create_parser(self, prog_name: str, subcommand: str) -> argparse.ArgumentParser:
        parser = CommandParser(
            prog=f"{os.path.basename(prog_name)} {subcommand}",
            description=self.help or None,
            missing_args_message=self.missing_args_message or None,
        )
        parser.add_argument("--version", action="version", version=self.get_version())
        self.add_base_arguments(parser)
        self.add_arguments(parser)
        return parser

    def add_base_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-v",
            "--verbosity",
            default=1,
            type=int,
            choices=(0, 1, 2, 3),
            help="Verbosity level: 0=minimal, 2=verbose, 3=debug.",
        )
        parser.add_argument(
            "--traceback",
            action="store_true",
            help="Raise on CommandError instead of printing it.",
        )
        color_group = parser.add_mutually_exclusive_group()
        color_group.add_argument(
            "--no-color", dest="no_color", action="store_true", help="Don't colorize output."
        )
        color_group.add_argument(
            "--force-color", dest="force_color", action="store_true", help="Force colorized output."
        )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Override to add command-specific arguments (pure argparse)."""

    def get_version(self) -> str:
        return __version__

    # -- execution ----------------------------------------------------------------

    def run_from_argv(self, argv: list[str]) -> None:
        """argv is [prog_name, subcommand, *cli_args] (Django-compatible)."""
        parser = self.create_parser(argv[0], argv[1])
        options: dict[str, Any] = {}
        try:
            options = vars(parser.parse_args(argv[2:]))
            options.pop("version", None)
            # Rebuild honoring parsed color flags.
            self.stdout = OutputWrapper(getattr(self.stdout, "out", None) or sys.stdout)
            self.stderr = OutputWrapper(getattr(self.stderr, "out", None) or sys.stderr, self.style.ERROR)
            color = options.get("force_color", False) or (
                not options.get("no_color", False) and _supports_color(getattr(self.stdout, "out", None))
            )
            self.style = Style(color)
            self._called_from_command_line = True
            self.execute(*[], **options)
        except CommandError as err:
            if options.get("traceback"):
                raise
            self.stderr.write(f"CommandError: {err}")
            sys.exit(err.returncode)

    def execute(self, *args: Any, **options: Any) -> None:
        """Boot the environment if needed, run system checks, run the command."""
        if self.requires_environment:
            from ...apps import apps

            if not apps.ready:
                import ronnie

                ronnie.setup()
        if self.requires_system_checks:
            self.check(
                tags=None if self.requires_system_checks == "__all__" else list(self.requires_system_checks),
                deployment_checks=options.get("deploy", False),
            )
        output = self.handle(*args, **options)
        if output:
            self.stdout.write(output, style_func=None)

    def check(self, tags: list[str] | None = None, deployment_checks: bool = False) -> None:
        messages = checks_module.run_checks(tags=tags, include_deployment_checks=deployment_checks)
        if errors := checks_module.get_error_count(messages):
            for message in messages:
                if message.is_serious():
                    self.stderr.write(str(message))
            raise CommandError(f"System check identified {errors} error(s).")

    def handle(self, *args: Any, **options: Any) -> str | None:
        """The actual logic of the command. May return a string to print."""
        raise NotImplementedError("subclasses of BaseCommand must provide a handle() method")


# -- discovery ------------------------------------------------------------------------


def find_commands(management_dir: str) -> list[str]:
    """Return command names inside a ``management/commands`` directory."""
    try:
        return [name for _, name, _ in pkgutil.iter_modules([management_dir]) if not name.startswith("_")]
    except (ImportError, FileNotFoundError):
        return []


def get_commands() -> dict[str, str]:
    """Map command name → module dotted path.

    Built-ins first; app commands on top, with apps earlier in INSTALLED_APPS
    overriding later ones (matching Django).
    """
    commands = {
        name: f"{BUILTIN_COMMANDS_PACKAGE}.{name}"
        for name in find_commands(_package_dir(BUILTIN_COMMANDS_PACKAGE))
    }
    from ...apps import apps

    try:
        app_configs = list(apps.get_app_configs())
    except AppRegistryNotReady:
        return commands  # no environment booted (e.g. startproject)
    for app_config in reversed(app_configs):  # earlier apps win
        path = app_config.path
        if path is None:
            continue
        commands_dir = str(path / "management" / "commands")
        for name in find_commands(commands_dir):
            commands[name] = f"{app_config.name}.management.commands.{name}"
    return commands


def _package_dir(dotted: str) -> str:
    module = importlib.import_module(dotted)
    return str(module.__path__[0])


def load_command_class(module_path: str, name: str) -> BaseCommand:
    module = importlib.import_module(module_path)
    command_cls: type[BaseCommand] | None = getattr(module, "Command", None)
    if command_cls is None:
        raise CommandError(f"Command module {module_path!r} has no Command class.")
    return command_cls()


def call_command(name: str, *args: Any, stdout: Any = None, stderr: Any = None, **options: Any) -> str | None:
    """Call a command programmatically (Django-compatible core subset).

    Extra keyword arguments override parsed CLI defaults.
    """
    commands = get_commands()
    try:
        module_path = commands[name]
    except KeyError:
        raise CommandError(f"Unknown command: {name!r}") from None
    command = load_command_class(module_path, name)
    if stdout is not None or stderr is not None:
        command.stdout = OutputWrapper(stdout or sys.stdout)
        command.stderr = OutputWrapper(stderr or sys.stderr, command.style.ERROR)

    parser = command.create_parser("ronnie", name)
    defaults = vars(parser.parse_args(list(args)))
    defaults.pop("version", None)
    for key, value in options.items():
        if key not in defaults:
            raise TypeError(
                f"Unknown option {key!r} for command {name!r}. "
                f"Valid options: {sorted(k for k in defaults if not k.startswith('_'))}"
            )
        defaults[key] = value
    command.execute(**defaults)
    return None


# -- CLI entry points --------------------------------------------------------------------


class ManagementUtility:
    """Encapsulate the logic of the ``ronnie``/``manage.py`` CLI."""

    GLOBAL_FLAGS = ("--settings", "--pythonpath")  # extracted from anywhere in argv

    def __init__(self, argv: list[str] | None = None) -> None:
        self.argv = argv or sys.argv[:]
        self.prog_name = os.path.basename(self.argv[0]) if self.argv else "ronnie"

    def main_help_text(self) -> str:
        if not self._environment_ready():
            usage = "ronnie <command> [options]"
        else:
            usage = f"{self.prog_name} <command> [options]"
        commands = sorted(get_commands())
        lines = [
            f"Type '{usage} --help' for help on a specific command.",
            "",
            "Available commands:",
        ]
        lines += [f"  {name}" for name in commands]
        return "\n".join(lines)

    def _environment_ready(self) -> bool:
        from ...apps import apps

        return apps.ready

    def _preprocess_argv(self) -> tuple[list[str], dict[str, str]]:
        """Extract global flags (--settings/--pythonpath) from anywhere in argv."""
        rest: list[str] = []
        extracted: dict[str, str] = {}
        argv = self.argv[1:]
        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg in self.GLOBAL_FLAGS and i + 1 < len(argv):
                extracted[arg.lstrip("-")] = argv[i + 1]
                i += 2
                continue
            if "=" in arg and arg.split("=", 1)[0] in self.GLOBAL_FLAGS:
                key, _, value = arg.partition("=")
                extracted[key.lstrip("-")] = value
                i += 1
                continue
            rest.append(arg)
            i += 1
        return rest, extracted

    def execute(self) -> None:
        args, globals_ = self._preprocess_argv()

        if pythonpath := globals_.get("pythonpath"):
            sys.path.insert(0, pythonpath)
        if settings_flag := globals_.get("settings"):
            os.environ["RONNIE_SETTINGS_MODULE"] = settings_flag

        if not args:
            print(self.main_help_text())
            return
        subcommand = args[0]

        if subcommand == "--version":
            print(__version__)
            return
        if subcommand in ("-h", "--help", "help"):
            if len(args) > 1 and self._try_boot():
                self._print_command_help(args[1])
            else:
                print(self.main_help_text())
            return

        commands = get_commands()
        if subcommand not in commands and self._try_boot():
            commands = get_commands()

        if subcommand not in commands:
            if subcommand.startswith("-"):
                sys.stderr.write(self.main_help_text())
                sys.exit(2)
            from ..exceptions import ImproperlyConfigured

            try:
                self._boot_environment()
            except ImproperlyConfigured as err:
                sys.stderr.write(f"CommandError: {err}\n")
                sys.exit(1)
            sys.stderr.write(f"Unknown command: {subcommand!r}. Type '{self.prog_name} help' for usage.\n")
            sys.exit(1)

        command = load_command_class(commands[subcommand], subcommand)
        if command.requires_environment and not self._environment_ready():
            from ..exceptions import ImproperlyConfigured

            try:
                self._boot_environment()
            except ImproperlyConfigured as err:
                sys.stderr.write(f"CommandError: {err}\n")
                sys.exit(1)

        command.run_from_argv([self.prog_name, *args])

    def _try_boot(self) -> bool:
        """Try to boot the environment; return True on success."""
        from ..exceptions import ImproperlyConfigured

        try:
            self._boot_environment()
            return True
        except ImproperlyConfigured:
            return False

    def _boot_environment(self) -> None:
        import ronnie

        ronnie.setup()

    def _print_command_help(self, name: str) -> None:
        commands = get_commands()
        if name not in commands:
            sys.stderr.write(f"Unknown command: {name!r}\n")
            return
        command = load_command_class(commands[name], name)
        parser = command.create_parser(self.prog_name, name)
        parser.print_help()


def execute_from_command_line(argv: list[str] | None = None) -> None:
    ManagementUtility(argv).execute()


def main() -> None:
    execute_from_command_line()
