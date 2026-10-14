"""Apply the semantic pre-admission verdict at the ledger's readiness boundary."""

from __future__ import annotations

from typing import cast

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._pre_admission_dod import judge_before_admission
from livespec_orchestrator_beads_fabro._pre_admission_verdict import DodVerdict, parse_judgement
from livespec_orchestrator_beads_fabro.commands._otel_scrub import (
    CREDENTIAL_URL_RE,
    REDACTION_MARKER,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "PRE_ADMISSION_DOD_KEY",
    "pre_admission_hold",
]


PRE_ADMISSION_DOD_KEY = "pre_admission_dod"


def pre_admission_hold(*, path: StoreConfig, item: WorkItem) -> str | None:
    """Return the needs-human finding, or allow the existing admission route.

    Unavailable judgements cannot create a hold: the in-run gate remains the
    backstop. Every readiness writer calls this same decision boundary.
    """
    result = judge_before_admission(path=path, item=item).bind_result(
        lambda response: parse_judgement(response=response)
    )
    if not is_successful(result):
        _record_unavailable(path=path, item=item, reason=unsafe_perform_io(result.failure()))
        return None
    verdict = unsafe_perform_io(result.unwrap())
    if verdict.failure_reason is not None:
        _record_hold(path=path, item=item, verdict=verdict)
    else:
        _write_state(path=path, item_id=item.id, state=None)
    return verdict.failure_reason


def _record_hold(*, path: StoreConfig, item: WorkItem, verdict: DodVerdict) -> None:
    """Keep the current hold separately from the append-only explanation.

    Only our top-level metadata key is replaced; unrelated metadata and nested
    audit provenance are carried verbatim from the raw record, never rebuilt
    from the narrower WorkItem projection.
    """
    reason = _ledger_text(text=str(verdict.failure_reason))
    remedies = [_ledger_text(text=remedy) for remedy in verdict.remedies]
    _write_state(
        path=path,
        item_id=item.id,
        state={
            "verdict": "needs-human",
            "failure_reason": reason,
            "remedies": remedies,
        },
    )
    client = make_beads_client(config=path)
    client.add_comment(
        issue_id=item.id,
        body="\n".join(
            [
                "livespec-pre-admission-dod",
                "",
                "verdict: needs-human",
                "",
                reason,
                "",
                "Remedies:",
                *(f"- {remedy}" for remedy in remedies),
            ]
        ),
    )


def _record_unavailable(*, path: StoreConfig, item: WorkItem, reason: str) -> None:
    """Explain a fail-open admission without retaining an earlier semantic hold."""
    _write_state(path=path, item_id=item.id, state=None)
    make_beads_client(config=path).add_comment(
        issue_id=item.id,
        body=(
            "livespec-pre-admission-dod\n\nverdict: unavailable\n\n"
            f"The pre-admission judgement did not run: {_ledger_text(text=reason)}"
        ),
    )


def _write_state(*, path: StoreConfig, item_id: str, state: dict[str, object] | None) -> None:
    """Replace our current verdict while preserving the raw metadata snapshot.

    A null value clears a resolved hold on both the fake store and beads:
    omission cannot clear it because beads merges top-level metadata keys.
    Historical comments remain append-only.
    """
    client = make_beads_client(config=path)
    metadata = dict(
        cast("dict[str, object]", client.show_issue(issue_id=item_id).get("metadata") or {})
    )
    metadata[PRE_ADMISSION_DOD_KEY] = state
    client.update_issue(issue_id=item_id, metadata=metadata)


def _ledger_text(*, text: str) -> str:
    """Keep every remedy without letting external text poison a later dispatch.

    Unlike bounded stderr summaries, verdicts must not be truncated. Credential
    shapes are redacted and template openers are rendered as literal brackets,
    following the existing needs-human comment writer's safety convention.
    """
    if CREDENTIAL_URL_RE.search(text) is not None:
        return REDACTION_MARKER
    return text.replace("{{", "[[").replace("{%", "[%").replace("{#", "[#")
