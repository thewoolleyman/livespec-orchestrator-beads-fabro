"""One module owns the plan anchor marker that shares a field with spec commitments.

`create_thread` stamps a plan epic's `spec_commitment_hint` with the plan
prefix plus the plan slug, and the ledger bridge persists that onto the
native `spec_id` column that genuine spec-clause commitments also use.
Consumers testing the field for PRESENCE alone therefore read every plan
anchor as a spec-change-tier commitment. These tests pin the
discrimination, and the single literal it keys on, at their one owner.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._plan_anchor"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_plan_anchor.py"
)

# A genuine obligation id_hint, of the shape the Spec Reader parses out of
# proposed-change front-matter. Every obligation in this repo's
# SPECIFICATION tree is a bare slug like this one and none begins with the
# plan prefix, which is what makes the prefix a sound discriminator rather
# than a convention.
_SPEC_CLAUSE_COMMITMENT = "contracts-dispatcher-admission"
_PLAN_SLUG = "codex-yolo-sandbox"
_PLAN_ANCHOR_MARKER = f"plan:{_PLAN_SLUG}"


def _plan_anchor() -> ModuleType:
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} must own the plan prefix literal"
    return importlib.import_module(_MODULE_NAME)


def test_the_package_defines_the_plan_prefix_literal_exactly_once() -> None:
    assert _plan_anchor().PLAN_HINT_PREFIX == "plan:"


def test_a_plan_marker_is_an_anchor_rather_than_a_spec_commitment() -> None:
    module = _plan_anchor()

    assert module.is_plan_anchor(spec_id=_PLAN_ANCHOR_MARKER) is True
    assert module.is_spec_commitment(spec_id=_PLAN_ANCHOR_MARKER) is False


def test_a_bare_obligation_slug_is_a_spec_commitment_rather_than_an_anchor() -> None:
    module = _plan_anchor()

    assert module.is_spec_commitment(spec_id=_SPEC_CLAUSE_COMMITMENT) is True
    assert module.is_plan_anchor(spec_id=_SPEC_CLAUSE_COMMITMENT) is False


def test_an_absent_or_empty_hint_is_neither_an_anchor_nor_a_commitment() -> None:
    module = _plan_anchor()

    assert module.is_plan_anchor(spec_id=None) is False
    assert module.is_spec_commitment(spec_id=None) is False
    assert module.is_spec_commitment(spec_id="") is False


def test_the_minted_plan_anchor_epic_carries_the_shared_prefix() -> None:
    epic = _plan_anchor().plan_anchor_epic(
        prefix="bd-ib",
        slug=_PLAN_SLUG,
        title="Codex YOLO sandbox",
        now="2026-08-27T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )

    assert epic.spec_commitment_hint == _PLAN_ANCHOR_MARKER
    assert epic.type == "epic"
    assert epic.notes == f"plan_slug={_PLAN_SLUG}"
