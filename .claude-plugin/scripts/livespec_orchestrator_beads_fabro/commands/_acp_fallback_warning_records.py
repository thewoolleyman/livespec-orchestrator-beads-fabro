"""One MODEL-FALLBACK warning record: its shape, its id, and its leak rules.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Every actually executed non-primary candidate appends one
idempotent journal record and yields one aggregate attention fact per
repository/node with id `hygiene:model-fallback:<repo>:<node>` ... The
newest unresolved observation supplies the deterministic summary."

THE RECORD CARRIES IDENTITIES AND DIGESTS, NEVER MATERIAL. The redaction
rule is stated twice over -- "journals, traces, events, diagnostics, and
refusals MUST store a redacted structural form ... never raw env values
or the full candidate chain", and the event itself "MUST contain no
command, env value, credential, prompt, raw error, or unredacted
diagnostic". A warning is read by a human in an attention row, so the
temptation is to attach the failing command or the provider's own
sentence; the builder below copies named fields off the TYPED event
rather than merging any raw payload, so there is no field an unredacted
string could arrive through.

THE WARNING ID IS A DIGEST OF THE EVENT PLUS ITS NODE, so re-projecting a
run appends nothing new. It is deliberately NOT the hold's
`observation_id`: one failover event mints a hold on the FAILING
candidate and a warning about the EXECUTED one, and the two retire on
entirely different evidence -- a later matching success for the hold, a
later successful PRIMARY attempt for the warning. Sharing one id would
make either retirement silently retire both.

BOTH DIGESTS RIDE ALONG BECAUSE THE LIFECYCLE NEEDS TO TELL THEM APART.
"Primary replacement retires the prior warning as append-only
`superseded`; non-primary chain changes alter only the full-chain digest,
not the primary generation, so they do not strand the warning." A record
carrying only one digest could not distinguish those two edits.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import AcpFallbackEvent
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import parse_hold_instant
from livespec_orchestrator_beads_fabro.commands._acp_schema_fields import non_empty_text

__all__: list[str] = [
    "MODEL_FALLBACK_CLEARED_STAGE",
    "MODEL_FALLBACK_SCHEMA_VERSION",
    "MODEL_FALLBACK_STAGE",
    "MODEL_FALLBACK_SUPERSEDED_STAGE",
    "ModelFallbackWarning",
    "model_fallback_warning_record",
    "parse_model_fallback_warning",
    "warning_id",
]

MODEL_FALLBACK_SCHEMA_VERSION = 1

MODEL_FALLBACK_STAGE = "acp-model-fallback-observed"

# The two retirement stages, kept apart because they assert different
# things: CLEARED says the primary demonstrably works again, SUPERSEDED
# says the primary an operator replaced is no longer the thing warned
# about. Folding them into one stage would lose which of those happened.
MODEL_FALLBACK_CLEARED_STAGE = "acp-model-fallback-cleared"
MODEL_FALLBACK_SUPERSEDED_STAGE = "acp-model-fallback-superseded"

_ID_LENGTH = 24
_ID_PREFIX = "acpwarn-"
_ID_SEPARATOR = "\x00"

_REQUIRED_TEXT: tuple[str, ...] = (
    "warning_id",
    "node",
    "occurred_at",
    "candidate_display_name",
    "candidate_key",
    "availability_key",
    "hold_key",
    "cause",
    "scope",
    "primary_generation",
    "full_chain",
    "event_id",
)


@dataclass(frozen=True, kw_only=True)
class ModelFallbackWarning:
    """One live warning that a non-primary candidate actually ran.

    Every field is an identity, a typed enum value, a digest or an
    instant. Nothing here can hold command text, an env value or a
    provider's raw sentence, which is the redaction rule expressed as a
    type rather than as a review note.
    """

    warning_id: str
    node: str
    occurred_at: str
    candidate_display_name: str
    candidate_key: str
    availability_key: str
    hold_key: str
    cause: str
    scope: str
    primary_generation: str
    full_chain: str
    event_id: str
    candidate_index: int
    work_item_id: str


def warning_id(*, event_id: str, node: str) -> str:
    """The STABLE id re-projecting one event's warning reproduces exactly."""
    material = _ID_SEPARATOR.join((event_id, node))
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:_ID_LENGTH]
    return f"{_ID_PREFIX}{digest}"


def model_fallback_warning_record(
    *, event: AcpFallbackEvent, work_item_id: str
) -> dict[str, object] | None:
    """Build one appendable warning, or `None` when nothing non-primary ran.

    Returning `None` rather than refusing is the right shape here because
    the caller projects EVERY event: exhaustion, and a transition back to
    candidate zero, are ordinary expected records that simply owe no
    warning. Making the caller distinguish them from an error would put
    Scenario 127's "an unexecuted preflight selection for a node never
    reached emits no fallback warning" control in the call site instead
    of here.
    """
    if not event.executed_non_primary:
        return None
    return {
        "stage": MODEL_FALLBACK_STAGE,
        "schema_version": MODEL_FALLBACK_SCHEMA_VERSION,
        "warning_id": warning_id(event_id=event.event_id, node=event.node),
        "node": event.node,
        "occurred_at": event.occurred_at,
        "candidate_display_name": event.to_display_name,
        "candidate_key": event.to_candidate_key,
        "candidate_index": event.to_candidate_index,
        "availability_key": event.from_availability_key,
        "hold_key": event.hold_key,
        "cause": event.cause,
        "scope": event.scope,
        "primary_generation": event.primary_generation,
        "full_chain": event.full_chain,
        "node_visit": event.node_visit,
        "engine_attempt": event.engine_attempt,
        "event_id": event.event_id,
        "work_item_id": work_item_id,
    }


def parse_model_fallback_warning(*, record: Mapping[str, Any]) -> ModelFallbackWarning | str:
    """Read one stored warning, or say why it cannot be read as this version.

    The version check runs first for the reason the hold parser's does: a
    later schema that happens to spell every v1 field must not be read on
    v1's meanings.
    """
    version = record.get("schema_version")
    if version != MODEL_FALLBACK_SCHEMA_VERSION:
        return f"unknown model-fallback warning schema_version {version!r}"
    fields: dict[str, str] = {}
    for name in _REQUIRED_TEXT:
        value = non_empty_text(value=record.get(name))
        if value is None:
            return f"model-fallback warning is missing required text field {name!r}"
        fields[name] = value
    if parse_hold_instant(text=fields["occurred_at"]) is None:
        return f"model-fallback warning occurrence time {fields['occurred_at']!r} is unreadable"
    index = record.get("candidate_index")
    if isinstance(index, bool) or not isinstance(index, int):
        return "model-fallback warning carries no readable candidate_index"
    work_item_id = record.get("work_item_id")
    return ModelFallbackWarning(
        warning_id=fields["warning_id"],
        node=fields["node"],
        occurred_at=fields["occurred_at"],
        candidate_display_name=fields["candidate_display_name"],
        candidate_key=fields["candidate_key"],
        availability_key=fields["availability_key"],
        hold_key=fields["hold_key"],
        cause=fields["cause"],
        scope=fields["scope"],
        primary_generation=fields["primary_generation"],
        full_chain=fields["full_chain"],
        event_id=fields["event_id"],
        candidate_index=index,
        work_item_id=work_item_id if isinstance(work_item_id, str) else "",
    )
