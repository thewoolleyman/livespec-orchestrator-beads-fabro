"""Tests for the filing-time Definition-of-Done display primitive (v115).

The Definition-of-Done-and-Proof-of-Done clause of `SPECIFICATION/contracts.md`
requires every front-end that files or reshapes an implement-kind work item to
display, BEFORE the filing is confirmed, four things: "the effective-criteria
parse, each assertion with its proof mode, the sandbox capabilities it resolved
(the committed `dispatcher.sandbox_capabilities` array, or `sandbox-capabilities:
unpublished` when the key is unset), and every Definition-of-Done finding the
host-side wall can detect"; and, "when the filer declines the section it MUST
display `definition-of-done: missing`". These cases bind that display.

WHY THE MODULE IS IMPORTED INSIDE EACH TEST BODY. A top-level import of a module
that does not exist yet makes the Red a COLLECTION error, which proves only
unimportability. The shape case's first assertion is a genuine check on the
module path instead, and it fails before any import is reached.

WHY EVERY LINE IS ASSERTED BY POSITION RATHER THAN BY CONTAINMENT. A display
whose four parts are present in any order satisfies an `in` check while telling
an operator nothing about which assertion carries which mode — the pairing IS the
information. The parse line also has to come FIRST, because it is the line that
says whether the section was read at all.

WHY A DISPLAY MUST NEVER RAISE. The clause says filing "stays consent-gated and a
front-end MUST NOT refuse on a finding". A display that threw on an unreadable
`.livespec.jsonc` would convert an advisory surface into a refusal, so both
unreadable-configuration arms are asserted to render a line and return.
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_filing_display.py"
)

_SPEC_HEADING = "## Effective acceptance criteria"


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-disp",
        type="task",
        status="backlog",
        title="A freshly filed task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-04T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _repo(*, tmp_path: Path, config: str | None = None) -> Path:
    """A repository carrying a governed spec tree and an optional dispatcher block."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    if config is not None:
        _ = (repo / ".livespec.jsonc").write_text(config, encoding="utf-8")
    return repo


def _capabilities_config(*, entries: str) -> str:
    return (
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"sandbox_capabilities": '
        + entries
        + "}}}"
    )


def _display(*, item: WorkItem, cwd: Path) -> list[str]:
    module = importlib.import_module(_MODULE)
    return module.filing_display(item=item, cwd=cwd).splitlines()


def test_the_display_module_is_a_module_of_its_own_exporting_its_named_surface() -> None:
    """The shape case, whose first assertion fails before any import is reached."""
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(_MODULE)

    assert set(module.__all__) == {
        "ADVISORY_FINDING_PREFIX",
        "CAPABILITIES_PREFIX",
        "FINDINGS_NONE_REPORT",
        "MECHANICAL_FINDING_PREFIX",
        "NO_ASSERTIONS_REPORT",
        "UNDECLARED_PROOF_MODE_REPORT",
        "filing_display",
    }


def test_a_conforming_filing_shows_the_parse_the_modes_the_capabilities_and_no_findings(
    tmp_path: Path,
) -> None:
    """The positive case: all four parts, in order, with each mode on its assertion."""
    item = _item(
        description=(
            "## Definition of Done\n"
            "\n"
            "- The accept valve refuses an item with no verified record.\n"
            "\n"
            "### Host-captured\n"
            "\n"
            "Reason: the proof needs the released build on an operator host.\n"
            "\n"
            "- The released build renders the pointer on the pull request.\n"
            "\n"
            f"References: {_SPEC_HEADING}\n"
        )
    )
    repo = _repo(tmp_path=tmp_path, config=_capabilities_config(entries='["terminal", "tmux"]'))

    lines = _display(item=item, cwd=repo)

    assert lines[0] == (
        "effective acceptance criteria: 2 gradeable assertion(s) resolved from"
        " description-definition-of-done"
    )
    assert lines[1] == (
        "assertion 1 (proof mode: factory_captured): The accept valve refuses an item"
        " with no verified record."
    )
    assert lines[2] == (
        "assertion 2 (proof mode: host_captured): The released build renders the pointer"
        " on the pull request."
    )
    assert lines[3] == "sandbox-capabilities: terminal, tmux"
    assert lines[4] == "definition-of-done findings: none"
    assert len(lines) == 5


def test_an_unset_capability_key_is_reported_unpublished_rather_than_empty(
    tmp_path: Path,
) -> None:
    """An unknown set is not an empty one, and the clause names the wording for it."""
    item = _item(
        description=(
            "## Definition of Done\n"
            "\n"
            "- The accept valve refuses an item with no verified record.\n"
            "\n"
            f"References: {_SPEC_HEADING}\n"
        )
    )

    lines = _display(item=item, cwd=_repo(tmp_path=tmp_path))

    assert "sandbox-capabilities: unpublished" in lines


def test_a_malformed_capability_mirror_is_displayed_rather_than_raised(tmp_path: Path) -> None:
    """A typo in the mirror is shown on the surface that can still repair it."""
    item = _item(
        description=(
            "## Definition of Done\n"
            "\n"
            "- The accept valve refuses an item with no verified record.\n"
            "\n"
            f"References: {_SPEC_HEADING}\n"
        )
    )
    repo = _repo(tmp_path=tmp_path, config=_capabilities_config(entries='["Headless-Browser"]'))

    lines = _display(item=item, cwd=repo)

    capability_line = next(line for line in lines if line.startswith("sandbox-capabilities:"))
    assert "declared but unusable" in capability_line
    assert "Headless-Browser" in capability_line


def test_an_unreadable_dispatcher_config_is_displayed_rather_than_raised(tmp_path: Path) -> None:
    """The display is advisory, so a broken config file cannot make it refuse."""
    item = _item(
        description=(
            "## Definition of Done\n"
            "\n"
            "- The accept valve refuses an item with no verified record.\n"
            "\n"
            f"References: {_SPEC_HEADING}\n"
        )
    )
    repo = _repo(tmp_path=tmp_path, config='{"livespec-orchestrator-beads-fabro": ')

    lines = _display(item=item, cwd=repo)

    capability_line = next(line for line in lines if line.startswith("sandbox-capabilities:"))
    assert "unreadable" in capability_line


def test_a_declined_section_shows_the_missing_marker_and_no_assertions(tmp_path: Path) -> None:
    """The ratified wording for a filer who declines the section, and no refusal.

    The marker rides the parse line because that line is what says WHICH repair
    applies; the no-assertions line is separate so the display never silently
    renders an empty list as a clean parse.
    """
    item = _item(description="Just prose. The filer declined the section.")

    lines = _display(item=item, cwd=_repo(tmp_path=tmp_path))

    assert "definition-of-done: missing" in lines[0]
    assert lines[1] == "assertions: none"


def test_a_legacy_criteria_field_item_reports_its_assertions_as_mode_undeclared(
    tmp_path: Path,
) -> None:
    """A legacy source declares no mode at all, which is not `factory_captured`.

    Rendering the default there would tell a filer their assertion is already
    declared, which is the one reading that stops them authoring the section.
    """
    item = _item(
        description="Just prose.",
        acceptance_criteria="- The accept valve refuses an unverified item.\n",
    )

    lines = _display(item=item, cwd=_repo(tmp_path=tmp_path))

    assert lines[0].endswith("resolved from criteria-field; definition-of-done: missing")
    assert lines[1] == (
        "assertion 1 (proof mode: undeclared): The accept valve refuses an unverified item."
    )


def test_a_mechanical_finding_and_an_advisory_finding_are_both_displayed_and_labelled(
    tmp_path: Path,
) -> None:
    """Both kinds appear, each named by kind, because the remedies differ.

    The mechanical one withholds `ready` and the advisory one must not, so a
    display that merged them would leave the filer unable to tell which of the two
    is blocking the item.
    """
    item = _item(
        description=(
            "## Definition of Done\n"
            "\n"
            "- Regression tests cover the accept valve.\n"
            "\n"
            "References: ## A heading the spec tree does not carry\n"
        )
    )

    lines = _display(item=item, cwd=_repo(tmp_path=tmp_path))

    mechanical = [
        line for line in lines if line.startswith("definition-of-done finding (mechanical)")
    ]
    advisory = [line for line in lines if line.startswith("definition-of-done finding (advisory)")]
    assert len(mechanical) == 1
    assert "does not resolve" in mechanical[0]
    assert len(advisory) == 1
    assert "regression tests" in advisory[0]
    assert "definition-of-done findings: none" not in lines
