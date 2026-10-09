"""Tests for the orphan-run termination routes and their fallback order."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs_terminate as term
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroTarget

# Recorded verbatim from hp (https://hp-xubuntu.perch-rudd.ts.net:32276) on
# 2026-08-30 against parked run 01M19HK2WMTSSGMT96HWNF0WKP: the envelope keys
# its listing `data`, and each option carries a `key` beside its `label`.
_QUESTIONS_BODY = json.dumps(
    {
        "data": [
            {
                "id": "q-7",
                "allow_freeform": False,
                "options": [
                    {"key": "R", "label": "[R] Retry the fix"},
                    {"key": "I", "label": "[I] Re-implement from scratch"},
                    {"key": "A", "label": "[A] Abandon (leave open for triage)"},
                ],
                "question_type": "multiple_choice",
                "stage": "escalate",
                "text": "The fix did not converge. What next?",
            }
        ],
        "meta": {"has_more": False},
    }
)


@dataclass(kw_only=True)
class _FakeTransport:
    results: dict[str, FabroHttpResult]
    calls: list[tuple[str, str]] = field(default_factory=list)
    bodies: list[bytes | None] = field(default_factory=list)

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = (headers, timeout_seconds)
        self.calls.append((method, url))
        self.bodies.append(body)
        route = url.rsplit("/runs/", maxsplit=1)[-1]
        return self.results.get(route, _failed())


@dataclass(kw_only=True)
class _FakeRunner:
    rm_exit_code: int = 0
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return CommandResult(exit_code=self.rm_exit_code, stdout="", stderr="")


def test_a_blocked_orphan_is_abandoned_through_the_answer_route(tmp_path: Path) -> None:
    transport = _FakeTransport(
        results={
            "01BLOCKED/questions": _ok(body=_QUESTIONS_BODY),
            "01BLOCKED/questions/q-7/answer": _ok(body="{}"),
        }
    )
    runner = _FakeRunner()

    outcome = term.terminate_orphan_run(
        port=_port(tmp_path=tmp_path, transport=transport, runner=runner),
        run_id="01BLOCKED",
        status_kind="blocked",
    )

    assert outcome.route == term.TERMINATION_ROUTE_ANSWER
    assert outcome.succeeded is True
    assert "[A] Abandon (leave open for triage)" in outcome.detail
    assert transport.calls == [
        ("GET", "https://hp.example:32276/api/v1/runs/01BLOCKED/questions"),
        ("POST", "https://hp.example:32276/api/v1/runs/01BLOCKED/questions/q-7/answer"),
    ]
    assert transport.bodies[1] == json.dumps(
        {"kind": "selected", "option_key": "A"}, sort_keys=True
    ).encode("utf-8")
    assert runner.calls == []


def test_a_running_orphan_is_terminated_through_the_cancel_route(tmp_path: Path) -> None:
    transport = _FakeTransport(results={"01RUNNING/cancel": _ok(body="{}")})
    runner = _FakeRunner()

    outcome = term.terminate_orphan_run(
        port=_port(tmp_path=tmp_path, transport=transport, runner=runner),
        run_id="01RUNNING",
        status_kind="running",
    )

    assert outcome.route == term.TERMINATION_ROUTE_CANCEL
    assert outcome.succeeded is True
    assert transport.calls == [("POST", "https://hp.example:32276/api/v1/runs/01RUNNING/cancel")]
    assert runner.calls == []


def test_a_running_orphan_can_be_held_at_the_cancel_boundary(tmp_path: Path) -> None:
    transport = _FakeTransport(results={"01RUNNING/cancel": _ok(body="{}")})
    runner = _FakeRunner()

    outcome = term.terminate_orphan_run(
        port=_port(tmp_path=tmp_path, transport=transport, runner=runner),
        run_id="01RUNNING",
        status_kind="running",
        destructive_action_held=lambda: True,
    )

    assert outcome is None
    assert transport.calls == []
    assert runner.calls == []


def test_rm_force_is_the_fallback_only_after_both_http_routes_fail(tmp_path: Path) -> None:
    transport = _FakeTransport(results={})
    runner = _FakeRunner()

    outcome = term.terminate_orphan_run(
        port=_port(tmp_path=tmp_path, transport=transport, runner=runner),
        run_id="01BLOCKED",
        status_kind="blocked",
    )

    assert [method for method, _ in transport.calls] == ["GET", "POST"]
    assert outcome.route == term.TERMINATION_ROUTE_RM
    assert outcome.succeeded is True
    assert runner.calls == [
        ["fabro", "rm", "-f", "01BLOCKED", "--server", "https://hp.example:32276"]
    ]
    assert "cancel route unavailable (boom)" in outcome.detail


def test_a_failed_rm_fallback_is_reported_as_not_succeeded(tmp_path: Path) -> None:
    transport = _FakeTransport(results={"01RUNNING/cancel": _refused(status=500)})

    outcome = term.terminate_orphan_run(
        port=_port(
            tmp_path=tmp_path,
            transport=transport,
            runner=_FakeRunner(rm_exit_code=4),
        ),
        run_id="01RUNNING",
        status_kind="running",
    )

    assert outcome.succeeded is False
    assert "cancel route unavailable (status 500)" in outcome.detail


def test_an_unanswerable_blocked_run_falls_through_to_cancel(tmp_path: Path) -> None:
    transport = _FakeTransport(
        results={
            "01BLOCKED/questions": _ok(
                body=json.dumps([{"id": "q-1", "options": [{"key": "R", "label": "Retry"}]}])
            ),
            "01BLOCKED/cancel": _ok(body="{}"),
        }
    )

    outcome = term.terminate_orphan_run(
        port=_port(tmp_path=tmp_path, transport=transport, runner=_FakeRunner()),
        run_id="01BLOCKED",
        status_kind="blocked",
    )

    assert outcome.route == term.TERMINATION_ROUTE_CANCEL


def test_an_abandon_option_carrying_no_key_is_not_answerable(tmp_path: Path) -> None:
    transport = _FakeTransport(
        results={
            "01BLOCKED/questions": _ok(
                body=json.dumps({"data": [{"id": "q-9", "options": [{"label": "Abandon"}]}]})
            ),
            "01BLOCKED/cancel": _ok(body="{}"),
        }
    )

    outcome = term.terminate_orphan_run(
        port=_port(tmp_path=tmp_path, transport=transport, runner=_FakeRunner()),
        run_id="01BLOCKED",
        status_kind="blocked",
    )

    assert outcome.route == term.TERMINATION_ROUTE_CANCEL


def test_a_rejected_answer_falls_through_to_cancel(tmp_path: Path) -> None:
    transport = _FakeTransport(
        results={
            "01BLOCKED/questions": _ok(body=_QUESTIONS_BODY),
            "01BLOCKED/cancel": _ok(body="{}"),
        }
    )

    outcome = term.terminate_orphan_run(
        port=_port(tmp_path=tmp_path, transport=transport, runner=_FakeRunner()),
        run_id="01BLOCKED",
        status_kind="blocked",
    )

    assert outcome.route == term.TERMINATION_ROUTE_CANCEL


def test_abandon_answer_reads_the_recorded_payload_and_rejects_the_rest() -> None:
    recorded = json.loads(_QUESTIONS_BODY)
    bare_question = {"question_id": "q-2", "choices": [{"key": "A", "text": "Abandon now"}]}
    aliased = [{"qid": "q-3", "answers": [{"option_key": "A", "value": "abandon it"}]}]

    assert term.abandon_answer(payload=recorded) == term.PendingAbandonAnswer(
        question_id="q-7", option_key="A", option="[A] Abandon (leave open for triage)"
    )
    assert term.abandon_answer(payload=bare_question) == term.PendingAbandonAnswer(
        question_id="q-2", option_key="A", option="Abandon now"
    )
    assert term.abandon_answer(payload=aliased) == term.PendingAbandonAnswer(
        question_id="q-3", option_key="A", option="abandon it"
    )
    assert term.abandon_answer(payload=None) is None
    assert term.abandon_answer(payload=["not-a-mapping"]) is None
    assert term.abandon_answer(payload=[{"options": [{"key": "A", "label": "Abandon"}]}]) is None
    assert (
        term.abandon_answer(payload=[{"id": "", "options": [{"key": "A", "label": "Abandon"}]}])
        is None
    )
    assert term.abandon_answer(payload=[{"id": "q-4", "options": "Abandon"}]) is None
    assert term.abandon_answer(payload=[{"id": "q-5", "options": [7]}]) is None
    assert (
        term.abandon_answer(payload=[{"id": "q-6", "options": [{"key": "R", "label": "Retry"}]}])
        is None
    )


def _port(*, tmp_path: Path, transport: _FakeTransport, runner: _FakeRunner) -> FabroPort:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url="https://hp.example:32276"),
        runner=runner,
        cwd=tmp_path,
        http=transport,
    )


def _ok(*, body: str) -> FabroHttpResult:
    return FabroHttpResult(status=200, body=body, error=None, payload=None, succeeded=True)


def _refused(*, status: int) -> FabroHttpResult:
    return FabroHttpResult(status=status, body="", error=None, payload=None, succeeded=False)


def _failed() -> FabroHttpResult:
    return FabroHttpResult(status=0, body="", error="boom", payload=None, succeeded=False)
