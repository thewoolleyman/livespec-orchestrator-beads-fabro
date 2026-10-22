"""The model the drift pass puts the shared spec-stated judgement through.

The one IMPURE seam `livespec_runtime.spec_stated.judge` is given: a
`ModelRunner` taking a rendered prompt and returning the model's reply. The
judgement itself — the prompt, the verdict schema, the parser — belongs to the
shared runtime module, which "opens no subprocess, no socket and no network
connection of its own and holds no credential"; everything a provider binding
needs is here.

⛔ THE PROMPT TRAVELS ON STANDARD INPUT, NOT AS AN ARGV ENTRY, and that is a
correctness requirement rather than a style choice. The judge prompt carries
the ENTIRE ratified spec tree, which is 1.36 MB in this repository as measured
2026-10-22, while Linux caps a single argv entry at 131072 bytes. A prompt
passed as an argument would make `execve` refuse the launch outright — the
runner maps that to exit 126 — so every merge of every pass would report a
judgement that could not be taken, for a reason nothing in the output names.
`claude -p` with no prompt argument reads the prompt from standard input, so
the prompt is written to a temporary file and that file's descriptor is handed
to the runner.

The temporary file is deleted as the context manager closes, after the child
has exited, which is what keeps a 1.36 MB prompt from accumulating on the host
across the ten-minute ticks of the root reconcile timer.

WHERE THE EXECUTABLE AND THE CREDENTIAL COME FROM IS NOT THIS MODULE'S
DECISION. Both are read through the Definition-of-Done judge's own resolvers —
`resolve_judge_path` and `select_factory_credential` — because this is the same
headless call on the same host, and a second account of "where is `claude`" or
"which credential does this host judge with" would drift from the first on the
next change to either, with both answers looking perfectly plausible.

A NON-ZERO EXIT ANSWERS THE EMPTY STRING, deliberately. The shared judgement's
parser treats a reply it cannot read as a `Failure`, and the drift pass maps
that to one UNPROCESSED merge — which stops the frontier at it. That is the
fail-closed route and it needs no exception: raising here would kill the whole
pass over one merge the next tick would retry anyway, losing every later
merge's finding with it.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_runtime import spec_stated

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    resolve_judge_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
)
from livespec_orchestrator_beads_fabro.effects import FloatParseFailure, parse_float

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "DEFAULT_DRIFT_JUDGE_MODEL",
    "DEFAULT_DRIFT_JUDGE_TIMEOUT_SECONDS",
    "DRIFT_JUDGE_MODEL_ENV",
    "DRIFT_JUDGE_TIMEOUT_ENV",
    "drift_judge",
    "resolve_drift_judge_model",
    "resolve_drift_judge_timeout_seconds",
]

DRIFT_JUDGE_MODEL_ENV = "LIVESPEC_DRIFT_JUDGE_MODEL"
DRIFT_JUDGE_TIMEOUT_ENV = "LIVESPEC_DRIFT_JUDGE_TIMEOUT_SECONDS"
DEFAULT_DRIFT_JUDGE_MODEL = "claude-opus-4-8"
DEFAULT_DRIFT_JUDGE_TIMEOUT_SECONDS = 600.0

_PROMPT_FILE_PREFIX = "livespec-drift-judge-"


def resolve_drift_judge_model(*, environ: dict[str, str]) -> str:
    """The judging model: the env override, else the committed default."""
    return environ.get(DRIFT_JUDGE_MODEL_ENV, "").strip() or DEFAULT_DRIFT_JUDGE_MODEL


def resolve_drift_judge_timeout_seconds(*, environ: dict[str, str]) -> float:
    """The judge's time box, falling back on an absent, bad or non-positive value.

    A zero or negative box is a self-inflicted hang rather than a tighter
    bound, and an unparseable one must not crash a pass whose whole contract is
    to fail soft per merge, so both read as the committed default.
    """
    parsed = parse_float(text=environ.get(DRIFT_JUDGE_TIMEOUT_ENV, ""))
    if isinstance(parsed, FloatParseFailure):
        return DEFAULT_DRIFT_JUDGE_TIMEOUT_SECONDS
    return parsed if parsed > 0 else DEFAULT_DRIFT_JUDGE_TIMEOUT_SECONDS


def drift_judge(*, project_root: Path, runner: CommandRunner) -> spec_stated.ModelRunner:
    """A `ModelRunner` that puts one rendered prompt to the headless judge.

    Returned as a closure rather than a class so that the model, the time box
    and the credential are resolved ONCE per pass: a pass over ten merges must
    not re-read the environment ten times, where two readings of one variable
    could disagree while both looked healthy.
    """
    environ = dict(os.environ)
    credential = select_factory_credential(
        environ=environ, home=Path.home(), warn=lambda message: sys.stderr.write(f"{message}\n")
    )
    judge_environ = dict(environ)
    judge_environ[CLAUDE_OAUTH_TOKEN_ENV] = environ.get(credential.env_name, "")
    argv = [
        resolve_judge_path(environ=environ),
        "-p",
        "--model",
        resolve_drift_judge_model(environ=environ),
    ]
    timeout_seconds = resolve_drift_judge_timeout_seconds(environ=environ)
    # A LAMBDA over a keyword-only helper, because `ModelRunner` is the shared
    # runtime's own type and `spec_stated.judge` calls it POSITIONALLY: the one
    # positional parameter here is fixed by a caller outside this repository,
    # and everything this module itself defines stays keyword-only.
    return lambda prompt: _judged(
        prompt=prompt,
        argv=argv,
        cwd=project_root,
        judge_environ=judge_environ,
        timeout_seconds=timeout_seconds,
        runner=runner,
    )


def _judged(
    *,
    prompt: str,
    argv: list[str],
    cwd: Path,
    judge_environ: dict[str, str],
    timeout_seconds: float,
    runner: CommandRunner,
) -> str:
    """One prompt put to the headless judge on standard input, and its reply."""
    with tempfile.TemporaryDirectory(prefix=_PROMPT_FILE_PREFIX) as scratch:
        prompt_path = Path(scratch) / "prompt.txt"
        _ = prompt_path.write_text(prompt, encoding="utf-8")
        with prompt_path.open("rb") as handle:
            result = runner.run(
                argv=argv,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                env=judge_environ,
                stdin=handle.fileno(),
            )
    return "" if result.exit_code != 0 else result.stdout
