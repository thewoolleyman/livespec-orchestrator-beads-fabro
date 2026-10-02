"""The implement node's adapter label, as one bounded grouping dimension.

Plan `factory-test-first-enforcement` slice S3 (work-item `bd-ib-3h5vfq`)
requires a Honeycomb board showing post-hoc Red share grouped by REPOSITORY
and by ADAPTER. `repo` already rides the `dispatcher.calibration` span; the
adapter did not, so this module derives it.

WHY THE CATALOG CLASSIFIES AND NOT A HAND PARSE. A resolved adapter is a whole
command line — environment assignments, an executable, arguments — and it is
the WRONG thing to put on a span: it is unbounded, it would be truncated by the
egress attribute cap, and two spellings of one agent would group as two
adapters. The committed agent catalog (`_acp_agent_catalog`) is the one place
that knows which rendered bytes belong to which registry agent id, so the
label is that id, and an adapter no catalog entry explains is
`UNKNOWN_ADAPTER` rather than a guess parsed out of the first token.

WHY THE JOURNAL IS THE SOURCE. `_dispatcher_acp_nodes.prepare_acp_nodes`
already resolves every node's adapter ONCE per dispatch and journals the
result, and calibration already reads that journal back for its fix-loop
count. Re-resolving the adapter here would be a second read of the same
configuration that nothing can prove agrees with the first — the exact
resolve-once-project-everywhere rule the integration contract follows.

TWO RECORD SHAPES, both handled. A legacy no-fallback node journals its
`adapter` as the rendered string; a fallback-enabled node journals the
REDACTED STRUCTURAL form instead (`command` plus `args`, never raw env
values), per `SPECIFICATION/contracts.md` section "Factory-configurable ACP
fallback priority". Classifying from `command` + `args` is therefore correct
for both, and it never touches an env value.

A dispatch with no `acp-nodes` record for the item — a refusal before the
resolution, or an entry point that never resolved nodes — reads as `None`:
unobservable, never a false label. A repository that REPLACES a shipped
catalog entry keeps that entry's id, so the label vocabulary is unchanged; a
repository that adds a wholly new agent whose launch distribution this
committed snapshot does not carry reads as `UNKNOWN_ADAPTER`.

This module is PURE: no IO, no environment reads, and it never raises.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import (
    builtin_agent_catalog,
)
from livespec_orchestrator_beads_fabro.commands._acp_agent_entry import AcpAgentEntry
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import ACP_NODES_STAGE

__all__: list[str] = [
    "IMPLEMENT_NODE",
    "UNKNOWN_ADAPTER",
    "adapter_label_for",
    "implement_adapter_label",
]

# The workflow node whose adapter writes the code, and therefore the one whose
# identity a test-first measurement is about. The other nodes (review, pr,
# janitor) do not author commits.
IMPLEMENT_NODE = "implement"

# The label for an adapter the committed catalog cannot explain. It NAMES the
# condition rather than leaving the field absent, so a board grouping by
# adapter shows the unclassified population instead of silently dropping it.
UNKNOWN_ADAPTER = "unknown"

_ACP_NODES_FIELD = "acp_nodes"
_RENDERED_FIELD = "adapter"
_COMMAND_FIELD = "command"
_ARGS_FIELD = "args"


def implement_adapter_label(
    *, records: tuple[Mapping[str, object], ...], work_item_id: str
) -> str | None:
    """The registry agent id of this dispatch's implement adapter, or None.

    Reads the LAST `acp-nodes` record for `work_item_id` — the most recent
    resolution is the one the run executed — and classifies its `implement`
    entry. `None` means no such record exists or its shape carries no adapter
    to classify.
    """
    entry = _implement_entry(records=records, work_item_id=work_item_id)
    if entry is None:
        return None
    return adapter_label_for(text=_adapter_text(entry=entry), catalog=builtin_agent_catalog())


def adapter_label_for(*, text: str, catalog: Mapping[str, AcpAgentEntry]) -> str:
    """Classify one resolved adapter's bytes against a catalog snapshot.

    The LONGEST matching launch command wins. Length is the discriminator
    because one entry's command can be a prefix of another's (`npx` against
    `npx -y @agentclientprotocol/claude-agent-acp`), and the more specific
    match is the one that identifies the agent.
    """
    matched = [
        agent_id for agent_id, entry in catalog.items() if entry.command and entry.command in text
    ]
    if not matched:
        return UNKNOWN_ADAPTER
    return max(matched, key=lambda agent_id: len(catalog[agent_id].command))


def _implement_entry(
    *, records: tuple[Mapping[str, object], ...], work_item_id: str
) -> Mapping[str, object] | None:
    """The implement node's journaled resolution for this item, or None."""
    found: Mapping[str, object] | None = None
    for record in records:
        if record.get("stage") != ACP_NODES_STAGE or record.get("work_item_id") != work_item_id:
            continue
        nodes = record.get(_ACP_NODES_FIELD)
        if not isinstance(nodes, dict):
            continue
        entry = cast("dict[str, object]", nodes).get(IMPLEMENT_NODE)
        if isinstance(entry, dict):
            found = cast("dict[str, object]", entry)
    return found


def _adapter_text(*, entry: Mapping[str, object]) -> str:
    """The bytes to classify, from either journaled record shape.

    The legacy shape's rendered `adapter` string is used as-is. The structural
    shape is reassembled from `command` plus the string members of `args` —
    env values are deliberately absent from that record and are not needed to
    identify the agent.

    An entry carrying NEITHER shape yields the empty string, which classifies
    as `UNKNOWN_ADAPTER` rather than as unobservable: the node WAS resolved
    and journaled, so the honest report is an adapter the catalog cannot
    explain, not an absent resolution.
    """
    rendered = entry.get(_RENDERED_FIELD)
    if isinstance(rendered, str):
        return rendered
    command = entry.get(_COMMAND_FIELD)
    raw_args = entry.get(_ARGS_FIELD)
    args = cast("list[object]", raw_args) if isinstance(raw_args, list) else []
    return " ".join(
        ([command] if isinstance(command, str) else [])
        + [arg for arg in args if isinstance(arg, str)]
    )
