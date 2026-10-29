"""What a production confirmation turn LEAVES BEHIND, and who runs it.

Beside `test_acp_confirmation_admission_wiring.py`, which binds that admission
runs the turn at all (`bd-ib-i4nert`). These bind the other Definition-of-Done
assertions of that item, and every one is a state in which the lock-out would
return if the condition it grades were dropped:

- A CONFIRMING turn leaves a journal row naming the expired observations it was
  run for, and an attempt-cost record charged to the ONE item whose evaluation
  ran it. A later admission is then not skipped for them -- which needs the
  factory read to keep seeing the probe's success PAST `HOLD_INTERVAL`, the
  window every ORDINARY run's success is aged out of. Without that, a
  low-traffic tenant re-runs a turn at every admission and is never satisfied.
  The ordinary-run case beside it is the control: it keeps its window.
- `dispatch --item` and `loop --item` differ in the WIP cap they pass the valve,
  and neither may differ in whether a turn is run. The pre-dispatch screen
  resolves a verdict ahead of the valve and the valve REUSES it while it is
  fresh, so a screen that ran no turn would hand the valve the refusal the turn
  exists to prevent.
- A turn that does NOT confirm is recorded on the refusal row it leaves, so a
  reader can tell "nobody asked" (an empty list) from "asked and not confirmed".

HERMETIC, as the sibling is: a recording fake engine and a fake run listing.
"""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_RUN_PREFIX = "01M5PROBE"
_OBSERVATION_ID = "acp-expired0001"
_ITEM = "bd-ib-low-traffic"

_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "default_factory": "hp",
      "factories": {"hp": {"server": "https://hp.example.ts.net:32276"}},
      "acp_nodes": {
        "implement": {
          "display_name": "Primary",
          "candidate_key": "primary",
          "availability_key": "anthropic",
          "command": "adapter-primary",
          "availability_signatures": [
            {
              "source": "protocol.message",
              "all_literals": ["usage limit"],
              "cause": "quota",
              "scope": "availability-domain",
              "hold_key": "anthropic"
            }
          ],
          "fallbacks": [
            {
              "display_name": "Fallback",
              "candidate_key": "fallback",
              "availability_key": "anthropic",
              "command": "adapter-fallback",
              "availability_signatures": [
                {
                  "source": "protocol.message",
                  "all_literals": ["usage limit"],
                  "cause": "quota",
                  "scope": "availability-domain",
                  "hold_key": "anthropic"
                }
              ]
            }
          ]
        }
      }
    }
  }
}
"""

_MANIFEST = """[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "adapter-primary"
"""

_GRAPH = """
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="a", timeout="60s"]
    start -> implement
    implement -> exit [label="green", condition="outcome=succeeded"]
"""


@dataclass(kw_only=True)
class _Command:
    exit_code: int
    stdout: str
    stderr: str = ""


@dataclass(kw_only=True)
class _Engine:
    """A fabro runner that mints a distinct run id per launch, as a factory does."""

    node_state: str = "succeeded"
    failure_cause: str | None = None
    launch_exit_code: int = 0
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> _Command:
        self.calls.append(list(argv))
        _ = (cwd, timeout_seconds, env)
        if "--version" in argv:
            return _Command(exit_code=0, stdout="fabro 0.254.0 (8869e88 2026-10-01)\n")
        if "inspect" in argv:
            run_id = next(part for part in argv if part.startswith(_RUN_PREFIX))
            record: dict[str, Any] = {
                "run_id": run_id,
                "status": {"kind": "succeeded" if self.node_state == "succeeded" else "failed"},
                "total_usd_micros": 7300,
                "stages": {"confirm@1": {"state": self.node_state}},
            }
            if self.failure_cause is not None:
                record["failure"] = {
                    "category": "transient_infra",
                    "signature": "confirm|deterministic|acp turn failed",
                    "causes": ["ACP protocol error", self.failure_cause],
                }
            return _Command(exit_code=0, stdout=json.dumps([record]))
        if "events" in argv:
            events = [{"event_id": "e1", "type": "agent.acp.started", "node": "confirm"}]
            return _Command(exit_code=0, stdout=json.dumps(events))
        if "rm" in argv:
            return _Command(exit_code=0, stdout="")
        return _Command(
            exit_code=self.launch_exit_code,
            stdout=f"Run: {_RUN_PREFIX}{len(self.launches()):016d}\n",
        )

    def launches(self) -> list[list[str]]:
        return [argv for argv in self.calls if "--label" in argv]


class _EmptyFactory:
    def __init__(self, *, repo: Path) -> None:
        self.repo = repo

    def list_runs(self, *, factory: str) -> tuple[()]:
        _ = factory
        return ()


@dataclass(frozen=True, kw_only=True)
class _Accounting:
    active_count: int = 0
    live_lock_active_ids: tuple[str, ...] = ()
    journal_unreadable_active_ids: tuple[str, ...] = ()
    green_terminal_active_ids: tuple[str, ...] = ()
    rework_pending_active_ids: tuple[str, ...] = ()


def _item() -> Any:
    types = importlib.import_module("livespec_orchestrator_beads_fabro.types")
    return types.WorkItem(
        id=_ITEM,
        type="task",
        status="ready",
        title="Task",
        description="Do it.",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy=None,
        acceptance_policy=None,
    )


def _expired_domain_hold_row() -> dict[str, object]:
    records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")
    classifier = importlib.import_module(f"{_PACKAGE}._acp_failure_classifier")
    return {
        "stage": records.HOLD_STAGE,
        "schema_version": records.HOLD_SCHEMA_VERSION,
        "observation_id": _OBSERVATION_ID,
        "scope": classifier.DOMAIN_SCOPE,
        "hold_key": "anthropic",
        "candidate_key": None,
        "cause": "quota",
        "evidence_kind": "acp-failover-event",
        "evidence_id": "petri:01M5S6FRWK93019DZVV3S5GS60:proof_capture",
        "occurred_at": "2026-10-25T10:21:34Z",
        "expires_at": "2026-10-25T10:36:34Z",
        "work_item_id": "bd-gj-oqko6n",
        "node": "proof_capture",
    }


def _rows(*, path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _repo(*, tmp_path: Path) -> Path:
    workflow = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_MANIFEST, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    _ = (tmp_path / ".livespec.jsonc").write_text(_CONFIG, encoding="utf-8")
    _ = (tmp_path / "journal.jsonl").write_text(
        json.dumps(_expired_domain_hold_row()) + "\n", encoding="utf-8"
    )
    return tmp_path


def _wire(*, repo: Path, monkeypatch: pytest.MonkeyPatch, engine: _Engine) -> Any:
    """Patch the valve's collaborators and return its module."""
    admission_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    eligibility_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    probe_run = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_run")
    monkeypatch.setattr(admission_module, "store_config", lambda **_: repo)
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(admission_module, "claimed_active_accounting", lambda **_: _Accounting())
    monkeypatch.setattr(admission_module, "session_headroom_policy", lambda **_: None)
    monkeypatch.setattr(admission_module, "FactoryRunReader", _EmptyFactory)
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(probe_run, "ShellCommandRunner", lambda: engine)
    return admission_module


def _journal(*, repo: Path) -> Any:
    io_module = importlib.import_module(f"{_PACKAGE}._dispatcher_io")
    return io_module.JournalFile(path=repo / "journal.jsonl")


def _turns_run_under(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capped: bool) -> int:
    """How many turns one admission pass runs, with the WIP cap enforced or not."""
    repo = _repo(tmp_path=tmp_path)
    engine = _Engine()
    admission_module = _wire(repo=repo, monkeypatch=monkeypatch, engine=engine)

    admission = admission_module.admit_and_select(
        repo=repo,
        items=[],
        candidates=[_item()],
        journal=_journal(repo=repo),
        enforce_cap=capped,
    )

    assert [item.id for item in admission.admitted] == [_ITEM]
    return len(engine.launches())


def test_dispatch_item_runs_the_owed_turns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`dispatch --item` is the operator override: it passes the valve no cap."""
    assert _turns_run_under(tmp_path=tmp_path, monkeypatch=monkeypatch, capped=False) == 2


def test_loop_item_runs_the_same_turns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`loop --item` reaches the valve through the cap-enforcing unattended drain."""
    assert _turns_run_under(tmp_path=tmp_path, monkeypatch=monkeypatch, capped=True) == 2


def test_the_pre_dispatch_screen_confirms_once_and_the_valve_reuses_its_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screen runs ahead of the valve, so it must run the turns the valve would."""
    repo = _repo(tmp_path=tmp_path)
    engine = _Engine()
    admission_module = _wire(repo=repo, monkeypatch=monkeypatch, engine=engine)
    screen = importlib.import_module(f"{_PACKAGE}._dispatcher_session_headroom_screen")
    screened = importlib.import_module(f"{_PACKAGE}._dispatcher_screened_verdict")
    args = argparse.Namespace()
    journal = _journal(repo=repo)

    refusal = screen.session_headroom_screen_refusal(
        args=args, repo=repo, items=[_item()], journal=journal
    )
    turns_at_the_screen = len(engine.launches())
    admission = admission_module.admit_and_select(
        repo=repo,
        items=[],
        candidates=[_item()],
        journal=journal,
        enforce_cap=False,
        screened=screened.screened_verdict_of(args=args),
    )

    assert refusal is None
    assert turns_at_the_screen == 2
    # The valve stood on the screen's verdict, so it spent no turn of its own.
    assert len(engine.launches()) == 2
    assert [item.id for item in admission.admitted] == [_ITEM]


def test_a_confirming_turn_is_journaled_with_what_it_satisfies_and_charged_to_one_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    admission_module = _wire(repo=repo, monkeypatch=monkeypatch, engine=_Engine())

    _ = admission_module.admit_and_select(
        repo=repo, items=[], candidates=[_item()], journal=_journal(repo=repo), enforce_cap=False
    )

    records = _rows(path=repo / "journal.jsonl")
    turns = [row for row in records if row["stage"] == "acp-availability-confirmation"]
    assert {row["candidate_key"] for row in turns} == {"primary", "fallback"}
    assert all(row["confirmed"] is True for row in turns)
    assert all(row["satisfies_observation_ids"] == [_OBSERVATION_ID] for row in turns)
    costs = [row for row in records if row["stage"] == "attempt-cost"]
    assert len(costs) == 2
    assert {row["work_item_id"] for row in costs} == {_ITEM}


def _probe_success_reader(*, labelled_as_probe: bool, start_time: str) -> Any:
    """A factory listing one SUCCEEDED turn for the primary, three days after the hold."""
    probe = importlib.import_module(f"{_PACKAGE}._acp_availability_probe")
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    candidate = schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="adapter-primary"),
        identity=schema.AcpCandidateIdentity(
            display_name="Primary", candidate_key="primary", availability_key="anthropic"
        ),
    )
    labels = dict(
        pair.split("=", 1) for pair in probe.availability_probe_labels(candidate=candidate)
    )
    if not labelled_as_probe:
        del labels[probe.AVAILABILITY_PROBE_LABEL_KEY]
    run_id = f"{_RUN_PREFIX}{0:016d}"
    row = {
        "run_id": run_id,
        "status": {"kind": "succeeded"},
        "goal": "Confirm one ACP candidate's availability.\n",
        "labels": labels,
        "start_time": start_time,
        "wall_time_ms": 30_000,
    }
    records = importlib.import_module(f"{_PACKAGE}._fabro_port_records")
    summaries = records.fabro_run_summaries_from_payload(payload=[row])
    payload = {
        run_id: [
            {
                "run_id": run_id,
                "status": {"kind": "succeeded"},
                "checkpoint": {
                    "current_node": "exit",
                    "completed_nodes": ["confirm", "exit"],
                    "node_outcomes": {"confirm": {"status": "succeeded"}},
                },
            }
        ]
    }

    class _Reader:
        def list_runs(self, *, factory: str) -> tuple[Any, ...]:
            return summaries if factory == "hp" else ()

        def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
            return payload.get(run_id) if factory == "hp" else None

    return _Reader()


def _later_primary_and_fallback(
    *, repo: Path, labelled_as_probe: bool, start_time: str = "2026-10-26T00:00:00Z"
) -> tuple[list[str], list[str]]:
    composer = importlib.import_module(f"{_PACKAGE}._dispatcher_acp_preflight")
    verdict = composer.resolve_acp_preflight(
        repo=repo,
        journal_path=repo / "journal.jsonl",
        now_iso="2026-10-29T12:00:00Z",
        factory_runs=_probe_success_reader(
            labelled_as_probe=labelled_as_probe, start_time=start_time
        ),
    )
    node = verdict.node_preflight(node="implement")
    return (
        [candidate.identity.candidate_key for candidate in node.candidates],
        [skip.candidate_key for skip in node.skipped],
    )


def test_a_confirming_probe_still_satisfies_the_expired_hold_days_later(tmp_path: Path) -> None:
    """The probe's success is read past `HOLD_INTERVAL`, for the candidate it ran through."""
    repo = _repo(tmp_path=tmp_path)

    selectable, skipped = _later_primary_and_fallback(repo=repo, labelled_as_probe=True)

    # The sibling candidate was never probed, so a turn through the primary
    # confirms nothing about it.
    assert selectable == ["primary"]
    assert skipped == ["fallback"]


def test_an_ordinary_runs_success_still_ages_out_of_the_factory_read(tmp_path: Path) -> None:
    """The control: only a probe is exempt from the window, so the exemption is narrow."""
    repo = _repo(tmp_path=tmp_path)

    selectable, skipped = _later_primary_and_fallback(repo=repo, labelled_as_probe=False)

    assert selectable == []
    assert skipped == ["primary", "fallback"]


def test_a_turn_that_does_not_confirm_is_recorded_on_the_refusal_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    engine = _Engine(node_state="failed")
    admission_module = _wire(repo=repo, monkeypatch=monkeypatch, engine=engine)
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    skips = importlib.import_module(f"{_PACKAGE}._acp_preflight_skips")

    admission = admission_module.admit_and_select(
        repo=repo, items=[], candidates=[_item()], journal=_journal(repo=repo), enforce_cap=False
    )

    assert admission.admitted == []
    refusals = [
        row for row in _rows(path=repo / "journal.jsonl") if row["stage"] == "acp-preflight-refusal"
    ]
    assert len(refusals) == 1
    assert refusals[0]["governing_condition"] == skips.OUTSTANDING_CONFIRMATION_SKIP
    assert len(engine.launches()) == 2
    assert refusals[0]["confirmation_turn_endings"] == [outcome.PROBE_SESSION_CREATED]


def test_a_probe_run_whose_start_cannot_be_read_confirms_nothing(tmp_path: Path) -> None:
    """An undatable success retires nothing, probe or not."""
    repo = _repo(tmp_path=tmp_path)

    selectable, skipped = _later_primary_and_fallback(
        repo=repo, labelled_as_probe=True, start_time="not-an-instant"
    )

    assert selectable == []
    assert skipped == ["primary", "fallback"]


def test_a_refused_turn_mints_the_new_hold_in_the_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An eligible refusal is an actual attempt, so it holds the allowance it measured."""
    repo = _repo(tmp_path=tmp_path)
    engine = _Engine(
        node_state="failed",
        failure_cause="You've hit your usage limit. Your limit will reset at 3pm.",
    )
    admission_module = _wire(repo=repo, monkeypatch=monkeypatch, engine=engine)
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")

    _ = admission_module.admit_and_select(
        repo=repo, items=[], candidates=[_item()], journal=_journal(repo=repo), enforce_cap=False
    )

    records = _rows(path=repo / "journal.jsonl")
    holds = [row for row in records if row["stage"] == "acp-availability-observed"]
    new_holds = [row for row in holds if row["observation_id"] != _OBSERVATION_ID]
    assert {row["cause"] for row in new_holds} == {"quota"}
    assert {row["work_item_id"] for row in new_holds} == {_ITEM}
    refusal = next(row for row in records if row["stage"] == "acp-preflight-refusal")
    assert refusal["confirmation_turn_endings"] == [outcome.PROBE_REFUSED]


def test_a_turn_that_cannot_be_run_leaves_the_confirmation_owed_and_records_no_ending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No participating factory: the candidate is skipped, nothing is launched or minted."""
    repo = _repo(tmp_path=tmp_path)
    _ = (repo / ".livespec.jsonc").write_text(
        _CONFIG.replace('      "default_factory": "hp",\n', "").replace(
            '      "factories": {"hp": {"server": "https://hp.example.ts.net:32276"}},\n', ""
        ),
        encoding="utf-8",
    )
    engine = _Engine()
    admission_module = _wire(repo=repo, monkeypatch=monkeypatch, engine=engine)

    admission = admission_module.admit_and_select(
        repo=repo, items=[], candidates=[_item()], journal=_journal(repo=repo), enforce_cap=False
    )

    assert admission.admitted == []
    assert engine.launches() == []
    records = _rows(path=repo / "journal.jsonl")
    assert [row for row in records if row["stage"] == "acp-availability-confirmation"] == []
    [refusal] = [row for row in records if row["stage"] == "acp-preflight-refusal"]
    assert refusal["confirmation_turn_endings"] == []


def test_a_turn_past_its_bound_is_reaped_and_leaves_the_candidates_skipped_without_a_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The timeout arm: unfinished probe work ends, and a terminated turn mints nothing."""
    repo = _repo(tmp_path=tmp_path)
    engine = _Engine(launch_exit_code=124, failure_cause="You've hit your usage limit.")
    admission_module = _wire(repo=repo, monkeypatch=monkeypatch, engine=engine)
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")

    admission = admission_module.admit_and_select(
        repo=repo, items=[], candidates=[_item()], journal=_journal(repo=repo), enforce_cap=False
    )

    assert admission.admitted == []
    assert len([argv for argv in engine.calls if "rm" in argv]) == 2
    records = _rows(path=repo / "journal.jsonl")
    held = [row for row in records if row["stage"] == "acp-availability-observed"]
    assert [row["observation_id"] for row in held] == [_OBSERVATION_ID]
    refusal = next(row for row in records if row["stage"] == "acp-preflight-refusal")
    assert refusal["confirmation_turn_endings"] == [outcome.PROBE_TIMED_OUT]
