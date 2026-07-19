"""Coverage for the PreToolUse beads-access guard hook.

The guard blocks a bare `bd` / `dolt` / direct-tenant `mysql` invocation unless
the command runs under a recognized per-project credential-injection env wrapper
(`with-<id>-env.sh`), turning the silent "ran outside the wrapper -> tenant auth
failure" footgun into an actionable deny that names the wrapper.

Both halves of the contract matter and are covered here: the POSITIVE matches
(what must be blocked) and — more importantly — the fail-open arms, since a hook
that blocks the wrong thing, or raises, wedges every Bash call in the session.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_PATH = _REPO_ROOT / ".claude" / "hooks" / "beads_access_guard.py"
_MODULE_NAME = "beads_access_guard_under_test"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


guard = _load_hook()


def _run_main(*, payload: object, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    return guard.main()


@pytest.mark.parametrize(
    "command",
    [
        "bd list",
        "bd",
        "dolt sql -q 'select 1'",
        "echo hi && bd show x",
        "(bd ready)",
        "$(bd list)",
    ],
)
def test_should_block_an_unwrapped_bd_or_dolt_invocation(command: str) -> None:
    assert guard.should_block(command=command) is True


@pytest.mark.parametrize(
    "command",
    [
        "mysql -h 127.0.0.1 -P 3307 -u user",
        "mysql --port=3307",
    ],
)
def test_should_block_mysql_only_when_aimed_at_the_tenant_endpoint(command: str) -> None:
    assert guard.should_block(command=command) is True


def test_should_not_block_mysql_without_a_tenant_endpoint_hint() -> None:
    assert guard.should_block(command="mysql --help") is False


@pytest.mark.parametrize(
    "command",
    [
        "with-livespec-env.sh -- bd list",
        "/data/projects/1password-env-wrapper/with-livespec-env.sh -- dolt sql",
        "with-some-project-env.sh -- mysql -h 127.0.0.1 -P 3307",
    ],
)
def test_should_not_block_a_command_running_under_an_env_wrapper(command: str) -> None:
    assert guard.should_block(command=command) is False


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m 'bd-ib-1jye.1 done'",
        "echo embedded-bd-in-a-word",
        "grep -rn beads .",
        "",
    ],
)
def test_should_not_block_unrelated_commands_that_merely_mention_the_tools(command: str) -> None:
    assert guard.should_block(command=command) is False


def test_main_emits_a_deny_decision_for_an_unwrapped_invocation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": "bd list"}}

    assert _run_main(payload=payload, monkeypatch=monkeypatch) == 0

    emitted = json.loads(capsys.readouterr().out)
    assert emitted["decision"] == "block"
    hook_output = emitted["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    # The deny must NAME the remedy, not merely refuse.
    assert "with-<project>-env.sh" in hook_output["permissionDecisionReason"]


def test_main_passes_through_a_wrapped_invocation_silently(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": "with-livespec-env.sh -- bd list"}}

    assert _run_main(payload=payload, monkeypatch=monkeypatch) == 0

    assert capsys.readouterr().out == ""


def test_main_fails_open_on_malformed_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json at all"))

    assert guard.main() == 0

    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(["not", "a", "dict"], id="payload-is-not-a-mapping"),
        pytest.param({"tool_name": "Bash"}, id="tool_input-missing"),
        pytest.param({"tool_input": "not-a-dict"}, id="tool_input-is-not-a-mapping"),
        pytest.param({"tool_input": {"command": 42}}, id="command-is-not-a-string"),
        pytest.param({"tool_input": {}}, id="command-missing"),
        pytest.param({"tool_input": {"command": ""}}, id="command-empty"),
    ],
)
def test_main_fails_open_on_any_unexpected_payload_shape(
    payload: object, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_main(payload=payload, monkeypatch=monkeypatch) == 0

    assert capsys.readouterr().out == ""
