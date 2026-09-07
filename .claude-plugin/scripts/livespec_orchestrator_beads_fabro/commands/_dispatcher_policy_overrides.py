"""Per-item overrides of the `dispatcher.*` policy settings.

Split out of `_dispatcher_policy_settings.py`, which keeps the
`.livespec.jsonc` reads of the GLOBAL defaults. The seam is the contract's
own structure rather than a line count: the dispatcher-policy-settings
contract in SPECIFICATION/contracts.md says each setting is a global default
and that a per-item ledger label overrides the global default for that one
work-item. Those are two questions with two inputs — the repository's
committed configuration, and this item's raw labels — and only the second one
needs a `WorkItem`. `_dispatcher_reconcile_runs_grace.py` named this seam as
the split that module was owed.

The overrides are NOT uniform, which is the reason they are worth reading
rather than pattern-matching:

- The three rework caps and `merge_on_review_cap` take the label's value
  whenever it parses, in either direction, and fall through to the global
  when it does not.
- `admission_policy` is floored: a design-human-gated (spec-change-tier)
  item takes the manual default whatever its label says.
- `groom_cut_approval` is ASYMMETRIC. Its label MAY only LOWER an item to
  `human` and MUST NOT raise one to `consensus`, so a repository opts INTO
  the automated groom cut once, in committed configuration a reviewer can
  see, and a single item can then only be more conservative than that. A
  `groom-cut-approval:consensus` label is therefore not an override at all —
  it is ignored and the item takes the global. A generic cap-shaped override
  would honor it, which is precisely the mistake this asymmetry exists to
  prevent.
- `answer_disposition` is asymmetric in exactly the same shape and for the
  same reason, so it is deliberately spelled the same way rather than
  generalized: the two settings share an asymmetry today, and folding them
  into one helper would make a future divergence in either a silent change to
  the other.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from returns.io import IOResult, IOSuccess

from livespec_orchestrator_beads_fabro._store_answer_disposition import (
    ANSWER_DISPOSITION_LABEL_PREFIX,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_ADMISSION_POLICY,
    DEFAULT_ANSWER_DISPOSITION,
    DEFAULT_GROOM_CUT_APPROVAL,
    PolicySettingUnreadable,
    resolve_acceptance_mode,
    resolve_acceptance_rework_cap,
    resolve_answer_disposition,
    resolve_auto_approve_ready,
    resolve_automated_regroom_cap,
    resolve_groom_cut_approval,
    resolve_merge_on_review_cap,
    resolve_review_fix_cap,
)
from livespec_orchestrator_beads_fabro.commands._plan_anchor import is_spec_commitment

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "ACCEPTANCE_REWORK_CAP_LABEL",
    "AUTOMATED_REGROOM_CAP_LABEL",
    "GROOM_CUT_APPROVAL_LABEL",
    "MERGE_ON_REVIEW_CAP_LABEL",
    "REVIEW_FIX_CAP_LABEL",
    "effective_acceptance_policy",
    "effective_acceptance_rework_cap",
    "effective_admission_policy",
    "effective_answer_disposition",
    "effective_automated_regroom_cap",
    "effective_groom_cut_approval",
    "effective_merge_on_review_cap",
    "effective_review_fix_cap",
]

_AUTO_ADMISSION = "auto"
MERGE_ON_REVIEW_CAP_LABEL = "merge-on-review-cap:"
REVIEW_FIX_CAP_LABEL = "review-fix-cap:"
ACCEPTANCE_REWORK_CAP_LABEL = "acceptance-rework-cap:"
AUTOMATED_REGROOM_CAP_LABEL = "automated-regroom-cap:"
GROOM_CUT_APPROVAL_LABEL = "groom-cut-approval:"


def effective_admission_policy(
    *, item: WorkItem, cwd: Path
) -> IOResult[str, PolicySettingUnreadable]:
    """The item's effective admission policy with per-item-over-global precedence."""
    if _is_spec_change_tier(item=item):
        return IOSuccess(DEFAULT_ADMISSION_POLICY)
    if item.admission_policy is not None:
        return IOSuccess(item.admission_policy)
    return resolve_auto_approve_ready(cwd=cwd).map(
        lambda auto: _AUTO_ADMISSION if auto else DEFAULT_ADMISSION_POLICY
    )


def effective_acceptance_policy(
    *, item: WorkItem, cwd: Path
) -> IOResult[str, PolicySettingUnreadable]:
    """The item's effective acceptance policy with per-item-over-global precedence."""
    if item.acceptance_policy is not None:
        return IOSuccess(item.acceptance_policy)
    return resolve_acceptance_mode(cwd=cwd)


def effective_merge_on_review_cap(
    *, item: WorkItem, cwd: Path, raw_labels: Sequence[str] = ()
) -> IOResult[bool, PolicySettingUnreadable]:
    """Resolve `merge_on_review_cap`, with a raw per-item label overriding global."""
    _ = item
    label_value = _raw_label_value(raw_labels=raw_labels, prefix=MERGE_ON_REVIEW_CAP_LABEL)
    parsed = _bool_label_value(value=label_value)
    if parsed is not None:
        return IOSuccess(parsed)
    return resolve_merge_on_review_cap(cwd=cwd)


def effective_review_fix_cap(
    *, item: WorkItem, cwd: Path, raw_labels: Sequence[str] = ()
) -> IOResult[int, PolicySettingUnreadable]:
    """Resolve `review_fix_cap`, with a raw per-item label overriding global."""
    _ = item
    label_value = _raw_label_value(raw_labels=raw_labels, prefix=REVIEW_FIX_CAP_LABEL)
    parsed = _positive_int_label_value(value=label_value)
    if parsed is not None:
        return IOSuccess(parsed)
    return resolve_review_fix_cap(cwd=cwd)


def effective_acceptance_rework_cap(
    *, item: WorkItem, cwd: Path, raw_labels: Sequence[str] = ()
) -> IOResult[int, PolicySettingUnreadable]:
    """Resolve `acceptance_rework_cap`, with a raw per-item label overriding global."""
    _ = item
    label_value = _raw_label_value(raw_labels=raw_labels, prefix=ACCEPTANCE_REWORK_CAP_LABEL)
    parsed = _positive_int_label_value(value=label_value)
    if parsed is not None:
        return IOSuccess(parsed)
    return resolve_acceptance_rework_cap(cwd=cwd)


def effective_automated_regroom_cap(
    *, item: WorkItem, cwd: Path, raw_labels: Sequence[str] = ()
) -> IOResult[int, PolicySettingUnreadable]:
    """Resolve `automated_regroom_cap`, with a raw per-item label overriding global."""
    _ = item
    label_value = _raw_label_value(raw_labels=raw_labels, prefix=AUTOMATED_REGROOM_CAP_LABEL)
    parsed = _positive_int_label_value(value=label_value)
    if parsed is not None:
        return IOSuccess(parsed)
    return resolve_automated_regroom_cap(cwd=cwd)


def effective_groom_cut_approval(
    *, item: WorkItem, cwd: Path, raw_labels: Sequence[str] = ()
) -> IOResult[str, PolicySettingUnreadable]:
    """Resolve `groom_cut_approval`; a per-item label may only LOWER to `human`.

    The one label value that overrides anything is `human`, and it is exactly
    the safe default. Every other label — `consensus` above all, but equally a
    typo or an empty value — falls through to the repository's committed
    setting, so no item can raise itself above what the repository opted into.
    """
    _ = item
    label_value = _raw_label_value(raw_labels=raw_labels, prefix=GROOM_CUT_APPROVAL_LABEL)
    if label_value == DEFAULT_GROOM_CUT_APPROVAL:
        return IOSuccess(DEFAULT_GROOM_CUT_APPROVAL)
    return resolve_groom_cut_approval(cwd=cwd)


def effective_answer_disposition(
    *, item: WorkItem, cwd: Path, raw_labels: Sequence[str] = ()
) -> IOResult[str, PolicySettingUnreadable]:
    """Resolve `answer_disposition`; a per-item label may only LOWER to `human`.

    The item's `answer:<human|consensus>` label when it says `human`, else the
    global `dispatcher.answer_disposition`. Everything else about the label —
    `consensus` above all, but equally a typo or an empty value — falls through
    to the repository's committed setting, so no single item can raise itself
    above what the repository opted into.
    """
    _ = item
    label_value = _raw_label_value(raw_labels=raw_labels, prefix=ANSWER_DISPOSITION_LABEL_PREFIX)
    if label_value == DEFAULT_ANSWER_DISPOSITION:
        return IOSuccess(DEFAULT_ANSWER_DISPOSITION)
    return resolve_answer_disposition(cwd=cwd)


def _raw_label_value(*, raw_labels: Sequence[str], prefix: str) -> str | None:
    for label in raw_labels:
        if label.startswith(prefix):
            return label[len(prefix) :]
    return None


def _bool_label_value(*, value: str | None) -> bool | None:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _positive_int_label_value(*, value: str | None) -> int | None:
    if value is None or not value.isdecimal():
        return None
    parsed = int(value)
    if parsed > 0:
        return parsed
    return None


def _is_spec_change_tier(*, item: WorkItem) -> bool:
    # A plan ANCHOR MARKER shares `spec_commitment_hint` with a genuine
    # commitment to ratified spec text, so presence is not the question: a
    # plan-anchored item pinned to the manual admission floor here is a
    # misrouting, not a gate.
    return is_spec_commitment(spec_id=item.spec_commitment_hint)
