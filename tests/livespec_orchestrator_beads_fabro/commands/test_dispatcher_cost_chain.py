"""The per-attempt cost reaches the EXISTING gate, and keeps its existing posture.

Binds the posture clause of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" -> "Cost follows every attempt in
a successful fallback run": "section "Fail-closed cost gate (keyed on `--item`
presence)" remains authoritative. ... Terminally unsuccessful runs retain the
existing no-cost-observation/no-gate posture."

THE WHOLE POINT IS THAT NO NEW GATE IS BUILT. An unpriceable chain has to arrive
at the gate as an ABSENT derived cost, so the fail-closed branch that has
existed since work-item 5v9 handles it unchanged -- unattended drain refuses, a
hand-picked `--item` dispatch warns. A second refusal path reading the chain
directly would be a second policy to keep in step with the first, and the two
would diverge silently because both produce a well-formed verdict.

THE DANGEROUS WRONG ANSWER HERE IS THE SINK'S OWN NUMBER, not zero. The sink
accrues a DEFAULT-PRICED micro-USD per span, so a run whose attempts were
unpriceable still has a plausible total sitting in the sink file. An
implementation that read the chain for the report but left the gate on the sink
would refuse nothing and report nothing wrong, while the number it gated on was
priced at a model no attempt ran. So the assertions below check the gate's own
journal record, not just the report.

EVERY ORDINARY DISPATCH MUST STAY ON THE LEGACY PATH, which is the control that
keeps "a single-candidate run is priced exactly as before this change" true in
the wiring as well as in the arithmetic. A repository with no resolvable
factory, a run with no id, a stream with no `agent.acp.started` records: each
yields NO chain cost, and the sink's own aggregate decides as it always has.
"""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_gate import (
    cost_gate_after_verdict,
    derived_costs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import CostSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import cost_sink_path

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "_dispatcher_cost_chain"
_MODULE_PATH = _COMMANDS / f"{_MODULE}.py"

_BASE = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
_BASE_MS = int(_BASE.timestamp() * 1000)
_WORK_ITEM = "bd-ib-tmgt7v"
_RUN_ID = "01M3WTPHJ0Y9TA263R3A4YCQN1"
_FACTORY = FactoryTarget(name="hp", server="https://factory.example:32276", dev_token=None)

# The implementer default, priced in the committed catalog, and a model nothing
# prices. The second is what darkens a run.
_PRICED_MODEL = "claude-opus-5"
_UNPRICED_MODEL = "some-unmeasured-model"


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _ScriptedRunner:
    """A runner answering `fabro events` from a fixture and `fabro ps` from another."""

    events_stdout: str = "[]"
    events_exit_code: int = 0
    ps_stdout: str = "[]"
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        del cwd, timeout_seconds
        self.calls.append(argv)
        if "events" in argv:
            return CommandResult(
                exit_code=self.events_exit_code, stdout=self.events_stdout, stderr=""
            )
        return CommandResult(exit_code=0, stdout=self.ps_stdout, stderr="")


@dataclass(kw_only=True)
class _RecordingPoster:
    calls: list[dict[str, object]] = field(default_factory=list)

    def post(self, *, url: str, body: str, title: str, timeout_seconds: float) -> bool:
        del url, title, timeout_seconds
        self.calls.append({"body": body})
        return True


def _chain_module() -> Any:
    """The composition module, through an in-body import.

    In-body rather than at module top so this file's FIRST failing assertion
    is a genuine check on the committed file rather than a collection error.
    """
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    return importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{_MODULE}")


def run_chain_cost(
    *,
    repo: Path,
    work_item_id: str,
    run_id: str,
    sink: CostSink,
    factory: FactoryTarget,
    runner: Any,
) -> Any:
    return _chain_module().run_chain_cost(
        repo=repo,
        work_item_id=work_item_id,
        run_id=run_id,
        sink=sink,
        factory=factory,
        runner=runner,
    )


def chain_costs(
    *,
    repo: Path,
    outcomes: tuple[DispatchOutcome, ...],
    sink: CostSink,
    runner: Any,
    factory_of: Callable[..., FactoryTarget | None] | None = None,
) -> dict[str, Any]:
    extra = {} if factory_of is None else {"factory_of": factory_of}
    return _chain_module().chain_costs(
        repo=repo, outcomes=outcomes, sink=sink, runner=runner, **extra
    )


def _instant(*, offset_ms: int) -> str:
    return (_BASE + timedelta(milliseconds=offset_ms)).isoformat().replace("+00:00", "Z")


def _identity(*, index: int, key: str) -> dict[str, Any]:
    return {
        "candidate_index": index,
        "display_name": f"display {key}",
        "candidate_key": key,
        "availability_key": "codex",
    }


def _start(*, index: int, offset_ms: int) -> dict[str, Any]:
    return {
        "type": "agent.acp.started",
        "node": "implement",
        "node_visit": 1,
        "candidate_index": index,
        "occurred_at": _instant(offset_ms=offset_ms),
        "primary_generation": "gen-a",
    }


def _chain_events() -> str:
    """A node visit whose primary failed at 120s and whose fallback then won."""
    return json.dumps(
        [
            _start(index=0, offset_ms=0),
            {
                "type": "agent.acp.failover",
                "schema_version": 1,
                "event_id": "ev-1",
                "occurred_at": _instant(offset_ms=120_000),
                "node": "implement",
                "node_visit": 1,
                "engine_attempt": 1,
                "from": _identity(index=0, key=_PRICED_MODEL),
                "to": _identity(index=1, key=_UNPRICED_MODEL),
                "hold_key": "codex",
                "cause": "quota",
                "scope": "availability-domain",
                "primary_generation": "gen-a",
                "full_chain": "chain-1",
                "attempted_durations_ms": [120_000],
            },
            _start(index=1, offset_ms=125_000),
        ]
    )


def _attr(*, key: str, string_value: str | None = None, int_value: int | None = None) -> Any:
    if int_value is not None:
        return {"key": key, "value": {"intValue": str(int_value)}}
    return {"key": key, "value": {"stringValue": "" if string_value is None else string_value}}


def _cc_span(*, request_id: str, model: str, started_at_ms: int) -> dict[str, object]:
    return {
        "name": "claude_code.llm_request",
        "spanId": f"span-{request_id}",
        "startTimeUnixNano": str(started_at_ms * 1_000_000),
        "attributes": [
            _attr(key="model", string_value=model),
            _attr(key="input_tokens", int_value=1_000_000),
            _attr(key="output_tokens", int_value=0),
            _attr(key="cache_creation_tokens", int_value=0),
            _attr(key="cache_read_tokens", int_value=0),
            _attr(key="work.item.id", string_value=_WORK_ITEM),
            _attr(key="request_id", string_value=request_id),
            _attr(key="node_id", string_value="implement"),
        ],
    }


def _args(*, journal_path: Path, items: list[str] | None = None) -> argparse.Namespace:
    return argparse.Namespace(items=items, fabro_bin="fabro", journal=str(journal_path))


def _green(*, work_item_id: str = _WORK_ITEM, run_id: str | None = _RUN_ID) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="green",
        stage="done",
        pr_number=7,
        merge_sha="abc123",
        detail="merged",
        fabro_run_id=run_id,
    )


def _failed(*, work_item_id: str = _WORK_ITEM) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="the run never converged",
        fabro_run_id=_RUN_ID,
    )


def _ps_null() -> str:
    """A null-cost `fabro ps` record (the dark fabro reality the gate fires on)."""
    return json.dumps(
        [
            {
                "run_id": _RUN_ID,
                "status": {"kind": "succeeded"},
                "goal": f"Work-item: {_WORK_ITEM}\nRepo: /x",
                "total_usd_micros": None,
            }
        ]
    )


def _seed_sink(*, args: argparse.Namespace, repo: Path, models: tuple[str, ...]) -> CostSink:
    """Accrue one 1M-input-token call per model, inside the matching window."""
    sink = CostSink(path=cost_sink_path(args=args, repo=repo))
    offsets = (10_000, 130_000)
    for index, model in enumerate(models):
        sink.accumulate_span(
            span=_cc_span(
                request_id=f"req-{index}",
                model=model,
                started_at_ms=_BASE_MS + offsets[index],
            )
        )
    return sink


def test_a_priceable_chain_sums_every_attempt_through_the_run_cost(tmp_path: Path) -> None:
    """Both attempts priced from committed bytes: 1M input each at opus-5 rates.

    5.00 USD per million input, twice, is 10_000_000 micro-USD. The single
    number proves the composition end to end: events read, windows built,
    observations attributed, catalog consulted, attempts summed.
    """
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = _seed_sink(args=args, repo=tmp_path, models=(_PRICED_MODEL, _PRICED_MODEL))

    cost = run_chain_cost(
        repo=tmp_path,
        work_item_id=_WORK_ITEM,
        run_id=_RUN_ID,
        sink=sink,
        factory=_FACTORY,
        runner=_ScriptedRunner(events_stdout=_chain_events()),
    )

    assert cost is not None
    assert cost.usd_micros == 10_000_000
    assert len(cost.attempts) == 2


def test_an_unpriceable_fallback_darkens_the_whole_run_cost(tmp_path: Path) -> None:
    """The winning candidate's model is not in the catalog, so the run goes dark."""
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = _seed_sink(args=args, repo=tmp_path, models=(_PRICED_MODEL, _UNPRICED_MODEL))

    cost = run_chain_cost(
        repo=tmp_path,
        work_item_id=_WORK_ITEM,
        run_id=_RUN_ID,
        sink=sink,
        factory=_FACTORY,
        runner=_ScriptedRunner(events_stdout=_chain_events()),
    )

    assert cost is not None
    assert cost.usd_micros is None
    assert cost.model_resolved is False


def test_the_events_read_is_server_qualified(tmp_path: Path) -> None:
    """The read goes to the dispatch's RESOLVED factory, never a bare local one.

    A bare `fabro events` answers for the local server, where this run does
    not exist -- a clean, plausible, wrong answer with no error.
    """
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = _seed_sink(args=args, repo=tmp_path, models=(_PRICED_MODEL,))
    runner = _ScriptedRunner(events_stdout=_chain_events())

    run_chain_cost(
        repo=tmp_path,
        work_item_id=_WORK_ITEM,
        run_id=_RUN_ID,
        sink=sink,
        factory=_FACTORY,
        runner=runner,
    )

    events_call = next(argv for argv in runner.calls if "events" in argv)
    assert _RUN_ID in events_call
    assert "--server" in events_call
    assert _FACTORY.server in events_call


@pytest.mark.parametrize(
    ("events_stdout", "events_exit_code"),
    [
        ("[]", 0),
        ('{"not": "an array"}', 0),
        ("", 1),
        ("not json at all", 0),
    ],
)
def test_an_unusable_event_stream_yields_no_chain_cost(
    tmp_path: Path, *, events_stdout: str, events_exit_code: int
) -> None:
    """No windows means no chain, and no chain means the legacy path decides.

    Each variant is a real shape -- a pre-chain engine emitting no started
    records, a changed envelope, a failed read, unparseable output. None of
    them is evidence about candidates, so none of them may replace the
    accumulator every ordinary dispatch is priced by today.
    """
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = _seed_sink(args=args, repo=tmp_path, models=(_PRICED_MODEL,))

    cost = run_chain_cost(
        repo=tmp_path,
        work_item_id=_WORK_ITEM,
        run_id=_RUN_ID,
        sink=sink,
        factory=_FACTORY,
        runner=_ScriptedRunner(events_stdout=events_stdout, events_exit_code=events_exit_code),
    )

    assert cost is None


def test_a_run_that_accrued_no_telemetry_yields_no_chain_cost(tmp_path: Path) -> None:
    """With no observations there is nothing to attribute, dark either way."""
    args = _args(journal_path=tmp_path / "journal.jsonl")

    cost = run_chain_cost(
        repo=tmp_path,
        work_item_id=_WORK_ITEM,
        run_id=_RUN_ID,
        sink=CostSink(path=cost_sink_path(args=args, repo=tmp_path)),
        factory=_FACTORY,
        runner=_ScriptedRunner(events_stdout=_chain_events()),
    )

    assert cost is None


def test_a_repository_with_no_resolvable_factory_yields_no_chain_costs(
    tmp_path: Path,
) -> None:
    """No factory, no server-qualified read, no chain cost -- and no crash.

    `tmp_path` carries no `.livespec.jsonc`, which is also the state every
    existing cost-gate test runs in: this is the control proving the new
    composition cannot disturb them.
    """
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = _seed_sink(args=args, repo=tmp_path, models=(_PRICED_MODEL,))
    runner = _ScriptedRunner(events_stdout=_chain_events())

    costs = chain_costs(repo=tmp_path, outcomes=(_green(),), sink=sink, runner=runner)

    assert costs == {}
    assert runner.calls == []


def test_a_terminally_unsuccessful_run_is_never_read_for_cost(tmp_path: Path) -> None:
    """ "Terminally unsuccessful runs retain the existing no-cost-observation posture."

    No events are fetched for it at all, which is stronger than discarding the
    result: a failed run's partial telemetry must not become a cost
    observation, and the read itself is what would make one available.
    """
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = _seed_sink(args=args, repo=tmp_path, models=(_PRICED_MODEL,))
    runner = _ScriptedRunner(events_stdout=_chain_events())

    costs = chain_costs(
        repo=tmp_path,
        outcomes=(_failed(),),
        sink=sink,
        runner=runner,
        factory_of=lambda **_: _FACTORY,
    )

    assert costs == {}
    assert runner.calls == []


def test_a_green_run_with_no_recorded_run_id_is_not_read(tmp_path: Path) -> None:
    """A run nobody can name cannot be queried; the legacy path decides."""
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = _seed_sink(args=args, repo=tmp_path, models=(_PRICED_MODEL,))
    runner = _ScriptedRunner(events_stdout=_chain_events())

    costs = chain_costs(
        repo=tmp_path,
        outcomes=(_green(run_id=None),),
        sink=sink,
        runner=runner,
        factory_of=lambda **_: _FACTORY,
    )

    assert costs == {}
    assert runner.calls == []


def test_a_resolved_chain_cost_is_keyed_by_work_item(tmp_path: Path) -> None:
    """The map the gate and the reporter both read is keyed the way they look."""
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = _seed_sink(args=args, repo=tmp_path, models=(_PRICED_MODEL, _PRICED_MODEL))

    costs = chain_costs(
        repo=tmp_path,
        outcomes=(_green(),),
        sink=sink,
        runner=_ScriptedRunner(events_stdout=_chain_events()),
        factory_of=lambda **_: _FACTORY,
    )

    assert set(costs) == {_WORK_ITEM}
    assert costs[_WORK_ITEM].usd_micros == 10_000_000


def test_the_derived_cost_map_prefers_the_chain_over_the_sink_aggregate(
    tmp_path: Path,
) -> None:
    """A priceable chain's total is what the gate gates on.

    The sink's own aggregate for these same two calls is a different number --
    it prices each span independently and falls back to the default model for
    anything it cannot name -- so this assertion is only satisfiable by reading
    the chain.
    """
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = _seed_sink(args=args, repo=tmp_path, models=(_PRICED_MODEL, _UNPRICED_MODEL))
    chains = chain_costs(
        repo=tmp_path,
        outcomes=(_green(),),
        sink=sink,
        runner=_ScriptedRunner(events_stdout=_chain_events()),
        factory_of=lambda **_: _FACTORY,
    )
    assert chains[_WORK_ITEM].usd_micros is None
    assert sink.usd_micros(key=_WORK_ITEM) is not None

    derived = derived_costs(args=args, repo=tmp_path, outcomes=[_green()], chains=chains)

    assert _WORK_ITEM not in derived


def test_a_darkened_chain_refuses_an_unattended_drain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The EXISTING fail-closed branch handles it: unattended drain refuses.

    Asserted on the gate's own journal record rather than on the report, so an
    implementation that darkened only the report while gating on the sink's
    default-priced number cannot pass. The alarm is asserted too, because a
    refusal nobody is told about is not the posture the gate promises: the
    ntfy topic is set so the spend-cap event actually leaves through the
    injected poster rather than being journaled as skipped.
    """
    monkeypatch.setenv("LIVESPEC_COST_MODE", "enforce")
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "livespec-test-topic")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_cost_chain"
        ".resolve_projection_factory",
        lambda **_: _FACTORY,
    )
    args = _args(journal_path=tmp_path / "journal.jsonl")
    _seed_sink(args=args, repo=tmp_path, models=(_PRICED_MODEL, _UNPRICED_MODEL))
    journal = _RecordingJournal()
    poster = _RecordingPoster()

    cost_gate_after_verdict(
        args=args,
        repo=tmp_path,
        outcomes=[_green()],
        journal=journal,
        runner=_ScriptedRunner(events_stdout=_chain_events(), ps_stdout=_ps_null()),
        poster=poster,
    )

    gate = next(record for record in journal.records if record.get("stage") == "cost-gate")
    assert gate["observable"] is False
    assert gate["refuse"] is True
    assert len(poster.calls) == 1
    assert _WORK_ITEM in str(poster.calls[0]["body"])
    assert "spend-cap-breach" in str(poster.calls[0]["body"])


def test_a_darkened_chain_only_warns_a_hand_picked_item_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Keyed on `--item` presence": a human-attended dispatch warns, never refuses.

    Same sink, same events, same mode as the test above -- the ONLY difference
    is `args.items`, which is exactly what the ratified gate is keyed on.
    """
    monkeypatch.setenv("LIVESPEC_COST_MODE", "enforce")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_cost_chain"
        ".resolve_projection_factory",
        lambda **_: _FACTORY,
    )
    args = _args(journal_path=tmp_path / "journal.jsonl", items=[_WORK_ITEM])
    _seed_sink(args=args, repo=tmp_path, models=(_PRICED_MODEL, _UNPRICED_MODEL))
    journal = _RecordingJournal()
    poster = _RecordingPoster()

    cost_gate_after_verdict(
        args=args,
        repo=tmp_path,
        outcomes=[_green()],
        journal=journal,
        runner=_ScriptedRunner(events_stdout=_chain_events(), ps_stdout=_ps_null()),
        poster=poster,
    )

    gate = next(record for record in journal.records if record.get("stage") == "cost-gate")
    assert gate["observable"] is False
    assert gate["refuse"] is False
    assert poster.calls == []


def test_the_report_mode_summary_names_the_pricing_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The default `report` posture echoes the chain's own unobservability.

    `report` mode never refuses, so the only visible artifact is the stderr
    summary -- and it must say the cost could not be PRICED rather than that
    no telemetry arrived, because telemetry did arrive.
    """
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_cost_chain"
        ".resolve_projection_factory",
        lambda **_: _FACTORY,
    )
    args = _args(journal_path=tmp_path / "journal.jsonl")
    _seed_sink(args=args, repo=tmp_path, models=(_PRICED_MODEL, _UNPRICED_MODEL))

    cost_gate_after_verdict(
        args=args,
        repo=tmp_path,
        outcomes=[_green()],
        journal=_RecordingJournal(),
        runner=_ScriptedRunner(events_stdout=_chain_events(), ps_stdout=_ps_null()),
        poster=_RecordingPoster(),
    )

    captured = capsys.readouterr().err
    assert "unobservable" in captured
    assert "could not be priced" in captured


def test_the_legacy_derived_cost_map_is_unchanged_without_chains(tmp_path: Path) -> None:
    """With no chain costs the map is exactly the sink's own aggregate.

    The control for "a single-candidate run is priced exactly as before this
    change" at the wiring level: the chains argument defaults to none, and the
    number the gate sees is the one it has always seen.
    """
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = _seed_sink(args=args, repo=tmp_path, models=(_PRICED_MODEL,))

    derived = derived_costs(args=args, repo=tmp_path, outcomes=[_green()])

    assert derived[_WORK_ITEM] == sink.usd_micros(key=_WORK_ITEM)
