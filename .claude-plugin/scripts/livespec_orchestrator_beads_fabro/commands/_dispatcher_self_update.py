"""Side-effecting orchestration for release-triggered self-update + canary.

The post-verdict stage runs after the dispatch verdict is final, compares the
running release with the released payload currently provisioned under the plugin
root, and canaries that candidate artifact. A passing canary alarms that a
restart is due; a failing canary keeps last-known-good and alarms through h1p's
`notify_terminal` seam.
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
from typing import Any, Protocol, cast

from livespec_runtime.github_auth.config import load_github_app_config
from livespec_runtime.github_auth.errors import GithubAppAuthError
from livespec_runtime.github_auth.provider import InstallationTokenProvider
from returns.pipeline import is_successful

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
    SELF_UPDATE_BREACH_CLASS,
    CanaryVerdict,
    PromotionDecision,
    ReleaseUpdateDecision,
    canary_self_check_argv,
    canary_verdict,
    promotion_decision,
    release_update_decision,
)
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "SELF_UPDATE_BREACH_CLASS",
    "CanaryVerdict",
    "PromotionDecision",
    "ReleaseUpdateDecision",
    "canary_self_check_argv",
    "canary_verdict",
    "candidate_dispatcher_bin",
    "github_token_supplier",
    "post_verdict_runner",
    "promotion_decision",
    "release_update_decision",
    "released_payload_version",
    "run_id",
    "running_release_version",
    "self_update_after_release",
    "self_update_after_verdict",
]

_CANARY_TIMEOUT_SECONDS = 300.0
_RESTART_DUE_CLASS = "self-update-restart-due"


class SelfUpdateJournal(Protocol):
    """The append-only journal seam the self-update stage records through.

    Structurally typed (no subclassing): any object with a keyword-only
    `append(record=...)` method satisfies it — the production `JournalFile`
    and the hermetic test tier's in-memory recorder alike. The stage records
    only leak-free scalar `stage` / `work_item_id` / `reason` fields.
    """

    def append(self, *, record: dict[str, object]) -> None: ...


def _released_payload_version_from_root(*, root: Path) -> str | None:
    text = attempt(
        action=lambda: (root / "plugin.json").read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if isinstance(text, AttemptFailure):
        return None
    parsed = parse_json(text=text)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    raw_version = cast("dict[str, Any]", parsed).get("version")
    return raw_version.strip() if isinstance(raw_version, str) and raw_version.strip() else None


def _import_time_plugin_root() -> Path:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import plugin_root

    return plugin_root()


_RUNNING_RELEASE_VERSION = _released_payload_version_from_root(root=_import_time_plugin_root())


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
    # `load_github_app_config` is on the Result railway since livespec-runtime
    # v0.21.2 — the absent-App-env refusal arrives as data on the failure
    # track, so no `attempt` exception boundary is needed to route it.
    config = load_github_app_config(environ=os.environ)
    if not is_successful(config):
        return f"C-mode dispatch refused: {config.failure().detail}"
    return InstallationTokenProvider(config=config.unwrap()).token


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


def self_update_after_verdict(  # noqa: PLR0913 - kw-only post-verdict seams and DI.
    *,
    repo: Path,
    outcomes: list[DispatchOutcome],
    journal: SelfUpdateJournal,
    runner: CommandRunner | None = None,
    token_supplier: Callable[[], str] | None = None,
    poster: NotifyPoster | None = None,
    running_release: str | None = _RUNNING_RELEASE_VERSION,
) -> None:
    """Run the release-comparison self-update gate after the verdict is final."""
    green = next((outcome for outcome in outcomes if outcome.status == "green"), None)
    if green is None:
        return
    from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import plugin_root

    candidate_root = plugin_root()
    available_release = released_payload_version(root=candidate_root)
    decision = release_update_decision(
        running_release=running_release_version(running_release=running_release),
        available_release=available_release,
    )
    if not decision.update_required:
        journal.append(
            record={
                "stage": _release_skip_stage(decision=decision),
                "work_item_id": green.work_item_id,
                "reason": decision.reason,
            }
        )
        return
    resolved_runner = post_verdict_runner(runner=runner, token_supplier=token_supplier)
    resolved_poster = poster if poster is not None else HttpNotifyPoster()
    self_update_after_release(
        work_item_id=green.work_item_id,
        candidate_bin=str(candidate_dispatcher_bin()),
        scratch_root=tempfile.mkdtemp(prefix=f"self-update-canary-{green.work_item_id}-"),
        repo=repo,
        journal=journal,
        runner=resolved_runner,
        poster=resolved_poster,
    )


def candidate_dispatcher_bin() -> Path:
    """The released payload's own `bin/dispatcher.py` canary target."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import plugin_root

    return plugin_root() / "scripts" / "bin" / "dispatcher.py"


def self_update_after_release(  # noqa: PLR0913 - kw-only fail-open stage; fields are caller inputs.
    *,
    work_item_id: str,
    candidate_bin: str,
    scratch_root: str,
    repo: Path,
    journal: SelfUpdateJournal,
    runner: CommandRunner | None = None,
    poster: NotifyPoster | None = None,
) -> None:
    """Stage + canary a newer released artifact before it can take over."""
    updated = attempt(
        action=lambda: _self_update(
            work_item_id=work_item_id,
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
    candidate_bin: str,
    scratch_root: str,
    repo: Path,
    journal: SelfUpdateJournal,
    runner: CommandRunner,
    poster: NotifyPoster,
) -> None:
    """The self-update body wrapped fail-open by `self_update_after_release`.

    The Dispatcher never writes code anywhere. It canaries the candidate
    artifact and records either a restart-due alarm on PASS or a fail-closed
    last-known-good alarm on FAIL. The fail-open backstop stays around the
    stage supervisor, but the canary itself is not skipped merely because the
    running artifact is a flattened plugin cache rather than a writable
    orchestrator checkout.
    """
    canary = runner.run(
        argv=canary_self_check_argv(candidate_bin=candidate_bin, scratch_root=scratch_root),
        cwd=repo,
        timeout_seconds=_CANARY_TIMEOUT_SECONDS,
    )
    verdict = canary_verdict(exit_code=canary.exit_code)
    decision = promotion_decision(verdict=verdict)
    stage = (
        _RESTART_DUE_CLASS if verdict is CanaryVerdict.PASS else "self-update-kept-last-known-good"
    )
    journal.append(
        record={
            "stage": stage,
            "work_item_id": work_item_id,
            "reason": decision.reason,
        }
    )
    outcome_class = (
        _RESTART_DUE_CLASS if verdict is CanaryVerdict.PASS else SELF_UPDATE_BREACH_CLASS
    )
    notify_terminal(
        events=(NotifyEvent(work_item_id=work_item_id, outcome_class=outcome_class),),
        run_id=run_id(),
        poster=poster,
        journal=journal,
    )


def released_payload_version(*, root: Path) -> str | None:
    """Read the provisioned released payload version from `plugin.json`."""
    return _released_payload_version_from_root(root=root)


def running_release_version(
    *,
    running_release: str | None = _RUNNING_RELEASE_VERSION,
) -> str | None:
    """Return the import-time running release marker."""
    if running_release is None:
        return None
    stripped = running_release.strip()
    return stripped if stripped else None


def _release_skip_stage(*, decision: ReleaseUpdateDecision) -> str:
    if "could not be determined" in decision.reason:
        return "self-update-release-undetermined"
    return "self-update-skipped"


def run_id() -> str:
    """A non-credential-bearing correlation id for one dispatch run.

    Generated per invocation (a random uuid4 hex): it carries no env / goal
    / secret material by construction, so it is always safe to ship in the
    alarm body and to correlate against the journal.
    """
    return uuid.uuid4().hex
