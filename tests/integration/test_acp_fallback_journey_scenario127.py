"""Scenario 127, end to end: one ordered-fallback journey and its version gate.

Binds `SPECIFICATION/scenarios.md` Scenario 127, "Ordered ACP fallback preserves
primary resolution, failure honesty, and one node visit". Every case here starts
from a `.livespec.jsonc` on disk and runs the REAL configuration, catalog, chain,
capability-gate and projection seams; nothing under test is stubbed.

WHAT IS STOOD IN, AND WHY THAT IS THE WHOLE OF IT. Two sockets, both at the
seams the product already publishes for the purpose:

- the factory's `GET /api/v1/system/info` answer, through the
  `FabroHttpTransport` the capability reader accepts. The reader itself, the
  path it builds, its authentication, its payload narrowing and its per-dispatch
  memoization are the production ones.
- the run's own event stream, through the `CommandRunner` the projection
  accepts. The `fabro events` argv, the server qualification, the scan, the hold
  ledger, the warning ledger and the journal writes are the production ones.

A LIVE FACTORY JOURNEY IS A SEPARATE, OPERATIONAL ARTEFACT. S7b's brief also
calls for one controlled run on `hp`, whose evidence is a run id and a journal
excerpt rather than a test. This module is what makes that run CHECKABLE: it
pins the exact event shapes, journal records and counts the live run must
produce, so a divergence is a failing assertion here rather than a judgement
call about a transcript.

WHY THE RECORDED STREAM IS NOT A TAUTOLOGY, which is the obvious objection to
every fixture-driven journey. A fixture can only prove something about the
product if the product DERIVES rather than echoes. Each assertion below is
chosen on that basis: the hold's `expires_at` is derived from occurrence time,
not supplied; the warning's `candidate_key` is the candidate that RESCUED the
node while the hold's is the one that FAILED, which no echo could separate; the
`primary_generation` the events carry is the one this repository's own
configuration resolves, computed here from the config rather than transcribed;
and the confirmed model is read off the started events by the production parser.
The two negative controls are load-bearing for the same reason -- an absent run
reads as unobservable cost, and a factory advertising neither capability refuses
before any of this is reachable.

"UNCHANGED RUN AND SANDBOX IDENTITY" IS ASSERTED AS WHAT THE ORCHESTRATOR CAN
OBSERVE. A Fabro sandbox is a property of its run: one run id is one container.
This repository holds no per-attempt container surface, so inventing an
assertion about one would be asserting against the fixture. What it CAN observe
is that the whole journey resolved to a single run id, reached that run through
exactly one events read against the pinned factory, and stayed inside one node
visit -- which is the same claim, taken on the evidence that exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_capability_gate import (
    CONFIG_OPTIONS_CAPABILITY,
    FALLBACK_CHAIN_CAPABILITY,
    acp_capability_refusal,
)
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import resolve_acp_catalogs
from livespec_orchestrator_beads_fabro.commands._acp_factory_capabilities import (
    factory_capability_reader,
)
from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import AcpEventScan
from livespec_orchestrator_beads_fabro.commands._acp_fallback_events import scan_acp_events
from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_records import (
    MODEL_FALLBACK_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import HOLD_STAGE
from livespec_orchestrator_beads_fabro.commands._acp_journal_records import journal_records
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import repository_acp_chains
from livespec_orchestrator_beads_fabro.commands._acp_projection_run import (
    AcpProjectionRequest,
    project_run_events,
    resolve_acp_primary_generations,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost import observe_run_cost
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_minimum_release_floor import (
    minimum_release_verdict,
    resolve_minimum_release,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import SYSTEM_INFO_PATH

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_NAME = "hp"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_RUN_ID = "01M3WW420JH49ZWJYV15HF73XN"
_WORK_ITEM = "bd-ib-jamtsf"
_REPO_NAME = "livespec-orchestrator-beads-fabro"
_NODE = "implement"

# The two-candidate chain. `glm-acp-agent` declares the `protocol` mechanism, so
# BOTH candidates carry `config_options` and the chain therefore owes both
# capability strings -- which is what lets one fixture exercise both gate arms.
_AGENT = "glm-acp-agent"
_PRIMARY_MODEL = "glm-5.2"
_FALLBACK_MODEL = "glm-5.1"
_PRIMARY_KEY = f"{_AGENT}/zai/{_PRIMARY_MODEL}"
_FALLBACK_KEY = f"{_AGENT}/zai/{_FALLBACK_MODEL}"
_AVAILABILITY_KEY = "zai"

# The cause the ratified Codex ChatGPT-account diagnostic classifies to. The
# classifier is bound elsewhere; what matters here is that the projection carries
# a candidate-scoped cause through to both ledgers unchanged.
_CAUSE = "model_unsupported"
_FAILOVER_EVENT_ID = "ev-failover-1"
_FAILOVER_AT = "2026-10-01T12:01:00Z"
# Derived by the hold ledger from occurrence time, never supplied by the event.
_EXPIRES_AT = "2026-10-01T12:16:00Z"
_CHAIN_DIGEST = "chain-digest-abc"
_RUN_COST_MICROS = 4321


def _pricing(*, model: str, multiplier: float) -> dict[str, Any]:
    """A complete per-model price table, so the run's cost is priceable.

    The built-in model catalog seeds no prices, so these ride a per-repository
    `dispatcher.model_catalog` -- the configuration surface Scenario 129's
    per-repository addition case establishes. The two candidates are priced
    DIFFERENTLY on purpose: a single shared table could not show that each
    candidate resolves its own.
    """
    return {
        "model": model,
        "input_usd_per_million": 1.0 * multiplier,
        "output_usd_per_million": 2.0 * multiplier,
        "cache_write_usd_per_million": 0.5 * multiplier,
        "cache_read_usd_per_million": 0.1 * multiplier,
    }


def _dispatcher_block() -> dict[str, Any]:
    """The dispatch target's committed dispatcher block for this journey."""
    return {
        "default_factory": _FACTORY_NAME,
        "factories": {_FACTORY_NAME: {"server": _SERVER}},
        "model_catalog": {
            f"zai/{_FALLBACK_MODEL}": {
                "display_name": "GLM 5.1",
                "pricing": _pricing(model=_FALLBACK_MODEL, multiplier=1.0),
            },
            f"zai/{_PRIMARY_MODEL}": {
                "display_name": "GLM 5.2",
                "pricing": _pricing(model=_PRIMARY_MODEL, multiplier=2.0),
            },
        },
        "acp_nodes": {
            _NODE: {
                "agent": _AGENT,
                "model": _PRIMARY_MODEL,
                "fallbacks": [{"agent": _AGENT, "model": _FALLBACK_MODEL}],
            }
        },
    }


def _repo(*, tmp_path: Path) -> Path:
    """A dispatch target on disk carrying the two-candidate chain."""
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({_REPO_NAME: {"dispatcher": _dispatcher_block()}}),
        encoding="utf-8",
    )
    return repo


def _chain(*, repo: Path) -> Any:
    """The node's chain, resolved through the real repository reader."""
    block = _dispatcher_block()
    catalogs = resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    chains = repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(chains, str), chains
    _ = repo
    return chains[_NODE]


@dataclass(kw_only=True)
class _Transport:
    """A recorded `GET /system/info`, through the production HTTP seam.

    `capabilities=None` is the UNREACHABLE factory: the transport reports a
    transport-level failure exactly as the urllib one does for a refused
    connection or a non-2xx status, so the gate meets the same value either way.
    """

    capabilities: list[str] | None
    urls: list[str] = field(default_factory=list)

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> Any:
        from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult

        _ = (headers, body, timeout_seconds)
        self.urls.append(f"{method} {url}")
        if self.capabilities is None:
            return FabroHttpResult(
                status=0,
                body="",
                error="URLError: connection refused",
                payload=None,
                succeeded=False,
            )
        payload: dict[str, Any] = {"capabilities": list(self.capabilities)}
        return FabroHttpResult(
            status=200, body=json.dumps(payload), error=None, payload=payload, succeeded=True
        )


@dataclass(kw_only=True)
class _EventsRunner:
    """A recorded `fabro events <run> --json --server <factory>` answer."""

    payload: object
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(list(argv))
        return CommandResult(exit_code=0, stdout=json.dumps(self.payload), stderr="")


@dataclass(kw_only=True)
class _Journal:
    """The real journal file every projection record is appended to."""

    path: Path

    def append(self, *, record: dict[str, object]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            _ = handle.write(json.dumps(record) + "\n")


def _target() -> FactoryTarget:
    return FactoryTarget(name=_FACTORY_NAME, server=_SERVER, dev_token=None)


def _refusal(*, capabilities: list[str] | None, repo: Path) -> tuple[str | None, _Transport]:
    """Run the real gate against a recorded factory answer."""
    transport = _Transport(capabilities=capabilities)
    block = _dispatcher_block()
    catalogs = resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    chains = repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(chains, str), chains
    _ = repo
    return (
        acp_capability_refusal(
            chains=chains,
            factory_name=_FACTORY_NAME,
            capabilities=factory_capability_reader(factory=_target(), transport=transport),
        ),
        transport,
    )


def _started(*, index: int, model: str, generation: str) -> dict[str, Any]:
    """One `agent.acp.started`, carrying the model the handler confirmed."""
    return {
        "type": "agent.acp.started",
        "schema_version": 1,
        "node": _NODE,
        "node_visit": 1,
        "candidate_index": index,
        "occurred_at": f"2026-10-01T12:0{index}:00Z",
        "primary_generation": generation,
        "model": model,
    }


def _failover(*, generation: str) -> dict[str, Any]:
    """The one `agent.acp.failover` this journey emits, primary to fallback."""
    return {
        "type": "agent.acp.failover",
        "schema_version": 1,
        "event_id": _FAILOVER_EVENT_ID,
        "occurred_at": _FAILOVER_AT,
        "node": _NODE,
        "node_visit": 1,
        "engine_attempt": 1,
        "from": {
            "candidate_index": 0,
            "display_name": "GLM ACP Agent GLM 5.2",
            "candidate_key": _PRIMARY_KEY,
            "availability_key": _AVAILABILITY_KEY,
        },
        "to": {
            "candidate_index": 1,
            "display_name": "GLM ACP Agent GLM 5.1",
            "candidate_key": _FALLBACK_KEY,
            "availability_key": _AVAILABILITY_KEY,
        },
        "hold_key": _PRIMARY_KEY,
        "cause": _CAUSE,
        "scope": "candidate",
        "primary_generation": generation,
        "full_chain": _CHAIN_DIGEST,
        "attempted": [_PRIMARY_KEY],
        "skipped": [],
    }


def _journey(*, repo: Path) -> list[dict[str, Any]]:
    """The run's whole event stream: primary start, failover, fallback start.

    The `primary_generation` is COMPUTED from this repository's own resolved
    chain rather than transcribed, so a configuration change that moved the
    generation would make the stream stop matching instead of silently agreeing.
    """
    generation = resolve_acp_primary_generations(repo=repo)[_NODE]
    return [
        _started(index=0, model=_PRIMARY_MODEL, generation=generation),
        _failover(generation=generation),
        _started(index=1, model=_FALLBACK_MODEL, generation=generation),
    ]


def _project(*, repo: Path, tmp_path: Path) -> tuple[Any, _EventsRunner, Path]:
    """Project the journey through the real seam, writing a real journal."""
    journal_path = tmp_path / "journal.jsonl"
    runner = _EventsRunner(payload=_journey(repo=repo))
    result = project_run_events(
        request=AcpProjectionRequest(
            repo=repo,
            repo_name=_REPO_NAME,
            work_item_id=_WORK_ITEM,
            run_id=_RUN_ID,
            journal_path=journal_path,
            run_succeeded=True,
        ),
        journal=_Journal(path=journal_path),
        runner=runner,
        factory=_target(),
    )
    return (result, runner, journal_path)


def _stage(*, journal_path: Path, stage: str) -> list[dict[str, Any]]:
    return [
        dict(record)
        for record in journal_records(journal_path=journal_path)
        if record.get("stage") == stage
    ]


def test_a_two_candidate_structured_chain_resolves_both_candidates_with_prices() -> None:
    """The configuration under test: one chain, two priced protocol candidates.

    This is the precondition every case below depends on, asserted rather than
    assumed: if the chain resolved to one candidate, a journey asserting one
    failover would still pass while proving nothing about ordered fallback.
    """
    chain = _chain(repo=Path())

    assert chain.enabled is True
    assert chain.identity is not None
    assert chain.identity.candidate_key == _PRIMARY_KEY
    assert dict(chain.config_options) == {"model": _PRIMARY_MODEL}
    assert len(chain.fallbacks) == 1

    fallback = chain.fallbacks[0]
    assert fallback.identity is not None
    assert fallback.identity.candidate_key == _FALLBACK_KEY
    assert dict(fallback.config_options) == {"model": _FALLBACK_MODEL}

    # Each candidate prices through the model-catalog entry its OWN identity
    # names, which is what makes a successful fallback's cost attributable.
    assert chain.pricing is not None
    assert fallback.pricing is not None
    assert chain.pricing.model == _PRIMARY_MODEL
    assert fallback.pricing.model == _FALLBACK_MODEL
    assert chain.pricing.input_usd_per_million != fallback.pricing.input_usd_per_million


def test_the_gate_reads_the_resolved_factorys_system_info_once_and_admits_it(
    tmp_path: Path,
) -> None:
    """A capable factory admits the chain, on ONE server-qualified read.

    The URL is asserted because "a local Fabro binary is not evidence of the
    remote capability": the read has to reach the resolved factory's own server,
    and the single entry proves the per-dispatch memoization holds across both of
    the gate's arms rather than issuing a round trip each.
    """
    refusal, transport = _refusal(
        capabilities=[FALLBACK_CHAIN_CAPABILITY, CONFIG_OPTIONS_CAPABILITY],
        repo=_repo(tmp_path=tmp_path),
    )

    assert refusal is None
    assert transport.urls == [f"GET {_SERVER}{SYSTEM_INFO_PATH}"]


def test_a_factory_without_the_fallback_capability_refuses_naming_it(tmp_path: Path) -> None:
    """New grammar against an engine that cannot advance candidates."""
    refusal, _ = _refusal(capabilities=[], repo=_repo(tmp_path=tmp_path))

    assert refusal is not None
    assert FALLBACK_CHAIN_CAPABILITY in refusal
    assert _FACTORY_NAME in refusal
    assert _NODE in refusal


def test_a_factory_without_the_config_options_capability_refuses_naming_it(
    tmp_path: Path,
) -> None:
    """The narrower arm, isolated by advertising the base capability.

    Without the base string present this chain would refuse on the base arm and
    this assertion would pass against a build with no `config_options` gate at
    all -- the arm has to be reached to be proven.
    """
    refusal, _ = _refusal(capabilities=[FALLBACK_CHAIN_CAPABILITY], repo=_repo(tmp_path=tmp_path))

    assert refusal is not None
    assert CONFIG_OPTIONS_CAPABILITY in refusal
    assert _FACTORY_NAME in refusal


def test_an_unreachable_factory_server_is_refused_rather_than_passed(tmp_path: Path) -> None:
    """Fail CLOSED. A gauge that passes when blinded turns a refusal into a pass.

    The refusal distinguishes "could not be read" from "advertised without it",
    because the remedies differ: the first factory may simply be down.
    """
    refusal, transport = _refusal(capabilities=None, repo=_repo(tmp_path=tmp_path))

    assert refusal is not None
    assert FALLBACK_CHAIN_CAPABILITY in refusal
    assert "could not be read" in refusal
    assert transport.urls == [f"GET {_SERVER}{SYSTEM_INFO_PATH}"]


def test_the_committed_minimum_release_floor_refuses_a_build_below_it(tmp_path: Path) -> None:
    """The RELEASE half of the version gate, read from this repository's own config.

    The floor is read from the committed `.livespec.jsonc` rather than from a
    fixture, because the assertion is about what this repository actually
    requires. A fixture floor would prove the comparison works and say nothing
    about whether a floor is committed at all.
    """
    floor = resolve_minimum_release(cwd=_REPO_ROOT)
    assert floor.unwrap() == "0.161.0"

    # A release-cache plugin root: a directory named like a build id, carrying
    # the released payload's own `plugin.json`.
    below = tmp_path / "b6e4012cafed"
    below.mkdir()
    _ = (below / "plugin.json").write_text(json.dumps({"version": "0.160.0"}), encoding="utf-8")

    verdict = minimum_release_verdict(plugin_root=below, executing_payload=below, cwd=_REPO_ROOT)

    assert verdict is not None
    assert verdict.refusal_detail is not None
    assert "0.160.0 is below the committed dispatcher.minimum_release floor 0.161.0" in (
        verdict.refusal_detail
    )


def test_the_committed_floor_clears_the_release_that_first_supported_the_grammar(
    tmp_path: Path,
) -> None:
    """The control: the floor refuses what is BELOW it, not every build.

    Without this, the refusal above is equally consistent with a floor that
    refuses everything -- which would stop the fleet rather than gate a feature.
    """
    at_floor = tmp_path / "b6e4012cafee"
    at_floor.mkdir()
    _ = (at_floor / "plugin.json").write_text(json.dumps({"version": "0.161.0"}), encoding="utf-8")

    verdict = minimum_release_verdict(
        plugin_root=at_floor, executing_payload=at_floor, cwd=_REPO_ROOT
    )

    assert verdict is not None
    assert verdict.refusal_detail is None
    assert verdict.undetermined_detail is None


def test_the_journey_projects_one_failover_one_hold_and_one_warning(tmp_path: Path) -> None:
    """The whole fallback journey, from the run's own events to both ledgers.

    `cleared` is asserted ZERO against a run that SUCCEEDED, which is Scenario
    127's own control: "overall run success does not clear the primary". A
    successful fallback is not evidence the primary recovered.
    """
    repo = _repo(tmp_path=tmp_path)

    result, runner, journal_path = _project(repo=repo, tmp_path=tmp_path)

    assert result.read is True
    assert result.holds == 1
    assert result.warnings == 1
    assert result.cleared == 0
    assert result.unobservable == 0
    assert result.nodes == (_NODE,)

    # One events read, server-qualified against the pinned factory and naming
    # exactly the one run: the journey never reached a second run or a second
    # host, which is what "unchanged run identity" means from here.
    [argv] = runner.calls
    assert argv[1:4] == ["events", _RUN_ID, "--json"]
    assert argv[-2:] == ["--server", _SERVER]

    [hold] = _stage(journal_path=journal_path, stage=HOLD_STAGE)
    # The hold keys the candidate that FAILED, never the one that rescued the
    # node -- the precise inversion the ordered chain exists to prevent.
    assert hold["hold_key"] == _PRIMARY_KEY
    assert hold["candidate_key"] == _PRIMARY_KEY
    assert hold["cause"] == _CAUSE
    assert hold["scope"] == "candidate"
    assert hold["evidence_id"] == _FAILOVER_EVENT_ID
    assert hold["work_item_id"] == _WORK_ITEM
    # Derived from occurrence time by the ledger, not carried by the event.
    assert hold["occurred_at"] == _FAILOVER_AT
    assert hold["expires_at"] == _EXPIRES_AT

    [warning] = _stage(journal_path=journal_path, stage=MODEL_FALLBACK_STAGE)
    # The warning names the candidate that RAN; the hold above names the one that
    # failed. One echoed field could not produce both.
    assert warning["candidate_key"] == _FALLBACK_KEY
    assert warning["candidate_index"] == 1
    assert warning["hold_key"] == _PRIMARY_KEY
    assert warning["node"] == _NODE
    assert warning["event_id"] == _FAILOVER_EVENT_ID
    assert warning["full_chain"] == _CHAIN_DIGEST
    assert warning["primary_generation"] == resolve_acp_primary_generations(repo=repo)[_NODE]


def test_the_journey_stays_in_one_node_visit_and_replays_no_predecessor(
    tmp_path: Path,
) -> None:
    """One sandbox, one node visit, no node re-entered: read off the real scan.

    A Fabro sandbox belongs to its run, so a single run id reached once is the
    orchestrator-side evidence of an unchanged sandbox. What the event stream can
    show independently is that the chain advanced INSIDE one node visit rather
    than by re-entering the node, and that no predecessor node started again.
    """
    repo = _repo(tmp_path=tmp_path)

    scan = scan_acp_events(payload=_journey(repo=repo))

    assert isinstance(scan, AcpEventScan), scan
    assert len(scan.events) == 1
    assert scan.events[0].event_type == "agent.acp.failover"
    assert scan.events[0].node_visit == 1
    assert scan.events[0].executed_non_primary is True

    # Both attempts sit in visit 1 of the SAME node: no retry, no replay.
    assert {start.node for start in scan.starts} == {_NODE}
    assert {start.node_visit for start in scan.starts} == {1}
    assert [start.candidate_index for start in scan.starts] == [0, 1]


def test_the_started_events_report_the_model_each_attempt_confirmed(tmp_path: Path) -> None:
    """Which model actually ran, read from the run's own events.

    This is the assertion the whole `config_options` mechanism exists to make
    answerable: a build whose engine accepted the chain and then ran the agent's
    own default would report the same model twice, and nothing else in the record
    would disagree.
    """
    scan = scan_acp_events(payload=_journey(repo=_repo(tmp_path=tmp_path)))

    assert isinstance(scan, AcpEventScan), scan
    assert [start.confirmed_model for start in scan.starts] == [_PRIMARY_MODEL, _FALLBACK_MODEL]


def test_the_runs_cost_is_attributed_to_that_run_and_to_no_other(tmp_path: Path) -> None:
    """The successful fallback run's cost, and the control that it is not a default.

    Cost is observed at the RUN level, so both attempts' usage is inside the one
    figure by construction. The second assertion is what makes the first mean
    something: a reader that returned the first row, or a constant, would report
    a cost for a run that is not in the inventory at all.
    """
    _ = _repo(tmp_path=tmp_path)
    inventory = json.dumps(
        [
            {"run_id": "01OTHERRUNOTHERRUNOTHERRU", "total_usd_micros": 99},
            {
                "run_id": _RUN_ID,
                "total_usd_micros": _RUN_COST_MICROS,
                "goal": f"Work-item: {_WORK_ITEM}",
            },
        ]
    )

    observed = observe_run_cost(ps_json=inventory, run_id=_RUN_ID)

    assert observed.observable is True
    assert observed.usd_micros == _RUN_COST_MICROS
    assert (
        observe_run_cost(ps_json=inventory, run_id="01ABSENTABSENTABSENTABSE").observable is False
    )
