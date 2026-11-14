"""Recovery routing's reseed step: a `seeded` route's seed, moved onto the default branch.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" → "A seed is moved onto the
current default branch before its run starts" governs every route that would
otherwise be `seeded`, "whether the seed comes from the preference order above or
from a current seed ruling". Routing applies these rules in the order written and
the first that matches decides:

- the seed's tree is its merge base's tree: it carries no work, the route is
  `fresh`, and the `recovery-route` record lists the seed as passed over with the
  reason `no-change`;
- the seed's merge base IS the tip: the seed is used unchanged;
- otherwise the seed is moved onto the tip by the diff-apply reseed
  (`_dispatcher_recovery_reseed`), and the seed record names the reseed commit and
  its ref;
- a reseed whose apply conflicts holds the item under `seed-reseed-conflict`.

THE STEP SITS AFTER THE ROUTE IS DECIDED, NOT INSIDE EACH SEEDED CONSTRUCTOR. Three
places build a `seeded` route (the fallback ladder, a current seed ruling and the
protected resume), and the paragraph governs them all alike, so one function that
takes a finished route and returns the route the run will actually take is the
only shape under which a fourth constructor cannot forget it.

THE TIP IS READ ONCE PER ROUTING PASS. The paragraph requires the default branch's
tip "once per routing pass, shared by every item the pass routes", so the reader is
a value the pass creates and hands to every item, and a reading that could not be
taken is remembered too: the next item must not spend a second round trip to learn
the same thing, and must not be held for a different reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import SEED_REMOTE
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    recovery_held_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_reseed import (
    ReseedUnobservable,
    SeedCarriesNoWork,
    reseed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_HELD,
    ROUTE_SEEDED,
    RecoveryHold,
    RecoveryMeasurement,
    RecoveryRoute,
    ReseedConflict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import observed_ref_commit

__all__: list[str] = [
    "MEASUREMENT_SEED_RESEED",
    "REFUSAL_SEED_RESEED_CONFLICT",
    "DefaultBranchTipReader",
    "reseed_route",
]

MEASUREMENT_SEED_RESEED = "seed-reseed"
REFUSAL_SEED_RESEED_CONFLICT = "seed-reseed-conflict"

_GIT_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True, kw_only=True)
class _DefaultTip:
    """The default branch's name and the commit it stood at when this pass read it."""

    branch: str
    commit: str


@dataclass(kw_only=True)
class DefaultBranchTipReader:
    """One routing pass's single reading of the default branch's tip."""

    _reading: _DefaultTip | ReseedUnobservable | None = field(default=None, init=False)

    def read(self, *, runner: CommandRunner, repo: Path) -> _DefaultTip | ReseedUnobservable:
        """The tip, read on the first call and remembered for the rest of the pass."""
        if self._reading is None:
            self._reading = _read_tip(runner=runner, repo=repo)
        return self._reading


def _read_tip(*, runner: CommandRunner, repo: Path) -> _DefaultTip | ReseedUnobservable:
    """Resolve the default branch, then ask origin where it stands."""
    branch = resolve_default_branch(repo=repo, runner=runner)
    if branch is None:
        return ReseedUnobservable(
            detail="the repository's default branch could not be resolved from git or the forge"
        )
    ref = f"refs/heads/{branch}"
    listed = runner.run(
        argv=["git", "ls-remote", SEED_REMOTE, ref], cwd=repo, timeout_seconds=_GIT_TIMEOUT_SECONDS
    )
    commit = observed_ref_commit(stdout=listed.stdout, ref=ref) if listed.exit_code == 0 else None
    if commit is None:
        return ReseedUnobservable(
            detail=f"git ls-remote {SEED_REMOTE} {ref} did not name the default branch's tip"
        )
    return _DefaultTip(branch=branch, commit=commit)


def reseed_route(
    *,
    route: RecoveryRoute,
    tip_reader: DefaultBranchTipReader,
    runner: CommandRunner,
    repo: Path,
    journal: JournalFile,
) -> RecoveryRoute:
    """The route the run will take: a `seeded` route's seed moved onto the tip, or its outcome."""
    seed = route.seed
    if route.route != ROUTE_SEEDED or seed is None:
        return route
    tip = tip_reader.read(runner=runner, repo=repo)
    outcome = (
        tip
        if isinstance(tip, ReseedUnobservable)
        else reseed(
            runner=runner,
            repo=repo,
            work_item_id=route.work_item_id,
            seed=seed,
            branch=tip.branch,
            tip=tip.commit,
        )
    )
    if isinstance(outcome, SeedCarriesNoWork):
        return RecoveryRoute(
            work_item_id=route.work_item_id,
            route=ROUTE_FRESH,
            passed_over_needs_human=route.passed_over_needs_human,
            passed_over_no_change=((seed.preservation_ref, seed.commit_sha),),
        )
    if isinstance(outcome, ReseedUnobservable | ReseedConflict):
        hold = (
            RecoveryHold(
                measurements=(
                    RecoveryMeasurement(name=MEASUREMENT_SEED_RESEED, detail=outcome.detail),
                )
            )
            if isinstance(outcome, ReseedUnobservable)
            else RecoveryHold(refusals=(REFUSAL_SEED_RESEED_CONFLICT,), reseed_conflict=outcome)
        )
        journal.append(record=recovery_held_record(work_item_id=route.work_item_id, hold=hold))
        return RecoveryRoute(work_item_id=route.work_item_id, route=ROUTE_HELD, hold=hold)
    return replace(route, seed=outcome)
