"""Operator command for inspecting Claude OAuth credential usability."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
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
    """Probe the exact OAuth token projected to the Claude review adapter."""
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
    payload = _payload(status=status)
    if args.as_json:
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        _ = write_stdout(text=_human(payload=payload))
    return 0 if status.usable else 1


def _payload(*, status: ClaudeCredentialStatus) -> dict[str, Any]:
    return {
        "condition": status.condition,
        "credential_env": CLAUDE_OAUTH_TOKEN_ENV,
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
