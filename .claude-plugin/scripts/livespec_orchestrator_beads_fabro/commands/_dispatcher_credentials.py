"""Credential and sandbox sibling-clone preparation for the Dispatcher."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from livespec_runtime.github_auth.errors import GithubAppAuthError
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_sandbox_image
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
    ClaudeCredentialStatus,
    absent_claude_credential_status,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential_io import (
    probe_claude_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth import (
    CodexProjectionRefusal,
    project_codex_auth,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_otel_config import (
    codex_otel_config_toml,
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
from livespec_orchestrator_beads_fabro.commands._jsonc import JsoncFailure, parse
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
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
    "credential_status",
    "credential_wrapper_text",
    "dispatch_required_credentials_text",
    "fetch_fleet_manifest_text",
    "materialize_overlay",
    "read_dispatch_comments",
    "read_dispatch_labels",
    "read_dispatch_target_credential_wrapper",
    "resolve_sibling_clones",
]

_DISPATCH_REQUIRED_CREDENTIALS = (
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "BEADS_DOLT_PASSWORD",
    CLAUDE_OAUTH_TOKEN_ENV,
)
_GITHUB_TOKEN_ENV = GITHUB_TOKEN_ENV_VAR  # single-sourced from _dispatcher_io
_LEDGER_READ_ERRORS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


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
    comments = attempt(
        action=lambda: read_work_item_comments(path=store_config(repo=repo), work_item_id=item.id),
        exceptions=_LEDGER_READ_ERRORS,
    )
    if isinstance(comments, AttemptFailure):
        return (
            f"ledger comments read failed for {item.id} "
            f"({type(comments.error).__name__}: {comments.error})"
        )
    return comments


def read_dispatch_labels(
    *,
    repo: Path,
    item: WorkItem,
) -> tuple[str, ...] | str:
    """Read raw beads labels that carry per-item dispatcher policy overrides."""
    record = attempt(
        action=lambda: make_beads_client(config=store_config(repo=repo)).show_issue(
            issue_id=item.id
        ),
        exceptions=_LEDGER_READ_ERRORS,
    )
    if isinstance(record, AttemptFailure):
        return (
            f"ledger label read failed for {item.id} "
            f"({type(record.error).__name__}: {record.error})"
        )
    labels = record.get("labels")
    if not isinstance(labels, list):
        return ()
    raw_labels = cast("list[object]", labels)
    return tuple(label for label in raw_labels if isinstance(label, str))


def materialize_overlay(  # noqa: PLR0913 — kw-only overlay materializer; each argument is an independent projection input, matching `render_run_config_overlay` it feeds.
    *,
    committed: Path,
    overlay: Path,
    repo: Path,
    work_item_id: str,
    dispatch_id: str,
    token: Callable[[], str],
    graph_override: Path | None = None,
    prepare_inputs: Mapping[str, str] | None = None,
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
    github_token = attempt(action=token, exceptions=(GithubAppAuthError,))
    if isinstance(github_token, AttemptFailure):
        exc = cast("GithubAppAuthError", github_token.error)
        return f"C-mode dispatch refused: GitHub App token mint failed: {exc.detail}"
    # Refresh the ambient GH_TOKEN so the host-side `gh api` fleet-manifest
    # fetch below runs on a currently-valid installation token too.
    os.environ[_GITHUB_TOKEN_ENV] = github_token
    siblings = resolve_sibling_clones(repo=repo)
    if isinstance(siblings, str):
        return siblings
    codex_snapshot = project_codex_auth(now_epoch=int(time.time()))
    if isinstance(codex_snapshot, CodexProjectionRefusal):
        return codex_snapshot.message
    sandbox_otel_endpoint = resolve_sandbox_otel_endpoint(environ=dict(os.environ))
    otel_env = cc_otel_overlay_env(
        work_item_id=work_item_id,
        dispatch_id=dispatch_id,
        endpoint=sandbox_otel_endpoint,
    )
    # Codex honors no `OTEL_*` variable, so the overlay above reaches Claude
    # Code only. Codex resolves its exporters from `$CODEX_HOME/config.toml`
    # alone, and projecting that file is what makes Codex spend telemetry
    # exist at all (work-item bd-ib-dbzp). Rendered unconditionally, exactly
    # like the credential snapshot beside it: this path has already returned
    # on a projection refusal, so `$CODEX_HOME` is always provisioned here.
    codex_otel_config = codex_otel_config_toml(
        endpoint=sandbox_otel_endpoint,
        work_item_id=work_item_id,
        dispatch_id=dispatch_id,
    )
    rendered = render_run_config_overlay(
        committed_text=committed.read_text(encoding="utf-8"),
        workflow_dir=committed.parent.resolve(),
        token=os.environ[CLAUDE_OAUTH_TOKEN_ENV],
        github_token=github_token,
        siblings=siblings,
        otel_env=otel_env,
        codex_auth_snapshot=codex_snapshot,
        codex_otel_config=codex_otel_config,
        # An unreadable `.livespec.jsonc` falls back to "no image override",
        # visibly and here rather than inside the reader. `unsafe_perform_io`
        # is required: `IOResult.value_or` returns `IO[value]`, not the value.
        fabro_sandbox_image=unsafe_perform_io(resolve_fabro_sandbox_image(cwd=repo).value_or(None)),
        # The per-dispatch payload's rendered graph, carrying this dispatch's
        # resolved node timeouts as literal durations.
        graph_override=graph_override,
        # The resolved integration contract's values, substituted into the
        # committed run config's `{{ inputs.* }}` prepare commands because the
        # pinned engine does not render that site. Forwarded rather than
        # re-derived: the caller passes the SAME resolved contract the
        # `--input` pairs come from.
        prepare_inputs=prepare_inputs,
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
    config_text = attempt(
        action=lambda: config_path.read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if isinstance(config_text, AttemptFailure):
        return ()
    data = parse(text=config_text)
    if isinstance(data, JsoncFailure):
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


def credential_status(
    *,
    repo: Path,
    probe: Callable[..., ClaudeCredentialStatus] | None = None,
) -> ClaudeCredentialStatus:
    """Assess the exact sandbox model credential, without deciding on it.

    Presence is not sufficient: an absent token answers the distinct
    absent-credential status, and a present one is assessed by a bounded live
    probe against the same ``CLAUDE_CODE_OAUTH_TOKEN`` projected into the
    sandbox. Values and response bodies are never logged.

    Separated from `check_credential_env` because the two callers need
    DIFFERENT halves of the answer: a dispatch needs the refusal MESSAGE, while
    the loop's bounded re-probe needs the classified CONDITION — it holds the
    pass open for a provider-limit refusal and returns on every other one, a
    distinction a refusal string cannot carry.
    """
    token = os.environ.get(CLAUDE_OAUTH_TOKEN_ENV, "")
    if token == "":
        return absent_claude_credential_status(wrapper_text=credential_wrapper_text(repo=repo))
    selected_probe = probe if probe is not None else probe_claude_credential
    return selected_probe(token=token)


def check_credential_env(
    *,
    repo: Path,
    probe: Callable[..., ClaudeCredentialStatus] | None = None,
) -> str | None:
    """Fail fast unless the exact sandbox model credential is usable.

    Presence is not sufficient: this bounded live probe uses the same
    ``CLAUDE_CODE_OAUTH_TOKEN`` projected into the sandbox and refuses
    before launch when it is revoked, exhausted/rate-limited, denied, or
    cannot be assessed. Values and response bodies are never logged.
    """
    status = credential_status(repo=repo, probe=probe)
    if status.usable:
        return None
    return (
        f"C-mode dispatch refused before sandbox launch: {status.message} "
        f"Observed condition: {status.condition}. Remedy: {status.remedy} "
        "The dispatch target's credential_wrapper must inject the full "
        f"per-wrapper credential set: {dispatch_required_credentials_text()}."
    )
