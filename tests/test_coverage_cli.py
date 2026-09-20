"""Coverage batch 1: CLI, commands, settings branches, exceptions, signals."""

from __future__ import annotations

import pytest

from ronnie import __version__, conf
from ronnie.core.exceptions import (
    AppRegistryNotReady,
    CommandError,
    ImproperlyConfigured,
    PermissionDenied,
    RonnieException,
    ValidationError,
)
from ronnie.core.management import (
    BaseCommand,
    OutputWrapper,
    Style,
    call_command,
    execute_from_command_line,
    find_commands,
    get_commands,
    load_command_class,
)
from ronnie.core.signals import Signal


class TestExceptions:
    def test_hierarchy_and_str(self):
        assert issubclass(ImproperlyConfigured, RonnieException)
        assert issubclass(CommandError, RonnieException)
        assert issubclass(PermissionDenied, RonnieException)
        assert str(CommandError("boom")) == "boom"
        assert str(ValidationError(["a", "b"])) == "a; b"
        assert ValidationError("solo").messages == ["solo"]
        assert str(AppRegistryNotReady("nope")) == "nope"

    def test_command_error_returncode(self):
        assert CommandError("x", returncode=7).returncode == 7


class TestConfBranches:
    def test_holder_lowercase_attributeerror(self):
        holder = conf.UserSettingsHolder(conf.global_settings)
        with pytest.raises(AttributeError, match="not defined"):
            _ = holder.not_upper

    def test_settings_module_on_holder_is_empty(self):
        conf.settings.configure(DEBUG=True)
        assert conf.settings.SETTINGS_MODULE == ""

    def test_repr_after_configure(self):
        conf.settings.configure(DEBUG=True)
        assert "(configured)" in repr(conf.settings)

    def test_delattr_removes_setting(self):
        conf.settings.configure(DEBUG=True, EXTRA=1)
        assert conf.settings.EXTRA == 1
        del conf.settings.EXTRA
        with pytest.raises(AttributeError):
            _ = conf.settings.EXTRA

    def test_delattr_wrapped_guard(self):
        conf.settings.configure(DEBUG=True)
        with pytest.raises(TypeError, match="_wrapped"):
            del conf.settings._wrapped

    def test_private_getattr_raises(self):
        conf.settings.configure(DEBUG=True)
        with pytest.raises(AttributeError):
            _ = conf.settings._hidden_thing

    def test_module_import_error_propagates(self, monkeypatch):
        monkeypatch.setenv(conf.SETTINGS_MODULE_ENV, "definitely_missing_module")
        with pytest.raises(ModuleNotFoundError):
            _ = conf.settings.DEBUG


class TestSignalsExtra:
    def test_disconnect_by_receiver_identity(self):
        sig, calls = Signal(), []
        receiver = _make_receiver(calls, "x")
        sig.connect(receiver, weak=False)
        sig.disconnect(receiver)
        sig.send()
        assert calls == []
        # disconnecting something never connected is a no-op
        assert sig.disconnect(lambda **kw: None) is False

    def test_disconnect_without_key(self):
        assert Signal().disconnect() is False

    def test_not_weakrefable_falls_back_to_strong(self):
        sig = Signal()
        calls: list[str] = []

        class NotWeakrefable:
            __slots__ = ()

            def __call__(self, sender, **kw) -> None:
                calls.append("called")

        instance = NotWeakrefable()
        sig.connect(instance)  # slotted instance can't be weak-referenced
        sig.send()
        assert calls == ["called"]

    def test_send_with_no_receivers(self):
        assert Signal().send() == []


def _make_receiver(calls: list, value: str):
    def receiver(sender, **kw) -> None:
        calls.append(value)

    return receiver


class TestManagementInternals:
    def test_find_commands_missing_dir(self):
        assert find_commands("/definitely/not/here") == []

    def test_load_command_class_without_command(self):
        import types

        module = types.ModuleType("ronnie.core.management.commands.fake")
        import sys

        sys.modules[module.__name__] = module
        try:
            with pytest.raises(CommandError, match="no Command class"):
                load_command_class(module.__name__, "fake")
        finally:
            del sys.modules[module.__name__]

    def test_output_wrapper_flush_and_style(self):
        import io

        out = io.StringIO()
        wrapper = OutputWrapper(out, Style(color=False).SUCCESS)
        wrapper.write("hi", ending="")
        assert out.getvalue() == "hi"
        wrapper.flush()  # no-op passthrough
        style = Style(color=True)
        assert "\033[32m" in style.SUCCESS("ok")
        assert style.ERROR("e").startswith("\033[31m")

    def test_call_command_injects_stderr(self, capsys):
        out, err = __import__("io").StringIO(), __import__("io").StringIO()
        call_command("version", stdout=out, stderr=err)
        assert __version__ in out.getvalue()

    def test_base_command_parser_missing_args_message(self):
        class NeedsArg(BaseCommand):
            requires_environment = False
            missing_args_message = "give me a name"

            def add_arguments(self, parser):
                parser.add_argument("name")

        with pytest.raises(SystemExit):
            NeedsArg().run_from_argv(["ronnie", "needsarg"])

    def test_base_command_check_errors_exit(self, monkeypatch):
        from ronnie.core import checks as checks_module

        @checks_module.register("cov")
        def _failing(deployment_checks: bool = False) -> list:
            return [checks_module.Error("broken", id="cov.E001")]

        class Checked(BaseCommand):
            requires_environment = False

            def handle(self, *a, **kw):
                return "never"

        with pytest.raises(CommandError, match="1 error"):
            Checked().execute()

    def test_get_commands_builtins_list(self):
        commands = get_commands()
        for expected in (
            "startproject",
            "startapp",
            "check",
            "migrate",
            "test",
            "shell",
            "runserver",
            "worker",
            "beat",
            "version",
            "diffsettings",
            "generatesecretkey",
        ):
            assert expected in commands, expected


class TestCLIBranches:
    def test_help_of_specific_command(self, capsys):
        conf.settings.configure(SECRET_KEY="k")
        execute_from_command_line(["ronnie", "help", "check"])
        out = capsys.readouterr().out
        assert "--deploy" in out

    def test_help_of_unknown_command(self, capsys):
        conf.settings.configure(SECRET_KEY="k")
        execute_from_command_line(["ronnie", "help", "no-such-thing"])
        assert "Unknown command" in capsys.readouterr().err

    def test_flag_like_subcommand_prints_help_and_exits(self, capsys):
        with pytest.raises(SystemExit) as exc:
            execute_from_command_line(["ronnie", "--bogus-flag"])
        assert exc.value.code == 2

    def test_settings_pythonpath_flags_extracted(self, monkeypatch, capsys):
        import sys

        original = list(sys.path)
        monkeypatch.setattr(sys, "path", [*original])  # a copy we can inspect
        execute_from_command_line(
            ["ronnie", "--pythonpath=/tmp", "diffsettings", "--settings=sample_settings"]
        )
        assert any(p.endswith("/tmp") for p in __import__("sys").path)
        assert "DEBUG" in capsys.readouterr().out

    def test_unknown_command_without_settings_prints_error(self, monkeypatch, capsys):
        monkeypatch.delenv(conf.SETTINGS_MODULE_ENV, raising=False)
        with pytest.raises(SystemExit) as exc:
            execute_from_command_line(["ronnie", "migrate"])
        assert exc.value.code == 1
        assert "CommandError" in capsys.readouterr().err


class TestCommandsWithSideEffects:
    @pytest.fixture(autouse=True)
    def _configured(self):
        conf.settings.configure(SECRET_KEY="k")

    def test_generatesecretkey(self):
        import io

        out = io.StringIO()
        call_command("generatesecretkey", stdout=out)
        key = out.getvalue().strip()
        assert len(key) == 50

    def test_diffsettings_only_defaults(self):
        import io

        conf.settings.SECRET_KEY = ""  # match the global default exactly
        out = io.StringIO()
        call_command("diffsettings", stdout=out)
        assert out.getvalue() == ""

    def test_shell_command_exec(self, monkeypatch):
        import importlib

        importlib.import_module("ronnie.core.management.commands.shell")  # warm cache
        executed: list[str] = []
        monkeypatch.setattr("builtins.exec", lambda code, ns: executed.append(code))
        call_command("shell", command="print('hi')")
        assert executed == ["print('hi')"]

    def test_shell_command_ipython_branch(self, monkeypatch):
        import sys
        import types

        fake = types.ModuleType("IPython")
        fake.start_ipython = lambda argv=None: None
        monkeypatch.setitem(sys.modules, "IPython", fake)
        call_command("shell")  # takes the IPython branch

    def test_shell_command_plain_python(self, monkeypatch):
        monkeypatch.setitem(__import__("sys").modules, "IPython", None)
        called = {"n": 0}

        class FakeInteract:
            def __call__(self, *a, **kw):
                called["n"] += 1

        import code as code_module

        monkeypatch.setattr(code_module, "interact", FakeInteract())
        call_command("shell", interface="python")
        assert called["n"] == 1

    def test_runserver_addrport_parsing(self, tmp_path):
        from ronnie.core.management.commands import runserver as rs

        command = rs.Command()
        assert command._parse_addrport(None) == ("127.0.0.1", 8000)
        assert command._parse_addrport("9000") == ("127.0.0.1", 9000)
        assert command._parse_addrport("0.0.0.0:8080") == ("0.0.0.0", 8080)
        with pytest.raises(CommandError, match="Invalid port"):
            command._parse_addrport("notaport")

    def test_runserver_asgi_path_and_launch(self, monkeypatch):
        from ronnie.core.management.commands import runserver as rs

        conf.settings.SETTINGS_MODULE = "sample_project.config"
        command = rs.Command()
        assert command._asgi_app_path() == "sample_project.asgi:application"

        launched: dict = {}
        monkeypatch.setattr("uvicorn.run", lambda *a, **kw: launched.update(args=a, kw=kw))
        command.execute(verbosity=0, addrport="127.0.0.1:9111", noreload=True)
        assert launched["args"] == ("sample_project.asgi:application",)
        assert launched["kw"]["port"] == 9111
        assert launched["kw"]["reload"] is False

    def test_runserver_requires_settings(self):
        from ronnie.core.management.commands import runserver as rs

        command = rs.Command()
        with pytest.raises(CommandError, match="SETTINGS_MODULE"):
            command._asgi_app_path()

    def test_migrate_without_migrations_message(self, tmp_path):
        import io

        conf.settings.INSTALLED_APPS = ["apps.news"]
        conf.settings.DATABASES = {"default": {"ENGINE": "sqlite", "NAME": tmp_path / "none.db"}}
        import ronnie
        from ronnie.apps import apps

        apps.clear_data()
        ronnie.setup()
        out = io.StringIO()
        call_command("migrate", stdout=out)
        assert "No migrations found" in out.getvalue()

    def test_check_command_writes_messages(self, monkeypatch):
        import io

        from ronnie.core import checks as checks_module

        conf.settings.DEBUG = False

        @checks_module.register("cov2")
        def _warn(deployment_checks: bool = False) -> list:
            return [checks_module.Warning("heads up", id="cov2.W001")]

        out = io.StringIO()
        call_command("check", stdout=out)
        assert "cov2.W001" in out.getvalue()

    def test_startproject_with_directory_argument(self, tmp_path):
        import io

        out = io.StringIO()
        call_command("startproject", "nested", str(tmp_path), stdout=out)
        assert (tmp_path / "nested" / "manage.py").is_file()

    def test_startapp_with_directory_argument(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "apps").mkdir()
        import io

        out = io.StringIO()
        call_command("startapp", "billing", "apps", stdout=out)
        assert (tmp_path / "apps" / "billing" / "apps.py").is_file()
        assert "apps.billing" in out.getvalue()
