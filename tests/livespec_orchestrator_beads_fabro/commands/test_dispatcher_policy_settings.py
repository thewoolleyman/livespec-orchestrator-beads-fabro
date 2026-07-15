"""Branch coverage for dispatcher policy setting resolution."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_ACCEPTANCE_REWORK_CAP,
    DEFAULT_MERGE_ON_REVIEW_CAP,
    DEFAULT_REVIEW_FIX_CAP,
    effective_acceptance_rework_cap,
    effective_merge_on_review_cap,
    effective_review_fix_cap,
    resolve_auto_approve_ready,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-policy",
        type="task",
        status="ready",
        title="A ready task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)


def _write_config(*, tmp_path: Path, text: str) -> Path:
    _ = (tmp_path / ".livespec.jsonc").write_text(text, encoding="utf-8")
    return tmp_path


def test_boolean_setting_reads_explicit_false(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text=(
            '{"livespec-orchestrator-beads-fabro": '
            '{"dispatcher": {"auto_approve_ready": false}}}'
        ),
    )

    assert resolve_auto_approve_ready(cwd=cwd) is False


def test_raw_boolean_false_label_beats_true_global(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text=(
            '{"livespec-orchestrator-beads-fabro": '
            '{"dispatcher": {"merge_on_review_cap": true}}}'
        ),
    )

    assert (
        effective_merge_on_review_cap(
            item=_item(), cwd=cwd, raw_labels=("merge-on-review-cap:false",)
        )
        is False
    )


def test_invalid_raw_labels_without_config_fall_back_to_safe_defaults() -> None:
    assert (
        effective_merge_on_review_cap(item=_item(), raw_labels=("merge-on-review-cap:sometimes",))
        is DEFAULT_MERGE_ON_REVIEW_CAP
    )
    assert (
        effective_review_fix_cap(item=_item(), raw_labels=("review-fix-cap:0",))
        == DEFAULT_REVIEW_FIX_CAP
    )
    assert (
        effective_acceptance_rework_cap(item=_item(), raw_labels=("acceptance-rework-cap:nope",))
        == DEFAULT_ACCEPTANCE_REWORK_CAP
    )


def test_unrelated_raw_labels_without_config_fall_back_to_safe_defaults() -> None:
    labels = ("merge-on-review-cap-extra:true", "review-fix-cap-extra:7")

    assert effective_merge_on_review_cap(item=_item(), raw_labels=labels) is False
    assert effective_review_fix_cap(item=_item(), raw_labels=labels) == DEFAULT_REVIEW_FIX_CAP
    assert (
        effective_acceptance_rework_cap(item=_item(), raw_labels=labels)
        == DEFAULT_ACCEPTANCE_REWORK_CAP
    )


def test_invalid_raw_labels_with_config_fall_back_to_global_values(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text=(
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": {'
            '"merge_on_review_cap": true,'
            '"review_fix_cap": 6,'
            '"acceptance_rework_cap": 7'
            "}}}"
        ),
    )

    assert (
        effective_merge_on_review_cap(
            item=_item(), cwd=cwd, raw_labels=("merge-on-review-cap:sometimes",)
        )
        is True
    )
    assert effective_review_fix_cap(item=_item(), cwd=cwd, raw_labels=("review-fix-cap:nope",)) == 6
    assert (
        effective_acceptance_rework_cap(
            item=_item(), cwd=cwd, raw_labels=("acceptance-rework-cap:0",)
        )
        == 7
    )
