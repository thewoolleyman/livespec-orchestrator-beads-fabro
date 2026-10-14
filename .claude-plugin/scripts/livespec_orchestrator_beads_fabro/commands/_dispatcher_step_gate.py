"""The pre-dispatch gate for the closed step set: preflights, waivers, persistence.

One entry point, `step_discipline_refusal`, runs the whole discipline for a
dispatch: each pre-dispatch preflight in turn, then the cross-dispatch
persistence check for any degraded post-merge outcome still standing. It returns
the operator-facing refusal text when the dispatch must not proceed, and None
when it may -- having journaled, either way, every outcome it produced.

WHY THE PREFLIGHTS ARE YIELDED LAZILY. A refusal must stop the sequence: the
master-CI preflight makes forge calls, and running them after the source
checkout has already refused spends network on an answer nobody will read.
A generator gives sequential evaluation without a hand-rolled early-return
ladder that would have to be re-read every time a fourth step is ratified.

WHY THE PERSISTENCE CHECK RUNS LAST. Its re-verification for a pre-dispatch step
is that step's own preflight passing THIS dispatch, so it has to run after them.
That is also the honest reading: those two steps verify themselves on every
dispatch, and `janitor-bootstrap` -- which cannot, because it only observes
after a merge -- gets the explicit recipe-presence check instead.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight import (
    master_ci_preflight,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_wait import (
    master_ci_wait,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_install_recipe import (
    hook_install_recipe_present,
    recipe_resolution_sentence,
    resolve_janitor_bootstrap_recipe,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import journal_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_source_preflight import (
    source_checkout_preflight,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_ids import (
    JANITOR_BOOTSTRAP,
    MASTER_CI,
    SOURCE_CHECKOUT,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_persistence import (
    DegradedStepOutcome,
    clearing_record,
    outstanding_degraded_step,
    persistence_refusal_detail,
    persistence_refusal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_waivers import (
    StepWaiver,
    resolve_step_waivers,
    waived_proceed_detail,
    waived_proceed_record,
    waiver_for,
)
from livespec_orchestrator_beads_fabro.io import write_stderr

__all__: list[str] = ["step_discipline_refusal"]


class StepRefusalLike(Protocol):
    """The shape every pre-dispatch refusal shares: what to print, what to journal."""

    @property
    def detail(self) -> str:
        """The operator-facing refusal text."""
        ...

    @property
    def record(self) -> dict[str, object]:
        """The journal record for the refusal."""
        ...


class StepOutcomeLike(Protocol):
    """A pre-dispatch preflight verdict: always a record, a refusal when it refused."""

    @property
    def refusal(self) -> StepRefusalLike | None:
        """The refusal, or None when the step passed."""
        ...

    @property
    def record(self) -> dict[str, object]:
        """The journal record, carried on both arms."""
        ...


def step_discipline_refusal(
    *, args: argparse.Namespace, repo: Path, identity: InvokerIdentity
) -> str | None:
    """Run the closed step set's pre-dispatch discipline; refusal text, or None."""
    path = journal_path(args=args, repo=repo)
    journal = JournalFile(path=path, identity=identity)
    waivers = resolve_step_waivers(cwd=repo)
    verified: set[str] = set()
    for step, outcome in _pre_dispatch_outcomes(repo=repo, waivers=waivers):
        journal.append(record=outcome.record)
        if outcome.refusal is None:
            verified.add(step)
            continue
        waiver = waiver_for(waivers=waivers, step=step)
        if waiver is None:
            return outcome.refusal.detail
        _journal_waived(journal=journal, waiver=waiver, waived=outcome.refusal.record)
    return _persistence_refusal(
        repo=repo,
        journal=journal,
        journal_path=path,
        waivers=waivers,
        verified=frozenset(verified),
    )


def _pre_dispatch_outcomes(
    *, repo: Path, waivers: tuple[StepWaiver, ...]
) -> Iterator[tuple[str, StepOutcomeLike]]:
    """Each pre-dispatch step's outcome, evaluated only when it is reached.

    The master-CI step is handed its own WAIT, resolved from the waivers this
    gate has already read, because that step now waits for a still-running
    default-branch run: the ratified clause keeps a committed `master-ci`
    waiver ahead of that wait, which it can only be if the waiver is known
    before the preflight starts rather than consulted after it returns.
    """
    runner = ShellCommandRunner()
    yield SOURCE_CHECKOUT, source_checkout_preflight(repo=repo, runner=runner)
    yield (
        MASTER_CI,
        master_ci_preflight(
            repo=repo,
            runner=runner,
            wait=master_ci_wait(waived=waiver_for(waivers=waivers, step=MASTER_CI) is not None),
        ),
    )


def _persistence_refusal(
    *,
    repo: Path,
    journal: JournalFile,
    journal_path: Path,
    waivers: tuple[StepWaiver, ...],
    verified: frozenset[str],
) -> str | None:
    """Refuse while a degraded post-merge outcome stands, unless cleared or waived."""
    degraded = outstanding_degraded_step(journal_path=journal_path)
    if degraded is None:
        return None
    provided, resolution = _reverified(repo=repo, degraded=degraded, verified=verified)
    if provided:
        journal.append(record=clearing_record(degraded=degraded))
        return None
    refusal = persistence_refusal_record(degraded=degraded, resolution=resolution)
    waiver = waiver_for(waivers=waivers, step=degraded.step)
    if waiver is not None:
        _journal_waived(journal=journal, waiver=waiver, waived=refusal)
        return None
    journal.append(record=refusal)
    return persistence_refusal_detail(degraded=degraded, resolution=resolution)


def _reverified(
    *, repo: Path, degraded: DegradedStepOutcome, verified: frozenset[str]
) -> tuple[bool, str | None]:
    """Whether this dispatch observes the degraded step's integration point provided.

    The second element is the re-verification's account of WHICH resolution it
    attempted, which only a declaration-resolved integration point has to give.
    It rides back with the verdict rather than being re-derived by the refusal
    because a second resolution could name a different recipe from the one
    actually looked for.
    """
    if degraded.step == JANITOR_BOOTSTRAP:
        recipe = resolve_janitor_bootstrap_recipe(cwd=repo)
        return (
            hook_install_recipe_present(repo=repo, recipe=recipe),
            recipe_resolution_sentence(recipe=recipe),
        )
    return degraded.step in verified, None


def _journal_waived(*, journal: JournalFile, waiver: StepWaiver, waived: dict[str, object]) -> None:
    """Journal the waived proceed with its owner, and say so on stderr."""
    journal.append(record=waived_proceed_record(waiver=waiver, waived=waived))
    _ = write_stderr(text=waived_proceed_detail(waiver=waiver))
