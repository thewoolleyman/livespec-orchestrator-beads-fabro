"""A hook that outlived its limit is parsed, journaled, and named as a cause.

Binds the THIRD, FOURTH and FIFTH sub-scenarios of `SPECIFICATION/scenarios.md`
Scenario 177 on the host side, for work-item ``bd-ib-xi63mq``:

- "A command node's over-limit push is named" -- the journal row naming
  `publish_draft`, the push operation, the resolved limit and the hook run's
  elapsed milliseconds, and the needs-human cause naming the first three.
- "A push that times out after its hook finished is not a hook-over-limit
  event" -- no row, and no cause lines to displace the existing classification.

THE NEGATIVE ARM IS THE LOAD-BEARING HALF, which is why it is asserted beside
the positive one rather than left to the implementation's good intentions. A
writer that emitted a row for every publication timeout would satisfy the
positive arm exactly as a correct one does, and the clause it would break --
"keeps its existing failure classification" -- is invisible at the surface the
positive arm reads. The two arms are asserted over the SAME writer and the same
journal, so a row that appeared for the hookless push would land in the records
list the positive assertion also reads.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_hook_over_limit"

_SENTINEL_LINE = (
    "LIVESPEC_HOOK_OVER_LIMIT: node=publish_draft operation=push "
    "limit_seconds=3600 hook_elapsed_ms=3477219"
)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _module() -> Any:
    module = importlib.import_module(_MODULE)
    for name in (
        "hook_over_limit_from_text",
        "journal_hook_over_limit",
        "hook_over_limit_cause_lines",
    ):
        assert hasattr(module, name), name
    return module


def test_an_over_limit_push_is_journaled_naming_all_four_facts() -> None:
    """Scenario 177: the row names the node, the operation, the limit, the elapsed."""
    module = _module()
    journal = _Journal()

    event = module.hook_over_limit_from_text(
        text=f"publish_draft output\n{_SENTINEL_LINE}\nmore output\n"
    )
    assert event is not None, "the sentinel the in-sandbox observer prints was not read"
    module.journal_hook_over_limit(journal=journal, work_item_id="bd-ib-xi63mq", event=event)

    assert journal.records == [
        {
            "work_item_id": "bd-ib-xi63mq",
            "stage": "hook-over-limit",
            "node": "publish_draft",
            "operation": "push",
            "limit_seconds": 3600,
            "hook_elapsed_ms": 3477219,
        }
    ]


def test_a_push_whose_hook_had_finished_is_not_an_event() -> None:
    """Scenario 177: no row, so the push keeps its existing classification."""
    module = _module()
    journal = _Journal()
    hookless = (
        "publish_draft output\n"
        "livespec hook-limit: no pre-push hook run was executing under pid 41 at the "
        "limit, so this is not a hook-over-limit event\n"
        "LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED: origin could not be reached\n"
    )

    event = module.hook_over_limit_from_text(text=hookless)
    module.journal_hook_over_limit(journal=journal, work_item_id="bd-ib-xi63mq", event=event)

    assert event is None, "a push with no hook running was read as a hook-over-limit event"
    assert journal.records == []
    assert module.hook_over_limit_cause_lines(event=event) == ()


def test_the_cause_lines_name_the_classification_the_node_and_the_operation() -> None:
    """Scenario 177: the stop is not presented as an agent's decision."""
    module = _module()
    event = module.hook_over_limit_from_text(text=_SENTINEL_LINE)
    assert event is not None

    lines = module.hook_over_limit_cause_lines(event=event)

    rendered = "\n".join(lines)
    assert "hook-over-limit" in rendered
    assert "publish_draft" in rendered
    assert "push" in rendered
    assert "3600" in rendered
    assert "no agent asked anything" in rendered
