"""Branch coverage for dispatcher policy setting resolution."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TypeVar

from livespec_orchestrator_beads_fabro.commands import _dispatcher_policy_settings
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
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
    resolve_auto_approve_ready,
)
from livespec_orchestrator_beads_fabro.commands._drive_config_schema import config_key_by_name
from livespec_orchestrator_beads_fabro.types import WorkItem
from returns.io import IOResult
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


def test_availability_probe_timeout_is_committed_only_and_defaults_to_120(tmp_path: Path) -> None:
    """The confirmation probe uses a committed positive-integer timeout dial."""
    resolver_name = "resolve_availability_probe_timeout_seconds"

    assert resolver_name in _dispatcher_policy_settings.__all__
    resolve = _dispatcher_policy_settings.resolve_availability_probe_timeout_seconds
    configured = _write_config(
        tmp_path=tmp_path,
        text=(
            '{"livespec-orchestrator-beads-fabro": '
            '{"dispatcher": {"availability_probe_timeout_seconds": 45}}}'
        ),
    )

    assert _read(resolve(cwd=_NO_CONFIG_CWD)) == 120
    assert _read(resolve(cwd=configured)) == 45
    assert config_key_by_name(key="availability_probe_timeout_seconds") is None


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


def test_neither_a_commitment_hint_nor_a_plan_anchor_pins_the_admission_policy() -> None:
    """The repair of `bd-ib-yykjko`: the hint is not the tier, in either direction.

    This pair used to assert the opposite of its second half — a
    commitment-carrying item pinned to the `manual` floor — and that reading is
    the inverted predicate the plan-child-disposition clause of
    `SPECIFICATION/constraints.md` names outright: the two fields "are
    near-opposites", since a non-null `spec_commitment_hint` marks an
    implementation FOLLOW-UP to an ALREADY-RATIFIED change and is therefore
    ordinary dispatchable work. Pinning it held exactly the set that should be
    admitted while admitting every unratified feature.

    BOTH values are asserted to keep their own policy, which is what makes the
    case discriminating: a resolution that had merely swapped the two answers
    would satisfy one half and fail the other. The hold a genuine
    spec-change-tier item earns is applied where the RECORDED classification can
    be read — the filing route and the pre-dispatch wall — and is bound by
    `tests/integration/test_spec_change_tier_commitment_hint.py`.
    """
    anchored = _item(spec_commitment_hint=_PLAN_ANCHOR_MARKER, admission_policy="auto")
    committed = _item(spec_commitment_hint=_SPEC_CLAUSE_COMMITMENT, admission_policy="auto")

    assert _read(effective_admission_policy(item=anchored, cwd=_NO_CONFIG_CWD)) == "auto"
    assert _read(effective_admission_policy(item=committed, cwd=_NO_CONFIG_CWD)) == "auto"
    # A manual-admission item still rests for the approve valve, which is
    # Scenario 10's own subject and is untouched by the repair.
    manual = _item(spec_commitment_hint=_SPEC_CLAUSE_COMMITMENT, admission_policy="manual")
    assert _read(effective_admission_policy(item=manual, cwd=_NO_CONFIG_CWD)) == (
        DEFAULT_ADMISSION_POLICY
    )
