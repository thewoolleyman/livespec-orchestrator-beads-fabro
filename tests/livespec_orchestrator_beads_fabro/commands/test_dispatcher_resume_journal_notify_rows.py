"""A refused resume's NOTIFICATION row must not pass for the factory run it never had.

`bd-ib-7uslox` narrowed the two-resume bound to resumes that went on to create a
factory run, because "the proof-loop caps are per run" and an attempt refused
before any run was created spent none of them. It recognises a created run as the
first later row for the item that names a `run_id`, which is the reading
`_run_attribution` owns.

WHY THAT NARROWING HAD NO EFFECT ON THE CASE IT WAS FILED FOR. The refusal path
ALARMS, and the alarm journals a row carrying the DISPATCHER's own per-invocation
correlation id under the key `run_id` — a uuid4 hex, not a Fabro run id. So every
refused resume was still followed by a row that names a `run_id` for the item, the
pending resume resolved as launched, and the bound counted an attempt that reached
no factory at all.

Measured 2026-10-18 on `bd-ib-nsrgxl`, pull request 3209, build 7b616ccef45b
(v0.213.1). The resume at 07:05:24Z was refused by the ACP preflight at 07:05:42Z
with no Fabro run, and `notify-sent` landed in the same second carrying run_id
cc0ac685ec9e4621b385747fb723102f. The resume at 07:24:48Z was refused and
notified the same way at 07:25:10Z with run_id 7e3b1cbe7b9a419d8333ccee7a645feb.
The third attempt, at 12:53Z, was refused: "pull request #3209 has already
anchored 2 resumes". A transient provider-headroom refusal had permanently cost
the item its resume route, leaving only a plain dispatch — which reclaims the
publish branch and discards the pull request's approved work.

WHY THE NOTIFY ROW IS PRODUCED BY THE NOTIFIER RATHER THAN SPELLED HERE. The
condition under test is a property of the row the alarm ACTUALLY writes, and a
hand-spelled `notify-sent` literal is a reconstruction of it — the shape this
repository's verification discipline calls an instrument that cannot return a hit.
Driving `notify_terminal` makes the fixture the writer's own output, so a notifier
that renamed its stage or stopped carrying an id cannot leave this case passing
against a reader that no longer covers it. The row is asserted to carry that id
BEFORE the bound is read, which is the positive control: without it, a notifier
writing no `run_id` would satisfy the case while saying nothing about the reader.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands import _dispatcher_notify as notify
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import (
    resume_journal_record,
    resumes_anchored_on,
)

_ITEM = "bd-ib-nsrgxl"
_PULL_REQUEST = 3209
_HEAD = "b" * 40

# The earlier run each attempt set out to finish, and the DISPATCHER correlation
# id its refusal's alarm journaled — a uuid4 hex, which is what no Fabro run id
# ever is.
_EARLIER_RUN = "01M53KM5V8QJ0000000000000A"
_DISPATCHER_RUN_ID = "cc0ac685ec9e4621b385747fb723102f"


class _CollectingJournal:
    """The notifier's append-one-record seam, keeping what it was handed."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


class _DeliveringPoster:
    """A poster that delivers, so the notifier journals `notify-sent`."""

    def post(self, *, url: str, body: str, title: str, timeout_seconds: float) -> bool:
        _ = url, body, title, timeout_seconds
        return True


def _notify_rows(*, work_item_id: str, run_id: str) -> tuple[dict[str, object], ...]:
    """The rows the real alarm journals for one refused dispatch of an item."""
    journal = _CollectingJournal()
    notify.notify_terminal(
        events=(notify.NotifyEvent(work_item_id=work_item_id, outcome_class="failed"),),
        run_id=run_id,
        poster=_DeliveringPoster(),
        journal=journal,
        environ={"CLAUDE_NTFY_TOPIC": "dispatcher-alarms"},
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


def test_a_resume_refused_before_any_run_anchors_nothing_though_its_alarm_named_a_run_id() -> None:
    """The measured journal: refusal, then the alarm's own row, and an unspent bound."""
    alarm_rows = _notify_rows(work_item_id=_ITEM, run_id=_DISPATCHER_RUN_ID)

    # The positive control: the condition under test is that this row DOES carry a
    # `run_id` for this item, which is what made the bound count the attempt.
    assert [row.get("run_id") for row in alarm_rows] == [_DISPATCHER_RUN_ID]
    assert [row.get("work_item_id") for row in alarm_rows] == [_ITEM]

    records = [_resume_row(earlier_run=_EARLIER_RUN), _preflight_refusal_row(), *alarm_rows]

    assert (
        resumes_anchored_on(records=records, work_item_id=_ITEM, pull_request=_PULL_REQUEST) == ()
    )
