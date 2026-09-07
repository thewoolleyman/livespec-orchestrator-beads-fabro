"""The v104 answer-disposition policy setting: read, and resolved per item.

The dispatcher-policy-settings contract in `SPECIFICATION/contracts.md` gained
`dispatcher.answer_disposition` as its fifth policy setting when v104 ratified
the attention-item answer-disposition policy in the same file. This file covers
the two halves the ratified clause names for the resolution: the global default
(`human` when nothing is configured) and the per-item `answer:<human|consensus>`
label that overrides it.

The asymmetry is the case worth reading twice, and it is the one a generic
cap-shaped override would get wrong. The label MAY lower an item to `human` and
MUST NOT raise one to `consensus`, so both directions are asserted against a
global that would make a wrong answer visible in each.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any, TypeVar

from livespec_orchestrator_beads_fabro.types import WorkItem
from returns.io import IOResult
from returns.unsafe import unsafe_perform_io

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_SETTINGS_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings"
_OVERRIDES_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides"
_OVERRIDES_PATH = _COMMANDS / "_dispatcher_policy_overrides.py"

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_NO_CONFIG_CWD = Path("tests/nonexistent-answer-disposition-cwd")

_Value = TypeVar("_Value")


def _read(outcome: IOResult[_Value, object]) -> _Value:
    """The value out of a successful policy read.

    `unsafe_perform_io` is mandatory rather than decorative: `IOResult.unwrap`
    yields `IO[value]`, and comparing that wrapper to `"human"` passes nothing
    and fails everything.
    """
    return unsafe_perform_io(outcome.unwrap())


def _settings() -> Any:
    return import_module(_SETTINGS_NAME)


def _overrides() -> Any:
    assert _OVERRIDES_PATH.is_file()
    return import_module(_OVERRIDES_NAME)


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-parked",
        type="task",
        status="blocked",
        title="An item parked on a question",
        description="It could not be finished without a decision.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason="needs-human",
    )


def _write_config(*, tmp_path: Path, dispatcher: dict[str, object]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({_PLUGIN_BLOCK: {"compat": {"pinned": "master"}, "dispatcher": dispatcher}}),
        encoding="utf-8",
    )
    return tmp_path


def test_the_setting_defaults_to_human_when_nothing_is_configured() -> None:
    """An absent file is an ANSWER, so the read lands on the documented default."""
    settings = _settings()

    assert settings.DEFAULT_ANSWER_DISPOSITION == "human"
    assert _read(settings.resolve_answer_disposition(cwd=_NO_CONFIG_CWD)) == "human"


def test_the_enum_accepts_consensus_and_refuses_anything_else(tmp_path: Path) -> None:
    """`consensus` is the one other member; an unreadable value FAILS, not defaults."""
    settings = _settings()
    opted_in = _write_config(
        tmp_path=tmp_path / "in", dispatcher={"answer_disposition": "consensus"}
    )
    nonsense = _write_config(
        tmp_path=tmp_path / "out", dispatcher={"answer_disposition": "whoever"}
    )

    assert _read(settings.resolve_answer_disposition(cwd=opted_in)) == "consensus"
    failure = unsafe_perform_io(settings.resolve_answer_disposition(cwd=nonsense).failure())
    assert failure.setting == "answer_disposition"
    assert "one of consensus, human" in failure.detail


def test_a_per_item_label_lowers_to_human_but_cannot_raise_to_consensus(tmp_path: Path) -> None:
    """The asymmetry, asserted in BOTH directions against a global that would show a slip.

    Lowering runs against a `consensus` global, so honoring the label is the
    only way to read `human`. Raising runs against a `human` global, so
    honoring the label would be the only way to read `consensus`. One global
    would have made one of the two answers indistinguishable from doing nothing.
    """
    overrides = _overrides()
    opted_in = _write_config(
        tmp_path=tmp_path / "in", dispatcher={"answer_disposition": "consensus"}
    )
    conservative = _write_config(
        tmp_path=tmp_path / "out", dispatcher={"answer_disposition": "human"}
    )
    lowered = overrides.effective_answer_disposition(
        item=_item(), cwd=opted_in, raw_labels=("answer:human",)
    )
    raised = overrides.effective_answer_disposition(
        item=_item(), cwd=conservative, raw_labels=("answer:consensus",)
    )

    assert _read(lowered) == "human"
    assert _read(raised) == "human"


def test_an_unlabeled_or_junk_labeled_item_inherits_the_global(tmp_path: Path) -> None:
    """Only the literal `human` overrides; a typo falls through rather than refusing."""
    overrides = _overrides()
    opted_in = _write_config(tmp_path=tmp_path, dispatcher={"answer_disposition": "consensus"})

    assert _read(overrides.effective_answer_disposition(item=_item(), cwd=opted_in)) == "consensus"
    assert (
        _read(
            overrides.effective_answer_disposition(
                item=_item(), cwd=opted_in, raw_labels=("answer:humann",)
            )
        )
        == "consensus"
    )
