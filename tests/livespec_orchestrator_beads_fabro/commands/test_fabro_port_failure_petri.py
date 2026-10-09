"""The failure reader reads the NESTED `failure.detail` block, not just a flat one.

The Petri-era engine (0.378.0-nightly.0, measured 2026-10-08 — research notes
006 and 007 of `plan/fabro-currency`) reports a failed run as
`conclusion.failure = {reason, detail: {message, category}}` and carries NO
`causes` and NO `signature`. The pinned 0.254 build emits the same nested shape
at `conclusion.failure`, and happened also to carry a FLAT
`checkpoint.failure = {message, category}` that the reader could already see —
which is the only reason the nested shape was never read.

So these are not engine branches. One reader covers both, keyed on the block's
own structure rather than on a version string no payload carries. The Petri
assertions below fail before that change because the nested block yields no
cause, no category and no signature, and the reader then correctly fails closed
on it — returning `None` for a run whose failure is fully described.

The fail-closed assertion is the load-bearing one, and it is the reason the
reader may not simply treat any `failure` mapping as classified: a block whose
variant this reader does not recognize must stay `None`, because a populated
record carrying three `None` fields asserts that the failure WAS classified and
found to be nothing in particular, and that assertion is laundered into a retry
decision downstream.
"""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro.commands._fabro_port_failure import (
    fabro_failure_detail_from_payload,
)

# The needs-human marker arrives inside `detail.message` on this engine, because
# a goal-gated script node's stderr is what populates that field (probe p6,
# research note 007, run 01M4DCSSJM6C).
_PETRI_NEEDS_HUMAN_MESSAGE = (
    "LIVESPEC_NEEDS_HUMAN: the acceptance criteria name a scenario this slice "
    "cannot bind\nscript exited with status 1"
)


def _petri_payload(*, message: str, category: str) -> list[dict[str, Any]]:
    """An `inspect --json` record in the Petri-era shape, failure block and all."""
    return [
        {
            "run_id": "01M4DCSSJM6C",
            "parent_id": None,
            "status": {"kind": "failed", "reason": "node_failed"},
            "run_spec": {},
            "sandbox": {},
            "stages": [],
            "start_record": {},
            "checkpoint": {},
            "conclusion": {
                "diff": "",
                "final_git_commit_sha": "2aaa5085",
                "stages": [],
                "status": "failed",
                "timestamp": "2026-10-08T12:00:00Z",
                "timing": {},
                "total_retries": 0,
                "failure": {
                    "reason": "script exited with status 1",
                    "detail": {"message": message, "category": category},
                },
            },
        }
    ]


def test_petri_failure_block_yields_its_category_and_message() -> None:
    detail = fabro_failure_detail_from_payload(
        payload=_petri_payload(message=_PETRI_NEEDS_HUMAN_MESSAGE, category="node_failure")
    )

    assert detail is not None
    assert detail.category == "node_failure"
    assert detail.cause == _PETRI_NEEDS_HUMAN_MESSAGE
    assert detail.signature is None


def test_petri_spend_ceiling_is_classified_from_the_nested_message() -> None:
    """A provider ceiling must stay permanent on the engine that drops `causes`.

    The pinned build carried the ceiling sentence in its cause chain, which is
    the only place the classifier looked. On Petri the same sentence arrives in
    `detail.message`, so a reader that scans only `causes` reports a spend
    ceiling as an ordinary retryable failure and the admission gate launches
    another sandbox against an allowance that is already gone.
    """
    detail = fabro_failure_detail_from_payload(
        payload=_petri_payload(
            message="You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage",
            category="transient_infra",
        )
    )

    assert detail is not None
    assert detail.provider_usage_limit is True
    assert detail.provider_usage_limit_provider == "codex"
    assert detail.category == "deterministic"


def test_an_unrecognized_failure_variant_still_fails_closed() -> None:
    payload: list[dict[str, Any]] = [
        {
            "run_id": "01M4DCSSJM6C",
            "status": {"kind": "failed", "reason": "node_failed"},
            # No `causes`, no `signature`, no `category`, and a `detail` that
            # carries neither of the two keys this reader knows how to read.
            "conclusion": {"failure": {"reason": "something new", "detail": {"hint": "unknown"}}},
        }
    ]

    assert fabro_failure_detail_from_payload(payload=payload) is None


def test_the_legacy_flat_block_is_read_exactly_as_before() -> None:
    payload: list[dict[str, Any]] = [
        {
            "run_id": "01M0EFZND0Z7K2SY1H21Q59GVF",
            "status": {"kind": "failed", "reason": "workflow_error"},
            "conclusion": {
                "failure": {
                    "causes": ["ACP protocol error", "script failed with exit 2"],
                    "category": "infra",
                    "signature": "node|transient_infra|exit",
                }
            },
        }
    ]

    detail = fabro_failure_detail_from_payload(payload=payload)

    assert detail is not None
    assert detail.cause == "script failed with exit 2"
    assert detail.category == "infra"
    assert detail.signature == "node|transient_infra|exit"
