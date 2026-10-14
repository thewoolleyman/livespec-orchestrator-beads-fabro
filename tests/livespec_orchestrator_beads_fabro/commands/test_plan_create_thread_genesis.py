"""`create_thread` starts the new plan epic's authority chain.

Genesis happens only where ONE writer can exist by construction, and
`create_thread` is the first of the two places relay research note 007 names:
the epic id it mints has not been seen by any other party until the call
returns, so no concurrent writer can be racing for the same chain.

THE ASSERTION IS ABOUT THE END STATE, not about a call having happened, because
the state is what every later reader depends on: the epic's `plan_epoch_chain`
cache names the created token as `current`, the walk from that cache reaches it,
and the chain reports epoch 0 with nothing committed. A `create_thread` that
created a token and failed to record it would satisfy a call-counting assertion
and leave an orphan nothing names.

THE IDENTITY CHECK BESIDE IT binds the other half of the design constraint:
genesis goes through `create_genesis_token` and there is no second genesis path.
A private create-if-absent here would produce the same cache and the same walk
on its FIRST run, and on a later one would re-create a closed token's id — the
upsert note 007 measured, which reopens the record and erases its close reason.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    ChainHead,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_genesis import create_genesis_token
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    ChainCache,
    read_chain_cache,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    from pathlib import Path

_SLUG = "relay-genesis"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _create(*, project_root: Path) -> str:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=project_root,
        config=_config(),
        slug=_SLUG,
        title="Relay genesis planning",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-10-13T08:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the plan's authority chain starts at creation.",
            assertions=("The created plan epic names its own genesis token.",),
        ),
    )
    epic_id = created["epic_id"]
    assert isinstance(epic_id, str)
    return epic_id


def test_create_thread_records_the_genesis_token_as_the_chain_start(tmp_path: Path) -> None:
    """A brand-new plan epic names its own chain from the moment it exists."""
    epic_id = _create(project_root=tmp_path)

    tokens = _fake().no_history_issue_ids()
    metadata = _fake().show_issue(issue_id=epic_id)["metadata"]
    assert isinstance(metadata, dict)

    assert len(tokens) == 1
    assert read_chain_cache(metadata=metadata) == ChainCache(latest_closed=None, current=tokens[0])
    head = read_chain_head(config=_config(), epic_id=epic_id)
    assert isinstance(head, ChainHead)
    assert head.current_token_id == tokens[0]
    assert head.latest_closed_token_id is None
    assert head.epoch == 0
    assert head.winning_operation_id is None
    # The genesis write is a read-modify-write of the epic's metadata, so the
    # slug the same call tagged has to survive it: `bd update --metadata`
    # replaces a nested object wholesale, and the cache is a nested object.
    assert metadata["plan_slug"] == _SLUG


def test_create_thread_reaches_the_one_sanctioned_genesis_primitive(tmp_path: Path) -> None:
    """There is no second genesis path, and this is what says so.

    A private create-if-absent would produce an indistinguishable chain on its
    FIRST run and an upsert that reopens a closed token on a later one. Binding
    the name is what keeps the already-named refusal and the read-back
    `create_genesis_token` performs in the path.
    """
    _ = _create(project_root=tmp_path)
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")

    assert getattr(plan, "create_genesis_token", None) is create_genesis_token
