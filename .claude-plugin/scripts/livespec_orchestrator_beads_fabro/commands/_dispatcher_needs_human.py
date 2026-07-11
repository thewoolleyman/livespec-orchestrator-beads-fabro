"""Full autonomous mode — the in-band needs-human resolve-or-escalate stage (S4).

Full autonomous mode (specified in `SPECIFICATION/spec.md`,
`SPECIFICATION/contracts.md`, and `SPECIFICATION/constraints.md`;
`SPECIFICATION/scenarios.md` Scenarios 35 and 36) LLM-resolves
`blocked_reason: needs-human` items rather than surfacing them — routing a
resolved item back onto its normal path — WHILE still escalating every
truly-unresolvable decision. This module owns the DECISION SEAM and the pure
classifier for that stage; the ledger writes, the per-decision audit record,
and the bounce-to-backlog escalation are sequenced by `dispatcher.py` (the
`_resolve_or_bounce_needs_human` wiring stage), mirroring how the reflector's
lessons-proposer seam lives here and its wiring stage lives in `dispatcher.py`.

Two disjoint escalation sources exist (the truly-unresolvable set defined in
`SPECIFICATION/spec.md`): a CONFIDENCE-bounded set (the LLM cannot confidently
resolve the decision) and a DESIGN-bounded set (three decisions reserved to a
human even at high confidence — drift acceptance, a spec-change slice, or a
regroom/backlog bounce — plus a `human-only` acceptance policy).
`resolution_resolves` is the pure engine rule that folds both sources plus the
deterministic `human-only` guard into a single resolve-or-escalate verdict.

The LLM resolver is an INJECTABLE seam (`NeedsHumanResolver`): the hermetic
test tier injects the scripted `RecordingNeedsHumanResolver` so NO real model
call ever fires in a test, while production wires the real
`ClaudeNeedsHumanResolver` (kept behind the `CommandRunner` subprocess seam) —
exactly the pattern the out-of-band reflector uses for its `LessonsProposer`
seam.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    effective_acceptance_policy,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        DispatchOutcome,
    )
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "NEEDS_HUMAN_GATE",
    "ClaudeNeedsHumanResolver",
    "NeedsHumanResolution",
    "NeedsHumanResolver",
    "RecordingNeedsHumanResolver",
    "resolution_resolves",
]

# The collapsed gate name this stage records on the per-decision audit record
# (`_dispatcher_autonomous_audit`), distinct from `approve` / `acceptance`.
NEEDS_HUMAN_GATE = "needs-human"

# The one acceptance policy that is a deliberate human gate the mode never
# collapses; a needs-human block on such an item is escalated regardless of the
# resolver's confidence.
_HUMAN_ONLY_ACCEPTANCE = "human-only"

# The `claude -p` subprocess ceiling for the production resolver (a generous
# default; the seam is behind the injected CommandRunner in every test).
_CLAUDE_TIMEOUT_SECONDS = 600.0


@dataclass(frozen=True, kw_only=True)
class NeedsHumanResolution:
    """One resolver verdict on a `needs-human` block.

    `resolvable` is the LLM's confidence gate — True IFF the engine can
    confidently resolve the decision. `design_gated` marks a decision reserved
    to a human BY DESIGN (drift acceptance, a spec-change slice, or a
    regroom/backlog bounce): the engine escalates it even when `resolvable` is
    True. `decision` is the resolved action (on a resolve) or the escalation
    rationale (on an escalate), carried verbatim into the per-decision audit
    record so no disposition is silent.
    """

    resolvable: bool
    design_gated: bool
    decision: str


class NeedsHumanResolver(Protocol):
    """Seam for resolving (or declining to resolve) one `needs-human` block.

    Production wires `ClaudeNeedsHumanResolver` (a headless `claude -p` call
    kept behind the `CommandRunner` subprocess seam); the hermetic test tier
    injects `RecordingNeedsHumanResolver` so NO real model call ever fires in a
    test. The resolver only REPORTS a verdict — the engine (`dispatcher.py`)
    owns the design-gated / human-only overrides via `resolution_resolves` and
    the ledger + audit effects.
    """

    def resolve(
        self, *, item: WorkItem, outcome: DispatchOutcome, repo: Path
    ) -> NeedsHumanResolution:
        """Evaluate the block on `item` (parked as `outcome`) in `repo`."""
        ...


@dataclass(kw_only=True)
class RecordingNeedsHumanResolver:
    """Test-double `NeedsHumanResolver`: returns a scripted verdict, records calls.

    `verdict` is the fixed `NeedsHumanResolution` every `resolve` returns;
    `calls` records each `(work_item_id, outcome_detail)` so a test can assert
    the resolver was consulted (and with what) without any real model call.
    """

    verdict: NeedsHumanResolution
    calls: list[tuple[str, str]] = field(default_factory=list)

    def resolve(
        self, *, item: WorkItem, outcome: DispatchOutcome, repo: Path
    ) -> NeedsHumanResolution:
        _ = repo
        self.calls.append((item.id, outcome.detail))
        return self.verdict


@dataclass(kw_only=True)
class ClaudeNeedsHumanResolver:
    """Production `NeedsHumanResolver`: a headless `claude -p` resolve pass.

    Every model effect crosses the injected `CommandRunner` seam, so this is
    exercised in production but NEVER run in a test (the hermetic tier injects
    `RecordingNeedsHumanResolver`). The resolve pass reads the block, returns a
    strict JSON verdict, and FAIL-SAFES to an escalation on any subprocess or
    parse failure — a broken or timed-out LLM call must never be read as a
    confident resolve (never guess).
    """

    runner: CommandRunner

    def resolve(  # pragma: no cover
        self, *, item: WorkItem, outcome: DispatchOutcome, repo: Path
    ) -> NeedsHumanResolution:
        # Real `claude -p` effect; the unit tier injects the recording double,
        # so no test ever fires a model call.
        return self._resolve_impl(item=item, outcome=outcome, repo=repo)

    def _resolve_impl(  # pragma: no cover
        self, *, item: WorkItem, outcome: DispatchOutcome, repo: Path
    ) -> NeedsHumanResolution:
        prompt = _resolve_prompt(item=item, outcome=outcome)
        result = self.runner.run(
            argv=["claude", "-p", prompt],
            cwd=repo,
            timeout_seconds=_CLAUDE_TIMEOUT_SECONDS,
        )
        if result.exit_code != 0:
            return _escalate_verdict(decision="resolver subprocess failed; escalating")
        return _parse_verdict(stdout=result.stdout)


def _resolve_prompt(*, item: WorkItem, outcome: DispatchOutcome) -> str:  # pragma: no cover
    """Build the strict-JSON resolve prompt for the production resolver."""
    return (
        "You are the full-autonomous-mode needs-human resolver. A dispatched "
        f"work-item parked at an in-loop human gate.\n\nWork-item: {item.id}\n"
        f"Title: {item.title}\nBlock detail: {outcome.detail}\n\n"
        "Decide whether the block is CONFIDENTLY resolvable without a human, "
        "and whether it is a decision reserved to a human by design (drift "
        "acceptance, a spec-change slice, or a regroom/backlog bounce). Reply "
        'with ONLY a JSON object: {"resolvable": bool, "design_gated": bool, '
        '"decision": string}.'
    )


def _parse_verdict(*, stdout: str) -> NeedsHumanResolution:  # pragma: no cover
    """Parse the resolver's strict-JSON reply, fail-safing to an escalation."""
    try:
        parsed: object = json.loads(stdout)
    except json.JSONDecodeError:
        return _escalate_verdict(decision="resolver reply was not JSON; escalating")
    if not isinstance(parsed, dict):
        return _escalate_verdict(decision="resolver reply was not an object; escalating")
    record = {str(key): value for key, value in cast("dict[object, object]", parsed).items()}
    resolvable = record.get("resolvable")
    design_gated = record.get("design_gated")
    decision = record.get("decision")
    if (
        isinstance(resolvable, bool)
        and isinstance(design_gated, bool)
        and isinstance(decision, str)
    ):
        return NeedsHumanResolution(
            resolvable=resolvable, design_gated=design_gated, decision=decision
        )
    return _escalate_verdict(decision="resolver reply was malformed; escalating")


def _escalate_verdict(*, decision: str) -> NeedsHumanResolution:  # pragma: no cover
    """A fail-safe escalation verdict (never a confident resolve)."""
    return NeedsHumanResolution(resolvable=False, design_gated=False, decision=decision)


def resolution_resolves(*, item: WorkItem, resolution: NeedsHumanResolution) -> bool:
    """Decide whether an armed `needs-human` block is auto-resolved or escalated.

    The engine auto-resolves ONLY when the LLM can confidently resolve the
    decision AND the decision is not reserved to a human. It escalates when:

    - `resolution.resolvable` is False — the CONFIDENCE-bounded truly-
      unresolvable set (the LLM cannot confidently resolve it);
    - `resolution.design_gated` is True — a DESIGN-bounded decision (drift
      acceptance, a spec-change slice, or a regroom/backlog bounce) reserved to
      a human even at high confidence;
    - the item's effective acceptance policy is `human-only` — a deliberate
      human gate the mode never collapses.

    Pure; no I/O. `True` means resolve-and-route-back; `False` means
    escalate-and-surface.
    """
    if not resolution.resolvable:
        return False
    if resolution.design_gated:
        return False
    return effective_acceptance_policy(item=item) != _HUMAN_ONLY_ACCEPTANCE
