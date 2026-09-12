"""The llm-provider-manager consumer boundary: its records and its injectable port.

livespec-overseer `SPECIFICATION/contracts.md` section "The LLM credential-provider
operation" (ratified at v051) makes `llm-provider-manager` the credential AUTHORITY for
this factory: it selects a validated Anthropic account, writes that account's real
credential into a target THIS consumer owns, and answers with a receipt carrying no
secret bytes. The Dispatcher's per-run overlay is the write seam on our side.

WHY A PORT RATHER THAN A DIRECT CALL. The manager is an out-of-process executable
holding real credentials for real accounts, so a hermetic test can neither run it nor
stand in for it at the subprocess layer without re-implementing its wire protocol. The
overlay materializer therefore depends on this Protocol, and `_dispatcher_credential_
manager_io` supplies the one implementation that actually shells out. That is also what
makes acceptance criterion 1 checkable: "obtains the credential through an injectable
manager request" is a statement about THIS seam, not about a subprocess.

THE VALUE AND THE RECEIPT ARE DELIBERATELY DIFFERENT TYPES. `CredentialReceipt` is the
secret-free identity the dispatch may journal, report against and hand to an operator;
`ProvisionedCredential` pairs it with the bytes, and those bytes cross exactly one seam —
materializer to overlay file. Nothing that accepts a `CredentialReceipt` can accidentally
be handed the value, because the value is not a field of it.

NO REQUEST PROXY EXISTS HERE, AND THAT IS NORMATIVE. The ratified proposal forbids the
manager from entering the inference request path: it provisions in place and the sandbox
authenticates to Anthropic directly as the selected account. So this port has no
"forward a request" verb and must never grow one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

__all__: list[str] = [
    "ANTHROPIC_PROVIDER",
    "FACTORY_PURPOSE",
    "INFERENCE_KIND",
    "ISOLATED_RUN_ADAPTER",
    "MANAGER_PROTOCOL_VERSION",
    "RECEIPT_MEMBERS",
    "REPORT_CLASSIFICATIONS",
    "CredentialManagerClient",
    "CredentialReceipt",
    "ManagerRefusal",
    "ProvisionedCredential",
    "RunFailureReport",
    "manager_refusal_detail",
]

# The version every consumer-protocol object carries. The manager rejects any other
# value, so it is pinned once here rather than spelled at each request builder.
MANAGER_PROTOCOL_VERSION: Final = 1

# The one registered provider row this factory consumes, named exactly as the manager's
# closed registry spells it. `claude-code-oauth` IS the "inference capability" the work
# item names: it is the credential kind a Claude Code sandbox authenticates with.
ANTHROPIC_PROVIDER: Final = "anthropic"
INFERENCE_KIND: Final = "claude-code-oauth"

# The purpose partition. `factory` is a policy partition over shared account usage, NOT a
# claim that factory and interactive credentials on one account have independent quota.
FACTORY_PURPOSE: Final = "factory"

# The only target adapter the manager registers, and the only one whose destination is
# per-run isolated rather than host-wide.
ISOLATED_RUN_ADAPTER: Final = "isolated-run"

# The receipt's closed member set, in the manager's own order. Closed in BOTH directions:
# a missing member and an unexpected extra one are equally a protocol violation, because
# an unexpected member could only come from a manager this build does not understand.
RECEIPT_MEMBERS: Final = (
    "record_id",
    "account_id",
    "validated_at",
    "purpose",
    "lease_expires_at",
)

# The four classifications a consumer may report. `authentication` is the only one that
# makes a credential suspect immediately; the rest feed the manager's own signal handling.
REPORT_CLASSIFICATIONS: Final = (
    "authentication",
    "rate-limit",
    "provider-outage",
    "unknown",
)


@dataclass(frozen=True, kw_only=True)
class CredentialReceipt:
    """The secret-free identity of one provisioned credential.

    Every field is safe to journal, log and quote to an operator. `record_id` is the
    identity a later failure report ties itself to, which is why a dispatch that
    provisions must retain this object for the whole run.
    """

    record_id: str
    account_id: str
    validated_at: str
    purpose: str
    lease_expires_at: str


@dataclass(frozen=True, kw_only=True)
class ProvisionedCredential:
    """One successful provision: the secret-free receipt plus the selected value.

    `value` is the only secret in this module and it crosses exactly one seam — the
    materializer writing the mode-600 run overlay. It is never journalled, never
    reported, and never part of a refusal.
    """

    receipt: CredentialReceipt
    value: str


@dataclass(frozen=True, kw_only=True)
class ManagerRefusal:
    """A typed, actionable refusal carrying no credential material.

    `error_type` is one of the manager's own typed results (`invalid-request`,
    `retryable-exhaustion`, `store-unavailable`, `provisioning-failed`, `internal-bug`)
    or a consumer-side transport classification. `remedy` is what an operator should DO,
    which is what makes the dispatch refusal actionable rather than merely typed.
    """

    error_type: str
    message: str
    remedy: str


@dataclass(frozen=True, kw_only=True)
class RunFailureReport:
    """One consumer-failure report: four identity scalars and nothing else.

    The manager keys idempotency on exactly these four values, so two reports built from
    the same run, credential, instant and classification ARE the same report and the
    second is answered `duplicate`. No diagnostic rides along: the contract permits an
    optional redacted one, and the safest redaction of a provider failure cause we did
    not author is to send none at all.
    """

    consumer_run_id: str
    record_id: str
    occurred_at: str
    classification: str


class CredentialManagerClient(Protocol):
    """The injected llm-provider-manager seam the Dispatcher depends on."""

    def provision(self, *, consumer_run_id: str) -> ProvisionedCredential | ManagerRefusal:
        """Obtain one Anthropic inference credential for this dispatch run.

        Returns the value plus its secret-free receipt, or a typed refusal. A refusal
        MUST leave the caller's overlay untouched.
        """
        ...

    def report(self, *, report: RunFailureReport) -> ManagerRefusal | None:
        """Report one run failure against a provisioned credential.

        Returns None when the manager accepted (or deduplicated) the report, and a
        typed refusal otherwise. Reporting is best-effort from the dispatch's point of
        view: a refused report is surfaced, never raised.
        """
        ...


def manager_refusal_detail(*, refusal: ManagerRefusal) -> str:
    """The operator-facing dispatch-refusal line for one manager refusal.

    Rendered here rather than at the call site so every surface that refuses a dispatch
    on a manager result says the same thing in the same shape, and so the rendering is
    covered once.
    """
    return (
        "C-mode dispatch refused: llm-provider-manager could not provision an "
        f"{ANTHROPIC_PROVIDER} {INFERENCE_KIND} credential for purpose "
        f"{FACTORY_PURPOSE} ({refusal.error_type}): {refusal.message} "
        f"Remedy: {refusal.remedy}"
    )
