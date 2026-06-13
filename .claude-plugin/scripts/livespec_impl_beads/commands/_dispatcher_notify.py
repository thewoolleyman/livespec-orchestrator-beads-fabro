"""Fail-open ntfy alarm for terminal dispatcher failures (operability gate).

0jxs operability precondition (USER-RATIFIED HARD requirement before the
W6 dark-factory cutover, epic livespec-4moata): an UNATTENDED dispatcher
run must ALARM a human on any terminal `failed` / `blocked` /
`stalled-no-progress` outcome, a non-green loop-end summary, or a
spend-cap breach, so a dark-factory run can never fail silently. This
module is the single reusable, fail-OPEN notifier those trigger points
call.

Trigger points wired today (`dispatcher._run_dispatch_command` /
`_run_loop_command`): a terminal `failed` outcome (including uvd's
`host-only-refused` stage and oyg's `stalled-no-progress` watchdog
outcome — both are `DispatchOutcome`s with a non-green `status`, so they
flow through `terminal_events` automatically, no per-class wiring), a
`blocked` outcome (parked at the in-loop human gate), and a non-green
loop-end summary. The remaining future producer (`spend-cap` breach is
y0m's class) is NOT a `DispatchOutcome.status`; it will call
`notify_terminal` with its own `NotifyEvent` once it exists, which is
exactly why this is a single reusable function rather than inline POST
calls.

Load-bearing invariant — **FAIL-OPEN**: the dispatch verdict / exit code
is computed by the caller BEFORE this stage runs, and nothing here flows
back into it. A missing topic, an unreachable server, an HTTP error, or a
hung POST (bounded by a short timeout) is caught, journaled as a
`notify-error` (or `notify-skipped`) record, and is otherwise a no-op. A
notification failure NEVER changes an outcome and NEVER blocks exit.

Credential hygiene (strict — mirrors the `_dispatcher_reflection` scrub
discipline, cc-otel-gap-analysis.md §3.6): the body ships ONLY the
work-item id, the outcome CLASS, and the run id. NEVER goal text, env
values, stderr blobs, file contents, the dispatch `detail`, or any remote
URL (which in this fleet can embed a PAT). A defense-in-depth regex fails
CLOSED on any credential-shaped value rather than redacting partially.

ntfy mechanism (mirrors the claude-code-ntfy plugin in daily host use):
the host posts a plain-body HTTP POST to `<server>/<topic>`. The topic
resolves from `CLAUDE_NTFY_DISPATCHER_TOPIC` (a DEDICATED dispatcher
topic) and falls back to `CLAUDE_NTFY_TOPIC`; an unset/empty topic makes
the notifier a silent no-op (a dispatch is never failed merely because
notifications are unconfigured). The server resolves from
`CLAUDE_NTFY_SERVER` and defaults to `https://ntfy.sh`, exactly as the
plugin's `notify-ready.sh` resolves them.
"""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from livespec_impl_beads.commands._dispatcher_engine import DispatchOutcome

__all__: list[str] = [
    "HttpNotifyPoster",
    "NotifyEvent",
    "NotifyPoster",
    "notify_terminal",
    "resolve_server",
    "resolve_topic",
    "terminal_events",
]

# The outcome class for the wave-level non-green loop-end summary (a
# distinct alarm class from any single item's failed/blocked status).
_NON_GREEN_LOOP_CLASS = "non-green-loop"
_LOOP_SUMMARY_ITEM_ID = "(loop)"

# Env-var NAMES (not secret values). The dedicated dispatcher topic is
# preferred so the alarm channel is not interleaved with the harness's
# own Stop/Notification pushes on CLAUDE_NTFY_TOPIC; the shared topic is
# the documented fallback.
_DISPATCHER_TOPIC_ENV = "CLAUDE_NTFY_DISPATCHER_TOPIC"
_SHARED_TOPIC_ENV = "CLAUDE_NTFY_TOPIC"
_SERVER_ENV = "CLAUDE_NTFY_SERVER"
_DEFAULT_SERVER = "https://ntfy.sh"

# Short POST timeout so a hung ntfy server can never stall the dispatcher
# at the verdict boundary (fail-open invariant). The dispatch has already
# decided its exit code; the alarm is strictly best-effort.
_POST_TIMEOUT_SECONDS = 5.0

# The push notification's Title header (the human-visible alarm summary).
_NTFY_TITLE = "livespec dispatcher: terminal failure"

# Defense-in-depth: reject any value that looks like a credential-bearing
# URL (`scheme://user:secret@host`) rather than redacting — a scrub miss
# must fail closed (cc-otel-gap-analysis.md §3.6). Identical shape to the
# reflection emitter's guard.
_CREDENTIAL_URL_RE = re.compile(r"[a-zA-Z0-9_-]+:[^@\s/]+@")
_REDACTION_MARKER = "[redacted]"

# Hard ceiling on every field that reaches the body, so an oversized id or
# class can never carry a smuggled blob.
_FIELD_MAX_LEN = 200


class JournalWriter(Protocol):
    """Append-one-record seam (mirrors `_dispatcher_engine.JournalWriter`)."""

    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


class NotifyPoster(Protocol):
    """The single HTTP-POST seam the notifier publishes through.

    Production is `HttpNotifyPoster`; the hermetic test tier injects a
    fake so no test ever makes a real network call. An implementation
    SHOULD return True on a delivered notification and False (or raise —
    `notify_terminal` catches everything) on any failure.
    """

    def post(self, *, url: str, body: str, title: str, timeout_seconds: float) -> bool:
        """POST `body` to `url`; return delivery success."""
        ...


@dataclass(frozen=True, kw_only=True)
class NotifyEvent:
    """One terminal condition worth alarming on.

    Carries ONLY the two leak-free fields the alarm body needs per the
    credential-hygiene contract: the work-item id and the outcome CLASS
    (`failed` / `blocked` / `stalled-no-progress` / `spend-cap-breach` /
    `non-green-loop`). The run id is supplied once per wave to
    `notify_terminal`, not per event.
    """

    work_item_id: str
    outcome_class: str


def terminal_events(
    *,
    outcomes: tuple[DispatchOutcome, ...],
    include_loop_summary: bool,
) -> tuple[NotifyEvent, ...]:
    """Derive the alarm events for a wave of outcomes.

    One event per non-green outcome (class = the leak-free `status`:
    `failed`, `blocked`, or oyg's `stalled-no-progress`). This covers
    uvd's `host-only-refused` (a `failed` outcome) and oyg's
    `stalled-no-progress` watchdog outcome automatically — any non-green
    `DispatchOutcome.status` becomes an alarm class with no per-class
    wiring. When `include_loop_summary` is set (the loop command) and any
    outcome is non-green, one additional `non-green-loop` summary event is
    appended so a non-green loop-end is alarmed as its own class. A
    fully-green wave yields no events (the notifier then no-ops). The
    `spend-cap` class (y0m) is not a `DispatchOutcome.status`; it will
    build its own `NotifyEvent` and call `notify_terminal` directly.
    """
    events = tuple(
        NotifyEvent(work_item_id=outcome.work_item_id, outcome_class=outcome.status)
        for outcome in outcomes
        if outcome.status != "green"
    )
    if include_loop_summary and events:
        events = (
            *events,
            NotifyEvent(work_item_id=_LOOP_SUMMARY_ITEM_ID, outcome_class=_NON_GREEN_LOOP_CLASS),
        )
    return events


@dataclass(frozen=True, kw_only=True)
class HttpNotifyPoster:
    """Production `NotifyPoster`: a plain-body HTTP POST via urllib.

    Mirrors the claude-code-ntfy plugin's POST shape (the message rides
    the request body; the alarm summary rides the `Title` header). Returns
    True on a 2xx, False on any HTTP / network error — it never raises, so
    a poster failure is data, but `notify_terminal`'s supervisor catches
    anything regardless.
    """

    def post(self, *, url: str, body: str, title: str, timeout_seconds: float) -> bool:
        request = urllib.request.Request(  # noqa: S310 - scheme is our own https default / env
            url,
            data=body.encode("utf-8"),
            method="POST",
            headers={"Title": title},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds):  # noqa: S310
                return True
        except (urllib.error.URLError, OSError, ValueError):
            return False


def resolve_topic(*, environ: dict[str, str]) -> str | None:
    """Resolve the dedicated dispatcher topic, falling back to the shared one.

    Returns the dedicated `CLAUDE_NTFY_DISPATCHER_TOPIC` when set and
    non-empty, else the shared `CLAUDE_NTFY_TOPIC`, else None. A None
    result makes the notifier a silent no-op (notifications unconfigured
    must never fail a dispatch).
    """
    dedicated = environ.get(_DISPATCHER_TOPIC_ENV, "")
    if dedicated != "":
        return dedicated
    shared = environ.get(_SHARED_TOPIC_ENV, "")
    if shared != "":
        return shared
    return None


def resolve_server(*, environ: dict[str, str]) -> str:
    """Resolve the ntfy server, defaulting to https://ntfy.sh.

    Matches the claude-code-ntfy plugin: `CLAUDE_NTFY_SERVER` overrides,
    otherwise the public default. A trailing slash is trimmed so the
    `<server>/<topic>` join never doubles it.
    """
    server = environ.get(_SERVER_ENV, "")
    if server == "":
        server = _DEFAULT_SERVER
    return server.rstrip("/")


def notify_terminal(
    *,
    events: tuple[NotifyEvent, ...],
    run_id: str,
    poster: NotifyPoster,
    journal: JournalWriter,
    environ: dict[str, str] | None = None,
) -> None:
    """Fail-open: POST one ntfy alarm per terminal `event`. NEVER raises.

    Called by the dispatcher AFTER the verdict / exit code is computed, so
    nothing here can change it. With no events, it is a no-op. With the
    topic unset it journals `notify-skipped` and returns (unconfigured
    notifications never fail a dispatch). Otherwise it POSTs a leak-free
    body (work-item id + outcome class + run id ONLY) per event through
    the injected `poster`, journaling `notify-sent` / `notify-failed` per
    event. Any exception anywhere is caught, journaled as `notify-error`,
    and swallowed — the alarm is strictly best-effort.
    """
    if not events:
        return
    try:
        _notify(events=events, run_id=run_id, poster=poster, journal=journal, environ=environ)
    except Exception as exc:
        # Fail-open supervisor: the verdict is already final, so a broad
        # catch is the whole point — any error is journaled and swallowed,
        # never raised (0jxs operability gate, mirroring the reflection
        # stage's fail-open supervisor).
        journal.append(
            record={
                "stage": "notify-error",
                "reason": f"{type(exc).__name__}: {_scrub(value=str(exc))}",
            }
        )


def _notify(
    *,
    events: tuple[NotifyEvent, ...],
    run_id: str,
    poster: NotifyPoster,
    journal: JournalWriter,
    environ: dict[str, str] | None,
) -> None:
    """The POST body wrapped fail-open by `notify_terminal`."""
    env = dict(os.environ) if environ is None else environ
    topic = resolve_topic(environ=env)
    if topic is None:
        journal.append(record={"stage": "notify-skipped", "reason": "no ntfy topic configured"})
        return
    url = f"{resolve_server(environ=env)}/{topic}"
    safe_run_id = _clip(value=_scrub(value=run_id))
    for event in events:
        _post_one(
            event=event,
            run_id=safe_run_id,
            url=url,
            poster=poster,
            journal=journal,
        )


def _post_one(
    *,
    event: NotifyEvent,
    run_id: str,
    url: str,
    poster: NotifyPoster,
    journal: JournalWriter,
) -> None:
    work_item_id = _clip(value=_scrub(value=event.work_item_id))
    outcome_class = _clip(value=_scrub(value=event.outcome_class))
    body = _build_body(work_item_id=work_item_id, outcome_class=outcome_class, run_id=run_id)
    delivered = poster.post(
        url=url,
        body=body,
        title=_NTFY_TITLE,
        timeout_seconds=_POST_TIMEOUT_SECONDS,
    )
    journal.append(
        record={
            "stage": "notify-sent" if delivered else "notify-failed",
            "work_item_id": work_item_id,
            "outcome_class": outcome_class,
            "run_id": run_id,
        }
    )


def _build_body(*, work_item_id: str, outcome_class: str, run_id: str) -> str:
    """The leak-free alarm body: work-item id + outcome class + run id ONLY."""
    lines = (f"work-item: {work_item_id}", f"outcome: {outcome_class}", f"run: {run_id}")
    return "\n".join(lines)


def _scrub(*, value: str) -> str:
    """Fail-closed credential scrub: replace a token-URL-shaped value wholesale.

    A scrub miss must fail closed (cc-otel-gap-analysis.md §3.6): a value
    matching the credential-URL shape is replaced with a marker rather
    than shipped partially.
    """
    if _CREDENTIAL_URL_RE.search(value) is not None:
        return _REDACTION_MARKER
    return value


def _clip(*, value: str) -> str:
    """Hard length ceiling so no field can carry a smuggled blob."""
    return value[:_FIELD_MAX_LEN]
