"""Scenario 126 — adoption of a beads-native row assigns it a real rank.

Binds `SPECIFICATION/scenarios.md` "Scenario 126 — Ledger normalization adopts
a beads-native `open` row and assigns it a real rank" and the contract it
realizes in `SPECIFICATION/contracts.md`: the work-item beads-issue mapping's
adoption bullet, which requires a rank-less adopted row to also receive a real,
non-sentinel rank from a single bottom-of-order insert.

Every case drives a REAL `dispatcher.main(argv=...)` CLI invocation over the
REAL store/client seam against the in-memory `FakeBeadsClient`; nothing is
stood in. The heading's fifth gherkin scenario is a claim about FOUR cadences,
so the bound test runs all four — `loop`, `dispatch`, the standalone
`ledger-normalize` CLI, and the pre-push `ledger-normalize --gate` — each over
its own freshly-seeded tenant, and compares the four resulting tenants to each
other as well as to the expected outcome. Comparing them to each other is what
makes the fifth case mean anything: four legs each asserted only against the
same expected map would pass just as well for four cadences that all
implemented the SAME wrong thing.

Three traps shaped the fixture, and each is a control that would let a wrong
implementation pass.

The `done` row carries rank `az`, a VALID order key that sorts strictly AFTER
every live key in the tenant. Its whole job is to be wrong to read: an
implementation that took the maximum key across ALL rows rather than the live
ones would derive `b00` from it, so the expected `a6` positively discriminates
"the insert read the LIVE order" from "the insert read the tenant". A sentinel
or absent rank on that row could not discriminate anything, because it would be
excluded either way.

The already-ranked `open` row carries `a3`, deliberately NOT the live maximum.
Were it the maximum, "it keeps its rank" and "the fresh key was derived from
it" would be one assertion wearing two hats, and a build that re-keyed it in
place could still land the expected fresh key. With the maximum living on a row
no cadence touches (`ready`, rank `a5`), the two claims are separable.

The two rank-less adopted rows are asserted to hold `a6` and `a7` — DISTINCT
keys, both strictly between the live maximum and the bottom sentinel. A single
shared key would satisfy "a real, non-sentinel rank was assigned" for each row
read on its own while leaving the two rows tied, which is the ordering
ambiguity `rank` exists to remove.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    plan_native_status_remaps,
    project_native_status_remaps,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.work_items.rank import BOTTOM_SENTINEL

# The tenant's live maximum key, on a row NO cadence adopts.
_LIVE_MAX_RANK = "a5"
# A valid order key sorting strictly after `_LIVE_MAX_RANK`, parked on the one
# `done` row so a whole-tenant maximum would be visibly wrong (see the module
# docstring): `key_between(a="az", b=None)` is `b00`, not `a6`.
_CLOSED_RANK = "az"
# What a single bottom-of-order insert below `_LIVE_MAX_RANK` yields, then a
# second insert below that.
_FIRST_ASSIGNED_RANK = "a6"
_SECOND_ASSIGNED_RANK = "a7"
# The already-ranked `open` row's key: real, and deliberately not the maximum.
_KEPT_RANK = "a3"

_ADOPTED_RANKLESS = "bd-ib-native-open"
_ADOPTED_CLAIM = "bd-ib-raw-claim"
_ADOPTED_RANKED = "bd-ib-open-ranked"
_PARKED = "bd-ib-parked"
_UNTOUCHED_LIVE = "bd-ib-live-max"
_CLOSED = "bd-ib-closed"

# The (status, rank) every cadence must leave behind, covering all five of the
# heading's gherkin scenarios in one tenant.
_EXPECTED_TENANT: dict[str, tuple[str, str]] = {
    # Case 1 — an `open` row with no rank is adopted into `backlog` AND ranked.
    _ADOPTED_RANKLESS: ("backlog", _FIRST_ASSIGNED_RANK),
    # Case 2 — an `in_progress` row is adopted into `active` (and, being
    # rank-less too, takes the next insert below the first).
    _ADOPTED_CLAIM: ("active", _SECOND_ASSIGNED_RANK),
    # Case 3 — an `open` row that already carries a real rank keeps it.
    _ADOPTED_RANKED: ("backlog", _KEPT_RANK),
    # Case 4 — a `deferred` row is left untouched, with no rank assigned.
    _PARKED: ("deferred", BOTTOM_SENTINEL),
    # The insert is a single insert, not a rebalance: no OTHER row is re-keyed.
    _UNTOUCHED_LIVE: ("ready", _LIVE_MAX_RANK),
    _CLOSED: ("done", _CLOSED_RANK),
}

_CADENCES = ("loop", "dispatch", "ledger-normalize", "ledger-normalize --gate")


@pytest.fixture(autouse=True)
def _fake_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    """A fresh in-memory tenant per case, plus an attributed invoker."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:ledger-adoption-rank-scenario126")
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


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ADOPTED_RANKLESS,
        type="task",
        status="open",
        title="A row a non-lifecycle writer left at a beads-native status",
        description="Adopt me.",
        origin="freeform",
        gap_id=None,
        # The adapter's read-time substitute for "metadata carries no rank" —
        # exactly what a raw `bd create` or a CI write ingress leaves behind.
        rank=BOTTOM_SENTINEL,
        assignee=None,
        depends_on=(),
        captured_at="2026-09-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _seeded_items() -> list[WorkItem]:
    """The six rows of the fixture, in the order the tenant holds them."""
    return [
        _item(id=_ADOPTED_RANKLESS),
        _item(id=_ADOPTED_CLAIM, status="in_progress"),
        _item(id=_ADOPTED_RANKED, rank=_KEPT_RANK),
        _item(id=_PARKED, status="deferred"),
        _item(id=_UNTOUCHED_LIVE, status="ready", rank=_LIVE_MAX_RANK),
        _item(id=_CLOSED, status="done", rank=_CLOSED_RANK, resolution="completed"),
    ]


def _seed() -> None:
    for item in _seeded_items():
        append_work_item(path=_config(), item=item)


def _tenant() -> dict[str, tuple[str, str]]:
    """Every row's (status, rank) read back through the REAL store seam."""
    materialized = materialize_work_items(records=read_work_items(path=_config()))
    return {item.id: (str(item.status), item.rank) for item in materialized.values()}


def _repo(*, tmp_path: Path, name: str) -> Path:
    """A governed repository carrying only the connection prefix each cadence needs."""
    repo = tmp_path / name
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}),
        encoding="utf-8",
    )
    return repo


def _argv(*, cadence: str, repo: Path) -> list[str]:
    """The real argv for one cadence.

    The two dispatch-path cadences name the adopted item explicitly. Both
    normalize the ledger BEFORE they select anything, so each then refuses at
    its requested-item preflight (the item is `backlog`, not `ready`) — which is
    itself evidence the invocation reached PAST normalization rather than
    short-circuiting ahead of it.
    """
    if cadence == "loop":
        return ["loop", "--repo", str(repo), "--item", _ADOPTED_RANKLESS, "--budget", "1"]
    if cadence == "dispatch":
        return ["dispatch", "--repo", str(repo), "--item", _ADOPTED_RANKLESS]
    if cadence == "ledger-normalize":
        return ["ledger-normalize", "--project-root", str(repo)]
    return ["ledger-normalize", "--project-root", str(repo), "--gate"]


def test_scenario126_every_cadence_adopts_the_row_and_assigns_it_the_same_real_rank(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """All four normalization cadences leave the identical, correctly-ranked tenant."""
    outcomes: dict[str, dict[str, tuple[str, str]]] = {}
    for index, cadence in enumerate(_CADENCES):
        reset_fake_singleton()
        _seed()
        assert _tenant()[_ADOPTED_RANKLESS] == ("open", BOTTOM_SENTINEL)

        repo = _repo(tmp_path=tmp_path, name=f"repo-{index}")
        _ = main(argv=_argv(cadence=cadence, repo=repo))
        _ = capsys.readouterr()

        outcomes[cadence] = _tenant()

    for cadence, tenant in outcomes.items():
        assert tenant == _EXPECTED_TENANT, cadence
    assert list(outcomes.values()) == [_EXPECTED_TENANT] * len(_CADENCES)


def test_the_assigned_keys_are_distinct_and_sit_below_the_live_order(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each insert lands strictly below the live maximum and above no sentinel."""
    _seed()
    _ = main(argv=_argv(cadence="ledger-normalize", repo=_repo(tmp_path=tmp_path, name="repo")))
    _ = capsys.readouterr()

    tenant = _tenant()
    first = tenant[_ADOPTED_RANKLESS][1]
    second = tenant[_ADOPTED_CLAIM][1]
    assert first != second
    for assigned in (first, second):
        assert assigned != BOTTOM_SENTINEL
        assert assigned > _LIVE_MAX_RANK
        assert assigned < BOTTOM_SENTINEL
    # Below the live maximum, and below the FIRST insert for the second row —
    # so the two adopted rows carry a total order rather than a tie.
    assert first < second


def test_the_ledger_normalize_cli_reports_the_rank_it_assigned(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The machine surface carries the assigned key beside the status transition."""
    _seed()
    argv = _argv(cadence="ledger-normalize", repo=_repo(tmp_path=tmp_path, name="repo"))

    exit_code = main(argv=[*argv, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    adoptions = {entry["item_id"]: entry for entry in payload["remapped"]}
    assert adoptions[_ADOPTED_RANKLESS]["rank"] == _FIRST_ASSIGNED_RANK
    assert adoptions[_ADOPTED_CLAIM]["rank"] == _SECOND_ASSIGNED_RANK
    # An already-ranked row is adopted with NO rank key at all, which is what
    # says the plan asked for no re-key rather than asking for the same key.
    assert "rank" not in adoptions[_ADOPTED_RANKED]


def test_the_planner_and_projection_stay_pure_over_the_same_rows() -> None:
    """Planning and projecting assign the same ranks and mutate no store row."""
    _seed()
    items = _seeded_items()
    before = _tenant()

    plan = plan_native_status_remaps(items=items)
    projected = project_native_status_remaps(items=items, remaps=plan)

    assert {item.id: (str(item.status), item.rank) for item in projected} == _EXPECTED_TENANT
    # The pure pair decided everything above without touching the tenant.
    assert _tenant() == before
