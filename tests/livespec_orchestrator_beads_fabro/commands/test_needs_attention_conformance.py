"""Tests for the producer-side envelope conformance gate."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
    composed_conformant,
)
from livespec_runtime.attention_item import (
    AttentionItem,
    Handoff,
    SourceRef,
    validate_attention_item_id,
)
from livespec_runtime.needs_attention import (
    ImplNextOutput,
    PlanThreadOutput,
    SpecNextOutput,
    WorkItemHumanValveLane,
)

_FAILURE_ID_PREFIX = "hygiene:attention-invalid:"


def _context() -> ConformanceContext:
    return ConformanceContext(project_root=Path("/repo"), repo="repo")


def _candidate(*, id_: str) -> AttentionItem:
    """One directly-composed candidate, built through the conformance boundary."""
    return _context().candidate(
        id=id_,
        kind="hygiene",
        urgency="low",
        summary="s",
        source_ref=SourceRef(repo="repo"),
        handoff=Handoff(kind="shell", command="true"),
    )


def _failures(*, attention: list[AttentionItem]) -> list[AttentionItem]:
    return [item for item in attention if item.id.startswith(_FAILURE_ID_PREFIX)]


def test_every_primitive_lane_composes_when_each_candidate_is_valid() -> None:
    attention = composed_conformant(
        context=_context(),
        spec_next=SpecNextOutput(
            op="revise", spec_target="SPECIFICATION", summary="s", command="c"
        ),
        impl_next=ImplNextOutput(work_item="bd-1", summary="s", command="c"),
        human_valve_lanes=[
            WorkItemHumanValveLane(
                verb="approve", work_item="bd-2", summary="s", action_id="approve:bd-2", command="c"
            )
        ],
        plan_threads=[PlanThreadOutput(topic="topic", path="p", summary="s", command="c")],
    )

    assert [item.id for item in attention] == [
        "valve:approve:bd-2",
        "impl:bd-1",
        "spec:revise:SPECIFICATION",
        "plan:topic",
    ]
    assert not _failures(attention=attention)


def test_each_primitive_lane_surfaces_its_own_rejection_loudly() -> None:
    """A rejected candidate in ANY lane leaves a visible failure behind."""
    attention = composed_conformant(
        context=_context(),
        # An empty `spec_target` makes the third id component empty, which the
        # runtime grammar refuses.
        spec_next=SpecNextOutput(op="revise", spec_target="", summary="s", command="c"),
        # A decimal work-item id is refused for the same reason.
        impl_next=ImplNextOutput(work_item="99", summary="s", command="c"),
        human_valve_lanes=[
            WorkItemHumanValveLane(verb="", work_item="", summary="s", action_id="a", command="c")
        ],
        plan_threads=[PlanThreadOutput(topic="", path="p", summary="s", command="c")],
    )

    assert len(_failures(attention=attention)) == len(attention) == 4
    assert all(validate_attention_item_id(id=item.id) for item in attention)
    assert all(item.urgency == "high" for item in attention)
    summaries = " ".join(item.summary for item in attention)
    assert "human-valve lane" in summaries
    assert "impl-next candidate for work-item 99" in summaries
    assert "spec-next candidate revise" in summaries
    assert "plan thread" in summaries


def test_a_rejected_candidate_does_not_suppress_its_valid_siblings() -> None:
    attention = composed_conformant(
        context=_context(),
        spec_next=None,
        impl_next=None,
        human_valve_lanes=[],
        plan_threads=[
            PlanThreadOutput(topic="good", path="p", summary="s", command="c"),
            PlanThreadOutput(topic="", path="p", summary="s", command="c"),
        ],
    )

    assert next(item.id for item in attention) == "plan:good"
    assert len(_failures(attention=attention)) == 1


def test_absent_singleton_primitives_compose_nothing_at_all() -> None:
    assert (
        composed_conformant(
            context=_context(),
            spec_next=None,
            impl_next=None,
            human_valve_lanes=[],
            plan_threads=[],
        )
        == []
    )


def test_directly_built_candidates_pass_through_when_their_ids_are_valid() -> None:
    ids = ["hygiene:capacity:repo", "host-only:reason:bd-1", "internal:awaiting-admission:bd-1"]

    assert [_candidate(id_=identifier).id for identifier in ids] == ids


def test_a_directly_built_candidate_with_an_unratified_prefix_surfaces_loudly() -> None:
    """The prefix, not just the shape, is what the runtime validator governs."""
    failure = _candidate(id_="provider-exhaustion:codex:bd-1")

    assert failure.id == f"{_FAILURE_ID_PREFIX}candidate-provider-exhaustion:codex:bd-1"
    assert "provider-exhaustion:codex:bd-1" in failure.summary
    assert failure.urgency == "high"
    assert validate_attention_item_id(id=failure.id)


def test_a_degenerate_candidate_id_still_yields_a_valid_failure_item() -> None:
    """The fixed prefix is what keeps the loud half itself un-droppable."""
    attention = [_candidate(id_=""), _candidate(id_="12345")]

    assert all(validate_attention_item_id(id=item.id) for item in attention)
    assert [item.id for item in attention] == [
        f"{_FAILURE_ID_PREFIX}candidate-",
        f"{_FAILURE_ID_PREFIX}candidate-12345",
    ]


def test_the_failure_handoff_is_a_runnable_shell_command_naming_the_repo() -> None:
    failure = _candidate(id_="bogus")

    assert failure.handoff.kind == "shell"
    assert failure.handoff.command.startswith("cd /repo && codex exec ")
    assert failure.handoff.command.endswith(" < /dev/null")
    assert failure.source_ref.repo == "repo"
