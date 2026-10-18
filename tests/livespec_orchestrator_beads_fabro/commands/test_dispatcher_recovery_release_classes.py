"""A provider-limit release routes exactly as a stall release does, measurement for
measurement.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" enumerates the release classes
in one breath and then says nothing further about them: "An item is *released for
recovery* when its latest journaled dispatch ended in a first-stall release (the
Dispatcher progress watchdog's own), a `provider-limit-release` record, or an
`adapter-launch-release` record." Every rule after that sentence is about the
MEASUREMENTS — the forge listing, the pull request's records, the factory board,
origin's refs — and none of them mentions which release got the item here.

WHY THIS NEEDS ITS OWN MODULE RATHER THAN A WIDER FIXTURE SOMEWHERE. Every routing
fixture in this directory ends its history in a `stall-cancel-release`, so the
whole route ladder is exercised against ONE release class. `RELEASE_STAGES` is a
frozenset and `released_for_recovery` is a fold over stage names, so a build that
recognised only the stall release would pass every one of those files and route a
provider-limit-released item `fresh` with no remote measurement at all — which is
precisely the loss that class exists to prevent, arriving silently and reading like
an ordinary first dispatch. Measured on this host 2026-10-16, four runs ended on an
Anthropic session limit with real preserved progress and only one was recovered,
by hand.

HOW THE PAIRING ISOLATES THE RELEASE CLASS, AND WHAT IT DOES NOT CLAIM. For each
world the two journals are byte-identical but for the release row's `stage`, and
the two passes answer the same scripted forge, factory and origin. So a difference
between them can only come from the release class, and an AGREEMENT is asserted on
both the route and the full command log — not the route alone, because two passes
that reached the same route by taking different measurements have not shown that
the class is irrelevant, they have shown that two different readings happened to
agree. The pairing is deliberately NOT a claim that either terminal writes exactly
these rows: each terminal's own record set is its own module's subject, and
reproducing them here would reintroduce the very difference these cases hold
constant.

WHY FOUR WORLDS. One world cannot distinguish "the release class is not read" from
"this world's route is reached whatever the history says" — the `fresh` route in
particular is also what an UNRELEASED item gets, so a build blind to the
provider-limit class produces the right answer there by accident. The four worlds
span the four routes the clause names, and the three non-`fresh` ones are each
reachable only from a release the pass recognised.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pytest

# Import order is load-bearing; see `test_dispatcher_recovery_routing_resume.py`
# for the cycle this leading import breaks.
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission as _admission,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_recovery_routing as routing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_records import (
    PROVIDER_LIMIT_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_HELD,
    ROUTE_RESUME,
    ROUTE_SEEDED,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    PUBLISH_HEAD_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_disposition import (
    STALL_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ = _admission

_ITEM_ID = "bd-ib-kn7ktk"
_BRANCH = f"feat/{_ITEM_ID}"
_RUN = "01M52R2WND7Y0000000000000Z"
_DISPATCH = "c1d2e3f405968788a9babbcbddcedfe0"
_PR = 3301

_PUBLISHED_HEAD = "db9feb3900000000000000000000000000000001"
_PRESERVED_COMMIT = "216c811200000000000000000000000000000002"
_PRESERVED_REF = f"refs/heads/needs-human/{_RUN}"

# The record a published run left on its pull request, which is what anchors a
# resume from EITHER release class: it lives on the forge rather than in the
# journal, so it is one of the measurements these cases hold constant.
_PROOF_BODY = (
    f"Proof of Done — verified — run {_RUN} — 2026-10-18T00:00:00Z\n"
    f"{PUBLISH_HEAD_LABEL}: {_PUBLISHED_HEAD}\n"
)

_RELEASE_STAGES = (STALL_RELEASE_STAGE, PROVIDER_LIMIT_RELEASE_STAGE)


class _Shell:
    """A scripted seam answering an empty exit 0 for anything a world omits.

    Class state for the reason every sibling module records: each party in the
    pass builds its own runner. `calls` is the whole point here rather than a
    convenience — the agreement these cases assert is an agreement about the
    MEASUREMENTS TAKEN, and only the command log carries that.
    """

    answers: ClassVar[dict[str, CommandResult]] = {}
    calls: ClassVar[list[str]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        joined = " ".join(argv)
        _Shell.calls.append(joined)
        for needle, result in _Shell.answers.items():
            if needle in joined:
                return result
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(frozen=True, kw_only=True)
class _World:
    """One scripted outside world, and the route every release class must reach in it."""

    name: str
    answers: dict[str, CommandResult]
    route: str


def _open_pull_request() -> CommandResult:
    return CommandResult(
        exit_code=0,
        stdout=json.dumps([{"number": _PR, "state": "OPEN", "headRefOid": _PUBLISHED_HEAD}]),
        stderr="",
    )


_NO_PULL_REQUEST = CommandResult(exit_code=0, stdout="[]", stderr="")


def _worlds() -> tuple[_World, ...]:
    """The four worlds, one per route the clause names.

    `held` fails the FIRST measurement, so it also pins that the release class is
    read before any of them: a pass that did not recognise the release would never
    ask the forge at all and would route `fresh` with an empty command log.
    """
    return (
        _World(
            name="held",
            answers={"gh pr list": CommandResult(exit_code=1, stdout="", stderr="boom")},
            route=ROUTE_HELD,
        ),
        _World(name="fresh", answers={"gh pr list": _NO_PULL_REQUEST}, route=ROUTE_FRESH),
        _World(
            name="seeded",
            answers={
                "gh pr list": _NO_PULL_REQUEST,
                "ls-remote origin refs/heads/needs-human/": CommandResult(
                    exit_code=0, stdout=f"{_PRESERVED_COMMIT}\t{_PRESERVED_REF}\n", stderr=""
                ),
            },
            route=ROUTE_SEEDED,
        ),
        _World(
            name="resume",
            answers={
                "gh pr list": _open_pull_request(),
                f"gh pr view {_PR} --json comments": CommandResult(
                    exit_code=0,
                    stdout=json.dumps({"comments": [{"body": _PROOF_BODY, "url": "u"}]}),
                    stderr="",
                ),
            },
            route=ROUTE_RESUME,
        ),
    )


def _work_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A released item awaiting recovery routing",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _history(*, release_stage: str) -> Sequence[dict[str, object]]:
    """One dispatch of the item that ended in `release_stage`, and nothing else.

    Identical across the two classes but for that one value, which is the whole
    construction: see this module's docstring for what the pairing isolates.
    """
    return (
        {
            "stage": "dispatch-id",
            "work_item_id": _ITEM_ID,
            "dispatch_id": _DISPATCH,
            "workflow_name": "implement-work-item",
        },
        {"stage": "fabro-run", "work_item_id": _ITEM_ID, "run_id": _RUN},
        {"stage": release_stage, "work_item_id": _ITEM_ID, "status": "ready", "run_id": _RUN},
    )


def _args(*, repo: Path, journal: JournalFile) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal.path),
        workflow_name="implement-work-item",
        fabro_bin="/usr/local/bin/fabro",
    )


@dataclass(frozen=True, kw_only=True)
class _Pass:
    """What one routing pass decided, and every command it took to decide it."""

    route: RecoveryRoute | None
    calls: tuple[str, ...]
    held_rows: tuple[dict[str, Any], ...]


def _route_once(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    world: _World,
    release_stage: str,
) -> _Pass:
    """Route the one candidate in `world`, from a history ending in `release_stage`."""
    journal = JournalFile(path=tmp_path / f"journal-{world.name}-{release_stage}.jsonl")
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in _history(release_stage=release_stage)),
        encoding="utf-8",
    )
    _Shell.answers = dict(world.answers)
    _Shell.calls = []
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)

    routed = routing.route_recovery(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        candidates=[_work_item()],
        journal=journal,
    )
    written = (
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    )
    return _Pass(
        route=routed.route_for(work_item_id=_ITEM_ID),
        calls=tuple(_Shell.calls),
        held_rows=tuple(one for one in written if one.get("stage") == "recovery-held"),
    )


@pytest.mark.parametrize("world", _worlds(), ids=lambda one: one.name)
def test_both_release_classes_route_identically_on_identical_measurements(
    world: _World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route, the command log and the hold record, compared class against class.

    The expected route is asserted FIRST, against the world's own declared answer,
    because an equality between two passes is satisfied just as well by two passes
    that are both wrong — and in this file the most likely way to be both wrong is
    the one the module docstring names: neither pass recognising its release and
    both routing `fresh` on an empty command log.
    """
    stall, provider_limit = (
        _route_once(tmp_path=tmp_path, monkeypatch=monkeypatch, world=world, release_stage=stage)
        for stage in _RELEASE_STAGES
    )

    assert stall.route is not None
    assert stall.route.route == world.route
    assert provider_limit.route == stall.route
    assert provider_limit.calls == stall.calls
    assert provider_limit.held_rows == stall.held_rows


def test_the_two_release_stages_under_comparison_are_not_the_same_string() -> None:
    """The instrument's own control: the pairing must compare two different classes.

    Both stage names are imported from the modules that WRITE them, so a rename
    moves both ends together — and if the two ever resolved to one value every
    case above would pass by comparing a reading with itself.
    """
    assert STALL_RELEASE_STAGE != PROVIDER_LIMIT_RELEASE_STAGE
    assert len(set(_RELEASE_STAGES)) == len(_RELEASE_STAGES)
