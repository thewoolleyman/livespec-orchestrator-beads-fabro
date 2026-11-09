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

A true resume is different: its recorded pull-request head is the continuation
base, not a candidate to compare with the default branch.  Before staging it,
the runner fetches the publish branch and proves that its fetched tip equals the
recorded head.  A bare object fetch is intentionally avoided because a forge may
decline it even when that object is reachable from the branch.  Failure names
the recorded head and prevents the engine from entering any workflow stage on a
default-branch worktree.

Both fetches land in a private per-staging ref that is read and then deleted,
never in `FETCH_HEAD`: that file is shared by every process fetching in the
checkout, so a concurrent fetch would overwrite the answer between the fetch and
the read.

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
    SourceCheckoutOutcome,
    source_checkout_preflight,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_source_target import (
    explicit_source_target_argv,
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
_REASON_RESUME_HEAD_UNOBSERVABLE = "source-resume-head-unobservable"


class _Launch(Protocol):
    def __call__(self, *, cwd: Path, argv: list[str] | None = None) -> CommandResult: ...


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
    # A resume (unlike a seeded recovery) continues from its own publish branch.
    # Both values are carried so the staging boundary can distinguish the two:
    # a seed's commit has a preservation ref and remains placed by its overlay.
    resume_head: str | None = None
    resume_fetch_ref: str | None = None

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        def launch(*, cwd: Path, argv: list[str] | None = None) -> CommandResult:
            return self.inner.run(
                argv=argv if argv is not None else original_argv,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                env=env,
                stdin=stdin,
            )

        original_argv = argv
        if cwd != self.plan.repo:
            return launch(cwd=cwd)
        return self._staged_run(launch=launch, argv=argv)

    def _staged_run(self, *, launch: _Launch, argv: list[str]) -> CommandResult:
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
        base = self._staging_base(head=head, suffix=suffix)
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
                "resume_head": self.resume_head,
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
            return launch(
                cwd=checkout, argv=self._launch_argv(argv=argv, outcome=outcome, base=base)
            )
        finally:
            self._cleanup(checkout=checkout, branch=branch, head=base.commit)

    def _staging_base(self, *, head: str, suffix: str) -> _StagingBase:
        """Freshly fetch the default branch and decide which commit to stage at."""
        if self.resume_head and not self.resume_fetch_ref:
            return self._resumed_staging_base(expected=self.resume_head, suffix=suffix)
        default_branch = self.plan.integration.contract.default_branch
        observed = self._fetched_tip(branch=default_branch, suffix=suffix)
        if observed.exit_code != 0:
            return _StagingBase(commit=head, origin_head="", failure=observed)
        origin_head = observed.stdout.strip()
        if origin_head == "":
            return _StagingBase(
                commit=head,
                origin_head="",
                failure=CommandResult(
                    exit_code=_UNREADABLE_ORIGIN_HEAD_EXIT,
                    stdout="",
                    stderr=(
                        f"fetched origin/{default_branch} but `git rev-parse` of the fetched "
                        "ref named no commit, so the staging base cannot be proven current: "
                        f"{observed.stderr.strip()}\n"
                    ),
                ),
            )
        if origin_head != head and self._behind(head=head, origin_head=origin_head):
            return _StagingBase(commit=origin_head, origin_head=origin_head, failure=None)
        return _StagingBase(commit=head, origin_head=origin_head, failure=None)

    def _fetched_tip(self, *, branch: str, suffix: str) -> CommandResult:
        """Fetch one origin branch into a private ref and read the commit it names.

        `FETCH_HEAD` is a single file per checkout, so a read of it is an answer
        about whichever process fetched last, not about THIS fetch. The private
        ref is unique to this staging, and it is deleted as soon as it has been
        read: the fetched objects stay for the `git worktree add` that follows.
        A failed fetch is returned as it came back.
        """
        ref = f"refs/livespec/staging/{suffix}"
        fetched = self._git(argv=["fetch", "--quiet", "origin", f"+refs/heads/{branch}:{ref}"])
        if fetched.exit_code != 0:
            return fetched
        observed = self._git(argv=["rev-parse", "--verify", f"{ref}^{{commit}}"])
        _ = self._git(argv=["update-ref", "-d", ref])
        return observed

    def _resumed_staging_base(self, *, expected: str, suffix: str) -> _StagingBase:
        """Fetch and prove the recorded pull-request head before staging it."""
        observed = self._fetched_tip(branch=self.plan.branch, suffix=suffix)
        actual = observed.stdout.strip()
        if observed.exit_code != 0 or actual != expected:
            detail = observed.stderr
            if observed.exit_code == 0:
                detail = f"origin/{self.plan.branch} resolved to {actual or '<no commit>'}"
            return _StagingBase(
                commit=expected,
                origin_head="",
                failure=self._resume_head_failure(expected=expected, detail=detail),
            )
        return _StagingBase(commit=expected, origin_head="", failure=None)

    def _resume_head_failure(self, *, expected: str, detail: str) -> CommandResult:
        return CommandResult(
            exit_code=_UNREADABLE_ORIGIN_HEAD_EXIT,
            stdout="",
            stderr=(
                "could not anchor resumed source checkout on pull-request head "
                f"{expected} from origin/{self.plan.branch}: {detail.strip()}\n"
            ),
        )

    def _behind(self, *, head: str, origin_head: str) -> bool:
        merge_base = self._git(argv=["merge-base", "--is-ancestor", head, origin_head])
        return merge_base.exit_code == 0

    def _launch_argv(
        self, *, argv: list[str], outcome: SourceCheckoutOutcome, base: _StagingBase
    ) -> list[str]:
        """Project this origin-proven staging result into the engine launch.

        The target names the branch the SELECTED staging base came from. When the
        fresh fetch moved the base to the default-branch head, the preflight's
        tracking ref can be a stale feature branch, and naming it would send the
        engine to an older tree than the one staged.
        """
        origin = self._git(argv=["config", "--get", "remote.origin.url"])
        origin_ref = str(outcome.record["origin_ref"])
        if base.origin_head != "" and base.commit == base.origin_head:
            origin_ref = f"origin/{self.plan.integration.contract.default_branch}"
        return explicit_source_target_argv(
            argv=argv,
            fabro_version=self.plan.fabro_version,
            origin_url=origin.stdout,
            origin_ref=origin_ref,
            # Only a RESUME owns a published branch. A SEEDED route also carries
            # a head, but its seed lives on a preservation ref and its publish
            # branch is not on origin, so it targets its staging base instead.
            resume_branch=(
                self.plan.branch if self.resume_head and not self.resume_fetch_ref else None
            ),
        )

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
        if base.failure.stderr.startswith("could not anchor resumed source checkout"):
            return _REASON_RESUME_HEAD_UNOBSERVABLE
        return _REASON_ORIGIN_HEAD_UNOBSERVABLE
    return _REASON_CREATED if created.exit_code == 0 else _REASON_CREATE_FAILED
