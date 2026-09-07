"""The variant the pre-dispatch criteria wall resolves, and how it fails.

Three properties, each of which fails invisibly in its own direction:

- a groom-kind resolution is EXEMPT, which is the whole point — a groom target
  has zero gradeable criteria by construction;
- an implement-kind resolution is NOT, so the wall keeps refusing exactly the
  dispatch it was built to refuse;
- an UNRESOLVABLE read answers `implement`, the armed side. Answering `groom`
  for an absent item or an unreadable config would let an environment fault
  open the gate, and the resulting pass would look identical to a deliberate
  exemption.

The preview's read-only-ness gets its own case because nothing else can catch
it: a wall that pinned would record a dispatch its own refusal then prevented,
and the pin it wrote would silently become the answer the NEXT attempt reused.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_dispatch_workflow import (
    dispatch_workflow_for,
    record_dispatch_workflow,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_criteria_wall_variant import (
    criteria_wall_variant,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import (
    WORKFLOW_KIND_GROOM,
    WORKFLOW_KIND_IMPLEMENT,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variants import RESERVED_WORKFLOW_NAME
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_GROOM_VARIANT = "groom-cut"
_IMPLEMENT_VARIANT = "slice"
_GROOM_DIR = f".fabro/workflows/{_GROOM_VARIANT}"
_IMPLEMENT_DIR = f".fabro/workflows/{_IMPLEMENT_VARIANT}"

_GROOM_WORKFLOW_TOML = (
    '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "groom"\n'
)
_IMPLEMENT_WORKFLOW_TOML = '[workflow]\ngraph = "workflow.fabro"\n'


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title="An epic awaiting decomposition",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _repo(*, tmp_path: Path) -> Path:
    """A target registering one groom-kind and one implement-kind variant."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {
                        "workflows": {
                            _GROOM_VARIANT: _GROOM_DIR,
                            _IMPLEMENT_VARIANT: _IMPLEMENT_DIR,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    _write_variant(repo=repo, directory=_GROOM_DIR, manifest_text=_GROOM_WORKFLOW_TOML)
    _write_variant(repo=repo, directory=_IMPLEMENT_DIR, manifest_text=_IMPLEMENT_WORKFLOW_TOML)
    return repo


def _write_variant(*, repo: Path, directory: str, manifest_text: str) -> None:
    variant = repo / directory
    variant.mkdir(parents=True)
    _ = (variant / "workflow.toml").write_text(manifest_text, encoding="utf-8")


def _pinned(*, item_id: str, workflow: str) -> None:
    append_work_item(path=_config(), item=_item(item_id=item_id))
    record_dispatch_workflow(path=_config(), work_item_id=item_id, workflow=workflow)


def test_a_groom_pinned_item_resolves_an_exempt_variant(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _pinned(item_id="bd-ib-wallgroom", workflow=_GROOM_VARIANT)

    variant = criteria_wall_variant(repo=repo, work_item_id="bd-ib-wallgroom")

    assert (variant.name, variant.kind, variant.exempt) == (
        _GROOM_VARIANT,
        WORKFLOW_KIND_GROOM,
        True,
    )


def test_an_implement_pinned_item_resolves_a_non_exempt_variant(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _pinned(item_id="bd-ib-wallimpl", workflow=_IMPLEMENT_VARIANT)

    variant = criteria_wall_variant(repo=repo, work_item_id="bd-ib-wallimpl")

    assert (variant.name, variant.kind, variant.exempt) == (
        _IMPLEMENT_VARIANT,
        WORKFLOW_KIND_IMPLEMENT,
        False,
    )


def test_an_explicit_workflow_name_outranks_the_items_pin(tmp_path: Path) -> None:
    """The dispatch's own `--workflow-name` is the most specific step.

    The pin says `slice` and the argument says `groom-cut`, so an exempt answer
    can only have come from the argument.
    """
    repo = _repo(tmp_path=tmp_path)
    _pinned(item_id="bd-ib-wallexplicit", workflow=_IMPLEMENT_VARIANT)

    variant = criteria_wall_variant(
        repo=repo, work_item_id="bd-ib-wallexplicit", workflow_name=_GROOM_VARIANT
    )

    assert (variant.name, variant.exempt) == (_GROOM_VARIANT, True)


def test_an_unresolvable_read_answers_the_armed_implement_side(tmp_path: Path) -> None:
    """An item absent from the tenant is an environment fault, not an exemption."""
    repo = _repo(tmp_path=tmp_path)

    variant = criteria_wall_variant(repo=repo, work_item_id="bd-ib-never-filed")

    assert (variant.name, variant.kind, variant.exempt) == (
        RESERVED_WORKFLOW_NAME,
        WORKFLOW_KIND_IMPLEMENT,
        False,
    )


def test_the_clause_names_the_variant_and_the_only_exempt_kind(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _pinned(item_id="bd-ib-wallclause", workflow=_IMPLEMENT_VARIANT)

    clause = criteria_wall_variant(repo=repo, work_item_id="bd-ib-wallclause").clause()

    assert _IMPLEMENT_VARIANT in clause
    assert f"kind {WORKFLOW_KIND_IMPLEMENT}" in clause
    assert f"{WORKFLOW_KIND_GROOM}-kind variant is exempt" in clause


def test_resolving_the_wall_variant_writes_no_pin(tmp_path: Path) -> None:
    """The wall asks which graph would run; it must not answer in the ledger.

    The item is pinned to `slice` and the wall is asked with an explicit
    `groom-cut`. A resolution that persisted would leave `groom-cut` behind and
    the NEXT dispatch would reuse it — a variant change made by a gate that
    exists only to refuse.
    """
    repo = _repo(tmp_path=tmp_path)
    _pinned(item_id="bd-ib-wallnowrite", workflow=_IMPLEMENT_VARIANT)

    _ = criteria_wall_variant(
        repo=repo, work_item_id="bd-ib-wallnowrite", workflow_name=_GROOM_VARIANT
    )

    assert (
        dispatch_workflow_for(path=_config(), work_item_id="bd-ib-wallnowrite")
        == _IMPLEMENT_VARIANT
    )
