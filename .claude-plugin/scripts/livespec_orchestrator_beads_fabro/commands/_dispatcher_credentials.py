"""Credential and sandbox sibling-clone preparation for the Dispatcher."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_runtime.github_auth.errors import GithubAppAuthError

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GITHUB_TOKEN_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CODEX_FRESHNESS_RUN_BUDGET_SECONDS,
    assess_codex_credential_freshness,
    cc_otel_overlay_env,
    project_codex_auth_snapshot,
    render_run_config_overlay,
    resolve_sandbox_otel_endpoint,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones import (
    fetch_fleet_manifest_text,
    resolve_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands._jsonc import JsoncParseError, loads
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)
from livespec_orchestrator_beads_fabro.store import (
    WorkItemComment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "CodexProjectionRefusal",
    "check_credential_env",
    "credential_wrapper_text",
    "dispatch_required_credentials_text",
    "fetch_fleet_manifest_text",
    "materialize_overlay",
    "project_codex_auth",
    "read_dispatch_comments",
    "read_dispatch_target_credential_wrapper",
    "read_host_codex_auth",
    "resolve_sibling_clones",
]

_OAUTH_TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"  # noqa: S105 - env-var NAME, not a secret value
_DISPATCH_REQUIRED_CREDENTIALS = (
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "BEADS_DOLT_PASSWORD",
    _OAUTH_TOKEN_ENV,
)
_GITHUB_TOKEN_ENV = GITHUB_TOKEN_ENV_VAR  # single-sourced from _dispatcher_io

# Host-side override for where the live Codex `auth.json` lives. The host
# is the sole `codex login`+refresh owner; the Dispatcher reads its
# auth.json directly (default `~/.codex/auth.json`) and projects a
# non-rotatable snapshot into the sandbox. An env-var NAME, not a secret.
_CODEX_HOME_ENV = "CODEX_HOME"


def read_dispatch_comments(
    *,
    repo: Path,
    item: WorkItem,
) -> tuple[WorkItemComment, ...] | str:
    """Read the item's ledger comments for the goal; error string on failure.

    Comments are operator riders appended after filing (e.g.
    pre-authorizations); a brief without them silently re-creates bn4
    finding (c), so a failed read REFUSES the dispatch (error-as-data,
    routed at the `ledger-comments` stage) instead of proceeding
    comment-blind.
    """
    try:
        return read_work_item_comments(path=store_config(repo=repo), work_item_id=item.id)
    except (
        BeadsCommandError,
        BeadsConnectionError,
        BeadsMappingError,
        BeadsTenantMissingError,
    ) as exc:
        return f"ledger comments read failed for {item.id} ({type(exc).__name__}: {exc})"


def materialize_overlay(
    *,
    committed: Path,
    overlay: Path,
    repo: Path,
    work_item_id: str,
    dispatch_id: str,
    token: Callable[[], str],
) -> str | None:
    """Write the uncommitted mode-600 run-config overlay.

    Returns None on success, or an actionable error message (an expected
    failure routed as data — the dispatch reports it at the
    `run-config-overlay` stage). The overlay is the RUN-SCOPED
    credential projection: the committed config (graph path absolutized)
    plus an appended env table carrying the CLAUDE_CODE_OAUTH_TOKEN
    value read from this process's environment and a GITHUB_TOKEN freshly
    minted from the App installation-token provider (`token` is the
    provider's accessor — the sandbox receives an ephemeral installation
    token, never the durable App key and never a fleet PAT; projected
    under GITHUB_TOKEN, not GH_TOKEN, so fabro's per-exec re-mint is not
    shadowed). Fabro
    `{{ env }}` interpolation is NOT usable here (see the module
    docstring), so the value MUST be materialized. The token never
    reaches a log, journal, or argv; the overlay file is deleted when
    the run returns.

    The overlay ALSO provisions the sandbox sibling clones: one depth-1
    prepare-step clone per fleet member (minus the dispatch target,
    keyed by the `--repo` basename) plus the non-secret
    `LIVESPEC_SIBLING_CLONES_ROOT` env key, so cross-repo checks under
    `just check` resolve family siblings inside the sandbox the same
    way livespec CI provisions them.

    It projects the in-sandbox Claude-Code OTel env (29f.3): the
    `cc_otel_overlay_env` dict carrying the correlation triple
    (`work_item_id` + `dispatch_id`) and the host-local E1 receiver
    endpoint, so CC native telemetry exports from inside the sandbox to
    the host-local enrich/receive stage. All NON-secret values — the
    Honeycomb ingest key is NOT among them (the sandbox ships plaintext;
    the host egress stage holds the key).

    Finally it projects the dual-credential Codex snapshot (scenarios.md
    Scenario 18 / Scenario 19): the host `auth.json` is read, freshness-
    gated against the run budget, and projected non-rotatably into the
    sandbox `$CODEX_HOME/auth.json` alongside the Claude OAuth env. A
    missing or too-short-lived host credential refuses the dispatch here
    with an actionable renewal message (naming `codex login`).
    """
    env_error = check_credential_env(repo=repo)
    if env_error is not None:
        return env_error
    try:
        github_token = token()
    except GithubAppAuthError as error:
        return f"C-mode dispatch refused: GitHub App token mint failed: {error.detail}"
    # Refresh the ambient GH_TOKEN so the host-side `gh api` fleet-manifest
    # fetch below runs on a currently-valid installation token too.
    os.environ[_GITHUB_TOKEN_ENV] = github_token
    siblings = resolve_sibling_clones(repo=repo)
    if isinstance(siblings, str):
        return siblings
    codex_snapshot = project_codex_auth(now_epoch=int(time.time()))
    if isinstance(codex_snapshot, CodexProjectionRefusal):
        return codex_snapshot.message
    otel_env = cc_otel_overlay_env(
        work_item_id=work_item_id,
        dispatch_id=dispatch_id,
        endpoint=resolve_sandbox_otel_endpoint(environ=dict(os.environ)),
    )
    rendered = render_run_config_overlay(
        committed_text=committed.read_text(encoding="utf-8"),
        workflow_dir=committed.parent.resolve(),
        token=os.environ[_OAUTH_TOKEN_ENV],
        github_token=github_token,
        siblings=siblings,
        otel_env=otel_env,
        codex_auth_snapshot=codex_snapshot,
    )
    if rendered is None:
        return (
            f"workflow config {committed} is not materializable: it must carry "
            '[workflow] graph = "..." and [run.environment] id = "..."'
        )
    overlay.unlink(missing_ok=True)
    descriptor = os.open(str(overlay), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        _ = handle.write(rendered)
    return None


def dispatch_required_credentials_text() -> str:
    return ", ".join(_DISPATCH_REQUIRED_CREDENTIALS)


def read_dispatch_target_credential_wrapper(*, repo: Path) -> tuple[str, ...]:
    config_path = repo / ".livespec.jsonc"
    try:
        data = loads(text=config_path.read_text(encoding="utf-8"))
    except (OSError, JsoncParseError):
        return ()
    if not isinstance(data, dict):
        return ()
    mapping = cast(dict[str, object], data)
    wrapper = mapping.get("credential_wrapper")
    if not isinstance(wrapper, list):
        return ()
    wrapper_parts = cast(list[object], wrapper)
    parts: list[str] = []
    for part in wrapper_parts:
        if not isinstance(part, str):
            return ()
        parts.append(part)
    return tuple(parts)


def credential_wrapper_text(*, repo: Path) -> str:
    wrapper = read_dispatch_target_credential_wrapper(repo=repo)
    if not wrapper:
        return f"no credential_wrapper configured in {repo / '.livespec.jsonc'}"
    return repr(list(wrapper))


def check_credential_env(*, repo: Path) -> str | None:
    """Fail fast when the sandbox model credential is absent.

    Returns None when CLAUDE_CODE_OAUTH_TOKEN is present, or an
    actionable error naming it. The Dispatcher's process env is the
    SOURCE of the run-scoped overlay projection, so an absent or empty
    variable means there is nothing to project. The dispatch target's
    credential_wrapper must inject the full per-wrapper credential set:
    GITHUB_APP_ID, GITHUB_PRIVATE_KEY, BEADS_DOLT_PASSWORD, and
    CLAUDE_CODE_OAUTH_TOKEN. The GitHub credential is minted
    per-dispatch by the App installation-token provider
    (`_github_token_supplier`), but the refusal enumerates the whole
    wrapper contract up front so adopters do not discover credentials
    one failure at a time. Values are never logged.
    """
    if os.environ.get(_OAUTH_TOKEN_ENV, "") != "":
        return None
    return (
        f"C-mode dispatch refused: {_OAUTH_TOKEN_ENV} is not set in the "
        f"Dispatcher's process environment. The run-config overlay "
        f"projects it into the sandbox env table (fabro "
        f"'{{{{ env.* }}}}' interpolation cannot deliver it — the "
        f"server-spawned worker env is allowlist-scrubbed), so an absent "
        f"variable leaves nothing to project. Invoke the Dispatcher under "
        f"the dispatch target's configured credential_wrapper "
        f"{credential_wrapper_text(repo=repo)}. That wrapper must inject "
        f"the full per-wrapper credential set: "
        f"{dispatch_required_credentials_text()}."
    )


def read_host_codex_auth() -> str | None:
    """Read the host's Codex `auth.json` text (the projection SOURCE).

    DIRECT host-file read — the host is the sole `codex login`+refresh
    owner; the sandbox never touches the live credential. Honors a
    host-side `CODEX_HOME` override (default `~/.codex`). Returns the raw
    text, or None when the file is missing/unreadable (any `OSError`), so
    the caller renders an actionable refusal naming `codex login`.
    """
    home = os.environ.get(_CODEX_HOME_ENV) or str(Path.home() / ".codex")
    try:
        return (Path(home) / "auth.json").read_text(encoding="utf-8")
    except OSError:
        return None


@dataclass(frozen=True, kw_only=True)
class CodexProjectionRefusal:
    """A dual-credential-projection refusal routed as data (missing/stale)."""

    message: str


def project_codex_auth(*, now_epoch: int) -> str | CodexProjectionRefusal:
    """Project the host Codex credential into the dispatch sandbox snapshot.

    Returns the non-rotatable `auth.json` snapshot string on success
    (scenarios.md Scenario 18), or a `_CodexProjectionRefusal` carrying an
    actionable message when the host credential is absent (Scenario 18
    precondition) or too short-lived for the run budget plus margin
    (Scenario 19). `now_epoch` is injected so the freshness gate stays
    deterministically testable. The refusal is a distinct type so a
    snapshot that happens to look like a message is never mistaken for one.
    """
    source_auth_json = read_host_codex_auth()
    if source_auth_json is None:
        return CodexProjectionRefusal(
            message=(
                "C-mode dispatch refused: no host Codex credential found at "
                f"${_CODEX_HOME_ENV}/auth.json (default ~/.codex/auth.json). "
                "The Dispatcher projects a non-rotatable snapshot of the "
                "host credential into the sandbox; run `codex login` on the "
                "orchestrator host before dispatch."
            )
        )
    verdict = assess_codex_credential_freshness(
        source_auth_json=source_auth_json,
        now_epoch=now_epoch,
        run_budget_seconds=CODEX_FRESHNESS_RUN_BUDGET_SECONDS,
    )
    if not verdict.fresh_enough:
        return CodexProjectionRefusal(
            message=verdict.renewal_message
            or "C-mode dispatch refused: host Codex credential requires renewal."
        )
    return project_codex_auth_snapshot(source_auth_json=source_auth_json)
