"""A SECOND consecutive absent run rests for a human instead of releasing.

Scenario 196's "A second consecutive absent run rests for a human". The
release is bounded to ONE per consecutive sequence of absent runs, because a
second vanished run is either a genuinely unrunnable item or something a
re-dispatch will meet again — and releasing it again is an unbounded loop with
no operator in it.

THE DISCRIMINATOR IS THE PRECEDING DISPATCH, NOT A LIFETIME COUNT, and the
journal fixture here is what makes that assertable: the item's launch rows
delimit its dispatches, and the earlier segment is where its predecessor's
ending sits. A lifetime count of release rows would agree with this fixture
and disagree with a release, a human move, an unrelated dispatch and then a
vanished run — the sequence `_dispatcher_stall_disposition` records the same
trap for.

The comment NAMES BOTH RUNS, because the pair is the finding: an operator
reading the newer run alone cannot see the pattern that stopped the release.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import CLAIM_STAMP_METADATA_KEY
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    REASON_RUN_ABSENT_REPEATED,
    REPEATED_COMMENT_MARKER,
    STRANDED_CLAIM_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey"

_ITEM_ID = "bd-ib-strandrep"
_FIRST_RUN = "01FIRSTVANISHEDRUN"
_SECOND_RUN = "01SECONDVANISHEDRUN"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"
_HOST = "test-dispatching-host"


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


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A slice whose second run also vanished",
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
    return replace(base, **overrides)


def _seed_claim(*, item: WorkItem) -> None:
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    raw = client.show_issue(issue_id=item.id).get("metadata")
    metadata = dict(raw) if isinstance(raw, dict) else {}
    metadata[CLAIM_STAMP_METADATA_KEY] = {
        "dispatch_id": "01DISPATCHTWO",
        "dispatching_host": _HOST,
        "run_id": _SECOND_RUN,
        "factory": {"name": _FACTORY, "server": _SERVER},
    }
    client.update_issue(issue_id=item.id, metadata=metadata)


def _journal(*, repo: Path) -> JournalFile:
    """Two dispatches, the FIRST of which ended in an absent-run release."""
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        "".join(
            f"{json.dumps(record)}\n"
            for record in (
                {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": "01DISPATCHONE"},
                {
                    "stage": "dispatch-run-stamp",
                    "work_item_id": _ITEM_ID,
                    "run_id": _FIRST_RUN,
                },
                {
                    "stage": STRANDED_CLAIM_RELEASE_STAGE,
                    "work_item_id": _ITEM_ID,
                    "run_id": _FIRST_RUN,
                    "reason": "run-absent",
                },
                {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": "01DISPATCHTWO"},
                {
                    "stage": "dispatch-run-stamp",
                    "work_item_id": _ITEM_ID,
                    "run_id": _SECOND_RUN,
                },
            )
        ),
        encoding="utf-8",
    )
    return JournalFile(path=path)


class _Runner:
    """A fake subprocess seam; the forge reports no merged pull request."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return CommandResult(exit_code=0, stdout="[]", stderr="")


def test_a_second_consecutive_absent_run_rests_at_blocked_needs_human(tmp_path: Path) -> None:
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed_claim(item=item)
    journal = _journal(repo=repo)

    survey = module.survey_stranded_claims(
        inputs=module.StrandedClaimInputs(
            repo=repo,
            items=(item,),
            journal=journal,
            runner=_Runner(),
            inventories=(
                module.FactoryInventory(
                    name=_FACTORY,
                    server_url=_SERVER,
                    fabro_bin="fabro",
                    surveyed=True,
                    status_kinds={},
                ),
            ),
            this_host=_HOST,
            now_iso="2026-10-18T09:00:00Z",
        )
    )

    rested = next(iter(read_work_items(path=_config())))
    assert (rested.status, rested.blocked_reason) == ("blocked", "needs-human")
    assert [recovered.reason for recovered in survey.recovered] == [REASON_RUN_ABSENT_REPEATED]
    bodies = [
        comment.text
        for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
        if comment.text.startswith(REPEATED_COMMENT_MARKER)
    ]
    assert len(bodies) == 1
    # BOTH runs, because the pair is the finding.
    assert _SECOND_RUN in bodies[0]
    assert _FIRST_RUN in bodies[0]
    assert REASON_RUN_ABSENT_REPEATED in bodies[0]
    # The release route must NOT have fired a second time for this item.
    stages = [
        json.loads(line).get("stage")
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    ]
    assert stages.count(STRANDED_CLAIM_RELEASE_STAGE) == 1
