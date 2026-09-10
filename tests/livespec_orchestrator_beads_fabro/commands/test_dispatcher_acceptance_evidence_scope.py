"""Tests for path-scoped admissibility of merged-diff acceptance evidence."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_evidence_scope import (
    diff_evidence,
    scope_for,
)

_DECLARATION_SECTION = (
    "diff --git a/.livespec-workflow-edit-exemption b/.livespec-workflow-edit-exemption\n"
    "--- /dev/null\n"
    "+++ b/.livespec-workflow-edit-exemption\n"
    "+reason=wire the gate into the CI workflow file with a pinned fabro binary\n"
)
_SOURCE_SECTION = (
    "diff --git a/tests/dev-tooling/checks/test_gate.py b/tests/dev-tooling/checks/test_gate.py\n"
    "--- a/tests/dev-tooling/checks/test_gate.py\n"
    "+++ b/tests/dev-tooling/checks/test_gate.py\n"
    "+    assert the_check_fails_closed()\n"
)
_CI_WORKFLOW_SECTION = (
    "diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n"
    "--- a/.github/workflows/ci.yml\n"
    "+++ b/.github/workflows/ci.yml\n"
    "+        run: just check-fabro-graph-validity\n"
)
# A rename that moves the declaration OUT to an ordinary documentation path. The
# section carries a real change to that path, so dropping it on the strength of
# its `a/` side alone would hide work that was genuinely done.
_DECLARATION_RENAME_SECTION = (
    "diff --git a/.livespec-workflow-edit-exemption b/docs/workflow-edit-exemption.md\n"
    "similarity index 90%\n"
    "rename from .livespec-workflow-edit-exemption\n"
    "rename to docs/workflow-edit-exemption.md\n"
)


def test_a_declaration_only_diff_leaves_no_admissible_text() -> None:
    evidence = diff_evidence(merged_diff=_DECLARATION_SECTION)

    assert evidence.admissible == ""
    assert evidence.ci_workflow == ""


def test_a_declaration_section_is_dropped_and_its_siblings_are_kept() -> None:
    evidence = diff_evidence(merged_diff=_DECLARATION_SECTION + _SOURCE_SECTION)

    assert "reason=wire the gate" not in evidence.admissible
    assert "the_check_fails_closed" in evidence.admissible
    assert evidence.ci_workflow == ""


def test_only_the_workflow_path_reaches_the_ci_workflow_body() -> None:
    evidence = diff_evidence(merged_diff=_SOURCE_SECTION + _CI_WORKFLOW_SECTION)

    assert "check-fabro-graph-validity" in evidence.ci_workflow
    assert "the_check_fails_closed" not in evidence.ci_workflow
    assert "the_check_fails_closed" in evidence.admissible


def test_a_rename_out_of_a_declaration_path_stays_admissible() -> None:
    evidence = diff_evidence(merged_diff=_DECLARATION_RENAME_SECTION)

    assert "docs/workflow-edit-exemption.md" in evidence.admissible


def test_text_before_the_first_header_stays_admissible() -> None:
    # A preamble belongs to no file, so no path rule can classify it. Narrowing
    # is this module's job only where a path says so.
    evidence = diff_evidence(merged_diff="commit 47edb04a\n\n    subject line\n" + _SOURCE_SECTION)

    assert "subject line" in evidence.admissible


def test_an_unreadable_diff_yields_empty_bodies() -> None:
    evidence = diff_evidence(merged_diff=None)

    assert evidence.admissible == ""
    assert evidence.ci_workflow == ""


def test_a_criterion_naming_the_ci_workflow_is_scoped_to_the_workflow_body() -> None:
    evidence = diff_evidence(merged_diff=_SOURCE_SECTION + _CI_WORKFLOW_SECTION)

    scope = scope_for(evidence=evidence, criterion="The CI workflow file pins the fabro binary.")

    assert scope.text == evidence.ci_workflow
    assert scope.absent_reason == "no merged diff change under .github/workflows/"


def test_a_criterion_naming_the_workflow_path_class_is_scoped_the_same_way() -> None:
    evidence = diff_evidence(merged_diff=_SOURCE_SECTION + _CI_WORKFLOW_SECTION)

    scope = scope_for(evidence=evidence, criterion="A path under .github/workflows/ runs the gate.")

    assert scope.text == evidence.ci_workflow


def test_a_criterion_naming_no_path_class_is_scoped_to_the_whole_admissible_body() -> None:
    # The under-firing control: `workflow file` alone also names this repo's
    # `workflow.fabro` graph, so it must NOT demand a `.github/workflows/` change.
    evidence = diff_evidence(merged_diff=_SOURCE_SECTION + _CI_WORKFLOW_SECTION)

    scope = scope_for(evidence=evidence, criterion="The workflow file declares the review node.")

    assert scope.text == evidence.admissible
    assert scope.absent_reason == "no merged diff or telemetry evidence"
