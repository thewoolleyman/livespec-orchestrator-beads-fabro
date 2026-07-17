"""Side-effecting orchestration for the Dispatcher's staged self-update + canary.

Work-item livespec-impl-beads-ddu; the 0jxs operability precondition. This
module is the ORCHESTRATION half of the staged-self-update layer; its PURE
decision + parsing half — self-merge detection, the canary verdict, the
promotion decision, and the `gh pr view` parsing — lives in
`_dispatcher_self_update_decision`, whose module docstring carries the full
0jxs hazard narrative (a self-merge that pulls impl-beads's OWN primary can
swap the running dispatcher's code out from under it, BRICKING the loop) and
the fix shape (pinned execution copy, staged self-update, canary-before-promote).

What lives HERE is everything the pure layer deliberately does NOT touch — the
side effects, driven by injected seams so the hermetic test tier can exercise
every branch WITHOUT a real fabro run (the self-machinery hang-guard):

  * **The post-verdict stage entry.** `self_update_after_verdict` runs AFTER the
    wave's verdict is final (alongside the cost gate / reflection / ntfy-alarm
    stages), FAIL-OPEN, and for each green self-merge candidate reads the merged
    file list and drives `self_update_after_merge`.
  * **The fail-open staged-promote body.** `self_update_after_merge` wraps
    `_self_update` in a broad supervisor (any error is journaled as
    `self-update-error` and swallowed — the load-bearing 0jxs invariant that the
    stage can never change a computed verdict or crash the dispatcher);
    `_self_update` guards the read-only-cache path, runs the candidate's canary
    self-check subprocess through the injected `CommandRunner`, promotes on a
    passing canary, and ALARMS through h1p's `notify_terminal` seam on a failing
    one.
  * **The canary target.** `candidate_dispatcher_bin` resolves the just-pulled
    primary's own `bin/dispatcher.py`.
  * **The credential-runner seam.** `github_token_supplier` /
    `post_verdict_runner` / `_github_token_error_supplier` resolve the GitHub
    App-token supplier from the wrapper-injected env and wrap the post-verdict
    subprocess runner so it re-mints `GH_TOKEN` before spawning; `run_id` is a
    non-credential-bearing correlation id.

Credential hygiene mirrors the notifier / cost gate: the alarm body ships ONLY
the work-item id + outcome class + run id, and the App-token supplier is
resolved from the dispatch target's configured `credential_wrapper` env — never
a fleet PAT or an ambient `gh` login.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from livespec_runtime.github_auth.config import load_github_app_config
from livespec_runtime.github_auth.errors import GithubAppAuthError
from livespec_runtime.github_auth.provider import InstallationTokenProvider

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GithubTokenEnvRunner,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_notify import (
    HttpNotifyPoster,
    NotifyEvent,
    NotifyPoster,
    notify_terminal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update_decision import (
    DISPATCHER_SCRIPT_PREFIXES,
    SELF_UPDATE_BREACH_CLASS,
    CanaryVerdict,
    PromotionDecision,
    canary_self_check_argv,
    canary_verdict,
    is_self_merge,
    parse_pr_files,
    pr_files_argv,
    promotion_decision,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "DISPATCHER_SCRIPT_PREFIXES",
    "SELF_UPDATE_BREACH_CLASS",
    "CanaryVerdict",
    "PromotionDecision",
    "canary_self_check_argv",
    "canary_verdict",
    "candidate_dispatcher_bin",
    "github_token_supplier",
    "is_self_merge",
    "parse_pr_files",
    "post_verdict_runner",
    "pr_files_argv",
    "promotion_decision",
    "run_id",
    "self_update_after_merge",
    "self_update_after_verdict",
]

_CANARY_TIMEOUT_SECONDS = 300.0


class SelfUpdateJournal(Protocol):
    """The append-only journal seam the self-update stage records through.

    Structurally typed (no subclassing): any object with a keyword-only
    `append(record=...)` method satisfies it — the production `JournalFile`
    and the hermetic test tier's in-memory recorder alike. The stage records
    only leak-free scalar `stage` / `work_item_id` / `reason` fields.
    """

    def append(self, *, record: dict[str, object]) -> None: ...


def github_token_supplier() -> Callable[[], str] | str:
    """Resolve the App-token supplier from the wrapper-injected env (fail-closed).

    Returns the caching `InstallationTokenProvider`'s `token` accessor
    (Pillar 1: callable at any time by any factory process; re-mints
    transparently past the 55-minute horizon), or the actionable refusal
    detail when the GitHub App env (GITHUB_APP_ID + GITHUB_PRIVATE_KEY)
    is absent. The dispatch TARGET's configured credential_wrapper is
    the ONLY credential source (Pillar 2): a missing App env is a hard
    refusal routed as data at the `github-app-auth` stage — NEVER a
    silent fall-through to a fleet PAT or an ambient `gh` login.
    """
    config = attempt(
        action=lambda: load_github_app_config(environ=os.environ),
        exceptions=(GithubAppAuthError,),
    )
    if isinstance(config, AttemptFailure):
        exc = cast("GithubAppAuthError", config.error)
        return f"C-mode dispatch refused: {exc.detail}"
    return InstallationTokenProvider(config=config).token


def _github_token_error_supplier(*, detail: str) -> Callable[[], str]:
    """Adapt an accessor-resolution failure to the runner's fail-closed seam."""

    def _raise_github_token_error() -> str:
        raise GithubAppAuthError(detail=detail)

    return _raise_github_token_error


def post_verdict_runner(
    *,
    runner: CommandRunner | None,
    token_supplier: Callable[[], str] | None = None,
) -> CommandRunner:
    """Resolve the post-verdict subprocess runner with first-class remint.

    Production default runners must refresh `GH_TOKEN` through the provider
    accessor before spawning. Injected runners keep their historic behavior
    unless the test or caller explicitly passes a supplier to prove wrapping.
    """
    resolved_runner: CommandRunner = runner if runner is not None else ShellCommandRunner()
    resolved_supplier = token_supplier
    if resolved_supplier is None and runner is None:
        supplier_or_error = github_token_supplier()
        resolved_supplier = (
            _github_token_error_supplier(detail=supplier_or_error)
            if isinstance(supplier_or_error, str)
            else supplier_or_error
        )
    if resolved_supplier is None:
        return resolved_runner
    return GithubTokenEnvRunner(inner=resolved_runner, token=resolved_supplier)


def self_update_after_verdict(
    *,
    repo: Path,
    outcomes: list[DispatchOutcome],
    journal: SelfUpdateJournal,
    runner: CommandRunner | None = None,
    token_supplier: Callable[[], str] | None = None,
    poster: NotifyPoster | None = None,
) -> None:
    """Run the staged-self-update gate after the verdict is final (work-item ddu).

    Called AFTER the wave's verdict / exit code is computed (alongside the
    cost gate / reflection / ntfy-alarm stages) and FAIL-OPEN: the whole
    stage is wrapped in a broad supervisor, so a `gh pr view` failure, an
    unparseable payload, or ANY exception is journaled as
    `self-update-error` and swallowed — it can never change a computed
    verdict or crash the dispatcher (the load-bearing 0jxs invariant).

    For each GREEN outcome carrying a PR number (a confirmed self-merge
    candidate), it reads the merged file list (`gh pr view <branch> --json
    files`) and runs `self_update_after_merge`: a merge that touched the
    dispatcher's OWN scripts CANARIES the just-pulled candidate and only
    PROMOTES it on a passing canary, else keeps the last-known-good copy
    and alarms. The candidate is the just-pulled primary's own
    `bin/dispatcher.py`; the canary scratch root is a throwaway temp dir.
    `runner` / `poster` are injectable for the hermetic test tier.
    """
    from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import resolve_merged_paths

    resolved_runner = post_verdict_runner(runner=runner, token_supplier=token_supplier)
    resolved_poster = poster if poster is not None else HttpNotifyPoster()
    for outcome in outcomes:
        if outcome.status != "green" or outcome.pr_number is None:
            continue
        merged_paths = resolve_merged_paths(repo=repo, runner=resolved_runner)
        self_update_after_merge(
            work_item_id=outcome.work_item_id,
            merged_paths=merged_paths,
            candidate_bin=str(candidate_dispatcher_bin()),
            scratch_root=tempfile.mkdtemp(prefix=f"self-update-canary-{outcome.work_item_id}-"),
            repo=repo,
            journal=journal,
            runner=resolved_runner,
            poster=resolved_poster,
        )


def candidate_dispatcher_bin() -> Path:
    """The just-pulled primary's own `bin/dispatcher.py` (the canary target).

    Resolved off the plugin root (the same anchor `workflow_toml` uses):
    after `_post_merge` pulls the primary, this path holds the STAGED new
    dispatcher code, which the canary self-checks before it can take over the
    loop.
    """
    from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import plugin_root

    return plugin_root() / "scripts" / "bin" / "dispatcher.py"


def self_update_after_merge(  # noqa: PLR0913 - kw-only fail-open stage; fields are caller inputs.
    *,
    work_item_id: str,
    merged_paths: tuple[str, ...],
    candidate_bin: str,
    scratch_root: str,
    repo: Path,
    journal: SelfUpdateJournal,
    runner: CommandRunner | None = None,
    poster: NotifyPoster | None = None,
) -> None:
    """Stage + canary a self-merge before it can take over (work-item ddu).

    The dispatcher-self-update hazard: `_post_merge` pulls the target
    repo's primary, and when the target IS impl-beads itself that pull
    swaps the running dispatcher's code. This stage, run AFTER a confirmed
    merge, FIRST skips cleanly when there is no writable orchestrator
    checkout to promote into (a read-only plugin cache — the
    self-contained-dispatch / adopter path), then gates the swap: when the
    merge touched the dispatcher's OWN scripts (`is_self_merge`), it
    CANARIES the staged candidate (the
    candidate's own cheap, side-effect-free `ledger-check` self-check —
    NEVER a real fabro run, per the self-machinery hang-guard) and only
    PROMOTES it to the active pinned copy on a passing canary; a failing
    canary keeps the last-known-good pinned copy and ALARMS through h1p's
    `notify_terminal` seam (`self-update-canary-failed` class).

    FAIL-OPEN, mirroring `_cost_gate_after_verdict`: the whole body is
    wrapped in a broad supervisor, so a canary subprocess failure, an
    unexpected payload, or ANY exception is journaled as
    `self-update-error` and swallowed — it can never crash the dispatcher
    or masquerade as a promotion (the load-bearing 0jxs invariant).
    `runner` / `poster` are injectable for the hermetic test tier;
    production is the real `ShellCommandRunner` / `HttpNotifyPoster`.
    """
    updated = attempt(
        action=lambda: _self_update(
            work_item_id=work_item_id,
            merged_paths=merged_paths,
            candidate_bin=candidate_bin,
            scratch_root=scratch_root,
            repo=repo,
            journal=journal,
            runner=runner if runner is not None else ShellCommandRunner(),
            poster=poster if poster is not None else HttpNotifyPoster(),
        ),
        exceptions=(OSError, RuntimeError),
    )
    if isinstance(updated, AttemptFailure):
        journal.append(
            record={
                "stage": "self-update-error",
                "reason": f"{type(updated.error).__name__}",
            }
        )


def _self_update(  # noqa: PLR0913 - kw-only fail-open stage body; fields are caller inputs.
    *,
    work_item_id: str,
    merged_paths: tuple[str, ...],
    candidate_bin: str,
    scratch_root: str,
    repo: Path,
    journal: SelfUpdateJournal,
    runner: CommandRunner,
    poster: NotifyPoster,
) -> None:
    """The self-update body wrapped fail-open by `self_update_after_merge`.

    Read-only-cache guard FIRST (the self-contained-dispatch / adopter
    path): when there is no writable orchestrator checkout to promote into
    — the flattened plugin cache has no `.git` — record a CLEAN
    `self-update-skipped` (the writable-checkout reason) and return,
    instead of attempting a never-landable promotion and leaning on the
    fail-open `0jxs` supervisor to swallow the resulting error. The
    fail-open backstop stays; this guard just removes a never-applicable
    code path from hiding behind it.
    """
    from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
        is_writable_orchestrator_checkout,
        plugin_root,
    )

    if not is_writable_orchestrator_checkout(root=plugin_root(), runner=runner):
        journal.append(
            record={
                "stage": "self-update-skipped",
                "work_item_id": work_item_id,
                "reason": "no writable orchestrator checkout to promote (read-only plugin cache)",
            }
        )
        return
    if not is_self_merge(merged_paths=merged_paths):
        journal.append(
            record={
                "stage": "self-update-skipped",
                "work_item_id": work_item_id,
                "reason": "merge did not touch the dispatcher's own scripts",
            }
        )
        return
    canary = runner.run(
        argv=canary_self_check_argv(candidate_bin=candidate_bin, scratch_root=scratch_root),
        cwd=repo,
        timeout_seconds=_CANARY_TIMEOUT_SECONDS,
    )
    decision = promotion_decision(verdict=canary_verdict(exit_code=canary.exit_code))
    stage = "self-update-promoted" if decision.promote else "self-update-kept-last-known-good"
    journal.append(
        record={
            "stage": stage,
            "work_item_id": work_item_id,
            "reason": decision.reason,
        }
    )
    if not decision.alarm:
        return
    notify_terminal(
        events=(NotifyEvent(work_item_id=work_item_id, outcome_class=SELF_UPDATE_BREACH_CLASS),),
        run_id=run_id(),
        poster=poster,
        journal=journal,
    )


def run_id() -> str:
    """A non-credential-bearing correlation id for one dispatch run.

    Generated per invocation (a random uuid4 hex): it carries no env / goal
    / secret material by construction, so it is always safe to ship in the
    alarm body and to correlate against the journal.
    """
    return uuid.uuid4().hex
