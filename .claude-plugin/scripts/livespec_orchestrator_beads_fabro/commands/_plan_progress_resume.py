"""The durable-progress reading a resume takes BEFORE deciding to dispatch.

`contracts.md` section "Required result, budget and progress epoch":
"resume_directive MUST report missing, overdue and unobservable tracking
findings. A budget's deadline or handoff count MUST NOT change whether
resume_directive takes or presents an executable action ... It MUST NOT
automatically dispatch an unobservable obligation; an unattended unobservable
resume MUST retain the obligation and expose an authorized diagnosis action for
the independent consumer. ... The progress check MUST precede the unattended
dispatch decision."

THIS READS THE CHAIN, NOT THE POINTER. The budget used to be read off the
`next_action` metadata, which every sanctioned writer rewrites wholesale, so a
pointer carrying a far-future deadline would report a healthy obligation while
the chain recorded an overdue one. The overdue FINDING is still the chain's.

AN OVERDUE OBLIGATION IS REPORTED AND NEVER WITHHELD. The expiry rule that made
an exhausted budget withhold the pointer's own action and expose only
`diagnose-plan-progress` was deleted on the maintainer's 2026-11-03 ruling
("Whatever 'stall' rule is in effect here, completely delete it"). So the
overdue arm returns `dispatch=True` with its finding, and the only arms that
withhold are the ones that could not READ the obligation at all.

EVERY ARM HERE IS READ-ONLY. "An overdue obligation MUST be visible even when no
new handoff is written", so reporting it cannot itself be a write.

WITHHOLDING AND EXPOSING ARE TWO SEPARATE OBLIGATIONS for an UNREADABLE
obligation: it yields `dispatch=False` for its own action plus the executable
plan-progress diagnosis, because returning no action at all would stall the plan.

THE CHAIN-HELD OBLIGATION IS READ THROUGH THE SHARED PLAN-OWNED READER, for a
reason this module's position makes acute: `decide_plan_resume` RETURNS on this
reading's verdict, before the pointer is consulted at all. So an obligation that
names the plan epic itself under some other repository would be read here against
the wrong tenant, reported UNOBSERVABLE, and the plan locked for its whole budget
— and a redirect applied only at the pointer read never runs for any
chain-tracked plan. `read_plan_owned_result` is the one entry point every
plan-level reader takes, rather than this module composing the project root, the
redirect and `read_result` itself: that composition is a rule a reader has to
remember, and the only part of it that announces its own absence is the root.
`_plan_result_plan_owned` carries the measurement and owns the discrimination.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import ChainHead
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import ChainFinding
from livespec_orchestrator_beads_fabro.commands._plan_epoch_reconcile import authorized_head
from livespec_orchestrator_beads_fabro.commands._plan_obligation import (
    Obligation,
    obligation_expiry,
    obligation_of,
)
from livespec_orchestrator_beads_fabro.commands._plan_recovery import (
    DIAGNOSIS_OPERATION_PREFIX,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNOBSERVABLE,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_plan_owned import (
    read_plan_owned_result,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "TRACKING_MISSING",
    "TRACKING_OVERDUE",
    "TRACKING_UNOBSERVABLE",
    "ResumeProgress",
    "diagnosis_operation",
    "evaluate_resume_progress",
]

TRACKING_MISSING = "plan-progress-tracking: missing"
TRACKING_OVERDUE = "plan-progress-tracking: overdue"
TRACKING_UNOBSERVABLE = "plan-progress-tracking: unobservable"

_SANCTIONED_MIGRATION = "migrate-plan-records"
# The write that creates an obligation where a chain already stands. Named as
# the remedy for a PRESENT chain tracking nothing, because `migrate-plan-records`
# — the remedy for an ABSENT one — creates only the genesis token, and a second
# run of it on a migrated epic reports that the chain already stands and creates
# nothing at all. Pointing a reader at it there names a remedy that cannot clear
# the finding it is named for.
_SANCTIONED_POINTER_WRITE = (
    "an executable-kind next_action write carrying required_result and budget"
)


@dataclass(frozen=True, kw_only=True)
class ResumeProgress:
    """One read-only reading of a plan's durable obligation.

    `dispatch` is whether the pointer's OWN action may still be taken.
    `authorized_action` is what the independent consumer may run INSTEAD when it
    may not — never `None` alongside `dispatch=False` for a tracked obligation,
    because a withheld dispatch with no alternative is a stalled plan.
    """

    findings: tuple[str, ...] = ()
    reason: str | None = None
    dispatch: bool = True
    authorized_action: str | None = None


def diagnosis_operation(*, epic_id: str) -> str:
    """The authorized read-only diagnosis action for one plan epic."""
    return f"{DIAGNOSIS_OPERATION_PREFIX}{epic_id}"


def evaluate_resume_progress(
    *,
    config: StoreConfig,
    epic_id: str,
    now: str,
) -> ResumeProgress:
    """Read one plan's durable obligation and say what may still be dispatched.

    `authorized_head` rather than a bare chain read, because "A partial write
    MUST be diagnosable and must not authorize a fresh dispatch until
    reconciled" — a head withheld for an unreconciled projection must not
    license a dispatch, and this is the question a dispatch gate asks.
    """
    head = authorized_head(config=config, epic_id=epic_id)
    if isinstance(head, ChainFinding):
        return _chain_finding_progress(epic_id=epic_id, finding=head)
    obligation = obligation_of(authority=head.authority)
    if obligation is None:
        return _untracked_chain_progress(head=head)
    observation = read_plan_owned_result(
        config=config, epic_id=epic_id, required_result=obligation.required_result, now=now
    )
    if observation.status == OBSERVATION_UNOBSERVABLE:
        return _unobservable_progress(
            epic_id=epic_id,
            obligation=obligation,
            detail=observation.detail,
            source=observation.source,
        )
    if observation.status == OBSERVATION_SATISFIED:
        return ResumeProgress()
    expiry = obligation_expiry(obligation=obligation, now=now)
    if expiry is None:
        return ResumeProgress()
    return _overdue_progress(obligation=obligation, expiry=expiry)


def _chain_finding_progress(*, epic_id: str, finding: ChainFinding) -> ResumeProgress:
    """A chain nobody can read authorizes no dispatch, only a diagnosis.

    The MISSING finding is the legacy case and is reported as missing tracking;
    every other finding — a fork, an unreadable record, an unreconciled partial
    write — is reported as UNOBSERVABLE, because the obligation exists and this
    reader could not measure it. Collapsing the two would tell an operator with
    a forked chain to run a migration.
    """
    if finding.code.endswith("missing"):
        return _missing_progress()
    report = (
        f"{TRACKING_UNOBSERVABLE}; chain={finding.code}; detail={finding.detail};"
        f" remedy={finding.remedy}; recovery={diagnosis_operation(epic_id=epic_id)}"
    )
    return ResumeProgress(
        findings=(report,),
        reason=f"plan authority is unreadable: {finding.code}",
        dispatch=False,
        authorized_action=diagnosis_operation(epic_id=epic_id),
    )


def _missing_progress() -> ResumeProgress:
    """A legacy pointer stays READABLE and names the sanctioned migration.

    The ABSENT-chain case alone. A chain that reads cleanly while tracking
    nothing is reported by `_untracked_chain_progress` instead, because the two
    have different remedies and this one's — the migration that creates a
    genesis token — can do nothing for an epic that already has one.

    `dispatch` stays TRUE deliberately. "Legacy three-key pointers MUST remain
    readable, report `plan-progress-tracking: missing`, and acquire the new
    shape on their next sanctioned write; legacy reads alone MUST NOT invent
    budgets or mutate the ledger." A legacy plan has no expired obligation to
    withhold — it has no obligation at all — so withholding here would strand
    every unmigrated plan behind a finding rather than reporting one.
    """
    report = (
        f"{TRACKING_MISSING}; this plan epic carries no authority chain, so no required"
        f" result or budget is tracked; remedy={_SANCTIONED_MIGRATION}"
    )
    return ResumeProgress(
        findings=(report,),
        reason="plan progress tracking is missing",
    )


def _untracked_chain_progress(*, head: ChainHead) -> ResumeProgress:
    """A chain that READS CLEANLY and tracks nothing names the write that would.

    This is the state `create_genesis_token` and the sanctioned migration both
    leave behind: the walk reached an open token, and no transition has yet
    committed a required result or a budget. It is NOT the legacy case, and
    reporting it as one — which this arm did until `bd-ib-paevjd`, with
    `bd-ib-lrik25` as the live instance — tells an operator that the epic
    "carries no authority chain" while its chain is standing, and names a
    migration that has already run.

    The open token is NAMED rather than merely not denied, because "the chain
    is present" has to be checkable: a finding that only dropped the false
    sentence would leave a reader unable to tell a present-but-empty chain from
    one this reader never looked at.

    `dispatch` stays TRUE for exactly the reason the legacy arm's does: an
    obligation that does not exist cannot have expired, so there is nothing to
    withhold. Withholding here would strand every freshly migrated plan behind
    a finding rather than reporting one.
    """
    report = (
        f"{TRACKING_MISSING}; this plan epic's authority chain is present at epoch"
        f" {head.epoch} with open token {head.current_token_id}, and that authority"
        f" tracks no required result or budget; remedy={_SANCTIONED_POINTER_WRITE}"
    )
    return ResumeProgress(
        findings=(report,),
        reason="plan progress tracking is missing: the authority chain tracks no obligation",
    )


def _unobservable_progress(
    *,
    epic_id: str,
    obligation: Obligation,
    detail: str,
    source: str,
) -> ResumeProgress:
    """A result nobody could read preserves its budget and dispatches nothing."""
    report = (
        f"{TRACKING_UNOBSERVABLE}; deadline={obligation.original_deadline};"
        f" handoffs={obligation.consumed_handoffs}/{obligation.max_handoffs};"
        f" source={source}; detail={detail};"
        f" recovery={diagnosis_operation(epic_id=epic_id)}"
    )
    return ResumeProgress(
        findings=(report,),
        reason="the plan's required result is unobservable, so dispatch is withheld",
        dispatch=False,
        authorized_action=diagnosis_operation(epic_id=epic_id),
    )


def _overdue_progress(*, obligation: Obligation, expiry: str) -> ResumeProgress:
    """An overdue obligation is REPORTED, and its own action is still dispatchable."""
    report = (
        f"{TRACKING_OVERDUE}; limit={expiry}; deadline={obligation.original_deadline};"
        f" handoffs={obligation.consumed_handoffs}/{obligation.max_handoffs}"
    )
    return ResumeProgress(findings=(report,))
