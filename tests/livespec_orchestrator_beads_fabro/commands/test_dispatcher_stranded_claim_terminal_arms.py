"""The terminal-completion arms the two headline cases cannot reach.

`test_dispatcher_stranded_claim_terminal.py` asserts the provider-limit
release and the ordinary needs-human rest end to end. These are the arms that
file cannot reach without breaking the thing it measures: a run whose record
will not read at all, a run that SUCCEEDED, a watchdog cancellation, a failure
that never reached the needs-human terminal, and a row whose state cannot be
re-read before the rest.

TWO OF THEM ARE SCENARIO 196'S OWN SUB-SCENARIOS rather than mere coverage.
The watchdog case is "A first-stall cancel with no live owner is completed as a
first-stall release", and it is the one disposition no `fabro inspect` payload
can carry: the watchdog's terminal status is STAMPED by the Dispatcher after it
removes the run, so the cancel row the Dispatcher journalled is the only honest
evidence. And the unreadable-record case is `terminal-evidence-unavailable`,
which must be a HOLD rather than a verdict — an unreadable failure says nothing
about whether any release route claims it.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    NEEDS_HUMAN_CAUSE_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NEEDS_HUMAN_MARKER
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_disposition import (
    STALL_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_SURVEY = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey"
_TERMINAL = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_terminal"
_RECOVERY = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_recovery"

_ITEM_ID = "bd-ib-strandarm"
_RUN_ID = "01TERMINALARMRUN"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"
_HOST = "owning-host"
_NOW = "2026-10-18T09:00:00Z"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A slice whose run ended unobserved",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _seed(*, item: WorkItem) -> None:
    append_work_item(path=_config(), item=item)
    record_claim_stamp(
        path=_config(),
        work_item_id=item.id,
        stamp=ClaimStamp(
            dispatch_id="01DISPATCH",
            dispatching_host=_HOST,
            run_id=_RUN_ID,
            factory_name=_FACTORY,
            factory_server=_SERVER,
        ),
    )


def _journal(*, repo: Path, rows: tuple[dict[str, object], ...] = ()) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    seeded: tuple[dict[str, object], ...] = (
        {"stage": "dispatch-id", "work_item_id": _ITEM_ID},
        *rows,
    )
    _ = path.write_text("".join(json.dumps(row) + "\n" for row in seeded), encoding="utf-8")
    return JournalFile(path=path)


def _payload(*, status: str, message: str) -> list[dict[str, Any]]:
    return [
        {
            "run_id": _RUN_ID,
            "status": {"kind": status, "reason": "workflow_error"},
            "checkpoint": {
                "current_node": "implement",
                "next_node_id": None,
                "completed_nodes": [],
                "node_outcomes": {"implement": {"status": status}},
            },
            "conclusion": {
                "status": status,
                "timestamp": "2026-10-18T08:00:00Z",
                "failure": {
                    "reason": "workflow_error",
                    "detail": {"message": message, "category": "transient_infra"},
                },
            },
        }
    ]


class _Runner:
    """A fake `fabro`/`gh` seam with a scriptable `inspect` answer."""

    def __init__(self, *, stdout: str, exit_code: int = 0) -> None:
        self.stdout = stdout
        self.exit_code = exit_code

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
        if argv[0] != "gh" and argv[1] == "inspect":
            return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr="")
        return CommandResult(exit_code=0, stdout="[]", stderr="")


def _survey(*, repo: Path, item: WorkItem, journal: JournalFile, runner: _Runner) -> object:
    module = importlib.import_module(_SURVEY)
    return module.survey_stranded_claims(
        inputs=module.StrandedClaimInputs(
            repo=repo,
            items=(item,),
            journal=journal,
            runner=runner,
            inventories=(
                module.FactoryInventory(
                    name=_FACTORY,
                    server_url=_SERVER,
                    fabro_bin="fabro",
                    surveyed=True,
                    status_kinds={_RUN_ID: "failed"},
                ),
            ),
            this_host=_HOST,
            now_iso=_NOW,
        )
    )


def _stages(*, journal: JournalFile) -> list[object]:
    return [
        json.loads(line).get("stage")
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    ]


@pytest.mark.parametrize(
    ("stdout", "exit_code"),
    [
        ("", 7),
        ("not json", 0),
    ],
)
def test_a_record_that_will_not_read_holds_rather_than_deciding(
    *, tmp_path: Path, stdout: str, exit_code: int
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)

    survey = _survey(
        repo=repo, item=item, journal=journal, runner=_Runner(stdout=stdout, exit_code=exit_code)
    )

    assert [held.hold_reason for held in survey.held] == ["terminal-evidence-unavailable"]
    assert next(iter(read_work_items(path=_config()))).status == "active"


def test_a_run_the_record_reports_succeeded_holds_rather_than_completing(
    tmp_path: Path,
) -> None:
    """The listing said failed and the record says succeeded: no outcome to apply.

    The two readings disagree, which can only mean the run ended between them.
    Nothing here may act on the stale half.
    """
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)
    runner = _Runner(stdout=json.dumps(_payload(status="succeeded", message="done")))

    survey = _survey(repo=repo, item=item, journal=journal, runner=runner)

    assert [held.hold_reason for held in survey.held] == ["terminal-evidence-unavailable"]


def test_a_watchdog_cancellation_is_completed_as_a_first_stall_release(
    tmp_path: Path,
) -> None:
    """Scenario 196's first-stall arm, keyed on the Dispatcher's own cancel row."""
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(
        repo=repo,
        rows=(
            {
                "stage": "watchdog-stall-cancel",
                "work_item_id": _ITEM_ID,
                "run_id": _RUN_ID,
                "factory": _FACTORY,
                "executing_stage": "implement",
            },
        ),
    )
    runner = _Runner(
        stdout=json.dumps(_payload(status="failed", message="no progress for a long time"))
    )

    survey = _survey(repo=repo, item=item, journal=journal, runner=runner)

    assert survey.held == ()
    released = next(iter(read_work_items(path=_config())))
    assert (released.status, released.assignee) == ("ready", None)
    # The WATCHDOG'S own release record, not one this subsection invented.
    assert STALL_RELEASE_STAGE in _stages(journal=journal)


def test_a_failure_that_never_reached_the_needs_human_terminal_still_rests(
    tmp_path: Path,
) -> None:
    """The final arm: a plain `failed` outcome no release route claims.

    It carries no needs-human marker, so the Dispatcher's own escalation
    declines it and every release route declines it too — which before this
    clause left the item `active` with no run behind it forever.
    """
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)
    runner = _Runner(
        stdout=json.dumps(_payload(status="failed", message="the sandbox vanished mid-run"))
    )

    survey = _survey(repo=repo, item=item, journal=journal, runner=runner)

    assert survey.held == ()
    rested = next(iter(read_work_items(path=_config())))
    assert (rested.status, rested.blocked_reason) == ("blocked", "needs-human")
    bodies = [
        comment.text
        for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
        if comment.text.startswith(NEEDS_HUMAN_CAUSE_MARKER)
    ]
    assert len(bodies) == 1
    assert _RUN_ID in bodies[0]


def test_a_row_whose_state_cannot_be_re_read_withholds_the_rest(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resting an unreadable row could overwrite a disposition already landed."""
    terminal = importlib.import_module(_TERMINAL)
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)
    runner = _Runner(
        stdout=json.dumps(_payload(status="failed", message="the sandbox vanished mid-run"))
    )

    def _refuse(*, path: StoreConfig, work_item_id: str) -> object:
        _ = (path, work_item_id)
        raise BeadsCommandError(command="bd show", exit_code=1, stderr="refused")

    monkeypatch.setattr(terminal, "claim_row_for", _refuse)

    survey = _survey(repo=repo, item=item, journal=journal, runner=runner)

    assert [recovered.route for recovered in survey.recovered] == ["terminal-run-completion"]
    assert [recovered.effects_written for recovered in survey.recovered] == [
        ("journal-record", terminal.EFFECT_TERMINAL_ROUTING)
    ]
    # Untouched: the rest was withheld rather than written blind.
    assert next(iter(read_work_items(path=_config()))).status == "active"


def test_a_terminal_route_with_no_observation_is_held(tmp_path: Path) -> None:
    """The recovery refuses to act on a terminal reading it was not given."""
    recovery = importlib.import_module(_RECOVERY)
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)

    outcome = recovery.recover_claim(
        repo=repo,
        journal=journal,
        request=recovery.ClaimRecoveryRequest(
            item=item,
            run_id=_RUN_ID,
            factory_name=_FACTORY,
            factory_server_url=_SERVER,
            action="terminal-run-completion",
            terminal=None,
        ),
        now_iso=_NOW,
    )

    assert outcome.hold_reason == "effect-unobservable"
    assert _stages(journal=journal) == ["dispatch-id"]
    assert next(iter(read_work_items(path=_config()))).status == "active"


def test_the_terminal_record_reports_the_observed_status_as_its_reason(
    tmp_path: Path,
) -> None:
    """The row restates no disposition it did not decide."""
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)
    runner = _Runner(
        stdout=json.dumps(
            _payload(
                status="failed",
                message=f"a fault\n{NEEDS_HUMAN_MARKER}: the implement node failed",
            )
        )
    )

    _ = _survey(repo=repo, item=item, journal=journal, runner=runner)

    rows = [
        json.loads(line)
        for line in journal.path.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("stage") == "stranded-claim-terminal-completion"
    ]
    assert [(row["run_id"], row["reason"], row["status"]) for row in rows] == [
        (_RUN_ID, "blocked", "active")
    ]
