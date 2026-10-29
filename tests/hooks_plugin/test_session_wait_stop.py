"""Coverage for the Claude Stop hook that runs the host session-wait check.

Scenario 158 requires the turn-end check to expose an ended unacknowledged
target and unfinished authorized work before the owning session finishes its
turn. The Claude runtime has a Stop hook surface, so the plugin registers one
that runs the shared `session_wait.py check` command and blocks the stop once
when it reports findings. Codex and pi are not covered by it.

The module is loaded by file location because `.claude-plugin/hooks/` is not a
package. Nothing here spawns a subprocess: the one `subprocess.run` call is
replaced on the module under test.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude-plugin" / "hooks"
_HOOK_PATH = _HOOKS_DIR / "session_wait_stop.py"
_MODULE_NAME = "session_wait_stop_under_test"

_FINDINGS_OUTPUT = json.dumps(
    {
        "summary": {
            "findings": [
                {
                    "finding": "ended-unacknowledged",
                    "id": "wait-1",
                    "record_state": "available",
                    "source": "wait",
                },
                {
                    "finding": "unmonitored",
                    "id": "op-1",
                    "record_state": "available",
                    "source": "obligation",
                },
            ],
            "healthy": False,
        }
    }
)


def _load_hook() -> ModuleType:
    assert _HOOK_PATH.is_file()
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _environment(*, monkeypatch: pytest.MonkeyPatch, stdin: str = "{}") -> None:
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/plugin")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/project")
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))


def _record_runs(
    *, hook: ModuleType, monkeypatch: pytest.MonkeyPatch, outcome: object
) -> list[list[str]]:
    commands: list[list[str]] = []

    def run_check(*, command: list[str], timeout_seconds: float) -> object:
        assert timeout_seconds > 0
        commands.append(command)
        return outcome

    monkeypatch.setattr(hook, "run_check", run_check)
    return commands


def test_manifest_registers_the_stop_hook_behind_the_codex_guard() -> None:
    manifest = json.loads((_HOOKS_DIR / "hooks.json").read_text())

    stop = manifest["hooks"].get("Stop")

    assert stop is not None
    command = stop[0]["hooks"][0]["command"]
    assert command.startswith('if [ -n "${CODEX_THREAD_ID:-}" ]; then exit 0; fi; ')
    assert command.endswith('python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session_wait_stop.py"')
    assert stop[0]["hooks"][0]["timeout"] >= 30


def test_check_command_runs_the_shared_check_against_the_project() -> None:
    hook = _load_hook()

    command = hook.check_command(plugin_root=Path("/plugin"), project=Path("/project"))

    assert command == [
        sys.executable,
        "/plugin/scripts/bin/session_wait.py",
        "check",
        "--repo",
        "/project",
    ]


def test_a_clean_check_lets_the_turn_end(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hook = _load_hook()
    _environment(monkeypatch=monkeypatch)
    commands = _record_runs(
        hook=hook, monkeypatch=monkeypatch, outcome=hook.CheckOutcome(returncode=0, stdout="{}")
    )

    assert hook.main() == 0

    assert len(commands) == 1
    assert capsys.readouterr().out == ""


def test_findings_block_the_stop_and_name_each_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hook = _load_hook()
    _environment(monkeypatch=monkeypatch)
    _ = _record_runs(
        hook=hook,
        monkeypatch=monkeypatch,
        outcome=hook.CheckOutcome(returncode=1, stdout=_FINDINGS_OUTPUT),
    )

    assert hook.main() == 0

    decision = json.loads(capsys.readouterr().out)
    assert decision["decision"] == "block"
    reason = decision["reason"]
    assert "wait-1: ended-unacknowledged" in reason
    assert "op-1: unmonitored" in reason
    assert "ack" in reason


@pytest.mark.parametrize(
    "outcome_factory",
    [
        lambda _hook: None,
        lambda hook: hook.CheckOutcome(returncode=2, stdout=""),
        lambda hook: hook.CheckOutcome(returncode=1, stdout="not json"),
        lambda hook: hook.CheckOutcome(returncode=1, stdout=json.dumps({"summary": []})),
    ],
)
def test_an_unavailable_check_blocks_once_instead_of_reading_as_healthy(
    outcome_factory: object, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hook = _load_hook()
    _environment(monkeypatch=monkeypatch)
    _ = _record_runs(hook=hook, monkeypatch=monkeypatch, outcome=outcome_factory(hook))  # type: ignore[operator]

    assert hook.main() == 0

    decision = json.loads(capsys.readouterr().out)
    assert decision["decision"] == "block"
    assert "unavailable" in decision["reason"]


@pytest.mark.parametrize("stdin", ['{"stop_hook_active": true}'])
def test_a_continued_stop_is_never_blocked_twice(
    stdin: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hook = _load_hook()
    _environment(monkeypatch=monkeypatch, stdin=stdin)
    commands = _record_runs(hook=hook, monkeypatch=monkeypatch, outcome=None)

    assert hook.main() == 0

    assert commands == []
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("stdin", ["not json", "[]", ""])
def test_unreadable_hook_input_still_runs_the_check(
    stdin: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hook = _load_hook()
    _environment(monkeypatch=monkeypatch, stdin=stdin)
    commands = _record_runs(
        hook=hook, monkeypatch=monkeypatch, outcome=hook.CheckOutcome(returncode=0, stdout="{}")
    )

    assert hook.main() == 0

    assert len(commands) == 1
    assert capsys.readouterr().out == ""


def test_native_codex_and_unresolved_environment_are_inert(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hook = _load_hook()
    commands = _record_runs(hook=hook, monkeypatch=monkeypatch, outcome=None)

    _environment(monkeypatch=monkeypatch)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread")
    assert hook.main() == 0

    _environment(monkeypatch=monkeypatch)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR")
    assert hook.main() == 0

    _environment(monkeypatch=monkeypatch)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT")
    assert hook.main() == 0

    assert commands == []
    assert capsys.readouterr().out == ""


def test_run_check_reports_the_exit_status_and_output(monkeypatch: pytest.MonkeyPatch) -> None:
    hook = _load_hook()
    seen: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen["command"] = command
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 1, stdout="out", stderr="")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    outcome = hook.run_check(command=["check"], timeout_seconds=12.0)

    assert outcome == hook.CheckOutcome(returncode=1, stdout="out")
    kwargs = seen["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["timeout"] == 12.0
    assert kwargs["stdin"] == subprocess.DEVNULL


@pytest.mark.parametrize("failure", [OSError("no interpreter"), subprocess.TimeoutExpired("c", 1)])
def test_run_check_reports_a_check_that_could_not_run_as_none(
    failure: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook = _load_hook()

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del command, kwargs
        raise failure

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.run_check(command=["check"], timeout_seconds=1.0) is None
