"""Isolate the engine's pre-run push in a disposable, origin-proven worktree.

The pinned engine compares branch tips, so an ancestor primary still triggers
its push. A unique source branch gives that push a normal worktree with the
repository's hooks intact. It is never the publish branch. The Fabro facade
supplies this runner ONLY to its run operation. This adapter knows no engine
argv syntax; ledger reads, watchdog polls and post-merge work keep their
ordinary runner. Cleanup belongs to the staged subprocess lifetime.

THE BRANCH IS STAGED AT THE FRESHLY FETCHED DEFAULT-BRANCH HEAD whenever the
dispatching checkout sits strictly behind it. Staging at the checkout's own
HEAD was not enough: that push runs the repository's push gates, and a commit
the primary happens to rest on is not a commit those gates are green for, so
an owner who had not fast-forwarded saw the engine's pre-run push refused and
the run die before its first node. The fetch is what makes the base CURRENT
rather than merely origin-reachable -- a local `origin/*` tracking ref names
whatever this clone's last fetch left, which is an answer about fetch state
reported as a fact about the branch.

An origin head that cannot be READ fails the staging closed. Falling back to
the checkout's HEAD there would reinstate exactly the defect above, and would
do it on the one path where nothing in the record says the base went unproven.
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

# A fetch that reported success while naming no commit leaves the staging base
# unproven exactly as a failed fetch does, so it is rendered as a failure in its
# own right rather than inherited from a `git rev-parse` that exited 0.
_UNREADABLE_ORIGIN_HEAD_EXIT = 1

_REASON_CREATED = "source-worktree-created"
_REASON_CREATE_FAILED = "source-worktree-create-failed"
_REASON_ORIGIN_HEAD_UNOBSERVABLE = "source-origin-head-unobservable"


class _Launch(Protocol):
    def __call__(self, *, cwd: Path) -> CommandResult: ...


@dataclass(frozen=True, kw_only=True)
class _StagingBase:
    """Which commit the source branch is created at, and the head that decided it.

    `origin_head` is the freshly fetched default-branch head and `commit` is
    what the branch is actually staged at; the two differ whenever the
    dispatching checkout was NOT strictly behind origin, which is why both are
    carried rather than one being inferred from the other.
    """

    commit: str
    origin_head: str
    failure: CommandResult | None


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
        base = self._staging_base(head=head)
        created = (
            base.failure
            if base.failure is not None
            else self._git(argv=["worktree", "add", "-b", branch, str(checkout), base.commit])
        )
        self.journal.append(
            record={
                **outcome.record,
                "stage": "source-checkout-stage",
                "work_item_id": self.plan.work_item_id,
                "worktree": str(checkout),
                "branch": branch,
                # BOTH heads, always. `head` (from the preflight record) is the
                # dispatching checkout's; these two are the fetched
                # default-branch head and the commit the branch was actually
                # created at. A record carrying one of the three cannot say
                # what the engine's pre-run push carried, which is the first
                # question a refused push raises.
                "default_branch_head": base.origin_head,
                "staged_at": base.commit,
                "status": "passed" if created.exit_code == 0 else "failed",
                "reason": _stage_reason(base=base, created=created),
                "terminal": created.exit_code != 0,
                "exit_code": created.exit_code,
                "detail": created.stderr,
            }
        )
        if base.failure is not None:
            # Nothing was created, so there is nothing to clean up -- and the
            # cleanup legs would journal their own failures against a worktree
            # and a ref that never existed.
            return base.failure
        try:
            if created.exit_code != 0:
                return created
            return launch(cwd=checkout)
        finally:
            self._cleanup(checkout=checkout, branch=branch, head=base.commit)

    def _staging_base(self, *, head: str) -> _StagingBase:
        """Freshly fetch the default branch and decide which commit to stage at."""
        default_branch = self.plan.integration.contract.default_branch
        fetched = self._git(argv=["fetch", "--quiet", "origin", default_branch])
        if fetched.exit_code != 0:
            return _StagingBase(commit=head, origin_head="", failure=fetched)
        observed = self._git(argv=["rev-parse", "FETCH_HEAD"])
        origin_head = observed.stdout.strip()
        if origin_head == "":
            return _StagingBase(
                commit=head,
                origin_head="",
                failure=CommandResult(
                    exit_code=_UNREADABLE_ORIGIN_HEAD_EXIT,
                    stdout="",
                    stderr=(
                        f"fetched origin/{default_branch} but `git rev-parse FETCH_HEAD` named "
                        "no commit, so the staging base cannot be proven current: "
                        f"{observed.stderr.strip()}\n"
                    ),
                ),
            )
        if origin_head != head and self._behind(head=head, origin_head=origin_head):
            return _StagingBase(commit=origin_head, origin_head=origin_head, failure=None)
        return _StagingBase(commit=head, origin_head=origin_head, failure=None)

    def _behind(self, *, head: str, origin_head: str) -> bool:
        merge_base = self._git(argv=["merge-base", "--is-ancestor", head, origin_head])
        return merge_base.exit_code == 0

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


def _stage_reason(*, base: _StagingBase, created: CommandResult) -> str:
    """Why the staging stage reads as it does; the two failures are NOT the same.

    An unobservable origin head and a refused `git worktree add` both leave no
    worktree, and the remedies have nothing in common -- one is a fetch that
    could not be taken, the other a checkout that could not be created.
    """
    if base.failure is not None:
        return _REASON_ORIGIN_HEAD_UNOBSERVABLE
    return _REASON_CREATED if created.exit_code == 0 else _REASON_CREATE_FAILED
