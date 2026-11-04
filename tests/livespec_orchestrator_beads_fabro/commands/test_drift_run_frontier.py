"""The coverage frontier advances only behind a contiguous all-filed prefix.

Assertion 4 of `bd-ib-yvjxo4`: "The frontier advances to a merge only when
every finding of that merge and of every earlier merge is filed, and a merge
whose pass fails or that carries a held finding stops the frontier until every
finding of it is filed."

Read through the LANE rather than the pass, because the frontier IS the
completed drift coverage point on the committed anchor: a pass that computed
the right prefix and recorded the wrong point would satisfy every assertion
about its own return value while the next pass re-judged merges it had already
processed, or skipped merges it had not.

Four cases, and the first two are each other's control.

A scope whose EVERY merge is filed writes a completed record naming the NEWEST
of them. A scope with a FAILED merge under a later success writes the attempt
record alone, naming the failed merge, and the previous frontier stands — which
is the case the independent review of this plan's scoping required (research
note 005, finding 3: "a later successful pass can skip a failed merge"). Either
case alone is satisfied by a build that always does that one thing.

A merge carrying a HELD finding stops the frontier too, and for a different
reason from a failure: its pass SUCCEEDED, so a build keyed on failures alone
would advance straight past it. The contract is explicit that a held finding
"is NOT disposed".

And an EMPTY scope advances nothing: there is no merge to name, so a completed
record would have to invent a point. The previous frontier stands.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._detection_coverage import (
    ATTEMPT_MARKER_PREFIX,
    COMPLETED_MARKER_PREFIX,
    DRIFT_CAPTURE_OPERATION,
    DetectionRun,
    record_detection_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._drift_run import DriftRunSeams
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

if TYPE_CHECKING:
    from collections.abc import Iterator

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_ANCHOR = "bd-ib-anchor"
_TARGET = "## A governing heading"
_OLDER = "aaaaaaa1"
_NEWER = "bbbbbbb2"


@dataclass(kw_only=True)
class _GitRunner:
    """A `CommandRunner` whose `git show` can be made to fail for ONE merge."""

    merges: tuple[str, ...] = (_OLDER, _NEWER)
    unreadable: str | None = None
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        if argv[1] == "symbolic-ref":
            return CommandResult(exit_code=0, stdout="origin/master\n", stderr="")
        if argv[1] == "rev-list":
            return CommandResult(exit_code=0, stdout="\n".join(self.merges) + "\n", stderr="")
        if argv[-1] == self.unreadable:
            return CommandResult(exit_code=128, stdout="", stderr="bad object")
        return CommandResult(exit_code=0, stdout=f"a subject\n+ hunk {argv[-1]}\n", stderr="")


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> Iterator[None]:
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="t", prefix="bd-ib", server_user="u", database="d", bd_path="bd", fake=True
    )


def _seed_anchor() -> None:
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=_ANCHOR,
            type="task",
            status="backlog",
            title="anchor",
            description="d",
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee=None,
            depends_on=(),
            captured_at="2026-08-01T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            blocked_reason=None,
            factory_safety=None,
            admission_policy=None,
            acceptance_policy=None,
            spec_commitment_hint=None,
        ),
    )


def _record_prior_frontier(*, point: str) -> None:
    _ = record_detection_run(
        path=_config(),
        anchor=_ANCHOR,
        run=DetectionRun(
            operation=DRIFT_CAPTURE_OPERATION,
            scope=point,
            invoker="human:maintainer",
            outcome="succeeded",
            exit_code=0,
            coverage_point=point,
        ),
    )


def _unstated(prompt: str) -> str:
    _ = prompt
    return (
        f'{{"kind": "unstated", "stated_by": [], '
        f'"generalization_target": "{_TARGET}", "rationale": "r"}}'
    )


def _project(*, root: Path, cap: int = 5) -> Path:
    spec_root = root / "SPECIFICATION"
    (spec_root / "proposed_changes").mkdir(parents=True)
    (spec_root / "history" / "v001" / "proposed_changes").mkdir(parents=True)
    _ = (spec_root / "contracts.md").write_text(f"{_TARGET}\n\ntext\n", encoding="utf-8")
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "t",
                        "prefix": "bd-ib",
                        "server_user": "u",
                        "database": "d",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "detection_coverage_anchor": _ANCHOR,
                        "drift_proposal_queue_cap": cap,
                    },
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return spec_root


def _lane(*, root: Path, runner: _GitRunner, judge: Callable[[str], str] = _unstated) -> object:
    import importlib

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_drift_lane"
    )
    return module.run_drift_lane(
        repo=root,
        invoker="reconcile-pass:test",
        seams=DriftRunSeams(runner=runner, judge=judge, now=lambda: "2026-10-22T00:00:00Z"),
    )


def _bodies(*, prefix: str) -> list[str]:
    return [
        str(comment["text"])
        for comment in make_beads_client(config=_config()).list_comments(issue_id=_ANCHOR)
        if str(comment["text"]).startswith(prefix)
    ]


def test_a_scope_whose_every_merge_is_filed_advances_to_the_newest_merge(
    tmp_path: Path,
) -> None:
    assert (_COMMANDS / "_drift_run_frontier.py").is_file()
    assert (_COMMANDS / "_dispatcher_reconcile_drift_lane.py").is_file()
    _ = _project(root=tmp_path)
    _seed_anchor()
    _record_prior_frontier(point="deadbeef")

    _ = _lane(root=tmp_path, runner=_GitRunner())

    completed = _bodies(prefix=COMPLETED_MARKER_PREFIX)
    assert len(completed) == 2
    assert f'"coverage_point": "{_NEWER}"' in completed[-1]


def test_a_failed_merge_stops_the_frontier_under_a_later_success(tmp_path: Path) -> None:
    assert (_COMMANDS / "_dispatcher_reconcile_drift_lane.py").is_file()
    _ = _project(root=tmp_path)
    _seed_anchor()
    _record_prior_frontier(point="deadbeef")

    _ = _lane(root=tmp_path, runner=_GitRunner(unreadable=_OLDER))

    completed = _bodies(prefix=COMPLETED_MARKER_PREFIX)
    attempts = _bodies(prefix=ATTEMPT_MARKER_PREFIX)
    # The previous frontier stands: the only completed record is still the
    # prior one, so the next pass re-enumerates both merges.
    assert len(completed) == 1
    assert '"coverage_point": "deadbeef"' in completed[0]
    assert any(_OLDER in body for body in attempts)


def test_a_merge_carrying_a_held_finding_stops_the_frontier(tmp_path: Path) -> None:
    assert (_COMMANDS / "_dispatcher_reconcile_drift_lane.py").is_file()
    spec_root = _project(root=tmp_path, cap=1)
    _seed_anchor()
    _record_prior_frontier(point="deadbeef")

    _ = _lane(root=tmp_path, runner=_GitRunner())

    # The older merge files, which fills the one-slot queue; the newer merge's
    # finding is held, and its pass SUCCEEDED — so a build keyed on failures
    # alone would advance the frontier straight past it.
    assert len(sorted((spec_root / "proposed_changes").glob("*.md"))) == 1
    completed = _bodies(prefix=COMPLETED_MARKER_PREFIX)
    assert len(completed) == 1
    assert '"coverage_point": "deadbeef"' in completed[0]


def test_an_empty_scope_advances_nothing(tmp_path: Path) -> None:
    assert (_COMMANDS / "_dispatcher_reconcile_drift_lane.py").is_file()
    _ = _project(root=tmp_path)
    _seed_anchor()
    _record_prior_frontier(point="deadbeef")

    _ = _lane(root=tmp_path, runner=_GitRunner(merges=()))

    assert len(_bodies(prefix=COMPLETED_MARKER_PREFIX)) == 1
