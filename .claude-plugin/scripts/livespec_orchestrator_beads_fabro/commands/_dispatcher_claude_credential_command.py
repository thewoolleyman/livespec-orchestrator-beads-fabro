"""Operator command for inspecting Claude OAuth credential usability."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    ClaudeCredentialStatus,
    absent_claude_credential_status,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential_io import (
    CLAUDE_CREDENTIAL_PROBE_MAX_OUTPUT_TOKENS,
    CLAUDE_CREDENTIAL_PROBE_MODEL,
    CLAUDE_CREDENTIAL_PROBE_TIMEOUT_SECONDS,
    probe_claude_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "assess_claude_credential",
    "run_claude_cred_status",
]

_WRAPPER_HINT = "the target repo's configured credential_wrapper"


def assess_claude_credential(
    *,
    token: str | None,
    probe: Callable[..., ClaudeCredentialStatus],
    wrapper_text: str,
) -> ClaudeCredentialStatus:
    """Assess absence locally or run exactly one injected usability probe."""
    if token is None or token == "":
        return absent_claude_credential_status(wrapper_text=wrapper_text)
    return probe(token=token)


def run_claude_cred_status(*, args: argparse.Namespace) -> int:
    """Probe the exact OAuth token projected to the Claude review adapter.

    The token is the one `select_factory_credential` resolves — the SAME
    selector the admission-time probe and the session-headroom gate call, so
    all four surfaces name ONE account. Reading the unnumbered
    `CLAUDE_CODE_OAUTH_TOKEN` here instead assessed anthropic-1 while every
    dispatch billed the published anthropic-3 slot (`bd-ib-6zfayy`, measured
    2026-10-16 04:00Z-04:20Z: this command reported HTTP 429 while the selected
    slot read HTTP 200 with about 88% five-hour headroom left, and every
    operator gate consulting it held for an account nothing was spending). Do
    NOT add a second resolution path: a fourth surface resolving its own
    credential is how the three that agree come to disagree again.

    The resolved NAME rides into both renderings, because a verdict that always
    named the unnumbered variable is unattributable — HTTP 429 says nothing
    about which pool slot answered for it.
    """
    choice = select_factory_credential(
        environ=os.environ,
        home=Path.home(),
        warn=lambda message: write_stderr(text=f"livespec-dispatch: {message}\n"),
    )
    status = assess_claude_credential(
        token=os.environ.get(choice.env_name),
        probe=probe_claude_credential,
        wrapper_text=_WRAPPER_HINT,
    )
    payload = _payload(status=status, credential_env=choice.env_name)
    if args.as_json:
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        _ = write_stdout(text=_human(payload=payload))
    return 0 if status.usable else 1


def _payload(*, status: ClaudeCredentialStatus, credential_env: str) -> dict[str, Any]:
    return {
        "condition": status.condition,
        "credential_env": credential_env,
        "error_type": status.error_type,
        "http_status": status.http_status,
        "input_tokens": status.input_tokens,
        "max_output_tokens": CLAUDE_CREDENTIAL_PROBE_MAX_OUTPUT_TOKENS,
        "message": status.message,
        "model": CLAUDE_CREDENTIAL_PROBE_MODEL,
        "output_tokens": status.output_tokens,
        "present": status.present,
        "probe_timeout_seconds": CLAUDE_CREDENTIAL_PROBE_TIMEOUT_SECONDS,
        "remedy": status.remedy,
        "usable": status.usable,
    }


def _human(*, payload: dict[str, Any]) -> str:
    return "\n".join(
        (
            f"credential_env: {payload['credential_env']}",
            f"present: {_human_bool(value=payload['present'])}",
            f"usable: {_human_bool(value=payload['usable'])}",
            f"condition: {payload['condition']}",
            f"http_status: {_human_optional(value=payload['http_status'])}",
            f"error_type: {_human_optional(value=payload['error_type'])}",
            f"model: {payload['model']}",
            f"max_output_tokens: {payload['max_output_tokens']}",
            f"input_tokens: {_human_optional(value=payload['input_tokens'])}",
            f"output_tokens: {_human_optional(value=payload['output_tokens'])}",
            f"probe_timeout_seconds: {payload['probe_timeout_seconds']}",
            f"message: {payload['message']}",
            f"remedy: {payload['remedy']}",
            "",
        )
    )


def _human_bool(*, value: object) -> str:
    return "true" if value is True else "false"


def _human_optional(*, value: object) -> str:
    return "null" if value is None else str(value)
