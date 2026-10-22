"""Whether any carrier of this plan's assertions is still open.

The gate's end-to-end behaviour is bound by
`tests/integration/test_plan_resume_open_carrier_await.py`, which drives the
production `resume_directive`. This module covers the two readings that tier
cannot DISCRIMINATE, because both of them produce a derived proof pointer there
and so look identical from the resume's own surface:

- a carrier whose repository the result reader cannot resolve is PASSED OVER
  rather than reported open, so the scan reaches the carriers behind it; and
- a carrier whose status cannot be READ is reported OPEN, because only a
  satisfied reading establishes that a carrier is closed.

The second is the fail-closed arm and is the one worth stating plainly: an
unobservable reading treated as closed would make a broken or unreachable tenant
the cheapest route to a plan proof record asserting work nobody could look at.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_carrier_gate import (
    first_open_carrier,
    plan_carrier_ids,
    unplaceable_carrier_ids,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_SCOPE_PREFIX,
    plan_comment_body,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_NOW = "2026-10-22T07:00:00Z"
_EPIC = "bd-ib-plan"
_OWN = "repo"
_OWN_PREFIX = "bd-ib"
# A sibling whose clone exists AND declares a tenant, so its carriers resolve.
_CARRIER_REPO = "carrier-repo"
_CARRIER_PREFIX = "cr"
# A sibling whose clone exists and declares NO tenant, so it is absent from the
# carrier tenancy altogether: the shape of a configured-but-unprovisioned peer,
# and what makes a carrier of its UNPLACEABLE rather than merely unreadable.
_STRANGER_REPO = "stranger-repo"


@pytest.fixture(autouse=True)
def _hermetic_tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix=_OWN_PREFIX,
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        repo_root=repo,
        fake=True,
    )


def _fake(*, repo: Path) -> FakeBeadsClient:
    client = make_beads_client(config=_config(repo=repo))
    assert isinstance(client, FakeBeadsClient)
    return client


def _connection(*, prefix: str) -> dict[str, object]:
    return {"livespec-orchestrator-beads-fabro": {"connection": {"prefix": prefix}}}


def _project(*, tmp_path: Path) -> Path:
    repo = tmp_path / _OWN
    repo.mkdir()
    configured: dict[str, object] = dict(_connection(prefix=_OWN_PREFIX))
    configured["cross_repo_targets"] = {
        name: {"github_url": f"https://github.com/thewoolleyman/{name}"}
        for name in (_CARRIER_REPO, _STRANGER_REPO)
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(configured), encoding="utf-8")
    carrier = tmp_path / _CARRIER_REPO
    carrier.mkdir()
    _ = (carrier / ".livespec.jsonc").write_text(
        json.dumps(_connection(prefix=_CARRIER_PREFIX)), encoding="utf-8"
    )
    (tmp_path / _STRANGER_REPO).mkdir()
    return repo


def _epic(*, repo: Path, carriers: tuple[str, ...]) -> None:
    fake = _fake(repo=repo)
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=_EPIC,
            issue_type="epic",
            title=_EPIC,
            description="## Definition of Done\n\n- The plan reaches its archive.\n",
            assignee=None,
            created_at=_NOW,
        )
    )
    if not carriers:
        return
    fake.add_comment(
        issue_id=_EPIC,
        body=plan_comment_body(
            prefix=PLAN_SCOPE_PREFIX,
            author="plan-session",
            now=_NOW,
            body="carriers:\n" + "\n".join(f"- {one}" for one in carriers),
        ),
    )


def _item(*, repo: Path, item_id: str, closed: bool) -> None:
    fake = _fake(repo=repo)
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=item_id,
            issue_type="task",
            title=item_id,
            description="a carrier of one plan assertion",
            assignee=None,
            created_at=_NOW,
        )
    )
    if closed:
        fake.close_issue(issue_id=item_id, reason="the carrier landed")


def test_a_plan_with_no_carrier_map_event_names_no_carriers(tmp_path: Path) -> None:
    """The positive control for every absence below.

    Without it, a gate that answered `None` unconditionally would satisfy the
    closed-carrier and unresolvable-carrier cases alike.
    """
    repo = _project(tmp_path=tmp_path)
    _epic(repo=repo, carriers=())

    assert plan_carrier_ids(config=_config(repo=repo), epic_id=_EPIC) == ()
    assert first_open_carrier(config=_config(repo=repo), epic_id=_EPIC) is None
    assert unplaceable_carrier_ids(config=_config(repo=repo), epic_id=_EPIC) == ()


def test_an_unresolvable_carrier_is_passed_over_so_the_scan_reaches_the_next(
    tmp_path: Path,
) -> None:
    """A carrier nothing can place must not hide the open carrier behind it.

    Its status was never measured, so the gate can say nothing about it — and an
    obligation naming a repository nothing resolves is one no later resume could
    observe either. Reporting it open would therefore substitute an
    unobservable wait for a readable one, and the readable one is the step the
    plan actually owes.
    """
    repo = _project(tmp_path=tmp_path)
    _item(repo=repo, item_id="cr-open", closed=False)
    _epic(repo=repo, carriers=("1: ob-5qlusq", "2: cr-open"))

    carrier = first_open_carrier(config=_config(repo=repo), epic_id=_EPIC)

    assert carrier is not None
    assert (carrier.item_id, carrier.repo) == ("cr-open", _CARRIER_REPO)


def test_a_carrier_whose_status_cannot_be_read_is_reported_open(tmp_path: Path) -> None:
    """Only a SATISFIED reading establishes that a carrier is closed.

    The carrier's repository RESOLVES — its prefix is the sibling's own — and the
    sibling's tenant holds no such record, which is what a carrier-map event
    naming a mistyped or deleted id looks like. The read is therefore
    `unobservable`, and treating that as closed would let an unreadable id
    discharge a plan assertion. The plan stalls diagnosably instead, and the
    recorded `await` reports the same unobservable reading on the next resume.
    """
    repo = _project(tmp_path=tmp_path)
    _epic(repo=repo, carriers=(f"1: {_CARRIER_PREFIX}-missing",))

    carrier = first_open_carrier(config=_config(repo=repo), epic_id=_EPIC)

    assert carrier is not None
    assert (carrier.item_id, carrier.repo) == (f"{_CARRIER_PREFIX}-missing", _CARRIER_REPO)


def test_the_carriers_no_configured_target_places_are_reported_in_written_order(
    tmp_path: Path,
) -> None:
    """The pass-over's companion reading, and the one a human pointer names.

    The SAME fixture as the pass-over case above, asked the other question: the
    carrier the scan skipped is the carrier reported here, and the carrier it
    waited on is not. Reading both off one fixture is what keeps the two from
    answering about different populations — a gate reporting every carrier, or
    none, would satisfy whichever question was asked in isolation.
    """
    repo = _project(tmp_path=tmp_path)
    _item(repo=repo, item_id="cr-open", closed=False)
    _epic(repo=repo, carriers=("1: ob-5qlusq", "2: cr-open", "3: hl-pu2xr6"))

    assert unplaceable_carrier_ids(config=_config(repo=repo), epic_id=_EPIC) == (
        "ob-5qlusq",
        "hl-pu2xr6",
    )


def test_every_carrier_closed_leaves_no_carrier_to_wait_on(tmp_path: Path) -> None:
    """The gate reads each carrier's status rather than its presence in the map."""
    repo = _project(tmp_path=tmp_path)
    _item(repo=repo, item_id="cr-one", closed=True)
    _item(repo=repo, item_id="cr-two", closed=True)
    _epic(repo=repo, carriers=("1: cr-one", "2: cr-two"))

    assert first_open_carrier(config=_config(repo=repo), epic_id=_EPIC) is None


def test_the_first_open_carrier_in_the_maintainers_own_order_is_the_one_waited_on(
    tmp_path: Path,
) -> None:
    """Two open carriers select deterministically, not by whichever read first."""
    repo = _project(tmp_path=tmp_path)
    _item(repo=repo, item_id="cr-one", closed=True)
    _item(repo=repo, item_id="cr-two", closed=False)
    _item(repo=repo, item_id="cr-three", closed=False)
    _epic(repo=repo, carriers=("1: cr-one", "2: cr-two, cr-three"))

    carrier = first_open_carrier(config=_config(repo=repo), epic_id=_EPIC)

    assert carrier is not None
    assert carrier.item_id == "cr-two"
