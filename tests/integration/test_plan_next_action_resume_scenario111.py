"""Scenario 111 — the typed `next_action` decides an unattended resume.

Binds `SPECIFICATION/scenarios.md` "Scenario 111 — Typed `next_action` drives
an unattended resume and cannot be truncated by wrapping" and the typed
next_action and last_session clauses it realizes, in
`SPECIFICATION/contracts.md`.

Everything that decides the resume runs as production code against the REAL
store/client seam — the in-memory `FakeBeadsClient` that is both the hermetic
CI backend and the no-live-connection runtime fallback. The plan is created
through `create_thread`, its pointer is written through `append_handoff` (which
updates the typed metadata in the same call that appends the entry) and
`set_next_action`, and the unattended marker is read off the process
environment through `is_unattended_session`, exactly as a resuming session
reads it. Nothing is stood in.

The fixture is built to defeat the reading that would look right and be wrong.
The retired parse derived the next action from the newest handoff's prose
marker line, and ordinary wrapping truncated that line twice on a live tenant —
deleting a constraint in one case and the factory route in the other — while
the directive reported one confident action either way. So the handoff here
carries a marker line that wraps mid-instruction, and the wrapped case asserts
that the prose IS still present and IS still readable (`recorded_next_actions`
returns the truncated fragment) BEFORE asserting the directive took the typed
route anyway. Without that control, "the resume took the typed action" would
pass just as well against a handoff carrying no marker line at all, which is a
probe that can only fail silently.

The attended case is the other control: the same epic carrying the same
dispatchable pointer asks when the environment marker is absent, so a passing
unattended case cannot be a directive that never asks.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.commands.plan import (
    UNATTENDED_ENV_VAR,
    NextAction,
    ResumeDirective,
    append_handoff,
    create_thread,
    is_unattended_session,
    read_timeline,
    recorded_next_actions,
    resume_directive,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    from pathlib import Path

_SLUG = "console-control-plane-primitives"
_TITLE = "Console control-plane primitives"
_SESSION = "console-control-plane-primitives"
_NOW = "2026-09-05T18:00:00Z"
_IMPL_REF = "bd-ib-w3nwz5.1"
_WRAPPED_REF = "overseer-adclcd.6"
# The handoff body the retired parse read. Its marker line wraps after "the",
# so a line-oriented reader sees an instruction that stops mid-sentence and
# loses the constraint the second line carries.
_HANDOFF_BODY = (
    "Landed the typed pointer; the wrapped-marker parse is retired.\n\n"
    "Next action: implement overseer-adclcd.6 through the\n"
    "factory, without touching the console shim.\n"
)
_TRUNCATED_FRAGMENT = "implement overseer-adclcd.6 through the"


@pytest.fixture(autouse=True)
def _hermetic_tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
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


def _impl_action(*, ref: str) -> NextAction:
    return NextAction(kind="impl", ref=ref, text="Dispatch b1 through the factory.")


def _resumable_plan(*, project_root: Path, ref: str) -> str:
    """Create the plan and hand it off, returning the epic id to resume from."""
    created = create_thread(
        project_root=project_root,
        config=_config(),
        slug=_SLUG,
        title=_TITLE,
        research_filename="001-charter.md",
        research_text="Charter for the console control-plane primitives.\n",
        now=_NOW,
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )
    epic_id = created["epic_id"]
    append_handoff(
        config=_config(),
        epic_id=epic_id,
        body=_HANDOFF_BODY,
        author=_SESSION,
        now=_NOW,
        next_action=_impl_action(ref=ref),
    )
    return epic_id


def _resume(*, epic_id: str) -> ResumeDirective:
    """Resume as a session does — the marker read off the real environment."""
    return resume_directive(
        config=_config(),
        epic_id=epic_id,
        unattended=is_unattended_session(env=os.environ),
    )


def _newest_handoff_body(*, epic_id: str) -> str:
    entries = read_timeline(config=_config(), epic_id=epic_id)
    return entries[-1].body


def test_scenario111_an_unattended_resume_takes_the_impl_next_action_without_asking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(UNATTENDED_ENV_VAR, "1")
    epic_id = _resumable_plan(project_root=tmp_path, ref=_IMPL_REF)

    directive = _resume(epic_id=epic_id)

    assert directive == ResumeDirective(
        ask=False,
        next_action=f"impl:{_IMPL_REF}",
        reason="unattended resume takes the typed next_action",
    )
    # The handoff write updated the pointer in the same call, and the entry it
    # appended is still on the timeline as an append-only record.
    assert [entry.kind for entry in read_timeline(config=_config(), epic_id=epic_id)] == ["handoff"]


def test_scenario111_a_human_next_action_raises_the_picker_naming_its_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(UNATTENDED_ENV_VAR, "1")
    epic_id = _resumable_plan(project_root=tmp_path, ref=_IMPL_REF)

    set_next_action(
        config=_config(),
        epic_id=epic_id,
        action=NextAction(
            kind="human",
            ref="",
            text="Confirm the anchor filename with the maintainer.",
        ),
        session=_SESSION,
        now=_NOW,
    )

    directive = _resume(epic_id=epic_id)

    assert directive == ResumeDirective(
        ask=True,
        next_action=None,
        reason="next_action kind human raises the picker",
    )


def test_scenario111_a_wrapped_prose_marker_line_cannot_decide_the_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(UNATTENDED_ENV_VAR, "1")
    epic_id = _resumable_plan(project_root=tmp_path, ref=_WRAPPED_REF)

    # The control: the prose marker IS there and IS readable, and what it reads
    # as is the truncated fragment — the retired parse's whole failure mode.
    assert recorded_next_actions(body=_newest_handoff_body(epic_id=epic_id)) == (
        _TRUNCATED_FRAGMENT,
    )

    directive = _resume(epic_id=epic_id)

    assert directive.next_action == f"impl:{_WRAPPED_REF}"
    assert not directive.ask


def test_scenario111_an_attended_resume_asks_even_carrying_a_dispatchable_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(UNATTENDED_ENV_VAR, raising=False)
    epic_id = _resumable_plan(project_root=tmp_path, ref=_IMPL_REF)

    directive = _resume(epic_id=epic_id)

    assert directive == ResumeDirective(ask=True, next_action=None, reason="interactive resume")
