"""The seed an item's current seed ruling names, as a recovery route carries it.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" → "A ruled seed names the tree a
released item's next dispatch starts from": "When the ruled ref exists at the ruled
SHA and no non-fallback refusal applies, the route MUST be `seeded`, and the seed
record MUST name the ruled ref as its preservation reference and the ruled SHA as
its immutable commit. When the ruled ref is absent, or stands at a commit other
than the ruled SHA, the route MUST be `held`, and the `recovery-held` record MUST
name the ref, the ruled SHA and the observed commit, or the ref's absence. Routing
MUST NOT then fall through to another preserved tree, to the observed published
head, or to `fresh`. An unreadable ref is the existing unobservable-measurement
hold."

THE RULING IS READ OFF THE ITEM'S LEDGER COMMENTS, through the one reader of
rulings (`_dispatcher_ruling_currency`), and never off the journal: a ruling
written from another checkout leaves no journal record on this host.

THE REF IS READ FROM ORIGIN, AND ITS EXIT CODE IS CHECKED. `verify_seed_ruling`,
the writer's own check, folds a failed read into "absent" because a writer that
cannot reach origin refuses either way. Routing cannot: "absent" holds the item as
a ruling to repair, while an unanswered read holds it as a measurement to retry,
and the two have different remedies. Taking the second for the first sends an
operator to re-rule a ref that was never missing.

AN UNREADABLE LEDGER IS A HOLD, NOT AN ABSENT RULING, for the fault classes that
say the ledger itself could not be asked — the same reasoning as an unreadable
ref, since an unread comment list may hold the ruling that decides the route. That
includes a comments response that could not be mapped (`BeadsMappingError`): the
comments exist but were not read. The faults that say only that this repository has
no ledger to ask (no configured connection, a work-item id the tenant does not hold)
read as no ruling: every candidate
of every pass reaches this read, and a candidate that is no ledger row cannot
carry one.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    LEDGER_WRITE_ERRORS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_measurements import (
    MEASUREMENT_PRESERVED_WORK,
    MEASUREMENT_SEED_RULING_COMMENTS,
    MEASUREMENT_SEED_RULING_REF,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import SEED_REMOTE
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_published_head import (
    leading_identifier,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    RecoveryHold,
    RecoveryMeasurement,
    RecoverySeed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ruling_currency import (
    FreshRuling,
    current_ruling,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import (
    SeedRuling,
    observed_ref_commit,
    ruled_ref_mismatch_detail,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.store import read_work_item_comments
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "current_seed_ruling",
    "ruled_seed",
]

_GIT_TIMEOUT_SECONDS = 120.0

# The faults that say the ledger could not be ASKED, as against the ones that say there
# is no ledger row to ask about.
_LEDGER_UNASKABLE = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)
_LEDGER_UNREADABLE = (
    *LEDGER_WRITE_ERRORS,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)


def current_seed_ruling(
    *, repo: Path, item: WorkItem
) -> SeedRuling | FreshRuling | RecoveryHold | None:
    """The ruling that governs this item, a comments-read hold, or `None`."""
    comments = attempt(
        action=lambda: read_work_item_comments(path=store_config(repo=repo), work_item_id=item.id),
        exceptions=_LEDGER_UNREADABLE,
    )
    if isinstance(comments, AttemptFailure):
        if isinstance(comments.error, _LEDGER_UNASKABLE):
            return RecoveryHold(
                measurements=(
                    RecoveryMeasurement(
                        name=MEASUREMENT_SEED_RULING_COMMENTS,
                        detail=(
                            f"the ledger comments of {item.id} could not be read "
                            f"({type(comments.error).__name__}: {comments.error}), so whether "
                            "a seed ruling governs its next dispatch could not be established"
                        ),
                    ),
                )
            )
        return None
    return current_ruling(comments=tuple(one.text for one in comments))


def ruled_seed(
    *,
    runner: CommandRunner,
    repo: Path,
    ruling: SeedRuling,
    earlier_run_ids: tuple[str, ...],
) -> RecoverySeed | RecoveryHold:
    """The seed a ruling names when origin carries its ref at its SHA; otherwise the hold."""
    result = runner.run(
        argv=["git", "ls-remote", SEED_REMOTE, ruling.preservation_ref],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return _hold(
            name=MEASUREMENT_PRESERVED_WORK,
            detail=(
                f"git ls-remote {SEED_REMOTE} {ruling.preservation_ref} exited {result.exit_code}; "
                f"whether the ruled seed ref stands at {ruling.commit_sha} could not be "
                "established, so no seed was taken and absence is not confirmed"
            ),
        )
    observed = observed_ref_commit(stdout=result.stdout, ref=ruling.preservation_ref)
    if observed != ruling.commit_sha:
        return _hold(
            name=MEASUREMENT_SEED_RULING_REF,
            detail=ruled_ref_mismatch_detail(ruling=ruling, observed=observed),
        )
    return RecoverySeed(
        source_run_id=leading_identifier(identifiers=earlier_run_ids),
        remote=SEED_REMOTE,
        commit_sha=ruling.commit_sha,
        preservation_ref=ruling.preservation_ref,
    )


def _hold(*, name: str, detail: str) -> RecoveryHold:
    """A hold naming one measurement; the item is not seeded from anywhere else."""
    return RecoveryHold(measurements=(RecoveryMeasurement(name=name, detail=detail),))
