"""Receipt-reading cases for the input-bound Definition-of-Done hygiene fact."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _needs_attention_definition_of_done as definition,
)
from livespec_orchestrator_beads_fabro.commands import _needs_attention_unpreflightable as module
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
    CandidateAttempt,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    DodJudgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_DISPATCH,
    did_not_run_comment,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _input_bound_receipt(*, subject_characters: int | None = 431) -> str:
    """One host receipt whose two configured candidates each hit the bound."""
    candidates = ("claude-acp:claude-opus-5", "codex-acp:gpt-5.6-terra")
    attempts = tuple(
        CandidateAttempt(
            agent=candidate.split(":", maxsplit=1)[0],
            model=candidate.split(":", maxsplit=1)[1],
            exit_code=1,
            outcome="input-limit-reached",
        )
        for candidate in candidates
    )
    return did_not_run_comment(
        item_id="bd-ib-input-bound",
        stage=STAGE_PRE_DISPATCH,
        digest="subject",
        rubric_digest="rubric",
        cause="input-limit-reached",
        subject_characters=subject_characters,
        carried_rider_count=2,
        bound_ended_candidates=candidates,
        attempts=attempts,
    )


def test_the_latest_host_receipt_controls_the_input_bound_measurement() -> None:
    input_bound = _input_bound_receipt()
    later_verdict = verdict_comment(
        item_id="bd-ib-input-bound",
        stage=STAGE_PRE_DISPATCH,
        digest="subject",
        rubric_digest="rubric",
        judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED),
    )
    unrelated_node_receipt = input_bound.replace("stage: pre-dispatch", "stage: dod-gate")

    assert module.latest_input_bound_measurement(comments=(input_bound,)) == (431, 2)
    assert module.latest_input_bound_measurement(comments=(input_bound, later_verdict)) is None
    assert module.latest_input_bound_measurement(
        comments=(input_bound, unrelated_node_receipt)
    ) == (
        431,
        2,
    )
    assert module.latest_input_bound_measurement(comments=(input_bound, "stage: pre-dispatch")) == (
        431,
        2,
    )
    assert module.latest_input_bound_measurement(comments=()) is None


def test_malformed_input_bound_measurements_do_not_create_a_hygiene_fact() -> None:
    malformed = _input_bound_receipt(subject_characters=None)
    non_decimal = malformed.replace("subject-size-characters: 431", "subject-size-characters: many")
    another_cause = malformed.replace("input-limit-reached", "no-eligible-model")

    assert module.latest_input_bound_measurement(comments=(malformed,)) is None
    assert module.latest_input_bound_measurement(comments=(non_decimal,)) is None
    assert module.latest_input_bound_measurement(comments=(another_cause,)) is None


def test_an_unconfigured_repository_has_no_receipt_lane(tmp_path: Path) -> None:
    assert (
        module.unpreflightable_definition_of_done_items(
            project_root=tmp_path, repo="repo", items=[]
        )
        == []
    )


def test_an_unreadable_item_receipt_and_empty_composer_both_report_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def resolved_config(*, cwd: Path, work_items_arg: str | None) -> StoreConfig:
        _ = cwd, work_items_arg
        return cast(StoreConfig, object())

    def unreadable_comments(*, path: StoreConfig, work_item_id: str) -> tuple[str, ...] | None:
        _ = path, work_item_id
        return None

    monkeypatch.setattr(module, "resolve_store_config", resolved_config)
    monkeypatch.setattr(module, "item_comment_bodies", unreadable_comments)

    assert (
        module.unpreflightable_definition_of_done_items(
            project_root=tmp_path,
            repo="repo",
            items=cast(list[WorkItem], [SimpleNamespace(id="bd-ib-item")]),
        )
        == []
    )
    assert (
        definition.definition_of_done_hygiene_items(project_root=tmp_path, repo="repo", items=[])
        == []
    )
