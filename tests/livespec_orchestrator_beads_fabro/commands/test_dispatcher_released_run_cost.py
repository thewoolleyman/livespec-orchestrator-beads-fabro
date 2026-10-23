"""A provider-limit-released run is costed, on its own factory, exactly once.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt": "For every run released under
'Provider-limit release and re-dispatch' ... the Dispatcher MUST journal one
attempt-cost record carrying the attempt's token use and elapsed time per node
attempt wherever the run record exposes them, priced under the rules below, or
marked cost-unobservable."

THE READS ARE ASSERTED SERVER-QUALIFIED, which is the trap `AGENTS.md`
catalogues and the one this reading is most exposed to. A bare `fabro events`
or `fabro ps` answers for the LOCAL server, where a run dispatched to `hp` does
not exist -- a clean, plausible, wrong answer with no error, which here would
report every released run as exposing no attempt and costing nothing. So the
argv of every call is checked for the release's own factory address.

EVERY UNREADABLE ARM STILL YIELDS A RECORD, and that is the direction the
clause fixes: "or marked cost-unobservable". A reading that returned nothing
would leave the released attempt with no observation at all, which reads
downstream as an attempt nobody spent anything on -- while the sequence fold
cannot tell a missing record from a run that cost nothing.

THE APPEND IS ASSERTED ONCE PER RELEASE AND NOT ONCE PER PASS. The release
record is withheld on a replay because a plain append is the one step that is
not idempotent, and the cost observation rides the same reading for the same
reason: "Each run or probe cost observation ... MUST be counted at most once
across reconciliation and resume".
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidateIdentity
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    AcpAvailabilityFailure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_attempts import (
    ATTEMPT_COST_RELEASED_RUN,
    ATTEMPT_COST_STAGE,
    attempt_cost_identity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    ProviderLimitRelease,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_disposition import (
    dispose_provider_limit_release,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "_dispatcher_released_run_cost"
_MODULE_PATH = _COMMANDS / f"{_MODULE}.py"

_BASE = datetime(2026, 10, 12, 9, 0, 0, tzinfo=timezone.utc)
_ITEM_ID = "bd-ib-plcost"
_RUN = "01M52R2WND7Y"
_NOW = "2026-10-16T19:20:00Z"
_FACTORY = "hp"
_SERVER = "https://hp-xubuntu.example:32276"
_NODE_ATTEMPT = "implement"
_IDENTITY = AcpCandidateIdentity(
    display_name="Claude ACP primary",
    candidate_key="claude-primary",
    availability_key="anthropic-team",
)


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    """The hermetic in-memory tenant, flipped on through its one env seam."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _ScriptedRunner:
    """A runner answering `fabro events` and `fabro ps` from two fixtures."""

    events_stdout: str = "[]"
    events_exit_code: int = 0
    ps_stdout: str = "[]"
    ps_exit_code: int = 0
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        del cwd, timeout_seconds
        self.calls.append(argv)
        if "events" in argv:
            return CommandResult(
                exit_code=self.events_exit_code, stdout=self.events_stdout, stderr=""
            )
        return CommandResult(exit_code=self.ps_exit_code, stdout=self.ps_stdout, stderr="")


def _module() -> Any:
    """The released-run reading, through an in-body import.

    In-body so this file's FIRST failing assertion is a genuine check on the
    committed file rather than a collection error.
    """
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    return importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{_MODULE}")


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path, declare_server: bool = True) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    factories: dict[str, object] = (
        {_FACTORY: {"server": _SERVER}} if declare_server else {_FACTORY: {}}
    )
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {"factories": factories},
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _instant(*, offset_ms: int) -> str:
    return (_BASE + timedelta(milliseconds=offset_ms)).isoformat().replace("+00:00", "Z")


def _events_payload() -> str:
    """Two attempts of one node visit, the first with a measured duration."""
    return json.dumps(
        [
            {
                "type": "agent.acp.started",
                "node": _NODE_ATTEMPT,
                "node_visit": 1,
                "candidate_index": 0,
                "occurred_at": _instant(offset_ms=0),
                "primary_generation": "gen-a",
            },
            {
                "type": "agent.acp.failover",
                "schema_version": 1,
                "event_id": "ev-1",
                "occurred_at": _instant(offset_ms=0),
                "node": _NODE_ATTEMPT,
                "node_visit": 1,
                "engine_attempt": 1,
                "from": {
                    "candidate_index": 0,
                    "display_name": "primary",
                    "candidate_key": "claude-primary",
                    "availability_key": "anthropic-team",
                },
                "to": {
                    "candidate_index": 1,
                    "display_name": "fallback",
                    "candidate_key": "codex-fallback",
                    "availability_key": "codex",
                },
                "hold_key": "anthropic-team",
                "cause": "quota",
                "scope": "availability-domain",
                "primary_generation": "gen-a",
                "full_chain": "chain-1",
                "attempted_durations_ms": [90_000],
            },
            {
                "type": "agent.acp.started",
                "node": _NODE_ATTEMPT,
                "node_visit": 1,
                "candidate_index": 1,
                "occurred_at": _instant(offset_ms=95_000),
                "primary_generation": "gen-a",
            },
        ]
    )


def _ps_payload(*, total_usd_micros: int | None, run_id: str = _RUN) -> str:
    return json.dumps(
        [
            {
                "run_id": run_id,
                "status": {"kind": "failed"},
                "goal": f"Work-item `{_ITEM_ID}`",
                "total_usd_micros": total_usd_micros,
            }
        ]
    )


def _release(*, run_id: str | None = _RUN) -> ProviderLimitRelease:
    return ProviderLimitRelease(
        factory=_FACTORY,
        run_id=run_id,
        node_attempt=_NODE_ATTEMPT,
        matched=AcpAvailabilityFailure(
            cause="quota",
            scope="availability-domain",
            hold_key="anthropic-team",
            availability_key="anthropic-team",
            candidate_key=None,
            source="protocol.message",
        ),
        executed=_IDENTITY,
        legacy_provider=None,
        recovery_source=f"the tree was preserved on refs/heads/needs-human/{_RUN}",
    )


def _record(
    *,
    tmp_path: Path,
    runner: _ScriptedRunner | None = None,
    release: ProviderLimitRelease | None = None,
    declare_server: bool = True,
) -> dict[str, object]:
    module = _module()
    return module.released_run_attempt_cost_record(  # pyright: ignore[reportAttributeAccessIssue]
        repo=_repo(tmp_path=tmp_path, declare_server=declare_server),
        work_item_id=_ITEM_ID,
        release=_release() if release is None else release,
        occurred_at=_NOW,
        runner=_ScriptedRunner() if runner is None else runner,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="A dispatched slice whose provider ceiling ended the run",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _journal(*, tmp_path: Path, lines: tuple[str, ...] = ()) -> JournalFile:
    path = tmp_path / "journal.jsonl"
    _ = path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return JournalFile(path=path)


def _records(*, journal: JournalFile, stage: str) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for line in journal.path.read_text(encoding="utf-8").splitlines():
        parsed: dict[str, object] = json.loads(line)
        if parsed.get("stage") == stage:
            found.append(parsed)
    return found


def _dispose(
    *,
    tmp_path: Path,
    journal: JournalFile,
    item: WorkItem,
    builder: object,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=item)
    dispose_provider_limit_release(
        repo=repo,
        item=item,
        outcome=DispatchOutcome(
            work_item_id=_ITEM_ID,
            status="provider-limit-release",
            stage="provider-limit-release",
            pr_number=None,
            merge_sha=None,
            detail="",
            fabro_run_id=_RUN,
            provider_limit_release=_release(),
        ),
        journal=journal,
        now_iso=_NOW,
        attempt_cost_of=builder,  # pyright: ignore[reportArgumentType]
    )


def _stub_builder() -> Any:
    """A record builder that reaches nothing, so the APPEND is what is tested."""

    def build(
        *,
        repo: Path,
        work_item_id: str,
        release: ProviderLimitRelease,
        occurred_at: str,
    ) -> dict[str, object]:
        del repo
        return {
            "stage": ATTEMPT_COST_STAGE,
            "observation_id": attempt_cost_identity(
                source=ATTEMPT_COST_RELEASED_RUN,
                factory=release.factory,
                run_id=release.run_id,
                node_attempt=release.node_attempt,
            ),
            "work_item_id": work_item_id,
            "occurred_at": occurred_at,
        }

    return build


@dataclass(frozen=True, kw_only=True)
class _UnreadableArm:
    """One way part of the released run's own record cannot be read.

    A case object rather than parametrized scalars, because several of them are
    booleans and a boolean parameter position says nothing about which question
    it answers.

    The two reads fail INDEPENDENTLY and the expectations are stated per arm
    rather than collapsed, which is the whole point of exercising them apart: a
    refused event stream leaves the engine's own whole-run figure perfectly
    readable, so darkening the cost there would report a measured charge as
    unobservable, while a refused `ps` leaves the attempts readable and only
    the price dark.
    """

    events_exit_code: int = 0
    ps_exit_code: int = 0
    run_id: str | None = _RUN
    declare_server: bool = True
    expect_calls: bool = True
    expect_usd_micros: int | None = None
    expect_attempt_count: int = 0


def test_the_released_run_reading_exists() -> None:
    """The one entry point this release's cost observation is built through."""
    module = _module()
    assert hasattr(module, "released_run_attempt_cost_record"), dir(module)


def test_the_record_carries_the_runs_own_attempts_and_the_engines_figure(
    tmp_path: Path,
) -> None:
    """Per-attempt elapsed from the event stream, the price from `ps`."""
    runner = _ScriptedRunner(
        events_stdout=_events_payload(), ps_stdout=_ps_payload(total_usd_micros=7_400)
    )
    record = _record(tmp_path=tmp_path, runner=runner)
    assert record["stage"] == ATTEMPT_COST_STAGE
    assert record["source"] == ATTEMPT_COST_RELEASED_RUN
    assert record["work_item_id"] == _ITEM_ID
    assert record["node_attempt"] == _NODE_ATTEMPT
    assert record["observation_id"] == attempt_cost_identity(
        source=ATTEMPT_COST_RELEASED_RUN,
        factory=_FACTORY,
        run_id=_RUN,
        node_attempt=_NODE_ATTEMPT,
    )
    attempts = record["attempts"]
    assert isinstance(attempts, list)
    assert [one["candidate_index"] for one in attempts] == [0, 1]
    assert [one["elapsed_ms"] for one in attempts] == [90_000, None]
    assert record["usd_micros"] == 7_400
    assert record["cost_observable"] is True


def test_both_reads_name_the_releases_own_factory(tmp_path: Path) -> None:
    """Server-qualified, per the module docstring: a bare read answers locally."""
    runner = _ScriptedRunner(
        events_stdout=_events_payload(), ps_stdout=_ps_payload(total_usd_micros=1)
    )
    _ = _record(tmp_path=tmp_path, runner=runner)
    verbs = {argv[1] for argv in runner.calls}
    assert verbs == {"events", "ps"}, runner.calls
    for argv in runner.calls:
        assert _SERVER in argv, argv


def test_another_repositorys_row_never_supplies_this_runs_figure(tmp_path: Path) -> None:
    """A factory serves every repository on its host, so the match is by run id.

    The listing below carries one well-formed figure belonging to somebody
    else's dispatch. Reading the head of the list would report it as this
    release's cost -- a plausible number for the wrong run, which no later
    reader could tell from a measurement.
    """
    runner = _ScriptedRunner(
        events_stdout=_events_payload(),
        ps_stdout=_ps_payload(total_usd_micros=31_400, run_id="01SOMEONEELSESRUN"),
    )
    record = _record(tmp_path=tmp_path, runner=runner)
    assert record["usd_micros"] is None
    assert record["cost_observable"] is False


def test_a_null_engine_figure_marks_the_release_cost_unobservable(tmp_path: Path) -> None:
    """The ORDINARY answer on this fleet, stated rather than inferred."""
    runner = _ScriptedRunner(
        events_stdout=_events_payload(), ps_stdout=_ps_payload(total_usd_micros=None)
    )
    record = _record(tmp_path=tmp_path, runner=runner)
    assert record["usd_micros"] is None
    assert record["cost_observable"] is False
    attempts = record["attempts"]
    assert isinstance(attempts, list)
    assert len(attempts) == 2


@pytest.mark.parametrize(
    "arm",
    [
        pytest.param(
            _UnreadableArm(events_exit_code=1, expect_usd_micros=9_100), id="events-refused"
        ),
        pytest.param(_UnreadableArm(ps_exit_code=1, expect_attempt_count=2), id="ps-refused"),
        pytest.param(_UnreadableArm(run_id=None, expect_calls=False), id="no-run-id"),
        pytest.param(
            _UnreadableArm(declare_server=False, expect_calls=False), id="no-declared-server"
        ),
    ],
)
def test_every_unreadable_arm_still_yields_a_record_of_what_it_could_read(
    tmp_path: Path, arm: _UnreadableArm
) -> None:
    """A record is owed for EVERY released run; absence is not an option."""
    runner = _ScriptedRunner(
        events_stdout=_events_payload(),
        events_exit_code=arm.events_exit_code,
        ps_stdout=_ps_payload(total_usd_micros=9_100),
        ps_exit_code=arm.ps_exit_code,
    )
    record = _record(
        tmp_path=tmp_path,
        runner=runner,
        release=_release(run_id=arm.run_id),
        declare_server=arm.declare_server,
    )
    attempts = record["attempts"]
    assert isinstance(attempts, list)
    assert record["stage"] == ATTEMPT_COST_STAGE
    assert record["usd_micros"] == arm.expect_usd_micros
    assert record["cost_observable"] is (arm.expect_usd_micros is not None)
    assert len(attempts) == arm.expect_attempt_count
    assert bool(runner.calls) is arm.expect_calls, runner.calls


def test_the_disposition_appends_exactly_one_attempt_cost_row(tmp_path: Path) -> None:
    """One release, one observation -- beside the release row itself."""
    journal = _journal(tmp_path=tmp_path)
    _dispose(tmp_path=tmp_path, journal=journal, item=_item(), builder=_stub_builder())
    rows = _records(journal=journal, stage=ATTEMPT_COST_STAGE)
    assert len(rows) == 1, rows
    assert rows[0]["work_item_id"] == _ITEM_ID
    assert rows[0]["occurred_at"] == _NOW
    assert len(_records(journal=journal, stage="provider-limit-release")) == 1


def test_a_replay_of_one_release_appends_no_second_observation(tmp_path: Path) -> None:
    """The cost observation rides the release record's own once-only reading."""
    journal = _journal(tmp_path=tmp_path)
    _dispose(tmp_path=tmp_path, journal=journal, item=_item(), builder=_stub_builder())
    _dispose(
        tmp_path=tmp_path,
        journal=journal,
        item=_item(status="active", assignee="fabro"),
        builder=_stub_builder(),
    )
    assert len(_records(journal=journal, stage=ATTEMPT_COST_STAGE)) == 1
