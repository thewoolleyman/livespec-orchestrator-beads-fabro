"""The SHAPE of one availability confirmation turn: a bounded minimal factory run.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry": "Availability is
confirmed only by a successfully completed ACP prompt turn using the
candidate's pinned adapter version, requested model and effort, and projected
worker credential identity. ... A host-side probe is permitted only when these
execution properties are equivalent and its outcome is durably observable
through the same authoritative evidence source; otherwise the probe MUST be a
minimal factory run. The probe sends one fixed minimal prompt."

THIS IS WHAT `_acp_availability_confirmation` HAD NOTHING TO RUN. That module
decides WHICH expired observations a successful attempt satisfies and has done
since `bd-ib-nk7jiz`; what no build carried was an attempt to satisfy them
with. So every expiry waited for an ordinary dispatch to rediscover the outage
by failing, against measured outages lasting DAYS and a fifteen-minute bounded
expiry. This module is the probe's shape, `_acp_availability_probe_outcome` is
what one ending MEANS, and `_acp_availability_probe_run` performs it -- the same
decision/record/perform split `_acp_failure_classifier` / `_acp_hold_records` /
`_acp_hold_ledger` take one level down.

A HOST-SIDE PROBE IS NOT AVAILABLE TO US, which is why this is a factory run and
not a subprocess. The clause permits one only when its execution properties are
equivalent AND its outcome is "durably observable through the same authoritative
evidence source" -- and that source is the factory's own run records, which
nothing host-side writes. So the probe is a run, and its own success becomes
host-wide evidence through the reader that already exists.

ONE ACP NODE IS THE WHOLE OF "MINIMAL". A second adapter-bearing node would
spend a second allowance per probe, and a script node would put a recorded
success on a node that launched no adapter -- which the succeeded-attempt reader
below would then read as a confirmation of an allowance nothing spent.

THE LABELS ARE THE MECHANISM, NOT A DECORATION. `_acp_factory_hold_evidence.
_successes` derives a `FactorySuccessObservation` from a succeeded node attempt
only where the run's labels record an entitlement for THAT NODE'S OWN ID, and
`confirmations_for_successes` then turns it into the confirmation
`_acp_candidate_preflight` consults. So labelling the probe node with the
candidate's entitlement is what makes a confirmation discoverable host-wide,
by every repository dispatching to the factory, with no peer list and no
sidecar -- the clause's own requirement, satisfied by the reader already built.

WHY THE OBSERVATION IDS ARE NOT IN A LABEL. Which expired observations a
confirmation satisfies is DERIVED, by `retired_by_success`, from the attempt's
own start instant and the hold's scope -- the ratified "MUST NOT satisfy a newer
observation" rule. A label naming them would be a second account of that
derivation, and the two could disagree: an id list rendered when the probe was
launched cannot know which records expired while it ran. The ids this probe
WOULD satisfy travel on its journal record instead, where they are provenance
rather than a decision.

TWO CANDIDATES ARE REFUSED BEFORE ANY RUN EXISTS, and both refusals are the
conservative direction rather than a limitation to work around.

An IDENTITY-LESS candidate belongs to no typed domain, so no typed observation
can be about it and there is nothing for a confirmation to satisfy; its
conservative legacy posture -- covered by every live legacy record -- is what
governs it instead, exactly as `outstanding_confirmation_holds` already says.

An IN-PROTOCOL candidate carries its requested model and effort in
`config_options` and NOTHING in its adapter (`_acp_agent_mechanism`:
"`protocol` carries nothing into the adapter at all"), and no build renders
those options into a run. A turn that did not use the requested model has not
confirmed "the candidate's pinned adapter version, requested model and effort",
so claiming it had would confirm a model nobody ran -- the one thing this whole
clause exists to stop. Such a candidate is therefore skipped for the evaluation
with no hold, which is the clause's own "any other probe failure" route, and it
becomes probeable the moment `config_options` reaches a rendered run.
"""

from __future__ import annotations

from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import render_adapter
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_labels import (
    AVAILABILITY_LABEL_SUFFIX,
    CANDIDATE_LABEL_SUFFIX,
    NODE_LABEL_PREFIX,
    candidate_label_value,
)

__all__: list[str] = [
    "AVAILABILITY_PROBE_GOAL",
    "AVAILABILITY_PROBE_GRAPH_FILE",
    "AVAILABILITY_PROBE_LABEL_KEY",
    "AVAILABILITY_PROBE_LABEL_VALUE",
    "AVAILABILITY_PROBE_MANIFEST",
    "AVAILABILITY_PROBE_NODE",
    "AVAILABILITY_PROBE_PROMPT",
    "availability_probe_graph",
    "availability_probe_labels",
    "availability_probe_refusal",
    "is_availability_probe_run",
]

# The ONE node whose completed turn is the confirmation. Named for what it does
# rather than for the candidate it runs, so every probe row carries the same
# node id and the succeeded-attempt reader joins on one name.
AVAILABILITY_PROBE_NODE = "confirm"
AVAILABILITY_PROBE_GRAPH_FILE = "availability-probe.fabro"
AVAILABILITY_PROBE_MANIFEST = f'[workflow]\ngraph = "{AVAILABILITY_PROBE_GRAPH_FILE}"\n'
AVAILABILITY_PROBE_GOAL = "Confirm one ACP candidate's availability.\n"

# The one fixed minimal prompt. FIXED, so two probes of one candidate are the
# same measurement, and MINIMAL, so a confirmation costs the smallest turn the
# provider will bill: it asks for a single word and forbids every tool the node
# could otherwise reach for. It carries no quotation mark and no backslash, so
# it needs no escaping in the attribute that carries it -- which is asserted
# rather than assumed, because an escaped prompt would no longer be the prompt
# the clause says is fixed.
AVAILABILITY_PROBE_PROMPT = "Reply with the single word OK. Make no changes and read no files."

# The ONE label that marks a run as a confirmation turn. Dotted and
# `livespec.`-prefixed like every other key this Dispatcher writes, and
# deliberately NOT one of the per-node entitlement keys: it says which rows are
# probes, while the entitlement labels beside it say what the probe ran.
AVAILABILITY_PROBE_LABEL_KEY = "livespec.acp.probe"
AVAILABILITY_PROBE_LABEL_VALUE = "availability-confirmation"


def availability_probe_refusal(*, candidate: AcpCandidate) -> str | None:
    """Why no confirmation turn can be run for this candidate, or `None`.

    A refusal is NOT a hold and NOT a failure of the candidate: it is the
    clause's "any other probe failure", which skips the candidate for the
    current evaluation and leaves selection to continue. See the module
    docstring for why each of the two is the conservative direction.
    """
    if candidate.identity is None:
        return (
            "this candidate declares no identity, so no typed availability "
            "observation is about it and a confirmation turn would satisfy nothing; "
            "its conservative legacy coverage governs it instead"
        )
    if candidate.config_options:
        return (
            "this candidate requests its model and effort in-protocol through "
            "config_options, which no rendered run carries, so a turn would not "
            "use the requested model and could not confirm it"
        )
    return None


def availability_probe_labels(*, candidate: AcpCandidate) -> tuple[str, ...]:
    """The `KEY=VALUE` run labels one confirmation turn carries.

    The probe marker first, then the probe node's two entitlement labels in the
    same key order and through the same passability encoding
    `dispatch_run_label_pairs` uses -- so a reader cannot tell a probe's
    entitlement labels from a dispatch's, which is exactly the point: the
    succeeded-attempt reader is one reader for both.

    An identity-less candidate contributes NO entitlement pair rather than an
    invented one. `availability_probe_refusal` already refuses such a candidate
    before any run exists, so this arm is the total-function tail rather than a
    reachable route -- and a label naming an entitlement nobody declared would
    be read host-wide as a confirmation of it.
    """
    marker = f"{AVAILABILITY_PROBE_LABEL_KEY}={AVAILABILITY_PROBE_LABEL_VALUE}"
    identity = candidate.identity
    if identity is None:
        return (marker,)
    prefix = f"{NODE_LABEL_PREFIX}.{AVAILABILITY_PROBE_NODE}"
    availability = candidate_label_value(key=identity.availability_key)
    key = candidate_label_value(key=identity.candidate_key)
    return (
        marker,
        f"{prefix}.{AVAILABILITY_LABEL_SUFFIX}={availability}",
        f"{prefix}.{CANDIDATE_LABEL_SUFFIX}={key}",
    )


def is_availability_probe_run(*, labels: Mapping[str, str]) -> bool:
    """Whether one listing row's labels mark it as a confirmation turn.

    Read off the LISTING, before any per-run read is spent, which is the bound
    `_acp_factory_hold_evidence` applies to its own arms: a factory serving this
    fleet listed 1626 rows, and a probe is rare.
    """
    return labels.get(AVAILABILITY_PROBE_LABEL_KEY) == AVAILABILITY_PROBE_LABEL_VALUE


def availability_probe_graph(*, candidate: AcpCandidate, timeout_seconds: int) -> str:
    """The one-ACP-node graph whose completed turn confirms this candidate.

    `acp.command` is `render_adapter` over the candidate's OWN adapter, which is
    the one function the dispatch path renders a node's adapter through. That
    equality is the equivalence claim the clause rests on: a probe whose bytes
    differed from the dispatch's would have exercised a neighbour.

    `timeout` is the committed `dispatcher.availability_probe_timeout_seconds`,
    carried INSIDE the graph as well as bounding the launch, so the engine ends
    an unfinished turn on its own rather than leaving the bound to the client
    alone -- the clause's "including termination of unfinished probe work".
    """
    rendered = _dot_escaped(text=render_adapter(adapter=candidate.adapter))
    return (
        "digraph AcpAvailabilityProbe {\n"
        "    start [shape=Mdiamond]\n"
        f"    {AVAILABILITY_PROBE_NODE} [\n"
        '        label="Availability confirmation: one fixed minimal prompt"\n'
        '        backend="acp"\n'
        f'        acp.command="{rendered}"\n'
        f'        timeout="{timeout_seconds}s"\n'
        f'        prompt="{AVAILABILITY_PROBE_PROMPT}"\n'
        "    ]\n"
        "    exit [shape=Msquare]\n"
        f"    start -> {AVAILABILITY_PROBE_NODE} -> exit\n"
        "}\n"
    )


def _dot_escaped(*, text: str) -> str:
    """One attribute value as a DOT quoted string's contents.

    Backslashes first and quotes second, because escaping the quotes first
    would then have their new backslashes escaped in turn.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')
