"""Classifying a failed run against the credential the llm-provider-manager provisioned.

livespec-overseer `SPECIFICATION/contracts.md` lets a consumer report exactly four
classifications — `authentication`, `rate-limit`, `provider-outage` and `unknown` — naming
the consumer run, the credential-record identity and the occurrence instant. An
`authentication` report makes the credential SUSPECT immediately, so it cannot be selected
again until it revalidates; that is the whole reason this path exists, and it is why the
classifier must not reach for `authentication` on anything weaker than evidence.

`unknown` IS A REAL ANSWER, NOT A FALLBACK WE FAILED TO AVOID. The ratified revision has
`unknown` release its matching lease without changing the credential's lifecycle state —
so reporting `unknown` returns capacity while asserting nothing about the account. A
classifier that guessed `authentication` from an ambiguous cause would instead sideline a
healthy account on no evidence, which is strictly worse than saying "a run failed and this
credential was in use".

THE INPUT IS THE STRUCTURED FAILURE THE DISPATCH ALREADY HOLDS. `FabroFailureDetail` is
what `fabro inspect --json` yields for a failed run: a cause, a category, a signature and
the typed `provider_usage_limit` flag the exhaustion gate already trusts. Nothing here
reads a run log, an agent transcript or a tool output — those can carry credential
material, and a report that carried any would violate the secret-free obligation this
module exists to satisfy.

NO DIAGNOSTIC IS EVER SENT, AND THAT IS DELIBERATE. The protocol permits an optional
REDACTED diagnostic. We did not author the provider's cause text and cannot prove what it
contains, so the only redaction we can stand behind is omission. The four identity scalars
are sufficient for the manager, and they are also exactly what makes a report idempotent:
two reports built from one failure are byte-identical, so a retry is answered `duplicate`
rather than double-counted.

THE TYPED FLAG OUTRANKS THE TEXT. `provider_usage_limit` is set by the same single
classification that names the vendor, so it is an observation rather than a guess; the
text conjunctions below are only consulted when that flag says nothing.
"""

from __future__ import annotations

from typing import Final, Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager import (
    CredentialManagerClient,
    CredentialReceipt,
    ManagerRefusal,
    RunFailureReport,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager_target import (
    rfc3339_second,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroFailureDetail

__all__: list[str] = [
    "AUTHENTICATION_CLASSIFICATION",
    "FAILED_STATUS",
    "PROVIDER_OUTAGE_CLASSIFICATION",
    "RATE_LIMIT_CLASSIFICATION",
    "UNKNOWN_CLASSIFICATION",
    "CredentialRunOutcome",
    "classify_run_failure",
    "outcome_failure_detail",
    "report_run_failure",
    "run_failure_report",
]

# The one `DispatchOutcome.status` that means the run failed. `blocked` is a run that
# reached `needs_human` and `green` is a success; neither is evidence about a credential,
# so neither is reported. Reporting a blocked run would make a healthy account suspect
# because a human was asked a question.
FAILED_STATUS: Final = "failed"

AUTHENTICATION_CLASSIFICATION: Final = "authentication"
RATE_LIMIT_CLASSIFICATION: Final = "rate-limit"
PROVIDER_OUTAGE_CLASSIFICATION: Final = "provider-outage"
UNKNOWN_CLASSIFICATION: Final = "unknown"

# Markers that name the provider REFUSING THE CREDENTIAL ITSELF. Each is a phrase a
# provider or adapter emits about the credential, never about the work: "unauthorized"
# alone is absent because a tool can print it about a repository.
_AUTHENTICATION_MARKERS: Final = (
    "401 unauthorized",
    "authentication_error",
    "invalid api key",
    "invalid bearer token",
    "oauth token has expired",
)

# Markers that name a provider-side capacity refusal, for the case where the typed
# `provider_usage_limit` flag was not set by whatever classified the run.
_RATE_LIMIT_MARKERS: Final = (
    "429",
    "rate_limit_error",
    "rate limit",
    "usage limit",
    "quota exceeded",
)

# Markers that name the provider being UNABLE rather than UNWILLING. `529` is Anthropic's
# overloaded status and `overloaded_error` its typed spelling.
_PROVIDER_OUTAGE_MARKERS: Final = (
    "500 internal server error",
    "502 bad gateway",
    "503 service unavailable",
    "529",
    "api_error",
    "overloaded_error",
    "overloaded",
)


class CredentialRunOutcome(Protocol):
    """The `DispatchOutcome` fields one credential failure report is derived from."""

    @property
    def status(self) -> str:
        """Terminal status; only `failed` is evidence about the credential."""
        ...

    @property
    def fabro_failure_cause(self) -> str | None:
        """Fabro's structured cause line, if it reported one."""
        ...

    @property
    def fabro_failure_category(self) -> str | None:
        """Fabro's failure category, if it reported one."""
        ...

    @property
    def fabro_failure_signature(self) -> str | None:
        """Fabro's failure signature, if it reported one."""
        ...

    @property
    def provider_usage_limit(self) -> bool:
        """Whether the run died on a provider usage or spend ceiling."""
        ...


def outcome_failure_detail(*, outcome: CredentialRunOutcome) -> FabroFailureDetail:
    """The outcome's three failure fields plus its typed flag, as one detail record."""
    return FabroFailureDetail(
        cause=outcome.fabro_failure_cause,
        category=outcome.fabro_failure_category,
        signature=outcome.fabro_failure_signature,
        provider_usage_limit=outcome.provider_usage_limit,
    )


def report_run_failure(
    *,
    manager: CredentialManagerClient,
    receipt: CredentialReceipt | None,
    consumer_run_id: str,
    outcome: CredentialRunOutcome,
    occurred_at_epoch: float,
) -> ManagerRefusal | None:
    """Report a failed run against the credential it used; None when nothing is owed.

    Nothing is owed when the run did not fail, or when no credential was provisioned —
    a dispatch refused BEFORE provisioning has no record identity to report against, and
    inventing one would attach a failure to whichever credential was selected next.
    """
    if receipt is None or outcome.status != FAILED_STATUS:
        return None
    return manager.report(
        report=run_failure_report(
            receipt=receipt,
            consumer_run_id=consumer_run_id,
            failure=outcome_failure_detail(outcome=outcome),
            occurred_at_epoch=occurred_at_epoch,
        )
    )


def classify_run_failure(*, failure: FabroFailureDetail | None) -> str:
    """The one manager classification this failed run supports.

    Ordered by how decisive the evidence is: the typed capacity flag first, then the
    credential-refusal markers, then capacity markers, then provider-unavailability
    markers. Anything else is honestly `unknown`.
    """
    if failure is None:
        return UNKNOWN_CLASSIFICATION
    if failure.provider_usage_limit:
        return RATE_LIMIT_CLASSIFICATION
    text = _readable_text(failure=failure)
    for markers, classification in (
        (_AUTHENTICATION_MARKERS, AUTHENTICATION_CLASSIFICATION),
        (_RATE_LIMIT_MARKERS, RATE_LIMIT_CLASSIFICATION),
        (_PROVIDER_OUTAGE_MARKERS, PROVIDER_OUTAGE_CLASSIFICATION),
    ):
        if any(marker in text for marker in markers):
            return classification
    return UNKNOWN_CLASSIFICATION


def run_failure_report(
    *,
    receipt: CredentialReceipt,
    consumer_run_id: str,
    failure: FabroFailureDetail | None,
    occurred_at_epoch: float,
) -> RunFailureReport:
    """One secret-free report tying this run's failure to the credential it used."""
    return RunFailureReport(
        consumer_run_id=consumer_run_id,
        record_id=receipt.record_id,
        occurred_at=rfc3339_second(epoch=occurred_at_epoch),
        classification=classify_run_failure(failure=failure),
    )


def _readable_text(*, failure: FabroFailureDetail) -> str:
    """The three structured fields, case-folded into one haystack."""
    return " ".join(
        part for part in (failure.cause, failure.category, failure.signature) if part is not None
    ).casefold()
