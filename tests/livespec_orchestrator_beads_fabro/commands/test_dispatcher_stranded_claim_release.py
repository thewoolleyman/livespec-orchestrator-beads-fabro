"""The absent-run release: the one recovery route this subsection owns.

Scenario 196's "A first absent run with no live owner is released", end to end
through the claim survey against a hermetic tenant, a faked factory listing and
a faked forge.

What makes the case worth asserting at this level rather than at the grading
ladder's is the THREE DURABLE EFFECTS and their order: the item has to come
back to `ready` with no `fabro` assignee, one `stranded-claim-release` journal
record has to name the item, the run, the factory and the reason `run-absent`,
and one ledger comment has to name the same facts. Before this existed,
`reconcile-runs` reported `held: []` and `reconciled: []` for exactly this
state and every recovery was a hand `drive --action move:<id>:ready`.
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
    REASON_RUN_ABSENT,
    RELEASE_COMMENT_MARKER,
    STRANDED_CLAIM_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_dispatcher_stranded_claim_survey.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey"

_ITEM_ID = "bd-ib-strandrel"
_RUN_ID = "01M55X0ZNKTFXC1J8D9MT6WBF4"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"
_HOST = "test-dispatching-host"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    """The hermetic in-memory tenant, flipped on through its one env seam."""
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
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _seed_claim(*, item: WorkItem) -> None:
    """File the item and stamp the claim its dead dispatch left behind."""
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    record = client.show_issue(issue_id=item.id)
    raw = record.get("metadata")
    metadata = dict(raw) if isinstance(raw, dict) else {}
    metadata[CLAIM_STAMP_METADATA_KEY] = {
        "dispatch_id": "01DISPATCHONE",
        "dispatching_host": _HOST,
        "run_id": _RUN_ID,
        "factory": {"name": _FACTORY, "server": _SERVER},
    }
    client.update_issue(issue_id=item.id, metadata=metadata)


def _journal(*, repo: Path) -> JournalFile:
    """A journal carrying this item's ONE launch: a confirmed first dispatch."""
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        "".join(
            f"{json.dumps(record)}\n"
            for record in (
                {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": "01DISPATCHONE"},
                {"stage": "dispatch-run-stamp", "work_item_id": _ITEM_ID, "run_id": _RUN_ID},
            )
        ),
        encoding="utf-8",
    )
    return JournalFile(path=path)


class _Runner:
    """A fake subprocess seam answering the forge with no merged pull request."""

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


def test_a_first_absent_run_with_no_live_owner_is_released(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
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
                    # Answered, and the run is not in it: `fabro ps -a` lists
                    # terminal runs too, so this is a POSITIVE absence.
                    surveyed=True,
                    status_kinds={},
                ),
            ),
            this_host=_HOST,
            now_iso="2026-10-18T09:00:00Z",
        )
    )

    released = next(iter(read_work_items(path=_config())))
    assert (released.status, released.assignee) == ("ready", None)
    assert survey.held == ()
    assert [recovered.reason for recovered in survey.recovered] == [REASON_RUN_ABSENT]
    rows = [
        json.loads(line)
        for line in journal.path.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("stage") == STRANDED_CLAIM_RELEASE_STAGE
    ]
    assert [
        (row["work_item_id"], row["run_id"], row["factory"], row["reason"]) for row in rows
    ] == [(_ITEM_ID, _RUN_ID, _FACTORY, REASON_RUN_ABSENT)]
    bodies = [
        comment.text
        for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
        if comment.text.startswith(RELEASE_COMMENT_MARKER)
    ]
    assert len(bodies) == 1
    assert _RUN_ID in bodies[0]
    assert _FACTORY in bodies[0]
    assert REASON_RUN_ABSENT in bodies[0]
