"""The durable-progress reading a resume takes BEFORE deciding to dispatch.

`contracts.md` section "Required result, budget and progress epoch":
"resume_directive MUST report missing, expired and unobservable tracking
findings. It MUST NOT automatically dispatch an exhausted or unobservable
obligation. An unattended expired resume MUST retain the obligation and expose
an authorized diagnosis/recovery action for the independent consumer. ... The
progress check MUST precede the unattended dispatch decision."

THIS READS THE CHAIN, NOT THE POINTER, and that is the whole reason the module
exists. The budget used to be read off the `next_action` metadata, which every
sanctioned writer rewrites wholesale — so the one fact a resume most needs to be
unable to lie about was stored exactly where a writer could hand it a new value.
A pointer carrying a far-future deadline and a zero handoff count is perfectly
well-formed, so a resume reading it reports a healthy obligation and dispatches
it, with nothing in the result to distinguish that from a correct reading.

EVERY ARM HERE IS READ-ONLY. "An expired wall clock MUST be visible even when no
new handoff is written", so reporting expiry cannot itself be a write — and the
chain's authority is what the next writer will read, so a reader that advanced
or cleared it would make the following reader see a healthy plan.

WITHHOLDING AND EXPOSING ARE TWO SEPARATE OBLIGATIONS, and this module answers
both because answering only the first leaves the independent consumer a dead
end. An expired or unobservable obligation yields `dispatch=False` for its OWN
action, plus an `authorized_action` that is executable: a still-bounded recorded
recovery attempt's own operation where one exists, and otherwise the
plan-progress diagnosis. A caller that returned no action at all would satisfy
"does not dispatch the exhausted obligation" while stalling the plan.

A RECORDED ATTEMPT IS HONOURED ONLY WHILE ITS OWN BOUND HOLDS. "A typed causal
attempt MAY restore bounded execution without resetting the original deadline" —
the bound is the attempt's, and an elapsed one authorizes nothing, because
otherwise the first attempt ever recorded would authorize its operation forever,
which is the self-renewing budget the clause forbids.

THE FINDING NAMES THE LIMIT, THE OBLIGATION AND THE REMEDY, because the three
have different remedies and an operator reading only "expired" cannot tell an
exhausted ceiling from a passed clock — nor which operation they are now
permitted to run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_continuation import instant_expired
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
    is_executable_operation,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNOBSERVABLE,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reader import read_result

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "TRACKING_EXPIRED",
    "TRACKING_MISSING",
    "TRACKING_UNOBSERVABLE",
    "ResumeProgress",
    "diagnosis_operation",
    "evaluate_resume_progress",
]

TRACKING_MISSING = "plan-progress-tracking: missing"
TRACKING_EXPIRED = "plan-progress-tracking: expired"
TRACKING_UNOBSERVABLE = "plan-progress-tracking: unobservable"

_ATTEMPT_FIELD = "attempt"
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
    observation = read_result(
        project_root=_project_root(config=config),
        reference=obligation.required_result,
        runner=ShellCommandRunner(),
        now=now,
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
    return _expired_progress(
        epic_id=epic_id,
        obligation=obligation,
        expiry=expiry,
        head=head,
        now=now,
    )


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


def _expired_progress(
    *,
    epic_id: str,
    obligation: Obligation,
    expiry: str,
    head: ChainHead,
    now: str,
) -> ResumeProgress:
    """An exhausted obligation, with whichever operation is still authorized."""
    prefix = (
        f"{TRACKING_EXPIRED}; limit={expiry}; deadline={obligation.original_deadline};"
        f" handoffs={obligation.consumed_handoffs}/{obligation.max_handoffs}"
    )
    attempt = _bounded_attempt(authority_record=head.authority.last_recovery_attempt, now=now)
    if attempt is None:
        return ResumeProgress(
            findings=(f"{prefix}; recovery={diagnosis_operation(epic_id=epic_id)}",),
            reason=f"the plan's required result expired at its {expiry} limit",
            dispatch=False,
            authorized_action=diagnosis_operation(epic_id=epic_id),
        )
    attempt_id, operation, attempt_deadline = attempt
    report = (
        f"{prefix}; authorized-recovery={attempt_id} until {attempt_deadline};"
        f" operation={operation}"
    )
    return ResumeProgress(
        findings=(report,),
        reason=f"bounded causal recovery attempt {attempt_id} is authorized",
        dispatch=False,
        authorized_action=operation,
    )


def _bounded_attempt(  # noqa: PLR0911 -- one fail-closed return per malformed shape; merging them loses which.
    *,
    authority_record: object,
    now: str,
) -> tuple[str, str, str] | None:
    """A recorded attempt's id, operation and bound, while that bound holds.

    Every arm fails CLOSED to `None`, which routes to a fresh diagnosis: the
    operation read here is one a consumer will EXECUTE, so an unreadable or
    unexecutable record must not become one. The operation is re-checked against
    the closed grammar rather than trusted, because the record is ledger data
    and a stored string is not evidence that it was ever validated.
    """
    if not isinstance(authority_record, dict):
        return None
    attempt = cast("dict[str, Any]", authority_record).get(_ATTEMPT_FIELD)
    if not isinstance(attempt, dict):
        return None
    fields = cast("dict[str, Any]", attempt)
    attempt_id = fields.get("attempt_id")
    operation = fields.get("next_operation")
    attempt_deadline = fields.get("attempt_deadline")
    if not isinstance(attempt_id, str) or attempt_id.strip() == "":
        return None
    if not isinstance(operation, str) or not is_executable_operation(operation=operation):
        return None
    if not isinstance(attempt_deadline, str):
        return None
    if instant_expired(until=attempt_deadline, now=now):
        return None
    return attempt_id, operation, attempt_deadline


def _project_root(*, config: StoreConfig) -> Path:
    root = config.repo_root
    return Path.cwd() if root is None else root
