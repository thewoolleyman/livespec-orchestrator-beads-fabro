"""WHEN the Dispatcher looks again after an admission-required chain emptied.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "If any potentially reachable node has no eligible candidate, the
item MUST remain ready without a claim or blocked reason, and the Dispatcher
MUST schedule another admission evaluation. ... The scheduled evaluation falls
at the earliest expiry among the holds that empty a chain, and otherwise after
`dispatcher.credential_reprobe_interval_seconds`; no human valve is the remedy
for that wait."

THE TWO ARMS ARE ASSERTED AGAINST EACH OTHER, AND THAT PAIRING IS THE CONTROL.
Each arm alone is satisfiable by an implementation that always takes it: one
that always scheduled `now + interval` would pass every interval case while
ignoring every hold expiry it was handed, and one that always reached for an
expiry would schedule nothing for the ephemeral skips -- which are the skips a
probe and a headroom reading produce, and which carry no expiry by
construction because the clause forbids them an invented one. So the hold arm
is asserted with an interval that would give a DIFFERENT answer, and the
interval arm with an emptied node no hold governs.

THE EARLIEST EXPIRY IS ASSERTED ACROSS BOTH AXES A CHAIN CAN EMPTY ALONG --
several holds on one node, and several emptied nodes -- because "earliest"
read off the first node in graph order, or off the first hold in ledger order,
is the same wrong answer arrived at two ways, and a fixture ordered
newest-first is the only one that can tell either apart from a real minimum.

THE EVIDENCE IS HANDED IN RATHER THAN REACHED FOR, which is what keeps this
derivation pure and keeps it honest about ONE evaluation: the holds and the
verdict come from a single ledger read, so a record retiring between two reads
cannot be surfaced by one half and acted on by the other.

NOTHING HERE INVENTS A HOLD. The ephemeral arms are asserted to name their own
governing condition and to report NO hold observation, because the clause says
a refusal with no governing hold "MUST NOT invent a hold identity or expiry" --
and an implementation that filled those fields from the interval arm's own
instant would read, at the journal, exactly like an observed provider outage.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_acp_availability_wait.py"
)

_NOW = "2026-10-15T12:00:00Z"
_INTERVAL = 300
# `_NOW` plus `_INTERVAL`, spelled out rather than computed, so the expected
# value cannot be produced by the same arithmetic the implementation uses.
_NOW_PLUS_INTERVAL = "2026-10-15T12:05:00Z"

_EARLIEST = "2026-10-15T12:01:00Z"
_LATER = "2026-10-15T12:40:00Z"
_LATEST = "2026-10-15T18:00:00Z"

_DOMAIN = "availability-domain"


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _wait_module() -> Any:
    return _module(name="_acp_availability_wait")


def _hold(*, expires_at: str, observation_id: str, hold_key: str = "codex") -> Any:
    records = _module(name="_acp_hold_records")
    return records.AcpAvailabilityHold(
        schema_version=1,
        observation_id=observation_id,
        scope=_DOMAIN,
        hold_key=hold_key,
        candidate_key=None,
        cause="quota",
        occurred_at=_NOW,
        expires_at=expires_at,
    )


def _hold_skip(*, hold_key: str = "codex") -> Any:
    """One skip a DURABLE typed hold decided, as the filter records it."""
    preflight = _module(name="_acp_candidate_preflight")
    return preflight.SkippedCandidate(
        availability_key=hold_key,
        candidate_key="only",
        reason=preflight.TYPED_HOLD_SKIP,
        cause="quota",
        scope=_DOMAIN,
        hold_key=hold_key,
    )


def _ephemeral_skip(*, reason: str) -> Any:
    preflight = _module(name="_acp_candidate_preflight")
    return preflight.SkippedCandidate(
        availability_key="anthropic",
        candidate_key="only",
        reason=reason,
        condition="exhausted" if reason == preflight.PROBE_SKIP else None,
    )


def _node(*, node: str, skipped: tuple[Any, ...]) -> Any:
    preflight = _module(name="_acp_candidate_preflight")
    return preflight.NodePreflight(node=node, enabled=True, candidates=(), skipped=skipped)


def _viable_node(*, node: str) -> Any:
    preflight = _module(name="_acp_candidate_preflight")
    schema = _module(name="_acp_candidate_schema")
    adapters = _module(name="_acp_node_adapters")
    candidate = schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
        identity=None,
        signatures=(),
    )
    return preflight.NodePreflight(node=node, enabled=True, candidates=(candidate,), skipped=())


def _verdict(
    *,
    nodes: tuple[Any, ...],
    exhausted: tuple[str, ...],
    unobservable: tuple[Any, ...] = (),
    refusal: str | None = None,
) -> Any:
    return _module(name="_acp_preflight_verdict").AcpPreflightVerdict(
        fallback_enabled=True,
        nodes=nodes,
        success_critical=("implement",),
        admission_required=tuple(exhausted),
        exhausted=exhausted,
        unobservable=unobservable,
        refusal=refusal,
    )


def _wait(
    *,
    verdict: Any,
    holds: tuple[Any, ...] = (),
    now_iso: str = _NOW,
    interval: int = _INTERVAL,
) -> Any:
    return _wait_module().availability_wait(
        verdict=verdict,
        holds=holds,
        now_iso=now_iso,
        reprobe_interval_seconds=interval,
    )


def test_the_module_is_its_own_cohesive_pure_file() -> None:
    """The derivation is PURE and reaches for no I/O seam of any kind."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH.name} does not exist yet"
    source = _MODULE_PATH.read_text(encoding="utf-8")

    for forbidden in ("subprocess", "socket", "urllib", "httpx", "requests", "open("):
        assert forbidden not in source, f"the pure wait derivation reaches for {forbidden}"


def test_a_governing_hold_schedules_its_own_expiry_not_the_interval() -> None:
    """The hold arm, asserted against an interval that answers differently."""
    verdict = _verdict(nodes=(_node(node="fix", skipped=(_hold_skip(),)),), exhausted=("fix",))

    wait = _wait(verdict=verdict, holds=(_hold(expires_at=_LATER, observation_id="obs-a"),))

    assert wait is not None
    assert wait.reevaluate_at == _LATER
    # The control: the interval arm's own answer, which this case must NOT take.
    assert wait.reevaluate_at != _NOW_PLUS_INTERVAL
    assert wait.node == "fix"
    assert wait.governing_condition == _module(name="_acp_candidate_preflight").TYPED_HOLD_SKIP
    assert [hold.observation_id for hold in wait.holds] == ["obs-a"]


def test_the_earliest_expiry_wins_across_the_holds_on_one_node() -> None:
    """ "The earliest expiry among the holds that empty a chain."

    Ordered newest-first, so a derivation reading the first hold rather than
    taking a minimum reports `_LATEST` and fails here.
    """
    verdict = _verdict(
        nodes=(
            _node(
                node="fix",
                skipped=(_hold_skip(hold_key="codex"), _hold_skip(hold_key="claude")),
            ),
        ),
        exhausted=("fix",),
    )

    wait = _wait(
        verdict=verdict,
        holds=(
            _hold(expires_at=_LATEST, observation_id="obs-late", hold_key="codex"),
            _hold(expires_at=_EARLIEST, observation_id="obs-early", hold_key="claude"),
        ),
    )

    assert wait is not None
    assert wait.reevaluate_at == _EARLIEST
    assert {hold.observation_id for hold in wait.holds} == {"obs-late", "obs-early"}
    assert {hold.expires_at for hold in wait.holds} == {_LATEST, _EARLIEST}


def test_the_earliest_expiry_wins_across_several_emptied_nodes() -> None:
    """The other axis: a derivation keyed on the first emptied node fails here.

    `fix` precedes `disposition` in the exhausted tuple and is held by the
    LATER record, so reporting the first node's own expiry reports `_LATEST`.
    """
    verdict = _verdict(
        nodes=(
            _node(node="fix", skipped=(_hold_skip(hold_key="codex"),)),
            _node(node="disposition", skipped=(_hold_skip(hold_key="claude"),)),
        ),
        exhausted=("fix", "disposition"),
    )

    wait = _wait(
        verdict=verdict,
        holds=(
            _hold(expires_at=_LATEST, observation_id="obs-fix", hold_key="codex"),
            _hold(expires_at=_EARLIEST, observation_id="obs-disposition", hold_key="claude"),
        ),
    )

    assert wait is not None
    assert wait.reevaluate_at == _EARLIEST
    # The NAMED node stays the first in graph order; only the instant is a
    # minimum. The two facts answer different questions and must not be fused.
    assert wait.node == "fix"
    assert wait.nodes == ("fix", "disposition")


def test_a_hold_governing_no_emptied_chain_does_not_set_the_instant() -> None:
    """ "The holds that empty a chain" -- not every live hold on the ledger.

    The emptied node is held by `codex`; the EARLIER record belongs to a
    `claude` domain that skipped nothing here. A derivation taking the minimum
    over the whole ledger reports `_EARLIEST` and fails.
    """
    verdict = _verdict(
        nodes=(_node(node="fix", skipped=(_hold_skip(hold_key="codex"),)),), exhausted=("fix",)
    )

    wait = _wait(
        verdict=verdict,
        holds=(
            _hold(expires_at=_EARLIEST, observation_id="obs-elsewhere", hold_key="claude"),
            _hold(expires_at=_LATER, observation_id="obs-fix", hold_key="codex"),
        ),
    )

    assert wait is not None
    assert wait.reevaluate_at == _LATER
    assert [hold.observation_id for hold in wait.holds] == ["obs-fix"]


@pytest.mark.parametrize("reason_name", ["PROBE_SKIP", "HEADROOM_SKIP", "LEGACY_HOLD_SKIP"])
def test_a_skip_carrying_no_expiry_schedules_the_reprobe_interval(reason_name: str) -> None:
    """ "And otherwise after `dispatcher.credential_reprobe_interval_seconds`."

    All three empty a chain while carrying no bounded expiry: the two ephemeral
    skips because the clause gives them none, and the legacy record because it
    is read as a vendor name rather than as a versioned observation.
    """
    preflight = _module(name="_acp_candidate_preflight")
    reason = getattr(preflight, reason_name)
    verdict = _verdict(
        nodes=(_node(node="implement", skipped=(_ephemeral_skip(reason=reason),)),),
        exhausted=("implement",),
    )

    wait = _wait(verdict=verdict)

    assert wait is not None
    assert wait.reevaluate_at == _NOW_PLUS_INTERVAL
    assert wait.governing_condition == reason
    # "It MUST NOT invent a hold identity or expiry."
    assert wait.holds == ()


def test_a_typed_hold_governs_over_an_ephemeral_skip_on_the_same_node() -> None:
    """Precedence, and the expiry that comes with it.

    A chain emptied partly by an observed outage and partly by a local skip is
    governed by the outage: that is the fact carrying a bounded expiry, and the
    one an operator can clear.
    """
    preflight = _module(name="_acp_candidate_preflight")
    verdict = _verdict(
        nodes=(
            _node(
                node="review",
                skipped=(_ephemeral_skip(reason=preflight.HEADROOM_SKIP), _hold_skip()),
            ),
        ),
        exhausted=("review",),
    )

    wait = _wait(verdict=verdict, holds=(_hold(expires_at=_LATER, observation_id="obs-a"),))

    assert wait is not None
    assert wait.governing_condition == preflight.TYPED_HOLD_SKIP
    assert wait.reevaluate_at == _LATER


def test_unreadable_availability_evidence_names_itself_and_invents_no_hold() -> None:
    """ "It MUST name the outstanding confirmation, unavailable evidence source."""
    verdict = _verdict(
        nodes=(_node(node="implement", skipped=()),),
        exhausted=("implement",),
        unobservable=({"stage": "acp-availability-observed", "schema_version": 9},),
    )

    wait = _wait(verdict=verdict)

    assert wait is not None
    assert wait.governing_condition == _wait_module().UNAVAILABLE_EVIDENCE
    assert wait.reevaluate_at == _NOW_PLUS_INTERVAL
    assert wait.holds == ()
    assert wait.unobservable_observations == 1


def test_a_typed_skip_whose_hold_has_since_retired_falls_back_to_the_interval() -> None:
    """A skip naming a record the handed-in evidence no longer carries.

    The skip is typed, so a derivation that trusted the skip's own words would
    report a hold identity it cannot substantiate. There is no expiry to read,
    so the cadence governs -- and no hold is named.
    """
    verdict = _verdict(nodes=(_node(node="fix", skipped=(_hold_skip(),)),), exhausted=("fix",))

    wait = _wait(verdict=verdict, holds=())

    assert wait is not None
    assert wait.reevaluate_at == _NOW_PLUS_INTERVAL
    assert wait.holds == ()


def test_a_viable_verdict_schedules_no_wait() -> None:
    """No chain is empty, so there is nothing to look again for."""
    verdict = _verdict(nodes=(_viable_node(node="implement"),), exhausted=())

    assert verdict.viable is True
    assert _wait(verdict=verdict) is None


def test_a_configuration_refusal_schedules_no_availability_wait() -> None:
    """An unreadable graph is a configuration refusal, not an availability wait.

    It names no admission-required node and no observation, and waiting cannot
    repair it -- so manufacturing an instant here would report a committed
    configuration fault as a provider outage that expires on its own.
    """
    verdict = _verdict(nodes=(), exhausted=(), refusal="workflow graph is unsupported")

    assert verdict.viable is False
    assert _wait(verdict=verdict) is None


def test_an_unreadable_hold_expiry_falls_back_to_the_interval() -> None:
    """A clock nobody can read schedules the cadence, never a passed instant.

    Adopting the unreadable text verbatim would write a `reevaluate_at` no
    comparison can order, and every later pass would read it as already due --
    the busy loop this wait exists to bound.
    """
    verdict = _verdict(nodes=(_node(node="fix", skipped=(_hold_skip(),)),), exhausted=("fix",))

    wait = _wait(
        verdict=verdict, holds=(_hold(expires_at="not-an-instant", observation_id="obs-a"),)
    )

    assert wait is not None
    assert wait.reevaluate_at == _NOW_PLUS_INTERVAL


def test_an_unreadable_evaluation_clock_schedules_no_wait() -> None:
    """Fail closed: an instant derived from an unreadable clock claims nothing."""
    preflight = _module(name="_acp_candidate_preflight")
    verdict = _verdict(
        nodes=(_node(node="implement", skipped=(_ephemeral_skip(reason=preflight.PROBE_SKIP),)),),
        exhausted=("implement",),
    )

    assert _wait(verdict=verdict, now_iso="not-an-instant") is None
