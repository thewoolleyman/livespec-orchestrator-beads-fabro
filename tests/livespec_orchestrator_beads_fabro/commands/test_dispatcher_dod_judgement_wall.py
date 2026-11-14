"""Tests for the pre-dispatch Definition-of-Done judgement's two wall surfaces.

Scenario 174's dispatch-time sub-scenarios are bound at the integration tier by
`tests/integration/test_dod_judgement_pre_dispatch_scenario174.py`, which drives
the whole wall. This module covers the arms that tier cannot reach: a repository
whose ledger CONNECTION cannot be resolved at all, so neither surface has a
record to read a standing verdict from, and the drain filter's GROOM exemption,
which `tests/integration/test_groom_variant_dod_judgement.py` reaches only
through `dod_judgement_refusal` — every dispatch there names an `--item`, and a
named id is narrowed to rather than filtered, so the filter's own exemption is
only observable from an unnarrowed enumeration.

WHY THAT ARM IS WORTH ITS OWN CASE RATHER THAN BEING LEFT TO FAIL LOUDLY. Both
surfaces run inside a pass composed of many others — the wall renders refusals
for six independent preconditions, and drain enumeration runs over every ready
row in the tenant — so an unresolvable connection raising from here would
replace an actionable refusal with a traceback about the file it was about to
name. The clause's own requirement is the same: when the judgement cannot run,
the dispatch proceeds as it would without it.

WHY THE CONTROL IS THE SAME STORE READ TWICE. "The items came back unchanged" is
satisfied just as well by a filter that drops nothing at all, which is exactly
what a build with the judgement removed would do. Each case therefore asserts
the pass-through BESIDE a leg that DOES drop the row, over one process-singleton
store holding one recorded refusing verdict, so the two legs differ in nothing
but whether the repository declares a connection.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import record_dispatch_workflow
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    DodJudgement,
    judgement_subject_digest,
    rubric_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_DISPATCH,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    judgement_rubric,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_wall import (
    dod_unrefused_candidates,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_HEADING = "## Effective acceptance criteria"
_FINDING = "bd-ib-wall: the References line omits the governing scenario; add that heading."

_GROOM_VARIANT = "groom-cut"
_GROOM_DIR = f".fabro/workflows/{_GROOM_VARIANT}"
# The kind rides `[run.inputs]`, which is where `_workflow_variant_kind` reads it.
_GROOM_WORKFLOW_TOML = (
    '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "groom"\n'
)


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _spec_tree(*, repo: Path) -> Path:
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nThe criteria clause.\n", encoding="utf-8"
    )
    return repo


def _connected_repo(*, tmp_path: Path) -> Path:
    """A repository that declares the `connection.prefix` the resolution needs."""
    repo = _spec_tree(repo=tmp_path / "connected")
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _groom_registering_repo(*, tmp_path: Path) -> Path:
    """A connected repository that also REGISTERS a groom-kind variant.

    The registry entry and the variant's own `workflow.toml` are both needed:
    the kind is a property of the directory the entry names, not of the entry,
    so a registered name whose manifest declares nothing reads as `implement`.
    """
    repo = _spec_tree(repo=tmp_path / "groom")
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {"workflows": {_GROOM_VARIANT: _GROOM_DIR}},
                }
            }
        ),
        encoding="utf-8",
    )
    variant = repo / _GROOM_DIR
    variant.mkdir(parents=True)
    _ = (variant / "workflow.toml").write_text(_GROOM_WORKFLOW_TOML, encoding="utf-8")
    return repo


def _unresolvable_repo(*, tmp_path: Path) -> Path:
    """The same spec tree with NO `.livespec.jsonc`, so no connection resolves.

    The spec tree is identical on purpose: the judgement subject is rendered
    from the item plus the body of each heading its reference line names, so a
    repository missing the heading would differ in the DIGEST as well as in the
    connection and either difference alone could explain the answer.
    """
    return _spec_tree(repo=tmp_path / "unresolvable")


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-wall",
        type="feature",
        status="ready",
        title="A released slice",
        description=(
            "## Definition of Done\n"
            "\n"
            "- The dispatched slice lands its change.\n"
            "\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _executing_rubric_digest() -> str:
    """The digest of the EXECUTING build's rubric, which both wall surfaces read.

    Taken off the shipped file rather than written as a literal: the wall reads
    the executing payload, so a verdict standing against any other rubric is one
    it would correctly refuse to reuse — and this module's subject is what the
    wall does with a verdict that DOES stand.
    """
    rubric = judgement_rubric()
    assert rubric is not None
    return rubric_digest(rubric=rubric)


def _record_held_verdict(*, repo: Path, item: WorkItem) -> None:
    """Stand a refusing verdict against this item's current bytes and rubric."""
    config = _config(repo=repo)
    append_work_item(path=config, item=item)
    append_work_item_comment(
        path=config,
        work_item_id=item.id,
        body=verdict_comment(
            item_id=item.id,
            stage=STAGE_PRE_DISPATCH,
            digest=judgement_subject_digest(item=item, cwd=repo),
            rubric_digest=_executing_rubric_digest(),
            judgement=DodJudgement(outcome=JUDGEMENT_HELD, findings=(_FINDING,)),
        ),
    )


def test_an_unresolvable_connection_excludes_no_candidate_from_the_enumeration(
    tmp_path: Path,
) -> None:
    """A ledger nothing can be read from drops nothing, and the control drops."""
    connected = _connected_repo(tmp_path=tmp_path)
    item = _item()
    _record_held_verdict(repo=connected, item=item)

    # The control: with the connection resolved, the standing refusal is read
    # and the row leaves the enumeration. Without this leg, the assertion below
    # passes just as well for a filter that never drops anything.
    assert dod_unrefused_candidates(items=[item], repo=connected) == []

    assert dod_unrefused_candidates(items=[item], repo=_unresolvable_repo(tmp_path=tmp_path)) == [
        item
    ]


def test_a_groom_pinned_candidate_survives_a_standing_refusing_verdict(tmp_path: Path) -> None:
    """A groom target is retained however the recorded verdict reads.

    The refusal no longer takes a judgement on such an item, but a verdict
    recorded by an earlier build or at admission outlives the dispatch that
    wrote it — and the one change that would retire it is the decomposition the
    groom run has not been allowed to produce. The CONTROL is the same
    repository and the same standing verdict with no pin written, which must
    drop the row: without it, "the item was enumerated" is satisfied just as
    well by a filter that never drops anything.
    """
    repo = _groom_registering_repo(tmp_path=tmp_path)
    item = _item()
    _record_held_verdict(repo=repo, item=item)

    assert dod_unrefused_candidates(items=[item], repo=repo) == []

    record_dispatch_workflow(path=_config(repo=repo), work_item_id=item.id, workflow=_GROOM_VARIANT)

    assert dod_unrefused_candidates(items=[item], repo=repo) == [item]


def test_an_unresolvable_connection_preserves_the_callers_order(tmp_path: Path) -> None:
    """The pass-through hands back the caller's own order, not a re-sort.

    The canonical ranking authority is upstream, so a pass-through that
    re-ordered would put a second one behind the id a consumer reads off the
    result — and with one item the order assertion cannot fail.
    """
    ranked = [replace(_item(), id="bd-ib-wall-b", rank="a9"), _item()]

    assert (
        dod_unrefused_candidates(items=ranked, repo=_unresolvable_repo(tmp_path=tmp_path)) == ranked
    )
