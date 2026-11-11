"""Rendering the committed run config's `inputs.*` tokens HOST-SIDE.

`_dispatcher_overlay` ASSEMBLES the whole run-config overlay; this module owns
one self-contained concern inside it — substituting the `{{ inputs.<name> }}`
tokens the committed `run.prepare` commands are templated with, because the
engine does not render that site. The two are separate concerns and separate
files for that reason: the assembly is about which projections one dispatch
declares, while this is the TOML-string surgery that makes a templated prepare
command executable.

Only `substitute_input_tokens` crosses the module boundary. The escaper below
it is reached from nowhere else and stays private here, because importing a
`_`-prefixed name across modules is what pyright strict's `reportPrivateUsage`
and this repository's `private_calls` check both reject.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

__all__: list[str] = [
    "substitute_input_tokens",
]

# The `{{ inputs.<name> }}` token the committed run config templates its prepare
# commands with. The name grammar is deliberately narrow (an identifier), so a
# MiniJinja expression this substituter does not understand is left for whatever
# does.
_INPUT_TOKEN_RE = re.compile(r"\{\{\s*inputs\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def substitute_input_tokens(*, text: str, prepare_inputs: Mapping[str, str] | None) -> str:
    """Render the run config's `inputs.*` tokens HOST-SIDE, because the engine does not.

    fabro 0.254.0 renders `inputs.*` in graph node attributes at run-create time
    and leaves `run.prepare` commands verbatim, so a templated prepare step
    reaches bash as a literal `{{` and kills the run in setup at exit 127 before
    any agent node runs. The committed payload has templated its toolchain and
    conformance premises that way since the typed-integration-contract change,
    which made every dispatch through it unrunnable.

    Substituting here rather than asking the engine to change keeps the values
    on the one already-resolved `ResolvedIntegrationContract` the `--input`
    pairs are rendered from, so the run config and the run's bound inputs cannot
    drift apart. The `--input` pairs are still sent: they are what the GRAPH
    reads, and the graph half works.

    A name the mapping does not carry is LEFT ALONE rather than blanked. An
    unresolved premise then fails visibly at its own step, instead of quietly
    becoming a no-op — which is the failure mode that made the sibling
    conformance-gate defect dangerous.
    """
    if not prepare_inputs:
        return text
    rendered: list[str] = []
    cursor = 0
    for match in _INPUT_TOKEN_RE.finditer(text):
        value = prepare_inputs.get(match.group(1))
        if value is None:
            continue
        rendered.append(text[cursor : match.start()])
        rendered.append(_escape_toml_basic_string(value=value))
        cursor = match.end()
    rendered.append(text[cursor:])
    return "".join(rendered)


def _escape_toml_basic_string(*, value: str) -> str:
    """Escape a substituted value for the TOML basic string it lands inside.

    Every token sits within `script = "..."`. Contract values arrive as one
    shell word-list from `shlex.join`, and `shlex.quote` emits the `'"'"'`
    sandwich for an embedded apostrophe — which carries double quotes. Written
    raw, one of those terminates the TOML string early and makes the WHOLE
    overlay unparseable, turning one repository's command into a dispatch-wide
    failure. Backslash first, so the quote escape is not re-escaped.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')
