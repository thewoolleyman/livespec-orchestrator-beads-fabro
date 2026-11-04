"""Negative and unreadable plan-epic verified-proof observations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._store_comments import WorkItemComment
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NextAction,
    resume_directive,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_UNOBSERVABLE,
    OBSERVATION_UNSATISFIED,
    SOURCE_LEDGER,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_plan_owned import (
    plan_owned_reference,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_plan_proof import (
    observe_plan_verified_proof,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_proof import observe_verified_proof
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import ResultRepository
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import VerifiedProofTarget
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.types import StoreConfig

_EPIC = "bd-ib-plan-proof"
_BUILD = "v0.170.0"
_OTHER_BUILD = "v0.170.1"
_ASSERTION = "The epic proof is read from a typed ledger record."
_MISSING_ASSERTION = "The requested assertion is absent from the record."
_NOW = "2026-10-31T12:00:00Z"


def _repo(*, tmp_path: Path) -> ResultRepository:
    clone = tmp_path / "repo"
    clone.mkdir()
    _ = (clone / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}),
        encoding="utf-8",
    )
    return ResultRepository(name="repo", clone=clone)


def _seed_epic(*, repository: ResultRepository, comments: tuple[str, ...]) -> None:
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


def _record(*, verdict: str, build: str = _BUILD, assertion: str = _ASSERTION) -> str:
    return (
        f"Plan Proof of Done — {verdict} — session independent — 2026-10-31T01:00:00Z\n"
        "\n"
        "## Build identity\n"
        "\n"
        f"- Release tag: {build}\n"
        "\n"
        f"## Assertion 1 — {assertion}\n"
        "Reproduced: yes.\n"
    )


@pytest.mark.parametrize(
    ("comments", "target"),
    [
        pytest.param(
            (_record(verdict="captured"),),
            VerifiedProofTarget(subject_id=_EPIC, build=_BUILD, assertions=(_ASSERTION,)),
            id="captured-only",
        ),
        pytest.param(
            (_record(verdict="not_reproduced"),),
            VerifiedProofTarget(subject_id=_EPIC, build=_BUILD, assertions=(_ASSERTION,)),
            id="latest-replay-refutes",
        ),
        pytest.param(
            (_record(verdict="verified"),),
            VerifiedProofTarget(subject_id=_EPIC, build=_BUILD, assertions=(_MISSING_ASSERTION,)),
            id="verified-record-omits-requested-assertion",
        ),
        pytest.param(
            (_record(verdict="verified", build=_OTHER_BUILD),),
            VerifiedProofTarget(subject_id=_EPIC, build=_BUILD, assertions=(_ASSERTION,)),
            id="verified-record-names-a-different-build",
        ),
        pytest.param(
            ("Plan Proof of Done — verified — this is prose, not a typed record\n",),
            VerifiedProofTarget(subject_id=_EPIC, build=_BUILD, assertions=(_ASSERTION,)),
            id="verified-looking-prose-is-not-a-plan-record",
        ),
    ],
)
def test_plan_epic_records_that_do_not_fulfil_the_target_are_unsatisfied(
    tmp_path: Path, comments: tuple[str, ...], target: VerifiedProofTarget
) -> None:
    repository = _repo(tmp_path=tmp_path)
    _seed_epic(repository=repository, comments=comments)

    observation = observe_verified_proof(
        repository=repository,
        target=target,
        runner=_NeverRuns(),
        now=_NOW,
    )

    assert observation.status == OBSERVATION_UNSATISFIED
    assert observation.source == SOURCE_LEDGER


def test_an_unreadable_plan_epic_comment_timeline_is_unobservable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repo(tmp_path=tmp_path)
    _seed_epic(repository=repository, comments=())
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._plan_result_plan_proof.read_work_item_comments",
        _unreadable_comments,
    )

    observation = observe_verified_proof(
        repository=repository,
        target=VerifiedProofTarget(subject_id=_EPIC, build=_BUILD, assertions=(_ASSERTION,)),
        runner=_NeverRuns(),
        now=_NOW,
    )

    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert observation.source == SOURCE_LEDGER
    assert "comment read" in observation.detail


def test_an_unconfigured_plan_repository_is_unobservable(tmp_path: Path) -> None:
    repository = ResultRepository(name="unconfigured", clone=tmp_path)

    observation = observe_plan_verified_proof(
        repository=repository,
        target=VerifiedProofTarget(subject_id=_EPIC, build=_BUILD, assertions=(_ASSERTION,)),
        now=_NOW,
    )

    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert observation.source == SOURCE_LEDGER


def test_a_verified_proof_target_on_the_epic_reads_the_plans_own_repository(
    tmp_path: Path,
) -> None:
    repository = _repo(tmp_path=tmp_path)

    reference = plan_owned_reference(
        config=store_config(repo=repository.clone),
        epic_id=_EPIC,
        required_result={
            "repo": "foreign",
            "verified_proof": {
                "subject_id": _EPIC,
                "build": _BUILD,
                "assertions": [_ASSERTION],
            },
        },
    )

    assert reference == {
        "repo": "repo",
        "verified_proof": {
            "subject_id": _EPIC,
            "build": _BUILD,
            "assertions": [_ASSERTION],
        },
    }


def test_an_unattended_resume_takes_an_in_budget_proof_verification_for_its_epic(
    tmp_path: Path,
) -> None:
    repository = _repo(tmp_path=tmp_path)
    _seed_epic(repository=repository, comments=(_record(verdict="captured"),))
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

    assert refusal is None
    assert not directive.ask
    assert directive.next_action == f"proof:verify:{_EPIC}"
    assert directive.observation is not None
    assert directive.observation.status == OBSERVATION_UNSATISFIED


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
        _NeverRuns().run(argv=[], cwd=tmp_path, timeout_seconds=1.0)


def _unreadable_comments(*, path: StoreConfig, work_item_id: str) -> tuple[WorkItemComment, ...]:
    del path, work_item_id
    raise BeadsConnectionError(detail="offline")
