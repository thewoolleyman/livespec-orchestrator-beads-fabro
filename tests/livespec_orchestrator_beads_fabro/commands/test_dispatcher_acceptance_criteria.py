"""Tests for acceptance-criteria segmentation and deterministic evidence checks."""

from __future__ import annotations

import textwrap

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_criteria import (
    _DIFF_EVIDENCE_MINIMUM_TERMS,  # pyright: ignore[reportPrivateUsage]
    _EXTERNAL_VERIFICATION_TERMS,  # pyright: ignore[reportPrivateUsage]
    criteria_checks,
    criteria_lines,
)

# The bd-ib-t02s fixture: TWO sentences hard-wrapped flush-left at authoring
# width. Every line but the first is a continuation carrying no indent and no
# list marker, which is what wrapped prose looks like. The pair also carries the
# two shapes that used to make segmentation a function of the wrap: a colon in
# the middle of the first sentence, and a sentence boundary in the middle of the
# third line.
_T02S_CRITERIA = (
    "A dispatch that fails AFTER the ledger claim is taken but BEFORE a fabro run id is\n"
    "recorded leaves the work-item dispatchable again: status back to its pre-admission\n"
    "value and the assignee cleared. A subsequent dispatch of the same item is admitted\n"
    "normally rather than refused as not in the ready set.\n"
)
_T02S_ASSERTIONS = (
    "A dispatch that fails AFTER the ledger claim is taken but BEFORE a fabro run id is "
    "recorded leaves the work-item dispatchable again: status back to its pre-admission "
    "value and the assignee cleared.",
    "A subsequent dispatch of the same item is admitted normally rather than refused as "
    "not in the ready set.",
)
# A merged diff that carries the work the fixture describes. It deliberately
# carries exactly ONE term of the fixture's tail fragment ("ready"), which is
# what made that fragment fail with "insufficient merged diff evidence" while
# its three siblings passed.
_T02S_DIFF = (
    "diff --git a/x b/x\n"
    "+release the ledger claim when a dispatch fails before a fabro run id is recorded\n"
    "+restore the pre-admission status and clear the assignee\n"
    "+a subsequent dispatch is admitted for the same work-item\n"
    "+refuse a dispatch whose item is not ready\n"
)
# The same diff with the SECOND assertion's work removed, so that assertion is
# genuinely unmet while its wrapped sibling is met.
_T02S_PARTIAL_DIFF = (
    "diff --git a/x b/x\n"
    "+release the ledger claim when a dispatch fails before a fabro run id is recorded\n"
    "+restore the pre-admission status and clear the assignee\n"
)
# This work-item's own final criterion — `just check is green with nothing
# skipped.` — opens with a LOWERCASE token. A sentence split that required the
# following word to be capitalized merged such a criterion into its predecessor,
# where it rode in on that predecessor's evidence instead of being judged.
_LOWERCASE_OPENER_ASSERTIONS = (
    "A dispatch that fails before a fabro run id is recorded releases its ledger claim.",
    "just check is green with nothing skipped.",
)
_LOWERCASE_OPENER_CRITERIA = "\n".join(_LOWERCASE_OPENER_ASSERTIONS) + "\n"
# A merged diff carrying the FIRST assertion's work and none of the second's, so
# the second is genuinely unmet and must not ride in on the first's evidence.
_LOWERCASE_OPENER_DIFF = (
    "diff --git a/x b/x\n"
    "+release the ledger claim when a dispatch fails before a fabro run id is recorded\n"
)
# A dotted VERSION that genuinely ENDS its sentence. Treating every token that
# merely contains a dot as an abbreviation fused this pair into one criterion,
# where the second assertion — a condition the merged diff does not carry — rode
# in on the first's evidence instead of being judged.
_DOTTED_TAIL_ASSERTIONS = (
    "The dispatcher releases its ledger claim on the build shipped as v0.88.0.",
    "just check is green with nothing skipped.",
)
_DOTTED_TAIL_CRITERIA = "\n".join(_DOTTED_TAIL_ASSERTIONS) + "\n"
# A merged diff carrying the FIRST assertion's work and none of the second's.
_DOTTED_TAIL_DIFF = (
    "diff --git a/x b/x\n+release the ledger claim on the build shipped as v0.88.0\n"
)
# An INITIALISM that genuinely ENDS its sentence. Suppressing the boundary after
# EVERY dotted initialism fused this pair into one criterion, where the second
# assertion — a condition the merged diff does not carry — rode in on the first's
# evidence instead of being judged.
_INITIALISM_TAIL_ASSERTIONS = (
    "The dispatcher journals every claim it releases in the U.S.",
    "The watchdog reaps a run that reports no progress.",
)
_INITIALISM_TAIL_CRITERIA = "\n".join(_INITIALISM_TAIL_ASSERTIONS) + "\n"
# A merged diff carrying the FIRST assertion's work and none of the second's.
_INITIALISM_TAIL_DIFF = (
    "diff --git a/x b/x\n+the dispatcher journals every claim it releases in the u.s.\n"
)
# Every width a criteria author might plausibly wrap at. `textwrap` is asked not
# to break on hyphens or inside long words, because doing so edits the CONTENT
# ("pre-admission" becomes "pre- admission") and this sweep varies the wrap
# alone.
_WRAP_WIDTHS = tuple(range(60, 200))
# The TELEMETRY-arm fixtures. bd-ib-5z0g hardened the DIFF arm; the telemetry
# arm still fired on a SINGLE incidental verification word, which made a
# measured 196 of this tenant's 682 recorded criteria lines unfailable by
# construction on any green dispatch.
#
# A criterion that merely MENTIONS a verification word while asserting something
# about the CODE. Its lone verification term is `test`; every other significant
# term names dispatcher behaviour, which is exactly what a merged diff evidences.
_INCIDENTAL_VERIFICATION_CRITERION = (
    "The dispatcher releases its ledger claim before the watchdog reaps a run under test.\n"
)
_INCIDENTAL_VERIFICATION_TERMS = (
    "dispatcher",
    "releases",
    "ledger",
    "claim",
    "before",
    "watchdog",
    "reaps",
    "test",
)
# A genuine verification ASSERTION: its subject IS the checkable outcome, so no
# merged diff can ever carry it and green telemetry is the only evidence there
# is. Failing this shape is bd-ib-5z0g's defect 1 — landed work sent to rework.
_VERIFICATION_ASSERTION_CRITERION = "The check suite is green with no test skipped.\n"
# A criterion carrying NO verification vocabulary at all. Green telemetry says
# nothing about it, so the telemetry arm stays shut whatever the dispatch did.
_CODE_ONLY_CRITERION = "The dispatcher journals the released ledger claim.\n"
_CODE_ONLY_TERMS = ("dispatcher", "journals", "released", "ledger", "claim")
# A merged diff about something else entirely: it carries none of the terms of
# any criterion above, so it supplies diff evidence to none of them.
_UNRELATED_DIFF = "diff --git a/x b/x\n+the acceptance pass records its own verdict\n"
# The bd-ib-6t4 / PR 2446 shape, measured 2026-09-10. The merged diff touched
# exactly two paths — the workflow-edit exemption DECLARATION and a test file —
# and nothing under `.github/`. The declaration's prose DESCRIBES the CI change
# it authorizes, so every CI-workflow criterion found its own vocabulary there
# and the item was accepted and CLOSED with the workflow edit never made.
_PR_2446_CRITERIA = (
    "- The CI workflow file installs or pins the fabro binary.\n"
    "- The CI workflow file sets LIVESPEC_FABRO_GRAPH_VALIDATION to fail_when_fabro_absent.\n"
)
# A criterion that names NO path class, whose vocabulary lives only in the
# declaration's prose. It is the second half of the same false pass: excluding
# the declaration is what makes it fail, independently of any path rule.
_DECLARATION_ONLY_CRITERION = "The dispatch installs a pinned fabro binary.\n"
_PR_2446_DIFF = (
    "diff --git a/.livespec-workflow-edit-exemption b/.livespec-workflow-edit-exemption\n"
    "new file mode 100644\n"
    "--- /dev/null\n"
    "+++ b/.livespec-workflow-edit-exemption\n"
    "@@ -0,0 +1,2 @@\n"
    "+reason=wire check-fabro-graph-validity into the CI workflow file, installs a\n"
    "+pinned fabro binary and sets LIVESPEC_FABRO_GRAPH_VALIDATION=fail_when_fabro_absent\n"
    "diff --git a/tests/dev-tooling/checks/test_fabro_graph_validity.py"
    " b/tests/dev-tooling/checks/test_fabro_graph_validity.py\n"
    "--- a/tests/dev-tooling/checks/test_fabro_graph_validity.py\n"
    "+++ b/tests/dev-tooling/checks/test_fabro_graph_validity.py\n"
    "@@ -1,0 +2,2 @@\n"
    "+def test_the_check_fails_closed_when_no_fabro_is_resolvable() -> None:\n"
    "+    assert True\n"
)
# The same merge with the CI workflow edit actually landed. The criteria are
# unchanged, so this is the discriminating control: the path rule must admit the
# evidence when a path of the named class genuinely carries it.
_PR_2446_LANDED_DIFF = _PR_2446_DIFF + (
    "diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n"
    "--- a/.github/workflows/ci.yml\n"
    "+++ b/.github/workflows/ci.yml\n"
    "@@ -1,0 +2,3 @@\n"
    "+      - name: install the pinned fabro binary\n"
    "+        run: LIVESPEC_FABRO_GRAPH_VALIDATION=fail_when_fabro_absent"
    " just check-fabro-graph-validity\n"
)


def _wrapped(*, text: str, width: int) -> str:
    return textwrap.fill(text, width=width, break_on_hyphens=False, break_long_words=False)


def _diff_carrying(*, terms: tuple[str, ...]) -> str:
    return "diff --git a/x b/x\n+" + " ".join(terms) + "\n"


def test_criteria_lines_folds_a_flush_left_wrapped_continuation() -> None:
    assert criteria_lines(criteria_text=_T02S_CRITERIA) == _T02S_ASSERTIONS


def test_t02s_fixture_produces_no_fragment_only_failure() -> None:
    checks = criteria_checks(
        criteria_text=_T02S_CRITERIA, merged_diff=_T02S_DIFF, telemetry_passed=False
    )

    assert [check.text for check in checks] == list(_T02S_ASSERTIONS)
    assert [check.passed for check in checks] == [True, True]
    assert {check.reason for check in checks} == {"matched merged diff evidence"}


def test_criteria_lines_drops_a_short_all_caps_header_after_a_completed_criterion() -> None:
    criteria = (
        "The dispatcher releases the ledger claim on an aborted dispatch.\n"
        "SCOPE\n"
        "The dispatcher journals the released claim.\n"
    )

    assert criteria_lines(criteria_text=criteria) == (
        "The dispatcher releases the ledger claim on an aborted dispatch.",
        "The dispatcher journals the released claim.",
    )


def test_criteria_lines_drops_a_dangling_colon_header_and_keeps_its_list() -> None:
    criteria = "The claim is released.\nDONE looks like:\n- the work-item is dispatchable again\n"

    assert criteria_lines(criteria_text=criteria) == (
        "The claim is released.",
        "the work-item is dispatchable again",
    )


def test_criteria_lines_keeps_a_one_word_wrapped_tail_with_its_sentence() -> None:
    # The livespec-overseer instance: the wrap left the single word "verdict."
    # on its own line, which no implementation could ever find evidence for.
    criteria = "The intake record carries the filed item id and the intake\nverdict.\n"

    assert criteria_lines(criteria_text=criteria) == (
        "The intake record carries the filed item id and the intake verdict.",
    )


def test_criteria_lines_segmentation_is_identical_at_every_wrap_width() -> None:
    joined = " ".join(_T02S_ASSERTIONS)

    segmentations = {
        criteria_lines(criteria_text=_wrapped(text=joined, width=width)) for width in _WRAP_WIDTHS
    }

    assert segmentations == {_T02S_ASSERTIONS}


def test_criteria_checks_verdict_is_identical_at_every_wrap_width() -> None:
    joined = " ".join(_T02S_ASSERTIONS)

    verdicts = {
        criteria_checks(
            criteria_text=_wrapped(text=joined, width=width),
            merged_diff=_T02S_DIFF,
            telemetry_passed=False,
        )
        for width in _WRAP_WIDTHS
    }

    assert len(verdicts) == 1
    assert all(check.passed for check in verdicts.pop())


def test_a_genuinely_unmet_wrapped_assertion_fails_at_every_wrap_width() -> None:
    # The discriminating control, run across the same sweep: folding a wrapped
    # continuation must not let an assertion the merged diff does not carry ride
    # in on its sibling's evidence.
    joined = " ".join(_T02S_ASSERTIONS)

    verdicts = {
        criteria_checks(
            criteria_text=_wrapped(text=joined, width=width),
            merged_diff=_T02S_PARTIAL_DIFF,
            telemetry_passed=False,
        )
        for width in _WRAP_WIDTHS
    }

    assert len(verdicts) == 1
    checks = verdicts.pop()
    assert [check.passed for check in checks] == [True, False]
    assert checks[1].text == _T02S_ASSERTIONS[1]
    assert checks[1].reason == "insufficient merged diff evidence"


def test_criteria_lines_starts_a_new_assertion_at_a_lowercase_sentence() -> None:
    assert criteria_lines(criteria_text=_LOWERCASE_OPENER_CRITERIA) == _LOWERCASE_OPENER_ASSERTIONS


def test_a_lowercase_assertion_is_judged_on_its_own_evidence() -> None:
    # The discriminating control for the lowercase opener: merging it into its
    # predecessor produced ONE passing check, so a condition the merged diff
    # does not carry was reported as met.
    checks = criteria_checks(
        criteria_text=_LOWERCASE_OPENER_CRITERIA,
        merged_diff=_LOWERCASE_OPENER_DIFF,
        telemetry_passed=False,
    )

    assert [check.text for check in checks] == list(_LOWERCASE_OPENER_ASSERTIONS)
    assert [check.passed for check in checks] == [True, False]
    assert checks[1].reason == "no merged diff or telemetry evidence"


def test_a_lowercase_assertion_is_segmented_identically_at_every_wrap_width() -> None:
    joined = " ".join(_LOWERCASE_OPENER_ASSERTIONS)

    segmentations = {
        criteria_lines(criteria_text=_wrapped(text=joined, width=width)) for width in _WRAP_WIDTHS
    }

    assert segmentations == {_LOWERCASE_OPENER_ASSERTIONS}


def test_criteria_lines_does_not_split_a_sentence_at_an_abbreviation() -> None:
    # A dot that closes an abbreviation or a dotted identifier does not end a
    # sentence, even when a capitalized word follows it.
    criteria = (
        "The parser leaves a dotted token alone, e.g. The file\n"
        "_dispatcher_acceptance_criteria.py folds a wrapped continuation.\n"
    )

    assert criteria_lines(criteria_text=criteria) == (
        "The parser leaves a dotted token alone, e.g. The file "
        "_dispatcher_acceptance_criteria.py folds a wrapped continuation.",
    )


def test_criteria_lines_starts_a_new_assertion_after_a_dotted_version() -> None:
    assert criteria_lines(criteria_text=_DOTTED_TAIL_CRITERIA) == _DOTTED_TAIL_ASSERTIONS


def test_criteria_lines_starts_a_new_assertion_after_a_dotted_filename() -> None:
    criteria = (
        "The fold lands in _dispatcher_acceptance_criteria.py.\n"
        "just check is green with nothing skipped.\n"
    )

    assert criteria_lines(criteria_text=criteria) == (
        "The fold lands in _dispatcher_acceptance_criteria.py.",
        "just check is green with nothing skipped.",
    )


def test_an_assertion_after_a_dotted_version_is_judged_on_its_own_evidence() -> None:
    # The discriminating control for the dotted tail: fusing the two sentences
    # produced ONE passing check, so a condition the merged diff does not carry
    # was reported as met.
    checks = criteria_checks(
        criteria_text=_DOTTED_TAIL_CRITERIA,
        merged_diff=_DOTTED_TAIL_DIFF,
        telemetry_passed=False,
    )

    assert [check.text for check in checks] == list(_DOTTED_TAIL_ASSERTIONS)
    assert [check.passed for check in checks] == [True, False]
    assert checks[1].reason == "no merged diff or telemetry evidence"


def test_a_dotted_tail_is_segmented_identically_at_every_wrap_width() -> None:
    joined = " ".join(_DOTTED_TAIL_ASSERTIONS)

    segmentations = {
        criteria_lines(criteria_text=_wrapped(text=joined, width=width)) for width in _WRAP_WIDTHS
    }

    assert segmentations == {_DOTTED_TAIL_ASSERTIONS}


def test_criteria_lines_keeps_a_parenthesized_abbreviation_with_its_sentence() -> None:
    # The abbreviation control, in the shape that a leading delimiter would hide:
    # `(e.g` must still read as an initialism rather than as a sentence end.
    criteria = "The parser folds a wrapped tail (e.g. The one-word one) into its sentence.\n"

    assert criteria_lines(criteria_text=criteria) == (
        "The parser folds a wrapped tail (e.g. The one-word one) into its sentence.",
    )


def test_criteria_lines_starts_a_new_assertion_after_a_trailing_initialism() -> None:
    assert criteria_lines(criteria_text=_INITIALISM_TAIL_CRITERIA) == _INITIALISM_TAIL_ASSERTIONS


def test_an_assertion_after_a_trailing_initialism_is_judged_on_its_own_evidence() -> None:
    # The discriminating control for the trailing initialism: fusing the two
    # sentences produced ONE passing check, so a condition the merged diff does
    # not carry was reported as met.
    checks = criteria_checks(
        criteria_text=_INITIALISM_TAIL_CRITERIA,
        merged_diff=_INITIALISM_TAIL_DIFF,
        telemetry_passed=False,
    )

    assert [check.text for check in checks] == list(_INITIALISM_TAIL_ASSERTIONS)
    assert [check.passed for check in checks] == [True, False]
    assert checks[1].reason == "no merged diff or telemetry evidence"


def test_a_trailing_initialism_is_segmented_identically_at_every_wrap_width() -> None:
    joined = " ".join(_INITIALISM_TAIL_ASSERTIONS)

    segmentations = {
        criteria_lines(criteria_text=_wrapped(text=joined, width=width)) for width in _WRAP_WIDTHS
    }

    assert segmentations == {_INITIALISM_TAIL_ASSERTIONS}


def test_criteria_lines_keeps_a_mid_sentence_initialism_with_its_sentence() -> None:
    # The discriminator for an ambiguous initialism is the FOLLOWING token's
    # case: a lowercase continuation means the initialism closes nothing.
    criteria = "The U.S. dispatcher releases its ledger claim on an aborted dispatch.\n"

    assert criteria_lines(criteria_text=criteria) == (
        "The U.S. dispatcher releases its ledger claim on an aborted dispatch.",
    )


def test_criteria_lines_keeps_a_single_letter_initial_with_its_sentence() -> None:
    # A single-letter initial closes no sentence whatever follows it, so the
    # capitalized surname after `C.` must not be read as a fresh assertion.
    criteria = "The parser folds a tail attributed to C. Woolley into its sentence.\n"

    assert criteria_lines(criteria_text=criteria) == (
        "The parser folds a tail attributed to C. Woolley into its sentence.",
    )


def test_criteria_lines_ignores_a_marker_that_carries_no_text() -> None:
    criteria = "-\n- The dispatcher journals the released claim.\n"

    assert criteria_lines(criteria_text=criteria) == (
        "The dispatcher journals the released claim.",
    )


def test_a_criterion_mentioning_one_verification_word_still_owes_diff_evidence() -> None:
    # The narrowing itself: one incidental verification term must not make an
    # assertion about the CODE unfailable on every green dispatch.
    assert tuple(
        term for term in _INCIDENTAL_VERIFICATION_TERMS if term in _EXTERNAL_VERIFICATION_TERMS
    ) == ("test",)

    checks = criteria_checks(
        criteria_text=_INCIDENTAL_VERIFICATION_CRITERION,
        merged_diff=_UNRELATED_DIFF,
        telemetry_passed=True,
    )

    assert [check.passed for check in checks] == [False]
    assert checks[0].reason == "no merged diff or telemetry evidence"


def test_a_verification_assertion_still_passes_on_green_telemetry() -> None:
    # The discriminating control for the narrowing: a criterion whose SUBJECT is
    # the checkable outcome has no merged-diff evidence to carry, so failing it
    # is exactly the false rework bd-ib-5z0g removed.
    checks = criteria_checks(
        criteria_text=_VERIFICATION_ASSERTION_CRITERION,
        merged_diff=_UNRELATED_DIFF,
        telemetry_passed=True,
    )

    assert [check.passed for check in checks] == [True]
    assert checks[0].reason == "matched green dispatch telemetry"


def test_a_criterion_with_no_verification_vocabulary_never_reaches_the_telemetry_arm() -> None:
    checks = criteria_checks(
        criteria_text=_CODE_ONLY_CRITERION,
        merged_diff=_UNRELATED_DIFF,
        telemetry_passed=True,
    )

    assert [check.passed for check in checks] == [False]
    assert checks[0].reason == "no merged diff or telemetry evidence"


def test_a_verification_assertion_fails_without_green_telemetry() -> None:
    # The telemetry arm is evidence, not a licence: the same assertion that
    # passes on a green dispatch must fail when nothing observed a green one.
    checks = criteria_checks(
        criteria_text=_VERIFICATION_ASSERTION_CRITERION,
        merged_diff=_UNRELATED_DIFF,
        telemetry_passed=False,
    )

    assert [check.passed for check in checks] == [False]


def test_the_diff_evidence_arm_still_requires_its_minimum_matching_terms() -> None:
    # The bd-ib-5z0g control, held across this narrowing: the diff arm's bar is
    # unchanged, so a diff one term short of the minimum still fails.
    below = _diff_carrying(terms=_CODE_ONLY_TERMS[: _DIFF_EVIDENCE_MINIMUM_TERMS - 1])
    at_minimum = _diff_carrying(terms=_CODE_ONLY_TERMS[:_DIFF_EVIDENCE_MINIMUM_TERMS])

    short_checks = criteria_checks(
        criteria_text=_CODE_ONLY_CRITERION, merged_diff=below, telemetry_passed=False
    )
    exact_checks = criteria_checks(
        criteria_text=_CODE_ONLY_CRITERION, merged_diff=at_minimum, telemetry_passed=False
    )

    assert [check.passed for check in short_checks] == [False]
    assert short_checks[0].reason == "insufficient merged diff evidence"
    assert [check.passed for check in exact_checks] == [True]
    assert exact_checks[0].reason == "matched merged diff evidence"


def test_the_pr_2446_shape_leaves_its_ci_workflow_criteria_unmet() -> None:
    # The regression itself: a merge that touched only the exemption declaration
    # and a test file was graded as having made the CI workflow edit, because the
    # declaration's prose restates that edit's own vocabulary.
    checks = criteria_checks(
        criteria_text=_PR_2446_CRITERIA, merged_diff=_PR_2446_DIFF, telemetry_passed=True
    )

    assert len(checks) == 2
    assert [check.passed for check in checks] == [False, False]
    assert {check.reason for check in checks} == {"no merged diff change under .github/workflows/"}


def test_a_criterion_evidenced_only_by_the_exemption_declaration_is_unmet() -> None:
    # The declaration exclusion on its own, with no path class named: a criterion
    # whose terms appear only in a DECLARATION of the change has no evidence that
    # the change was made.
    checks = criteria_checks(
        criteria_text=_DECLARATION_ONLY_CRITERION,
        merged_diff=_PR_2446_DIFF,
        telemetry_passed=True,
    )

    assert [check.passed for check in checks] == [False]
    assert checks[0].reason == "insufficient merged diff evidence"


def test_a_ci_workflow_criterion_is_met_when_the_workflow_path_carries_its_terms() -> None:
    # The discriminating control: the same criteria against the same merge with
    # the `.github/workflows/` edit actually landed. Scoping the search to the
    # named path class must admit real evidence, not merely refuse false evidence.
    checks = criteria_checks(
        criteria_text=_PR_2446_CRITERIA,
        merged_diff=_PR_2446_LANDED_DIFF,
        telemetry_passed=False,
    )

    assert [check.passed for check in checks] == [True, True]
    assert {check.reason for check in checks} == {"matched merged diff evidence"}
