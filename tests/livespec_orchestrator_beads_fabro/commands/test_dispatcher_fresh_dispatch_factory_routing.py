"""A FRESH dispatch does not read the item's recorded factory as a pin.

`SPECIFICATION/contracts.md` section "Factory addresses resolved from a host
registry" fixes the selection order — an explicit `--factory`, then
`LIVESPEC_FABRO_FACTORY`, then, "for a resume only, the item's recorded
factory", then overflow selection or `dispatcher.default_factory` — and says
outright that "a fresh dispatch MUST NOT read the item's recorded factory as a
pin" and that the admission claim stamp "MUST apply the same order, using the
route recovery routing assigned before the admission valve".

WHY EVERY CASE SEEDS A RECORDED PIN THAT IS NOT THE DEFAULT. That is the state
the defect occurs in: an item that once ran on one factory routes back to it on
its next dispatch, however the repository's default has moved since. A case
whose pin names the default factory passes against a resolution that reads the
pin unconditionally, because there is then nothing for the pin to win — the two
answers coincide. The pin here is a STILL-DECLARED factory, for the same reason:
a name `dispatcher.factories` no longer declares is already ignored, so a case
built on a stale name cannot distinguish the rule from its one pre-existing
escape.

WHY THE STAMP AND THE SUBMISSION ARE ASSERTED TOGETHER. They are two resolutions
of one order, taken at different moments by different code — the pending claim
stamp at admission, through `unrecorded_dispatch_factory_target`, and the launch
through `args_with_dispatch_factory_target` — and the measured failure mode of
letting them drift is a claim held against a factory the run never reached. A
test that read only one of them would pass for a build that moved the other.

WHY THE ROUTE IS CONSTRUCTED RATHER THAN MEASURED. Recovery routing's own
decision is the subject of its own tests; what is under test here is what each
launch path DOES with the route it was handed. Handing the path a route also
makes the resume case expressible at all: a resume route is reached only through
a released item with a live anchor, which a unit tier cannot stage without
standing in for the forge.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimStamp, claim_row_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatching_host import (
    DISPATCHING_HOST_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_VERIFIED,
    ProofRecord,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_RESUME,
    ROUTE_SEEDED,
    RecoveryResume,
    RecoveryRoute,
    RecoverySeed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routing import RecoveryRouting
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    RESUMED_AT_PR,
    SOURCE_FACTORY_RUN,
    ResumeAnchor,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import ResumeGather
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    ResumeObservation,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    dispatch_factory_for,
    record_dispatch_factory,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_ITEM_ID = "bd-ib-freshfactory"
_HOST = "admitting-host"
_ENV_FACTORY_VAR = "LIVESPEC_FABRO_FACTORY"

# The repository's default, and the factory the item has been running on. They
# are deliberately DIFFERENT declared entries: see the module docstring.
_DEFAULT = "petri"
_DEFAULT_SERVER = "https://gmktec-xubuntu.perch-rudd.ts.net:32276"
_RECORDED = "hp"
_RECORDED_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"

# The published head and pull request the resume cases anchor on.
_HEAD = "0123456789abcdef0123456789abcdef01234567"
_PULL_REQUEST = 2600
_EARLIER_RUN = "01M5EARLIERRUNXXXXXXXXXXXX"

_LAUNCHED = DispatchOutcome(
    work_item_id=_ITEM_ID,
    status="succeeded",
    stage="done",
    pr_number=None,
    merge_sha=None,
    detail="stubbed launch",
)


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv(DISPATCHING_HOST_ENV_VAR, _HOST)
    monkeypatch.delenv(_ENV_FACTORY_VAR, raising=False)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        """
        {
          "livespec-orchestrator-beads-fabro": {
            "connection": {"prefix": "bd-ib", "tenant": "test-tenant", "fake": true},
            "dispatcher": {
              "default_factory": "petri",
              "factories": {
                "hp": {"server": "https://hp-xubuntu.perch-rudd.ts.net:32276"},
                "petri": {"server": "https://gmktec-xubuntu.perch-rudd.ts.net:32276"}
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="A dispatchable slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-23T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _seed_pinned(*, repo: Path) -> None:
    """Seed the row AND the recorded factory pin every case has to overcome."""
    append_work_item(path=store_config(repo=repo), item=_item())
    record_dispatch_factory(path=store_config(repo=repo), work_item_id=_ITEM_ID, factory=_RECORDED)


def _stamp_now(*, repo: Path) -> ClaimStamp | None:
    return claim_row_for(path=store_config(repo=repo), work_item_id=_ITEM_ID).stamp


def _launch_through(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    routing: RecoveryRouting,
    factory: str | None = None,
) -> argparse.Namespace:
    """Drive `dispatch --item`'s admit-and-launch step and return the launch args.

    Only what LEAVES the process is stood in for: the ledger status write, the
    dispatch-label read, the publish-branch reclaim and the Fabro launch itself.
    The admission valve, its claim stamp and the per-item argument pins all run
    for real, because they are between them the whole subject — a stubbed pin
    would make this a test of the stub's own answer.
    """
    launch_module = importlib.import_module(f"{_PACKAGE}._dispatcher_run_launch")
    eligibility_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    admission_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(launch_module, "post_admission_publish_branch_reclaim", lambda **_: None)
    launched: list[argparse.Namespace] = []

    def _dispatch(**kwargs: Any) -> DispatchOutcome:
        launched.append(kwargs["args"])
        return _LAUNCHED

    monkeypatch.setattr(launch_module, "dispatch_one", _dispatch)

    outcome = launch_module.admit_and_dispatch_target(
        args=argparse.Namespace(
            factory=factory,
            journal=None,
            fabro_bin=None,
            workflow_name=None,
        ),
        repo=repo,
        items=[],
        target=_item(),
        journal=JournalFile(path=repo / "journal.jsonl"),
        janitor=None,
        marked=False,
        routing=routing,
    )

    # The valve ADMITTED the target rather than holding or refusing it, which is
    # what makes the stamp and the launch args below this dispatch's own.
    assert outcome is _LAUNCHED
    return launched[0]


def test_a_fresh_dispatch_of_a_pinned_item_is_stamped_with_and_sent_to_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `fresh` route ignores the recorded pin, at the stamp and at the launch.

    The item records a still-declared factory that is NOT the configured
    default, nothing routes this dispatch, and recovery routing assigned it the
    `fresh` route — so the pin has no layer to win on and both resolutions must
    answer `dispatcher.default_factory`.

    The recorded pin is asserted to have MOVED as well, because the dispatch
    writes it: an item left recording the old factory would route back to it the
    next time any surface read that record as a pin.
    """
    repo = _repo(tmp_path=tmp_path)
    _seed_pinned(repo=repo)

    launched = _launch_through(
        repo=repo,
        monkeypatch=monkeypatch,
        routing=RecoveryRouting(routes=(RecoveryRoute(work_item_id=_ITEM_ID, route=ROUTE_FRESH),)),
    )

    stamp = _stamp_now(repo=repo)
    assert stamp is not None
    assert stamp.factory_name == _DEFAULT
    assert stamp.factory_server == _DEFAULT_SERVER
    assert launched.fabro_factory_target.name == _DEFAULT
    assert launched.fabro_factory_target.server == _DEFAULT_SERVER
    assert dispatch_factory_for(path=store_config(repo=repo), work_item_id=_ITEM_ID) == _DEFAULT


def _gather() -> ResumeGather:
    """One gathered resume measurement, as the command's own gather returns it."""
    return ResumeGather(
        observation=ResumeObservation(
            work_item_id=_ITEM_ID,
            status="ready",
            anchor_head=_HEAD,
            pull_request=_PULL_REQUEST,
            pull_request_state="OPEN",
            pull_request_head=_HEAD,
            liveness_observed=True,
        ),
        anchor=ResumeAnchor(
            record=ProofRecord(
                verdict=VERDICT_VERIFIED,
                run_id=_EARLIER_RUN,
                timestamp="2026-10-23T01:50:00Z",
                url=f"https://forge.example/pull/{_PULL_REQUEST}#issuecomment-1",
                body=f"Publish-branch head: {_HEAD}\n",
            ),
            run_id=_EARLIER_RUN,
            head=_HEAD,
            resumed_at=RESUMED_AT_PR,
            source=SOURCE_FACTORY_RUN,
        ),
        branch=f"feat/{_ITEM_ID}",
        earlier_run_ids=(_EARLIER_RUN,),
        workflow_name=None,
    )


def _resume_route() -> RecoveryRoute:
    """The route recovery routing assigns an item it resumes.

    The payload is what a resume CARRIES rather than decoration: the launch sets
    the entry node and head from it, so a route naming the route word alone would
    exercise an arm no resume reaches.
    """
    return RecoveryRoute(
        work_item_id=_ITEM_ID,
        route=ROUTE_RESUME,
        resume=RecoveryResume(
            entry_node=RESUMED_AT_PR,
            head=_HEAD,
            pull_request=_PULL_REQUEST,
            earlier_run_ids=(_EARLIER_RUN,),
            source=SOURCE_FACTORY_RUN,
            workflow_name=None,
        ),
    )


def test_a_resume_routed_dispatch_is_stamped_with_and_sent_to_the_recorded_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `resume` route reads the recorded pin, at the stamp and at the launch.

    The resume is the one route that CONTINUES the run lineage the recorded
    factory belongs to, so the pin keeps its layer here and must beat
    `dispatcher.default_factory` — which is the paired half of the fresh case
    above, on the same fixture and the same recorded pin, so neither can be
    satisfied by a build that answers one name unconditionally.

    Driven through `dispatch --item`'s own admit-and-launch step rather than
    through `resume --item`, because this is the leg where recovery routing
    assigns the route INSIDE an ordinary dispatch: the route is a per-item value
    the launch path applies, and the clause's "a `dispatch` or `loop` pass whose
    recovery routing routes the item `resume`" is exactly that path.
    """
    repo = _repo(tmp_path=tmp_path)
    _seed_pinned(repo=repo)

    launched = _launch_through(
        repo=repo,
        monkeypatch=monkeypatch,
        routing=RecoveryRouting(routes=(_resume_route(),)),
    )

    stamp = _stamp_now(repo=repo)
    assert stamp is not None
    assert stamp.factory_name == _RECORDED
    assert stamp.factory_server == _RECORDED_SERVER
    assert launched.fabro_factory_target.name == _RECORDED
    assert launched.fabro_factory_target.server == _RECORDED_SERVER
    assert dispatch_factory_for(path=store_config(repo=repo), work_item_id=_ITEM_ID) == _RECORDED


def test_the_resume_command_is_stamped_with_and_sent_to_the_recorded_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`resume --item` is the OTHER resume leg, and it carries no route value.

    The clause names two ways a dispatch's route is resume, and the second is an
    invocation of the resume command itself — which never consults recovery
    routing, so nothing on that path carries a `RecoveryRoute` for the pin layer
    to be read off. It is therefore its own case rather than a variation of the
    one above: a build that threaded the route only through the launch paths
    satisfies that case and sends every `resume --item` to the default factory.

    The real admission valve and the real per-item factory pin run; only the
    measurement seams around this decision stand in — the preamble, the gather,
    the ladder, the pre-dispatch wall, the launch and the post-verdict tail —
    because the gather reaches the forge and the factory and the subject here is
    neither.
    """
    repo = _repo(tmp_path=tmp_path)
    _seed_pinned(repo=repo)
    resume_module = importlib.import_module(f"{_PACKAGE}._dispatcher_resume_command")
    eligibility_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    admission_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(resume_module, "dispatch_preamble", lambda **_: (None, None))
    monkeypatch.setattr(resume_module, "arm_otel_egress", lambda **_: None)
    monkeypatch.setattr(
        resume_module,
        "prepare",
        lambda **_: ([_item()], JournalFile(path=repo / "journal.jsonl")),
    )
    monkeypatch.setattr(resume_module, "gather_resume", lambda **_: _gather())
    monkeypatch.setattr(resume_module, "resume_refusals", lambda **_: ())
    monkeypatch.setattr(resume_module, "ShellCommandRunner", lambda: None)
    monkeypatch.setattr(resume_module, "pre_dispatch_wall_exit", lambda **_: None)
    monkeypatch.setattr(resume_module, "dispatch_tail_exit", lambda **_: 0)
    launched: list[argparse.Namespace] = []

    def _dispatch(**kwargs: Any) -> DispatchOutcome:
        launched.append(kwargs["args"])
        return _LAUNCHED

    monkeypatch.setattr(resume_module, "dispatch_one", _dispatch)

    exit_code = resume_module.run_resume_command(
        args=argparse.Namespace(
            repo=str(repo),
            item=_ITEM_ID,
            journal=str(repo / "journal.jsonl"),
            janitor=None,
            fabro_bin=None,
            factory=None,
            workflow=None,
            workflow_name=None,
            as_json=False,
        )
    )

    assert exit_code == 0
    stamp = _stamp_now(repo=repo)
    assert stamp is not None
    assert stamp.factory_name == _RECORDED
    assert stamp.factory_server == _RECORDED_SERVER
    assert launched[0].fabro_factory_target.name == _RECORDED
    assert launched[0].fabro_factory_target.server == _RECORDED_SERVER


def test_a_seeded_recovery_dispatch_of_a_pinned_item_is_sent_to_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `seeded` route is a FRESH dispatch, however much tree it starts from.

    "Every other dispatch is a FRESH dispatch, whatever entry point carries it:
    a `dispatch --item`, a `drive` action `impl:<id>` or a loop drain whose item
    recovery routing routes `seeded` or `fresh`" — so a seed starts a lineage of
    its own and the recorded pin has no layer to win on, even though the route
    checks out a commit the earlier run produced.

    A CONTROL rather than a case that could fail on its own: once the launch
    reads the route NAME, a `seeded` route answers `resume=False` by the same
    line a `fresh` one does, so nothing could have reddened it after the fresh
    case landed. What it guards is the near-miss the route's own payload invites
    — a launch that treats "carries a tree to start from" as a resume, which a
    `seeded` route does carry. Measured by mutation 2026-10-23: reading
    `route.resume is not None` instead of the route name is still correct and
    reds nothing, while reading `route.resume is not None or route.seed is not
    None` reds this case alone of the six.
    """
    repo = _repo(tmp_path=tmp_path)
    _seed_pinned(repo=repo)

    launched = _launch_through(
        repo=repo,
        monkeypatch=monkeypatch,
        routing=RecoveryRouting(
            routes=(
                RecoveryRoute(
                    work_item_id=_ITEM_ID,
                    route=ROUTE_SEEDED,
                    seed=RecoverySeed(
                        source_run_id=_EARLIER_RUN,
                        remote="origin",
                        commit_sha=_HEAD,
                        preservation_ref=f"refs/livespec/preserved/{_EARLIER_RUN}",
                    ),
                ),
            )
        ),
    )

    stamp = _stamp_now(repo=repo)
    assert stamp is not None
    assert stamp.factory_name == _DEFAULT
    assert launched.fabro_factory_target.name == _DEFAULT
    assert launched.fabro_factory_target.server == _DEFAULT_SERVER
    # The seed's own tree still travels, so the case is about the FACTORY rather
    # than about a route the launch failed to execute.
    assert launched.resume_head == _HEAD


@pytest.mark.parametrize("named_by", ["flag", "environment"])
def test_a_named_factory_outranks_the_recorded_pin_on_a_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, named_by: str
) -> None:
    """`--factory` and `LIVESPEC_FABRO_FACTORY` win "whatever factory the item recorded".

    Driven on a RESUME route deliberately: that is the one route where the
    recorded pin is a live layer, so it is the only state in which the two
    selections actually contest. On a fresh route the pin loses to the default
    anyway, and a case built there would pass for a build that read no explicit
    selection at all.

    CONTROLS, both of them: the explicit layers sat above the pin before this
    clause narrowed it and neither could have reddened. What they guard is the
    narrowing's own fail direction — a resume arm that returned the pin BEFORE
    consulting the two selections would satisfy the resume case above while
    silently ignoring the only routing mechanism `drive.py` has. Measured by
    mutation 2026-10-23: returning the usable recorded pin ahead of the explicit
    layers in the resume arm reds both rows and nothing else in the module.
    """
    repo = _repo(tmp_path=tmp_path)
    _seed_pinned(repo=repo)
    if named_by == "environment":
        monkeypatch.setenv(_ENV_FACTORY_VAR, _DEFAULT)

    launched = _launch_through(
        repo=repo,
        monkeypatch=monkeypatch,
        routing=RecoveryRouting(routes=(_resume_route(),)),
        factory=_DEFAULT if named_by == "flag" else None,
    )

    stamp = _stamp_now(repo=repo)
    assert stamp is not None
    assert stamp.factory_name == _DEFAULT
    assert stamp.factory_server == _DEFAULT_SERVER
    assert launched.fabro_factory_target.name == _DEFAULT
    assert launched.fabro_factory_target.server == _DEFAULT_SERVER
    assert dispatch_factory_for(path=store_config(repo=repo), work_item_id=_ITEM_ID) == _DEFAULT


def test_a_drain_wave_sends_its_resume_routed_item_to_the_recorded_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `loop` leg, which is a SEPARATE call site from `dispatch --item`'s.

    The clause names three ways a dispatch's route is resume and the drain is the
    third: "a `dispatch` or `loop` pass whose recovery routing routes the item
    `resume`". The two launch paths deliberately do not share one function, so
    each reads the route and hands it to the valve on its own line — which means
    a build that wired the targeted path and not the drain satisfies every case
    above while sending every drained resume to the default factory.

    This case was authored AFTER the implementation rather than against a Red of
    its own, so it rides the suite-green leg. The mutation that reds it —
    dropping the drain's own `resume_ids` hand-off — could not be measured here:
    this repository's TDD order guard refuses a product-file write while HEAD is
    a closed Green, which is the guard working as designed. What stands in its
    place is that the assertion is read off the valve's own write (the claim
    stamp) and the launch's own namespace, neither of which the drain supplies
    for the other.

    Recovery routing is HANDED rather than measured, exactly as in the cases
    above: its own decision has its own tests, and a resume route is reached only
    through a released item with a live anchor.
    """
    repo = _repo(tmp_path=tmp_path)
    _seed_pinned(repo=repo)
    wave_module = importlib.import_module(f"{_PACKAGE}._dispatcher_loop_wave")
    eligibility_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    admission_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    rework_module = importlib.import_module(f"{_PACKAGE}._dispatcher_rework_admission")
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(wave_module, "await_usable_credential", lambda **_: None)
    monkeypatch.setattr(wave_module, "resolve_acp_preflight", lambda **_: None)
    monkeypatch.setattr(wave_module, "post_admission_publish_branch_reclaim", lambda **_: None)
    monkeypatch.setattr(
        wave_module,
        "route_recovery",
        lambda **_: RecoveryRouting(routes=(_resume_route(),)),
    )
    launched: list[argparse.Namespace] = []

    def _dispatch(**kwargs: Any) -> DispatchOutcome:
        launched.append(kwargs["args"])
        return _LAUNCHED

    monkeypatch.setattr(wave_module, "dispatch_one", _dispatch)

    outcomes = wave_module.dispatch_loop_wave(
        args=argparse.Namespace(
            repo=str(repo),
            journal=str(repo / "journal.jsonl"),
            item=None,
            items=None,
            budget=1,
            parallel=1,
            factory=None,
            fabro_bin=None,
            workflow_name=None,
            as_json=False,
            dry_run=False,
            skip_ledger_check=True,
        ),
        repo=repo,
        items=[_item()],
        selected_candidates=[_item()],
        journal=JournalFile(path=repo / "journal.jsonl"),
        janitor=None,
        rework=rework_module.ReworkPass(scope_ids=frozenset()),
    )

    # The wave ADMITTED and launched the candidate rather than deferring it,
    # which is what makes the stamp and the namespace below this wave's own.
    assert outcomes == [_LAUNCHED]
    stamp = _stamp_now(repo=repo)
    assert stamp is not None
    assert stamp.factory_name == _RECORDED
    assert stamp.factory_server == _RECORDED_SERVER
    assert launched[0].fabro_factory_target.name == _RECORDED
    assert launched[0].fabro_factory_target.server == _RECORDED_SERVER
