"""Tests for TAKING the spec-change-tier classification of one work-item.

The impure half of the decision. The claim this module exists to fail on is the
clause's own exemption — "An item classified `bug`, `chore` or `non_functional`
is never spec-change tier and routes as every other factory-dispatchable item",
and Scenario 206's "A bug is routed as today".

THE EXEMPTION IS GRADED ON THE SPEND, not only on the verdict. A classification
that asked the behaviour judgement and then discarded the answer returns the
same `tier: none`, so each exempt case counts the model calls: one, the
classification itself. That is also the honest reading of the record, whose
`stated_kind` is `None` for such an item because none was ever measured.

THE FEATURE CASE IS WHAT MAKES THEM EVIDENCE. Without a classification that
genuinely reaches the behaviour judgement, a reader that never took one
satisfies every exempt case in the module.

EVERY ABSENCE IS A SEPARATE ARM. A judge that answers outside the four-word
vocabulary, one whose invocation raises, and a feature whose behaviour verdict
cannot be taken are three different failures to MEASURE, and all three reach
surfaces sitting on the dispatch path and the intake path — so each must answer
`None` rather than raise.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_judge import (
    host_spec_change_tier_reader,
    spec_change_tier_classification,
    unclassified_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_GOVERNING = "## Grooming and slice-size calibration"
_TOPIC = "spec-stated-judgement-and-spec-change-tier"

_UNSTATED_REPLY = (
    '{"kind": "unstated", "stated_by": [],'
    f' "generalization_target": "{_GOVERNING}", "rationale": "Nothing states it."}}'
)


def _item(*, item_type: str = "feature") -> WorkItem:
    return WorkItem(
        id="bd-ib-57ss2n",
        type=item_type,  # pyright: ignore[reportArgumentType]
        status="pending-approval",
        title="The spec-change tier is decided by the spec-stated judgement",
        description="## Definition of Done\n\n- The tier is decided.\n\nReferences: ## Other\n",
        origin="freeform",
        gap_id=None,
        rank="b0f",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-24T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_GOVERNING}\n\nIt says something else.\n", encoding="utf-8"
    )
    return repo


class _Model:
    """A `ModelRunner` double answering the classification, then the judgement."""

    def __init__(self, *, replies: list[str]) -> None:
        self.replies = replies
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.replies[len(self.prompts) - 1]


class _Runner:
    """A `CommandRunner` double standing in for the headless judge."""

    def __init__(self, *, replies: list[str]) -> None:
        self.replies = replies
        self.calls = 0

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
        start_new_session: bool = False,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin, start_new_session)
        self.calls += 1
        return CommandResult(exit_code=0, stdout=self.replies[self.calls - 1], stderr="")


def test_a_bug_a_chore_and_a_non_functional_item_take_no_behaviour_judgement(
    tmp_path: Path,
) -> None:
    """The exemption, read off the SPEND as well as off the verdict."""
    for answer in ("bug", "chore", "non_functional"):
        model = _Model(replies=[answer, _UNSTATED_REPLY])

        verdict = spec_change_tier_classification(
            item=_item(),
            repo=_repo(tmp_path=tmp_path),
            linked_topic=None,
            topic_ratified=False,
            run_model=model,
        )

        assert verdict is not None
        assert verdict.item_class == answer
        assert verdict.stated_kind is None
        assert verdict.holds is False
        assert len(model.prompts) == 1


def test_the_stored_type_is_evidence_rather_than_the_answer(tmp_path: Path) -> None:
    """An item STORED as a feature the judgement calls a bug is exempt.

    The clause makes the stored type evidence and the classification the
    answer, so a reader keyed on `item.type` would hold this item.
    """
    model = _Model(replies=["bug", _UNSTATED_REPLY])

    verdict = spec_change_tier_classification(
        item=_item(item_type="feature"),
        repo=_repo(tmp_path=tmp_path),
        linked_topic=None,
        topic_ratified=False,
        run_model=model,
    )

    assert verdict is not None
    assert verdict.holds is False


def test_a_feature_whose_behaviour_is_unstated_carries_the_generalization_target(
    tmp_path: Path,
) -> None:
    """The positive case, without which every exemption above is free."""
    model = _Model(replies=["feature", _UNSTATED_REPLY])

    verdict = spec_change_tier_classification(
        item=_item(),
        repo=_repo(tmp_path=tmp_path),
        linked_topic=_TOPIC,
        topic_ratified=False,
        run_model=model,
    )

    assert verdict is not None
    assert verdict.holds is True
    assert verdict.stated_kind == "unstated"
    assert verdict.generalization_target == _GOVERNING
    assert verdict.linked_proposal_topic == _TOPIC
    assert len(model.prompts) == 2


def test_the_stored_type_travels_into_the_classification_prompt_as_evidence(
    tmp_path: Path,
) -> None:
    """ "The stored type being evidence rather than the answer" is a prompt input."""
    model = _Model(replies=["chore"])

    _ = spec_change_tier_classification(
        item=_item(item_type="chore"),
        repo=_repo(tmp_path=tmp_path),
        linked_topic=None,
        topic_ratified=False,
        run_model=model,
    )

    assert "chore" in model.prompts[0]


def test_an_answer_outside_the_four_word_vocabulary_is_a_classification_that_did_not_run(
    tmp_path: Path,
) -> None:
    """An unreadable verdict is a failure to measure, never a `tier: none`."""
    assert (
        spec_change_tier_classification(
            item=_item(),
            repo=_repo(tmp_path=tmp_path),
            linked_topic=None,
            topic_ratified=False,
            run_model=_Model(replies=["probably a feature"]),
        )
        is None
    )


def test_a_judge_whose_invocation_raises_answers_no_classification(tmp_path: Path) -> None:
    """An `OSError` here would unwind through the dispatch and intake paths."""

    def _raising(_prompt: str) -> str:
        raise OSError("no space left on device")

    assert (
        spec_change_tier_classification(
            item=_item(),
            repo=_repo(tmp_path=tmp_path),
            linked_topic=None,
            topic_ratified=False,
            run_model=_raising,
        )
        is None
    )


def test_a_feature_whose_behaviour_verdict_cannot_be_taken_answers_no_classification(
    tmp_path: Path,
) -> None:
    """A half-taken classification is not a tier, so it is not reported as one."""
    assert (
        spec_change_tier_classification(
            item=_item(),
            repo=_repo(tmp_path=tmp_path),
            linked_topic=None,
            topic_ratified=False,
            run_model=_Model(replies=["feature", "not json at all"]),
        )
        is None
    )


def test_the_absent_reader_takes_no_classification_and_spends_nothing() -> None:
    """The named arm a surface that must not spend a model call asks for."""
    assert (
        unclassified_spec_change_tier(
            item=_item(), repo=Path("/nonexistent"), linked_topic=None, topic_ratified=False
        )
        is None
    )


def test_the_host_reader_puts_the_classification_to_this_hosts_headless_judge(
    tmp_path: Path,
) -> None:
    """The binding every refusing surface defaults to, driven end to end."""
    runner = _Runner(replies=["feature", _UNSTATED_REPLY])

    verdict = host_spec_change_tier_reader(runner=runner)(
        item=_item(), repo=_repo(tmp_path=tmp_path), linked_topic=_TOPIC, topic_ratified=True
    )

    assert verdict is not None
    assert verdict.holds is True
    assert verdict.topic_ratified is True
    assert runner.calls == 2
