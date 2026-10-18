"""The two-resume bound's remaining assertions, once a notify row no longer names a run.

Every case here is satisfied by the ONE predicate `bd-ib-upqaqw` added to
`_run_attribution` — the exclusion of the notifier's `notify-` stages from the
Fabro-run reading — which is why they land on the suite-green leg rather than each
carrying its own Red: the behaviour was already implemented by the time they were
written, and the commit hook refuses a Red whose test passes. The Red itself is
`test_dispatcher_resume_journal_notify_rows.py`, which records the measured
journal and the mechanism.

WHICH OF THEM ARE CONTROLS, MEASURED RATHER THAN ASSUMED. The first draft of this
docstring called all four controls — cases that "could not fail before the change
landed". That was wrong, and the discriminator was a mutation: with the exclusion
deleted from `_named_fabro_run` (the deletion asserted to have applied, per
AGENTS.md's mutation-did-not-apply trap), THREE of the four fail — the unspent
bound, the newest-run reading, and the prefix walk — while
`test_two_resumes_that_each_created_a_run_still_refuse_a_third_naming_both`
passes. So only that last one is a control in the strict sense; the other three
are behavioural assertions of the same predicate, and each would have earned its
own Red had one predicate not satisfied all of them at once. Recorded here
because "this cannot fail" is exactly the claim this repository's verification
discipline says foreclose action and then stop being examined.

WHY THE CONTROL EARNS ITS PLACE ANYWAY. A predicate is only right in so far as the
refusal it feeds comes out the right way round in BOTH directions. The two refusal
cases are deliberately the same journal shape differing in ONE row per attempt:
whether each attempt's refusal was followed by a `fabro-run` row or only by the
alarm's own. A build that excluded too much — the whole `run_id` key, say —
satisfies the unspent case while silently retiring the bound altogether, and the
launched case is the only thing in the suite that fails on it. A build that
excluded too little satisfies the launched case while leaving the measured defect
in place, which is what the Red covers. Neither direction is evidence alone.

WHY THE REFUSAL IS READ THROUGH THE LADDER RATHER THAN OFF THE COUNT. The
assertion is about a third resume attempt being refused or not, and that verdict
is `resume_refusals`'s, not `resumes_anchored_on`'s. Both cases therefore compose
the real pair — the journal reader feeding the real observation feeding the real
ladder — against a world in which EVERY other measurement comes back clean, so the
bound is the only arm that can speak. The unspent case asserts the WHOLE refusal
tuple is empty rather than merely that no bound refusal appears, which is what
proves that world clean; without it, an observation tripping some earlier arm
would report "not refused by the bound" while refusing the resume for a reason
nobody checked.

WHY THE NOTIFIER'S THIRD STAGE IS BOUND HERE TOO. The reader excludes a stage
PREFIX, and nothing in that predicate establishes that the notifier's rows carry
it. The last case walks every stage the alarm actually journals — including the
`notify-skipped` arm no refusal path reaches, which is exactly the one a prefix
rule must already cover — and asserts each is excluded from the Fabro-run reading.
It is the positive control for the prefix: without it, a notifier renamed out of
the prefix would leave every case above passing against a reader that no longer
covers it.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands import _dispatcher_notify as notify
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import (
    resume_journal_record,
    resumes_anchored_on,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    PR_STATE_OPEN,
    ResumeObservation,
    resume_refusals,
)
from livespec_orchestrator_beads_fabro.commands._run_attribution import (
    journaled_run_ids,
    newest_journaled_run_id,
)

_ITEM = "bd-ib-nsrgxl"
_PULL_REQUEST = 3209
_HEAD = "b" * 40

# The two earlier runs the two attempts each set out to finish, and the Fabro run
# a LAUNCHED resume of each would have created.
_FIRST_EARLIER_RUN = "01M53KM5V8QJ0000000000000A"
_SECOND_EARLIER_RUN = "01M53KM5V8QJ0000000000000B"
_FIRST_RESUMED_RUN = "01M53KM5V8QJ0000000000000C"
_SECOND_RESUMED_RUN = "01M53KM5V8QJ0000000000000D"

# The dispatcher correlation ids the two refusals' alarms journaled, as measured.
_FIRST_ALARM_ID = "cc0ac685ec9e4621b385747fb723102f"
_SECOND_ALARM_ID = "7e3b1cbe7b9a419d8333ccee7a645feb"

_ANCHORED_REFUSAL_MARKER = "has already anchored"


class _CollectingJournal:
    """The notifier's append-one-record seam, keeping what it was handed."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


class _DeliveringPoster:
    """A poster that delivers, so the notifier journals its `sent` stage."""

    def post(self, *, url: str, body: str, title: str, timeout_seconds: float) -> bool:
        _ = url, body, title, timeout_seconds
        return True


class _FailingPoster:
    """A poster that does not deliver, so the notifier journals its `failed` stage."""

    def post(self, *, url: str, body: str, title: str, timeout_seconds: float) -> bool:
        _ = url, body, title, timeout_seconds
        return False


def _alarm_rows(
    *,
    run_id: str,
    poster: notify.NotifyPoster | None = None,
    environ: dict[str, str] | None = None,
) -> tuple[dict[str, object], ...]:
    """The rows the real alarm journals for one terminal dispatch of the item."""
    journal = _CollectingJournal()
    notify.notify_terminal(
        events=(notify.NotifyEvent(work_item_id=_ITEM, outcome_class="failed"),),
        run_id=run_id,
        poster=_DeliveringPoster() if poster is None else poster,
        journal=journal,
        environ={"CLAUDE_NTFY_TOPIC": "dispatcher-alarms"} if environ is None else environ,
    )
    return tuple(journal.records)


def _resume_row(*, earlier_run: str) -> dict[str, object]:
    """One journaled resume attempt of this pull request, as the Dispatcher writes it."""
    return resume_journal_record(
        work_item_id=_ITEM,
        earlier_run_ids=(earlier_run,),
        pull_request=_PULL_REQUEST,
        head=_HEAD,
        resumed_at="pr",
        source="pull-request-latest-record",
    )


def _preflight_refusal_row() -> dict[str, object]:
    """The ACP preflight's refusal: an attempt that reached no factory, so names no run."""
    return {
        "stage": "acp-preflight-refusal",
        "work_item_id": _ITEM,
        "detail": "session-headroom-shortfall",
    }


def _fabro_run_row(*, run_id: str) -> dict[str, object]:
    """The row a LAUNCHED dispatch writes on first sight of its factory run id."""
    return {"stage": "fabro-run", "work_item_id": _ITEM, "run_id": run_id}


def _refused_attempts() -> list[dict[str, object]]:
    """Two attempts, each refused before any run, each refusal alarmed.

    The measured journal of pull request 3209: resume, preflight refusal, alarm;
    resume, preflight refusal, alarm. No `fabro-run` row anywhere.
    """
    return [
        _resume_row(earlier_run=_FIRST_EARLIER_RUN),
        _preflight_refusal_row(),
        *_alarm_rows(run_id=_FIRST_ALARM_ID),
        _resume_row(earlier_run=_SECOND_EARLIER_RUN),
        _preflight_refusal_row(),
        *_alarm_rows(run_id=_SECOND_ALARM_ID),
    ]


def _launched_attempts() -> list[dict[str, object]]:
    """Two resumes that each CREATED a factory run, each run then alarming.

    One row different from `_refused_attempts` per attempt — the `fabro-run` row —
    and the alarms are kept so the launched case cannot pass merely by carrying no
    notification rows at all.
    """
    return [
        _resume_row(earlier_run=_FIRST_EARLIER_RUN),
        _fabro_run_row(run_id=_FIRST_RESUMED_RUN),
        *_alarm_rows(run_id=_FIRST_ALARM_ID),
        _resume_row(earlier_run=_SECOND_EARLIER_RUN),
        _fabro_run_row(run_id=_SECOND_RESUMED_RUN),
        *_alarm_rows(run_id=_SECOND_ALARM_ID),
    ]


def _observation(*, earlier_resumes: tuple[str, ...]) -> ResumeObservation:
    """A world in which every measurement but the chain count comes back clean.

    Ready item, an anchor at the pull request's own head, the forge and the
    factory both answering, nothing alive, no lock, no Definition-of-Done
    difference, pull request open. So the only arm of the ladder that can refuse
    is the bound, which is what makes an empty refusal tuple readable as "the
    bound did not refuse" rather than as luck.
    """
    return ResumeObservation(
        work_item_id=_ITEM,
        status="ready",
        anchor_head=_HEAD,
        forge_observed=True,
        pull_request=_PULL_REQUEST,
        pull_request_state=PR_STATE_OPEN,
        pull_request_head=_HEAD,
        records_observed=True,
        live_runs=(),
        liveness_observed=True,
        lock_age_seconds=None,
        changed_assertions=(),
        earlier_resumes=earlier_resumes,
        unanchoring_cancel_stage=None,
    )


def _refusals_for(*, records: list[dict[str, object]]) -> tuple[str, ...]:
    """The real ladder's verdict for a third attempt against one journal."""
    anchored = resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=_PULL_REQUEST)
    return resume_refusals(observation=_observation(earlier_resumes=anchored))


def test_two_resumes_refused_before_any_run_leave_a_third_attempt_unrefused() -> None:
    """Each refusal journaled an alarm row, and the bound still has nothing to count."""
    records = _refused_attempts()

    # The condition under test exists: both alarms DID name a `run_id` for this
    # item, which is what used to resolve each refused attempt as launched.
    assert [row.get("run_id") for row in records if "run_id" in row] == [
        _FIRST_ALARM_ID,
        _SECOND_ALARM_ID,
    ]
    assert (
        resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=_PULL_REQUEST) == ()
    )
    # The whole tuple, not just the bound's arm: an empty one is what establishes
    # that nothing else in this world refuses either.
    assert _refusals_for(records=records) == ()


def test_two_resumes_that_each_created_a_run_still_refuse_a_third_naming_both() -> None:
    """The bound is narrowed, not retired — the only case that fails on over-exclusion."""
    records = _launched_attempts()

    assert resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=_PULL_REQUEST) == (
        _FIRST_EARLIER_RUN,
        _SECOND_EARLIER_RUN,
    )

    refusals = _refusals_for(records=records)

    assert len(refusals) == 1
    assert _ANCHORED_REFUSAL_MARKER in refusals[0]
    assert "2 resumes" in refusals[0]
    assert _FIRST_EARLIER_RUN in refusals[0]
    assert _SECOND_EARLIER_RUN in refusals[0]


def test_the_newest_journaled_run_reading_never_returns_an_alarm_rows_run_id() -> None:
    """Proof attribution reads these, so an alarm id here is attributed to a run.

    The alarm row is the NEWEST row of the journal, which is the position that
    decides the singular reading — so a reader that merely preferred an earlier
    `fabro-run` row for some other reason would pass while still returning the
    alarm id here.
    """
    records = [
        _resume_row(earlier_run=_FIRST_EARLIER_RUN),
        _fabro_run_row(run_id=_FIRST_RESUMED_RUN),
        *_alarm_rows(run_id=_FIRST_ALARM_ID),
    ]

    assert newest_journaled_run_id(records=records, work_item_id=_ITEM) == _FIRST_RESUMED_RUN
    assert journaled_run_ids(records=records, work_item_id=_ITEM) == (_FIRST_RESUMED_RUN,)

    # And with no factory run at all the reading is the ABSENCE of one, never the
    # alarm's id — the arm a preference-ordering build would get wrong.
    alarm_only = [_resume_row(earlier_run=_FIRST_EARLIER_RUN), *_alarm_rows(run_id=_FIRST_ALARM_ID)]

    assert newest_journaled_run_id(records=alarm_only, work_item_id=_ITEM) is None
    assert journaled_run_ids(records=alarm_only, work_item_id=_ITEM) == ()


def test_every_stage_the_alarm_journals_is_excluded_from_the_fabro_run_reading() -> None:
    """The prefix rule's positive control, including the arm no refusal path reaches.

    Walks the three stages the notifier actually writes — delivered, undelivered,
    and the unconfigured-topic skip — and asserts each is excluded. The skip row
    carries no `run_id` and so is already harmless today; it is here because the
    claim being bound is about the PREFIX covering what this writer produces, and
    a stage that drifted out of the prefix would be invisible to every other case.
    """
    written = [
        *_alarm_rows(run_id=_FIRST_ALARM_ID, poster=_DeliveringPoster()),
        *_alarm_rows(run_id=_FIRST_ALARM_ID, poster=_FailingPoster()),
        *_alarm_rows(run_id=_FIRST_ALARM_ID, environ={}),
    ]

    # Three distinct stages, so the walk below is not three readings of one row.
    assert len({row.get("stage") for row in written}) == 3

    for row in written:
        assert journaled_run_ids(records=(row,), work_item_id=_ITEM) == ()
        assert newest_journaled_run_id(records=(row,), work_item_id=_ITEM) is None
