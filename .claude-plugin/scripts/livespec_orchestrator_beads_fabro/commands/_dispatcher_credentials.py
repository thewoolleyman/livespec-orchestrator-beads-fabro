"""Credential and sandbox sibling-clone preparation for the Dispatcher."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

from livespec_runtime.github_auth.errors import GithubAppAuthError

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth import (
    CodexProjectionRefusal,
    project_codex_auth,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GITHUB_TOKEN_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    cc_otel_overlay_env,
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
    "check_credential_env",
    "credential_wrapper_text",
    "dispatch_required_credentials_text",
    "fetch_fleet_manifest_text",
    "materialize_overlay",
    "read_dispatch_comments",
    "read_dispatch_target_credential_wrapper",
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
