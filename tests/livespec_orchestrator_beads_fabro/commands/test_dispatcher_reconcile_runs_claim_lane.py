"""The claim lane AS A RECONCILIATION PASS, not merely as a survey.

Scenario 196's "Every reconciliation surface releases a qualifying absent-run
claim" is a claim about the PASS, and the survey passing in isolation says
nothing about whether a pass reaches it. These cases drive `reconcile_runs`
itself.

TWO PROPERTIES ARE WHAT THE WIRING HAS TO GET RIGHT, and each has a case.
The lane rides the SAME `fabro ps -a --json` listing the orphan join read — a
second listing would let the two lanes describe one factory two ways — so the
runner is asserted to have been asked for exactly one `ps` per factory. And a
DECLARED factory this pass could not survey still reaches the lane as an
unsurveyed inventory, because a claim naming it must be held as
`factory-unobservable` rather than graded against an inventory nobody took;
without that entry it would grade `claim-unattributable`, which names a
different remedy.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs as reconcile
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    REASON_RUN_ABSENT,
    STRANDED_CLAIM_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-claimlane"
_RUN_ID = "01CLAIMLANERUN"
_HOST = "owning-host"
_HP = FactoryTarget(name="hp", server="https://hp.example:32276", dev_token=None)
_UNDECLARED_SERVER = FactoryTarget(name="vps", server=None, dev_token=None)


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
        title="A dispatched slice whose run vanished",
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


def _stamp(**overrides: object) -> ClaimStamp:
    base = ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host=_HOST,
        run_id=_RUN_ID,
        factory_name="hp",
        factory_server="https://hp.example:32276",
    )
    return replace(base, **overrides)


def _seed(*, stamp: ClaimStamp) -> WorkItem:
    item = _item()
    append_work_item(path=_config(), item=item)
    record_claim_stamp(path=_config(), work_item_id=item.id, stamp=stamp)
    return item


class _Runner:
    """A fake `fabro`/`gh`/`docker` seam recording which verb was asked."""

    def __init__(self) -> None:
        self.ps_calls: list[str] = []
        self.gh_calls: list[list[str]] = []

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
        if argv[0] == "gh":
            self.gh_calls.append(argv)
            return CommandResult(exit_code=0, stdout="[]", stderr="")
        # Every other invocation this pass makes is the ONE `fabro ps` per
        # declared factory, which both lanes then share.
        self.ps_calls.append(argv[argv.index("--server") + 1])
        return CommandResult(exit_code=0, stdout="[]", stderr="")


def _journal(*, repo: Path) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps({"stage": "dispatch-id", "work_item_id": _ITEM_ID}) + "\n",
        encoding="utf-8",
    )
    return JournalFile(path=path)


def _inputs(
    *,
    repo: Path,
    runner: _Runner,
    journal: JournalFile,
    items: list[WorkItem],
    claim_journal: JournalFile | None,
) -> ReconcileInputs:
    return ReconcileInputs(
        repo=repo,
        fabro_bin="fabro",
        id_prefix="bd-ib",
        items=items,
        journaled=journaled_runs(text=""),
        runner=runner,
        journal=journal,
        ledger=make_beads_client(config=_config()),
        blocked_run_grace_seconds=0,
        claim_journal=claim_journal,
        claim_host=_HOST,
    )


def _rows(*, journal: JournalFile, stage: str) -> list[dict[str, Any]]:
    return [
        record
        for line in journal.path.read_text(encoding="utf-8").splitlines()
        if (record := json.loads(line)).get("stage") == stage
    ]


def test_a_reconcile_runs_pass_releases_a_qualifying_absent_run_claim(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _seed(stamp=_stamp())
    journal = _journal(repo=repo)
    runner = _Runner()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            repo=repo, runner=runner, journal=journal, items=[item], claim_journal=journal
        ),
        factories=[_HP],
    )

    released = next(iter(read_work_items(path=_config())))
    assert (released.status, released.assignee) == ("ready", None)
    assert [claim.reason for claim in summary.recovered_claims] == [REASON_RUN_ABSENT]
    assert summary.held_claims == ()
    rows = _rows(journal=journal, stage=STRANDED_CLAIM_RELEASE_STAGE)
    assert [(row["work_item_id"], row["run_id"], row["factory"]) for row in rows] == [
        (_ITEM_ID, _RUN_ID, "hp")
    ]
    # ONE listing per factory, shared by both lanes.
    assert runner.ps_calls == [str(_HP.server)]
    assert len(runner.gh_calls) == 1


def test_a_pass_with_no_claim_journal_leaves_every_claim_alone(tmp_path: Path) -> None:
    """The narrow observation-only callers: a recovery must read before writing."""
    repo = _repo(tmp_path=tmp_path)
    item = _seed(stamp=_stamp())
    journal = _journal(repo=repo)
    runner = _Runner()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(repo=repo, runner=runner, journal=journal, items=[item], claim_journal=None),
        factories=[_HP],
    )

    assert (summary.recovered_claims, summary.held_claims) == ((), ())
    assert next(iter(read_work_items(path=_config()))).status == "active"
    assert runner.gh_calls == []


def test_a_declared_factory_this_pass_could_not_survey_still_holds_its_claims(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _seed(stamp=_stamp(factory_name="vps", factory_server=None))
    journal = _journal(repo=repo)
    runner = _Runner()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            repo=repo, runner=runner, journal=journal, items=[item], claim_journal=journal
        ),
        factories=[_HP, _UNDECLARED_SERVER],
    )

    assert [held.hold_reason for held in summary.held_claims] == ["factory-unobservable"]
    assert next(iter(read_work_items(path=_config()))).status == "active"


def test_a_dry_pass_projects_the_claim_route_and_writes_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _seed(stamp=_stamp())
    journal = _journal(repo=repo)

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            repo=repo, runner=_Runner(), journal=journal, items=[item], claim_journal=journal
        ),
        factories=[_HP],
        dry_run=True,
    )

    assert [claim.route for claim in summary.recovered_claims] == ["absent-run-release"]
    assert _rows(journal=journal, stage=STRANDED_CLAIM_RELEASE_STAGE) == []
    assert next(iter(read_work_items(path=_config()))).status == "active"
