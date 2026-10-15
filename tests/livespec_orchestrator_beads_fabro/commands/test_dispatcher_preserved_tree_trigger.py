"""Which runs need their tree preserved, and which already carry it elsewhere."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = f"{_PACKAGE}._dispatcher_preserved_tree_trigger"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_preserved_tree_trigger.py"
)

_CHECKPOINT_FAILURE_TEXT = (
    "git checkpoint commit failed for node implement: git commit failed (exit 1)"
)
_NEEDS_HUMAN_TEXT = "LIVESPEC_NEEDS_HUMAN: loop cannot auto-resolve this work-item; run terminated"
_PATCH = "diff --git a/a.py b/a.py\n+changed\n"


def _events(*, patch: str | None) -> tuple[dict[str, Any], ...]:
    """A checkpoint-failed run's stream, with or without a terminal patch."""
    failed: dict[str, Any] = {"type": "run.failed", "reason": _CHECKPOINT_FAILURE_TEXT}
    if patch is not None:
        failed["patch"] = patch
    return (
        {"type": "checkpoint.failed", "node": "implement", "error": "git commit failed (exit 1)"},
        failed,
    )


def test_a_checkpoint_failed_run_with_no_terminal_patch_needs_its_tree_preserved() -> None:
    # The module does not exist at Red, so this is a genuine assertion failure
    # rather than a collection error.
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    trigger = importlib.import_module(_MODULE)
    decided = trigger.preservation_trigger(
        failure_text=_CHECKPOINT_FAILURE_TEXT, records=_events(patch=None)
    )
    assert decided.preserves is True
    assert decided.node == "implement"
    assert decided.terminal_patch_bytes is None
    assert decided.terminal_patch_sha256 is None
    assert "no terminal patch" in decided.reason


def test_a_checkpoint_failed_run_whose_terminal_patch_carries_its_work_gets_no_ref() -> None:
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    trigger = importlib.import_module(_MODULE)
    decided = trigger.preservation_trigger(
        failure_text=_CHECKPOINT_FAILURE_TEXT, records=_events(patch=_PATCH)
    )
    assert decided.preserves is False
    # The pointer's size and digest are what make the suppression auditable: a
    # suppression recording neither would be indistinguishable from a reading
    # that never looked.
    assert decided.terminal_patch_bytes == len(_PATCH.encode("utf-8"))
    assert decided.terminal_patch_sha256 == hashlib.sha256(_PATCH.encode("utf-8")).hexdigest()


def test_an_unobservable_terminal_patch_does_not_count_as_observed() -> None:
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    trigger = importlib.import_module(_MODULE)
    decided = trigger.preservation_trigger(failure_text=_CHECKPOINT_FAILURE_TEXT, records=None)
    assert decided.preserves is True
    assert decided.node == "implement"
    assert decided.terminal_patch_bytes is None
    assert decided.terminal_patch_sha256 is None
    assert "could not be read" in decided.reason


def test_a_run_that_did_not_end_on_a_failed_checkpoint_preserves_no_tree() -> None:
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    trigger = importlib.import_module(_MODULE)
    decided = trigger.preservation_trigger(failure_text=_NEEDS_HUMAN_TEXT, records=None)
    assert decided.preserves is False
    assert decided.node is None
    assert "no failed engine checkpoint" in decided.reason
