"""Ordering regressions for plan-epic verified-proof observations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import IssueDraft, make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NextAction,
    read_next_action,
    resume_directive,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNSATISFIED,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_proof import observe_verified_proof
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import ResultRepository
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import VerifiedProofTarget

_EPIC = "bd-ib-plan-proof-staleness"
_BUILD = "v0.170.0"
_ASSERTION = "The epic proof is read from a typed ledger record."
_NOW = "2026-10-31T12:00:00Z"


def _repository(*, tmp_path: Path) -> ResultRepository:
    clone = tmp_path / "repo"
    clone.mkdir()
    _ = (clone / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}),
        encoding="utf-8",
    )
    return ResultRepository(name="repo", clone=clone)


def _seed(*, repository: ResultRepository, comments: tuple[str, ...]) -> None:
    client = make_beads_client(config=store_config(repo=repository.clone))
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_EPIC,
            issue_type="epic",
            title="plan proof",
            description="## Definition of Done\n\n- proof.\n",
            assignee=None,
            created_at="2026-10-31T00:00:00Z",
        )
    )
    for comment in comments:
        client.add_comment(issue_id=_EPIC, body=comment)


def _record(*, verdict: str) -> str:
    return (
        f"Plan Proof of Done — {verdict} — session independent — 2026-10-31T01:00:00Z\n"
        "\n"
        "## Build identity\n"
        "\n"
        f"- Release tag: {_BUILD}\n"
        "\n"
        f"## Assertion 1 — {_ASSERTION}\n"
        "Reproduced: yes.\n"
    )


def _target() -> VerifiedProofTarget:
    return VerifiedProofTarget(subject_id=_EPIC, build=_BUILD, assertions=(_ASSERTION,))


def _carrier_map() -> str:
    return "plan-scope-event\n\ncarriers:\n- 1: plan-level proof"


def test_a_verified_record_predating_a_carrier_map_event_is_unsatisfied(tmp_path: Path) -> None:
    repository = _repository(tmp_path=tmp_path)
    _seed(repository=repository, comments=(_record(verdict="verified"), _carrier_map()))

    observation = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_NeverRuns(),
        now=_NOW,
    )

    assert observation.status == OBSERVATION_UNSATISFIED
    assert "carrier-map event at ledger comment position 2" in observation.detail


def test_a_verified_record_after_capture_and_carrier_map_is_satisfied(tmp_path: Path) -> None:
    repository = _repository(tmp_path=tmp_path)
    _seed(
        repository=repository,
        comments=(_record(verdict="captured"), _carrier_map(), _record(verdict="verified")),
    )

    observation = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_NeverRuns(),
        now=_NOW,
    )

    assert observation.status == OBSERVATION_SATISFIED


def test_resume_keeps_a_proof_pointer_when_capture_supersedes_verification(tmp_path: Path) -> None:
    repository = _repository(tmp_path=tmp_path)
    _seed(
        repository=repository,
        comments=(_record(verdict="verified"), _record(verdict="captured")),
    )
    config = store_config(repo=repository.clone)
    action = NextAction(
        kind="proof",
        ref=f"verify:{_EPIC}",
        text="Verify the captured plan proof.",
        required_result={
            "repo": "repo",
            "verified_proof": {
                "subject_id": _EPIC,
                "build": _BUILD,
                "assertions": [_ASSERTION],
            },
        },
        budget={"deadline": "2099-01-01T00:00:00Z", "max_handoffs": 1},
    )

    refusal = set_next_action(
        config=config,
        epic_id=_EPIC,
        action=action,
        session="plan-session",
        now=_NOW,
    )
    directive = resume_directive(config=config, epic_id=_EPIC, unattended=True)
    pointer = read_next_action(config=config, epic_id=_EPIC)

    assert refusal is None
    assert not directive.ask
    assert directive.next_action == f"proof:verify:{_EPIC}"
    assert pointer == action


class _NeverRuns:
    """The plan proof path never reads a pull request or runs a comparison."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del argv, cwd, timeout_seconds, env, stdin
        raise AssertionError("plan-epic proof reading must not invoke the forge")


def test_the_plan_reader_guard_rejects_an_accidental_forge_call(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="must not invoke"):
        _ = _NeverRuns().run(argv=[], cwd=tmp_path, timeout_seconds=1.0)
