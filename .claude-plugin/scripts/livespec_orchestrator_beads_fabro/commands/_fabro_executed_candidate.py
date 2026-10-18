"""WHICH candidate entitlement a run's own labels record for a failed attempt.

`SPECIFICATION/contracts.md` section "Provider-limit permanence and root-cause
surfacing": "The provider is attributed from the recorded executed candidate
identity, never inferred from a shared message literal." Scenario 65's "A
shared provider sentence is attributed to the candidate that ran" grades it.

WHY THE SENTENCE CANNOT ANSWER IT. Claude and Codex both say "You've hit your
usage limit", so the hint list in `_fabro_port_permanent_failure` that
RECOGNISES the ceiling cannot also decide whose allowance is gone -- and the
hint it is measured under maps that sentence to `codex`. On a failing Claude
attempt that is wrong in BOTH directions at once: the dispatcher-owned record
is written under a vendor nothing spent, so it refuses later dispatches on an
intact allowance while the exhausted one stays unheld and is spent again.

WHERE THE IDENTITY COMES FROM: THE FACTORY'S OWN RUN LABELS. Section
"Factory-configurable ACP fallback priority" requires availability evidence to
be discoverable from the factory's NATIVE run records and to survive the
removal of a repository-local dispatch journal, so `_dispatcher_run_labels`
stamps `livespec.acp.<node>.availability` and `livespec.acp.<node>.candidate`
on every dispatch. This module is the READ side of exactly those keys, and it
imports their spelling from that writer rather than repeating it: a reader
that spelled a key its writer does not would find nothing and report an
absent identity, which is the misattribution above arriving silently.

WHY AN ABSENT IDENTITY KEEPS THE v107 CAUSE-TEXT ATTRIBUTION RATHER THAN
REFUSING. `dispatch_run_label_pairs` emits a pair only for a node that
resolved an identity, so an identity-less legacy adapter leaves its node
unlabelled -- and the contract keeps that adapter on "the conservative legacy
posture", covered by legacy provider records and minting them through v107
cause-text attribution. There is no entitlement for a typed hold to be scoped
by, and inventing one would mint an entitlement nobody declared.

AN ENTITLEMENT KEY MAY ARRIVE DIGESTED, and that is read as it stands. An
`availability_key` is opaque by contract, so a key outside the engine's label
alphabet is written as the marked `sha256:` digest `candidate_label_value`
produces. The digest IS what the run recorded, so attributing it is honest;
what it costs is that a LEGACY provider-only record keyed on a digest covers
only identity-less candidates, because `legacy_record_covers_candidate` matches
a built-in candidate's provenance-assigned alias and nothing else. That
narrowness is the right direction for this item -- Scenario 65 requires the
hold to cover the executed candidate's availability domain ONLY -- and the
typed hold path is where an operator-declared identity is scoped properly.

THE NODE KEY IS NORMALIZED BECAUSE THE TWO ENGINES SPELL IT DIFFERENTLY. The
pinned engine keys its outcome map by the bare graph node id (`implement`);
the Petri-era engine keys its stage map by ordinal and visit
(`002-implement@1`, measured on the candidate build's `inspect` payload), and
`_fabro_terminal_evidence` deliberately carries that key WHOLE because the
visit it names is a fact the engine recorded. The label, by contrast, is keyed
on the graph node id alone, because that is what the dispatch resolved its
adapters per. So both affixes are stripped, independently: a key may carry
either, both or neither. No node in this repository's committed graph begins
with digits and a hyphen, so the ordinal strip cannot shadow a real node name.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace

from livespec_orchestrator_beads_fabro.commands._dispatcher_run_labels import (
    AVAILABILITY_LABEL_SUFFIX,
    CANDIDATE_LABEL_SUFFIX,
    NODE_LABEL_PREFIX,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail

__all__: list[str] = [
    "ExecutedCandidate",
    "attributed_provider_limit_failure",
    "executed_candidate_identity",
    "graph_node_id",
    "recorded_availability_keys",
]

# The Petri-era stage key's leading execution ordinal, as the only prefix this
# reader removes. Anchored and digits-only, so a node id that merely contains a
# hyphen keeps every character of its own name.
_STAGE_ORDINAL_PREFIX = re.compile(r"^\d+-")


@dataclass(frozen=True, kw_only=True)
class ExecutedCandidate:
    """The entitlement one run's labels record for ONE node's attempt.

    `node` is the normalized graph node id the label was found under rather
    than the key it was asked about, so a caller can report WHICH node the
    attribution came from without re-deriving the normalization and reaching a
    second answer.

    `availability_key` is required and `candidate_key` optional, which mirrors
    what each one decides. The availability key names whose allowance was
    spent, so without it there is no attribution to make at all; the candidate
    key names WHAT ran, and an attribution missing it is still scoped to the
    right domain.
    """

    node: str
    availability_key: str
    candidate_key: str | None


def executed_candidate_identity(
    *, labels: Mapping[str, str], node: str | None
) -> ExecutedCandidate | None:
    """The entitlement these run labels record for one failing node attempt.

    `None` for every way the question cannot be answered — no failing node was
    established, or the node carries no availability label — because all of
    them leave the caller on the same conservative legacy posture and none of
    them is evidence about a vendor.
    """
    if node is None:
        return None
    graph_node = graph_node_id(node=node)
    availability = _label(labels=labels, node=graph_node, suffix=AVAILABILITY_LABEL_SUFFIX)
    if graph_node == "" or availability is None:
        return None
    return ExecutedCandidate(
        node=graph_node,
        availability_key=availability,
        candidate_key=_label(labels=labels, node=graph_node, suffix=CANDIDATE_LABEL_SUFFIX),
    )


def recorded_availability_keys(*, labels: Mapping[str, str]) -> frozenset[str]:
    """EVERY availability key these run labels record, across every node.

    This is the question a run record nobody could READ leaves open. The
    attribution above asks which entitlement ONE named node spent, which needs
    the record to say which node failed; when the record is unreadable it says
    nothing of the kind, and any of the node attempts the labels name could
    have been the one that spent an allowance. So the honest answer is the
    whole recorded set, and the caller treats each of those entitlements as
    unconfirmed rather than picking one.

    It is derived from the label KEYS rather than from a node list, because
    `dispatch_run_label_pairs` emits a pair only for a node that resolved an
    identity: a reader asking about nodes it already knew could only ever
    return the nodes it already knew.
    """
    prefix = f"{NODE_LABEL_PREFIX}."
    suffix = f".{AVAILABILITY_LABEL_SUFFIX}"
    return frozenset(
        value.strip()
        for key, value in labels.items()
        if key.startswith(prefix) and key.endswith(suffix) and value.strip()
    )


def attributed_provider_limit_failure(
    *, failure: FabroFailureDetail | None, executed: ExecutedCandidate | None
) -> FabroFailureDetail | None:
    """Re-attribute a CLASSIFIED provider-limit failure from what ran.

    The typed flag is the gate, and it is load-bearing rather than defensive:
    a dispatch stamps these labels on every run while a provider ceiling is
    rare, so an attribution that applied itself to any failure would name a
    vendor for an ordinary transport fault and break the invariant
    `FabroFailureDetail` states — that the provider is non-None exactly when
    the flag is set.

    RECOGNITION IS NOT TOUCHED. Whether the failure IS a ceiling stays with
    the cause-text classification that read it; only WHOSE ceiling it was
    moves here. Keeping the two apart is what lets the same message literal
    recognise a ceiling for either vendor without ever naming one.
    """
    if failure is None or not failure.provider_usage_limit or executed is None:
        return failure
    return replace(
        failure,
        provider_usage_limit_provider=executed.availability_key,
        provider_usage_limit_entitlement=executed.candidate_key,
    )


def _label(*, labels: Mapping[str, str], node: str, suffix: str) -> str | None:
    """One of a node's two entitlement labels as non-blank text, or `None`."""
    value = labels.get(f"{NODE_LABEL_PREFIX}.{node}.{suffix}")
    if value is None:
        return None
    return value.strip() or None


def graph_node_id(*, node: str) -> str:
    """The graph node id a recorded node or stage key names.

    The visit suffix is removed before the ordinal prefix so each affix is
    read off the end it was written on; neither step depends on the other
    having found anything.

    PUBLIC because a second surface now has to ask the same question of the
    same two engine spellings. `_dispatcher_terminal_events` matches a stage
    key taken off one engine's record against a node id taken off the other's
    event stream, and a reader spelling that normalization for itself would be
    a third copy of a rule whose whole job is that every caller agrees on it.
    """
    return _STAGE_ORDINAL_PREFIX.sub("", node.split("@", maxsplit=1)[0].strip())
