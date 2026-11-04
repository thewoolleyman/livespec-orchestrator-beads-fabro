"""Shared HTTP projection adapter for legacy command-runner test doubles.

The affected dispatcher tests model a successful or failed legacy dump through
their runner doubles.  Preserve-by-reference now reads the server projection,
so this adapter expresses the same fixture facts at the HTTP boundary.  Tests
that need a distinct projection install their own narrower replacement.
"""

from __future__ import annotations

from typing import Protocol

import pytest
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import (
    FabroHttpPort,
    FabroHttpResult,
)

_LEGACY_DUMP_MODULES = frozenset(
    {
        "test_dispatcher_preserve_reference_edges",
        "test_dispatcher_reconcile_runs",
        "test_dispatcher_reconcile_runs_container_sweep",
        "test_dispatcher_reconcile_runs_export",
        "test_dispatcher_reconcile_supersession",
        "test_dispatcher_run_reconcile_hook",
        "test_dispatcher_run_wall_budget_held",
        "test_dispatcher_run_wall_budget_launcher",
        "test_dispatcher_run_wall_budget_watch",
        "test_dispatcher_run_wall_budget_terminal",
    }
)
_DEFAULT_DIFF = "diff --git a/app.py b/app.py\n+print('kept')\n"


class _StateApi(Protocol):
    def run_state(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult: ...

    def bearer_token(self) -> str | None: ...


class _LegacyStateApi:
    def __init__(self, *, result: FabroHttpResult, fallback: FabroHttpPort) -> None:
        self._result = result
        self._fallback = fallback

    def run_state(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult:
        _ = (run_id, timeout_seconds)
        return self._result

    def bearer_token(self) -> str | None:
        return self._fallback.bearer_token()

    def questions(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult:
        return self._fallback.questions(run_id=run_id, timeout_seconds=timeout_seconds)

    def answer_question(
        self, *, run_id: str, question_id: str, option_key: str, timeout_seconds: float
    ) -> FabroHttpResult:
        return self._fallback.answer_question(
            run_id=run_id,
            question_id=question_id,
            option_key=option_key,
            timeout_seconds=timeout_seconds,
        )

    def cancel(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult:
        return self._fallback.cancel(run_id=run_id, timeout_seconds=timeout_seconds)


@pytest.fixture(autouse=True)
def legacy_dump_runner_serves_run_state(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Adapt old runner-double export facts to the new state endpoint."""
    if (
        request.module is None
        or request.module.__name__.rsplit(".", 1)[-1] not in _LEGACY_DUMP_MODULES
    ):
        return

    monkeypatch.setattr(
        FabroPort,
        "server_api",
        lambda port: _legacy_state_api(port=port, module=request.module),
    )


def _legacy_state_api(*, port: FabroPort, module: object) -> _StateApi:
    fallback = FabroHttpPort(target=port.target, transport=port.http)
    runner = port.runner
    if "Permission" in type(runner).__name__:
        raise PermissionError("artifact is unreadable")
    _stamp_during_legacy_export(runner=runner, module=module)
    if _legacy_failure_code(runner=runner) != 0:
        return _LegacyStateApi(result=_failed_state_result(), fallback=fallback)
    return _LegacyStateApi(result=_successful_state_result(runner=runner), fallback=fallback)


def _stamp_during_legacy_export(*, runner: object, module: object) -> None:
    stamp_on_dump = getattr(runner, "stamp_on_dump", None)
    append_stamps = getattr(module, "_append_stamps", None)
    if isinstance(stamp_on_dump, tuple) and len(stamp_on_dump) == 2 and callable(append_stamps):
        append_stamps(path=stamp_on_dump[0], run_ids=[stamp_on_dump[1]])


def _legacy_failure_code(*, runner: object) -> int:
    if "Failing" in type(runner).__name__:
        return 1
    code = getattr(runner, "dump_exit_code", getattr(runner, "exit_code", 0))
    return code if isinstance(code, int) else 0


def _failed_state_result() -> FabroHttpResult:
    return FabroHttpResult(
        status=500,
        body="fixture run storage not found",
        error=None,
        payload=None,
        succeeded=False,
    )


def _successful_state_result(*, runner: object) -> FabroHttpResult:
    configured = getattr(runner, "stage_diffs", None)
    stage_diffs = configured if isinstance(configured, dict) else {"002-implement@1": _DEFAULT_DIFF}
    stages = {
        _stage_name(path=path): {"first_event_seq": _stage_sequence(path=path), "diff": diff}
        for path, diff in stage_diffs.items()
        if isinstance(path, str) and isinstance(diff, str)
    }
    return FabroHttpResult(
        status=200, body="", error=None, payload={"stages": stages}, succeeded=True
    )


def _stage_name(*, path: str) -> str:
    return path[4:] if path[:3].isdigit() and path[3:4] == "-" else path


def _stage_sequence(*, path: str) -> int:
    return int(path[:3]) if path[:3].isdigit() else 1
