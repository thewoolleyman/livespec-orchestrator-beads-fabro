"""The draft comment's shape, and what counts as an APPROVED draft.

`_dispatcher_groom_park` writes these comments; the apply gate in
`_dispatcher_workflow_variant` reads them. This file covers the shape both
ends share, and the one non-obvious rule in it: approval is POSITIONAL.

WHY POSITION AND NOT PRESENCE. The draft and the operator's approval are two
comments on one append-only list, and the ratified cut lets an operator send a
draft BACK for re-drafting through `resolve-blocked:<work-item-id>:backlog`.
So an item can carry, in order, a draft, an approval, and then a second draft —
and it is not approved. A reader asking merely "does this item have an approval
comment" would answer yes and let the stale consent authorise the new cut. The
cases below drive exactly that sequence.

WHY POSITION IS NOT ENOUGH EITHER. Ordering makes a NEWER draft win; it never
makes a send-back stop reading as consent. `resolve-blocked:<id>:backlog` is a
REJECTION, and `drive` accepts `--answer` on it — so an operator who bounces a
cut as too coarse and says why has written an answer comment after the draft.
Reading position alone, that rejection authorises the filing of the very
decomposition it rejected, in the window before any re-draft lands and forever
if none ever does. The two cases below are the control pair: they differ in
nothing but the disposition their action id carries, so a reader that cannot
separate them is wrong by construction.

The strictness of the marker match is the other rule worth a case. Only a
comment whose FIRST LINE opens with the marker is a draft, so an operator
explaining the mechanism, or a failure write-up quoting a body, cannot satisfy
the apply gate by talking about grooming.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_answer import (
    ANSWER_COMMENT_MARKER,
    render_answer_comment,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, append_work_item_comment
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_groom_draft"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_groom_draft.py"
)

_ITEM_ID = "bd-ib-groom-draft"
_GROOM_VARIANT = "groom-cut"
_OTHER_VARIANT = "groom-cut-v2"
_AT = "2026-09-06T00:00:00Z"


def _draft_module() -> Any:
    """Import the draft-comment module, proving the file exists first."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _answer(
    *, disposition: str, invoker: str = "human:maintainer", answer: str = "Ship it."
) -> str:
    """One operator answer, rendered by the writer the gate has to read.

    Built through `render_answer_comment` rather than hand-written so the two
    dispositions differ in nothing this test controls: the same invoker, the
    same timestamp, the same body, the same header shape. What is left is the
    disposition, which is exactly the signal under test.
    """
    return render_answer_comment(
        answer=answer,
        aid=f"resolve-blocked:{_ITEM_ID}:{disposition}",
        identity=InvokerIdentity(invoker=invoker, invoker_source="cli"),
        at=_AT,
    )


def _approval(*, invoker: str = "human:maintainer") -> str:
    return _answer(disposition="ready", invoker=invoker, answer="Approved.")


def _rendered(*, variant: str = _GROOM_VARIANT, draft: str = "Layer 1: slice A.") -> str:
    return _draft_module().render_groom_draft_comment(
        draft=draft, variant=variant, run_id="01M1DRAFT", at=_AT
    )


def test_the_rendered_comment_names_its_variant_and_carries_the_draft_verbatim() -> None:
    module = _draft_module()

    body = _rendered(draft="Layer 1: slice A. Layer 2: slice B.")

    assert body.startswith(f"{module.GROOM_DRAFT_COMMENT_MARKER} (")
    assert "Layer 1: slice A. Layer 2: slice B." in body
    assert module.drafting_groom_variant(text=body) == _GROOM_VARIANT


def test_a_comment_that_is_not_a_draft_names_no_variant() -> None:
    module = _draft_module()

    assert module.drafting_groom_variant(text=_approval()) is None
    assert module.drafting_groom_variant(text="an ordinary operator rider") is None


def test_a_comment_merely_quoting_the_marker_is_not_a_draft() -> None:
    """Prose ABOUT grooming must not be able to satisfy the apply gate."""
    module = _draft_module()

    quoted = f"A failure write-up. It said:\n{_rendered()}"

    assert module.drafting_groom_variant(text=quoted) is None


def test_a_marker_line_naming_an_empty_variant_is_not_a_draft() -> None:
    module = _draft_module()

    unnamed = f"{module.GROOM_DRAFT_COMMENT_MARKER} ( , x):\nd"

    assert module.drafting_groom_variant(text=unnamed) is None


def test_an_item_with_no_draft_carries_no_approved_draft() -> None:
    module = _draft_module()

    assert module.approved_groom_draft(comments=()) is None
    assert module.approved_groom_draft(comments=(_approval(),)) is None


def test_a_draft_awaiting_its_human_is_not_approved() -> None:
    """The draft rests; nothing has consented to it yet."""
    module = _draft_module()

    assert module.approved_groom_draft(comments=(_rendered(),)) is None


def test_a_draft_followed_by_an_approval_is_approved_under_its_own_variant() -> None:
    module = _draft_module()

    approved = module.approved_groom_draft(comments=(_rendered(), _approval()))

    assert approved == _GROOM_VARIANT


def test_a_draft_answered_with_the_ready_disposition_is_approved() -> None:
    """Half of the control pair: `ready` is the one disposition that consents."""
    module = _draft_module()

    approval = _answer(disposition="ready", answer="Approved as drafted.")

    assert approval.startswith(ANSWER_COMMENT_MARKER)
    assert module.approved_groom_draft(comments=(_rendered(), approval)) == _GROOM_VARIANT


def test_a_draft_sent_back_with_the_backlog_disposition_is_not_approved() -> None:
    """The other half: a send-back carrying feedback must not read as consent.

    The first assertion is the control, not decoration. This comment IS an
    answer comment — a reader keying on the marker alone answers "approved"
    here and files the decomposition the operator just rejected. Only the
    disposition in the action id separates it from the case above.
    """
    module = _draft_module()

    send_back = _answer(disposition="backlog", answer="Too coarse; cut layer 2 finer.")

    assert send_back.startswith(ANSWER_COMMENT_MARKER)
    assert module.approved_groom_draft(comments=(_rendered(), send_back)) is None


def test_a_send_back_after_an_approval_revokes_it() -> None:
    """The newest answer is the operator's standing verdict on the draft."""
    module = _draft_module()

    comments = (
        _rendered(),
        _approval(),
        _answer(disposition="backlog", answer="On reflection, no."),
    )

    assert module.approved_groom_draft(comments=comments) is None


def test_an_ordinary_rider_after_a_draft_is_not_an_answer() -> None:
    """A rider is not a verdict, so it neither approves the draft nor revokes one."""
    module = _draft_module()

    assert module.approved_groom_draft(comments=(_rendered(), "an ordinary operator rider")) is None
    assert module.approved_groom_draft(comments=(_rendered(), _approval(), "a rider")) == (
        _GROOM_VARIANT
    )


def test_a_re_draft_after_an_approval_is_not_approved() -> None:
    """The bounce-and-re-draft sequence, which a presence check would get wrong.

    A reader asking only whether an approval comment EXISTS would answer yes
    here and let the first cut's consent authorise the second cut, which is a
    filing the operator never approved.
    """
    module = _draft_module()

    comments = (_rendered(), _approval(), _rendered(variant=_OTHER_VARIANT))

    assert module.approved_groom_draft(comments=comments) is None


def test_the_newest_approved_draft_wins_over_an_older_one() -> None:
    """A re-draft that IS approved reports the second variant, not the first."""
    module = _draft_module()

    comments = (
        _rendered(),
        _approval(),
        _rendered(variant=_OTHER_VARIANT),
        _approval(invoker="human:second"),
    )

    assert module.approved_groom_draft(comments=comments) == _OTHER_VARIANT


def test_the_store_read_reports_the_approved_draft_from_the_items_own_comments() -> None:
    """Read back through the ledger, which is the surface the apply gate uses."""
    module = _draft_module()
    reset_fake_singleton()
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=_ITEM_ID,
            type="task",
            status="ready",
            title="An epic carrying an approved cut",
            description="It has been groomed and approved.",
            origin="freeform",
            gap_id=None,
            rank="m",
            assignee=None,
            depends_on=(),
            captured_at=_AT,
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
        ),
    )
    append_work_item_comment(path=_config(), work_item_id=_ITEM_ID, body=_rendered())
    append_work_item_comment(path=_config(), work_item_id=_ITEM_ID, body=_approval())

    assert module.approved_groom_draft_for(path=_config(), work_item_id=_ITEM_ID) == _GROOM_VARIANT
