"""Tests for the plan-owned redirect both of a resume's obligation reads take.

The redirect is NARROW in the one direction that matters, and each case here is
a different way of not being the plan epic: a value that is no reference at all,
a reference whose target is another item, a target that is not an object, and a
reference carrying neither of the two item-target kinds. A redirect that fired
on any of those would read a carrier child's result — legitimately filed in a
sibling tenant under the cross-tenant execution mirror — from this project's
tenant instead, reporting it unobservable or, worse, resolving some same-named
record here.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._plan_result_plan_owned import (
    plan_owned_reference,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_EPIC = "bd-ib-plan"
_OTHER = "bd-ib-carrier-child"
_FOREIGN = "livespec-dev-tooling"
_OWN = "repo"


def _config(*, tmp_path: Path) -> StoreConfig:
    """A checkout naming no origin and no primary, so its identity is its name."""
    repo = tmp_path / _OWN
    repo.mkdir()
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        repo_root=repo,
        fake=True,
    )


def test_a_status_obligation_on_the_epic_is_redirected_to_this_project(tmp_path: Path) -> None:
    """The archive leg's own obligation: the epic's closed status.

    The epic lives in the plan's own tenant whatever the recorded `repo` says,
    so the read must resolve there or the plan locks behind a pointer no
    sanctioned write can replace.
    """
    recorded = {"repo": _FOREIGN, "item_status": {"item_id": _EPIC, "status": "closed"}}

    assert plan_owned_reference(
        config=_config(tmp_path=tmp_path), epic_id=_EPIC, required_result=recorded
    ) == {"repo": _OWN, "item_status": {"item_id": _EPIC, "status": "closed"}}


def test_a_comment_obligation_on_the_epic_is_redirected_to_this_project(tmp_path: Path) -> None:
    """The proof and review legs' own obligation: a marker comment on the epic."""
    recorded = {
        "repo": _FOREIGN,
        "item_comment": {"item_id": _EPIC, "marker": "Plan Proof of Done"},
    }

    assert plan_owned_reference(
        config=_config(tmp_path=tmp_path), epic_id=_EPIC, required_result=recorded
    ) == {"repo": _OWN, "item_comment": {"item_id": _EPIC, "marker": "Plan Proof of Done"}}


def test_an_obligation_on_another_item_keeps_its_recorded_repository(tmp_path: Path) -> None:
    """An `impl` leg's target is a CHILD, and a child's repository is a real fact.

    This is the case the redirect must leave alone: the plan's carrier children
    are filed wherever the execution mirror put them, and rewriting their
    repository would aim the read at a tenant that never held them.
    """
    recorded = {"repo": _FOREIGN, "item_status": {"item_id": _OTHER, "status": "closed"}}

    assert (
        plan_owned_reference(
            config=_config(tmp_path=tmp_path), epic_id=_EPIC, required_result=recorded
        )
        is recorded
    )


def test_an_obligation_carrying_no_item_target_keeps_its_recorded_repository(
    tmp_path: Path,
) -> None:
    """A reference naming a pull request or a branch file names no item at all."""
    recorded = {"repo": _FOREIGN, "pull_request_state": {"number": 7, "state": "MERGED"}}

    assert (
        plan_owned_reference(
            config=_config(tmp_path=tmp_path), epic_id=_EPIC, required_result=recorded
        )
        is recorded
    )


def test_a_target_that_is_not_an_object_keeps_its_recorded_repository(tmp_path: Path) -> None:
    """A malformed target names no item either, and the reader owes the refusal.

    Deciding a redirect here would be this module grading a reference shape
    `read_result` has not admitted, which is the one thing it must not do: the
    parse's own refusal ladder is what reports a malformed obligation.
    """
    recorded = {"repo": _FOREIGN, "item_status": "closed"}

    assert (
        plan_owned_reference(
            config=_config(tmp_path=tmp_path), epic_id=_EPIC, required_result=recorded
        )
        is recorded
    )


def test_a_value_that_is_no_reference_at_all_is_handed_back(tmp_path: Path) -> None:
    """Legacy and absent tracking reach the readers as values no parse admits."""
    assert (
        plan_owned_reference(
            config=_config(tmp_path=tmp_path), epic_id=_EPIC, required_result="legacy"
        )
        == "legacy"
    )
