"""Tests for management commands, discovery and CLI (Fase 3)."""

from __future__ import annotations

from io import StringIO

import pytest

from ronnie import __version__
from ronnie.apps import apps as registry
from ronnie.core.exceptions import CommandError
from ronnie.core.management import (
    BaseCommand,
    call_command,
    execute_from_command_line,
    get_commands,
)


class TestCallCommand:
    def test_builtin_version(self):
        out = StringIO()
        call_command("version", stdout=out)
        assert __version__ in out.getvalue()

    def test_app_command_discovered(self):
        registry.populate(["apps.blog"])
        out = StringIO()
        call_command("echo", "hola", stdout=out)
        assert out.getvalue().strip() == "hola"

    def test_app_command_options(self):
        registry.populate(["apps.blog"])
        out = StringIO()
        call_command("echo", "hola", stdout=out, upper=True)
        assert out.getvalue().strip() == "HOLA"

    def test_unknown_command(self):
        with pytest.raises(CommandError, match="Unknown command"):
            call_command("nope")

    def test_unknown_option_typeerror(self):
        with pytest.raises(TypeError, match="Unknown option"):
            call_command("version", bogus=1)

    def test_earlier_apps_override_builtin(self):
        registry.populate(["apps.override"])  # apps.override defines `version`
        out = StringIO()
        call_command("version", stdout=out)
        assert out.getvalue().strip() == "OVERRIDDEN"


class TestGetCommands:
    def test_builtins_available_without_environment(self):
        commands = get_commands()
        assert "startproject" in commands
        assert "check" in commands

    def test_app_commands_available_when_populated(self):
        registry.populate(["apps.blog"])
        assert "echo" in get_commands()


class TestBaseCommand:
    def test_handle_not_implemented(self):
        class Cmd(BaseCommand):
            pass

        with pytest.raises(NotImplementedError):
            Cmd().handle()

    def test_command_error_returncode(self, capsys):
        class Failing(BaseCommand):
            def handle(self, *a, **kw):
                raise CommandError("boom", returncode=3)

        with pytest.raises(SystemExit) as exc:
            Failing().run_from_argv(["ronnie", "failing"])
        assert exc.value.code == 3

    def test_parser_has_base_options(self):
        parser = BaseCommand().create_parser("ronnie", "x")
        args = parser.parse_args(["--verbosity", "2"])
        assert args.verbosity == 2


class TestStartProject:
    def test_creates_expected_files(self, tmp_path):
        out = StringIO()
        call_command("startproject", "demo", str(tmp_path), stdout=out)
        root = tmp_path / "demo"
        for rel in (
            "manage.py",
            "config/__init__.py",
            "config/settings.py",
            "config/asgi.py",
            "apps/__init__.py",
        ):
            assert (root / rel).is_file(), rel

    def test_generated_settings_compile_and_have_secret(self, tmp_path):
        call_command("startproject", "demo", str(tmp_path), stdout=StringIO())
        settings_py = (tmp_path / "demo" / "config" / "settings.py").read_text()
        compile(settings_py, "settings.py", "exec")
        assert 'SECRET_KEY = "' in settings_py
        assert len(settings_py.split('SECRET_KEY = "')[1].split('"')[0]) == 50
        manage_py = (tmp_path / "demo" / "manage.py").read_text()
        assert "demo.config.settings" in manage_py

    def test_refuses_existing_directory(self, tmp_path):
        (tmp_path / "demo").mkdir()
        (tmp_path / "demo" / "x.txt").write_text("x")
        with pytest.raises(CommandError, match="already exists"):
            call_command("startproject", "demo", str(tmp_path))

    def test_rejects_invalid_name(self, tmp_path):
        with pytest.raises(CommandError, match="valid project name"):
            call_command("startproject", "not-valid", str(tmp_path))


class TestStartApp:
    def test_creates_app_under_apps_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "apps").mkdir()
        call_command("startapp", "blog", stdout=StringIO())
        root = tmp_path / "apps" / "blog"
        assert (root / "routes.py").is_file()
        apps_py = (root / "apps.py").read_text()
        assert 'name = "apps.blog"' in apps_py
        assert "class BlogConfig(AppConfig):" in apps_py

    def test_creates_app_in_cwd_without_apps_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        call_command("startapp", "user_auth", stdout=StringIO())
        apps_py = (tmp_path / "user_auth" / "apps.py").read_text()
        assert 'name = "user_auth"' in apps_py
        assert "class UserAuthConfig(AppConfig):" in apps_py


class TestCLI:
    def test_version_flag(self, capsys):
        execute_from_command_line(["ronnie", "--version"])
        assert __version__ in capsys.readouterr().out

    def test_unknown_command_exits_nonzero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            execute_from_command_line(["ronnie", "definitely-not-a-command"])
        assert exc.value.code == 1

    def test_no_args_prints_help(self, capsys):
        execute_from_command_line(["ronnie"])
        assert "Available commands:" in capsys.readouterr().out

    def test_settings_flag_used_by_command(self, capsys):
        # `ronnie diffsettings --settings sample_settings` boots the module env
        execute_from_command_line(["ronnie", "diffsettings", "--settings", "sample_settings"])
        out = capsys.readouterr().out
        assert "DEBUG" in out

    def test_help_subcommand(self, capsys):
        execute_from_command_line(["ronnie", "help"])
        assert "Available commands:" in capsys.readouterr().out


class TestChecks:
    def test_check_passes_with_settings(self, monkeypatch):
        from ronnie.conf import settings

        settings.configure(SECRET_KEY="abc", DEBUG=False)
        out = StringIO()
        call_command("check", stdout=out)
        assert "no issues" in out.getvalue()

    def test_check_deploy_flags_empty_secret(self):
        from ronnie.conf import settings

        settings.configure(SECRET_KEY="", DEBUG=False)
        out = StringIO()
        with pytest.raises(CommandError, match="1 error"):
            call_command("check", "--deploy", stdout=out, stderr=out)
        assert "settings.E001" in out.getvalue()

    def test_check_deploy_flags_debug_true(self):
        from ronnie.conf import settings

        settings.configure(SECRET_KEY="x", DEBUG=True)
        out = StringIO()
        with pytest.raises(CommandError, match="1 error"):
            call_command("check", "--deploy", stdout=out, stderr=out)
        assert "settings.E002" in out.getvalue()

    def test_check_reports_warning_without_deploy(self):
        from ronnie.conf import settings

        settings.configure(SECRET_KEY="", DEBUG=False)
        out = StringIO()
        call_command("check", stdout=out)
        assert "settings.W001" in out.getvalue()

    def test_check_tag_filter(self):
        from ronnie.conf import settings

        settings.configure(SECRET_KEY="", DEBUG=False)
        out = StringIO()
        call_command("check", "--tag", "nope", stdout=out)
        assert "settings.W001" not in out.getvalue()
