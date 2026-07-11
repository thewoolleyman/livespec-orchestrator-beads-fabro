"""Codex credential projection for the Dispatcher."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CODEX_FRESHNESS_RUN_BUDGET_SECONDS,
    assess_codex_credential_freshness,
    project_codex_auth_snapshot,
)

__all__: list[str] = [
    "CodexProjectionRefusal",
    "project_codex_auth",
    "read_host_codex_auth",
]

# Host-side override for where the live Codex `auth.json` lives. The host
# is the sole `codex login`+refresh owner; the Dispatcher reads its
# auth.json directly (default `~/.codex/auth.json`) and projects a
# non-rotatable snapshot into the sandbox. An env-var NAME, not a secret.
_CODEX_HOME_ENV = "CODEX_HOME"


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
