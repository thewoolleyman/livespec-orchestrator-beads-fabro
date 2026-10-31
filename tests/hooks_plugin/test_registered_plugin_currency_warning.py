"""Scenario 271 coverage for the registered-build SessionStart warning."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude-plugin" / "hooks"
_HOOK_PATH = _HOOKS_DIR / "registered_plugin_currency_warning.py"
_MODULE_NAME = "registered_plugin_currency_warning_under_test"


def _load_hook() -> ModuleType:
    assert _HOOK_PATH.is_file()
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def test_session_start_warns_but_succeeds_when_the_registered_build_is_stale(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The hook names both versions and must never block a session."""
    hook = _load_hook()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/executing-build")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/governed-project")
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setattr(
        hook,
        "registered_build_warning",
        lambda **_arguments: "WARNING: registered build 1.2.3 lags latest released version 1.2.4",
    )

    assert hook.main() == 0

    stderr = capsys.readouterr().err
    assert "registered build 1.2.3" in stderr
    assert "latest released version 1.2.4" in stderr


def test_hook_is_silent_when_its_currency_check_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SessionStart is fail-open when registry or marketplace state is unreadable."""
    hook = _load_hook()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/executing-build")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/governed-project")
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setattr(hook, "registered_build_warning", lambda **_arguments: None)

    assert hook.main() == 0

    assert capsys.readouterr().err == ""


def test_currency_check_forwards_only_a_successful_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = _load_hook()
    calls: list[list[str]] = []

    def run(*args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(args[0]))
        return subprocess.CompletedProcess(args[0], 0, "WARNING: 1.2.3 -> 1.2.4\n", "")

    monkeypatch.setattr(hook.subprocess, "run", run)

    assert (
        hook.registered_build_warning(
            plugin_root=Path("/executing-build"), project=Path("/governed-project")
        )
        == "WARNING: 1.2.3 -> 1.2.4"
    )

    assert calls == [
        [
            sys.executable,
            "/executing-build/scripts/bin/registered_plugin_currency.py",
            "--repo",
            "/governed-project",
        ]
    ]


def test_hook_skips_native_codex_without_reading_claude_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = _load_hook()
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)

    assert hook.main() == 0


def test_hook_is_silent_when_claude_did_not_supply_a_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = _load_hook()
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)

    assert hook.main() == 0


def test_hook_swallows_an_unavailable_currency_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = _load_hook()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/executing-build")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/governed-project")
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)

    def unavailable(**_arguments: object) -> str:
        raise OSError("unavailable")

    monkeypatch.setattr(hook, "registered_build_warning", unavailable)

    assert hook.main() == 0


def test_manifest_registers_the_claude_only_currency_hook() -> None:
    manifest = json.loads((_HOOKS_DIR / "hooks.json").read_text(encoding="utf-8"))
    commands = [entry["command"] for entry in manifest["hooks"]["SessionStart"][0]["hooks"]]

    assert any(
        command.startswith('if [ -n "${CODEX_THREAD_ID:-}" ]; then exit 0; fi; ')
        and command.endswith(
            'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/registered_plugin_currency_warning.py"'
        )
        for command in commands
    )
