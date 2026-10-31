"""Moving the scripted publication stages' command bodies out of the agent prompt.

WHY THE BODIES LEAVE THE GRAPH. The Petri-era engine's default `compact` fidelity
renders every completed command stage into the preamble of every later agent
request as its FULL `Script:` text. The `publish_draft`, `pr_refresh`, `pr` and
`pr_refresh_head` scripts are about 58,000 characters (roughly 25,000 tokens)
that no agent turn reads, re-sent to `review`, `proof_verify` and
`proof_capture` (`plan/factory-context-per-turn-reduction`, research note 006).

So the Dispatcher splits each of those nodes in the PER-DISPATCH copy of the
graph. The committed graph is untouched and stays the one place the scripts are
written and tested. The copy's `script` becomes a short invocation of a helper
file; the helper's bytes ride the `env` of ONE prepare step, which the engine's
preamble does not render (`_dispatcher_prepare_payload`), and a shell writes
them below the sandbox plugins root before any stage runs.

HOW THE ENGINE'S TEMPLATE INPUTS REACH THE HELPER. A helper file is never
template-expanded, so each input token in a body is replaced by an expansion of
a variable the NODE's own short script sets from the same token, which the
engine still expands exactly as it did when the token sat in the body.
`default_branch`, `merge_hold` and `merge_mode` are single values and travel as
`LIVESPEC_STAGE_INPUT_*` environment assignments. `sandbox_check_suite` is the
declared check-suite command line, which one engine hands the script as a single
shell-quoted word and another as several raw words; both reach the helper as its
positional arguments, and the helper re-quotes every word so the function that
used to say `set -- <the token>` rebuilds precisely the argument list it was
given, whichever engine rendered it.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "STAGE_SCRIPT_NODES",
    "StageScripts",
    "externalize_stage_scripts",
    "materialize_stage_helpers",
    "stage_script_filename",
    "stage_script_prepare_steps_block",
]

STAGE_SCRIPT_NODES: tuple[str, ...] = ("publish_draft", "pr_refresh", "pr", "pr_refresh_head")

_ENV_INPUTS: Mapping[str, str] = {
    "default_branch": "LIVESPEC_STAGE_INPUT_DEFAULT_BRANCH",
    "merge_hold": "LIVESPEC_STAGE_INPUT_MERGE_HOLD",
    "merge_mode": "LIVESPEC_STAGE_INPUT_MERGE_MODE",
}
_SUITE_INPUT = "sandbox_check_suite"
_OPEN = "{" + "{"
_CLOSE = "}" + "}"
_TOKEN = re.compile(r"\{\{ inputs\.(\w+) \}\}")
_SUITE_TOKEN = f"{_OPEN} inputs.{_SUITE_INPUT} {_CLOSE}"
_SUITE_SET = f"set -- {_SUITE_TOKEN}"
_SUITE_REBUILD = 'eval "set -- $livespec_suite_words"'
_SUITE_CAPTURE = r"""livespec_suite_words=''
for livespec_suite_word in "$@"; do
  livespec_suite_quoted=$(printf '%s' "$livespec_suite_word" | sed "s/'/'\\\\''/g")
  livespec_suite_words="$livespec_suite_words '$livespec_suite_quoted'"
done
set --
"""


@dataclass(frozen=True, kw_only=True)
class StageScripts:
    """A graph with the stage scripts externalized, and the helper each one became."""

    text: str
    helpers: Mapping[str, str]


def stage_script_filename(*, node: str) -> str:
    """The helper file a node's invocation runs, below the sandbox plugins root."""
    return f"livespec-stage-{node}.sh"


def externalize_stage_scripts(*, graph_text: str) -> StageScripts | str:
    """Replace each present stage node's script with an invocation of its helper.

    A node the graph does not declare is left alone, because a registered
    variant need not carry the scripted stages at all. Returns an actionable
    refusal when a script names an input this projection has no seam for: a
    token left in a helper would reach the shell unexpanded.
    """
    text = graph_text
    helpers: dict[str, str] = {}
    for node in STAGE_SCRIPT_NODES:
        found = _script_attribute(text=text, node=node)
        if found is None:
            continue
        built = _helper_and_invocation(node=node, body=_unescape(raw=found.group("raw")))
        if isinstance(built, str):
            return built
        helper, invocation = built
        helpers[node] = helper
        text = text[: found.start("raw")] + _escape(value=invocation) + text[found.end("raw") :]
    return StageScripts(text=text, helpers=helpers)


def materialize_stage_helpers(*, committed_graph: Path, rendered_graph: Path) -> None:
    """Write only helpers invoked by the rendered graph from the tracked source.

    This executes inside the sandbox after its clone and virtual environment are
    prepared.  Keeping the bodies in the tracked graph means the generated run
    config contains only this short extraction invocation, never an env payload
    holding tens of kilobytes of command text.
    """
    rendered = rendered_graph.read_text(encoding="utf-8")
    committed = committed_graph.read_text(encoding="utf-8")
    split = externalize_stage_scripts(graph_text=committed)
    if isinstance(split, str):
        raise TypeError(split)
    root = Path(
        os.environ.get("LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT", Path.home() / ".claude/plugins")
    )
    root.mkdir(parents=True, exist_ok=True)
    for node, helper in split.helpers.items():
        if stage_script_filename(node=node) in rendered:
            path = root / stage_script_filename(node=node)
            _ = path.write_text(helper, encoding="utf-8")
            _ = path.chmod(0o700)


def stage_script_prepare_steps_block(
    *, committed_graph: Path, rendered_graph: Path | None
) -> str | None:
    """Render a short sandbox extraction step for the externalized helpers."""
    if rendered_graph is None:
        return ""
    rendered = attempt(
        action=lambda: rendered_graph.read_text(encoding="utf-8"), exceptions=(OSError,)
    )
    committed = attempt(
        action=lambda: committed_graph.read_text(encoding="utf-8"), exceptions=(OSError,)
    )
    if isinstance(rendered, AttemptFailure) or isinstance(committed, AttemptFailure):
        return None
    split = externalize_stage_scripts(graph_text=committed)
    if isinstance(split, str):
        return None
    wanted = [
        (node, helper)
        for node, helper in split.helpers.items()
        if stage_script_filename(node=node) in rendered
    ]
    if not wanted:
        return ""
    _ = wanted
    command = (
        "from pathlib import Path; "
        "from livespec_orchestrator_beads_fabro.commands._dispatcher_stage_scripts "
        "import materialize_stage_helpers; "
        f"materialize_stage_helpers(committed_graph=Path({str(committed_graph)!r}), "
        f"rendered_graph=Path({str(rendered_graph)!r}))"
    )
    script = f"set -eu\nuv run python -c {shlex.quote(command)}"
    header = (
        "\n# --- Dispatcher-materialized scripted publication stages: the bodies the\n"
        "# --- compact preamble would otherwise re-send to every later agent node ---\n"
    )
    return header + "[[run.prepare.steps]]\nscript = " + json.dumps(script) + "\n"


def _script_attribute(*, text: str, node: str) -> re.Match[str] | None:
    """The node's one-line `script` attribute value, as the file carries it."""
    pattern = re.compile(
        rf'(?m)^    {node} \[\n(?:        (?!script=")[^\n]*\n)*        script="(?P<raw>[^\n]*)"$'
    )
    return pattern.search(text)


def _helper_and_invocation(*, node: str, body: str) -> tuple[str, str] | str:
    """The helper file's text and the node's replacement script, or a refusal."""
    source = body.replace(_SUITE_SET, _SUITE_REBUILD)
    names = sorted(set(_TOKEN.findall(source)))
    unknown = [name for name in names if name not in _ENV_INPUTS]
    if unknown:
        return (
            f"workflow node {node} script uses template input(s) {', '.join(unknown)} that the "
            "stage-script externalization cannot pass to a helper file"
        )
    helper = _TOKEN.sub(lambda match: "${" + _ENV_INPUTS[match.group(1)] + "}", source)
    uses_suite = _SUITE_REBUILD in source
    if uses_suite:
        helper = _SUITE_CAPTURE + helper
    assignments = "".join(f"{_ENV_INPUTS[name]}={_OPEN} inputs.{name} {_CLOSE} " for name in names)
    path = f"{sandbox_plugins_root_expansion()}/{stage_script_filename(node=node)}"
    suite = f" {_SUITE_TOKEN}" if uses_suite else ""
    return helper + "\n", f'{assignments}sh "{path}"{suite}'


def _unescape(*, raw: str) -> str:
    return re.sub(r'\\([\\"])', r"\1", raw)


def _escape(*, value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
