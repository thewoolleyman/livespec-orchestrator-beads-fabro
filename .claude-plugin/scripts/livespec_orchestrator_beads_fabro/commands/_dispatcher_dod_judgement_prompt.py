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
# The prompt carries every referenced clause, so the host candidate needs no
# tools.  `--allowedTools` only pre-approves named default tools; `--tools` is
# the Claude flag that replaces the available set.  An empty set prevents a
# candidate from spending another request exploring the governed repository or
# `/etc/livespec` after it already has the complete judgement subject.
_AVAILABLE_TOOLS = ""
_STREAM_OUTPUT_FORMAT = "stream-json"

# The ONE thing a host taking appends, and the whole of it: the verdict form.
# PUBLIC, because the repository preflight appends the identical bytes — a second
# copy over there is two ending contracts that can drift, and a drifted one makes
# the preflight's verdict unreadable while the judge it ran was perfectly healthy.
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
    """Where the `dod_gate` node's own prompt sits under a payload root.

    Resolved through `executing_payload_root` rather than `plugin_root`, because
    this is a packaged ASSET read: it must keep resolving after the installation
    the running code was copied from has been evicted.
    """
    root = executing_payload_root() if payload_root is None else payload_root
    return root / ".fabro" / "workflows" / RESERVED_WORKFLOW_NAME / "prompts" / "dod-gate.md"


def judgement_rubric(*, payload_root: Path | None = None) -> str | None:
    """The executing build's `dod-gate.md` bytes, or `None` when unreadable.

    PUBLIC because the GATE reads it, not this module: the rubric's digest is
    half the reuse condition, so it has to be in hand before the gate decides
    whether to take a judgement at all. Reading it twice — once to decide and
    once to grade — would be two readings of a file a release can replace
    between them, and the verdict would then name a rubric the judge never saw.
    """
    read = attempt(
        action=lambda: dod_gate_prompt_path(payload_root=payload_root).read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    return None if isinstance(read, AttemptFailure) else read


def judgement_prompt(*, gate_prompt: str, subject: str) -> str:
    """The node's prompt, the host ending contract, then the item's subject."""
    return f"{gate_prompt}{HOST_ENDING_CONTRACT}{subject}\n"


def judgement_argv(
    *,
    judge_path: str,
    model: str,
    allowed_directory: Path,
    stream_usage: bool = False,
) -> list[str]:
    """The Claude host-judge invocation, with its prompt supplied on standard input.

    `stream_usage` asks Claude for its streaming JSON transcript, the only output
    form in which a headless call reports the usage of each request it makes. A
    taking that bounds a candidate's input needs that report; a taking that does
    not bound it keeps the plain-text reply, so the flag is opt-in rather than a
    new default every caller inherits.

    `allowed_directory` is the one directory the invocation may read besides its
    own working directory. The call is also isolated from the invoking profile:
    no setting source, no managed settings, no slash commands, a strict empty MCP
    configuration and no session persistence.
    """
    argv = [
        judge_path,
        "-p",
        "--model",
        model,
        "--tools",
        _AVAILABLE_TOOLS,
    ]
    argv.extend(
        (
            "--add-dir",
            str(allowed_directory),
            "--setting-sources",
            "",
            "--managed-settings",
            "{}",
            "--disable-slash-commands",
            "--strict-mcp-config",
            "--no-session-persistence",
        )
    )
    if stream_usage:
        argv.extend(("--output-format", _STREAM_OUTPUT_FORMAT, "--verbose"))
    return argv


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
