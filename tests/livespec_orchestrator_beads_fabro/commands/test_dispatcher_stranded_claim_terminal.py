"""A terminal failed run gets the DISPATCHER'S OWN disposition, not a new one.

Scenario 196's "A terminal failed run with no live owner receives the
Dispatcher's own terminal disposition" and "An ordinary failed run rests for a
human with its cause". The clause is explicit that reconciliation "adds no
recovery route of its own except the absent-run release": when the owning
Dispatcher was killed after its run ended, reconciliation applies the
disposition that Dispatcher would have applied, "exactly as if it had observed
it".

THE TWO CASES ARE EACH OTHER'S CONTROL, which is the whole point of asserting
them together. Without the ordinary-failure case, a completion that RELEASED
every failed run would satisfy the provider-limit assertion while destroying
the human route the contract keeps for an unclassifiable failure. Without the
provider-limit case, one that rested every failed run at `blocked` would
satisfy the ordinary assertion while re-creating the measured outage the
release exists to end — a session-limit kill resting a slice for a human and
discarding its preserved work.

THE FIXTURE IS THE MEASURED OUTAGE, reused from
`test_dispatcher_provider_limit_terminal_outcome.py`: the implement node's
innermost cause reading "You have hit your session limit", which the engine
records with the typed provider-usage-limit flag.

THE CAUSE COMMENT IS THE DISPATCHER'S OWN and is asserted as such. This
subsection renders no needs-human record of its own — doing so would be a
second account of one ending, which is exactly what "adds no recovery route of
its own" forbids — so the assertion is that the Dispatcher's writer ran, naming
the run id and the reason its terminal recorded.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import CLAIM_STAMP_METADATA_KEY
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    NEEDS_HUMAN_CAUSE_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NEEDS_HUMAN_MARKER
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_records import (
    PROVIDER_LIMIT_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey"

_ITEM_ID = "bd-ib-strandterm"
_RUN_ID = "01M52R2WND7YTERMINALRUN"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"
_HOST = "test-dispatching-host"

_SESSION_LIMIT = "You have hit your session limit, resets 7:20pm (UTC)"
_INFRA_FAULT = "Failed to inspect Docker image: connection refused"


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
        title="A slice whose run ended while its Dispatcher was being killed",
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
        "dispatch_id": "01DISPATCHONE",
        "dispatching_host": _HOST,
        "run_id": _RUN_ID,
        "factory": {"name": _FACTORY, "server": _SERVER},
    }
    client.update_issue(issue_id=item.id, metadata=metadata)


def _journal(*, repo: Path) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps({"stage": "dispatch-id", "work_item_id": _ITEM_ID}) + "\n",
        encoding="utf-8",
    )
    return JournalFile(path=path)


def _inspect_payload(*, cause: str) -> list[dict[str, Any]]:
    """One terminated run whose implement node failed, routed to needs_human."""
    return [
        {
            "run_id": _RUN_ID,
            "status": {"kind": "failed", "reason": "workflow_error"},
            "checkpoint": {
                "current_node": "needs_human",
                "next_node_id": None,
                "completed_nodes": ["implement"],
                "node_outcomes": {"implement": {"status": "failed"}},
            },
            "conclusion": {
                "status": "failed",
                "timestamp": "2026-10-18T08:00:00Z",
                "failure": {
                    "reason": "workflow_error",
                    "detail": {
                        "message": (
                            f"ACP protocol error\n{cause}\n"
                            f"{NEEDS_HUMAN_MARKER}: the implement node failed"
                        ),
                        "category": "transient_infra",
                    },
                },
            },
        }
    ]


class _Runner:
    """A fake `fabro` seam answering `inspect` with one terminated run.

    It answers no `gh` call, and that absence is an ASSERTION rather than an
    omission: the forge is one of the absent-run release's preconditions and
    nothing else reads it, so a TERMINAL claim that reached the forge would be
    paying for a measurement no verdict here consults.
    """

    def __init__(self, *, cause: str) -> None:
        self.cause = cause

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
        if argv[1] == "inspect":
            return CommandResult(
                exit_code=0,
                stdout=json.dumps(_inspect_payload(cause=self.cause)),
                stderr="",
            )
        # `ps -a --json` (the executed-candidate attribution) and `events`
        # (the terminal event stream) both answer with nothing to read, which
        # keeps the attribution on its legacy posture: no entitlement was
        # measured, so no typed hold is minted.
        return CommandResult(exit_code=0, stdout="[]", stderr="")


def _survey(
    *, module: object, repo: Path, item: WorkItem, journal: JournalFile, cause: str
) -> object:
    return module.survey_stranded_claims(
        inputs=module.StrandedClaimInputs(
            repo=repo,
            items=(item,),
            journal=journal,
            runner=_Runner(cause=cause),
            inventories=(
                module.FactoryInventory(
                    name=_FACTORY,
                    server_url=_SERVER,
                    fabro_bin="fabro",
                    surveyed=True,
                    # The factory DOES report the run, terminal and failed.
                    status_kinds={_RUN_ID: "failed"},
                ),
            ),
            this_host=_HOST,
            now_iso="2026-10-18T09:00:00Z",
        )
    )


def _stages(*, journal: JournalFile) -> list[object]:
    return [
        json.loads(line).get("stage")
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    ]


def test_an_eligible_provider_limit_failure_takes_the_provider_limit_release(
    tmp_path: Path,
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed_claim(item=item)
    journal = _journal(repo=repo)

    survey = _survey(module=module, repo=repo, item=item, journal=journal, cause=_SESSION_LIMIT)

    assert survey.held == ()
    released = next(iter(read_work_items(path=_config())))
    assert (released.status, released.assignee) == ("ready", None)
    # The DISPATCHER'S OWN record, written by its own disposition — not a
    # record this subsection invented for the same event.
    assert PROVIDER_LIMIT_RELEASE_STAGE in _stages(journal=journal)


def test_a_failure_no_release_route_claims_rests_for_a_human_with_its_cause(
    tmp_path: Path,
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed_claim(item=item)
    journal = _journal(repo=repo)

    survey = _survey(module=module, repo=repo, item=item, journal=journal, cause=_INFRA_FAULT)

    assert survey.held == ()
    rested = next(iter(read_work_items(path=_config())))
    assert (rested.status, rested.blocked_reason) == ("blocked", "needs-human")
    assert PROVIDER_LIMIT_RELEASE_STAGE not in _stages(journal=journal)
    bodies = [
        comment.text
        for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
        if comment.text.startswith(NEEDS_HUMAN_CAUSE_MARKER)
    ]
    assert len(bodies) == 1
    # The comment is the DISPATCHER'S OWN, rendered by its own writer: this
    # subsection applies that disposition and renders no cause comment of its
    # own, so what it names is the run id and the reason the terminal recorded.
    assert _RUN_ID in bodies[0]
    assert "the implement node failed" in bodies[0]
