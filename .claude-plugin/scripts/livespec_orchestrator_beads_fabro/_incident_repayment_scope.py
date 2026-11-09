"""What one normal repayment carrier owes, and the flags it must never inherit.

Pure. The scope is read off the recorded incident attempt: the marker the
expedited repair left beside its code or tests, the cumulative original paths,
the landed commits the deferred validation replays, and the recorded deferred
debt. Validation names each obligation still outstanding rather than grading
marker removal alone, because acceptance receives the original change and
evidence corpus plus the follow-up, not the diff that deleted a comment.
"""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt

__all__: list[str] = [
    "INCIDENT_FLAGS",
    "RepaymentScope",
    "RepaymentValidation",
    "incident_flags_delta",
    "incident_marker",
    "repayment_brief",
    "repayment_scope",
    "scrub_incident_flags",
    "validate_repayment_carrier",
]

# The two incident execution flags. A normal dispatch removes both BEFORE
# provider selection and before any sandbox, hook or pull-request execution,
# whatever value they carry: a malformed inherited value is removed, never
# parsed, because a normal run has no incident mode to resolve it into.
INCIDENT_FLAGS: tuple[str, ...] = (
    "EXPEDITED_INCIDENT_RESPONSE",
    "EXPEDITED_INCIDENT_RESPONSE_REVERT",
)
_MARKER_PREFIX = "EXPEDITED_INCIDENT_RESPONSE flag: "


@dataclass(frozen=True, kw_only=True)
class RepaymentScope:
    """The cumulative original incident scope one repayment carrier must cover."""

    item_id: str
    marker: str
    repair_pr_number: int
    original_paths: tuple[str, ...]
    landed_commits: tuple[str, ...]
    deferred_work: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class RepaymentValidation:
    """The named obligations a repayment carrier still owes; empty means complete."""

    outstanding: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """True only when nothing of the cumulative scope remains outstanding."""
        return not self.outstanding


def incident_marker(*, item_id: str) -> str:
    """The exact code/test marker an expedited repair leaves beside its change."""
    return _MARKER_PREFIX + item_id


def repayment_scope(*, attempt: IncidentAttempt) -> RepaymentScope:
    """Read the cumulative scope the repayment carrier owes off a recorded attempt."""
    return RepaymentScope(
        item_id=attempt.item_id,
        marker=incident_marker(item_id=attempt.item_id),
        repair_pr_number=attempt.pr_number,
        original_paths=attempt.original_paths,
        landed_commits=attempt.landed_commits,
        deferred_work=attempt.deferred_work,
    )


def validate_repayment_carrier(
    *,
    scope: RepaymentScope,
    marker_paths: Iterable[str],
    validated_paths: Iterable[str],
    repaid_debt: Iterable[str],
) -> RepaymentValidation:
    """Name every obligation the carrier's head tree and evidence leave outstanding.

    `marker_paths` are the paths of the carrier's head tree that still carry the
    marker; `validated_paths` are the original paths the run's normal validation
    exercised; `repaid_debt` names the deferred work the carrier discharged.
    """
    validated = frozenset(validated_paths)
    repaid = frozenset(repaid_debt)
    outstanding = [f"marker-present:{path}" for path in sorted(marker_paths)]
    outstanding += [
        f"original-path-unvalidated:{path}"
        for path in scope.original_paths
        if path not in validated
    ]
    outstanding += [
        f"deferred-debt-outstanding:{work}" for work in scope.deferred_work if work not in repaid
    ]
    return RepaymentValidation(outstanding=tuple(outstanding))


def repayment_brief(*, scope: RepaymentScope, marker_paths: tuple[str, ...] | None = ()) -> str:
    """The brief a repayment run carries: what to remove and what to exercise.

    `marker_paths` are the paths still carrying the marker where the brief was
    written; `None` means that scan could not be taken, which the brief says
    rather than rendering as "no path carries it".
    """
    lines = [
        (
            f"Normal factory repayment of incident {scope.item_id} "
            f"(expedited repair merged as PR #{scope.repair_pr_number})."
        ),
        f"Remove every `{scope.marker}` marker from the code and tests.",
        *_marker_path_lines(marker=scope.marker, marker_paths=marker_paths),
        (
            f"The repayment pull request MUST leave no file carrying `{scope.marker}`: "
            "it is not accepted while any file at its head still does."
        ),
        "Exercise the cumulative original incident paths under normal validation:",
        *(f"- {path}" for path in scope.original_paths),
        "Replay deferred validation over the landed commits:",
        *(f"- {commit}" for commit in scope.landed_commits),
        "Repay the recorded deferred debt:",
        *(f"- {work}" for work in scope.deferred_work),
    ]
    return "\n".join(lines) + "\n"


def _marker_path_lines(*, marker: str, marker_paths: tuple[str, ...] | None) -> list[str]:
    if marker_paths is None:
        unread = (
            f"The paths still carrying `{marker}` could not be read when this brief was written;"
        )
        return [f"{unread} find every one with `git grep -l -F -e '{marker}'`."]
    if not marker_paths:
        return [f"No path was found carrying `{marker}` on the default branch."]
    return [
        f"Paths that still carry `{marker}` on the default branch:",
        *map("- {}".format, marker_paths),
    ]


def scrub_incident_flags(*, environ: MutableMapping[str, str]) -> tuple[str, ...]:
    """Remove both incident flags from `environ`, whatever they hold; return what was removed."""
    removed = tuple(name for name in INCIDENT_FLAGS if name in environ)
    for name in removed:
        del environ[name]
    return removed


def incident_flags_delta() -> dict[str, str | None]:
    """The subprocess environment delta that removes both flags unconditionally."""
    return dict.fromkeys(INCIDENT_FLAGS)
