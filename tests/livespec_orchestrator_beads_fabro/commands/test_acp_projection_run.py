"""Reading a run's ACP events from the DISPATCH'S OWN factory, and replaying it.

Binds the I/O half of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" -> "The Dispatcher MUST
fetch events from the run's resolved factory target ... and replay
projection during reconciliation", plus the terminal-completion trigger
in "a typed terminal failure or an idempotently projected
`agent.acp.failover` event from a run of ANY eventual outcome".

THE CONTROL THAT MATTERS MOST IS THE SERVER QUALIFICATION, and it is
asserted on the ARGV rather than on the outcome. A projection that read
the LOCAL server would produce a clean, plausible, entirely wrong
answer -- `AGENTS.md` records that exact trap, where a bare `fabro ps`
reported `No running processes found` while the dispatch was healthy on
`hp`. Nothing in the result distinguishes the two, so the test reads the
command the port actually built.

THE SECOND CONTROL IS THE NO-OP. A repository with no fallback-enabled
node must launch NO process at all -- the additive guarantee the whole
feature opens with -- so the fake runner asserts it was never called
rather than asserting the result was empty, which an implementation that
fetched and then discarded would also satisfy.

Everything is HERMETIC: repositories are built in `tmp_path`, the Fabro
port is driven through an injected runner, and nothing reaches a
factory or a tenant.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_projection_failure import (
    REASON_FETCH_FAILED,
    REASON_RUN_NOT_FOUND,
    unresolved_projection_failures,
)
from livespec_orchestrator_beads_fabro.commands._acp_projection_run import (
    AcpProjectionRequest,
    project_run_events,
    resolve_projection_factory,
)
from livespec_orchestrator_beads_fabro.commands._acp_projection_terminal import (
    PROJECTION_ERROR_STAGE,
    project_terminal_run_events,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    resolve_acp_primary_generations,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_acp_projection import (
    replay_acp_projection,
    replay_targets,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    JournaledRuns,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_orphan_runs import InertLedger

_OCCURRED = "2026-09-12T12:00:00Z"
_HP_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_VPS_SERVER = "https://vps.perch-rudd.ts.net:32276"
_RUN_ID = "01M3R750MNDHENDYKY5MBKRYXJ"

_GRAPH = """
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="a", timeout="60s"]
    gate [shape=parallelogram, timeout="60s"]
    start -> implement
    implement -> gate
    gate -> exit [label="green", condition="outcome=succeeded"]
"""

_MANIFEST = """[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "adapter-primary"
"""

_ENABLED_CONFIG: dict[str, Any] = {
    "livespec-orchestrator-beads-fabro": {
        "dispatcher": {
            "default_factory": "hp",
            "factories": {
                "hp": {"server": _HP_SERVER},
                "vps": {"server": _VPS_SERVER},
            },
            "acp_nodes": {
                "implement": {
                    "display_name": "Primary",
                    "candidate_key": "primary",
                    "availability_key": "codex",
                    "command": "adapter-primary",
                    "fallbacks": [
                        {
                            "display_name": "Fallback",
                            "candidate_key": "fallback",
                            "availability_key": "anthropic",
                            "command": "adapter-fallback",
                        }
                    ],
                }
            },
        }
    }
}


@dataclass(kw_only=True)
class _Journal:
    path: Path
    records: list[dict[str, Any]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        stamped = {"at": _OCCURRED, "invoker": "human:tester", **record}
        self.records.append(dict(stamped))
        with self.path.open("a", encoding="utf-8") as handle:
            _ = handle.write(json.dumps(stamped, sort_keys=True) + "\n")

    def staged(self, *, stage: str) -> list[dict[str, Any]]:
        return [record for record in self.records if record.get("stage") == stage]


@dataclass(kw_only=True)
class _Runner:
    """A CommandRunner that records every argv and answers with one result."""

    result: CommandResult
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
        return self.result


@dataclass(frozen=True, kw_only=True)
class _Outcome:
    work_item_id: str
    status: str
    fabro_run_id: str | None


def _failover_payload() -> list[dict[str, Any]]:
    return [
        {
            "type": "agent.acp.failover",
            "schema_version": 1,
            "event_id": "ev-1",
            "occurred_at": _OCCURRED,
            "node": "implement",
            "node_visit": 1,
            "engine_attempt": 1,
            "from": {
                "candidate_index": 0,
                "display_name": "Primary",
                "candidate_key": "primary",
                "availability_key": "codex",
            },
            "to": {
                "candidate_index": 1,
                "display_name": "Fallback",
                "candidate_key": "fallback",
                "availability_key": "anthropic",
            },
            "hold_key": "codex",
            "cause": "quota",
            "scope": "availability-domain",
            "primary_generation": "gen-a",
            "full_chain": "chain-1",
        }
    ]


def _repo(*, tmp_path: Path, config: dict[str, Any] | None = None) -> Path:
    workflow = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(_MANIFEST, encoding="utf-8")
    (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(_ENABLED_CONFIG if config is None else config), encoding="utf-8"
    )
    (tmp_path / "tmp").mkdir()
    return tmp_path


def _request(*, repo: Path, run_succeeded: bool = False) -> AcpProjectionRequest:
    return AcpProjectionRequest(
        repo=repo,
        repo_name=repo.name,
        work_item_id="bd-ib-xtgwpz",
        run_id=_RUN_ID,
        journal_path=repo / "tmp" / "fabro-dispatch-journal.jsonl",
        run_succeeded=run_succeeded,
    )


def _journal(*, repo: Path) -> _Journal:
    return _Journal(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")


def _ok(*, payload: object) -> CommandResult:
    return CommandResult(exit_code=0, stdout=json.dumps(payload), stderr="")


def test_the_resolved_generations_name_every_fallback_enabled_node(tmp_path: Path) -> None:
    """One resolution answers BOTH the fact's node set and the supersede compare."""
    assert resolve_acp_primary_generations(repo=_repo(tmp_path=tmp_path)).keys() == {"implement"}


def test_a_repository_with_no_fallback_metadata_resolves_no_generations(
    tmp_path: Path,
) -> None:
    """The v107 path: no enabled node, so nothing to project and nothing to compare."""
    repo = _repo(tmp_path=tmp_path, config={"livespec-orchestrator-beads-fabro": {}})
    assert resolve_acp_primary_generations(repo=repo) == {}


def test_a_configuration_that_will_not_resolve_yields_no_generations(
    tmp_path: Path,
) -> None:
    """Fail-SOFT after the run: refusing here would strand the evidence.

    Both refusal layers are exercised, because they fail on different
    reads and an implementation could fail soft on one while raising on
    the other: the chain GRAMMAR refuses an unknown key, and the chain
    RESOLUTION refuses a node the workflow declares no adapter input for.
    """
    broken = json.loads(json.dumps(_ENABLED_CONFIG))
    broken["livespec-orchestrator-beads-fabro"]["dispatcher"]["acp_nodes"]["implement"][
        "unknown_key"
    ] = "boom"
    assert resolve_acp_primary_generations(repo=_repo(tmp_path=tmp_path, config=broken)) == {}
    unresolvable = json.loads(json.dumps(_ENABLED_CONFIG))
    nodes = unresolvable["livespec-orchestrator-beads-fabro"]["dispatcher"]["acp_nodes"]
    nodes["review"] = nodes.pop("implement")
    second = tmp_path / "second"
    second.mkdir()
    assert resolve_acp_primary_generations(repo=_repo(tmp_path=second, config=unresolvable)) == {}


def test_the_events_read_is_server_qualified_against_the_resolved_factory(
    tmp_path: Path,
) -> None:
    """The argv, not the result: a local read would look exactly as healthy."""
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    runner = _Runner(result=_ok(payload=_failover_payload()))
    result = project_run_events(request=_request(repo=repo), journal=journal, runner=runner)
    assert result.holds == 1
    assert len(runner.calls) == 1
    assert runner.calls[0][1:] == ["events", _RUN_ID, "--json", "--server", _HP_SERVER]
    assert journal.staged(stage="acp-projection-succeeded")


def test_a_caller_supplied_factory_wins_so_a_replay_reads_the_right_host(
    tmp_path: Path,
) -> None:
    """Reconciliation is already on one factory; re-resolving could switch hosts."""
    repo = _repo(tmp_path=tmp_path)
    runner = _Runner(result=_ok(payload=[]))
    _ = project_run_events(
        request=_request(repo=repo),
        journal=_journal(repo=repo),
        runner=runner,
        factory=FactoryTarget(name="vps", server=_VPS_SERVER, dev_token=None),
    )
    assert runner.calls[0][-2:] == ["--server", _VPS_SERVER]


def test_a_repository_with_no_fallback_enabled_node_launches_no_process(
    tmp_path: Path,
) -> None:
    """The additive no-op, asserted on the RUNNER rather than on the result."""
    repo = _repo(tmp_path=tmp_path, config={"livespec-orchestrator-beads-fabro": {}})
    journal = _journal(repo=repo)
    runner = _Runner(result=_ok(payload=[]))
    result = project_run_events(request=_request(repo=repo), journal=journal, runner=runner)
    assert (runner.calls, journal.records, result.nodes) == ([], [], ())


def test_an_unresolvable_factory_is_recorded_as_an_unread_stream(tmp_path: Path) -> None:
    """No server to ask is not the same as nothing to read."""
    no_factories = json.loads(json.dumps(_ENABLED_CONFIG))
    del no_factories["livespec-orchestrator-beads-fabro"]["dispatcher"]["factories"]
    del no_factories["livespec-orchestrator-beads-fabro"]["dispatcher"]["default_factory"]
    repo = _repo(tmp_path=tmp_path, config=no_factories)
    assert resolve_projection_factory(repo=repo, work_item_id="bd-ib-xtgwpz") is None
    journal = _journal(repo=repo)
    runner = _Runner(result=_ok(payload=[]))
    result = project_run_events(request=_request(repo=repo), journal=journal, runner=runner)
    assert result.reason == REASON_FETCH_FAILED
    assert runner.calls == []
    unresolved = unresolved_projection_failures(journal_path=journal.path)
    assert unresolved[0].factory_name == "unresolved"


def test_a_factory_that_forgot_the_run_records_a_run_not_found_failure(
    tmp_path: Path,
) -> None:
    """Run absence is a failure arm, and it never resolves the fact."""
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    runner = _Runner(
        result=CommandResult(exit_code=1, stdout="", stderr=f"run {_RUN_ID} not found")
    )
    result = project_run_events(request=_request(repo=repo), journal=journal, runner=runner)
    assert result.reason == REASON_RUN_NOT_FOUND
    failure = journal.staged(stage="acp-projection-failure")[0]
    # Leak-free: the typed token is recorded, the adapter's sentence is not.
    assert failure["reason"] == REASON_RUN_NOT_FOUND
    assert "not found" not in json.dumps(failure)


def test_a_terminal_dispatch_projects_its_run_whatever_the_outcome_was(
    tmp_path: Path,
) -> None:
    """A run that failed later still observed the outage that made it fall back."""
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    runner = _Runner(result=_ok(payload=_failover_payload()))
    result = project_terminal_run_events(
        outcome=_Outcome(work_item_id="bd-ib-xtgwpz", status="failed", fabro_run_id=_RUN_ID),
        repo=repo,
        journal=journal,
        runner=runner,
    )
    assert (result.holds, result.warnings, result.cleared) == (1, 1, 0)


def test_a_terminal_that_created_no_run_raises_no_projection_fact(tmp_path: Path) -> None:
    """A dispatch that never reached a factory has no event stream to be unread."""
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    runner = _Runner(result=_ok(payload=[]))
    result = project_terminal_run_events(
        outcome=_Outcome(work_item_id="bd-ib-xtgwpz", status="failed", fabro_run_id=None),
        repo=repo,
        journal=journal,
        runner=runner,
    )
    assert (result.nodes, runner.calls, journal.records) == ((), [], [])


def test_a_projection_that_raises_is_absorbed_into_a_journal_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hook never fails the terminal it is reporting."""
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)

    def _explode(**_kwargs: object) -> None:
        raise OSError("the journal volume went away")

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._acp_projection_terminal.project_run_events",
        _explode,
    )
    result = project_terminal_run_events(
        outcome=_Outcome(work_item_id="bd-ib-xtgwpz", status="green", fabro_run_id=_RUN_ID),
        repo=repo,
        journal=journal,
    )
    assert result.nodes == ()
    error = journal.staged(stage=PROJECTION_ERROR_STAGE)[0]
    assert error["reason"] == "OSError"
    # Leak-free: the exception TYPE is recorded, never its message.
    assert "volume went away" not in json.dumps(error)


def _reconcile_inputs(*, repo: Path, journal: _Journal, runner: _Runner) -> ReconcileInputs:
    return ReconcileInputs(
        repo=repo,
        fabro_bin="fabro",
        id_prefix="bd-ib",
        items=(),
        journaled=JournaledRuns(
            newest_run_id_by_item={"bd-ib-xtgwpz": _RUN_ID},
            item_id_by_run={_RUN_ID: "bd-ib-xtgwpz"},
        ),
        runner=runner,
        journal=journal,
        ledger=InertLedger(),
    )


def test_reconciliation_replays_exactly_the_runs_that_still_owe_a_projection(
    tmp_path: Path,
) -> None:
    """The replay set is the unresolved failures, not the whole inventory."""
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    failing = _Runner(result=CommandResult(exit_code=1, stdout="", stderr="unreachable"))
    _ = project_run_events(request=_request(repo=repo), journal=journal, runner=failing)
    assert unresolved_projection_failures(journal_path=journal.path)
    healthy = _Runner(result=_ok(payload=_failover_payload()))
    inputs = _reconcile_inputs(repo=repo, journal=journal, runner=healthy)
    hp = FactoryTarget(name="hp", server=_HP_SERVER, dev_token=None)
    assert replay_targets(inputs=inputs, factory=hp, journal_path=journal.path) == (
        (_RUN_ID, "bd-ib-xtgwpz"),
    )
    assert replay_acp_projection(inputs=inputs, factory=hp) == 1
    assert healthy.calls[0][-2:] == ["--server", _HP_SERVER]
    # The replay succeeded, so the fact it was replaying is resolved.
    assert unresolved_projection_failures(journal_path=journal.path) == ()


def test_a_replay_skips_another_factorys_failures_and_unattributed_runs(
    tmp_path: Path,
) -> None:
    """A failure on `vps` is not `hp`'s to re-read, and a nameless run is nobody's."""
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    failing = _Runner(result=CommandResult(exit_code=1, stdout="", stderr="unreachable"))
    _ = project_run_events(
        request=_request(repo=repo),
        journal=journal,
        runner=failing,
        factory=FactoryTarget(name="vps", server=_VPS_SERVER, dev_token=None),
    )
    healthy = _Runner(result=_ok(payload=[]))
    inputs = ReconcileInputs(
        repo=repo,
        fabro_bin="fabro",
        id_prefix="bd-ib",
        items=(),
        journaled=JournaledRuns(newest_run_id_by_item={}, item_id_by_run={}),
        runner=healthy,
        journal=journal,
        ledger=InertLedger(),
    )
    hp = FactoryTarget(name="hp", server=_HP_SERVER, dev_token=None)
    assert replay_acp_projection(inputs=inputs, factory=hp) == 0
    vps = FactoryTarget(name="vps", server=_VPS_SERVER, dev_token=None)
    # Right factory, but the run is journaled to no work-item, so it is skipped
    # rather than replayed under a guessed id.
    assert replay_acp_projection(inputs=inputs, factory=vps) == 0
    assert healthy.calls == []


def test_a_targeted_reconciliation_replays_its_own_items_newest_run(
    tmp_path: Path,
) -> None:
    """A per-item recovery repairs that item's projection in the same pass."""
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    healthy = _Runner(result=_ok(payload=[]))
    inputs = ReconcileInputs(
        repo=repo,
        fabro_bin="fabro",
        id_prefix="bd-ib",
        items=(),
        journaled=JournaledRuns(
            newest_run_id_by_item={"bd-ib-xtgwpz": _RUN_ID},
            item_id_by_run={_RUN_ID: "bd-ib-xtgwpz"},
        ),
        runner=healthy,
        journal=journal,
        ledger=InertLedger(),
        only_work_item_id="bd-ib-xtgwpz",
    )
    hp = FactoryTarget(name="hp", server=_HP_SERVER, dev_token=None)
    assert replay_acp_projection(inputs=inputs, factory=hp) == 1
    assert journal.staged(stage="acp-projection-succeeded")


def test_a_targeted_reconciliation_of_an_item_with_no_run_replays_nothing(
    tmp_path: Path,
) -> None:
    """An item that never dispatched has no run to re-read."""
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    healthy = _Runner(result=_ok(payload=[]))
    inputs = ReconcileInputs(
        repo=repo,
        fabro_bin="fabro",
        id_prefix="bd-ib",
        items=(),
        journaled=JournaledRuns(newest_run_id_by_item={}, item_id_by_run={}),
        runner=healthy,
        journal=journal,
        ledger=InertLedger(),
        only_work_item_id="bd-ib-never",
    )
    assert (
        replay_acp_projection(
            inputs=inputs, factory=FactoryTarget(name="hp", server=_HP_SERVER, dev_token=None)
        )
        == 0
    )
