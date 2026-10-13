"""The ADMISSION-REQUIRED ACP node set, and the availability wait it schedules.

Binds the v127 widening in `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority": "The admission-required set is
wider: every ACP node potentially reachable in the submitted graph is
admission-required, success-critical or not. ... If any potentially reachable
node has no eligible candidate, the item MUST remain ready without a claim or
blocked reason, and the Dispatcher MUST schedule another admission evaluation.
... The scheduled evaluation falls at the earliest expiry among the holds that
empty a chain, and otherwise after `dispatcher.credential_reprobe_interval_
seconds`" -- together with `SPECIFICATION/scenarios.md` Scenario 60's
"A chain exhausted by live holds waits until scheduled reevaluation" and
"An availability wait without a live hold remains visible and retries
automatically".

THE SHARP CONTROL IS THE CONDITIONAL NODE. Before v127 a `fix`, `review_fix` or
`disposition` outage left admission wide open, because those nodes dominate no
green path; the run then reached one of them with a held candidate and died
mid-flight. So the assertions below are deliberately written against those three
rather than against `implement`: an implementation that still graded only the
dominators passes every `implement`-shaped assertion and changes nothing.

THE SECOND CONTROL IS THAT DOMINANCE SURVIVED. Widening admission by REPLACING
the dominator derivation would satisfy the first control and silently destroy
the success-critical set the reached-node termination and the attention surfaces
read. The two sets are asserted apart, on one graph, in one test.

Everything is HERMETIC: graphs, journals and configuration are built in
`tmp_path` or inline, nothing launches an adapter and nothing reaches a
provider.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    build_acp_preflight_verdict,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_WORKFLOW_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

# The dominators of the committed graph's green terminal -- the set
# `derive_success_critical` must keep returning, unchanged by the widening.
# `fix`, `review_fix` and `disposition` are absent: a run that never goes Red
# reaches `exit` without any of them.
_COMMITTED_DOMINATORS = frozenset(
    {"dod_gate", "implement", "proof_capture", "proof_verify", "pr", "review"}
)

_NOW = "2026-10-13T12:00:00Z"
_EXPIRY = "2026-10-13T12:15:00Z"
_EARLIER_EXPIRY = "2026-10-13T12:05:00Z"
_REPROBE_SECONDS = 300
_NOW_PLUS_REPROBE = "2026-10-13T12:05:00Z"

# A graph carrying exactly the two shapes the wait derivation needs: one ACP
# node that dominates the green terminal and one that only sits on a Red path.
# Both are reachable, so both are admission-required.
_MINIMAL_GRAPH = """
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="a", timeout="60s"]
    fix [backend="acp", acp.command="b", timeout="60s"]
    gate [shape=parallelogram, timeout="60s"]
    start -> implement
    implement -> gate
    gate -> exit [label="green", condition="outcome=succeeded"]
    gate -> fix [label="red"]
    fix -> gate
"""

# Every ACP node the committed graph declares. All nine are reachable from
# `start`, so all nine are admission-required under v127.
_COMMITTED_ACP_NODES = frozenset(
    {
        "dod_gate",
        "implement",
        "fix",
        "review_fix",
        "proof_capture",
        "proof_verify",
        "pr",
        "review",
        "disposition",
    }
)


def _identity(*, availability_key: str, candidate_key: str) -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    return schema.AcpCandidateIdentity(
        display_name=f"{availability_key}/{candidate_key}",
        candidate_key=candidate_key,
        availability_key=availability_key,
    )


def _candidate(*, availability_key: str = "codex", candidate_key: str = "gpt-5-5") -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
        identity=_identity(availability_key=availability_key, candidate_key=candidate_key),
        signatures=(),
    )


def _chain(*, node: str, candidates: tuple[Any, ...]) -> Any:
    resolution = importlib.import_module(f"{_PACKAGE}._acp_chain_resolution")
    return resolution.ResolvedAcpChain(
        node=node,
        primary=candidates[0],
        fallbacks=tuple(candidates[1:]),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


def _hold(*, hold_key: str, expires_at: str = _EXPIRY, cause: str = "quota") -> Any:
    records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")
    return records.AcpAvailabilityHold(
        schema_version=1,
        observation_id=f"obs-{hold_key}",
        scope="availability-domain",
        hold_key=hold_key,
        candidate_key=None,
        cause=cause,
        occurred_at=_NOW,
        expires_at=expires_at,
    )


def _ledger(*, holds: tuple[Any, ...] = ()) -> Any:
    ledger = importlib.import_module(f"{_PACKAGE}._acp_hold_ledger")
    return ledger.AcpHoldLedger(holds=holds, unobservable=(), observation_ids=frozenset())


def _inputs(**overrides: Any) -> Any:
    preflight = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")
    return preflight.PreflightInputs(**overrides)


def _waits() -> Any:
    """The wait module, proving its file exists first.

    The existence assertion runs BEFORE the import so an unimplemented slice
    fails on a genuine assertion rather than on a `ModuleNotFoundError`, which
    proves only unimportability and says nothing about the behaviour.
    """
    module_path = _COMMANDS / "_acp_availability_wait.py"
    assert module_path.is_file(), "_acp_availability_wait.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}._acp_availability_wait")


def _minimal_verdict(*, chains: dict[str, Any], holds: tuple[Any, ...] = (), **inputs: Any) -> Any:
    """A verdict over `_MINIMAL_GRAPH`, whose ACP nodes are `implement` and `fix`."""
    return build_acp_preflight_verdict(
        chains=chains,
        graph_text=_MINIMAL_GRAPH,
        ledger=_ledger(holds=holds),
        inputs=_inputs(holds=holds, **inputs),
    )


def _single(*, node: str, availability_key: str = "codex") -> Any:
    return _chain(
        node=node,
        candidates=(_candidate(availability_key=availability_key, candidate_key=node),),
    )


def _committed_chains(*, availability_key: str = "codex") -> dict[str, Any]:
    """One single-candidate chain per ACP node of the committed graph."""
    return {
        node: _chain(
            node=node,
            candidates=(_candidate(availability_key=availability_key, candidate_key=node),),
        )
        for node in sorted(_COMMITTED_ACP_NODES)
    }


def _committed_verdict(*, holds: tuple[Any, ...] = (), **inputs: Any) -> Any:
    return build_acp_preflight_verdict(
        chains=_committed_chains(),
        graph_text=_WORKFLOW_GRAPH.read_text(encoding="utf-8"),
        ledger=_ledger(holds=holds),
        inputs=_inputs(holds=holds, **inputs),
    )


def test_every_potentially_reachable_acp_node_is_admission_required() -> None:
    """A held conditional repair or adjudication node now empties admission.

    The three nodes this asserts on -- `fix`, `review_fix` and `disposition` --
    are exactly the ones the pre-v127 dominator-only grade left out, so a
    verdict that still graded the dominators would report `viable` here while
    the run it admitted could not start `fix`'s adapter at all.
    """
    module_path = _COMMANDS / "_acp_admission_required.py"
    assert module_path.is_file(), "_acp_admission_required.py is not implemented yet"
    required = importlib.import_module(f"{_PACKAGE}._acp_admission_required")
    graph_module = importlib.import_module(f"{_PACKAGE}._acp_workflow_graph")
    graph = graph_module.parse_workflow_graph(text=_WORKFLOW_GRAPH.read_text(encoding="utf-8"))

    derived = required.derive_admission_required(graph=graph, start="start")
    verdict = _committed_verdict(holds=(_hold(hold_key="codex"),))

    assert set(derived) == _COMMITTED_ACP_NODES
    assert set(verdict.admission_required) == _COMMITTED_ACP_NODES
    assert {"fix", "review_fix", "disposition"} <= set(verdict.exhausted)
    assert verdict.viable is False


def test_the_dominator_derivation_still_returns_the_narrower_success_critical_set() -> None:
    """The widening ADDED a derivation; it did not widen the existing one.

    This is the control on the obvious wrong way to satisfy its sibling above:
    make `derive_success_critical` return the reachable set. That passes every
    admission assertion in this module and silently destroys the dominator set
    the reached-node termination and the attention surfaces read -- `fix` would
    then report as a node no green path can avoid, which is false of the graph
    and would make a held `fix` indistinguishable from a held `implement` at
    every surface that tells those two apart.

    So the two sets are asserted APART, on ONE graph, in ONE verdict: the
    dominators exactly, the reachable set exactly, and the strict-subset
    relation between them. A derivation that collapsed them in either direction
    fails at least one of the three.
    """
    graph_module = importlib.import_module(f"{_PACKAGE}._acp_workflow_graph")
    critical_module = importlib.import_module(f"{_PACKAGE}._acp_success_critical")
    graph = graph_module.parse_workflow_graph(text=_WORKFLOW_GRAPH.read_text(encoding="utf-8"))

    critical = critical_module.derive_success_critical(graph=graph)
    verdict = _committed_verdict()

    assert set(critical.nodes) == _COMMITTED_DOMINATORS
    assert critical.start == "start"
    assert critical.green_terminal == "exit"
    assert set(verdict.success_critical) == _COMMITTED_DOMINATORS
    assert _COMMITTED_DOMINATORS < _COMMITTED_ACP_NODES
    assert {"fix", "review_fix", "disposition"} == _COMMITTED_ACP_NODES - _COMMITTED_DOMINATORS


def test_the_scheduled_instant_is_the_earliest_expiry_among_the_emptying_holds() -> None:
    """Earliest, across EVERY emptied chain -- not the first one encountered.

    The two holds are deliberately ordered against the graph: `implement` is
    declared first and is held until 12:15, while `fix` is declared second and
    is held only until 12:05. A derivation that took the first exhausted node's
    own expiry would schedule 12:15 and leave the item waiting ten minutes past
    the moment it became dispatchable again -- a plausible instant, in the
    right format, that no reader could tell from the correct one.
    """
    waits = _waits()
    held = (
        _hold(hold_key="codex", expires_at=_EXPIRY),
        _hold(hold_key="anthropic", expires_at=_EARLIER_EXPIRY),
    )
    verdict = _minimal_verdict(
        chains={
            "implement": _single(node="implement", availability_key="codex"),
            "fix": _single(node="fix", availability_key="anthropic"),
        },
        holds=held,
    )

    wait = waits.schedule_availability_wait(
        verdict=verdict, now_iso=_NOW, reprobe_interval_seconds=_REPROBE_SECONDS
    )

    assert verdict.exhausted == ("implement", "fix")
    assert wait.nodes == ("implement", "fix")
    assert wait.governing_condition == waits.LIVE_HOLD_CONDITION
    assert wait.scheduled_at == _EARLIER_EXPIRY
    assert wait.hold_expiries == (_EARLIER_EXPIRY, _EXPIRY)


def test_a_healthy_fallback_nodes_own_skips_do_not_schedule_the_wait() -> None:
    """Only the holds that EMPTIED a chain decide when the item is next looked at.

    `implement` keeps an eligible fallback, so it is holding nothing back, and
    its held primary carries the EARLIER expiry; `fix` is wholly held and
    lapses later. A derivation that collected every skip in the verdict would
    schedule the wait at `implement`'s primary expiry -- an instant at which
    `fix` is still held, so the next pass refuses again and the schedule the
    record reported was never true. The ordering is deliberate: with the
    expiries the other way round the wrong derivation returns the right answer.
    """
    waits = _waits()
    held = (
        _hold(hold_key="codex", expires_at=_EARLIER_EXPIRY),
        _hold(hold_key="anthropic", expires_at=_EXPIRY),
    )
    verdict = _minimal_verdict(
        chains={
            "implement": _chain(
                node="implement",
                candidates=(
                    _candidate(availability_key="codex", candidate_key="primary"),
                    _candidate(availability_key="openrouter", candidate_key="fallback"),
                ),
            ),
            "fix": _single(node="fix", availability_key="anthropic"),
        },
        holds=held,
    )

    wait = waits.schedule_availability_wait(
        verdict=verdict, now_iso=_NOW, reprobe_interval_seconds=_REPROBE_SECONDS
    )

    assert verdict.exhausted == ("fix",)
    assert wait.nodes == ("fix",)
    assert wait.governing_condition == waits.LIVE_HOLD_CONDITION
    assert wait.scheduled_at == _EXPIRY
    assert wait.hold_expiries == (_EXPIRY,)


def test_a_chain_emptied_with_no_governing_hold_waits_the_reprobe_interval() -> None:
    """The "otherwise" arm: no hold governs, so the committed dial does.

    An ephemeral credential-probe skip mints no record and carries no expiry,
    so there is no hold instant to wait for. The record must still name a
    condition and an instant without INVENTING a hold identity or expiry --
    Scenario 60's "when no hold governs the refusal, the record names the
    outstanding confirmation, unavailable evidence source, or admission-time
    credential-probe skip without inventing a hold identity or expiry".
    """
    waits = _waits()
    candidate_preflight = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")
    verdict = _minimal_verdict(
        chains={"implement": _single(node="implement"), "fix": _single(node="fix")},
        probe=lambda _key: "exhausted",
    )

    wait = waits.schedule_availability_wait(
        verdict=verdict, now_iso=_NOW, reprobe_interval_seconds=_REPROBE_SECONDS
    )

    assert wait.governing_condition == candidate_preflight.PROBE_SKIP
    assert wait.scheduled_at == _NOW_PLUS_REPROBE
    assert wait.hold_expiries == ()


def test_a_legacy_provider_record_that_empties_a_chain_supplies_its_own_expiry() -> None:
    """A legacy record is a hold too, so its expiry schedules the wait.

    Scenario 60's "A legacy provider record remains effective during migration"
    makes the legacy blanket exhaust an admission-required chain, and its
    sibling "A chain exhausted by live holds waits until scheduled
    reevaluation" says the wait falls at "the earliest expiry among the
    covering holds" -- current or legacy. Reading only TYPED expiries would
    quietly route every legacy-governed wait onto the reprobe interval, which
    is the "otherwise" arm reached while a hold does in fact govern.
    """
    waits = _waits()
    verdict = _minimal_verdict(
        chains={"implement": _single(node="implement"), "fix": _single(node="fix")},
        legacy_provider_expiries={"codex": _EARLIER_EXPIRY},
        builtin_pairs=frozenset({("codex", "implement"), ("codex", "fix")}),
    )

    wait = waits.schedule_availability_wait(
        verdict=verdict, now_iso=_NOW, reprobe_interval_seconds=_REPROBE_SECONDS
    )

    assert verdict.exhausted == ("implement", "fix")
    assert wait.governing_condition == waits.LIVE_HOLD_CONDITION
    assert wait.scheduled_at == _EARLIER_EXPIRY
    assert wait.hold_expiries == (_EARLIER_EXPIRY,)


def test_a_viable_verdict_schedules_no_wait_at_all() -> None:
    """Nothing is waiting, so there is no instant to name.

    The positive control for the three cases above: a derivation that always
    returned a wait would satisfy every one of them while parking a healthy
    repository on a schedule nothing asked for.
    """
    waits = _waits()
    verdict = _minimal_verdict(
        chains={"implement": _single(node="implement"), "fix": _single(node="fix")}
    )

    assert verdict.viable is True
    assert (
        waits.schedule_availability_wait(
            verdict=verdict, now_iso=_NOW, reprobe_interval_seconds=_REPROBE_SECONDS
        )
        is None
    )


def test_an_unreadable_evaluation_clock_raises_rather_than_naming_an_instant() -> None:
    """A bug, raised -- never an invented instant and never `now` itself.

    The clock is the Dispatcher's own `utc_now_iso()`, so an unparseable value
    is a bug rather than an expected error. Both soft alternatives are worse
    than raising: falling back to `now` schedules an immediate retry, which is
    the busy loop the clause forbids, and omitting the instant leaves the
    refusal record without the one field an operator reads to learn when the
    item moves again.
    """
    waits = _waits()
    verdict = _minimal_verdict(
        chains={"implement": _single(node="implement"), "fix": _single(node="fix")},
        probe=lambda _key: "exhausted",
    )

    with pytest.raises(ValueError, match="not an ISO-8601 instant"):
        _ = waits.schedule_availability_wait(
            verdict=verdict, now_iso="not-an-instant", reprobe_interval_seconds=_REPROBE_SECONDS
        )


def _pass_wait() -> Any:
    """The per-pass wait resolver, proving its file exists first."""
    module_path = _COMMANDS / "_dispatcher_availability_wait.py"
    assert module_path.is_file(), "_dispatcher_availability_wait.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}._dispatcher_availability_wait")


@dataclass(kw_only=True)
class _MemoryJournal:
    """A journal that keeps every appended record, so the refusal is readable."""

    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(frozen=True, kw_only=True)
class _Accounting:
    """The claim accounting, stubbed so the rework leg has a marked row."""

    active_count: int = 0
    live_lock_active_ids: tuple[str, ...] = ()
    journal_unreadable_active_ids: tuple[str, ...] = ()
    green_terminal_active_ids: tuple[str, ...] = ()
    rework_pending_active_ids: tuple[str, ...] = ()


def _item(**overrides: object) -> Any:
    types = importlib.import_module("livespec_orchestrator_beads_fabro.types")
    fields: dict[str, object] = {
        "id": "bd-ib-item",
        "type": "task",
        "status": "ready",
        "title": "Task",
        "description": "Do it.",
        "origin": "freeform",
        "gap_id": None,
        "rank": "a1",
        "assignee": None,
        "depends_on": (),
        "captured_at": "2026-10-13T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
        "admission_policy": None,
        "acceptance_policy": None,
    }
    fields.update(overrides)
    return types.WorkItem(**fields)


def _held_conditional_verdict() -> Any:
    """A verdict whose ONLY emptied chain is the conditional repair node."""
    held = (_hold(hold_key="anthropic"),)
    return _minimal_verdict(
        chains={
            "implement": _single(node="implement", availability_key="codex"),
            "fix": _single(node="fix", availability_key="anthropic"),
        },
        holds=held,
    )


def test_the_pass_resolver_reads_the_committed_reprobe_interval(tmp_path: Path) -> None:
    """The dial comes from the repository, never from a constant in the code.

    The committed value is deliberately NOT the 300-second default: a resolver
    that returned the default would satisfy an undeclared-key fixture exactly
    as a correct one does, so only a declared non-default interval can tell
    them apart. The second half asserts the default IS still the answer when
    the key is absent, which is the arm the first half cannot reach.
    """
    pass_wait = _pass_wait()
    policy = importlib.import_module(f"{_PACKAGE}._dispatcher_policy_settings")
    declared = tmp_path / "declared"
    declared.mkdir()
    (declared / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
        '{"credential_reprobe_interval_seconds": 900}}}',
        encoding="utf-8",
    )
    undeclared = tmp_path / "undeclared"
    undeclared.mkdir()
    verdict = _minimal_verdict(
        chains={"implement": _single(node="implement"), "fix": _single(node="fix")},
        probe=lambda _key: "exhausted",
    )

    assert policy.DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS != 900
    assert (
        pass_wait.resolve_availability_wait(
            repo=declared, verdict=verdict, now_iso=_NOW, journal_path=None
        ).scheduled_at
        == "2026-10-13T12:15:00Z"
    )
    assert (
        pass_wait.resolve_availability_wait(
            repo=undeclared, verdict=verdict, now_iso=_NOW, journal_path=None
        ).scheduled_at
        == _NOW_PLUS_REPROBE
    )


def test_a_viable_pass_resolves_no_wait_and_reads_no_configuration(tmp_path: Path) -> None:
    """Nothing is waiting, so the committed dial is never even read.

    The read is skipped rather than performed and discarded, which is what
    keeps the common viable pass free of a configuration read whose answer
    cannot change anything. The unreadable fixture is the observable: a
    resolver that read first would refuse or raise on it.
    """
    pass_wait = _pass_wait()
    (tmp_path / ".livespec.jsonc").write_text("{ this is not json", encoding="utf-8")
    verdict = _minimal_verdict(
        chains={"implement": _single(node="implement"), "fix": _single(node="fix")}
    )

    assert verdict.viable is True
    assert (
        pass_wait.resolve_availability_wait(
            repo=tmp_path, verdict=verdict, now_iso=_NOW, journal_path=None
        )
        is None
    )


def test_the_containment_refusal_names_the_condition_the_node_and_the_instant() -> None:
    """The three fields Scenario 60 requires on the journaled refusal.

    "the refusal is journaled with the work-item id, governing condition,
    admission-required node lacking an eligible candidate, and scheduled
    reevaluation instant" -- and, "when present", the applicable hold
    observations and their expiries.
    """
    waits = _waits()
    composer = importlib.import_module(f"{_PACKAGE}._dispatcher_acp_preflight")
    journal = _MemoryJournal()
    verdict = _held_conditional_verdict()
    wait = waits.schedule_availability_wait(
        verdict=verdict, now_iso=_NOW, reprobe_interval_seconds=_REPROBE_SECONDS
    )

    outcome = composer.acp_preflight_refusal(
        work_item_id="bd-ib-waiting", verdict=verdict, journal=journal, wait=wait
    )

    assert outcome is not None
    [record] = [
        entry
        for entry in journal.records
        if entry.get("stage") == composer.ACP_PREFLIGHT_REFUSAL_STAGE
    ]
    assert record["work_item_id"] == "bd-ib-waiting"
    assert record["governing_condition"] == waits.LIVE_HOLD_CONDITION
    assert record["nodes"] == ["fix"]
    assert record[waits.SCHEDULED_AT_KEY] == _EXPIRY
    assert record["hold_expiries"] == [_EXPIRY]
    assert record["admission_required"] == ["implement", "fix"]
    assert record["exhausted"] == ["fix"]


def test_a_graph_shape_refusal_names_no_node_and_no_instant() -> None:
    """A fault is not a wait, so it invents neither a node nor a schedule.

    An unreadable or ambiguous graph refuses a fallback-enabled dispatch and
    its remedy is a committed change, not the passage of time. Stamping a
    scheduled instant on it would advertise a wait that nothing will ever
    retire, and naming a node would name one no measurement found.
    """
    waits = _waits()
    composer = importlib.import_module(f"{_PACKAGE}._dispatcher_acp_preflight")
    journal = _MemoryJournal()
    verdict = build_acp_preflight_verdict(
        chains={"implement": _single(node="implement")},
        graph_text="    start [shape=Mdiamond]\n",
        ledger=_ledger(),
        inputs=_inputs(),
    )

    outcome = composer.acp_preflight_refusal(
        work_item_id="bd-ib-broken-graph",
        verdict=verdict,
        journal=journal,
        wait=waits.schedule_availability_wait(
            verdict=verdict, now_iso=_NOW, reprobe_interval_seconds=_REPROBE_SECONDS
        ),
    )

    [record] = [
        entry
        for entry in journal.records
        if entry.get("stage") == composer.ACP_PREFLIGHT_REFUSAL_STAGE
    ]
    assert outcome is not None
    assert "declares no green terminal node" in str(record["detail"])
    assert waits.SCHEDULED_AT_KEY not in record
    assert "nodes" not in record
    assert "governing_condition" not in record


def test_a_waiting_item_keeps_its_ready_row_with_no_claim_and_no_blocked_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The item is untouched: no status write, no assignee, no dispatch lock.

    This is the half of the clause no journal record can establish -- "the
    item MUST remain ready without a claim or blocked reason". The observables
    are the two writes a claim consists of, so the assertions are that neither
    happened: `update_work_item_status` is never called, and the dispatch-lock
    directory the claim would create does not exist. A refusal that journaled
    all three required fields and still claimed the row would pass every other
    assertion in this module.
    """
    admission = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    eligibility = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    lock = importlib.import_module(f"{_PACKAGE}._dispatcher_dispatch_lock")
    composer = importlib.import_module(f"{_PACKAGE}._dispatcher_acp_preflight")
    waits = _waits()
    status_writes: list[dict[str, object]] = []
    monkeypatch.setattr(admission, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(
        admission, "update_work_item_status", lambda **kwargs: status_writes.append(kwargs)
    )
    monkeypatch.setattr(eligibility, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(admission, "resolve_acp_preflight", lambda **_: _held_conditional_verdict())
    journal = _MemoryJournal()

    verdict = admission.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[_item(id="bd-ib-waiting", status="ready")],
        journal=journal,
        enforce_cap=False,
    )

    assert verdict.admitted == []
    assert [outcome.work_item_id for outcome in verdict.refused] == ["bd-ib-waiting"]
    assert status_writes == []
    assert not lock.dispatch_lock_path(repo=tmp_path, work_item_id="bd-ib-waiting").exists()
    [record] = [
        entry
        for entry in journal.records
        if entry.get("stage") == composer.ACP_PREFLIGHT_REFUSAL_STAGE
    ]
    assert record["governing_condition"] == waits.LIVE_HOLD_CONDITION
    assert record["nodes"] == ["fix"]
    assert record[waits.SCHEDULED_AT_KEY] == _EXPIRY


_LONG_PAST = "2020-01-01T00:00:00Z"


def _recorded_refusal_line(*, scheduled_at: str, nodes: list[str]) -> str:
    """One prior pass's journaled containment refusal, as a JSON line."""
    waits = _waits()
    composer = importlib.import_module(f"{_PACKAGE}._dispatcher_acp_preflight")
    candidate_preflight = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")
    return json.dumps(
        {
            "at": scheduled_at,
            "stage": composer.ACP_PREFLIGHT_REFUSAL_STAGE,
            "work_item_id": "bd-ib-waiting",
            "governing_condition": candidate_preflight.PROBE_SKIP,
            "nodes": nodes,
            waits.SCHEDULED_AT_KEY: scheduled_at,
            "hold_expiries": [],
        }
    )


def _probe_emptied_verdict() -> Any:
    """A verdict whose chains are emptied by an EPHEMERAL probe refusal.

    Used wherever the freshly scheduled instant has to be in the future
    relative to the real wall clock: the reprobe arm derives its instant from
    the evaluation time, so it cannot go stale the way a fixture hold expiry
    would.
    """
    return _minimal_verdict(
        chains={"implement": _single(node="implement"), "fix": _single(node="fix")},
        probe=lambda _key: "exhausted",
    )


def test_the_scheduled_wait_is_reconstructed_from_the_journal_alone(tmp_path: Path) -> None:
    """A restarted Dispatcher reads the schedule its predecessor recorded.

    The reconstruction is proved from the JOURNAL FILE ALONE, copied into a
    directory that shares nothing else with the pass that wrote it: no process
    state, no repository, no configuration. An implementation that remembered
    the instant in memory -- the natural way to "schedule" something -- cannot
    answer in the second directory at all.

    The newest record wins, because a later pass's schedule supersedes an
    earlier one, and the journal's own order IS the chronology.
    """
    pass_wait = _pass_wait()
    first = tmp_path / "first"
    first.mkdir()
    journal = first / "journal.jsonl"
    journal.write_text(
        "\n".join(
            (
                json.dumps({"stage": "loop-pick", "picked": ["bd-ib-other"]}),
                _recorded_refusal_line(scheduled_at=_EARLIER_EXPIRY, nodes=["implement"]),
                _recorded_refusal_line(scheduled_at=_EXPIRY, nodes=["fix"]),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    restarted = tmp_path / "restarted"
    restarted.mkdir()
    _ = (restarted / "journal.jsonl").write_text(
        journal.read_text(encoding="utf-8"), encoding="utf-8"
    )

    reconstructed = pass_wait.reconstructed_availability_wait(
        journal_path=restarted / "journal.jsonl"
    )

    assert reconstructed is not None
    assert reconstructed.scheduled_at == _EXPIRY
    assert reconstructed.nodes == ("fix",)


def test_a_journal_carrying_no_recorded_schedule_reconstructs_nothing(tmp_path: Path) -> None:
    """Absence is reported as absence, never as an invented schedule.

    The two fixtures are the ones a reader could mistake for a schedule: a
    journal full of OTHER stages' records, and a record that carries the
    scheduled instant but none of the other fields a schedule needs. Reading
    the second would invent a wait out of a field that means something else on
    somebody else's line.
    """
    pass_wait = _pass_wait()
    waits = _waits()
    (tmp_path / "other-stages.jsonl").write_text(
        json.dumps({"stage": "outcome", "outcome": {"work_item_id": "bd-ib-x"}}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "half.jsonl").write_text(
        json.dumps({"stage": "acp-preflight-refusal", waits.SCHEDULED_AT_KEY: _EXPIRY}) + "\n",
        encoding="utf-8",
    )

    assert pass_wait.reconstructed_availability_wait(journal_path=None) is None
    assert pass_wait.reconstructed_availability_wait(journal_path=tmp_path / "absent.jsonl") is None
    assert (
        pass_wait.reconstructed_availability_wait(journal_path=tmp_path / "other-stages.jsonl")
        is None
    )
    assert pass_wait.reconstructed_availability_wait(journal_path=tmp_path / "half.jsonl") is None


def test_an_elapsed_instant_is_reported_as_due_and_a_live_one_is_not() -> None:
    """`elapsed` decides on the instants, and an unreadable one holds the wait.

    The unreadable arm reports NOT elapsed deliberately: "due" is the
    direction that spends work, so one malformed record must not read as a
    wait that is due on every pass forever.
    """
    waits = _waits()
    wait = waits.AvailabilityWait(
        nodes=("fix",), governing_condition=waits.LIVE_HOLD_CONDITION, scheduled_at=_EXPIRY
    )

    assert wait.elapsed(now_iso=_EXPIRY) is True
    assert wait.elapsed(now_iso="2026-10-13T12:20:00Z") is True
    assert wait.elapsed(now_iso=_NOW) is False
    assert wait.elapsed(now_iso="not-an-instant") is False
    assert (
        waits.AvailabilityWait(
            nodes=("fix",), governing_condition=waits.LIVE_HOLD_CONDITION, scheduled_at="unreadable"
        ).elapsed(now_iso=_NOW)
        is False
    )


def test_an_elapsed_schedule_is_reevaluated_once_per_pass_and_rescheduled_forward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One pass, one refusal per item, and a FRESH future instant each time.

    The seeded schedule lapsed in 2020, so it is elapsed against any real
    clock. Three observables separate "reevaluated once per loop pass" from
    the two ways of getting it wrong, and each would pass the other's
    assertions:

    - a BUSY LOOP appends more than one refusal per item in the single pass;
    - a RETRY AGAINST A DEAD DEADLINE re-reports the elapsed instant as this
      pass's schedule, rather than superseding it with a fresh one;
    - and the superseded instant is carried alongside, so the journal shows
      WHICH schedule this pass reevaluated rather than leaving a reader to
      infer it from two rows' timestamps.
    """
    admission = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    eligibility = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    composer = importlib.import_module(f"{_PACKAGE}._dispatcher_acp_preflight")
    io_module = importlib.import_module(f"{_PACKAGE}._dispatcher_io")
    waits = _waits()
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text(
        _recorded_refusal_line(scheduled_at=_LONG_PAST, nodes=["implement", "fix"]) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(admission, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(admission, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(eligibility, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(admission, "resolve_acp_preflight", lambda **_: _probe_emptied_verdict())

    verdict = admission.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[_item(id="bd-ib-waiting"), _item(id="bd-ib-also-waiting")],
        journal=io_module.JournalFile(path=journal_path),
        enforce_cap=False,
    )

    refusals = [
        record
        for record in _journal_records(path=journal_path)
        if record.get("stage") == composer.ACP_PREFLIGHT_REFUSAL_STAGE
        and record.get("superseded_scheduled_reevaluation_at") is not None
    ]
    assert verdict.admitted == []
    assert [record["work_item_id"] for record in refusals] == [
        "bd-ib-waiting",
        "bd-ib-also-waiting",
    ]
    for record in refusals:
        assert record["superseded_scheduled_reevaluation_at"] == _LONG_PAST
        assert record["reevaluation_was_due"] is True
        assert record[waits.SCHEDULED_AT_KEY] > _LONG_PAST


def test_a_first_pass_with_no_recorded_schedule_supersedes_nothing(tmp_path: Path) -> None:
    """The keys are written as nulls rather than omitted on a first pass.

    An omitted key is indistinguishable from a record written by a build that
    predates the supersession fields, so a reader could not tell "no prior
    schedule existed" from "this pass never asked". Writing them as nulls is
    what makes the first pass say so.
    """
    pass_wait = _pass_wait()

    wait = pass_wait.resolve_availability_wait(
        repo=tmp_path, verdict=_probe_emptied_verdict(), now_iso=_NOW, journal_path=None
    )

    assert wait is not None
    assert wait.superseded_at is None
    assert wait.reevaluation_was_due is False
    assert wait.record["superseded_scheduled_reevaluation_at"] is None
    assert wait.record["reevaluation_was_due"] is False


def _journal_records(*, path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _rework_pass(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    verdict: Any,
) -> tuple[Any, list[dict[str, object]]]:
    """One admission pass whose only candidate is a parked rework row.

    The row is `active` with its assignee already set and holds no live
    dispatch lock, which is exactly what the claim accounting classifies as a
    sanctioned rework park. `candidates` is empty so the row rides the rework
    leg alone, as the targeted-dispatch path drives it.
    """
    admission = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    eligibility = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    io_module = importlib.import_module(f"{_PACKAGE}._dispatcher_io")
    status_writes: list[dict[str, object]] = []
    monkeypatch.setattr(admission, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(
        admission, "update_work_item_status", lambda **kwargs: status_writes.append(kwargs)
    )
    monkeypatch.setattr(eligibility, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(
        admission,
        "claimed_active_accounting",
        lambda **_: _Accounting(rework_pending_active_ids=("bd-ib-parked",)),
    )
    monkeypatch.setattr(admission, "resolve_acp_preflight", lambda **_: verdict)
    return (
        admission.admit_and_select(
            repo=tmp_path,
            items=[_item(id="bd-ib-parked", status="active", assignee="fabro")],
            candidates=[],
            journal=io_module.JournalFile(path=tmp_path / "journal.jsonl"),
            enforce_cap=False,
        ),
        status_writes,
    )


def test_a_parked_rework_row_stays_parked_on_a_held_conditional_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rework re-dispatch reads the SAME admission-required predicate.

    "The same predicate governs rework admission, where the parked item stays
    parked without a claim." The emptied chain is the CONDITIONAL repair node,
    which is the only shape that can tell the predicates apart: under the
    pre-v127 dominator-only grade `fix` was not admission-required, so this
    parked row would have been re-dispatched straight into the outage.

    "Without a claim" is asserted as the two writes a rework claim consists
    of, both absent: no dispatch lock and no status write. The marker is left
    stamped, which is what makes the row re-selectable by a later drain rather
    than stranded.
    """
    lock = importlib.import_module(f"{_PACKAGE}._dispatcher_dispatch_lock")
    composer = importlib.import_module(f"{_PACKAGE}._dispatcher_acp_preflight")
    waits = _waits()

    admission, status_writes = _rework_pass(
        tmp_path=tmp_path, monkeypatch=monkeypatch, verdict=_held_conditional_verdict()
    )

    assert admission.rework == []
    assert admission.admitted == []
    assert [outcome.stage for outcome in admission.refused] == [
        composer.ACP_PREFLIGHT_REFUSAL_STAGE
    ]
    assert [outcome.work_item_id for outcome in admission.refused] == ["bd-ib-parked"]
    assert status_writes == []
    assert not lock.dispatch_lock_path(repo=tmp_path, work_item_id="bd-ib-parked").exists()
    [record] = [
        entry
        for entry in _journal_records(path=tmp_path / "journal.jsonl")
        if entry.get("stage") == composer.ACP_PREFLIGHT_REFUSAL_STAGE
    ]
    assert record["admission_required"] == ["implement", "fix"]
    assert record["exhausted"] == ["fix"]
    assert record["governing_condition"] == waits.LIVE_HOLD_CONDITION
    assert record[waits.SCHEDULED_AT_KEY] == _EXPIRY


def test_the_same_parked_rework_row_is_re_dispatched_under_a_viable_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive control, and it is what makes its sibling mean anything.

    Identical fixture, identical pass, one difference: nothing is held. The
    row is admitted and takes its dispatch lock. Without this, a rework leg
    that refused every marked row for any reason at all -- a broken
    accounting stub, a selection bug -- would satisfy the refusal assertions
    above while proving nothing about the admission-required predicate.
    """
    lock = importlib.import_module(f"{_PACKAGE}._dispatcher_dispatch_lock")
    rework = importlib.import_module(f"{_PACKAGE}._dispatcher_rework_admission")
    viable = _minimal_verdict(
        chains={"implement": _single(node="implement"), "fix": _single(node="fix")}
    )

    admission, status_writes = _rework_pass(
        tmp_path=tmp_path, monkeypatch=monkeypatch, verdict=viable
    )

    assert viable.viable is True
    assert [item.id for item in admission.rework] == ["bd-ib-parked"]
    assert admission.refused == []
    # The rework leg re-occupies a slot its own `active` row already holds, so
    # it writes no status -- the claim it DOES take is the dispatch lock.
    assert status_writes == []
    assert lock.dispatch_lock_path(repo=tmp_path, work_item_id="bd-ib-parked").exists()
    assert [
        entry
        for entry in _journal_records(path=tmp_path / "journal.jsonl")
        if entry.get("stage") == rework.REWORK_ADMIT_STAGE
    ] != []
