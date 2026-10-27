"""The prompt and host-invocation settings for a DoD judgement.

This is deliberately separate from the candidate-chain runner: the prompt's
identity is shared by both host judgement entry points, while candidate
selection and usage accounting are execution concerns.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import executing_payload_root
from livespec_orchestrator_beads_fabro.commands._workflow_variants import RESERVED_WORKFLOW_NAME
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    FloatParseFailure,
    attempt,
    parse_float,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__all__: list[str] = [
    "HOST_ENDING_CONTRACT",
    "dod_gate_prompt_path",
    "judgement_argv",
    "judgement_prompt",
    "judgement_rubric",
    "resolve_judge_path",
    "resolve_judge_timeout_seconds",
]

_JUDGE_PATH_ENV = "LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH"
_TIMEOUT_ENV = "LIVESPEC_DOD_JUDGEMENT_TIMEOUT_SECONDS"
_DEFAULT_TIMEOUT_SECONDS = 600.0
_JUDGE_EXECUTABLE = "claude"
_CONVENTIONAL_JUDGE_PATH = "~/.local/bin/claude"
_ALLOWED_TOOLS = "Read,Grep,Glob"

HOST_ENDING_CONTRACT = """
## How THIS taking of the judgement ends — a host call, not a node

You are running as a host call rather than as a node of a graph, so ONE thing
replaces the "How to end" section above. Nothing else changes: every check, its
order, and every remedy it names are exactly as written, and this section adds
no rule of its own about how to grade any of them.

There is no graph to fall through, so end with a JSON object on the LAST line of
your reply in BOTH directions:

- every check clean: {"outcome": "passed"}
- any finding: {"outcome": "failed", "failure_reason": "<the findings>"}, one
  finding per line inside `failure_reason`, each naming the work-item id, the
  offending element quoted verbatim, and the remedy.

A reply whose last line is neither is read as a judgement that could not run,
and the item is then routed exactly as it would be without the judgement.

## The work-item under judgement

It follows verbatim.

"""


def dod_gate_prompt_path(*, payload_root: Path | None = None) -> Path:
    """Where the executing build carries the DoD-gate prompt."""
    root = executing_payload_root() if payload_root is None else payload_root
    return root / ".fabro" / "workflows" / RESERVED_WORKFLOW_NAME / "prompts" / "dod-gate.md"


def judgement_rubric(*, payload_root: Path | None = None) -> str | None:
    """The executing build's prompt bytes, or ``None`` when unreadable."""
    read = attempt(
        action=lambda: dod_gate_prompt_path(payload_root=payload_root).read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    return None if isinstance(read, AttemptFailure) else read


def judgement_prompt(*, gate_prompt: str, subject: str) -> str:
    """The node's prompt, its host ending contract, and the subject."""
    return f"{gate_prompt}{HOST_ENDING_CONTRACT}{subject}\n"


def judgement_argv(*, judge_path: str, model: str) -> list[str]:
    """The Claude invocation, which receives its prompt on standard input."""
    return [judge_path, "-p", "--allowedTools", _ALLOWED_TOOLS, "--model", model]


def resolve_judge_path(
    *,
    environ: dict[str, str],
    which: Callable[[str], str | None] = shutil.which,
    conventional: Path | None = None,
) -> str:
    """Resolve the host Claude command without probing it separately."""
    override = environ.get(_JUDGE_PATH_ENV, "").strip()
    if override:
        return override
    found = which(_JUDGE_EXECUTABLE)
    if found is not None:
        return found
    local_bin = (
        Path(_CONVENTIONAL_JUDGE_PATH).expanduser() if conventional is None else conventional
    )
    return str(local_bin) if local_bin.is_file() else _JUDGE_EXECUTABLE


def resolve_judge_timeout_seconds(*, environ: dict[str, str]) -> float:
    """Resolve a positive timeout, falling back for missing or invalid values."""
    parsed = parse_float(text=environ.get(_TIMEOUT_ENV, ""))
    if isinstance(parsed, FloatParseFailure):
        return _DEFAULT_TIMEOUT_SECONDS
    return parsed if parsed > 0 else _DEFAULT_TIMEOUT_SECONDS
