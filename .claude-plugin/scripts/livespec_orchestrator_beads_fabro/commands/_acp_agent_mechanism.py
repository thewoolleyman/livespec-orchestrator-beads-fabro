"""HOW one agent takes `model` and `effort` -- exactly one mechanism per agent.

`SPECIFICATION/contracts.md` section "Agent and model catalogs" makes each
agent entry declare "the mechanism by which the agent takes `model` and
`effort`, EXACTLY ONE of `protocol` (ACP session config options) or an explicit
per-agent environment or argument mapping", and section
"Factory-configurable ACP fallback priority" -> "In-protocol model and effort
selection" adds that "the two mechanisms MUST NOT be combined for one
candidate".

WHY THE MECHANISM IS DATA RATHER THAN A BRANCH PER AGENT. The alternative --
a renderer that knows "Claude takes `ANTHROPIC_MODEL`, Codex takes
`CODEX_CONFIG`" -- puts the provider list back in the code, which is the exact
thing the adapter-configuration contract exists to remove: "Switching any node
to any model behind any provider protocol ... MUST be a configuration change
with no code change." With the mapping as data, a new agent is a catalog entry.

THE FOUR KINDS, and why `json_env` is not just `env`. `env` assigns the model
to its own environment variable. `json_env` merges the model INTO A JSON OBJECT
that one environment variable already carries -- which is what the ratified
Codex form requires: section "Built-in ACP node defaults" spells out that a
pinned adapter is "the un-pinned base string with `model` and
`model_reasoning_effort` ADDED inside `CODEX_CONFIG`, the object's keys
remaining in sorted order". An `env` mapping could only REPLACE that object and
would drop the posture keys the same section says are ALWAYS present. `arg`
carries the settings on the command line for an adapter whose own interface
takes them there, and `protocol` carries nothing into the adapter at all: the
requested values ride the rendered chain's `config_options` instead.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "ARG_MECHANISM",
    "ENV_MECHANISM",
    "JSON_ENV_MECHANISM",
    "MECHANISM_KINDS",
    "PROTOCOL_MECHANISM",
    "VALUE_PLACEHOLDER",
    "AcpModelMechanism",
]

# The in-protocol mechanism: the Dispatcher renders NOTHING into the adapter
# and the rendered chain candidate carries a `config_options` object instead.
PROTOCOL_MECHANISM = "protocol"

# The model rides its own environment variable, e.g. `ANTHROPIC_MODEL`.
ENV_MECHANISM = "env"

# The model rides a JSON object an environment variable already carries, e.g.
# `CODEX_CONFIG`. The object's other keys survive and its key order stays
# sorted, which is what makes the ratified Codex bytes reproducible.
JSON_ENV_MECHANISM = "json_env"

# The model rides the command line. The mapping value is a shell-tokenized
# template, so one setting may contribute several argv tokens (`-c model=...`
# is two).
ARG_MECHANISM = "arg"

MECHANISM_KINDS: tuple[str, ...] = (
    ARG_MECHANISM,
    ENV_MECHANISM,
    JSON_ENV_MECHANISM,
    PROTOCOL_MECHANISM,
)

# What an `arg` template substitutes. Spelled as a placeholder rather than a
# positional format so a template carrying a literal brace is unambiguous.
VALUE_PLACEHOLDER = "{value}"


@dataclass(frozen=True, kw_only=True)
class AcpModelMechanism:
    """One agent's declared route for `model` and, when set, `effort`.

    `model` and `effort` are the mechanism's TARGETS, and what each one names
    depends on `kind`: an environment variable for `env`, a key inside the
    JSON object for `json_env`, an argv template for `arg`, and an ACP session
    config option id for `protocol`. `effort` is empty when the agent exposes
    no effort route at all, which is different from an agent that exposes one
    and a candidate that sets none.

    `env` is the environment variable carrying the JSON object, and it is
    meaningful ONLY for `json_env`. Its emptiness elsewhere is not a default:
    the grammar refuses the key outside that kind, so an empty value here
    cannot be mistaken for one an operator wrote.
    """

    kind: str
    model: str
    effort: str = ""
    env: str = ""
