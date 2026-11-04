"""The DEGRADED readings one performed confirmation turn can come back with.

Beside `test_acp_availability_probe_timeout.py`, which binds the clause. These
are the arms a healthy factory never produces, and every one of them is a state
in which a probe would be reported CONFIRMED if the reading simply fell through
-- which is the one direction the whole clause exists to refuse. "It MUST NOT
treat an unobserved candidate as confirmed unheld."

THE RUN-ID-LESS LAUNCH IS THE SHARPEST OF THEM, and it is read in both
directions. `fabro run` prints the run id early, so a launch this Dispatcher
killed usually carries one; a launch that carries none has unfinished work on a
factory nothing here can name, and `terminated` must say so rather than claim a
reap that never happened.

A SEPARATE module rather than cases in that one because these were authored at
that Red's Green, and a Red's test bytes are fixed across its Red-to-Green pair.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_RUN_ID = "01M5PROBE00000000000000000"
_NOW = "2026-10-20T12:30:00Z"

_FACTORIES_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "default_factory": "hp",
      "factories": {
        "hp": {"server": "https://hp.example.ts.net:32276"}
      }
    }
  }
}
"""


def _runner() -> Any:
    return importlib.import_module(f"{_PACKAGE}._acp_availability_probe_run")


@dataclass(kw_only=True)
class _Command:
    exit_code: int
    stdout: str
    stderr: str = ""


@dataclass(kw_only=True)
class _Engine:
    """A fabro runner whose every per-verb answer the case supplies."""

    launch_exit_code: int = 0
    launch_stdout: str = f"Run: {_RUN_ID}\n"
    rm_exit_code: int = 0
    inspect_stdout: str = "[]"
    events_stdout: str = "[]"
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
            return _Command(exit_code=0, stdout=self.inspect_stdout)
        if "events" in argv:
            return _Command(exit_code=0, stdout=self.events_stdout)
        if "rm" in argv:
            return _Command(exit_code=self.rm_exit_code, stdout="")
        return _Command(exit_code=self.launch_exit_code, stdout=self.launch_stdout)

    def subcommands(self) -> list[str]:
        """Which fabro verbs this probe actually spent."""
        verbs = ("run", "inspect", "events", "rm")
        return [verb for argv in self.calls for verb in verbs if verb in argv]


def _candidate() -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="claude-code-acp"),
        identity=schema.AcpCandidateIdentity(
            display_name="Claude Opus 5",
            candidate_key="claude-opus-5-high",
            availability_key="anthropic",
        ),
    )


def _probe(*, tmp_path: Path, engine: _Engine) -> Any:
    _ = (tmp_path / ".livespec.jsonc").write_text(_FACTORIES_CONFIG, encoding="utf-8")
    return _runner().run_availability_probe(
        repo=tmp_path,
        candidate=_candidate(),
        builtin=True,
        work_item_id="bd-ib-n3pzcl",
        observation_ids=(),
        now_iso=_NOW,
        timeout_seconds=120,
        runner=engine,
    )


def test_a_launch_whose_run_id_cannot_be_read_confirms_nothing_and_reads_nothing(
    tmp_path: Path,
) -> None:
    """No run was named, so no turn completed and nothing could be asked about it."""
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    engine = _Engine(launch_stdout="the launch printed no run id\n")

    result = _probe(tmp_path=tmp_path, engine=engine)

    assert not isinstance(result, str), result
    assert result.ending == outcome.PROBE_PROCESS_EXIT
    assert result.confirmed is False
    assert result.run_id is None
    assert result.terminated is False
    assert result.hold_record is None
    assert result.journal_record["cost_usd_micros"] is None
    # Nothing was asked about a run that was never named.
    assert engine.subcommands() == ["run"]


def test_a_timed_out_launch_whose_run_id_cannot_be_read_reaps_nothing_and_says_so(
    tmp_path: Path,
) -> None:
    """Unfinished work on a factory this Dispatcher cannot name is reported, not claimed."""
    module = _runner()
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    engine = _Engine(
        launch_exit_code=module.PROBE_LAUNCH_TIMEOUT_EXIT_CODE,
        launch_stdout="the launch printed no run id\n",
    )

    result = _probe(tmp_path=tmp_path, engine=engine)

    assert not isinstance(result, str), result
    assert result.ending == outcome.PROBE_TIMED_OUT
    assert result.terminated is False
    assert engine.subcommands() == ["run"]


def test_a_reap_the_factory_refuses_is_reported_as_not_terminated(tmp_path: Path) -> None:
    """A reap that did not land leaves work running, and the record must not claim it did."""
    module = _runner()
    engine = _Engine(
        launch_exit_code=module.PROBE_LAUNCH_TIMEOUT_EXIT_CODE,
        rm_exit_code=1,
    )

    result = _probe(tmp_path=tmp_path, engine=engine)

    assert not isinstance(result, str), result
    assert result.terminated is False
    assert engine.subcommands() == ["run", "rm"]


def test_a_pinned_engine_checkpoint_record_confirms_through_its_node_outcomes(
    tmp_path: Path,
) -> None:
    """The pinned engine answers from a checkpoint, the Petri era from `stages`."""
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    probe = importlib.import_module(f"{_PACKAGE}._acp_availability_probe")
    engine = _Engine(
        inspect_stdout=json.dumps(
            [
                {
                    "run_id": _RUN_ID,
                    "status": {"kind": "succeeded"},
                    "total_usd_micros": 11,
                    "checkpoints": [
                        {"checkpoint": "ignored"},
                        {"node_outcomes": {probe.AVAILABILITY_PROBE_NODE: {"status": "succeeded"}}},
                    ],
                }
            ]
        )
    )

    result = _probe(tmp_path=tmp_path, engine=engine)

    assert not isinstance(result, str), result
    assert result.ending == outcome.PROBE_TURN_COMPLETED
    assert result.journal_record["cost_usd_micros"] == 11


@pytest.mark.parametrize(
    "inspect_stdout",
    [
        # No run record at all.
        "[]",
        # A record carrying no gradeable outcome in either shape.
        json.dumps([{"run_id": _RUN_ID, "status": {"kind": "failed"}}]),
        # `checkpoints` present but not a list.
        json.dumps([{"run_id": _RUN_ID, "checkpoints": {"node_outcomes": {}}}]),
        # `checkpoints` an EMPTY list, which must fall through to `stages`.
        json.dumps([{"run_id": _RUN_ID, "checkpoints": []}]),
        # A checkpoint list carrying nothing readable.
        json.dumps([{"run_id": _RUN_ID, "checkpoints": ["not-a-checkpoint"]}]),
    ],
)
def test_an_ungradeable_run_record_confirms_nothing(tmp_path: Path, inspect_stdout: str) -> None:
    """Unavailable evidence is never a completed turn, in any of its shapes."""
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    engine = _Engine(inspect_stdout=inspect_stdout)

    result = _probe(tmp_path=tmp_path, engine=engine)

    assert not isinstance(result, str), result
    assert outcome.probe_confirms(ending=result.ending) is False


@pytest.mark.parametrize(
    ("events_stdout", "expected_ending"),
    [
        # Not an array at all.
        ('{"type": "agent.acp.started"}', "PROBE_PROCESS_EXIT"),
        # An array carrying nothing readable.
        ('["agent.acp.started"]', "PROBE_PROCESS_EXIT"),
        # Another node's start says nothing about the probe's own attempt.
        ('[{"type": "agent.acp.started", "node": "implement"}]', "PROBE_PROCESS_EXIT"),
        # Some other event type on the probe node.
        ('[{"type": "agent.acp.finished", "node": "confirm"}]', "PROBE_PROCESS_EXIT"),
        # A start whose node the engine recorded unreadably is read as the
        # probe's own: the run has exactly one node, so a start in it crossed
        # the probe's prompt boundary, and the conservative direction here is
        # the one that does NOT let a refusal read as a bare process exit.
        ('[{"type": "agent.acp.started", "node": null}]', "PROBE_SESSION_CREATED"),
        # The visit-qualified spelling of the probe node.
        ('[{"type": "agent.acp.started", "node": "confirm@1"}]', "PROBE_SESSION_CREATED"),
    ],
)
def test_the_prompt_boundary_is_read_off_the_probe_nodes_own_start(
    tmp_path: Path, events_stdout: str, expected_ending: str
) -> None:
    """A session that opened and one that never did take different routes."""
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    engine = _Engine(
        inspect_stdout=json.dumps(
            [
                {
                    "run_id": _RUN_ID,
                    "status": {"kind": "failed"},
                    "stages": {"confirm@1": {"state": "failed"}},
                }
            ]
        ),
        events_stdout=events_stdout,
    )

    result = _probe(tmp_path=tmp_path, engine=engine)

    assert not isinstance(result, str), result
    assert result.ending == getattr(outcome, expected_ending)


def test_one_entitlement_shared_across_nodes_is_probed_once_per_evaluation() -> None:
    """A confirmation turn spends a real allowance, so the memo is not an optimisation.

    The contract lets one entitlement be "repeated across nodes when that
    identity is truly shared", and the verdict builder hands every node of one
    evaluation the SAME memo. Without it each node probes the shared candidate
    again -- one real factory run apiece -- so this counts the turns rather than
    reading the verdict, which is identical either way.
    """
    preflight = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    resolution = importlib.import_module(f"{_PACKAGE}._acp_chain_resolution")
    digests = importlib.import_module(f"{_PACKAGE}._acp_chain_digests")
    classifier = importlib.import_module(f"{_PACKAGE}._acp_failure_classifier")
    hold_records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")

    built = hold_records.hold_observation_record(
        failure=classifier.AcpAvailabilityFailure(
            cause="quota",
            scope="availability-domain",
            hold_key="anthropic",
            availability_key="anthropic",
            candidate_key=None,
            source="protocol.message",
        ),
        evidence_kind="candidate-attempt",
        evidence_id="hp:01MEARLIER:implement",
        occurred_at="2026-10-20T11:00:00Z",
        work_item_id="bd-ib-n3pzcl",
        node="implement",
    )
    assert isinstance(built, dict)
    expired = hold_records.parse_hold_record(record=built)
    assert not isinstance(expired, str), expired

    turns: list[str] = []

    def confirm(candidate: Any) -> str:
        turns.append(candidate.identity.candidate_key)
        return outcome.PROBE_TURN_COMPLETED

    inputs = preflight.PreflightInputs(expired_holds=(expired,), confirm=confirm)
    memo: dict[str, str] = {}
    assessed: dict[str, str] = {}
    for node in ("implement", "review"):
        primary = _candidate()
        chain = resolution.ResolvedAcpChain(
            node=node,
            enabled=True,
            primary=primary,
            fallbacks=(),
            primary_generation=digests.primary_generation_digest(primary=primary),
            full_chain=digests.full_chain_digest(primary=primary, fallbacks=()),
            redacted={},
        )
        graded = preflight.filter_node_candidates(
            chain=chain, inputs=inputs, assessed=assessed, confirmed=memo
        )
        assert graded.skipped == ()

    assert turns == ["claude-opus-5-high"]


def test_a_cancelled_run_is_its_own_ending(tmp_path: Path) -> None:
    """Both spellings the engine uses for a cancellation read as one ending."""
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")

    for spelling in ("cancelled", "canceled"):
        engine = _Engine(
            inspect_stdout=json.dumps([{"run_id": _RUN_ID, "status": {"kind": spelling}}]),
            events_stdout='[{"type": "agent.acp.started", "node": "confirm"}]',
        )

        result = _probe(tmp_path=tmp_path, engine=engine)

        assert not isinstance(result, str), result
        assert result.ending == outcome.PROBE_CANCELLED
