"""The factory runbook names the recipe as the way to take a candidate canary.

Assertion under test: *the factory runbook names the recipe as the way to take a
candidate canary*.

The runbook is where an operator goes when a build has been re-pinned or a
factory host restarted, so it is the only place a canary procedure can be named
and found. A recipe that exists but is unnamed there is a recipe the next
operator takes a canary without — by hand, off a real backlog item, which is
exactly how canaries 5 and 6 of plan `fabro-currency` were lost to an
item-quality refusal that read like an engine fault.

The committed deliverables are named here as literals and asserted to appear in
the prose, rather than being read out of the module and compared with the
runbook's own text. The second form passes whenever both happen to say the same
wrong thing.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RUNBOOK = (_REPO_ROOT / "orchestrator-image" / "README.md").read_text(encoding="utf-8")
_SECTION = "### Taking a candidate canary"
_RECIPE = "just take-candidate-canary"
_SCRIPT_RELPATH = "orchestrator-image/take-candidate-canary.sh"
_TEMPLATE_RELPATH = "orchestrator-image/candidate-canary-work-item-template.md"
_MARKER_RELPATH = "orchestrator-image/candidate-canary-log.md"


def test_the_runbook_carries_a_candidate_canary_section_naming_the_recipe() -> None:
    assert _SECTION in _RUNBOOK

    section = _RUNBOOK[_RUNBOOK.index(_SECTION) :]

    assert _RECIPE in section
    # The invocation, not just the recipe name: `just` passes script arguments
    # after `--`, so a reader copying a bare recipe name reaches the script's own
    # "--factory is required" refusal instead of a canary.
    assert f"{_RECIPE} -- --factory" in section


def test_the_section_names_the_recipe_as_the_way_rather_than_one_way() -> None:
    section = _RUNBOOK[_RUNBOOK.index(_SECTION) :]

    # Filing a canary by hand is the failure mode the fixture exists to remove,
    # so the runbook has to say the recipe is the route and say why — a section
    # that merely documents a convenience leaves hand-filing sanctioned.
    assert "sanctioned" in section
    assert "by hand" in section
    assert "dod_gate" in section


def test_the_section_names_the_committed_fixture_and_the_log_it_edits() -> None:
    section = _RUNBOOK[_RUNBOOK.index(_SECTION) :]

    assert _TEMPLATE_RELPATH in section
    assert _MARKER_RELPATH in section
    # `--factory` is the argument that makes a canary evidence about one engine;
    # the runbook has to say it is never defaulted, because the configured
    # factories can carry different Fabro builds.
    assert "--factory" in section
    assert "never defaulted" in section


def test_the_runbook_contents_table_lists_the_canary_files() -> None:
    contents = _RUNBOOK[_RUNBOOK.index("## Contents") : _RUNBOOK.index("## Hard constraints")]

    for relpath in (_SCRIPT_RELPATH, _TEMPLATE_RELPATH, _MARKER_RELPATH):
        assert f"`{Path(relpath).name}`" in contents
