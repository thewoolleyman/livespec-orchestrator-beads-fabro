"""Integration-tier acceptance for the named-workflow-variant scenario.

Binds `SPECIFICATION/scenarios.md` "Named workflow variants resolve by
recorded precedence and refuse before any run" and the contract it realizes,
`SPECIFICATION/contracts.md` section "Named workflow variants" together with
the resolution order of section "Target-local workflow". Every case drives the
real `dispatcher.main(argv=["dispatch", ...])` CLI over a real on-disk journal
and the real store/client seam against the in-memory `FakeBeadsClient`; only
`run_dispatch` is stood in, so no fabro sandbox launches. The ledger pin, the
registry parse, the precedence and the three refusals are all production code.

WHAT IS MEASURED, AND WHY IT IS THE DISPATCH RECORD. The resolution's answer is
two values, not one, and neither is recoverable from the other: `workflow_name`
says which registered variant was selected, `workflow_toml` says which committed
file that selection resolved to. Asserting only the name would pass for a
dispatch that selected `fast` and then ran the bundle, and asserting only the
path would pass for one that reached the right directory under the wrong name.
Both ride the `dispatch-id` record, which is written immediately before the run
is launched, so it is also the discriminator the refusal cases use in the
negative: a refusal that fires before any Fabro run exists leaves NO
`dispatch-id` record at all.

THE REFUSAL CASES ASSERT NO-RUN ON TWO INDEPENDENT INSTRUMENTS. The recording
`run_dispatch` stand-in proves the launch seam was never entered, and the
absent `dispatch-id` stage proves the dispatch never reached the point of
recording a run. Either alone would be satisfied by a dispatch that failed for
some unrelated reason, which is why each case also pins the refusal's OWN
journal stage: the three faults share one exit code, so the stage is the only
thing that says which registry fault refused.

THE DEFAULT-VERSUS-RESERVED CASE CARRIES A CONTROL, because "the dispatch
resolved `slow`" is evidence that `dispatcher.default_workflow` outranks the
reserved name only if the reserved name is what the SAME repository resolves
once the default is removed. The control leg deletes that one key and asserts
the target's own committed `implement-work-item` workflow wins instead.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import record_dispatch_workflow
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_variant import (
    WORKFLOW_VARIANT_INCOMPLETE_STAGE,
    WORKFLOW_VARIANT_RESERVED_NAME_STAGE,
    WORKFLOW_VARIANT_UNREGISTERED_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variants import RESERVED_WORKFLOW_NAME
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-variants"
_DISPATCH_ID_STAGE = "dispatch-id"

_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)

# A complete variant is a whole directory: the manifest, the graph it names,
# and nothing merged in from the bundle. `workflow.fabro` is BOTH the graph and
# the file the completeness refusal looks for, so a directory holding only the
# manifest is exactly the incomplete shape the contract refuses.
_WORKFLOW_TOML = '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "fabro-sandbox"\n'
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

_FAST_DIR = ".fabro/workflows/fast"
_SLOW_DIR = ".fabro/workflows/slow"
_BROKEN_DIR = ".fabro/workflows/broken"
_RESERVED_DIR = f".fabro/workflows/{RESERVED_WORKFLOW_NAME}"


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic C-mode dispatch environment + fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("named-workflow-variants")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:named-workflow-variants")
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
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed_item() -> WorkItem:
    """One dispatchable item, filed through the real store seam."""
    item = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="pending-approval",
        title="A dispatched slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatch record names the resolved workflow variant.",
    )
    append_work_item(path=_config(), item=item)
    return item


def _write_workflow(*, repo: Path, directory: str, complete: bool = True) -> Path:
    """Materialize one workflow directory, optionally missing its graph."""
    workflow = repo / directory
    workflow.mkdir(parents=True)
    manifest = workflow / "workflow.toml"
    _ = manifest.write_text(_WORKFLOW_TOML, encoding="utf-8")
    if complete:
        _ = (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    return manifest


def _repo(
    *,
    tmp_path: Path,
    workflows: dict[str, str],
    default_workflow: str | None = None,
    complete: Sequence[str] = (),
    incomplete: Sequence[str] = (),
) -> Path:
    """A dispatch target declaring `workflows` and carrying the named directories.

    Every leg also carries the target's own committed reserved workflow, so the
    reserved name resolves to a hermetic path in this tmp tree rather than to
    the plugin's bundled one — which is what lets the default-versus-reserved
    control assert a SPECIFIC winner instead of merely "not `slow`".
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    dispatcher: dict[str, object] = {"workflows": workflows}
    if default_workflow is not None:
        dispatcher["default_workflow"] = default_workflow
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Chad Woolley",
                    "operator_email": "thewoolleyman@gmail.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": dispatcher,
                },
            }
        ),
        encoding="utf-8",
    )
    for directory in (_RESERVED_DIR, *complete):
        _ = _write_workflow(repo=repo, directory=directory)
    for directory in incomplete:
        _ = _write_workflow(repo=repo, directory=directory, complete=False)
    return repo


def _registered_repo(*, tmp_path: Path, default_workflow: str | None = "slow") -> Path:
    """The two-variant target every precedence case resolves against."""
    return _repo(
        tmp_path=tmp_path,
        workflows={"fast": _FAST_DIR, "slow": _SLOW_DIR},
        default_workflow=default_workflow,
        complete=(_FAST_DIR, _SLOW_DIR),
    )


def _recording_run_dispatch(*, calls: list[str]) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in recording that a run WAS launched."""

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


def _records(*, repo: Path) -> list[dict[str, object]]:
    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def _stages(*, repo: Path) -> list[str]:
    return [str(record.get("stage")) for record in _records(repo=repo)]


def _outcome_record(*, repo: Path) -> dict[str, object]:
    """The terminal outcome record, whose own `stage` is the refusal's stage.

    A pre-run refusal does NOT append a top-level record named for its stage:
    `failed_dispatch_outcome` journals one `outcome` record carrying the stage
    inside it. Reading the outer `stage` field instead is a probe that can only
    fail, which is why the lookup lives here rather than in each case.
    """
    written = [record for record in _records(repo=repo) if record.get("stage") == "outcome"]
    assert len(written) == 1
    outcome = written[0]["outcome"]
    assert isinstance(outcome, dict)
    return cast("dict[str, object]", outcome)


def _dispatch_record(*, repo: Path) -> dict[str, object]:
    written = [
        record for record in _records(repo=repo) if record.get("stage") == _DISPATCH_ID_STAGE
    ]
    assert len(written) == 1
    return written[0]


def _dispatch(*, repo: Path, workflow: Path | None = None, name: str | None = None) -> int:
    argv = ["dispatch", "--repo", str(repo), "--item", _ITEM_ID, "--no-close-on-merge"]
    if workflow is not None:
        argv += ["--workflow", str(workflow)]
    if name is not None:
        argv += ["--workflow-name", name]
    return main(argv=argv)


def _resolved(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    workflow: Path | None = None,
    name: str | None = None,
) -> tuple[str, str]:
    """Drive one dispatch and read back the variant name and committed path."""
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording_run_dispatch(calls=calls))

    _ = _dispatch(repo=repo, workflow=workflow, name=name)

    # The run WAS launched, which is what makes the recorded resolution the
    # resolution a real dispatch would have carried into the sandbox.
    assert calls == [_ITEM_ID]
    record = _dispatch_record(repo=repo)
    return str(record["workflow_name"]), str(record["workflow_toml"])


def test_an_explicit_workflow_path_outranks_the_recorded_workflow_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The raw-path escape hatch wins, and the selected name still rides beside it."""
    _ = _seed_item()
    repo = _registered_repo(tmp_path=tmp_path)
    explicit = _write_workflow(repo=tmp_path, directory="explicit")

    name, committed = _resolved(repo=repo, monkeypatch=monkeypatch, workflow=explicit, name="fast")

    # The path is the explicit one, NOT the `fast` variant's directory — while
    # `fast` is still the name recorded, so the two values are shown to be
    # independent rather than one derived from the other.
    assert committed == str(explicit)
    assert committed != str(repo / _FAST_DIR / "workflow.toml")
    assert name == "fast"


def test_the_recorded_workflow_name_outranks_the_items_dispatch_workflow_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--workflow-name` wins over the name a prior dispatch pinned to the item."""
    _ = _seed_item()
    repo = _registered_repo(tmp_path=tmp_path)
    # The pin a prior dispatch would have left, written through the production
    # writer rather than hand-assembled metadata.
    record_dispatch_workflow(path=_config(), work_item_id=_ITEM_ID, workflow="slow")

    name, committed = _resolved(repo=repo, monkeypatch=monkeypatch, name="fast")

    assert name == "fast"
    assert committed == str(repo / _FAST_DIR / "workflow.toml")


def test_the_dispatch_workflow_pin_outranks_the_configured_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry with no argument re-runs the variant the first attempt ran."""
    _ = _seed_item()
    repo = _registered_repo(tmp_path=tmp_path, default_workflow="slow")
    record_dispatch_workflow(path=_config(), work_item_id=_ITEM_ID, workflow="fast")

    name, committed = _resolved(repo=repo, monkeypatch=monkeypatch)

    assert name == "fast"
    assert committed == str(repo / _FAST_DIR / "workflow.toml")


def test_the_configured_default_outranks_the_reserved_workflow_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`dispatcher.default_workflow` wins when nothing more specific chooses."""
    _ = _seed_item()
    repo = _registered_repo(tmp_path=tmp_path, default_workflow="slow")

    name, committed = _resolved(repo=repo, monkeypatch=monkeypatch)

    assert name == "slow"
    assert committed == str(repo / _SLOW_DIR / "workflow.toml")


def test_the_reserved_name_is_what_the_same_target_resolves_without_a_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control for the case above: drop the one key and the reserved name wins.

    Without it, "the dispatch resolved `slow`" would be equally consistent with
    a default that outranks the reserved name and with one that is simply the
    only thing this target could ever resolve.
    """
    _ = _seed_item()
    repo = _registered_repo(tmp_path=tmp_path, default_workflow=None)

    name, committed = _resolved(repo=repo, monkeypatch=monkeypatch)

    assert name == RESERVED_WORKFLOW_NAME
    assert committed == str(repo / _RESERVED_DIR / "workflow.toml")


@pytest.mark.parametrize(
    ("workflows", "incomplete", "selected", "stage", "named"),
    [
        pytest.param(
            {"fast": _FAST_DIR},
            (),
            "missing",
            WORKFLOW_VARIANT_UNREGISTERED_STAGE,
            "missing",
            id="unregistered-name",
        ),
        pytest.param(
            {"broken": _BROKEN_DIR},
            (_BROKEN_DIR,),
            "broken",
            WORKFLOW_VARIANT_INCOMPLETE_STAGE,
            "workflow.fabro",
            id="incomplete-directory",
        ),
        pytest.param(
            {RESERVED_WORKFLOW_NAME: _FAST_DIR},
            (),
            None,
            WORKFLOW_VARIANT_RESERVED_NAME_STAGE,
            RESERVED_WORKFLOW_NAME,
            id="reserved-name-redefined",
        ),
    ],
)
def test_a_registry_fault_refuses_under_its_own_stage_before_any_run_exists(
    workflows: dict[str, str],
    incomplete: tuple[str, ...],
    selected: str | None,
    stage: str,
    named: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each of the three registry faults refuses under its own journal stage.

    The stage is the discriminator, not the exit code: all three faults, and
    every other pre-run refusal, share one. `named` is what the scenario's own
    Then requires the refusal to name — the unregistered variant, the missing
    file, the reserved name — so a stage reached for the wrong reason cannot
    pass by matching the stage alone.
    """
    _ = _seed_item()
    repo = _repo(
        tmp_path=tmp_path,
        workflows=workflows,
        complete=tuple(
            directory for directory in workflows.values() if directory not in incomplete
        ),
        incomplete=incomplete,
    )
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording_run_dispatch(calls=calls))

    exit_code = _dispatch(repo=repo, name=selected)

    assert exit_code != 0
    outcome = _outcome_record(repo=repo)
    assert (outcome["status"], outcome["stage"]) == ("failed", stage)
    assert outcome["work_item_id"] == _ITEM_ID
    assert named in str(outcome["detail"])
    # No Fabro run exists, on two independent instruments: the launch seam was
    # never entered, and the dispatch never reached the record it writes
    # immediately before launching one.
    assert calls == []
    assert _DISPATCH_ID_STAGE not in _stages(repo=repo)
