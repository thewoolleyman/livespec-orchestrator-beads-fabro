"""A proof-mode-only Definition of Done edit leaves the tier decision's input alone.

Assertions of `bd-ib-ajtmgf`: the asked-for behaviour statement the spec-change
tier judgement places before its model says WHAT the item asks for, and the
proof-mode partition (which sub-heading a bullet sits under, that sub-heading's
`Reason:` line, and the order of the bullets) says only HOW each assertion is
proved. So the digest the reuse condition compares, and the statement the judge
reads, must not move when only the partition moves — and must move when
anything the judge reads does.

The cases are each other's controls: the three partition-only edits must leave
the digest unchanged, while a changed word, title, references line or
description prose outside the bullets must change it. A digest that ignored the
whole description would pass the first three and fail the rest.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    asked_for_behaviour,
    behaviour_digest,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_REFERENCES = "References: ## Scenario 206 — The spec-change tier is decided"
_ALPHA = "The first behaviour is observable."
_BETA = "The second behaviour names the landed, head and lookup fields."
_GAMMA = "The third behaviour is recorded."

_FLAT = f"""Prose before the section.

## Definition of Done

{_REFERENCES}

- {_ALPHA}
- {_BETA}
- {_GAMMA}

## Notes

Prose after the section.
"""

_PARTITIONED = f"""Prose before the section.

## Definition of Done

{_REFERENCES}

- {_BETA}
- {_GAMMA}

### Host-captured

Reason: only a host can observe the first behaviour.

- {_ALPHA}

## Notes

Prose after the section.
"""


def _item(**overrides: object) -> WorkItem:
    base: dict[str, object] = {
        "id": "bd-ib-one",
        "type": "feature",
        "status": "backlog",
        "title": "A title",
        "description": _FLAT,
        "origin": "freeform",
        "gap_id": None,
        "rank": "m",
        "assignee": None,
        "depends_on": (),
        "captured_at": "2026-01-01T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
    }
    base.update(overrides)
    return WorkItem(**base)  # pyright: ignore[reportArgumentType]


def _digest(**overrides: object) -> str:
    return behaviour_digest(item=_item(**overrides))


def test_moving_a_bullet_under_a_proof_mode_sub_heading_keeps_the_digest() -> None:
    assert _digest(description=_PARTITIONED) == _digest(description=_FLAT)


def test_a_changed_reason_line_keeps_the_digest() -> None:
    reworded = _PARTITIONED.replace(
        "only a host can observe the first behaviour.", "a different, longer reason."
    )
    assert _digest(description=reworded) == _digest(description=_PARTITIONED)


def test_reordering_the_bullets_keeps_the_digest() -> None:
    reordered = _FLAT.replace(
        f"- {_ALPHA}\n- {_BETA}\n- {_GAMMA}", f"- {_GAMMA}\n- {_ALPHA}\n- {_BETA}"
    )
    assert reordered != _FLAT
    assert _digest(description=reordered) == _digest(description=_FLAT)


def test_a_bullet_changed_by_one_word_changes_the_digest() -> None:
    reworded = _FLAT.replace("is observable", "is plainly observable")
    assert _digest(description=reworded) != _digest(description=_FLAT)


def test_a_bullet_changed_while_moved_changes_the_digest() -> None:
    reworded = _PARTITIONED.replace("first behaviour", "primary behaviour")
    assert _digest(description=reworded) != _digest(description=_PARTITIONED)


def test_a_changed_title_references_line_or_outside_prose_changes_the_digest() -> None:
    base = _digest()
    assert _digest(title="Another title") != base
    assert _digest(description=_FLAT.replace("Scenario 206", "Scenario 207")) != base
    assert _digest(description=_FLAT.replace("before the section", "ahead of it")) != base
    assert _digest(description=_FLAT.replace("after the section", "behind it")) != base


def test_the_statement_carries_each_bullet_once_without_the_partition() -> None:
    statement = asked_for_behaviour(item=_item(description=_PARTITIONED))
    for bullet in (_ALPHA, _BETA, _GAMMA):
        assert statement.count(bullet) == 1
    assert "Host-captured" not in statement
    assert "Reason:" not in statement
    assert "Human-attested" not in statement
    assert "Prose before the section." in statement
    assert "Prose after the section." in statement
    assert _REFERENCES in statement


def test_a_description_without_a_section_is_rendered_verbatim() -> None:
    statement = asked_for_behaviour(item=_item(description="Plain prose, no section."))
    assert "Description: Plain prose, no section." in statement
