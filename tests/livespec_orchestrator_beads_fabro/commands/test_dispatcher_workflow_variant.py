"""The three pre-run refusals a workflow-variant registry can earn.

`_workflow_variants` is total by design; `_dispatcher_workflow_variant` is
where a registry the Dispatcher cannot honour becomes a REFUSAL — one carrying
its own journal stage, in the same shape the ACP-node and node-timeout
refusals already take, and every one of them raised BEFORE any Fabro run
exists.

The three causes, and what each test has to prove is NOT happening instead:

- an unregistered selected name — must not quietly run the reserved graph;
- a registered directory missing `workflow.toml` or `workflow.fabro` — must
  not be merged with the bundle to fill the gap;
- a registry entry named `implement-work-item` — must not be silently inert.

The last one is checked FIRST in the implementation because it is a fault of
the table rather than of the selection, so it holds however the selection
resolves; the test that pins that ordering is the one where BOTH faults are
present at once.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_materialize import (
    MaterializationRefusal,
    materialize_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_variant import (
    WORKFLOW_VARIANT_INCOMPLETE_STAGE,
    WORKFLOW_VARIANT_NOT_GROOM_STAGE,
    WORKFLOW_VARIANT_RESERVED_NAME_STAGE,
    WORKFLOW_VARIANT_UNREGISTERED_STAGE,
    WorkflowVariantRefusal,
    prepare_workflow_variant,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variants import (
    RESERVED_WORKFLOW_NAME,
    WorkflowVariant,
)

_VARIANT_DIR = ".fabro/workflows/codex-first"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMITTED_WORKFLOW = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)
_GIT_AUTHOR = {"operator_name": "Operator", "operator_email": "operator@example.com"}


class _RecordingJournal:
    """Collects journal records so the dispatch record can be asserted on."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _write_dispatcher_config(*, repo: Path, block: dict[str, object]) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": _GIT_AUTHOR,
                "livespec-orchestrator-beads-fabro": {"dispatcher": block},
            }
        ),
        encoding="utf-8",
    )


def _registered_repo(*, tmp_path: Path, files: tuple[str, ...]) -> Path:
    """A target registering `codex-first` whose directory holds only `files`."""
    repo = tmp_path / "repo"
    variant = repo / _VARIANT_DIR
    variant.mkdir(parents=True)
    for name in files:
        _ = (variant / name).write_text(f"# {name}\n", encoding="utf-8")
    _write_dispatcher_config(
        repo=repo,
        block={"workflows": {"codex-first": _VARIANT_DIR}, "default_workflow": "codex-first"},
    )
    return repo


def test_a_target_declaring_no_registry_selects_the_reserved_variant(tmp_path: Path) -> None:
    """The unconfigured case reaches the reserved workflow with nothing refused."""
    assert prepare_workflow_variant(repo=tmp_path) == WorkflowVariant(
        name=RESERVED_WORKFLOW_NAME, directory=None
    )


def test_a_complete_registered_variant_resolves(tmp_path: Path) -> None:
    """A directory holding both the manifest and the graph is honoured."""
    repo = _registered_repo(tmp_path=tmp_path, files=("workflow.toml", "workflow.fabro"))

    assert prepare_workflow_variant(repo=repo) == WorkflowVariant(
        name="codex-first", directory=_VARIANT_DIR
    )


def test_an_unregistered_name_is_refused_naming_the_variant(tmp_path: Path) -> None:
    """Refusal one: the selected name matches no registry entry."""
    repo = _registered_repo(tmp_path=tmp_path, files=("workflow.toml", "workflow.fabro"))

    refusal = prepare_workflow_variant(repo=repo, name="typo-first")

    assert isinstance(refusal, WorkflowVariantRefusal)
    assert refusal.stage == WORKFLOW_VARIANT_UNREGISTERED_STAGE
    assert "typo-first" in refusal.detail
    assert "codex-first" in refusal.detail


def test_an_unregistered_name_against_an_empty_registry_says_so(tmp_path: Path) -> None:
    """The refusal names what IS registered, including when that is nothing."""
    refusal = prepare_workflow_variant(repo=tmp_path, name="codex-first")

    assert isinstance(refusal, WorkflowVariantRefusal)
    assert refusal.stage == WORKFLOW_VARIANT_UNREGISTERED_STAGE
    assert "registered: none" in refusal.detail


def test_a_directory_missing_the_graph_is_refused_naming_the_file(tmp_path: Path) -> None:
    """Refusal two: a registered directory that is not a complete workflow."""
    repo = _registered_repo(tmp_path=tmp_path, files=("workflow.toml",))

    refusal = prepare_workflow_variant(repo=repo)

    assert isinstance(refusal, WorkflowVariantRefusal)
    assert refusal.stage == WORKFLOW_VARIANT_INCOMPLETE_STAGE
    assert "workflow.fabro" in refusal.detail
    assert "codex-first" in refusal.detail


def test_a_directory_missing_the_manifest_is_refused_naming_the_file(tmp_path: Path) -> None:
    """The manifest half of refusal two, so neither file is the only one checked."""
    repo = _registered_repo(tmp_path=tmp_path, files=("workflow.fabro",))

    refusal = prepare_workflow_variant(repo=repo)

    assert isinstance(refusal, WorkflowVariantRefusal)
    assert refusal.stage == WORKFLOW_VARIANT_INCOMPLETE_STAGE
    assert "workflow.toml" in refusal.detail
    assert "workflow.fabro" not in refusal.detail


def test_an_empty_registered_directory_names_every_missing_file(tmp_path: Path) -> None:
    """One refusal enumerating every applicable cause, not the first one found."""
    repo = _registered_repo(tmp_path=tmp_path, files=())

    refusal = prepare_workflow_variant(repo=repo)

    assert isinstance(refusal, WorkflowVariantRefusal)
    assert refusal.stage == WORKFLOW_VARIANT_INCOMPLETE_STAGE
    assert "workflow.toml, workflow.fabro" in refusal.detail


def test_a_registry_entry_claiming_the_reserved_name_is_refused(tmp_path: Path) -> None:
    """Refusal three: the reserved name cannot be redefined by a registry entry."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_dispatcher_config(
        repo=repo, block={"workflows": {RESERVED_WORKFLOW_NAME: ".fabro/workflows/hijacked"}}
    )

    refusal = prepare_workflow_variant(repo=repo)

    assert isinstance(refusal, WorkflowVariantRefusal)
    assert refusal.stage == WORKFLOW_VARIANT_RESERVED_NAME_STAGE
    assert RESERVED_WORKFLOW_NAME in refusal.detail


def test_the_reserved_name_conflict_outranks_a_selection_fault(tmp_path: Path) -> None:
    """A table fault is reported as a table fault, whatever the selection does.

    Both faults are present: the registry claims the reserved name AND the
    selected name is unregistered. Reporting the selection would name an entry
    the operator never wrote while leaving the one they did write unmentioned.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_dispatcher_config(
        repo=repo, block={"workflows": {RESERVED_WORKFLOW_NAME: ".fabro/workflows/hijacked"}}
    )

    refusal = prepare_workflow_variant(repo=repo, name="typo-first")

    assert isinstance(refusal, WorkflowVariantRefusal)
    assert refusal.stage == WORKFLOW_VARIANT_RESERVED_NAME_STAGE


def test_materialize_dispatch_routes_a_variant_refusal_to_its_own_stage(
    tmp_path: Path,
) -> None:
    """The refusal reaches the dispatch record before any Fabro run exists.

    The payload and adapter steps share this call site, so the assertion that
    NOTHING was journaled is the load-bearing half: it proves the refusal
    happened at the first step rather than after a payload was materialized.
    """
    repo = _registered_repo(tmp_path=tmp_path, files=("workflow.toml",))
    journal = _RecordingJournal()

    refusal = materialize_dispatch(
        args=argparse.Namespace(workflow=None, repo=str(repo)),
        repo=repo,
        work_item_id="bd-ib-27puvv",
        journal=journal,
    )

    assert isinstance(refusal, MaterializationRefusal)
    assert refusal.stage == WORKFLOW_VARIANT_INCOMPLETE_STAGE
    assert journal.records == []


def test_materialize_dispatch_materializes_the_selected_variant_directory(
    tmp_path: Path,
) -> None:
    """The payload, graph render and adapter layers all read the SELECTED variant.

    The registered directory is a real copy of the shipped workflow, so the
    whole downstream chain genuinely runs against it. Its `workflow.toml` is
    then the file the dispatch materialized — which is what makes the existing
    `acp_nodes` / `node_timeouts` refusals apply to a variant as a peer of the
    reserved workflow rather than being evaluated against a bundle it is not
    running.
    """
    repo = tmp_path / "repo"
    variant = repo / _VARIANT_DIR
    variant.parent.mkdir(parents=True)
    _ = shutil.copytree(_COMMITTED_WORKFLOW.parent, variant)
    _write_dispatcher_config(
        repo=repo,
        block={"workflows": {"codex-first": _VARIANT_DIR}, "default_workflow": "codex-first"},
    )
    journal = _RecordingJournal()

    materialized = materialize_dispatch(
        args=argparse.Namespace(workflow=None, repo=str(repo)),
        repo=repo,
        work_item_id="bd-ib-27puvv",
        journal=journal,
    )

    assert not isinstance(materialized, MaterializationRefusal), materialized
    assert materialized.committed_workflow == variant / "workflow.toml"
    assert materialized.workflow_name == "codex-first"
    assert [record["stage"] for record in journal.records] == ["node-timeouts", "acp-nodes"]


def test_materialize_dispatch_selects_the_variant_named_on_the_namespace(
    tmp_path: Path,
) -> None:
    """The ledger-pinned name on the Namespace is what chooses the directory.

    The dispatch command paths overwrite `args.workflow_name` with the name
    the work-item is pinned to before calling here, so this is the seam the
    whole retry-consistency guarantee passes through: a materializer that
    ignored the Namespace would re-resolve `dispatcher.default_workflow` on
    every attempt and quietly move a half-finished item onto another graph.

    `default_workflow` is deliberately absent from the registry config, so
    the reserved workflow is what the unselected case would resolve — which
    makes the selected variant's directory the only way this assertion holds.
    """
    repo = tmp_path / "repo"
    variant = repo / _VARIANT_DIR
    variant.parent.mkdir(parents=True)
    _ = shutil.copytree(_COMMITTED_WORKFLOW.parent, variant)
    _write_dispatcher_config(repo=repo, block={"workflows": {"codex-first": _VARIANT_DIR}})
    journal = _RecordingJournal()

    materialized = materialize_dispatch(
        args=argparse.Namespace(workflow=None, repo=str(repo), workflow_name="codex-first"),
        repo=repo,
        work_item_id="bd-ib-u7arwz",
        journal=journal,
    )

    assert not isinstance(materialized, MaterializationRefusal), materialized
    assert materialized.committed_workflow == variant / "workflow.toml"
    assert materialized.workflow_name == "codex-first"


# --- The apply gate (v100): the FOURTH refusal, about the ITEM ---------------
#
# The three cases above are faults of the REGISTRY. This one is a fault of the
# combination: a work-item carrying an approved groom draft, resolving to a
# workflow that does not groom. It has its own stage for the same reason they
# do — the four share one exit code, so the stage is the only thing that says
# which fault refused.
#
# THE THREE ROUTES THE CONTRACT ENUMERATES ARE COVERED SEPARATELY, because the
# gate has to survive all three and they arrive by different mechanisms: an
# explicit `--workflow-name` naming the reserved workflow, the same naming a
# registered implement variant, and a CLEARED pin falling through to
# `dispatcher.default_workflow`. The third is the one a pin-keyed gate would
# miss — clearing the pin is precisely what disarms such a gate — so it is
# driven through `materialize_dispatch` end to end with a real ledger.


def _groom_manifest(*, kind: str) -> str:
    return f'[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "{kind}"\n'


def _kinded_repo(*, tmp_path: Path, default_workflow: str | None = None) -> Path:
    """A target registering one groom variant and one implement variant."""
    repo = tmp_path / "repo"
    for name, kind in (("groom-cut", "groom"), ("codex-first", "implement")):
        directory = repo / ".fabro" / "workflows" / name
        directory.mkdir(parents=True)
        _ = (directory / "workflow.toml").write_text(_groom_manifest(kind=kind), encoding="utf-8")
        _ = (directory / "workflow.fabro").write_text("digraph G {}\n", encoding="utf-8")
    block: dict[str, object] = {
        "workflows": {
            "groom-cut": ".fabro/workflows/groom-cut",
            "codex-first": ".fabro/workflows/codex-first",
        }
    }
    if default_workflow is not None:
        block["default_workflow"] = default_workflow
    _write_dispatcher_config(repo=repo, block=block)
    return repo


def test_an_approved_groom_draft_dispatched_under_its_groom_variant_resolves(
    tmp_path: Path,
) -> None:
    """The control: the gate must not refuse the dispatch it exists to protect."""
    repo = _kinded_repo(tmp_path=tmp_path)

    resolved = prepare_workflow_variant(
        repo=repo, name="groom-cut", approved_groom_draft="groom-cut"
    )

    assert resolved == WorkflowVariant(name="groom-cut", directory=".fabro/workflows/groom-cut")


def test_an_approved_groom_draft_dispatched_under_the_reserved_workflow_is_refused(
    tmp_path: Path,
) -> None:
    """The reserved workflow MUST NOT groom, however explicitly it is asked to."""
    repo = _kinded_repo(tmp_path=tmp_path)

    refusal = prepare_workflow_variant(
        repo=repo, name=RESERVED_WORKFLOW_NAME, approved_groom_draft="groom-cut"
    )

    assert isinstance(refusal, WorkflowVariantRefusal)
    assert refusal.stage == WORKFLOW_VARIANT_NOT_GROOM_STAGE
    assert "groom-cut" in refusal.detail


def test_an_approved_groom_draft_dispatched_under_an_implement_variant_is_refused(
    tmp_path: Path,
) -> None:
    """The refused variant is REGISTERED and COMPLETE; only its kind is wrong.

    A gate that checked registration or completeness would pass this case, so
    the assertion is on the stage rather than merely on there being a refusal.
    """
    repo = _kinded_repo(tmp_path=tmp_path)

    refusal = prepare_workflow_variant(
        repo=repo, name="codex-first", approved_groom_draft="groom-cut"
    )

    assert isinstance(refusal, WorkflowVariantRefusal)
    assert refusal.stage == WORKFLOW_VARIANT_NOT_GROOM_STAGE


def test_an_item_carrying_no_approved_draft_is_never_gated(tmp_path: Path) -> None:
    """Ordinary implement dispatches are untouched by the gate."""
    repo = _kinded_repo(tmp_path=tmp_path)

    resolved = prepare_workflow_variant(repo=repo, name="codex-first")

    assert resolved == WorkflowVariant(name="codex-first", directory=".fabro/workflows/codex-first")


def test_an_incomplete_directory_is_reported_as_incomplete_not_as_non_groom(
    tmp_path: Path,
) -> None:
    """An incomplete variant reads as `implement`, so ORDER decides which is named.

    Checking the kind before completeness would report "not a groom variant"
    for a directory whose real fault is that half of it is missing, sending the
    operator to fix the wrong thing.
    """
    repo = _registered_repo(tmp_path=tmp_path, files=("workflow.toml",))

    refusal = prepare_workflow_variant(
        repo=repo, name="codex-first", approved_groom_draft="groom-cut"
    )

    assert isinstance(refusal, WorkflowVariantRefusal)
    assert refusal.stage == WORKFLOW_VARIANT_INCOMPLETE_STAGE


def test_a_cleared_pin_falling_through_to_the_default_is_refused_end_to_end(
    tmp_path: Path,
) -> None:
    """The route a pin-keyed gate could not catch, driven through the ledger.

    Nothing on the item says `groom` any more — the pin is gone — so the ONLY
    surviving signal is the draft comment the park wrote, which is what the
    gate reads. The dispatch is driven through `materialize_dispatch` so the
    ledger read, the fall-through to `dispatcher.default_workflow` and the
    refusal are all production code, and the empty journal proves the refusal
    landed before any payload was materialized.
    """
    from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
    from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_draft import (
        render_groom_draft_comment,
    )
    from livespec_orchestrator_beads_fabro.commands._drive_answer import ANSWER_COMMENT_MARKER
    from livespec_orchestrator_beads_fabro.store import append_work_item, append_work_item_comment
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

    repo = _kinded_repo(tmp_path=tmp_path, default_workflow="codex-first")
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": _GIT_AUTHOR,
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "livespec-impl-beads",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "workflows": {
                            "groom-cut": ".fabro/workflows/groom-cut",
                            "codex-first": ".fabro/workflows/codex-first",
                        },
                        "default_workflow": "codex-first",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    config = StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )
    reset_fake_singleton()
    append_work_item(
        path=config,
        item=WorkItem(
            id="bd-ib-apply",
            type="task",
            status="ready",
            title="A groomed epic awaiting its apply dispatch",
            description="Its cut is drafted and approved.",
            origin="freeform",
            gap_id=None,
            rank="m",
            assignee=None,
            depends_on=(),
            captured_at="2026-09-06T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
        ),
    )
    append_work_item_comment(
        path=config,
        work_item_id="bd-ib-apply",
        body=render_groom_draft_comment(
            draft="Layer 1: slice A.",
            variant="groom-cut",
            run_id="01M1APPLY",
            at="2026-09-06T00:00:00Z",
        ),
    )
    append_work_item_comment(
        path=config,
        work_item_id="bd-ib-apply",
        body=(
            f"{ANSWER_COMMENT_MARKER} (human:maintainer via cli, "
            f"2026-09-06T00:00:00Z, resolve-blocked:bd-ib-apply:ready):\nApproved."
        ),
    )
    journal = _RecordingJournal()

    refusal = materialize_dispatch(
        args=argparse.Namespace(workflow=None, repo=str(repo)),
        repo=repo,
        work_item_id="bd-ib-apply",
        journal=journal,
    )

    assert isinstance(refusal, MaterializationRefusal)
    assert refusal.stage == WORKFLOW_VARIANT_NOT_GROOM_STAGE
    assert journal.records == []
