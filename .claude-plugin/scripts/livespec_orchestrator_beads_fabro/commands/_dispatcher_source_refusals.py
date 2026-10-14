"""How a source-checkout preflight outcome READS: its operator text and its record.

Split out of `_dispatcher_source_preflight` along the same cohesion seam its
master-CI sibling uses: DECIDING an outcome -- the git reads and the
classification -- stays there, and SAYING it is all this module does.

EVERY OUTCOME IS A RECORD HERE, including the pass. A step whose success left no
trace would make the journal unable to answer "did this step run?", which is the
question an audit of a refusal that did NOT happen has to ask. The pass is a
sanctioned outcome in its own right, so it is journaled like the other two.

AND EVERY RECORD CARRIES THE STEP IDENTIFIER. The stage name says what ran; the
step id is what a waiver entry, a degraded outcome and a clearing record all
match on, and prose is not matchable.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_ids import SOURCE_CHECKOUT
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_waivers import WAIVER_ESCAPE

__all__: list[str] = [
    "NOT_A_WORKTREE_REMEDY",
    "STAGE",
    "UNPUSHED_REMEDY",
    "SourceCheckoutOutcome",
    "SourceCheckoutRefusal",
    "not_a_worktree_outcome",
    "pass_outcome",
    "unreachable_outcome",
]

STAGE = "source-checkout-origin-reachability"

_REASON_REACHABLE = "source-head-origin-reachable"
_REASON_UNREACHABLE = "source-head-not-origin-reachable"
_REASON_NOT_A_WORKTREE = "source-checkout-not-a-git-worktree"

UNPUSHED_REMEDY = (
    "preserve the unpushed commit(s) on a branch/worktree and publish from that "
    "worktree before dispatching. For an ancestor checkout, fast-forward to its "
    "origin tracking ref. Do not push from the "
    "primary checkout; the commit-refuse hook correctly forbids that path"
)

NOT_A_WORKTREE_REMEDY = (
    "point the dispatch at a real Git checkout of the target repository (check "
    f"`--repo`, and that the path is a clone rather than an export), {WAIVER_ESCAPE}"
)


@dataclass(frozen=True, kw_only=True)
class SourceCheckoutRefusal:
    """Terminal source-checkout preflight refusal, ready to emit and journal."""

    detail: str
    record: dict[str, object]


@dataclass(frozen=True, kw_only=True)
class SourceCheckoutOutcome:
    """A preflight verdict: always a journal record, plus a refusal when it refused."""

    refusal: SourceCheckoutRefusal | None
    record: dict[str, object]


def pass_outcome(
    *, head: str, origin_refs: tuple[str, ...], origin_ref: str
) -> SourceCheckoutOutcome:
    """HEAD is contained by an origin ref: dispatch proceeds, and the pass is journaled."""
    return SourceCheckoutOutcome(
        refusal=None,
        record={
            **_identity(),
            "terminal": False,
            "status": "passed",
            "reason": _REASON_REACHABLE,
            "head": head,
            "origin_ref": origin_ref,
            "origin_refs": list(origin_refs),
        },
    )


def not_a_worktree_outcome(*, repo: str) -> SourceCheckoutOutcome:
    """The dispatch target is not a Git worktree, so origin reachability is UNPROVABLE.

    This is a refusal rather than a skip because absence of proof is refusal.
    The step exists to prove the base Fabro will stage is reachable from origin,
    and a path with no git worktree to interrogate cannot answer that question
    either way -- proceeding on it is the fail-open this discipline retires,
    just wearing "not applicable" as its disguise.
    """
    cause = (
        f"{repo} is not a Git worktree, so the base Fabro would stage cannot be "
        "proven reachable from any origin ref"
    )
    return _refusing(
        reason=_REASON_NOT_A_WORKTREE,
        cause=cause,
        remedy=NOT_A_WORKTREE_REMEDY,
        record_fields={"repo": repo},
        detail=(
            "ERROR: the dispatch target is not a Git worktree; origin reachability "
            "cannot be verified, so the dispatch is refused before sandbox work.\n"
            f"Target: {repo}\n"
            f"Reason: {cause}\n"
            f"Remedy: {NOT_A_WORKTREE_REMEDY}.\n"
        ),
    )


def unreachable_outcome(
    *,
    head: str,
    origin_refs: tuple[str, ...],
    unpushed: tuple[str, ...],
    push: CommandResult,
) -> SourceCheckoutOutcome:
    """HEAD is not contained by any origin ref: refuse, naming the unpushed work."""
    commits = "\n".join(f"  {commit}" for commit in unpushed)
    detail = (
        "ERROR: source checkout HEAD is not reachable from any origin ref; "
        "refusing dispatch before sandbox work.\n"
        f"HEAD: {head or '<unknown>'}\n"
        "Unpushed commit(s):\n"
        f"{commits}\n"
        "Pre-clone source push outcome (dry-run):\n"
        f"{_push_outcome_text(push=push)}\n"
        f"Remedy: {UNPUSHED_REMEDY}.\n"
    )
    return _refusing(
        reason=_REASON_UNREACHABLE,
        cause="HEAD is not an ancestor of any `origin/*` ref",
        remedy=UNPUSHED_REMEDY,
        record_fields={
            "head": head,
            "origin_refs": list(origin_refs),
            "unpushed_commits": list(unpushed),
            "push_outcome": {
                "exit_code": push.exit_code,
                "stdout": push.stdout,
                "stderr": push.stderr,
            },
        },
        detail=detail,
    )


def _refusing(
    *,
    reason: str,
    cause: str,
    remedy: str,
    record_fields: dict[str, object],
    detail: str,
) -> SourceCheckoutOutcome:
    record: dict[str, object] = {
        **_identity(),
        "terminal": True,
        "status": "failed",
        "reason": reason,
        "detail": cause,
        **record_fields,
        "remedy": remedy,
    }
    # The SAME record object on both arms, as on the master-CI sibling: the
    # caller journals `outcome.record` unconditionally, so a refusal whose two
    # records could drift would journal one thing and print another.
    return SourceCheckoutOutcome(
        refusal=SourceCheckoutRefusal(detail=detail, record=record), record=record
    )


def _identity() -> dict[str, object]:
    """The keys every source-checkout journal record carries, pass or refusal alike."""
    return {"stage": STAGE, "step": SOURCE_CHECKOUT}


def _push_outcome_text(*, push: CommandResult) -> str:
    stdout = push.stdout.strip() or "<empty stdout>"
    stderr = push.stderr.strip() or "<empty stderr>"
    return f"  exit_code={push.exit_code}\n  stdout={stdout}\n  stderr={stderr}"
