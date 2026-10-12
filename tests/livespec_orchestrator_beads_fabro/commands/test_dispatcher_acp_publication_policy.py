"""Workflow-kind policy for the retired implementation `pr` ACP adapter.

The end-to-end journey — the refusal landing before any claim or run, on both
dispatch entry paths, with its two admitting controls — is bound at the
integration tier by
`tests/integration/test_publication_adapter_override_refusal_scenario86.py`.
These cases cover the decisions that tier cannot isolate: the per-item variant
grading, the malformed-override shape, and the value the journal row must not
carry.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_acp_publication_policy as policy
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_publication_policy import (
    ACP_PUBLICATION_POLICY_STAGE,
    GROOM_ONLY_ACP_NODES,
    IMPLEMENTATION_PR_NOT_APPLIED_REASON,
    PUBLICATION_ACP_NODE,
    implementation_pr_override_refusal,
    scoped_repository_block,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import (
    WORKFLOW_KIND_GROOM,
    WORKFLOW_KIND_IMPLEMENT,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title=item_id,
        description="publication policy fixture",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def test_repository_pr_is_scoped_only_for_implementation() -> None:
    """Four shapes, and only one of them loses the entry.

    The three non-dropping arms are asserted to return the block UNCHANGED
    rather than merely equal, because that identity is what keeps a groom
    dispatch — and an implementation dispatch against a repository configuring
    no `pr` — byte-identical to what it resolved before this policy existed.

    The dropping arm additionally asserts the CALLER'S mapping is untouched. The
    nested table is copied, so a caller still holding the block it read sees its
    own `pr` entry; a shallow-only copy would mutate it under them, and nothing
    downstream would report that the configuration they thought they read had
    changed.
    """
    block: dict[str, object] = {
        "acp_nodes": {"pr": {"command": "legacy"}, "review": {"command": "review"}},
        "other": "preserved",
    }

    groom, groom_audit = scoped_repository_block(block=block, workflow_kind=WORKFLOW_KIND_GROOM)
    assert groom is block
    assert groom_audit == ()

    malformed: dict[str, object] = {"acp_nodes": "invalid-but-unrelated"}
    untouched, untouched_audit = scoped_repository_block(
        block=malformed, workflow_kind=WORKFLOW_KIND_IMPLEMENT
    )
    assert untouched is malformed
    assert untouched_audit == ()

    without_pr: dict[str, object] = {"acp_nodes": {"review": {"command": "review"}}}
    no_pr, no_pr_audit = scoped_repository_block(
        block=without_pr, workflow_kind=WORKFLOW_KIND_IMPLEMENT
    )
    assert no_pr is without_pr
    assert no_pr_audit == ()

    implementation, audit = scoped_repository_block(
        block=block, workflow_kind=WORKFLOW_KIND_IMPLEMENT
    )
    assert implementation == {
        "acp_nodes": {"review": {"command": "review"}},
        "other": "preserved",
    }
    assert block["acp_nodes"] == {"pr": {"command": "legacy"}, "review": {"command": "review"}}
    assert audit == (
        {
            "layer": "repository",
            "node": "pr",
            "entry": "dispatcher.acp_nodes.pr",
            "workflow_kind": WORKFLOW_KIND_IMPLEMENT,
            "reason": IMPLEMENTATION_PR_NOT_APPLIED_REASON,
        },
    )


def test_the_groom_only_set_is_exactly_the_publication_node() -> None:
    """One node, named once, so the policy and the registries cannot diverge."""
    assert frozenset({PUBLICATION_ACP_NODE}) == GROOM_ONLY_ACP_NODES
    assert PUBLICATION_ACP_NODE == "pr"


def _grade_by_id(*, repo: Path, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str | None]]:
    """Grade each item's kind from its id, recording what the policy asked for.

    The variant preview and the kind read are stood in TOGETHER, because the
    claim under test is which ITEMS the refusal names — and threading a real
    registry through would make the case about variant resolution, which
    `_workflow_variant_kind` owns and its own tests cover.

    BOTH STAND-INS ASSERT THE REPO THEY WERE HANDED. The policy resolves a
    variant and then grades its kind, and those are two separate calls that
    could be given two different roots; a stand-in that ignored the argument
    would be blind to exactly that, and the resulting resolution would read as
    a correct answer about the wrong repository.
    """
    seen: list[tuple[str, str | None]] = []

    def preview(*, repo: Path, work_item_id: str, name: str | None) -> str:
        assert repo == expected
        seen.append((work_item_id, name))
        return "groom" if work_item_id.endswith("groom") else "implement"

    def groom(*, repo: Path, variant: str) -> bool:
        assert repo == expected
        return variant == "groom"

    expected = repo
    monkeypatch.setattr(policy, "previewed_workflow_variant", preview)
    monkeypatch.setattr(policy, "is_groom_variant", groom)
    return seen


def test_an_override_of_another_node_is_graded_without_reading_any_variant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-`pr` override returns before the selection is read at all.

    Asserted on the RECORDED PREVIEW CALLS rather than on the `None` return,
    because returning `None` is equally consistent with a policy that graded
    every item and found nothing — and that policy would resolve a variant per
    item on every dispatch in the fleet, for a question it had already settled
    from the arguments.
    """
    seen = _grade_by_id(repo=tmp_path, monkeypatch=monkeypatch)
    journal = _Journal()

    refusal = implementation_pr_override_refusal(
        args=argparse.Namespace(acp_node=("review=uvx review",), workflow_name=None),
        repo=tmp_path,
        items=(_item(item_id="bd-ib-implement"),),
        journal=journal,
    )

    assert refusal is None
    assert seen == []
    assert journal.records == []


def test_a_groom_only_selection_is_eligible_and_journals_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every item groom-kind means the override has a node to apply to."""
    _ = _grade_by_id(repo=tmp_path, monkeypatch=monkeypatch)
    journal = _Journal()

    refusal = implementation_pr_override_refusal(
        args=argparse.Namespace(acp_node=("pr=uvx filing",), workflow_name="groom-work"),
        repo=tmp_path,
        items=(_item(item_id="bd-ib-a-groom"), _item(item_id="bd-ib-b-groom")),
        journal=journal,
    )

    assert refusal is None
    assert journal.records == []


def test_a_mixed_selection_refuses_naming_only_its_implementation_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per-item grading, a sorted id list, and the removal remedy.

    The selection deliberately mixes kinds and lists its implementation items
    out of order, because both halves can be wrong independently: a policy that
    refused on the groom item too would name it here, and one that reported ids
    in arrival order would make the message depend on queue order.
    """
    seen = _grade_by_id(repo=tmp_path, monkeypatch=monkeypatch)
    journal = _Journal()

    refusal = implementation_pr_override_refusal(
        args=argparse.Namespace(acp_node=("pr=uvx forbidden",), workflow_name="selected"),
        repo=tmp_path,
        items=(
            _item(item_id="bd-ib-z"),
            _item(item_id="bd-ib-mid-groom"),
            _item(item_id="bd-ib-a"),
        ),
        journal=journal,
    )

    assert isinstance(refusal, str)
    assert "command stage" in refusal
    assert "remove the override" in refusal
    assert "bd-ib-a, bd-ib-z" in refusal
    assert "bd-ib-mid-groom" not in refusal
    assert seen == [
        ("bd-ib-z", "selected"),
        ("bd-ib-mid-groom", "selected"),
        ("bd-ib-a", "selected"),
    ]
    assert journal.records == [
        {
            "stage": ACP_PUBLICATION_POLICY_STAGE,
            "work_item_ids": ["bd-ib-a", "bd-ib-z"],
            "result": "refused",
            "layer": "dispatch",
            "node": "pr",
            "reason": refusal,
        }
    ]


@pytest.mark.parametrize(
    "override",
    [
        pytest.param("pr", id="no-value"),
        pytest.param(" pr = uvx spaced", id="spaced"),
        pytest.param("pr=", id="empty-value"),
    ],
)
def test_a_malformed_override_naming_pr_still_refuses_before_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: str
) -> None:
    """The node is read off the LEFT-HAND SIDE, so a malformed value is still `pr`.

    Each of these is rejected one stage later by the generic malformed-entry
    refusal — but that stage runs AFTER the claim, so an override that reached
    it would leave an `active` row nobody is working. Reading the name before
    the `=` is what keeps the refusal where the clause puts it.
    """
    _ = _grade_by_id(repo=tmp_path, monkeypatch=monkeypatch)
    journal = _Journal()

    refusal = implementation_pr_override_refusal(
        args=argparse.Namespace(acp_node=(override,), workflow_name=None),
        repo=tmp_path,
        items=(_item(item_id="bd-ib-implement"),),
        journal=journal,
    )

    assert isinstance(refusal, str)
    assert len(journal.records) == 1


def test_an_absent_override_argument_is_not_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An entry point exposing no `--acp-node` at all reads as no override.

    `getattr` with a default rather than attribute access, because the wall is
    shared by entry points whose parsers differ, and an `AttributeError` here
    would surface as a dispatch crash rather than as a refusal or a pass.
    """
    _ = _grade_by_id(repo=tmp_path, monkeypatch=monkeypatch)

    assert (
        implementation_pr_override_refusal(
            args=argparse.Namespace(),
            repo=tmp_path,
            items=(_item(item_id="bd-ib-implement"),),
            journal=_Journal(),
        )
        is None
    )
