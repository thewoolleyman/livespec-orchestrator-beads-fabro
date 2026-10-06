"""Whether THIS HOST's environment carries a usable dispatch credential.

Split from `_dispatcher_credentials` by cohesion. That module PROJECTS
credentials into a sandbox overlay -- it writes a mode-600 run-config overlay
and renders env tables for a run that does not exist yet. This one asks the
opposite-facing question: does the machine running the Dispatcher right now hold
a credential the sandbox could use, and is it actually usable rather than merely
present? Nothing here writes an overlay, and nothing in the overlay renderer
probes a provider.

THE PROBE SEAM LIVES HERE WITH ITS CALLERS. `probe_claude_credential` is
resolved through THIS module's namespace, so a caller that stands the probe in
stands in the one the whole dispatch path uses. That identity is the reason
`assess_credential_status` is public at all: the loop's bounded credential
re-probe needs the TYPED `condition`, not a refusal string it would have to
pattern-match, because it waits on exactly one condition (a provider-limit or
rate-limit refusal) and must exit its wait on every other.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
    ClaudeCredentialStatus,
    absent_claude_credential_status,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential_io import (
    probe_claude_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_wrapper import (
    credential_wrapper_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
)

__all__: list[str] = [
    "assess_credential_status",
    "check_credential_env",
    "dispatch_required_credentials_text",
]

_DISPATCH_REQUIRED_CREDENTIALS = (
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "BEADS_DOLT_PASSWORD",
    CLAUDE_OAUTH_TOKEN_ENV,
)


def dispatch_required_credentials_text() -> str:
    return ", ".join(_DISPATCH_REQUIRED_CREDENTIALS)


def assess_credential_status(
    *,
    repo: Path,
    probe: Callable[..., ClaudeCredentialStatus] | None = None,
) -> ClaudeCredentialStatus:
    """Assess the projected worker credential: absence locally, else ONE bounded probe.

    Public because the refusal STRING is not the whole answer. The loop's
    bounded credential re-probe -- the admission-time probe-refusal clause of
    the provider spend-containment rules in `SPECIFICATION/contracts.md` --
    waits on ONE condition — a provider-limit or rate-limit refusal —
    and must exit its wait on every other, so it needs the typed
    `condition` rather than prose it would have to pattern-match. Keeping the
    assessment here rather than duplicating it in the re-probe module also
    keeps ONE probe seam: `probe_claude_credential` is resolved through this
    module's namespace, so a caller that stands the probe in stands in the one
    the whole dispatch path uses.
    """
    credential_choice = select_factory_credential(
        environ=os.environ,
        home=Path.home(),
        warn=lambda message: sys.stderr.write(f"livespec-dispatch: {message}\n"),
    )
    token = os.environ.get(credential_choice.env_name, "")
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
    status = assess_credential_status(repo=repo, probe=probe)
    if status.usable:
        return None
    return (
        f"C-mode dispatch refused before sandbox launch: {status.message} "
        f"Observed condition: {status.condition}. Remedy: {status.remedy} "
        "The dispatch target's credential_wrapper must inject the full "
        f"per-wrapper credential set: {dispatch_required_credentials_text()}."
    )
