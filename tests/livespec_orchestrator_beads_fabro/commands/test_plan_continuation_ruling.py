"""The `plan_continuation_ruling` verdict, over every ruling on a live timeline.

The mirror of `_plan_continuation_ruling`. `_plan_continuation`'s parser decides
whether the LATEST ruling is current; this verdict decides which rulings a human
has to look at, across the WHOLE timeline, so a stale malformed ruling is visible
too.

WHY EVERY CASE CARRIES A COMPLETE RULING AND TWO NON-RULINGS BESIDE IT. "The
offender is reported" is equally consistent with a verdict that reports every
ruling-shaped event, and "a complete ruling is silent" with one that reports
nothing at all. So the timeline each case runs against also holds a complete
authorization and two entries that are not rulings, and every assertion reads the
WHOLE finding set rather than one hit inside it. The malformed ruling is recorded
FIRST and the complete one after it, so a verdict that read only the latest
ruling — which is all the parser reads — would report nothing here.

WHY ONE CASE ASSERTS MEMBERSHIP WHERE THE REST ASSERT EQUALITY. A body too short
to carry its later lines is missing several at once, so equality there would pin
this module's whole arm list into the case that exists to reach the out-of-range
read. Every case whose body is complete except for the one line under test
asserts the EXACT set, which is what separates "this arm fires" from "some arm
fires".
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands import (
    _plan_continuation,
    _plan_continuation_ruling,
)
from livespec_orchestrator_beads_fabro.commands._plan_continuation_ruling import (
    PLAN_CONTINUATION_RULING_CHECK_ID,
    OpenPlanEpic,
    PlanContinuationRulingFinding,
    plan_continuation_ruling_findings,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    HANDOFF_KIND,
    SCOPE_KIND,
    PlanTimelineEntry,
)

_EPIC = "bd-ib-liveplan"
_SLUG = "a-live-plan"
_AUTHOR = "Chad Woolley"
_RECORDED_AT = "2026-10-11T09:00:00Z"
_LATER = "2026-10-12T09:00:00Z"

_AUTHORIZED = "plan-continuation: authorized"
_REVOKED = "plan-continuation: revoked"
_UNTIL = "until: archive"
_BY = "by: Chad Woolley"
_DIRECTIVE = "directive: continue to the archive without asking"
_ATTENDED = "recorded-attended: true"

_COMPLETE_AUTHORIZATION = "\n".join((_AUTHORIZED, _UNTIL, _BY, _DIRECTIVE, _ATTENDED))
_COMPLETE_REVOCATION = "\n".join((_REVOKED, _BY))
_ORDINARY_SCOPE_EVENT = "Requirement carriers:\n- one\n\nExplicit deferrals:\n- none"
_HANDOFF = "Next action: dispatch bd-ib-onemore"


def _entry(
    *, body: str, kind: str = SCOPE_KIND, created_at: str = _RECORDED_AT
) -> PlanTimelineEntry:
    return PlanTimelineEntry(kind=kind, body=body, author=_AUTHOR, created_at=created_at)


def _timeline_findings(
    *, entries: tuple[PlanTimelineEntry, ...]
) -> tuple[PlanContinuationRulingFinding, ...]:
    """Every finding over one plan epic carrying exactly `entries`."""
    return plan_continuation_ruling_findings(
        epics=(OpenPlanEpic(epic_id=_EPIC, plan_slug=_SLUG, entries=entries),)
    )


def _findings(*, malformed: str) -> tuple[PlanContinuationRulingFinding, ...]:
    """Every finding over one plan epic whose timeline holds `malformed` plus controls."""
    return _timeline_findings(
        entries=(
            _entry(body=malformed),
            _entry(body=_COMPLETE_AUTHORIZATION, created_at=_LATER),
            _entry(body=_ORDINARY_SCOPE_EVENT, created_at=_LATER),
            _entry(body=_HANDOFF, kind=HANDOFF_KIND, created_at=_LATER),
        )
    )


def test_the_check_id_is_the_verdict_name_the_contract_states() -> None:
    assert PLAN_CONTINUATION_RULING_CHECK_ID == "plan_continuation_ruling"


def test_the_ruling_line_prefixes_are_imported_rather_than_redefined() -> None:
    """The verdict reads the ruling through the parser's own vocabulary.

    The guarantee this check owes is that a ruling it reports is not current, so
    the two modules cannot be allowed to disagree about what a ruling line is. A
    second copy of a prefix would read identically on the day it was written and
    silently stop agreeing on the day either side changed.
    """
    assert "UNTIL_PREFIX" in _plan_continuation.__all__
    assert "is_continuation_ruling" in _plan_continuation.__all__
    assert "ruling_line_value" in _plan_continuation.__all__
    assert _plan_continuation_ruling.UNTIL_PREFIX is _plan_continuation.UNTIL_PREFIX
    assert _plan_continuation_ruling.is_continuation_ruling is (
        _plan_continuation.is_continuation_ruling
    )
    assert _plan_continuation_ruling.ruling_line_value is _plan_continuation.ruling_line_value


def test_a_ruling_lacking_its_until_line_is_reported_naming_the_epic_and_the_instant() -> None:
    findings = _findings(malformed="\n".join((_AUTHORIZED, _BY, _DIRECTIVE, _ATTENDED)))

    assert [
        (one.check_id, one.subject, one.verdict, one.created_at, one.missing) for one in findings
    ] == [(PLAN_CONTINUATION_RULING_CHECK_ID, _EPIC, "error", _RECORDED_AT, ("until:",))]
    [reported] = findings
    assert _RECORDED_AT in reported.event
    assert "until:" in reported.event
    assert _AUTHORIZED in reported.event
    # The conformance family requires a remediation sentence, and it must name the
    # act that clears the finding rather than restating the verdict.
    assert "re-record" in reported.remediation


def test_an_until_line_carrying_no_value_is_not_a_present_line() -> None:
    """An empty value is absence, not presence.

    An `until:` line with nothing after the colon satisfies a reader that tests
    the prefix and nothing else, and it carries no deadline for the expiry rule to
    read — which is why the parser already refuses it and why this verdict has to
    report the same body rather than certify it.
    """
    findings = _findings(malformed="\n".join((_AUTHORIZED, "until: ", _BY, _DIRECTIVE, _ATTENDED)))

    assert [one.missing for one in findings] == [("until:",)]


def test_a_body_too_short_to_carry_its_until_line_is_reported() -> None:
    """The out-of-range read, which a well-formed ruling cannot reach."""
    findings = _findings(malformed=_AUTHORIZED)

    assert len(findings) == 1
    assert "until:" in findings[0].missing


def test_a_ruling_lacking_its_by_line_is_reported() -> None:
    findings = _findings(malformed="\n".join((_AUTHORIZED, _UNTIL, _DIRECTIVE, _ATTENDED)))

    assert [one.missing for one in findings] == [("by:",)]


def test_a_ruling_lacking_its_directive_line_is_reported() -> None:
    findings = _findings(malformed="\n".join((_AUTHORIZED, _UNTIL, _BY, _ATTENDED)))

    assert [one.missing for one in findings] == [("directive:",)]


def test_a_ruling_whose_last_line_is_not_the_attended_marker_is_reported() -> None:
    """The hand-written ruling of Scenario 168, which is this verdict's whole point.

    The marker is the one line a caller cannot supply — the scope-event primitive
    writes it after every caller-provided field — so a body carrying everything
    else is exactly what a hand-authored comment looks like.
    """
    findings = _findings(
        malformed="\n".join((_AUTHORIZED, _UNTIL, _BY, _DIRECTIVE, "recorded-attended: false"))
    )

    assert [one.missing for one in findings] == [("recorded-attended: true",)]


def test_a_ruling_carrying_a_sixth_line_is_reported_though_no_line_is_missing() -> None:
    """The one malformed shape that passes every line test.

    The extra line sits in the MIDDLE rather than at the end, so `until:`, `by:`
    and `directive:` are each still at their own position and the attended marker
    is still last. Appending it instead would also break the last-line arm, and the
    case would then pass against a verdict that never counted the lines at all.
    """
    findings = _findings(
        malformed="\n".join(
            (_AUTHORIZED, _UNTIL, _BY, _DIRECTIVE, "note: appended by hand", _ATTENDED)
        )
    )

    assert [one.missing for one in findings] == [()]
    [reported] = findings
    assert "more than 5 lines" in reported.event


def test_every_missing_line_of_one_ruling_is_named_in_one_finding() -> None:
    """One ruling yields ONE finding naming all of its missing lines, never several.

    A verdict emitting one finding per missing line would satisfy every case above
    and report four offenders for one comment, which is four remediations for one
    act.
    """
    findings = _findings(malformed="\n".join((_AUTHORIZED, "stray prose")))

    assert [one.missing for one in findings] == [
        ("until:", "by:", "directive:", "recorded-attended: true")
    ]


def test_a_revocation_lacking_its_by_line_is_reported() -> None:
    findings = _findings(malformed=_REVOKED)

    assert [one.missing for one in findings] == [("by:",)]
    [reported] = findings
    assert _REVOKED in reported.event


def test_a_revocation_whose_by_line_carries_no_value_is_reported() -> None:
    findings = _findings(malformed="\n".join((_REVOKED, "by: ")))

    assert [one.missing for one in findings] == [("by:",)]


def test_a_complete_revocation_is_silent() -> None:
    """A revocation owes its `by:` line and nothing else.

    It is two lines by construction, so neither the attended marker nor the
    five-line count is a condition on it — a verdict that applied the
    authorization's arms here would report every well-formed revocation ever
    written.
    """
    assert _timeline_findings(entries=(_entry(body=_COMPLETE_REVOCATION),)) == ()


def test_a_complete_authorization_is_silent() -> None:
    assert _timeline_findings(entries=(_entry(body=_COMPLETE_AUTHORIZATION),)) == ()


def test_a_timeline_carrying_no_ruling_is_silent() -> None:
    """Neither an ordinary scope event nor a handoff is a ruling.

    The handoff body is ruling-SHAPED — its first line is the authorization
    prefix — so this also pins the kind test: a verdict keyed on the first line
    alone would report a handoff comment nobody can record a ruling in.
    """
    assert (
        _timeline_findings(
            entries=(
                _entry(body=_ORDINARY_SCOPE_EVENT),
                _entry(body=_HANDOFF, kind=HANDOFF_KIND),
                _entry(body=_AUTHORIZED, kind=HANDOFF_KIND),
            )
        )
        == ()
    )


def test_each_epic_handed_in_reports_its_own_rulings_under_its_own_id() -> None:
    """The verdict is over a SET of epics, and each finding names the epic it came from.

    Two epics rather than one, each with a different malformed ruling: a verdict
    that reported the right count while attributing both to the first epic would
    satisfy every single-epic case above.
    """
    second = "bd-ib-otherplan"
    findings = plan_continuation_ruling_findings(
        epics=(
            OpenPlanEpic(
                epic_id=_EPIC,
                plan_slug=_SLUG,
                entries=(_entry(body="\n".join((_AUTHORIZED, _UNTIL, _BY, _ATTENDED))),),
            ),
            OpenPlanEpic(
                epic_id=second,
                plan_slug="another-live-plan",
                entries=(
                    _entry(body=_COMPLETE_AUTHORIZATION),
                    _entry(body=_REVOKED, created_at=_LATER),
                ),
            ),
        )
    )

    assert [(one.subject, one.created_at, one.missing) for one in findings] == [
        (_EPIC, _RECORDED_AT, ("directive:",)),
        (second, _LATER, ("by:",)),
    ]
