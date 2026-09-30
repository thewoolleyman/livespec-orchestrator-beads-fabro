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

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_schema_fields import (
    missing_keys_refusal,
    non_empty_text,
    unknown_keys_refusal,
)

__all__: list[str] = [
    "ARG_MECHANISM",
    "ENV_MECHANISM",
    "JSON_ENV_MECHANISM",
    "MECHANISM_KEYS",
    "MECHANISM_KINDS",
    "PROTOCOL_MECHANISM",
    "VALUE_PLACEHOLDER",
    "AcpModelMechanism",
    "parse_model_mechanism",
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

# The closed key set one mechanism table may carry.
MECHANISM_KEYS: frozenset[str] = frozenset({"effort", "env", "kind", "model"})

_REQUIRED_MECHANISM_KEYS: frozenset[str] = frozenset({"kind", "model"})


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


def parse_model_mechanism(*, value: object, key: str) -> AcpModelMechanism | str:
    """Parse one agent's declared mechanism table, or refuse naming the key.

    The `env` rule is keyed on `kind` in BOTH directions, and the second
    direction is the one worth having. Requiring `env` for `json_env` catches
    an incomplete mapping; FORBIDDING it elsewhere catches a mapping that reads
    as complete and is not -- an `env`-kind entry carrying `env:
    "CODEX_CONFIG"` looks exactly like a JSON mapping and would silently assign
    the whole model to that variable, destroying the object it was meant to
    merge into.
    """
    if not isinstance(value, dict):
        return f"{key} must be a mechanism table; got {value!r}"
    table = cast("dict[str, Any]", value)
    shape = _shape_refusal(table=table, key=key)
    if shape is not None:
        return shape
    kind = cast("str", table["kind"])
    model = non_empty_text(value=table["model"])
    if model is None:
        return f"{key}.model must be non-empty text; got {table['model']!r}"
    targets = _optional_targets(table=table, key=key)
    if isinstance(targets, str):
        return targets
    effort, carrier = targets
    refusal = _carrier_refusal(kind=kind, carrier=carrier, key=key)
    if refusal is not None:
        return refusal
    return AcpModelMechanism(kind=kind, model=model, effort=effort, env=carrier)


def _shape_refusal(*, table: Mapping[str, Any], key: str) -> str | None:
    """Refuse an unknown key, an incomplete table, or an unrecognised kind.

    The three are one question -- is this table's SHAPE a mechanism at all --
    and they are asked in this order because each later check reads a field the
    earlier one proved present.
    """
    unknown = unknown_keys_refusal(entry=table, allowed=MECHANISM_KEYS, key=key)
    if unknown is not None:
        return unknown
    missing = missing_keys_refusal(entry=table, required=_REQUIRED_MECHANISM_KEYS, key=key)
    if missing is not None:
        return missing
    kind = table["kind"]
    if kind not in MECHANISM_KINDS:
        return f"{key}.kind must be one of {', '.join(MECHANISM_KINDS)}; got {kind!r}"
    return None


def _optional_targets(*, table: Mapping[str, Any], key: str) -> tuple[str, str] | str:
    """The declared `effort` and `env` targets, each empty when absent.

    Both are read in one pass because both are the same question about an
    optional non-empty string, and the pair is what the caller needs; returning
    them separately would need a sentinel to distinguish "absent" from a
    refusal, which is the shape that invites reading a message as a value.
    """
    resolved: list[str] = []
    for name in ("effort", "env"):
        if name not in table:
            resolved.append("")
            continue
        text = non_empty_text(value=table[name])
        if text is None:
            return f"{key}.{name} must be non-empty text; got {table[name]!r}"
        resolved.append(text)
    return (resolved[0], resolved[1])


def _carrier_refusal(*, kind: str, carrier: str, key: str) -> str | None:
    """Refuse an `env` carrier that is missing where it is required, or present
    where it is meaningless."""
    if kind == JSON_ENV_MECHANISM and carrier == "":
        return (
            f"{key}.env must name the environment variable carrying the JSON object "
            f"for the {JSON_ENV_MECHANISM!r} mechanism"
        )
    if kind != JSON_ENV_MECHANISM and carrier != "":
        return (
            f"{key}.env is meaningful only for the {JSON_ENV_MECHANISM!r} mechanism; "
            f"kind {kind!r} declares none"
        )
    return None
