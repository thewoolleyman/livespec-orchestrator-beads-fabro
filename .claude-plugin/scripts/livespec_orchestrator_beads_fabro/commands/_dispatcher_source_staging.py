"""Isolate the engine's pre-run push in a disposable, origin-proven worktree.

The pinned engine compares branch tips, so an ancestor primary still triggers
its push. A unique source branch at the verified HEAD gives that push a normal
worktree with the repository's hooks intact. It is never the publish branch.
The Fabro facade supplies this runner ONLY to its run operation. This adapter
knows no engine argv syntax; ledger reads, watchdog polls and post-merge work
keep their ordinary runner. Cleanup belongs to the staged subprocess lifetime.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_source_preflight import (
    source_checkout_preflight,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_ids import SOURCE_CHECKOUT
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_waivers import (
    resolve_step_waivers,
    waived_proceed_record,
    waiver_for,
)

__all__: list[str] = ["SourceStagingRunner"]

_GIT_TIMEOUT_SECONDS = 30.0


class _Launch(Protocol):
    def __call__(self, *, cwd: Path) -> CommandResult: ...


@dataclass(frozen=True, kw_only=True)
class SourceStagingRunner:
    """Run an invocation in this plan's source worktree; supplied to the run facade."""

    inner: CommandRunner
    plan: DispatchPlan
    journal: JournalWriter
    worktree_root: Path | None = None

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        def launch(*, cwd: Path) -> CommandResult:
            return self.inner.run(
                argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
            )

        if cwd != self.plan.repo:
            return launch(cwd=cwd)
        return self._staged_run(launch=launch)

    def _staged_run(self, *, launch: _Launch) -> CommandResult:
        # Re-prove at the staging boundary: the source can move after admission.
        outcome = source_checkout_preflight(repo=self.plan.repo, runner=self.inner)
        self.journal.append(record={**outcome.record, "work_item_id": self.plan.work_item_id})
        if outcome.refusal is not None:
            waiver = waiver_for(
                waivers=resolve_step_waivers(cwd=self.plan.repo), step=SOURCE_CHECKOUT
            )
            if waiver is not None:
                # A committed waiver retains its existing launch path. It is not
                # relabelled as an origin-proven staged source.
                self.journal.append(
                    record=waived_proceed_record(waiver=waiver, waived=outcome.record)
                )
                return launch(cwd=self.plan.repo)
            return CommandResult(exit_code=3, stdout="", stderr=outcome.refusal.detail)
        head = str(outcome.record["head"])
        suffix = uuid4().hex
        branch = f"livespec/source/{suffix}"
        root = self.worktree_root if self.worktree_root is not None else Path.home() / ".worktrees"
        checkout = root / self.plan.repo.name / f"fabro-source-{suffix}"
        created = self._git(argv=["worktree", "add", "-b", branch, str(checkout), head])
        self.journal.append(
            record={
                **outcome.record,
                "stage": "source-checkout-stage",
                "work_item_id": self.plan.work_item_id,
                "worktree": str(checkout),
                "branch": branch,
                "status": "passed" if created.exit_code == 0 else "failed",
                "reason": (
                    "source-worktree-created"
                    if created.exit_code == 0
                    else "source-worktree-create-failed"
                ),
                "terminal": created.exit_code != 0,
                "exit_code": created.exit_code,
                "detail": created.stderr,
            }
        )
        try:
            if created.exit_code != 0:
                return created
            return launch(cwd=checkout)
        finally:
            self._cleanup(checkout=checkout, branch=branch, head=head)

    def _cleanup(self, *, checkout: Path, branch: str, head: str) -> None:
        # Delete only the unique staging ref, and only if it still names the
        # source commit. Failed cleanup is journaled with its exact venue/ref.
        self._clean_remote(checkout=checkout, branch=branch, head=head)
        removed = self._git(argv=["worktree", "remove", "--force", str(checkout)])
        self._record(
            stage="source-checkout-remove", result=removed, checkout=checkout, branch=branch
        )
        if removed.exit_code == 0:
            deleted = self._git(argv=["update-ref", "-d", f"refs/heads/{branch}", head])
            self._record(
                stage="source-checkout-branch-remove",
                result=deleted,
                checkout=checkout,
                branch=branch,
            )

    def _clean_remote(self, *, checkout: Path, branch: str, head: str) -> None:
        ref = f"refs/heads/{branch}"
        observed = self._git(argv=["ls-remote", "--heads", "origin", ref])
        if observed.exit_code == 0 and not observed.stdout.strip():
            return
        result = observed
        if observed.exit_code == 0:
            if observed.stdout.split() == [head, ref]:
                # Keep hooks enabled. Deletion may run the same full check suite
                # as the engine's initial push, so it gets the launch's budget.
                result = self.inner.run(
                    argv=["git", "push", f"--force-with-lease={ref}:{head}", "origin", f":{ref}"],
                    cwd=checkout,
                    timeout_seconds=self.plan.fabro_timeout_seconds,
                )
            else:
                result = CommandResult(
                    exit_code=1, stdout="", stderr=f"staging ref {ref} changed; retained on origin"
                )
        self._record(
            stage="source-checkout-remote-remove", result=result, checkout=checkout, branch=branch
        )

    def _git(self, *, argv: list[str]) -> CommandResult:
        return self.inner.run(
            argv=["git", *argv], cwd=self.plan.repo, timeout_seconds=_GIT_TIMEOUT_SECONDS
        )

    def _record(self, *, stage: str, result: CommandResult, checkout: Path, branch: str) -> None:
        self.journal.append(
            record={
                "stage": stage,
                "work_item_id": self.plan.work_item_id,
                "worktree": str(checkout),
                "branch": branch,
                "exit_code": result.exit_code,
                "status": "passed" if result.exit_code == 0 else "failed",
                "detail": result.stderr,
            }
        )
