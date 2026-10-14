"""Losing visibility retains ownership of a possibly live run."""

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked import (
    escalate_needs_human_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    bounce_non_convergence_to_backlog,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_run_claim import (
    release_pre_run_claim_if_needed,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import WorkItem

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_fabro_reattach import Runner
from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_fabro_reattach_deadline import (
    plan_for_test,
)


@pytest.mark.parametrize("inspect_exit", [0, 1])
def test_exhausted_visibility_names_live_run_journals_attempts_and_retains_claim(
    *, tmp_path: Path, inspect_exit: int
) -> None:
    (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"connection":{"prefix":"bd-ib"}}}',
        encoding="utf-8",
    )
    config = store_config(repo=tmp_path)
    item = WorkItem(
        id="bd-ib-w3k6dm",
        type="bug",
        status="active",
        title="Retain supervision",
        description="Retain the claim while a run may still be alive.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-14T09:40:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    append_work_item(path=config, item=item)
    runner = Runner(
        replies=[
            CommandResult(
                exit_code=1,
                stdout="Run: 01DROPPED\n",
                stderr="error decoding response body: timed out",
            ),
            *[
                CommandResult(
                    exit_code=inspect_exit,
                    stdout="{}" if inspect_exit == 0 else "",
                    stderr="server request timed out after 30s" if inspect_exit else "",
                )
            ]
            * 12,
        ]
    )
    journal = JournalFile(path=tmp_path / "dispatch.jsonl")
    outcome = run_dispatch(
        plan=plan_for_test(repo=tmp_path),
        runner=runner,
        journal=journal,
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=1, interval_seconds=0),
    )
    assert (outcome.status, outcome.stage) == ("run-unobservable", "fabro-reattach")
    assert outcome.fabro_run_id == "01DROPPED"
    assert "01DROPPED" in outcome.detail
    assert "possibly still alive" in outcome.detail
    assert "claim retained" in outcome.detail
    for disposition in (
        release_pre_run_claim_if_needed,
        escalate_needs_human_block,
        bounce_non_convergence_to_backlog,
    ):
        disposition(repo=tmp_path, item=item, outcome=outcome, journal=journal)
    stored = list(read_work_items(path=config))
    assert len(stored) == 1
    assert (stored[0].status, stored[0].assignee) == ("active", "fabro")
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    attempts = [record for record in records if record["stage"] == "fabro-reattach"]
    assert [record["attempt"] for record in attempts] == list(range(1, 13))
    assert all(record["run_id"] == "01DROPPED" for record in attempts)
    assert all(record["exit_code"] == inspect_exit for record in attempts)
    assert len(runner.calls) == 13
    assert "ledger-admit-release" not in {record["stage"] for record in records}
