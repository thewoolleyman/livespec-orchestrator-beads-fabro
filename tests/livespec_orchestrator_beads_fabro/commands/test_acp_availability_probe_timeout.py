"""A probe past its bound is TERMINATED, skips its candidate, and selection goes on.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry": "Any other probe
failure skips that candidate for the current evaluation, creates no hold, and
allows selection to continue to later eligible candidates. ... Probe execution
MUST be bounded by the committed-configuration-only
`dispatcher.availability_probe_timeout_seconds` (positive integer, default
120), including termination of unfinished probe work." Scenario 127's "A
timed-out availability probe skips its candidate and permits an eligible
fallback" is the scenario, and its three Thens are the three claims below:
terminated, skipped without a hold, and the fallback selected.

THE TERMINATION IS ASSERTED ON THE ENGINE RATHER THAN ON A RETURN VALUE. No
return value can carry "the unfinished work was ended", and a runner that
answered whatever it was asked cannot tell a correct reap from a plausible one
-- so the reap is read back out of the recorded argv, keyed on the fabro
SUBCOMMAND rather than on call order, which is what lets each assertion name
the read it is about.

THE SELECTION HALF IS WHAT THE SKIP IS FOR, and it is asserted on the
SURVIVING candidate rather than on the skip. A filter that recorded the skip
while emptying the node satisfies every assertion about the skip itself, and
the item then waits on a chain that had an eligible fallback all along -- the
"without defeating an eligible fallback" half of Scenario 60.

EVERY NEGATIVE IS PAIRED WITH THE POSITIVE IT MUST DIFFER FROM. The confirming
probe below is what refuses a filter that skips every candidate owing a
confirmation, which is what the build before this one did unconditionally; and
the no-seam case is what keeps that earlier behaviour intact where no probe is
supplied at all.

Everything is HERMETIC: configuration lives in `tmp_path`, the engine is
injected, no port reaches a server, and nothing launches an adapter or touches
a provider.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = "_acp_availability_probe_run"

_RUN_ID = "01M5PROBE00000000000000000"
_NOW = "2026-10-20T12:30:00Z"
_WORK_ITEM = "bd-ib-n3pzcl"
# `ShellCommandRunner` maps a timed-out command to this exit status.
_TIMEOUT_EXIT = 124

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


def _runner_module() -> Any:
    """Import the probe's performing half, proving its file exists first."""
    path = _COMMANDS / f"{_MODULE}.py"
    assert path.is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


@dataclass(kw_only=True)
class _Command:
    """The one shape the port's runner protocol reads off a result."""

    exit_code: int
    stdout: str
    stderr: str = ""


@dataclass(kw_only=True)
class _Engine:
    """A fabro runner keyed on SUBCOMMAND, recording every argv it was given."""

    launch_exit_code: int = 0
    node_state: str = "succeeded"
    failure_cause: str | None = None
    cost_usd_micros: int | None = 7300
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
            return _Command(exit_code=0, stdout=json.dumps([self._record()]))
        if "events" in argv:
            return _Command(exit_code=0, stdout=json.dumps(self._events()))
        if "rm" in argv:
            return _Command(exit_code=0, stdout="")
        return _Command(exit_code=self.launch_exit_code, stdout=f"Run: {_RUN_ID}\n")

    def _record(self) -> dict[str, Any]:
        probe = importlib.import_module(f"{_PACKAGE}._acp_availability_probe")
        record: dict[str, Any] = {
            "run_id": _RUN_ID,
            "status": {"kind": "succeeded" if self.node_state == "succeeded" else "failed"},
            "goal": "Confirm one ACP candidate's availability.",
            "total_usd_micros": self.cost_usd_micros,
            "stages": {f"{probe.AVAILABILITY_PROBE_NODE}@1": {"state": self.node_state}},
        }
        if self.failure_cause is not None:
            record["failure"] = {
                "category": "transient_infra",
                "signature": "confirm|deterministic|acp turn failed",
                "causes": ["ACP protocol error", self.failure_cause],
            }
        return record

    def _events(self) -> list[dict[str, Any]]:
        probe = importlib.import_module(f"{_PACKAGE}._acp_availability_probe")
        return [
            {
                "event_id": "ev-1",
                "type": "agent.acp.started",
                "occurred_at": "2026-10-20T12:29:00Z",
                "node": probe.AVAILABILITY_PROBE_NODE,
            }
        ]

    def argv_for(self, *, subcommand: str) -> list[list[str]]:
        """Every recorded argv whose fabro subcommand is this one."""
        return [argv for argv in self.calls if subcommand in argv]


def _candidate(
    *, availability_key: str = "anthropic", candidate_key: str = "claude-opus-5-high"
) -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(
            command="claude-code-acp", env={"ANTHROPIC_MODEL": "claude-opus-5"}
        ),
        identity=schema.AcpCandidateIdentity(
            display_name=f"candidate {candidate_key}",
            candidate_key=candidate_key,
            availability_key=availability_key,
        ),
    )


def _repo(*, tmp_path: Path) -> Path:
    _ = (tmp_path / ".livespec.jsonc").write_text(_FACTORIES_CONFIG, encoding="utf-8")
    return tmp_path


def _probe(*, tmp_path: Path, engine: _Engine, timeout_seconds: int = 120) -> Any:
    """Perform one confirmation turn through the injected engine."""
    return _runner_module().run_availability_probe(
        repo=_repo(tmp_path=tmp_path),
        candidate=_candidate(),
        builtin=True,
        work_item_id=_WORK_ITEM,
        observation_ids=("acp-aaaa1111",),
        now_iso=_NOW,
        timeout_seconds=timeout_seconds,
        runner=engine,
    )


def test_a_probe_past_its_bound_is_terminated_and_mints_no_hold(tmp_path: Path) -> None:
    """The first and second Thens: unfinished work ended, candidate skipped, no hold."""
    module = _runner_module()
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    engine = _Engine(launch_exit_code=_TIMEOUT_EXIT, failure_cause="You've hit your usage limit.")

    result = _probe(tmp_path=tmp_path, engine=engine)

    assert not isinstance(result, str), result
    assert result.ending == outcome.PROBE_TIMED_OUT
    assert result.confirmed is False
    assert result.terminated is True
    # The unfinished probe work was ended ON THE ENGINE, read back off the argv.
    reaps = engine.argv_for(subcommand="rm")
    assert len(reaps) == 1
    assert _RUN_ID in reaps[0]
    assert "-f" in reaps[0]
    # No hold, even though the recorded failure carries a quota sentence.
    assert result.hold_record is None
    assert result.journal_record["outcome"] == outcome.PROBE_TIMED_OUT
    assert module.PROBE_LAUNCH_TIMEOUT_EXIT_CODE == _TIMEOUT_EXIT


def test_the_launch_is_bounded_by_the_committed_probe_timeout(tmp_path: Path) -> None:
    """The bound is the configured figure, carried into the graph the engine ran."""
    engine = _Engine()

    result = _probe(tmp_path=tmp_path, engine=engine, timeout_seconds=97)

    assert not isinstance(result, str), result
    assert engine.argv_for(subcommand="run")


def test_a_completed_turn_confirms_and_reaps_nothing(tmp_path: Path) -> None:
    """The positive control: without it every refusal here passes vacuously."""
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    engine = _Engine()

    result = _probe(tmp_path=tmp_path, engine=engine)

    assert not isinstance(result, str), result
    assert result.ending == outcome.PROBE_TURN_COMPLETED
    assert result.confirmed is True
    assert result.terminated is False
    assert engine.argv_for(subcommand="rm") == []
    assert result.hold_record is None
    assert result.journal_record["cost_usd_micros"] == 7300
    assert result.journal_record["confirmed"] is True


def test_an_eligible_refusal_mints_the_hold_and_still_reaps_nothing(tmp_path: Path) -> None:
    """A refusal is an actual attempt, so it holds the allowance it measured."""
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    engine = _Engine(
        launch_exit_code=1,
        node_state="failed",
        failure_cause="You've hit your usage limit. Your limit will reset at 3pm.",
    )

    result = _probe(tmp_path=tmp_path, engine=engine)

    assert not isinstance(result, str), result
    assert result.ending == outcome.PROBE_REFUSED
    assert result.confirmed is False
    assert result.hold_record is not None
    assert result.hold_record["cause"] == "quota"
    assert result.hold_record["occurred_at"] == _NOW
    assert engine.argv_for(subcommand="rm") == []


def test_a_candidate_the_probe_cannot_run_is_refused_before_any_run_exists(
    tmp_path: Path,
) -> None:
    """An in-protocol candidate's model reaches no adapter, so nothing is launched."""
    module = _runner_module()
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    engine = _Engine()

    result = module.run_availability_probe(
        repo=_repo(tmp_path=tmp_path),
        candidate=schema.AcpCandidate(
            adapter=adapters.AcpAdapter(command="grok-acp"),
            identity=schema.AcpCandidateIdentity(
                display_name="Grok", candidate_key="grok-4.6", availability_key="xai"
            ),
            config_options={"model": "grok-4.6"},
        ),
        builtin=False,
        work_item_id=_WORK_ITEM,
        observation_ids=(),
        now_iso=_NOW,
        timeout_seconds=120,
        runner=engine,
    )

    assert isinstance(result, str)
    assert "config_options" in result
    assert engine.calls == []


def test_a_repository_with_no_participating_factory_refuses_without_launching(
    tmp_path: Path,
) -> None:
    """A probe has nowhere to become host-wide evidence, so it is not run at all."""
    module = _runner_module()
    engine = _Engine()

    result = module.run_availability_probe(
        repo=tmp_path,
        candidate=_candidate(),
        builtin=True,
        work_item_id=_WORK_ITEM,
        observation_ids=(),
        now_iso=_NOW,
        timeout_seconds=120,
        runner=engine,
    )

    assert isinstance(result, str)
    assert "factory" in result
    assert engine.calls == []


def _filter_inputs(*, confirm: Any, expired: Any) -> Any:
    """One evaluation's preflight inputs carrying the confirmation seam."""
    import dataclasses

    preflight = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")
    names = {one.name for one in dataclasses.fields(preflight.PreflightInputs)}
    assert "confirm" in names, "PreflightInputs carries no confirmation-turn seam yet"
    return preflight.PreflightInputs(expired_holds=expired, confirm=confirm)


def _expired_domain_hold() -> Any:
    """One EXPIRED domain observation over the primary's allowance."""
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
        work_item_id=_WORK_ITEM,
        node="implement",
    )
    assert isinstance(built, dict)
    parsed = hold_records.parse_hold_record(record=built)
    assert not isinstance(parsed, str), parsed
    return parsed


def _chain() -> Any:
    """A two-candidate chain whose primary owes a confirmation and whose fallback does not.

    The digests are taken through the production functions rather than
    transcribed, so a configuration-independent fixture cannot drift into
    agreeing with a constant nobody rechecks.
    """
    resolution = importlib.import_module(f"{_PACKAGE}._acp_chain_resolution")
    digests = importlib.import_module(f"{_PACKAGE}._acp_chain_digests")
    primary = _candidate()
    fallbacks = (_candidate(availability_key="chatgpt", candidate_key="gpt-5.5-high"),)
    return resolution.ResolvedAcpChain(
        node="implement",
        enabled=True,
        primary=primary,
        fallbacks=fallbacks,
        primary_generation=digests.primary_generation_digest(primary=primary),
        full_chain=digests.full_chain_digest(primary=primary, fallbacks=fallbacks),
        redacted={},
    )


def test_a_timed_out_probe_skips_its_candidate_and_selection_reaches_the_fallback() -> None:
    """The third Then, asserted on the SURVIVING candidate rather than on the skip."""
    preflight = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    probed: list[str] = []

    def confirm(candidate: Any) -> str:
        probed.append(candidate.identity.candidate_key)
        return outcome.PROBE_TIMED_OUT

    graded = preflight.filter_node_candidates(
        chain=_chain(),
        inputs=_filter_inputs(confirm=confirm, expired=(_expired_domain_hold(),)),
        assessed={},
    )

    # Selection CONTINUED: the chain is not empty and the fallback is selected.
    assert graded.exhausted is False
    assert [one.identity.candidate_key for one in graded.candidates] == ["gpt-5.5-high"]
    assert [one.candidate_key for one in graded.skipped] == ["claude-opus-5-high"]
    assert graded.skipped[0].reason == preflight.OUTSTANDING_CONFIRMATION_SKIP
    assert graded.skipped[0].condition == outcome.PROBE_TIMED_OUT
    # The fallback owes no confirmation, so it was never probed.
    assert probed == ["claude-opus-5-high"]


def test_a_confirming_probe_leaves_its_candidate_selectable() -> None:
    """The positive control for the filter: not every owed confirmation skips."""
    preflight = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")

    graded = preflight.filter_node_candidates(
        chain=_chain(),
        inputs=_filter_inputs(
            confirm=lambda _candidate: outcome.PROBE_TURN_COMPLETED,
            expired=(_expired_domain_hold(),),
        ),
        assessed={},
    )

    assert [one.identity.candidate_key for one in graded.candidates] == [
        "claude-opus-5-high",
        "gpt-5.5-high",
    ]
    assert graded.skipped == ()


def test_with_no_seam_supplied_an_owed_confirmation_skips_exactly_as_before() -> None:
    """A snapshot composing a verdict reaches no factory, so it probes nothing."""
    preflight = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")

    graded = preflight.filter_node_candidates(
        chain=_chain(),
        inputs=_filter_inputs(confirm=None, expired=(_expired_domain_hold(),)),
        assessed={},
    )

    assert [one.identity.candidate_key for one in graded.candidates] == ["gpt-5.5-high"]
    assert graded.skipped[0].reason == preflight.OUTSTANDING_CONFIRMATION_SKIP
    assert graded.skipped[0].condition is None
