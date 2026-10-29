"""A confirmation turn the agent rejects for authentication is named for what it is.

Beside `test_acp_availability_probe_run_degraded.py`, which covers the readings
a healthy factory never produces. The measured case is the one this module is
built around: the adapter answered `session/prompt` with JSON-RPC error -32000
"Authentication required" three seconds into the turn, the graph routed the
failed `confirm` stage to `exit`, the run therefore read SUCCEEDED, and the
journal recorded `process-exit` -- a label that sends an operator to debug an
adapter that never started, when the adapter was fine and the credential was
absent.

THE ENDING IS GRADED FROM THE PROBE NODE'S OWN FAILURE, not from the run's. A
run whose graph absorbed the failed turn carries no run-level failure block at
all, so a grader reading only the run reports nothing and falls through to the
process exit; the stage's recorded output, or its `stage.failed` event, is where
the sentence lives, and which of the two an engine writes differs by
generation. Both are driven.

IT IS NOT A REFUSAL, AND THE DISTINCTION IS THE EXPENSIVE ONE. An authentication
rejection after a session was created has both halves of the refusal ending --
the prompt boundary crossed and a recorded sentence -- so a grader that tested
refusal first would mint a fifteen-minute hold on a provider that never
refused anything. The clause's own non-eligible list names authentication, and a
hold is exactly what that list exists to prevent.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_RUN_ID = "01M5PROBEAUTH0000000000000"
_NOW = "2026-10-29T10:05:00Z"
_REJECTION = "the agent answered `session/prompt` with an error: Authentication required"

_CONFIG = json.dumps(
    {
        "livespec-orchestrator-beads-fabro": {
            "dispatcher": {
                "default_factory": "hp",
                "factories": {"hp": {"server": "https://hp.example.ts.net:32276"}},
            }
        }
    }
)


def _module(name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


@dataclass(kw_only=True)
class _Command:
    exit_code: int
    stdout: str
    stderr: str = ""


@dataclass(kw_only=True)
class _Engine:
    inspect_record: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> _Command:
        _ = (cwd, timeout_seconds, env)
        if "--version" in argv:
            return _Command(exit_code=0, stdout="fabro 0.254.0 (8869e88 2026-10-01)\n")
        if "inspect" in argv:
            return _Command(exit_code=0, stdout=json.dumps([self.inspect_record]))
        if "events" in argv:
            return _Command(exit_code=0, stdout=json.dumps(self.events))
        return _Command(exit_code=0, stdout=f"Run: {_RUN_ID}\n")


def _record(*, state: str, output: str | None, run_failure: dict[str, Any] | None = None) -> Any:
    stage: dict[str, Any] = {"state": state}
    if output is not None:
        stage["output"] = output
    record: dict[str, Any] = {
        "run_id": _RUN_ID,
        "status": {"kind": "succeeded"},
        "stages": {"confirm@1": stage, "exit@1": {"state": "succeeded"}},
    }
    if run_failure is not None:
        record["failure"] = run_failure
    return record


def _started() -> dict[str, Any]:
    return {"type": "agent.acp.started", "node": "confirm"}


def _probe(*, tmp_path: Path, engine: _Engine, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    _ = (tmp_path / ".livespec.jsonc").write_text(_CONFIG, encoding="utf-8")
    candidate_schema = _module("_acp_candidate_schema")
    adapters = _module("_acp_node_adapters")
    candidate = candidate_schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="claude-code-acp"),
        identity=candidate_schema.AcpCandidateIdentity(
            display_name="Claude Sonnet 5.5",
            candidate_key="claude-sonnet-5-5",
            availability_key="anthropic",
        ),
    )
    return _module("_acp_availability_probe_run").run_availability_probe(
        repo=tmp_path,
        candidate=candidate,
        builtin=True,
        work_item_id="bd-ib-3pfauo",
        observation_ids=("acpobs-f2987ee775375454124951e3",),
        now_iso=_NOW,
        timeout_seconds=120,
        runner=engine,
    )


def test_the_vocabulary_names_an_authentication_ending_that_does_not_confirm() -> None:
    """The new member is spelled for what it is and sits among the unconfirmed ones."""
    outcome = _module("_acp_availability_probe_outcome")

    assert getattr(outcome, "PROBE_AUTHENTICATION_FAILED", None) == "authentication-failure"
    assert "authentication-failure" in outcome.PROBE_ENDINGS
    assert "authentication-failure" in outcome.PROBE_UNCONFIRMED_ENDINGS
    assert outcome.probe_confirms(ending="authentication-failure") is False


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"turn_completed": True}, "turn-completed"),
        ({"timed_out": True}, "timed-out"),
        ({"cancelled": True}, "cancelled"),
        ({}, "authentication-failure"),
    ],
)
def test_the_authentication_reading_ranks_below_the_bound_the_turn_and_cancellation(
    overrides: dict[str, bool], expected: str
) -> None:
    """A completed, killed or cancelled turn keeps its own ending; only the rest is auth."""
    outcome = _module("_acp_availability_probe_outcome")
    declared = {one.name for one in dataclasses.fields(outcome.AcpProbeObservation)}
    assert "authentication_failed" in declared, sorted(declared)
    fields: dict[str, bool] = {
        "turn_completed": False,
        "acp_started": False,
        "cancelled": False,
        "timed_out": False,
        "authentication_failed": True,
    }
    fields.update(overrides)

    observation = outcome.AcpProbeObservation(failure=None, **fields)

    assert outcome.probe_ending(observation=observation) == expected


def test_a_stage_the_graph_absorbed_is_graded_from_its_recorded_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The measured shape: the run succeeded, the confirm stage failed, no session started."""
    engine = _Engine(inspect_record=_record(state="failed", output=_REJECTION))

    result = _probe(tmp_path=tmp_path, engine=engine, monkeypatch=monkeypatch)

    assert not isinstance(result, str), result
    assert result.ending == "authentication-failure"
    assert result.confirmed is False
    assert result.hold_record is None
    assert result.journal_record["outcome"] == "authentication-failure"
    assert result.journal_record["confirmed"] is False
    assert result.journal_record["satisfies_observation_ids"] == ["acpobs-f2987ee775375454124951e3"]


def test_a_stage_failed_event_is_graded_the_same_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pinned engine's record names the failure on a `stage.failed` event."""
    engine = _Engine(
        inspect_record=_record(state="failed", output=None),
        events=[{"type": "stage.failed", "node_id": "confirm", "failure": {"message": _REJECTION}}],
    )

    result = _probe(tmp_path=tmp_path, engine=engine, monkeypatch=monkeypatch)

    assert not isinstance(result, str), result
    assert result.ending == "authentication-failure"
    assert result.journal_record["outcome"] == "authentication-failure"


def test_an_authentication_rejection_after_a_session_started_mints_no_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both halves of a refusal are present, and it is still not one."""
    engine = _Engine(
        inspect_record=_record(
            state="failed",
            output=_REJECTION,
            run_failure={"causes": ["ACP protocol error", _REJECTION]},
        ),
        events=[_started()],
    )

    result = _probe(tmp_path=tmp_path, engine=engine, monkeypatch=monkeypatch)

    assert not isinstance(result, str), result
    assert result.ending == "authentication-failure"
    assert result.hold_record is None


def test_a_failed_stage_that_says_nothing_about_authentication_keeps_its_ending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: a failed stage is not by itself an authentication failure."""
    engine = _Engine(
        inspect_record=_record(state="failed", output="the adapter exited with status 2")
    )

    result = _probe(tmp_path=tmp_path, engine=engine, monkeypatch=monkeypatch)

    assert not isinstance(result, str), result
    assert result.ending == "process-exit"
    assert result.journal_record["outcome"] == "process-exit"
