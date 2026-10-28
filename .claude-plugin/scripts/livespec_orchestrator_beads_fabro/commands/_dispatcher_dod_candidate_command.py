"""The direct host command one resolved `dod_gate` candidate is run through.

The host runs the one-shot CLIs, never the ACP adapter command itself: an adapter
is a JSON-RPC stdio server that does not grade a prompt on standard input, and
the Codex adapter path is baked into the factory sandbox image. This module turns
a catalog-resolved candidate into the argv and environment of that CLI, resolves
the Claude executable and the judge's time box, and names the model a candidate
resolved to, so a record can say which model each leg asked.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
)
from livespec_orchestrator_beads_fabro.effects import FloatParseFailure, parse_float

if TYPE_CHECKING:
    from collections.abc import Callable

    from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate

__all__: list[str] = [
    "candidate_command",
    "candidate_model",
    "judgement_argv",
    "resolve_judge_path",
    "resolve_judge_timeout_seconds",
]

_JUDGE_PATH_ENV = "LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH"
_TIMEOUT_ENV = "LIVESPEC_DOD_JUDGEMENT_TIMEOUT_SECONDS"
_DEFAULT_TIMEOUT_SECONDS = 600.0
_JUDGE_EXECUTABLE = "claude"
_CONVENTIONAL_JUDGE_PATH = "~/.local/bin/claude"
# The read-only grant check 6 needs to search `scenarios.md` for a governing
# scenario before concluding none does. A headless call grants no tool at all by
# default, so without this the judge can only report what it was handed — and
# "no scenario governs this" is exactly the conclusion the prompt forbids it
# from reaching by recollection.
_ALLOWED_TOOLS = "Read,Grep,Glob"
_CODEX_AGENT = "codex-acp"
_CODEX_SANDBOX_SETTINGS = frozenset({"sandbox_mode", "approval_policy"})
_CLAUDE_AGENT = "claude-acp"


def judgement_argv(*, judge_path: str, model: str) -> list[str]:
    """The Claude host-judge invocation, with its prompt supplied on standard input."""
    return [
        judge_path,
        "-p",
        "--allowedTools",
        _ALLOWED_TOOLS,
        "--model",
        model,
    ]


def resolve_judge_path(
    *,
    environ: dict[str, str],
    which: Callable[[str], str | None] = shutil.which,
    conventional: Path | None = None,
) -> str:
    """The judge executable: override, then PATH, then the conventional install.

    The last resort is the BARE NAME rather than a verdict of our own that no
    model is eligible. Letting the runner fail to exec it reports the absence as
    the measurement it is — exit 127 — instead of as a guess this resolver made
    without trying.
    """
    override = environ.get(_JUDGE_PATH_ENV, "").strip()
    if override:
        return override
    found = which(_JUDGE_EXECUTABLE)
    if found is not None:
        return found
    local_bin = (
        Path(_CONVENTIONAL_JUDGE_PATH).expanduser() if conventional is None else conventional
    )
    if local_bin.is_file():
        return str(local_bin)
    return _JUDGE_EXECUTABLE


def resolve_judge_timeout_seconds(*, environ: dict[str, str]) -> float:
    """The judge's time box, falling back on an absent, bad or non-positive value.

    A zero or negative box is a self-inflicted hang rather than a tighter
    bound, and an unparseable one must not crash a path whose whole contract is
    to fail soft, so both read as the committed default.
    """
    raw = environ.get(_TIMEOUT_ENV, "")
    parsed = parse_float(text=raw)
    if isinstance(parsed, FloatParseFailure):
        return _DEFAULT_TIMEOUT_SECONDS
    return parsed if parsed > 0 else _DEFAULT_TIMEOUT_SECONDS


def candidate_command(
    *, candidate: AcpCandidate, environ: dict[str, str]
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
    """
    judge_environ = {**environ, **candidate.adapter.env}
    if candidate.agent_id == _CODEX_AGENT:
        settings = _codex_settings(candidate=candidate)
        model = settings.pop("model", "")
        argv = ["codex", "exec", "-m", model]
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
        argv = judgement_argv(judge_path=resolve_judge_path(environ=environ), model=model)
        return argv, judge_environ
    return [candidate.adapter.command, *candidate.adapter.args], judge_environ


def _codex_settings(*, candidate: AcpCandidate) -> dict[str, str]:
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


def candidate_model(*, candidate: AcpCandidate) -> str:
    """The model one candidate resolved to, read where its CLI is told it."""
    if candidate.agent_id == _CODEX_AGENT:
        return _codex_settings(candidate=candidate).get("model", "")
    return candidate.adapter.env.get("ANTHROPIC_MODEL", "")
