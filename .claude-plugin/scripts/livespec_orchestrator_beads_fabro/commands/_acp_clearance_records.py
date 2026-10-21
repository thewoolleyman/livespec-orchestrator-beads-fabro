"""The factory-native record ONE operator clearance is, and how it is written.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Observations, successful availability confirmations, and operator
clearances MUST each be recorded as a factory-native record on the
participating factory whose evidence they create or retire -- a confirmation by
the factory run that confirmed it, and an operator clearance by a minimal
factory-native record whose recorded outcome carries the clearance's exact
identity, actor, time, and reason -- so retirement is reconstructible from the
same source as observation."

THE FACTORY IS THE AUTHORITY AND THE JOURNAL IS AN AUDIT REFERENCE, which is
the same division `_acp_factory_hold_records` keeps for the observation half
and the reason this record exists at all. A clearance that lived only in the
clearing repository's own journal would retire the hold for that checkout and
leave every PEER dispatching into a record their operator believes is gone --
and the peer has no access to that journal, so nothing in its evidence would
even hint that a clearance had happened. The same section's "Hold observations
and their retirement evidence MUST remain reconstructible after any
repository-local dispatch journal is removed" is what forbids it outright.

A LABELLED RUN IS THE MINIMAL FACTORY-NATIVE RECORD, and the two halves of it
answer two different questions. The run LABEL is what a reader recognises from
`fabro ps -a --json` alone, before it has spent a per-run read on anything; the
run's recorded OUTCOME is what carries the clearance itself. Putting the
clearance in the label instead would not work and would not be minimal: an
`availability_key` is opaque by contract and a `--reason` is operator prose, so
neither fits the engine's label alphabet, while the outcome is ordinary text
with no shape imposed on it.

THIS MODULE IS PURE AND KNOWS NOTHING ABOUT A FACTORY. It owns the record's
SHAPE -- what one clearance is, which label marks it, and the one line its
recorded outcome carries -- so every decision about that shape is exercisable
with no factory at all. `_acp_clearance_factory_record` beside it owns the
write, and the direction of the one edge between them is what keeps the pair
acyclic, exactly as `_acp_factory_hold_records` and `_acp_factory_hold_evidence`
are split one concern over.

THE OUTCOME IS ONE LINE OF JSON WITH SORTED KEYS. One line because a
deterministic script node's recorded output is read back whole and a
multi-line payload would have to be reassembled from whatever the engine chose
to keep; sorted keys because two Dispatchers rendering one clearance must
produce byte-identical text, which is what lets a reader compare a record
against the clearance it claims to be rather than merely parse it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

__all__: list[str] = [
    "CLEARANCE_LABEL_KEY",
    "CLEARANCE_LABEL_VALUE",
    "CLEARANCE_MARKER_KEY",
    "CLEARANCE_MARKER_VALUE",
    "AcpHoldClearance",
    "clearance_outcome_text",
    "clearance_run_labels",
]

# The ONE label that marks a run as a clearance record. Dotted and
# `livespec.`-prefixed like every other key this Dispatcher writes, so a
# receiver allowlist keys on the prefix rather than on a list of names, and
# deliberately NOT one of `_dispatcher_run_labels`' entitlement keys: a
# clearance spends no allowance, and a row carrying an entitlement label would
# be read by the observation and confirmation arms as an attempt.
CLEARANCE_LABEL_KEY = "livespec.acp.clearance"
CLEARANCE_LABEL_VALUE = "record"

# The marker the recorded outcome's own line carries, so a reader can tell this
# record's line from any other text a run happens to print. It is a field of
# the payload rather than a prefix on it, which keeps the whole line valid JSON
# and therefore readable by one parse instead of a parse plus a strip.
CLEARANCE_MARKER_KEY = "livespec_acp_clearance"
CLEARANCE_MARKER_VALUE = 1


@dataclass(frozen=True, kw_only=True)
class AcpHoldClearance:
    """One operator clearance, as the factory-native record states it.

    The four things the clause requires the recorded outcome to carry are all
    here: the exact IDENTITY is the `(scope, hold_key, candidate_key)` target
    plus the `observation_ids` it resolved to, the ACTOR is `actor`, the TIME
    is `cleared_at`, and the REASON is `reason`.

    `observation_ids` rides beside the target triple rather than instead of it,
    and both are load-bearing. The ids are what make the retirement EXACT --
    an observation minted after the clearance from a genuinely new attempt
    carries a new id and is untouched, with no instant comparison to get wrong
    -- while the triple is what an operator actually named and so is what a
    human reading the record needs in order to recognise their own act.

    `candidate_key` is optional because a domain-scoped clearance names none,
    which is the same asymmetry the hold record keeps: a record's scope decides
    whether the field may be present at all.
    """

    scope: str
    hold_key: str
    candidate_key: str | None
    observation_ids: tuple[str, ...]
    actor: str
    cleared_at: str
    reason: str


def clearance_run_labels() -> tuple[str, ...]:
    """The `KEY=VALUE` run labels a clearance record carries.

    Exactly one pair, which is what "minimal" means here: anything a reader
    needs in order to DECIDE is in the recorded outcome, and the label's whole
    job is to say which rows are worth reading at all.
    """
    return (f"{CLEARANCE_LABEL_KEY}={CLEARANCE_LABEL_VALUE}",)


def clearance_outcome_text(*, clearance: AcpHoldClearance) -> str:
    """The one line this clearance's recorded outcome carries.

    `sort_keys` and the absent separators argument together make the rendering
    a function of the clearance alone -- see the module docstring for why two
    Dispatchers must render one clearance identically.
    """
    return json.dumps(_payload(clearance=clearance), sort_keys=True)


def _payload(*, clearance: AcpHoldClearance) -> Mapping[str, object]:
    """The clearance as the mapping its recorded line encodes."""
    return {
        CLEARANCE_MARKER_KEY: CLEARANCE_MARKER_VALUE,
        "scope": clearance.scope,
        "hold_key": clearance.hold_key,
        "candidate_key": clearance.candidate_key,
        "observation_ids": list(clearance.observation_ids),
        "actor": clearance.actor,
        "cleared_at": clearance.cleared_at,
        "reason": clearance.reason,
    }
