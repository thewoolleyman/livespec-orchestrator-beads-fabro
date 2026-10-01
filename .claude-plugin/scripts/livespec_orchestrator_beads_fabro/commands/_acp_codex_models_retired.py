"""The RETIRED `dispatcher.codex_models` shorthand, and the migration it prints.

`SPECIFICATION/contracts.md` section "Built-in ACP node defaults":
"`dispatcher.codex_models` is retired. A repository routes a node to Codex by
writing a structured entry whose `agent` is `codex-acp` for THAT node; no
class-shaped shorthand exists. A `.livespec.jsonc` that sets
`dispatcher.codex_models` MUST refuse before claim, and the refusal MUST print
the equivalent `dispatcher.acp_nodes` entries ... so the migration is a copy."

THE REFUSAL CARRIES THE MIGRATION BECAUSE THE RETIREMENT DESTROYS THE ONLY PLACE
THE VALUES WERE WRITTEN DOWN. A class-shaped tier named a model and an effort
ONCE and expanded them across three nodes; the structured form names them per
node. An operator re-deriving that mapping by hand has to know which nodes the
`implementer` class covered, which is exactly the knowledge the retirement
removes from the configuration surface. So this module prints the entries rather
than describing them, and prints the values the operator actually wrote rather
than a worked example.

THE BUILT-IN TIER VALUES ARE RESTATED HERE, NOT IMPORTED, BECAUSE THEY NO LONGER
EXIST ANYWHERE ELSE. They were the defaults a PARTIAL tier table inherited -- a
repository that wrote `{"implementer": {}}` ran `gpt-5.5` at `low` -- so a
migration that omitted them would silently re-point such a node at whatever the
structured form resolves instead. They are frozen historical values describing
what the retired key DID, and they are deliberately not a live default: nothing
here is consulted unless the retired key is present, and its presence refuses.

THE UN-PINNED TIER MIGRATES TO THE MANUAL FORM. The same section defines the
opt-out as "a MANUAL-form candidate whose `command` is the baked path ... and
whose `CODEX_CONFIG` carries no `model` key" and states that "there is no
structured spelling of the opt-out". Printing a structured entry for a `model:
""` tier would therefore re-pin a node its operator had deliberately un-pinned,
which is the one migration error this message exists to prevent.

KNOWN CONSEQUENCE, recorded rather than hidden: a retired tier's
`compaction_token_limit` has no structured spelling either. It survives as an
ordinary adapter ARGUMENT on a manual-form entry -- where section "ACP node
timeouts" already puts it -- and the refusal does not print it, because the
ratified migration above is the `{agent, model, effort}` triple. The loss is not
silent: the dispatch refuses, so the operator rewrites the entry rather than
discovering the drop in a run transcript.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import CODEX_ADAPTER_BASE

__all__: list[str] = [
    "CODEX_MODELS_KEY",
    "codex_models_retirement_refusal",
]

CODEX_MODELS_KEY = "codex_models"

_ACP_NODES_KEY = "acp_nodes"
_CODEX_AGENT_ID = "codex-acp"
_TIER_MODEL_KEY = "model"
_TIER_EFFORT_KEY = "reasoning_effort"

# Each retired class, the nodes it covered, and the values a PARTIAL table of it
# inherited. The node tuples are the contract's own enumeration.
_RETIRED_CLASSES: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    ("implementer", ("implement", "fix", "review_fix"), "gpt-5.5", "low"),
    ("pr", ("pr",), "gpt-5.3-codex-spark", "high"),
)


def codex_models_retirement_refusal(*, block: Mapping[str, Any]) -> str | None:
    """The retirement refusal for a block that sets the key, else `None`.

    Keyed on the key's PRESENCE rather than on its contents: the contract
    retires the key itself, so a malformed value refuses for the same reason a
    well-formed one does. A malformed value simply contributes no migration
    lines, because there is nothing in it to copy.
    """
    if CODEX_MODELS_KEY not in block:
        return None
    models = block[CODEX_MODELS_KEY]
    lines = [
        line
        for class_name, nodes, default_model, default_effort in _RETIRED_CLASSES
        for line in _class_lines(
            models=models,
            class_name=class_name,
            nodes=nodes,
            default_model=default_model,
            default_effort=default_effort,
        )
    ]
    return "\n".join([_header(), *lines, _footer()])


def _header() -> str:
    """Why the dispatch refused, and what replaces the retired key."""
    return (
        f"dispatcher.{CODEX_MODELS_KEY} is retired; no class-shaped shorthand expands into the "
        f"per-repository layer. Route each node to Codex with its own structured "
        f"dispatcher.{_ACP_NODES_KEY} entry. The equivalent configuration is:"
    )


def _footer() -> str:
    """The one thing the printed entries cannot carry."""
    return (
        f"Remove dispatcher.{CODEX_MODELS_KEY} and add the entries above under "
        f"dispatcher.{_ACP_NODES_KEY}."
    )


def _class_lines(
    *,
    models: object,
    class_name: str,
    nodes: tuple[str, ...],
    default_model: str,
    default_effort: str,
) -> list[str]:
    """One migration line per node this class covered, if it was configured."""
    tier = _tier_table(models=models, class_name=class_name)
    if tier is None:
        return []
    model = _tier_string(tier=tier, key=_TIER_MODEL_KEY, default=default_model)
    effort = _tier_string(tier=tier, key=_TIER_EFFORT_KEY, default=default_effort)
    entry = _entry(model=model, effort=effort)
    return [f"  dispatcher.{_ACP_NODES_KEY}.{node}: {entry}" for node in nodes]


def _tier_table(*, models: object, class_name: str) -> Mapping[str, Any] | None:
    """One class's declared table, or `None` when it declared none.

    A non-table `codex_models`, and a non-table entry under it, both resolve to
    `None` for the same reason: there is no model or effort in them to copy, and
    the refusal above does not depend on finding one.
    """
    if not isinstance(models, dict):
        return None
    entry = cast("dict[str, Any]", models).get(class_name)
    if not isinstance(entry, dict):
        return None
    return cast("dict[str, Any]", entry)


def _tier_string(*, tier: Mapping[str, Any], key: str, default: str) -> str:
    """One tier field, falling back to what a partial table used to inherit."""
    value = tier.get(key)
    return value if isinstance(value, str) else default


def _entry(*, model: str, effort: str) -> str:
    """The `dispatcher.acp_nodes` value replacing one covered node's tier.

    An EMPTY model is the retired opt-out, which has no structured spelling, so
    it migrates to the manual-form un-pinned base string instead. Spelling it as
    a JSON string is what makes the line copyable into a `.livespec.jsonc`: the
    base string carries single quotes of its own, and the escaping is the
    difference between a value that pastes and one that has to be repaired.
    """
    if model == "":
        return json.dumps(CODEX_ADAPTER_BASE)
    return json.dumps({"agent": _CODEX_AGENT_ID, "model": model, "effort": effort})
