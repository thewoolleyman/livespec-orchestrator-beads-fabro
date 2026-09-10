"""Integration-tier acceptance for the variant-aware pre-dispatch criteria wall.

The pre-dispatch acceptance-criteria wall of `SPECIFICATION/contracts.md`
section "Effective acceptance criteria" refuses an AI-dispositive item whose
effective criteria parse to zero gradeable assertions. A GROOM target has zero
by construction: section "Consensus-gated automated groom cut" sends a
`backlog` item through the groom door precisely because it is not yet
decomposed, and says outright that such an item "carries the approved draft in
place of an acceptance". The two clauses collided in the implementation, and
the wall refused every groom dispatch for the one property that defines a groom
target (measured 2026-09-07 on `bd-ib-z2ctra`: `loop --item` -> exit 5).

WHAT IS MEASURED, AND WHY BOTH LEGS ARE HERE. The exemption is worthless as a
one-sided assertion: a wall that stopped firing altogether would satisfy "the
groom dispatch launched" perfectly. Every case therefore comes in a pair over
ONE fixture repository holding BOTH a groom-kind and an implement-kind variant,
differing only in the item's `dispatch_workflow` pin -- the groom-pinned leg
launches a run, the implement-pinned leg still refuses with the dedicated exit
code. The pin is written through the PRODUCTION writer, not hand-assembled
metadata, so the leg the field hit is the leg under test.

THE LAUNCH IS ASSERTED ON THE RECORDING STAND-IN, not on the exit code. A
dispatch can exit 0 without launching anything, and the whole point of the wall
is what happens BEFORE any factory run exists, so "a run was created" has to be
read off the launch seam itself. The refusing leg reads the same instrument in
the negative and pins the exit code as well, because a refusal for some
unrelated precondition would leave the identical empty launch list.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import record_dispatch_workflow
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-groomwall"
_EXIT_PRECONDITION_ERROR = 3
_EXIT_UNGRADEABLE_CRITERIA = 5

_GROOM_VARIANT = "groom-cut"
_IMPLEMENT_VARIANT = "slice"
_GROOM_DIR = f".fabro/workflows/{_GROOM_VARIANT}"
_IMPLEMENT_DIR = f".fabro/workflows/{_IMPLEMENT_VARIANT}"
_RESERVED_DIR = ".fabro/workflows/implement-work-item"

_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)

# The kind rides `[run.inputs]`, which is where `_workflow_variant_kind` reads
# it from. The implement leg declares NOTHING rather than declaring `implement`
# explicitly, because an undeclared kind is what every variant registered
# before that key existed looks like — the shape the exemption must not open on.
_GROOM_WORKFLOW_TOML = (
    '[workflow]\ngraph = "workflow.fabro"\n\n'
    '[run.environment]\nid = "fabro-sandbox"\n\n'
    '[run.inputs]\nworkflow_kind = "groom"\n'
)
_IMPLEMENT_WORKFLOW_TOML = (
    '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "fabro-sandbox"\n'
)

_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment + a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("groom-variant-criteria-wall")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:groom-variant-criteria-wall")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
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


def _seed_item() -> WorkItem:
    """One dispatchable item carrying NO gradeable acceptance criteria at all.

    Neither a criteria field nor a description `Exit criteria` section, so both
    legs of the effective-criteria resolution order come back empty — the exact
    shape a `backlog` epic arrives at the groom door in.
    """
    item = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="An epic awaiting decomposition",
        description="Decompose this into gradeable slices.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        # AI-dispositive, so the wall is armed: `human-only` is the per-item
        # escape the refusal names, and using it here would make every leg pass
        # for a reason that has nothing to do with the variant.
        acceptance_policy="ai-only",
        acceptance_criteria=None,
    )
    append_work_item(path=_config(), item=item)
    return item


def _write_workflow(*, repo: Path, directory: str, manifest_text: str) -> None:
    workflow = repo / directory
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(manifest_text, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")


def _repo(*, tmp_path: Path) -> Path:
    """One target registering both a groom-kind and an implement-kind variant."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Chad Woolley",
                    "operator_email": "thewoolleyman@gmail.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {
                        "wip_cap": 3,
                        "acceptance_mode": "ai-only",
                        "workflows": {
                            _GROOM_VARIANT: _GROOM_DIR,
                            _IMPLEMENT_VARIANT: _IMPLEMENT_DIR,
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    _write_workflow(repo=repo, directory=_GROOM_DIR, manifest_text=_GROOM_WORKFLOW_TOML)
    _write_workflow(repo=repo, directory=_IMPLEMENT_DIR, manifest_text=_IMPLEMENT_WORKFLOW_TOML)
    # The target's own reserved workflow, so a dispatch that named no variant
    # resolves inside this tmp tree rather than reaching the bundled payload.
    _write_workflow(repo=repo, directory=_RESERVED_DIR, manifest_text=_IMPLEMENT_WORKFLOW_TOML)
    return repo


def _recording_run_dispatch(*, calls: list[str]) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in recording that a factory run WAS created."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        calls.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="dispatched",
        )

    return _run_dispatch


def _dispatch(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    subcommand: str = "dispatch",
) -> tuple[int, list[str]]:
    """Drive one real dispatch and report its exit code plus what it launched."""
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording_run_dispatch(calls=calls))
    argv = [subcommand, "--repo", str(repo), "--item", _ITEM_ID, "--no-close-on-merge"]
    if subcommand == "loop":
        argv += ["--budget", "3"]
    return main(argv=argv), calls


def test_a_groom_pinned_target_with_no_criteria_still_reaches_the_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wall exempts a groom-kind dispatch and a run is created."""
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path)
    record_dispatch_workflow(path=_config(), work_item_id=_ITEM_ID, workflow=_GROOM_VARIANT)

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch)

    assert (exit_code, calls) == (0, [_ITEM_ID])
    assert exit_code != _EXIT_UNGRADEABLE_CRITERIA


def test_an_implement_pinned_target_with_no_criteria_is_still_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: the same item, the same repo, a non-groom variant, refused.

    Without this the exemption above is indistinguishable from a wall that was
    simply disarmed. The exit code is compared against the precondition code as
    well, because the whole point of a dedicated code is that it is DISTINCT.
    """
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path)
    record_dispatch_workflow(path=_config(), work_item_id=_ITEM_ID, workflow=_IMPLEMENT_VARIANT)

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch)

    assert (exit_code, calls) == (_EXIT_UNGRADEABLE_CRITERIA, [])
    assert exit_code != _EXIT_PRECONDITION_ERROR


def test_the_refusal_names_the_resolved_workflow_variant(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator can tell a groom-path refusal from an implement-path one."""
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path)
    record_dispatch_workflow(path=_config(), work_item_id=_ITEM_ID, workflow=_IMPLEMENT_VARIANT)

    _exit_code, _calls = _dispatch(repo=repo, monkeypatch=monkeypatch)

    stderr = capsys.readouterr().err
    assert _ITEM_ID in stderr
    assert "empty or ungradeable" in stderr
    assert _IMPLEMENT_VARIANT in stderr
    assert "kind implement" in stderr


def test_the_drain_exempts_the_same_groom_pinned_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exemption is a property of the candidate, so the drain honours it too.

    The two dispatch paths reach the wall through separate call sites, so an
    exemption wired into only one of them would leave the drain refusing exactly
    the item the door prepared for it.
    """
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path)
    record_dispatch_workflow(path=_config(), work_item_id=_ITEM_ID, workflow=_GROOM_VARIANT)

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch, subcommand="loop")

    assert (exit_code, calls) == (0, [_ITEM_ID])
