"""A recorded spec-change tier holds the item until its topic ratifies.

The first half of assertion 3 of `bd-ib-57ss2n`: "A spec-change-tier item whose
linked topic has no revision record with decision accept or modify, or for which
the judgement does not return `stated` against the ratified spec, rests out of
`ready`". The wall refusal that carries it is the second half and is exercised by
its own module.

The ratification read is exercised against a REAL spec-history fixture rather
than a stubbed topic set, because the thing it has to get right is the file
layout: the topic is the stem of a `proposed_changes/<topic>.md` file whose
paired `<topic>-revision.md` carries `decision: accept` or `decision: modify`,
and a reader that looked one directory up, or keyed on the revision file's own
stem, would return a plausible non-empty set with the wrong members in it.

`reject` is the control the independent review of this plan's scoping required
(research note 005, finding 1: "archived proposal presence is not ratification").
A rejected proposal is archived under exactly the same path as an accepted one,
so a read keyed on PRESENCE releases every hold whose proposal was refused.

The hold's three reasons are asserted apart because each sends the operator
somewhere different, and the one most easily collapsed is
`awaiting-rejudgement`: folding it into `unratified-topic` tells an operator
their ratified proposal was not ratified, and the remedy that implies cannot
exist.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_ITEM = "bd-ib-one"
_TOPIC = "a-ratified-topic"
_TARGET = "## A governing clause"


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _recorded(**overrides: object) -> Any:
    record = _module(name="_spec_change_tier_record")
    base: dict[str, object] = {
        "tier": "spec-change",
        "classification": "feature",
        "verdict_kind": "unstated",
        "generalization_target": _TARGET,
        "linked_proposal_topic": _TOPIC,
        "spec_version": "170",
        "digest": "a-digest",
    }
    base.update(overrides)
    return record.RecordedSpecChangeTier(**base)


def _hold(*, recorded: Any, ratified: frozenset[str]) -> Any:
    return _module(name="_spec_change_tier_hold").spec_change_hold(
        work_item_id=_ITEM, recorded=recorded, ratified_topics=ratified
    )


def _spec_root(*, root: Path, decisions: dict[str, str]) -> Path:
    spec_root = root / "SPECIFICATION"
    for index, (topic, decision) in enumerate(sorted(decisions.items()), start=1):
        changes = spec_root / "history" / f"v{index:03d}" / "proposed_changes"
        changes.mkdir(parents=True)
        _ = (changes / f"{topic}.md").write_text("the proposal\n", encoding="utf-8")
        _ = (changes / f"{topic}-revision.md").write_text(
            f"---\nproposal: {topic}.md\ndecision: {decision}\n---\n", encoding="utf-8"
        )
    return spec_root


def test_the_ratification_read_admits_accept_and_modify_and_refuses_reject(
    tmp_path: Path,
) -> None:
    commitments = _module(name="_dispatcher_spec_commitments")
    assert "ratified_proposal_topics" in commitments.__all__

    spec_root = _spec_root(
        root=tmp_path,
        decisions={
            "an-accepted-topic": "accept",
            "a-modified-topic": "modify",
            "a-rejected-topic": "reject",
        },
    )
    assert commitments.ratified_proposal_topics(spec_root=spec_root) == frozenset(
        {"an-accepted-topic", "a-modified-topic"}
    )
    # A spec root with no history carries no ratified topic, which must not read
    # as "every topic is ratified".
    assert commitments.ratified_proposal_topics(spec_root=tmp_path / "absent") == frozenset()


def test_an_unratified_topic_holds_the_item_and_names_it() -> None:
    hold = _hold(recorded=_recorded(), ratified=frozenset())
    assert hold is not None
    assert hold.reason == _module(name="_spec_change_tier_hold").REASON_UNRATIFIED_TOPIC
    assert hold.linked_proposal_topic == _TOPIC
    assert _TOPIC in hold.refusal
    assert "unstated" in hold.refusal
    assert _TARGET in hold.refusal


def test_a_held_item_naming_no_topic_says_so_rather_than_naming_nothing() -> None:
    hold = _hold(
        recorded=_recorded(linked_proposal_topic=None, generalization_target=None),
        ratified=frozenset({_TOPIC}),
    )
    assert hold is not None
    assert hold.reason == _module(name="_spec_change_tier_hold").REASON_NO_LINKED_TOPIC
    assert "(none linked)" in hold.refusal
    assert "named no existing heading to generalize" in hold.refusal


def test_a_ratified_topic_still_holds_until_the_judgement_is_re_run() -> None:
    hold = _hold(recorded=_recorded(), ratified=frozenset({_TOPIC}))
    assert hold is not None
    assert hold.reason == _module(name="_spec_change_tier_hold").REASON_AWAITING_REJUDGEMENT
    assert _TOPIC in hold.refusal


def test_no_record_and_a_released_record_both_hold_nothing() -> None:
    assert _hold(recorded=None, ratified=frozenset()) is None
    assert (
        _hold(
            recorded=_recorded(tier="none", linked_proposal_topic=None),
            ratified=frozenset(),
        )
        is None
    )
