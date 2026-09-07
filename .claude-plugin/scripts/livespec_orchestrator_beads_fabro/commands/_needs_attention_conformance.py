"""Producer-side envelope conformance for the needs-attention composition.

The needs-attention machine-envelope contract in `SPECIFICATION/contracts.md`
binds this producer twice over: it MUST NOT emit an item that fails the runtime
validator, and it MUST NOT silently omit a candidate that failed validation — a
composition-time validation failure MUST surface as a visible failure alongside
the valid items. The second half is the load-bearing one: absence of an
attention item reads as RESOLUTION downstream, so a validation failure that
merely shortened the list would manufacture an all-clear.

Since livespec-runtime v0.22.0 the validator runs at CONSTRUCTION:
`AttentionItem.__post_init__` raises `InvalidAttentionItemIdError` rather than
letting an invalid value exist, and the shared normalizer
`livespec_runtime.needs_attention.compose_needs_attention` no longer filters. A
refusal is therefore no longer a silent omission — it is an exception that would
take the WHOLE envelope down, which is loud but useless. The ownership cut puts
that validator (and the normalizer over injected facts) in `livespec-runtime`,
whose vendored tree is read-only here, so the loud half lives on this side of the
cut instead, as an exception boundary around each candidate.

There are two such boundaries, one per composition route:

- `ConformanceContext.candidate` wraps the construction of a candidate this
  repository composes DIRECTLY, so a refused id costs that one candidate and
  never its valid siblings;
- `composed_conformant` routes each injected primitive through the runtime
  normalizer ON ITS OWN, so a refusal names exactly which candidate the
  validator rejected. Routing one primitive at a time is what keeps the runtime
  the single authority on both id FORMATION and validity: this module never
  formats a candidate id itself, so it cannot drift from the grammar it is
  checking against.

Either way the rejection is re-emitted as a visible failure item.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from livespec_runtime.attention_item import (
    AttentionItem,
    AttentionKind,
    AttentionUrgency,
    Handoff,
    InvalidAttentionItemIdError,
    SourceRef,
)
from livespec_runtime.needs_attention import (
    ImplNextOutput,
    PlanThreadOutput,
    SpecNextOutput,
    WorkItemHumanValveLane,
    compose_needs_attention,
)

__all__: list[str] = [
    "ConformanceContext",
    "composed_conformant",
    "conformant_lane",
]

# The failure item is itself an envelope item, so it must clear the very
# validator that rejected the candidate it reports — otherwise the loud half
# would be silently dropped by the same mechanism it exists to expose. The
# runtime grammar accepts `hygiene:<type>:<resource>` when both trailing
# components are non-empty and non-decimal, so the rejected candidate's own key
# is carried behind a fixed literal prefix: that makes the resource component
# unconditionally well-formed no matter how degenerate the rejected key was,
# while still naming it verbatim for the operator.
_FAILURE_TYPE = "attention-invalid"
_FAILURE_KEY_PREFIX = "candidate-"


@dataclass(frozen=True, slots=True, kw_only=True)
class ConformanceContext:
    """The repo identity every conformance decision is reported against."""

    project_root: Path
    repo: str

    def candidate(
        self,
        *,
        id: str,
        kind: AttentionKind,
        urgency: AttentionUrgency,
        summary: str,
        source_ref: SourceRef,
        handoff: Handoff,
    ) -> AttentionItem:
        """Build one directly-composed candidate, surfacing a refusal loudly.

        The lanes this repository composes as `AttentionItem` values directly
        never pass through the runtime normalizer, so this constructor is where
        the runtime validator meets them at all. A refused candidate is replaced
        by a visible failure item rather than dropped OR allowed to abort the
        pass, so the count of things needing attention never falls silently and
        one bad id never costs its valid siblings.

        `id` shadows the builtin deliberately: the parameter names mirror
        `AttentionItem`'s own fields one-for-one, so a call site reads as the
        construction it replaces.
        """
        try:
            return AttentionItem(
                id=id,
                kind=kind,
                urgency=urgency,
                summary=summary,
                source_ref=source_ref,
                handoff=handoff,
            )
        except InvalidAttentionItemIdError as refused:
            return _failure_item(
                context=self,
                subject=f"{kind} candidate with stable id {refused.id!r}",
                key=refused.id,
            )


def composed_conformant(
    *,
    context: ConformanceContext,
    spec_next: SpecNextOutput | None,
    impl_next: ImplNextOutput | None,
    human_valve_lanes: Sequence[WorkItemHumanValveLane],
    plan_threads: Sequence[PlanThreadOutput],
) -> list[AttentionItem]:
    """Normalize each injected primitive alone, surfacing every rejection.

    Equivalent to one `compose_needs_attention` call over all the primitives,
    except that a candidate the runtime validator rejects leaves a visible
    failure item behind instead of leaving nothing behind.
    """
    attention: list[AttentionItem] = []
    for lane in human_valve_lanes:
        attention.extend(
            conformant_lane(
                context=context,
                subject=f"human-valve lane {lane.verb} for work-item {lane.work_item}",
                key=f"{lane.verb}-{lane.work_item}",
                compose=partial(
                    compose_needs_attention, repo=context.repo, human_valve_lanes=(lane,)
                ),
            )
        )
    if impl_next is not None:
        attention.extend(
            conformant_lane(
                context=context,
                subject=f"impl-next candidate for work-item {impl_next.work_item}",
                key=impl_next.work_item,
                compose=partial(compose_needs_attention, repo=context.repo, impl_next=impl_next),
            )
        )
    if spec_next is not None:
        attention.extend(
            conformant_lane(
                context=context,
                subject=f"spec-next candidate {spec_next.op} on {spec_next.spec_target}",
                key=f"{spec_next.op}-{spec_next.spec_target}",
                compose=partial(compose_needs_attention, repo=context.repo, spec_next=spec_next),
            )
        )
    for thread in plan_threads:
        attention.extend(
            conformant_lane(
                context=context,
                subject=f"plan thread {thread.topic}",
                key=thread.topic,
                compose=partial(compose_needs_attention, repo=context.repo, plan_threads=(thread,)),
            )
        )
    return attention


def conformant_lane(
    *,
    context: ConformanceContext,
    subject: str,
    key: str,
    compose: Callable[[], list[AttentionItem]],
) -> list[AttentionItem]:
    """Compose one lane, replacing a validator refusal with a loud failure.

    The boundary for a lane whose items are BUILT ELSEWHERE — by the runtime
    normalizer over an injected primitive, or by the runtime's own hygiene
    scan. Granularity is the lane rather than the candidate because the
    construction happens inside that call, so `composed_conformant` routes one
    primitive at a time to keep the lane and the candidate the same thing.
    """
    try:
        composed = compose()
    except InvalidAttentionItemIdError:
        return [_failure_item(context=context, subject=subject, key=key)]
    return composed


def _failure_item(*, context: ConformanceContext, subject: str, key: str) -> AttentionItem:
    return AttentionItem(
        id=f"hygiene:{_FAILURE_TYPE}:{_FAILURE_KEY_PREFIX}{key}",
        kind="hygiene",
        urgency="high",
        summary=(
            f"Attention candidate rejected by the runtime validator: {subject}. "
            "It is absent from the envelope because composition failed validation, "
            "never because the underlying fact resolved."
        ),
        source_ref=SourceRef(repo=context.repo),
        handoff=Handoff(
            kind="shell",
            command=_failure_command(context=context, subject=subject),
        ),
    )


def _failure_command(*, context: ConformanceContext, subject: str) -> str:
    prompt = (
        f"inspect-attention-validation-failure in repository {context.project_root}. "
        f"The rejected composition candidate is: {subject}. Repair the derivation so "
        "the candidate carries a stable id the runtime validator accepts; never "
        "resolve it by dropping the candidate."
    )
    return (
        f"cd {shlex.quote(str(context.project_root))} && "
        f"codex exec {shlex.quote(prompt)} < /dev/null"
    )
