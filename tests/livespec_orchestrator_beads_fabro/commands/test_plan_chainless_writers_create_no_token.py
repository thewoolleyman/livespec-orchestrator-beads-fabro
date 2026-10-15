"""No sanctioned writer but the two genesis writes may create a chain token.

Relay research note 007 permits exactly two writes to create a plan epic's
first authority token: `create_thread`, whose epic id no other party has seen
until the call returns, and the sanctioned plan-record migration, a deliberate
once-per-epic operator act. A genesis minted by a writer racing another writer
forks the authority permanently, and a chain is only an exclusion while every
writer closes the SAME token.

WHY THIS IS A GUARD AND NOT A RED. The behaviour already holds, so no honest
failing Red is available for it: every sanctioned write funnels through
`commit_tracked_write`, which routes a chain-less epic to `_legacy_write`, and
that path creates nothing. What there is no guard against is a LATER edit:
"create the genesis here" is the obvious, locally-reasonable repair for the
missing-tracking finding a chain-less reader keeps printing, and taking it in
any of these writers is invisible at every surface except the forked chain it
eventually produces. These cases exist to refuse that edit.

THE WRITERS ARE EXERCISED THROUGH THEIR PUBLIC PRIMITIVES, not through
`commit_tracked_write`, which `test_plan_tracked_write` already covers at that
seam. They funnel there today; that they do is exactly what a later edit could
change, so asserting it one level below the writers a reader of note 007 would
go and edit would assert the wrong thing.

`resume_directive` IS EXERCISED ON BOTH OF ITS ARMS, and labelled, because only
one of them writes at all. On an epic carrying its Definition of Done it is a
pure read; on an epic MISSING that section it records the unattended human gap
pointer through `set_next_action`, and THAT is the arm a genesis could leak
into. A mutation establishes the difference rather than an argument: a genesis
planted in `_plan_tracked_write._legacy_write` failed the three writer cases AND
the gap-pointer resume case, while a pure read reaches no writer at all and so
cannot catch it. An unlabelled single resume case would therefore have been one
fixture detail away from proving nothing — and the fixture detail that decides
it is a heading in a description, which nothing in the case name would show.

THE POSITIVE CONTROL IS LOAD-BEARING. "No token appeared" is equally consistent
with a measurement that can never see one, so the same reading is taken against
a CHAINED epic, where a sanctioned write MUST mint the successor token its own
transition names. Without it, a token count broken in any way would pass every
case here.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import read_chain_head
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    MISSING_TRACKING,
    ChainFinding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_genesis import create_genesis_token
from livespec_orchestrator_beads_fabro.commands._plan_handoff import (
    append_handoff,
    append_supervisor_handoff,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NextAction,
    resume_directive,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PROJECT_NAME = "repo"
_EPIC_ID = "bd-ib-chainless"
_TARGET_ID = "bd-ib-chainlesstarget"
_SLUG = "chainless-plan"
_DEADLINE = "2099-10-20T09:00:00Z"
_NOW = "2026-10-13T09:00:00Z"
# The heading `definition_of_done_findings` looks for. Spelled here rather than
# imported so the fixture states the shape it is building.
_DEFINITION_SECTION = "## Definition of Done\n\n- A thing holds."
_NO_DEFINITION = "This epic records no Definition of Done section."
# The two states of the epic's Definition of Done section, named rather than
# spelled as a boolean so each case says which epic it builds.
_SECTION_PRESENT = "definition-present"
_SECTION_ABSENT = "definition-absent"
# Each case is (writer, that state). The section only changes
# `resume_directive`, which reads on one arm and records the unattended gap
# pointer on the other.
_CASES = (
    ("append_handoff", _SECTION_PRESENT),
    ("append_supervisor_handoff", _SECTION_PRESENT),
    ("set_next_action", _SECTION_PRESENT),
    ("resume_directive", _SECTION_PRESENT),
    ("resume_directive", _SECTION_ABSENT),
)
_CASE_IDS = (
    "append_handoff",
    "append_supervisor_handoff",
    "set_next_action",
    "resume_directive-reads",
    "resume_directive-records-the-gap-pointer",
)


@pytest.fixture(autouse=True)
def _hermetic_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _fake(*, config: StoreConfig) -> FakeBeadsClient:
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    return client


def _seed(*, tmp_path: Path, definition: str = _SECTION_PRESENT) -> StoreConfig:
    repo = tmp_path / _PROJECT_NAME
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    config = store_config(repo=repo)
    fake = _fake(config=config)
    for issue_id, status in ((_EPIC_ID, "active"), (_TARGET_ID, "ready")):
        epic = issue_id == _EPIC_ID
        absent = epic and definition == _SECTION_ABSENT
        _ = fake.create_issue(
            draft=IssueDraft(
                issue_id=issue_id,
                issue_type="epic" if epic else "feature",
                title=issue_id,
                description=_NO_DEFINITION if absent else _DEFINITION_SECTION,
                assignee=None,
                created_at="2026-10-13T08:00:00Z",
                metadata={"rank": "a0"},
            )
        )
        fake.update_issue(issue_id=issue_id, status=status)
    return config


def _action() -> NextAction:
    return NextAction(
        kind="impl",
        ref=_TARGET_ID,
        text="Keep going.",
        required_result={
            "repo": _PROJECT_NAME,
            "item_status": {"item_id": _TARGET_ID, "status": "done"},
        },
        budget={"deadline": _DEADLINE, "max_handoffs": 5},
    )


def _drive(*, writer: str, config: StoreConfig) -> None:
    """Run one of the four sanctioned non-genesis writers against the epic."""
    if writer == "append_handoff":
        assert (
            append_handoff(
                config=config,
                epic_id=_EPIC_ID,
                body="A handoff entry.",
                author="relay-session",
                now=_NOW,
                next_action=_action(),
            )
            is None
        )
        return
    if writer == "append_supervisor_handoff":
        assert (
            append_supervisor_handoff(
                config=config,
                epic_id=_EPIC_ID,
                slug=_SLUG,
                body="A supervisor handoff entry.",
                now=_NOW,
                next_action=_action(),
            )
            is None
        )
        return
    if writer == "set_next_action":
        assert (
            set_next_action(
                config=config,
                epic_id=_EPIC_ID,
                action=_action(),
                session="relay-session",
                now=_NOW,
            )
            is None
        )
        return
    assert writer == "resume_directive", writer
    _ = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)


@pytest.mark.parametrize(("writer", "definition"), _CASES, ids=_CASE_IDS)
def test_a_sanctioned_writer_creates_no_token_on_a_chain_less_epic(
    tmp_path: Path,
    writer: str,
    definition: str,
) -> None:
    """The epic stays chain-less, and its reader keeps naming the migration.

    Both halves matter. The token count is the prohibition; the still-missing
    finding is what says the writer took the LEGACY path rather than silently
    establishing some other authority — a writer that recorded a chain cache
    naming a token it did not create would satisfy the count alone.
    """
    config = _seed(tmp_path=tmp_path, definition=definition)
    assert _fake(config=config).no_history_issue_ids() == ()

    _drive(writer=writer, config=config)

    assert _fake(config=config).no_history_issue_ids() == ()
    finding = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(finding, ChainFinding)
    assert finding.code == MISSING_TRACKING
    assert "plan-record migration" in finding.remedy


def test_the_same_reading_sees_the_token_a_chained_write_does_create(
    tmp_path: Path,
) -> None:
    """The positive control: this instrument CAN see a token appear.

    One sanctioned write on a CHAINED epic commits a transition, which closes
    the current token and creates the successor its own payload names — so the
    live count moves. Without this, every case above would pass against a token
    reading that was broken rather than against a writer that created nothing.

    The genesis record SURVIVES this first transition, which is why the reading
    is two rather than one: a commit discards the predecessor of the token it
    closed, and the genesis has none.
    """
    config = _seed(tmp_path=tmp_path)
    genesis = create_genesis_token(config=config, epic_id=_EPIC_ID)
    assert isinstance(genesis, str)
    assert _fake(config=config).no_history_issue_ids() == (genesis,)

    _drive(writer="set_next_action", config=config)

    tokens = _fake(config=config).no_history_issue_ids()
    assert genesis in tokens
    assert len(tokens) == 2
