"""A refused intake route is reported by its caller, never discarded.

With the committed key `dispatcher.claim_tokens` true, intake's routing write is
a claim-changing write (`SPECIFICATION/contracts.md`, "Claim tokens"): it lands
only after intake wins the item's current token, and a route that does not win
writes nothing and answers the protocol's outcome name. Two callers of intake
used to drop that answer:

- GROOM files each approved slice and then routes it. A refused route left the
  slice at `pending-approval` and the groom result said nothing about it.
- RELEASE-SPEC-TIER routes the released item back through intake. A refused
  route was reported as `intake-routing-failed` with a dataclass repr in the
  summary, and the protocol's outcome appeared nowhere a caller could read it.

Each case drives a public entry point against the in-memory tenant:
`file_approved_slices` (the front-end's filing seam), `file_groom_plan` (the
Dispatcher's apply seam, which files through the same call) and
`run_human_valve_action` for the valve.

HOW A REFUSED ROUTE IS MADE. A claim writer reads the item's current token,
mints the successor, and only then closes the token. `_lose_the_first_route`
steps in at that close and has another writer close the token first, which is
the race the protocol exists for. Only intake's first close is lost, so a cut of
two slices has one refused route and one that lands.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro import intake_dor
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_comments import (
    append_work_item_comment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro._store_groom_approval import GroomApproval
from livespec_orchestrator_beads_fabro.commands import _drive_release_spec_tier_valve as valve
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_apply import (
    GROOM_CUT_FILED_STAGE,
    file_groom_plan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.commands._intake_valve_claim_writes import (
    ClaimWriteRefused,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    SpecChangeTierDecision,
    behaviour_digest,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_FILING,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.commands.groom import (
    CandidateSlice,
    GroomResult,
    file_approved_slices,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem, WorkItemStatus
from livespec_runtime.spec_stated import SpecStatedVerdict
from returns.io import IOFailure

_ORIGINAL = "bd-ib-refused-route"
_HEADING = "## A governing clause"
# The repository's directory name is the identity a slice's `repo_target` is matched against.
_LOCAL_REPO = "repo"
_FIRST = "Report the refused route"
_SECOND = "Keep the routed slice as it was"
_APPROVAL = GroomApproval(approver="thewoolleyman", route="resolve-blocked ready valve")
_ANOTHER_WRITER = "another writer won this token"
_ACTOR = InvokerIdentity(invoker="human:chad", invoker_source="flag")
_TRIAGED = "intake:triaged"
_CUT_OVER = {"claim_tokens": True}
_CONNECTION = {
    "tenant": "livespec-impl-beads",
    "prefix": "bd-ib",
    "server_user": "livespec-impl-beads",
    "database": "livespec-impl-beads",
    "bd_path": "bd",
    "fake": True,
}
_PLAN = (
    "livespec-groom-plan | approver=thewoolleyman | route=resolve-blocked ready valve"
    f" ;; slice={_FIRST} | tier=factory | repo={_LOCAL_REPO}"
    " | acceptance=The refusal is reported. | blockers=none | spec=no"
    " | scope=Report the refused route of a filed slice."
)


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    TRANSITION_OBSERVATIONS.clear()
    # The Definition-of-Done judgement is a model call and not this module's
    # subject; stood down, intake routes on its mechanical findings alone.
    monkeypatch.setattr(
        intake_dor, "judge_item_definition_of_done", lambda **_kwargs: SimpleNamespace(holds=False)
    )
    yield
    TRANSITION_OBSERVATIONS.clear()
    reset_fake_singleton()


def _config(*, repo_root: Path | None = None) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _repo(*, tmp_path: Path, dispatcher: dict[str, bool] = _CUT_OVER) -> Path:
    """A repository with a readable spec tree and the given committed `dispatcher` block."""
    repo = tmp_path / _LOCAL_REPO
    spec = repo / "SPECIFICATION"
    (spec / "history" / "v001").mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nBody.\n", encoding="utf-8"
    )
    block = {"connection": _CONNECTION, "dispatcher": dispatcher}
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": block}), encoding="utf-8"
    )
    return repo


def _original(*, status: WorkItemStatus, assignee: str | None = None) -> WorkItem:
    return WorkItem(
        id=_ORIGINAL,
        type="feature",
        status=status,
        title="An item whose intake route can be refused",
        description=f"## Definition of Done\n\n- It does the thing.\n\nReferences: {_HEADING}\n",
        origin="freeform",
        gap_id=None,
        rank="m",
        assignee=assignee,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _seed(*, item: WorkItem) -> FakeBeadsClient:
    """File the item through a descriptor naming no repository, then name it a fresh token.

    The store names a first token itself on an item created in a cut-over
    repository; seeding without one keeps the token the case contests the one
    the case minted.
    """
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    metadata = dict(client.show_issue(issue_id=item.id)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = create_claim_token(client=client)
    client.update_issue(issue_id=item.id, metadata=metadata, names_claim_token=True)
    return client


def _lose_the_first_route(*, client: FakeBeadsClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Have another writer win the first token intake contests, and no other."""
    close = client.close_issue_without_verdict
    lost: list[str] = []

    def _raced(*, issue_id: str, reason: str) -> None:
        if not lost and json.loads(reason)["writer"] == "intake":
            lost.append(issue_id)
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def _slice(*, title: str) -> CandidateSlice:
    return CandidateSlice(
        title=title,
        description=f"Do the one thing {title!r} names.",
        acceptance="The check suite verifies it.",
        autonomy_tier="factory",
        repo_target=_LOCAL_REPO,
    )


def _groom(*, repo: Path) -> GroomResult:
    """The front-end's filing of an approved cut of two independent local slices."""
    return file_approved_slices(
        path=_config(repo_root=repo),
        regroom_item_id=_ORIGINAL,
        local_repo=_LOCAL_REPO,
        approval=_APPROVAL,
        slices=[_slice(title=_FIRST), _slice(title=_SECOND)],
    )


def _groom_with_the_first_route_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[FakeBeadsClient, GroomResult]:
    repo = _repo(tmp_path=tmp_path)
    client = _seed(item=_original(status="backlog"))
    _lose_the_first_route(client=client, monkeypatch=monkeypatch)
    return client, _groom(repo=repo)


def test_a_groom_reports_the_slice_whose_intake_route_was_refused_and_the_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 1: the refused slice's id and the protocol's outcome are in the result."""
    client, result = _groom_with_the_first_route_refused(tmp_path=tmp_path, monkeypatch=monkeypatch)

    refused_id, routed_id = result.filed_slice_ids
    refused, routed = (client.show_issue(issue_id=slice_id) for slice_id in result.filed_slice_ids)
    assert asdict(result).get("refused_slice_routes") == (
        {"slice_id": refused_id, "outcome": "claim-changed"},
    )
    # What the report describes: the refused route wrote nothing, the other landed.
    assert (refused["status"], _TRIAGED in refused["labels"]) == ("pending-approval", False)
    assert _TRIAGED in routed["labels"]
    assert routed_id != refused_id


def test_a_groom_with_a_refused_slice_route_is_reported_as_not_fully_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 2: the cut is filed and the original closed, and the groom still says it fell short."""
    client, result = _groom_with_the_first_route_refused(tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert getattr(result, "fully_applied", None) is False
    assert result.regroomed_out is True
    assert client.show_issue(issue_id=_ORIGINAL)["status"] == "closed"


@pytest.mark.parametrize(
    "dispatcher",
    [_CUT_OVER, {"claim_tokens": False}, {}],
    ids=["key-true", "key-false", "key-unset"],
)
def test_a_groom_whose_every_route_landed_reports_no_refusal_and_is_fully_applied(
    dispatcher: dict[str, bool], tmp_path: Path
) -> None:
    """Nothing is reported where nothing was refused, with the key true, false or unset."""
    repo = _repo(tmp_path=tmp_path, dispatcher=dispatcher)
    client = _seed(item=_original(status="backlog"))

    result = _groom(repo=repo)

    assert asdict(result).get("refused_slice_routes") == ()
    assert getattr(result, "fully_applied", None) is True
    assert all(
        _TRIAGED in client.show_issue(issue_id=slice_id)["labels"]
        for slice_id in result.filed_slice_ids
    )


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_the_dispatcher_apply_seam_journals_the_refused_slice_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 1 and 2 on the Dispatcher's groom: its result is the journal record of the filing."""
    repo = _repo(tmp_path=tmp_path)
    item = _original(status="active", assignee="dispatcher")
    client = _seed(item=item)
    _lose_the_first_route(client=client, monkeypatch=monkeypatch)
    journal = _Journal()

    filed = file_groom_plan(
        repo=repo, item=item, text=_PLAN, variant="groom-cut", run_id="01RUN", journal=journal
    )

    (record,) = [entry for entry in journal.records if entry["stage"] == GROOM_CUT_FILED_STAGE]
    (slice_id,) = record["filed_slice_ids"]
    assert filed is True
    assert record.get("refused_slice_routes") == [
        {"slice_id": slice_id, "outcome": "claim-changed"}
    ]
    assert record.get("fully_applied") is False
    assert client.show_issue(issue_id=slice_id)["status"] == "pending-approval"


def _held(*, repo: Path) -> FakeBeadsClient:
    """The item at `pending-approval` under a recorded spec-change-tier hold, as a filing leaves it."""
    item = _original(status="pending-approval")
    client = _seed(item=item)
    held = SpecChangeTierDecision(
        tier="spec-change",
        classification="feature",
        verdict=SpecStatedVerdict(
            kind="unstated", stated_by=(), generalization_target=_HEADING, rationale="not stated"
        ),
        linked_proposal_topic="a-refused-route",
    )
    append_work_item_comment(
        path=_config(repo_root=repo),
        work_item_id=_ORIGINAL,
        body=spec_change_tier_comment(
            item_id=_ORIGINAL,
            stage=STAGE_FILING,
            decision=held,
            spec_version="1",
            digest=behaviour_digest(item=item),
        ),
    )
    return client


def _release(*, repo: Path) -> dict[str, object]:
    return run_human_valve_action(
        repo=repo,
        action_id=f"release-spec-tier:{_ORIGINAL}:{_HEADING}",
        runner=lambda **_kwargs: SimpleNamespace(returncode=0, stdout="[]", stderr=""),
        identity=_ACTOR,
    )


def _attested() -> bool:
    return any(
        comment.text.startswith("livespec-spec-tier-attestation")
        for comment in read_work_item_comments(path=_config(), work_item_id=_ORIGINAL)
    )


def test_a_release_whose_intake_route_lost_its_token_fails_with_claim_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 3, over the real intake route: the lost token is the valve's domain error."""
    repo = _repo(tmp_path=tmp_path)
    client = _held(repo=repo)
    _lose_the_first_route(client=client, monkeypatch=monkeypatch)

    result = _release(repo=repo)

    record = client.show_issue(issue_id=_ORIGINAL)
    journal = result["journal"]
    assert result["status"] == "failed"
    assert result["domain_error"] == "claim-changed"
    assert "ClaimWriteRefused(" not in str(result["summary"])
    assert "the attestation stands" in str(result["summary"])
    assert (record["status"], _TRIAGED in record["labels"]) == ("pending-approval", False)
    assert isinstance(journal, dict)
    assert journal["heading"] == _HEADING
    assert _attested()


@pytest.mark.parametrize(
    "outcome", ["claim-transition-pending", "claim-token-missing", "claim-tokens-unreadable"]
)
def test_a_release_reports_whichever_outcome_the_protocol_refused_its_route_with(
    outcome: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 3: the domain error is the outcome intake answered, not one fixed name."""
    repo = _repo(tmp_path=tmp_path)
    _ = _held(repo=repo)
    refused = ClaimWriteRefused(
        work_item_id=_ORIGINAL, writer="intake", intent="route:ready", outcome=outcome
    )
    monkeypatch.setattr(valve, "apply_intake_dor", lambda **_kwargs: IOFailure(refused))

    result = _release(repo=repo)

    assert result["status"] == "failed"
    assert result["domain_error"] == outcome
    assert result["work_item_ref"] == _ORIGINAL
    assert _attested()
