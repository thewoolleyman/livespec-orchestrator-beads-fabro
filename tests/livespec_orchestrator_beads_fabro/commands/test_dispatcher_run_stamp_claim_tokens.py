"""The run stamp is a claim-changing write, so it wins the item's token first.

`SPECIFICATION/contracts.md` ("Dispatcher policy settings" -> "Stranded claim
release" -> "Claim tokens") defines a claim-changing write as "any write that
changes an item's status, its `fabro` assignee or its run stamp". The Dispatcher
writes two run stamps the moment it learns its run: the run id with its factory
target, and the claim stamp naming the run and the dispatching host.

Before the cutover both read the item's whole metadata object, add their keys
and send the whole object back, the token key included. After it, a stamp sent
that way by a writer that had been overtaken would put a CLOSED token id back
on the item. So with `dispatcher.claim_tokens` true each stamp is one
token-guarded write that sends its keys as an overlay and names the successor.

These cases drive `stamp_dispatch_run`, the one public entry both writes are
made from, against the in-memory tenant:

- WON: both stamps land, each under its own won token, and the item names the
  last successor.
- LOST at the first stamp: nothing is written to the item, the claim stamp is
  not contested at all, and the dispatch still proceeds with its attribution.
- LOST at the claim stamp: the run stamp stands and the claim stays pending.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_STAMP_METADATA_KEY,
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    create_claim_token,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_stamp import (
    RUN_CLAIM_STAMP_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import (
    STAMP_JOURNAL_STAGE,
    stamp_dispatch_run,
)

_ITEM_ID = "bd-ib-runstamp"
_RUN_ID = "01RUNSTAMPTOKEN"
_DISPATCH_ID = "01DISPATCHRUNSTAMP"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"
_WRITER = "dispatcher-run-stamp"
_ANOTHER_WRITER = "another writer won this token"
_REFUSED_STAGE = "claim-write-refused"


@pytest.fixture(autouse=True)
def _fresh_tenant() -> object:
    reset_fake_singleton()
    TRANSITION_OBSERVATIONS.clear()
    yield
    TRANSITION_OBSERVATIONS.clear()
    reset_fake_singleton()


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)

    def of_stage(self, *, stage: str) -> list[dict[str, object]]:
        return [record for record in self.records if record["stage"] == stage]


def _repo(*, tmp_path: Path, claim_tokens: bool) -> Path:
    dispatcher = {"claim_tokens": True} if claim_tokens else {}
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib", "tenant": "test-tenant", "fake": True},
                    "dispatcher": dispatcher,
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_ITEM_ID,
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor",
        fabro_factory_name=_FACTORY,
        fabro_factory_server=_SERVER,
    )


def _admitted_claim(*, repo: Path) -> tuple[FakeBeadsClient, str]:
    """An `active` claim carrying admission's pending stamp and an open current token."""
    config = store_config(repo=repo)
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM_ID,
            issue_type="task",
            title="A slice whose run was just learned",
            description="Implement the slice.",
            assignee="fabro",
            created_at="2026-11-06T00:00:00Z",
        )
    )
    client.update_issue(issue_id=_ITEM_ID, status="active", metadata={"rank": "a0"})
    record_claim_stamp(
        path=config,
        work_item_id=_ITEM_ID,
        stamp=ClaimStamp(
            dispatch_id=_DISPATCH_ID,
            dispatching_host="owning-host",
            run_id=None,
            factory_name=_FACTORY,
            factory_server=None,
        ),
    )
    token = create_claim_token(client=client)
    metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ITEM_ID, metadata=metadata)
    return client, token


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _current_token(*, client: FakeBeadsClient) -> str:
    return client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]


def _won(*, client: FakeBeadsClient, token: str) -> tuple[object, object, str]:
    """The writer and intent `token` was won with, and the successor it named."""
    reason = json.loads(client.show_issue(issue_id=token)["close_reason"])
    return reason["writer"], reason["intent"], reason["successor"]


def _lose_contest(
    *, client: FakeBeadsClient, monkeypatch: pytest.MonkeyPatch, contest: int
) -> None:
    """Let another writer win the item's current token on its `contest`-th contest."""
    close = client.close_issue_without_verdict
    contests: list[str] = []

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == _current_token(client=client):
            contests.append(issue_id)
            if len(contests) == contest:
                close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def test_enabled_stamps_each_win_a_token_and_land_their_keys_with_its_successor(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _admitted_claim(repo=repo)
    journal = _Journal()

    attribution = stamp_dispatch_run(plan=_plan(repo=repo), journal=journal, run_id=_RUN_ID)

    record = client.show_issue(issue_id=_ITEM_ID)
    metadata = record["metadata"]
    run_writer, run_intent, held = _won(client=client, token=token)
    claim_writer, claim_intent, last = _won(client=client, token=held)
    assert attribution.metadata_run_ids == {_RUN_ID: _ITEM_ID}
    assert (run_writer, run_intent) == (_WRITER, "run-stamp")
    assert (claim_writer, claim_intent) == (_WRITER, "run-claim-stamp")
    assert metadata[CLAIM_TOKEN_METADATA_KEY] == last
    assert client.show_issue(issue_id=last)["status"] != "closed"
    assert metadata["dispatch_fabro_run_id"] == _RUN_ID
    assert metadata["dispatch_factory"] == {"name": _FACTORY, "server": _SERVER}
    # The claim stamp learned its run and kept the dispatch admission stamped it with.
    assert (
        metadata[CLAIM_STAMP_METADATA_KEY]["run_id"],
        metadata[CLAIM_STAMP_METADATA_KEY]["dispatch_id"],
    ) == (_RUN_ID, _DISPATCH_ID)
    # A stamp changes neither the status nor the assignee, nor any other key.
    assert (record["status"], record["assignee"], metadata["rank"]) == ("active", "fabro", "a0")
    assert [row["stamped"] for row in journal.of_stage(stage=STAMP_JOURNAL_STAGE)] == [True]
    assert [row["claim_stamped"] for row in journal.of_stage(stage=RUN_CLAIM_STAMP_STAGE)] == [True]
    assert journal.of_stage(stage=_REFUSED_STAGE) == []


def test_an_enabled_run_stamp_that_loses_the_token_writes_nothing_and_is_not_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The claim moved under the run: no stamp lands, and the claim stamp is not contested."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _admitted_claim(repo=repo)
    before = _snapshot(client=client)
    _lose_contest(client=client, monkeypatch=monkeypatch, contest=1)
    journal = _Journal()

    attribution = stamp_dispatch_run(plan=_plan(repo=repo), journal=journal, run_id=_RUN_ID)

    [stamp_row] = journal.of_stage(stage=STAMP_JOURNAL_STAGE)
    [claim_row] = journal.of_stage(stage=RUN_CLAIM_STAMP_STAGE)
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["close_reason"] == _ANOTHER_WRITER
    # The dispatch proceeds: the run exists, and the mapping is a fact about the dispatch.
    assert attribution.metadata_run_ids == {_RUN_ID: _ITEM_ID}
    assert stamp_row["stamped"] is False
    assert "claim-changed" in str(stamp_row["stamp_failure_detail"])
    assert claim_row["claim_stamped"] is False
    assert str(claim_row["claim_stamp_failure_detail"]).startswith("claim stamp not attempted")
    # ONE contest, not two: the claim stamp never tried for the other writer's token.
    assert [row["intent"] for row in journal.of_stage(stage=_REFUSED_STAGE)] == ["run-stamp"]
    assert "claim-changed" in capsys.readouterr().err


def test_an_enabled_claim_stamp_that_loses_the_token_leaves_the_claim_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run stamp won and stands; the claim stamp's own contest was lost."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _admitted_claim(repo=repo)
    _lose_contest(client=client, monkeypatch=monkeypatch, contest=2)
    journal = _Journal()

    _ = stamp_dispatch_run(plan=_plan(repo=repo), journal=journal, run_id=_RUN_ID)

    metadata = client.show_issue(issue_id=_ITEM_ID)["metadata"]
    _, _, held = _won(client=client, token=token)
    [claim_row] = journal.of_stage(stage=RUN_CLAIM_STAMP_STAGE)
    assert metadata["dispatch_fabro_run_id"] == _RUN_ID
    assert metadata[CLAIM_STAMP_METADATA_KEY]["run_id"] is None
    # The item still names the token the run stamp named: the lost write changed nothing.
    assert metadata[CLAIM_TOKEN_METADATA_KEY] == held
    assert client.show_issue(issue_id=held)["close_reason"] == _ANOTHER_WRITER
    assert claim_row["claim_stamped"] is False
    assert "claim-changed" in str(claim_row["claim_stamp_failure_detail"])
    assert [row["intent"] for row in journal.of_stage(stage=_REFUSED_STAGE)] == ["run-claim-stamp"]


def test_disabled_stamps_land_without_touching_the_token_the_item_names(tmp_path: Path) -> None:
    """Before the cutover both stamps are the writes they always were."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    client, token = _admitted_claim(repo=repo)
    journal = _Journal()

    _ = stamp_dispatch_run(plan=_plan(repo=repo), journal=journal, run_id=_RUN_ID)

    metadata = client.show_issue(issue_id=_ITEM_ID)["metadata"]
    assert metadata["dispatch_fabro_run_id"] == _RUN_ID
    assert metadata[CLAIM_STAMP_METADATA_KEY]["run_id"] == _RUN_ID
    assert metadata[CLAIM_TOKEN_METADATA_KEY] == token
    assert client.show_issue(issue_id=token)["status"] != "closed"
    assert client.no_history_issue_ids() == (token,)


def test_a_second_dispatch_handed_the_same_claim_stamps_nothing_onto_the_firsts_run(
    tmp_path: Path,
) -> None:
    """Sequential, not racing: the claim already carries the first dispatch's run."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _admitted_claim(repo=repo)
    second_journal = _Journal()

    _ = stamp_dispatch_run(
        plan=_plan(repo=repo), journal=_Journal(), run_id=_RUN_ID, dispatch_id=_DISPATCH_ID
    )
    as_first_left_it = _snapshot(client=client)
    _ = stamp_dispatch_run(
        plan=_plan(repo=repo),
        journal=second_journal,
        run_id="01ANOTHERRUN",
        dispatch_id="01ANOTHERDISPATCH",
    )

    _, _, held = _won(client=client, token=token)
    _, _, last = _won(client=client, token=held)
    assert _snapshot(client=client) == as_first_left_it
    # Nothing was contested: the first dispatch's last successor is still open.
    assert _current_token(client=client) == last
    assert client.show_issue(issue_id=last)["status"] != "closed"
    assert [row["stamped"] for row in second_journal.of_stage(stage=STAMP_JOURNAL_STAGE)] == [False]
    assert [row["intent"] for row in second_journal.of_stage(stage=_REFUSED_STAGE)] == ["run-stamp"]


def test_the_same_dispatch_moving_to_a_new_run_re_stamps_its_own_claim(tmp_path: Path) -> None:
    """A re-dispatch inside one watch loop is the same dispatch, so its stamp follows it."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, _ = _admitted_claim(repo=repo)

    for run_id in (_RUN_ID, "01THENEXTRUN"):
        _ = stamp_dispatch_run(
            plan=_plan(repo=repo), journal=_Journal(), run_id=run_id, dispatch_id=_DISPATCH_ID
        )

    metadata = client.show_issue(issue_id=_ITEM_ID)["metadata"]
    assert metadata["dispatch_fabro_run_id"] == "01THENEXTRUN"
    assert metadata[CLAIM_STAMP_METADATA_KEY]["run_id"] == "01THENEXTRUN"


def test_a_run_stamp_for_an_item_that_left_active_is_refused_uncontested(tmp_path: Path) -> None:
    """The claim moved under the run before the run was learned."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _admitted_claim(repo=repo)
    client.update_issue(issue_id=_ITEM_ID, status="ready", clear_assignee=True)
    before = _snapshot(client=client)

    _ = stamp_dispatch_run(
        plan=_plan(repo=repo), journal=_Journal(), run_id=_RUN_ID, dispatch_id=_DISPATCH_ID
    )

    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["status"] != "closed"
