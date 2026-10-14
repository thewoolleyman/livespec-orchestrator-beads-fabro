"""Branch coverage for dispatcher policy setting resolution."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TypeVar

from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    _is_spec_change_tier,
    effective_acceptance_rework_cap,
    effective_admission_policy,
    effective_merge_on_review_cap,
    effective_review_fix_cap,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_ACCEPTANCE_REWORK_CAP,
    DEFAULT_ADMISSION_POLICY,
    DEFAULT_MERGE_ON_REVIEW_CAP,
    DEFAULT_REVIEW_FIX_CAP,
    DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT,
    resolve_auto_approve_ready,
    resolve_session_headroom_floor_percent,
)
from livespec_orchestrator_beads_fabro.types import WorkItem
from returns.io import IOResult
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

_NO_CONFIG_CWD = Path("tests/nonexistent-policy-cwd")

# The two values that share `spec_commitment_hint`. The commitment fixture
# is a bare obligation slug, the shape the Spec Reader parses out of
# proposed-change front-matter; the anchor is what `create_thread` stamps.
_SPEC_CLAUSE_COMMITMENT = "contracts-dispatcher-admission"
_PLAN_ANCHOR_MARKER = "plan:codex-yolo-sandbox"

_Value = TypeVar("_Value")


def _read(outcome: IOResult[_Value, object]) -> _Value:
    """The value out of a successful policy read.

    `unsafe_perform_io` is mandatory rather than decorative: `IOResult.unwrap`
    yields `IO[value]`, and comparing that wrapper to `False`/`3` passes
    nothing and fails everything.
    """
    return unsafe_perform_io(outcome.unwrap())


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

    assert _read(resolve_auto_approve_ready(cwd=cwd)) is False


def test_raw_boolean_false_label_beats_true_global(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text=(
            '{"livespec-orchestrator-beads-fabro": '
            '{"dispatcher": {"merge_on_review_cap": true}}}'
        ),
    )

    assert (
        _read(
            effective_merge_on_review_cap(
                item=_item(), cwd=cwd, raw_labels=("merge-on-review-cap:false",)
            )
        )
        is False
    )


def test_invalid_raw_labels_without_config_fall_back_to_safe_defaults() -> None:
    assert (
        _read(
            effective_merge_on_review_cap(
                item=_item(),
                cwd=_NO_CONFIG_CWD,
                raw_labels=("merge-on-review-cap:sometimes",),
            )
        )
        is DEFAULT_MERGE_ON_REVIEW_CAP
    )
    assert (
        _read(
            effective_review_fix_cap(
                item=_item(), cwd=_NO_CONFIG_CWD, raw_labels=("review-fix-cap:0",)
            )
        )
        == DEFAULT_REVIEW_FIX_CAP
    )
    assert (
        _read(
            effective_acceptance_rework_cap(
                item=_item(), cwd=_NO_CONFIG_CWD, raw_labels=("acceptance-rework-cap:nope",)
            )
        )
        == DEFAULT_ACCEPTANCE_REWORK_CAP
    )


def test_unrelated_raw_labels_without_config_fall_back_to_safe_defaults() -> None:
    labels = ("merge-on-review-cap-extra:true", "review-fix-cap-extra:7")

    assert (
        _read(effective_merge_on_review_cap(item=_item(), cwd=_NO_CONFIG_CWD, raw_labels=labels))
        is False
    )
    assert (
        _read(effective_review_fix_cap(item=_item(), cwd=_NO_CONFIG_CWD, raw_labels=labels))
        == DEFAULT_REVIEW_FIX_CAP
    )
    assert (
        _read(effective_acceptance_rework_cap(item=_item(), cwd=_NO_CONFIG_CWD, raw_labels=labels))
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
        _read(
            effective_merge_on_review_cap(
                item=_item(), cwd=cwd, raw_labels=("merge-on-review-cap:sometimes",)
            )
        )
        is True
    )
    assert (
        _read(effective_review_fix_cap(item=_item(), cwd=cwd, raw_labels=("review-fix-cap:nope",)))
        == 6
    )
    assert (
        _read(
            effective_acceptance_rework_cap(
                item=_item(), cwd=cwd, raw_labels=("acceptance-rework-cap:0",)
            )
        )
        == 7
    )


def test_spec_change_tier_is_the_commitment_not_the_plan_anchor() -> None:
    """A plan anchor marker rides the same field; only a real commitment is that tier."""
    assert _is_spec_change_tier(item=_item(spec_commitment_hint=_PLAN_ANCHOR_MARKER)) is False
    assert _is_spec_change_tier(item=_item(spec_commitment_hint=_SPEC_CLAUSE_COMMITMENT)) is True


def test_a_plan_anchored_item_keeps_its_own_admission_policy() -> None:
    """The routing consequence: only a real commitment is pinned to the manual floor."""
    anchored = _item(spec_commitment_hint=_PLAN_ANCHOR_MARKER, admission_policy="auto")
    committed = _item(spec_commitment_hint=_SPEC_CLAUSE_COMMITMENT, admission_policy="auto")

    assert _read(effective_admission_policy(item=anchored, cwd=_NO_CONFIG_CWD)) == "auto"
    assert (
        _read(effective_admission_policy(item=committed, cwd=_NO_CONFIG_CWD))
        == DEFAULT_ADMISSION_POLICY
    )


def test_the_session_headroom_floor_accepts_its_whole_inclusive_range(tmp_path: Path) -> None:
    """`0` and `100` are VALUES, and an unconfigured read answers with 20.

    `0` is the case worth asserting: it is the clause's own way of disabling
    both headroom skips while keeping the reading, so a reader that treated it
    as "unset" would silently restore the default floor and skip candidates the
    operator asked it to admit.
    """
    assert _read(resolve_session_headroom_floor_percent(cwd=_NO_CONFIG_CWD)) == (
        DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT
    )
    for configured in (0, 100):
        directory = tmp_path / f"floor-{configured}"
        directory.mkdir()
        cwd = _write_config(
            tmp_path=directory,
            text=(
                '{"livespec-orchestrator-beads-fabro": '
                f'{{"dispatcher": {{"session_headroom_floor_percent": {configured}}}}}}}'
            ),
        )
        assert _read(resolve_session_headroom_floor_percent(cwd=cwd)) == configured


def test_a_floor_above_a_hundred_is_unreadable_rather_than_clamped(tmp_path: Path) -> None:
    """An unmeetable floor is the operator's config being wrong, not a value.

    Clamping would honour a floor nobody wrote; admitting it would refuse every
    covered candidate forever, since no reading can leave more than 100 percent
    of an allowance remaining. The refusal names the inclusive range, which is
    what tells this setting's message apart from every open-ended `>=` one.
    """
    cwd = _write_config(
        tmp_path=tmp_path,
        text=(
            '{"livespec-orchestrator-beads-fabro": '
            '{"dispatcher": {"session_headroom_floor_percent": 101}}}'
        ),
    )
    outcome = resolve_session_headroom_floor_percent(cwd=cwd)

    assert not is_successful(outcome)
    failure = unsafe_perform_io(outcome.failure())
    assert failure.setting == "session_headroom_floor_percent"
    assert "from 0 through 100 inclusive" in failure.detail
