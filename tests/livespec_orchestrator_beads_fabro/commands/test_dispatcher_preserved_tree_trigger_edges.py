"""The readings of a checkpoint-failed run's stream that a healthy run cannot reach."""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_trigger import (
    failed_checkpoint_node,
    preservation_trigger,
)

_PATCH = "diff --git a/a.py b/a.py\n+changed\n"
_UNNAMED_CLASS_TEXT = "the run ended checkpoint_failed"


def _stream(*, events: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    return tuple(events)


def test_an_event_before_the_checkpoint_failure_is_passed_over_rather_than_read() -> None:
    """The scan must reach a checkpoint failure that is not the stream's first event.

    A reader that answered off the first record would report no checkpoint
    failure for every real run, because a run emits its start and its node
    events before anything fails.
    """
    decided = preservation_trigger(
        failure_text="unrelated prose",
        records=_stream(
            events=[
                {"type": "run.started"},
                {"type": "agent.tool.completed"},
                {"type": "checkpoint.failed", "node": "review_fix"},
            ]
        ),
    )
    assert decided.preserves is True
    assert decided.node == "review_fix"


def test_a_checkpoint_failure_event_naming_no_node_still_preserves_the_tree() -> None:
    """An unnamed node is a checkpoint failure whose node is unknown.

    Collapsing it onto "no checkpoint failure" would suppress the publication
    for the one engine shape that reports the class without the sentence.
    """
    for unnamed in ({"type": "checkpoint.failed"}, {"type": "checkpoint.failed", "node": ""}):
        decided = preservation_trigger(failure_text="", records=_stream(events=[unnamed]))
        assert decided.preserves is True, unnamed
        assert decided.node is None, unnamed


def test_a_failure_text_naming_only_the_failure_class_still_preserves_the_tree() -> None:
    decided = preservation_trigger(failure_text=_UNNAMED_CLASS_TEXT, records=None)
    assert decided.preserves is True
    assert decided.node is None
    assert failed_checkpoint_node(failure_text=_UNNAMED_CLASS_TEXT) is None


def test_a_terminal_patch_held_one_level_down_is_still_an_observed_patch() -> None:
    """The nested spelling is read, because the response shape was unmeasured.

    A patch missed where one exists costs one recoverable duplicate ref; the
    reading is still taken so the suppression records the figures when it can.
    """
    decided = preservation_trigger(
        failure_text="checkpoint commit failed for node implement",
        records=_stream(
            events=[
                {"type": "run.failed", "data": {"note": "no patch here"}},
                {"type": "run.failed", "data": {"terminal_patch": _PATCH}},
            ]
        ),
    )
    assert decided.preserves is False
    assert decided.terminal_patch_bytes == len(_PATCH.encode("utf-8"))


def test_a_terminal_event_whose_every_patch_spelling_is_empty_carries_no_patch() -> None:
    """An empty patch is NO patch -- a zero-length diff asserts no work was done."""
    decided = preservation_trigger(
        failure_text="checkpoint commit failed for node implement",
        records=_stream(
            events=[
                {"type": "run.failed", "patch": "", "diff": "", "payload": {"patch": ""}},
            ]
        ),
    )
    assert decided.preserves is True
    assert decided.terminal_patch_bytes is None
