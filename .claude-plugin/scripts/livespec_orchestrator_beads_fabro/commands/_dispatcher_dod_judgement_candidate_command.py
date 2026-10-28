"""The direct host command and identity of one resolved `dod_gate` candidate.

Split out of `_dispatcher_dod_judgement_candidates` by cohesion: the chain decides
the ORDER candidates run in and what each result amounts to, while this owns only
how one catalog-resolved candidate becomes a command line and what it is called.
The label and the model are read from the same place the command is built from, so
a record naming a candidate names what the host actually invoked.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_prompt import (
    judgement_argv,
    resolve_judge_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate

__all__: list[str] = ["candidate_command", "candidate_label", "candidate_model"]

_CODEX_AGENT = "codex-acp"
_CODEX_SANDBOX_SETTINGS = frozenset({"sandbox_mode", "approval_policy"})
_CLAUDE_AGENT = "claude-acp"


def candidate_command(
    *, candidate: AcpCandidate, environ: dict[str, str], bound_input: bool
) -> tuple[list[str], dict[str, str]]:
    """The direct host command for one catalog-resolved ACP candidate.

    The host runs the one-shot CLIs, never the ACP adapter command itself: an
    adapter is a JSON-RPC stdio server that does not grade a prompt on standard
    input, and the Codex adapter path is baked into the factory sandbox image.
    What the candidate resolved still reaches the CLI: its adapter environment
    (effort, endpoint and auth overrides) and, for Codex, every string
    `CODEX_CONFIG` setting as a `-c` override. The factory's sandbox and
    approval settings do not carry over; a host judge only reads, so Codex runs
    `-s read-only`, the counterpart of the Claude judge's read-only tool list.

    Under `bound_input` each CLI is also asked for its usage-reporting output
    form, because a candidate that reports no usage can be neither measured nor
    ended by the bound.
    """
    judge_environ = {**environ, **candidate.adapter.env}
    if candidate.agent_id == _CODEX_AGENT:
        settings = codex_settings(candidate=candidate)
        model = settings.pop("model", "")
        argv = ["codex", "exec", "-m", model]
        if bound_input:
            argv.append("--json")
        for key, value in settings.items():
            argv.extend(("-c", f"{key}={json.dumps(value)}"))
        argv.extend(("-s", "read-only"))
        return argv, judge_environ
    if candidate.agent_id == _CLAUDE_AGENT:
        model = candidate.adapter.env.get("ANTHROPIC_MODEL", "")
        credential = select_factory_credential(
            environ=environ,
            home=Path.home(),
            warn=lambda message: sys.stderr.write(f"{message}\n"),
        )
        judge_environ[CLAUDE_OAUTH_TOKEN_ENV] = environ.get(credential.env_name, "")
        argv = judgement_argv(
            judge_path=resolve_judge_path(environ=environ),
            model=model,
            stream_usage=bound_input,
        )
        return argv, judge_environ
    return [candidate.adapter.command, *candidate.adapter.args], judge_environ


def candidate_label(*, candidate: AcpCandidate) -> str:
    """Render a durable candidate identity without host-local paths."""
    if candidate.agent_id == _CODEX_AGENT:
        model = codex_settings(candidate=candidate).get("model")
        return f"{candidate.agent_id}:{model if model is not None else ''}"
    if candidate.agent_id == _CLAUDE_AGENT:
        return f"{candidate.agent_id}:{candidate.adapter.env.get('ANTHROPIC_MODEL', '')}"
    return candidate.agent_id or ""


def candidate_model(*, candidate: AcpCandidate) -> str:
    """The model one candidate resolved to, read where its CLI is told it."""
    if candidate.agent_id == _CODEX_AGENT:
        return codex_settings(candidate=candidate).get("model", "")
    return candidate.adapter.env.get("ANTHROPIC_MODEL", "")


def codex_settings(*, candidate: AcpCandidate) -> dict[str, str]:
    """The string settings rendered into this candidate's catalog adapter.

    Only a string is carried, so a malformed value is dropped rather than
    rendered, and the sandbox and approval settings belong to the factory
    sandbox, so they are not carried either.
    """
    raw = candidate.adapter.env.get("CODEX_CONFIG", "")
    try:
        decoded: object = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    payload = cast("dict[str, object]", decoded)
    return {
        key: value
        for key, value in payload.items()
        if key not in _CODEX_SANDBOX_SETTINGS and isinstance(value, str)
    }
