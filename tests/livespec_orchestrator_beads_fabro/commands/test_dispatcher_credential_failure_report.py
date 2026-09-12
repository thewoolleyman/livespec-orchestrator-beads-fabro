"""Classifying a failed run against the credential the manager provisioned.

The classification cases are paired deliberately. Every positive case names the marker
that fires, and the module's default answer is `unknown` — so a classifier that simply
returned `authentication` for everything would pass each positive case and fail the
controls. The controls are what make the positive cases mean anything, because an
`authentication` report makes a credential SUSPECT and sidelines a real account.

Idempotency is asserted as a property of the REPORT OBJECT rather than of the manager:
the manager keys duplicates on the four identity members, so two reports built from one
failure at one instant must be equal. If they were not, a retry would be counted twice
however correct the manager's own deduplication is.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_failure_report import (
    AUTHENTICATION_CLASSIFICATION,
    PROVIDER_OUTAGE_CLASSIFICATION,
    RATE_LIMIT_CLASSIFICATION,
    UNKNOWN_CLASSIFICATION,
    classify_run_failure,
    outcome_failure_detail,
    report_run_failure,
    run_failure_report,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager import (
    REPORT_CLASSIFICATIONS,
    CredentialReceipt,
    ManagerRefusal,
    ProvisionedCredential,
    RunFailureReport,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroFailureDetail

_RUN_ID = "dispatch-report-1"
_RECORD_ID = "5f1b7a0c-0000-4000-8000-00000000cafe"
_NOW = 1_789_000_000.0


def _receipt() -> CredentialReceipt:
    return CredentialReceipt(
        record_id=_RECORD_ID,
        account_id="anthropic-2",
        validated_at="2026-09-12T08:00:00Z",
        purpose="factory",
        lease_expires_at="2026-09-12T14:00:00Z",
    )


def _outcome(
    *,
    status: str = "failed",
    cause: str | None = None,
    category: str | None = None,
    signature: str | None = None,
    provider_usage_limit: bool = False,
) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-wqhes7",
        status=status,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="",
        fabro_failure_cause=cause,
        fabro_failure_category=category,
        fabro_failure_signature=signature,
        provider_usage_limit=provider_usage_limit,
    )


class _RecordingManager:
    """Records the reports a dispatch sends, and can refuse one."""

    def __init__(self, *, refusal: ManagerRefusal | None = None) -> None:
        self.refusal = refusal
        self.reports: list[RunFailureReport] = []

    def provision(self, *, consumer_run_id: str) -> ProvisionedCredential | ManagerRefusal:
        raise NotImplementedError(consumer_run_id)

    def report(self, *, report: RunFailureReport) -> ManagerRefusal | None:
        self.reports.append(report)
        return self.refusal


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_the_typed_capacity_flag_outranks_every_text_marker() -> None:
    """It is set by the same classification that names the vendor: an observation."""
    failure = FabroFailureDetail(
        cause="401 unauthorized", category=None, signature=None, provider_usage_limit=True
    )

    assert classify_run_failure(failure=failure) == RATE_LIMIT_CLASSIFICATION


@pytest.mark.parametrize(
    "cause",
    [
        "HTTP 401 Unauthorized from the provider",
        "authentication_error while opening the session",
        "invalid api key supplied",
        "invalid bearer token",
        "oauth token has expired",
    ],
)
def test_a_credential_refusal_by_the_provider_classifies_as_authentication(cause: str) -> None:
    assert (
        classify_run_failure(failure=FabroFailureDetail(cause=cause, category=None, signature=None))
        == AUTHENTICATION_CLASSIFICATION
    )


@pytest.mark.parametrize(
    "cause",
    [
        "HTTP 429 returned",
        "rate_limit_error",
        "rate limit reached",
        "usage limit",
        "quota exceeded",
    ],
)
def test_a_capacity_refusal_classifies_as_rate_limit(cause: str) -> None:
    assert (
        classify_run_failure(failure=FabroFailureDetail(cause=cause, category=None, signature=None))
        == RATE_LIMIT_CLASSIFICATION
    )


@pytest.mark.parametrize(
    "cause",
    [
        "500 internal server error",
        "502 bad gateway",
        "503 service unavailable",
        "HTTP 529 from the provider",
        "api_error",
        "overloaded_error",
    ],
)
def test_a_provider_that_is_unable_rather_than_unwilling_classifies_as_outage(
    cause: str,
) -> None:
    assert (
        classify_run_failure(failure=FabroFailureDetail(cause=cause, category=None, signature=None))
        == PROVIDER_OUTAGE_CLASSIFICATION
    )


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(None, id="no-failure-block"),
        pytest.param(
            FabroFailureDetail(cause=None, category=None, signature=None), id="empty-failure-block"
        ),
        pytest.param(
            FabroFailureDetail(
                cause="the implementer left the worktree unchanged",
                category="code_test_review_or_tool_failure",
                signature="LIVESPEC_DEAD_IMPLEMENTER",
            ),
            id="a-failure-that-says-nothing-about-the-credential",
        ),
    ],
)
def test_a_failure_that_is_not_evidence_about_the_credential_is_honestly_unknown(
    failure: FabroFailureDetail | None,
) -> None:
    """`unknown` releases the lease without changing lifecycle state — a real answer.

    Guessing `authentication` here would sideline a healthy account on no evidence,
    which is strictly worse than saying "a run failed and this credential was in use".
    """
    assert classify_run_failure(failure=failure) == UNKNOWN_CLASSIFICATION


def test_the_category_and_signature_are_read_as_well_as_the_cause() -> None:
    assert (
        classify_run_failure(
            failure=FabroFailureDetail(
                cause=None, category="transient_infra", signature="rate_limit_error"
            )
        )
        == RATE_LIMIT_CLASSIFICATION
    )


def test_every_classification_this_module_can_emit_is_one_the_protocol_allows() -> None:
    emitted = {
        AUTHENTICATION_CLASSIFICATION,
        RATE_LIMIT_CLASSIFICATION,
        PROVIDER_OUTAGE_CLASSIFICATION,
        UNKNOWN_CLASSIFICATION,
    }

    assert emitted == set(REPORT_CLASSIFICATIONS)


# ---------------------------------------------------------------------------
# The report object
# ---------------------------------------------------------------------------


def test_a_report_ties_the_run_to_the_credential_record_and_carries_nothing_else() -> None:
    report = run_failure_report(
        receipt=_receipt(),
        consumer_run_id=_RUN_ID,
        failure=FabroFailureDetail(cause="401 unauthorized", category=None, signature=None),
        occurred_at_epoch=_NOW,
    )

    assert report.consumer_run_id == _RUN_ID
    assert report.record_id == _RECORD_ID
    assert report.classification == AUTHENTICATION_CLASSIFICATION
    assert report.occurred_at.endswith("Z")
    assert set(report.__dataclass_fields__) == {
        "consumer_run_id",
        "record_id",
        "occurred_at",
        "classification",
    }


def test_two_reports_built_from_one_failure_are_the_same_report() -> None:
    """Idempotency is a property of the object, not merely of the manager's dedup."""
    failure = FabroFailureDetail(cause="rate_limit_error", category=None, signature=None)
    kwargs = {
        "receipt": _receipt(),
        "consumer_run_id": _RUN_ID,
        "failure": failure,
        "occurred_at_epoch": _NOW,
    }

    assert run_failure_report(**kwargs) == run_failure_report(**kwargs)  # pyright: ignore[reportArgumentType]


def test_the_outcome_projection_carries_the_typed_flag_alongside_the_text() -> None:
    detail = outcome_failure_detail(
        outcome=_outcome(cause="c", category="cat", signature="sig", provider_usage_limit=True)
    )

    assert detail == FabroFailureDetail(
        cause="c", category="cat", signature="sig", provider_usage_limit=True
    )


# ---------------------------------------------------------------------------
# Reporting a run
# ---------------------------------------------------------------------------


def test_a_failed_run_is_reported_against_the_credential_it_used() -> None:
    manager = _RecordingManager()

    outcome = report_run_failure(
        manager=manager,
        receipt=_receipt(),
        consumer_run_id=_RUN_ID,
        outcome=_outcome(cause="HTTP 401 Unauthorized"),
        occurred_at_epoch=_NOW,
    )

    assert outcome is None
    assert manager.reports[0].record_id == _RECORD_ID
    assert manager.reports[0].classification == AUTHENTICATION_CLASSIFICATION


@pytest.mark.parametrize("status", ["green", "blocked"])
def test_a_run_that_did_not_fail_tells_the_credential_authority_nothing(status: str) -> None:
    """A `blocked` run asked a human a question; that is not evidence about an account."""
    manager = _RecordingManager()

    outcome = report_run_failure(
        manager=manager,
        receipt=_receipt(),
        consumer_run_id=_RUN_ID,
        outcome=_outcome(status=status, cause="HTTP 401 Unauthorized"),
        occurred_at_epoch=_NOW,
    )

    assert outcome is None
    assert manager.reports == []


def test_a_dispatch_refused_before_provisioning_reports_against_no_record() -> None:
    """There is no record identity, and inventing one would blame the next credential."""
    manager = _RecordingManager()

    outcome = report_run_failure(
        manager=manager,
        receipt=None,
        consumer_run_id=_RUN_ID,
        outcome=_outcome(cause="HTTP 401 Unauthorized"),
        occurred_at_epoch=_NOW,
    )

    assert outcome is None
    assert manager.reports == []


def test_a_refused_report_is_returned_rather_than_raised() -> None:
    """A dispatch that completed must not be turned into a failure by its own report."""
    refusal = ManagerRefusal(error_type="invalid-report", message="m", remedy="r")
    manager = _RecordingManager(refusal=refusal)

    assert (
        report_run_failure(
            manager=manager,
            receipt=_receipt(),
            consumer_run_id=_RUN_ID,
            outcome=_outcome(cause="HTTP 401 Unauthorized"),
            occurred_at_epoch=_NOW,
        )
        is refusal
    )
