"""What a current seed ruling does to the route of a released or unreleased item.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" → "A ruled seed names the tree a
released item's next dispatch starts from". The sibling module
`test_dispatcher_recovery_ruled_seed` holds the plain seeded case; this module
holds every way a ruling meets another rule.

EVERY CASE PAIRS A RULING WITH A WORLD THAT HAS A DIFFERENT ANSWER WITHOUT ONE. The
control of each is the same world with no ruling, asserted first: a build that
ignored rulings entirely would satisfy a case whose world gave the ruled answer
anyway. The needs-human ref stands on origin in every world, so a route that falls
through to "another preserved tree" is visible as a seed naming it.

WHAT A HOLD MUST NOT DO IS ASSERTED, NOT ASSUMED. A ruled ref that is absent or
moved holds the item, and the three things the clause forbids it from doing —
seeding from the needs-human tree, seeding from the published head, routing
`fresh` — are each one the world makes available, so the assertion that the route
is `held` with no seed is evidence rather than the absence of a path.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import IssueDraft, make_beads_client
from livespec_orchestrator_beads_fabro.commands import _dispatcher_recovery_ruled_seed as ruled
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fresh_ruling import (
    fresh_ruling_comment_body,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import RECAPTURE_EXHAUSTED_MARKER
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_HELD,
    ROUTE_RESUME,
    ROUTE_SEEDED,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routing import (
    RecoveryRouting,
    route_recovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import (
    seed_ruling_comment_body,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsConnectionError,
    BeadsMappingError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = "bd-ib-ruled"
_RUN = "01RULEDRUN00000000000000A"
_DISPATCH = "d" * 32
_BRANCH = f"feat/{_ITEM}"
_PULL_REQUEST = 4001

_NH_REF = f"refs/heads/needs-human/{_RUN}"
_NH_COMMIT = "a1" * 20
_RULED_REF = f"refs/heads/rescue/{_ITEM}"
_RULED_SHA = "b2" * 20
_OTHER_REF = f"refs/heads/rescue-two/{_ITEM}"
_OTHER_SHA = "c3" * 20
_HEAD = "e0" * 20
_MOVED_SHA = "f4" * 40
_FIRST = "2026-11-10T01:00:00Z"
_SECOND = "2026-11-10T02:00:00Z"


@dataclass(frozen=True, kw_only=True)
class _World:
    """What the forge, the factory board and origin say."""

    refs: dict[str, str]
    pull_request_state: str | None = None
    live_run: bool = False
    failing_ls_remote: str | None = None


class _Origin:
    """A scripted origin, forge and factory board; an unscripted argv FAILS."""

    def __init__(self, *, world: _World) -> None:
        self.world = world

    def answer(self, *, argv: list[str]) -> CommandResult:
        joined = " ".join(argv)
        if argv[:3] == ["git", "ls-remote", "origin"]:
            if self.world.failing_ls_remote in argv[3:]:
                return CommandResult(exit_code=128, stdout="", stderr="fatal: unreachable")
            lines = [
                f"{commit}\t{ref}"
                for ref, commit in sorted(self.world.refs.items())
                if any(fnmatch.fnmatchcase(ref, pattern) for pattern in argv[3:])
            ]
            return CommandResult(exit_code=0, stdout="\n".join(lines), stderr="")
        if joined.startswith(f"gh pr list --head {_BRANCH}"):
            state = self.world.pull_request_state
            listed = (
                []
                if state is None
                else [{"number": _PULL_REQUEST, "state": state, "headRefOid": _HEAD}]
            )
            return CommandResult(exit_code=0, stdout=json.dumps(listed), stderr="")
        if joined.startswith(f"gh pr view {_PULL_REQUEST} --json comments"):
            return CommandResult(exit_code=0, stdout=json.dumps({"comments": []}), stderr="")
        if "ps -a --json" in joined or "inspect" in joined:
            running = [{"run_id": _RUN, "status": "running"}] if self.world.live_run else []
            return CommandResult(exit_code=0, stdout=json.dumps(running), stderr="")
        message = f"unscripted command reached the shell seam: {joined}"
        raise AssertionError(message)


def _work_item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status="ready",
        title="A released item an operator ruled a seed for",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _journal(*, tmp_path: Path, ending: str) -> JournalFile:
    """The item's dispatch history, ending the way the case says.

    `stall-anchored` is a first-stall release whose cancel record anchors a resume
    (pull request and head named); `stall` anchors nothing; `none` is a dispatch
    with no ending at all; `recapture-cancel` is a cancel the recovery-release
    reading excludes, so the item is NOT released by its journal.
    """
    anchor = {"pull_request": _PULL_REQUEST, "published_head": _HEAD}
    rows: list[dict[str, object]] = [
        {"stage": "dispatch-id", "work_item_id": _ITEM, "dispatch_id": _DISPATCH},
        {"stage": "fabro-run", "work_item_id": _ITEM, "run_id": _RUN},
    ]
    if ending in {"stall", "stall-anchored"}:
        rows.append(
            {
                "stage": "watchdog-stall-cancel",
                "work_item_id": _ITEM,
                "dispatch_id": _DISPATCH,
                "run_id": _RUN,
                "factory": "hp",
                "executing_stage": "proof_capture",
                **(anchor if ending == "stall-anchored" else {}),
            }
        )
        rows.append({"stage": "stall-cancel-release", "work_item_id": _ITEM, "status": "ready"})
    if ending == "recapture-cancel":
        outcome = {
            "work_item_id": _ITEM,
            "status": "cancelled",
            "detail": RECAPTURE_EXHAUSTED_MARKER,
        }
        rows.append({"stage": "outcome", "outcome": outcome})
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    _ = journal.path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")
    return journal


def _ruling(*, ref: str = _RULED_REF, sha: str = _RULED_SHA, instant: str = _FIRST) -> str:
    return seed_ruling_comment_body(
        work_item_id=_ITEM,
        preservation_ref=ref,
        commit_sha=sha,
        invoker="coordinator",
        reason="the ruled tree carries the checked work",
        instant=instant,
    )


def _consumed(*, marker: str, instant: str) -> str:
    return "\n".join((marker, f"ruling-instant: {instant}", "dispatch-id: x", "run-id: y"))


def _ledger(*, tmp_path: Path, comments: tuple[str, ...]) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    client = make_beads_client(config=store_config(repo=tmp_path))
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM,
            issue_type="task",
            title="A released item an operator ruled a seed for",
            description="",
            assignee=None,
            created_at="2026-11-10T00:00:00Z",
        )
    )
    for body in comments:
        client.add_comment(issue_id=_ITEM, body=body)


def _route(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    world: _World,
    comments: tuple[str, ...],
    ending: str = "stall",
) -> tuple[RecoveryRoute, RecoveryRouting, JournalFile]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    _ledger(tmp_path=tmp_path, comments=comments)
    origin = _Origin(world=world)

    def _run(
        _self: ShellCommandRunner,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        return origin.answer(argv=argv)

    monkeypatch.setattr(ShellCommandRunner, "run", _run)
    journal = _journal(tmp_path=tmp_path, ending=ending)
    routing = route_recovery(
        args=argparse.Namespace(
            repo=str(tmp_path),
            journal=str(journal.path),
            item=None,
            items=None,
            skip_ledger_check=True,
            workflow_name=None,
            fabro_bin="/usr/local/bin/fabro",
        ),
        repo=tmp_path,
        candidates=[_work_item()],
        journal=journal,
    )
    route = routing.route_for(work_item_id=_ITEM)
    assert route is not None
    return route, routing, journal


def _rows(*, journal: JournalFile, stage: str) -> list[dict[str, Any]]:
    written = (
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    )
    return [record for record in written if record.get("stage") == stage]


_TREES = {_NH_REF: _NH_COMMIT, _RULED_REF: _RULED_SHA}


def test_the_scripted_origin_refuses_a_command_no_case_scripted() -> None:
    """The instrument's own control: every claim below rests on this refusal firing."""
    with pytest.raises(AssertionError, match="unscripted command"):
        _ = _Origin(world=_World(refs={})).answer(argv=["git", "fetch", "origin"])


@pytest.mark.parametrize("ending", ["none", "recapture-cancel"])
def test_an_item_whose_dispatch_was_not_released_for_recovery_is_seeded_by_a_ruling(
    ending: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cancel the journal does not count as a release still yields to a ruling."""
    world = _World(refs=_TREES)
    control, _, _ = _route(
        tmp_path=tmp_path / "control",
        monkeypatch=monkeypatch,
        world=world,
        comments=(),
        ending=ending,
    )
    assert control.route == ROUTE_FRESH

    route, _, _ = _route(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        world=world,
        comments=(_ruling(),),
        ending=ending,
    )

    assert route.route == ROUTE_SEEDED
    assert route.seed is not None
    assert (route.seed.preservation_ref, route.seed.commit_sha) == (_RULED_REF, _RULED_SHA)


def test_a_ruling_outranks_a_resume_every_precondition_of_which_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _World(refs={**_TREES, f"refs/heads/{_BRANCH}": _HEAD}, pull_request_state="OPEN")
    control, _, _ = _route(
        tmp_path=tmp_path / "control",
        monkeypatch=monkeypatch,
        world=world,
        comments=(),
        ending="stall-anchored",
    )
    assert control.route == ROUTE_RESUME

    route, _, _ = _route(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        world=world,
        comments=(_ruling(),),
        ending="stall-anchored",
    )

    assert route.route == ROUTE_SEEDED
    assert route.resume is None
    assert route.seed is not None
    assert (route.seed.preservation_ref, route.seed.commit_sha) == (_RULED_REF, _RULED_SHA)


def test_a_current_fresh_ruling_routes_fresh_past_a_resumable_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh ruling wins even when every resume precondition would otherwise pass."""
    route, _, _ = _route(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        world=_World(refs={**_TREES, f"refs/heads/{_BRANCH}": _HEAD}, pull_request_state="OPEN"),
        comments=(
            fresh_ruling_comment_body(
                work_item_id=_ITEM,
                invoker="coordinator",
                reason="start from the default branch",
                instant=_SECOND,
            ),
        ),
        ending="stall-anchored",
    )

    assert route.route == ROUTE_FRESH
    assert route.resume is None
    assert route.seed is None


@pytest.mark.parametrize(
    ("refs", "observed"),
    [
        ({_NH_REF: _NH_COMMIT}, "absent"),
        ({_NH_REF: _NH_COMMIT, _RULED_REF: _MOVED_SHA}, _MOVED_SHA),
    ],
)
def test_a_ruled_ref_that_is_absent_or_moved_holds_the_item_and_names_what_origin_observed(
    refs: dict[str, str], observed: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    route, routing, journal = _route(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        world=_World(refs={**refs, f"refs/heads/{_BRANCH}": _HEAD}),
        comments=(_ruling(),),
    )

    assert route.route == ROUTE_HELD
    assert route.seed is None
    assert routing.offered(candidates=[_work_item()]) == []
    held = _rows(journal=journal, stage="recovery-held")
    assert len(held) == 1
    assert held[0]["measurements"] == ["seed-ruling-ref"]
    detail = str(held[0]["details"])
    assert _RULED_REF in detail
    assert _RULED_SHA in detail
    assert f"origin observed {observed}" in detail
    assert _rows(journal=journal, stage="recovery-route") == []
    report = routing.held_report(work_item_id=_ITEM)
    assert report is not None
    assert _RULED_REF in report


def test_a_ruled_ref_origin_cannot_be_read_is_the_unobservable_measurement_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    route, _, journal = _route(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        world=_World(refs=_TREES, failing_ls_remote=_RULED_REF),
        comments=(_ruling(),),
    )

    assert route.route == ROUTE_HELD
    assert route.seed is None
    held = _rows(journal=journal, stage="recovery-held")
    assert held[0]["measurements"] == ["preserved-work"]
    assert "absence is not confirmed" in str(held[0]["details"])
    assert "origin observed" not in str(held[0]["details"])


@pytest.mark.parametrize(
    ("world", "remedy"),
    [
        (
            _World(refs=_TREES, pull_request_state="MERGED"),
            f"reconcile-merged --item {_ITEM}",
        ),
        (_World(refs=_TREES, live_run=True), "still live on its factory"),
    ],
    ids=["merged-pull-request", "live-earlier-run"],
)
def test_a_non_fallback_refusal_keeps_its_precedence_over_a_ruling_at_the_ruled_commit(
    world: _World, remedy: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    route, _, journal = _route(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        world=world,
        comments=(_ruling(),),
        ending="stall-anchored",
    )

    assert route.route == ROUTE_HELD
    assert route.seed is None
    held = _rows(journal=journal, stage="recovery-held")
    assert held[0]["measurements"] == []
    refusals = [str(one) for one in held[0]["refusals"]]
    assert len(refusals) == 1
    assert remedy in refusals[0]


def test_the_dispatch_is_seeded_from_the_ref_the_later_of_two_rulings_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _World(refs={**_TREES, _OTHER_REF: _OTHER_SHA})
    earlier = _ruling(ref=_RULED_REF, sha=_RULED_SHA, instant=_FIRST)
    later = _ruling(ref=_OTHER_REF, sha=_OTHER_SHA, instant=_SECOND)

    route, _, _ = _route(
        tmp_path=tmp_path, monkeypatch=monkeypatch, world=world, comments=(earlier, later)
    )

    assert route.route == ROUTE_SEEDED
    assert route.seed is not None
    assert (route.seed.preservation_ref, route.seed.commit_sha) == (_OTHER_REF, _OTHER_SHA)


@pytest.mark.parametrize(
    "comments",
    [
        pytest.param(
            (_ruling(), _consumed(marker="livespec-seed-ruling-consumed", instant=_FIRST)),
            id="consumed",
        ),
        pytest.param(
            (
                _ruling(),
                fresh_ruling_comment_body(
                    work_item_id=_ITEM, invoker="coordinator", reason="start over", instant=_SECOND
                ),
            ),
            id="replaced-by-a-later-fresh-ruling",
        ),
    ],
)
def test_a_consumed_or_replaced_seed_ruling_no_longer_governs_the_route(
    comments: tuple[str, ...], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    route, _, _ = _route(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        world=_World(refs=_TREES),
        comments=comments,
    )

    assert route.route == ROUTE_SEEDED
    assert route.seed is not None
    assert route.seed.preservation_ref == _NH_REF


def test_an_unreadable_ledger_holds_the_item_rather_than_routing_past_a_ruling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _unreachable(**_: object) -> object:
        raise BeadsConnectionError(detail="dolt server unreachable")

    monkeypatch.setattr(ruled, "read_work_item_comments", _unreachable)

    route, _, journal = _route(
        tmp_path=tmp_path, monkeypatch=monkeypatch, world=_World(refs=_TREES), comments=()
    )

    assert route.route == ROUTE_HELD
    held = _rows(journal=journal, stage="recovery-held")
    assert held[0]["measurements"] == ["seed-ruling-comments"]
    assert _ITEM in str(held[0]["details"])


def test_an_unmappable_comments_response_holds_the_item_rather_than_routing_past_a_ruling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _unmappable(**_: object) -> object:
        raise BeadsMappingError(record_id=_ITEM, detail="bd comments returned an unmappable body")

    monkeypatch.setattr(ruled, "read_work_item_comments", _unmappable)

    route, _, journal = _route(
        tmp_path=tmp_path, monkeypatch=monkeypatch, world=_World(refs=_TREES), comments=()
    )

    assert route.route == ROUTE_HELD
    held = _rows(journal=journal, stage="recovery-held")
    assert held[0]["measurements"] == ["seed-ruling-comments"]
    assert _ITEM in str(held[0]["details"])
