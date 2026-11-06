"""factory-bypass audit — REPORT-ONLY on-demand attention surface.

Answers: "which recently-merged PRs changed product `.py` without going
through the factory GitHub App?" A product-code PR whose author is NOT the
factory App is an in-session factory bypass — the empirical signal for the
2026-07-15 force-factory decision (plan/force-factory/findings.md; epic
bd-ib-y2xro4, work-item bd-ib-c4a2bi). It is an attention surface, NOT a
gate: it shells out to `gh` (network) so it MUST NOT run inside `just check`
or any hook, and it exits 0 regardless of findings.

Placement: a standalone bin wrapper + the `just factory-bypass-audit` recipe
(NOT part of the `check` aggregate), per the spec's decision rule — the
network dependency rules out the network-free `needs-attention` surface and
would require SPECIFICATION/ changes there.

Factory App identity: `app/thewoolleyman-factory-bot` — the login `gh pr list --json
author` reports for this repo's GitHub App. That single App authors BOTH the
factory Dispatcher's work-item PRs AND the release-please / bump-pin PRs
(discovered from merged-PR history + `.github/workflows/`, where the
Dispatcher and release-please both mint the `thewoolleyman-factory-bot` App token via
`APP_ID`/`APP_PRIVATE_KEY`). Exempting that login therefore covers both
"went through the factory" and "the release-please bot". Configurable via
`--factory-app-login`; extend with `--allow-author` / `--allow-label` for
maintainer-overridden work.

FLEET SCOPE. `--repo` selects which repository is audited, and it selects it
for BOTH reads: the merged-PR window AND the product-path declaration the
classifier derives its prefixes from (`_factory_bypass_product_paths`). The
prefixes were a single hardcoded orchestrator-only tuple until bd-ib-jtr22v,
which made the counter structurally blind outside this one repository — it
could not classify a product `.py` in `livespec` or `livespec-dev-tooling`,
the repositories where the drift it exists to measure actually happens, and it
reported that blindness as "no bypasses found". `--product-prefix` overrides
the derivation for a repository that declares no layout of its own.

RECORDED EXCEPTIONS, TWO KINDS. A product-code PR carrying a `Factory-Override`
trailer on any of its commits is a DECLARED, auditable in-session change, not an
undeclared bypass; it is reported as an unverified exception. A product-code PR
that matches a retained exact incident receipt — read through the canonical
incident-authority reader for an `--incident-item` the operator names, and
bound to this PR's number, head and complete landed commit set — is a recorded
INCIDENT exception, reported with whether its normal factory repayment is still
outstanding (the chain has not reached `closed`). Both are counted separately
from findings: suppressing them would make an exception indistinguishable from
work that never touched product code, which is the opposite of an audit trail.
A named incident whose chain cannot be read is reported as a refusal and excepts
nothing, so its carriers stay flagged.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
from livespec_orchestrator_beads_fabro.commands._factory_bypass_gh import (
    DEFAULT_GH_SEAM,
    GhSeam,
    PullRequest,
    fetch_merged_prs,
    fetch_repo_pyproject,
)
from livespec_orchestrator_beads_fabro.commands._factory_bypass_product_paths import (
    ProductPathPolicy,
    is_product_py,
    product_policy,
)
from livespec_orchestrator_beads_fabro.commands._factory_bypass_render import (
    render_json,
    render_report,
)
from livespec_orchestrator_beads_fabro.commands._incident_provenance import (
    IncidentReceipt,
    matching_incident_receipt,
)
from livespec_orchestrator_beads_fabro.commands._incident_receipt_source import (
    IncidentReceiptRefusal,
    add_incident_item_argument,
    describe_refusal,
    incident_authority_client,
    resolve_incident_receipts,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "FACTORY_OVERRIDE_TRAILER",
    "AuditPolicy",
    "AuditReport",
    "BypassFinding",
    "RecordedException",
    "audit_pull_requests",
    "carries_factory_override",
    "main",
    "render_json",
    "render_report",
    "resolve_product_policy",
]

# The discovered factory App login as `gh pr list --json author` renders it.
DEFAULT_FACTORY_APP_LOGIN = "app/thewoolleyman-factory-bot"
DEFAULT_LIMIT = 100
# The git trailer key an author writes to declare an in-session product change.
FACTORY_OVERRIDE_TRAILER = "Factory-Override:"


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditPolicy:
    """The audit's axes: what counts as product code, who is never flagged, which receipts hold."""

    factory_app_login: str
    allow_authors: frozenset[str]
    allow_labels: frozenset[str]
    product_paths: ProductPathPolicy
    repository: str = ""
    incident_receipts: tuple[IncidentReceipt, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class BypassFinding:
    """A merged PR that changed product code without going through the factory."""

    number: int
    title: str
    author_login: str
    product_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordedException:
    """A product-code PR excepted by a declared trailer or an exact incident receipt."""

    number: int
    title: str
    author_login: str
    kind: str = "factory-override"
    item_id: str = ""
    repayment_outstanding: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditReport:
    """The audit outcome: PRs scanned, flagged, excepted, and incidents it could not verify."""

    scanned: int
    findings: tuple[BypassFinding, ...]
    exceptions: tuple[RecordedException, ...]
    incident_refusals: tuple[str, ...] = ()


def carries_factory_override(*, pr: PullRequest) -> bool:
    """True iff any of the PR's commits carries a `Factory-Override` trailer line."""
    return any(
        line.strip().startswith(FACTORY_OVERRIDE_TRAILER)
        for message in pr.commit_messages
        for line in message.splitlines()
    )


def resolve_product_policy(
    *,
    repo: str | None,
    overrides: tuple[str, ...] = (),
    seam: GhSeam = DEFAULT_GH_SEAM,
) -> ProductPathPolicy:
    """Derive the audited repository's product-path prefixes through the `gh` seam."""
    if overrides:
        return product_policy(pyproject_text=None, overrides=overrides)
    return product_policy(pyproject_text=fetch_repo_pyproject(repo=repo, seam=seam))


def _recorded_exception(*, pr: PullRequest, policy: AuditPolicy) -> RecordedException | None:
    """The exception this PR is recorded under, exact receipt first, else a declared trailer."""
    receipt = matching_incident_receipt(
        receipts=policy.incident_receipts,
        repository=policy.repository,
        pr_number=pr.number,
        head_sha=pr.head_sha,
        landed_commits=pr.landed_commits,
    )
    if receipt is not None:
        return RecordedException(
            number=pr.number,
            title=pr.title,
            author_login=pr.author_login,
            kind="incident-receipt",
            item_id=receipt.item_id,
            repayment_outstanding=receipt.repayment_outstanding,
        )
    if carries_factory_override(pr=pr):
        return RecordedException(number=pr.number, title=pr.title, author_login=pr.author_login)
    return None


def audit_pull_requests(
    *,
    prs: list[PullRequest],
    policy: AuditPolicy,
    incident_refusals: tuple[str, ...] = (),
) -> AuditReport:
    """Flag product-code PRs whose author is not exempt and whose change is not excepted."""
    findings: list[BypassFinding] = []
    exceptions: list[RecordedException] = []
    for pr in prs:
        product_paths = tuple(
            path for path in pr.files if is_product_py(path=path, policy=policy.product_paths)
        )
        if not product_paths:
            continue
        if pr.author_login == policy.factory_app_login or pr.author_login in policy.allow_authors:
            continue
        if any(label in policy.allow_labels for label in pr.labels):
            continue
        recorded = _recorded_exception(pr=pr, policy=policy)
        if recorded is not None:
            exceptions.append(recorded)
            continue
        findings.append(
            BypassFinding(
                number=pr.number,
                title=pr.title,
                author_login=pr.author_login,
                product_paths=product_paths,
            )
        )
    return AuditReport(
        scanned=len(prs),
        findings=tuple(findings),
        exceptions=tuple(exceptions),
        incident_refusals=incident_refusals,
    )


def _build_parser() -> argparse.ArgumentParser:
    """The CLI surface; `--repo` selects the audited repository for BOTH gh reads."""
    parser = argparse.ArgumentParser(prog="factory-bypass-audit")
    _ = parser.add_argument("--repo", dest="repo", default=None)
    _ = parser.add_argument("--limit", dest="limit", type=int, default=DEFAULT_LIMIT)
    _ = parser.add_argument("--merged-since", dest="merged_since", default=None)
    _ = parser.add_argument(
        "--factory-app-login", dest="factory_app_login", default=DEFAULT_FACTORY_APP_LOGIN
    )
    _ = parser.add_argument("--allow-author", dest="allow_authors", action="append", default=None)
    _ = parser.add_argument("--allow-label", dest="allow_labels", action="append", default=None)
    _ = parser.add_argument(
        "--product-prefix", dest="product_prefixes", action="append", default=None
    )
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    # The project whose store configuration reaches the incident ledger; the
    # audited `--repo` is a forge slug, not a checkout.
    _ = parser.add_argument("--project-root", dest="project_root", default=".")
    add_incident_item_argument(parser=parser)
    return parser


def _incident_receipts(
    *,
    args: argparse.Namespace,
    authority_client: BeadsClient | None,
) -> tuple[tuple[IncidentReceipt, ...], tuple[str, ...]]:
    """The named items' receipts and the refusals of the items that could not be read."""
    item_ids: tuple[str, ...] = tuple(args.incident_items or ())
    if not item_ids:
        return (), ()
    client = incident_authority_client(repo=Path(args.project_root), client=authority_client)
    receipts: list[IncidentReceipt] = []
    refusals: list[str] = []
    for item_id in item_ids:
        resolved = resolve_incident_receipts(
            client=client, repository=args.repo, item_ids=(item_id,)
        )
        if isinstance(resolved, IncidentReceiptRefusal):
            refusals.append(describe_refusal(refusal=resolved))
        else:
            receipts.extend(resolved)
    return tuple(receipts), tuple(refusals)


def main(
    *,
    argv: list[str] | None = None,
    seam: GhSeam = DEFAULT_GH_SEAM,
    authority_client: BeadsClient | None = None,
) -> int:
    """Supervisor for the factory-bypass audit. Always exits 0 (report-only)."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.incident_items and args.repo is None:
        parser.error("--incident-item binds receipts to a repository: pass --repo owner/name")
    receipts, refusals = _incident_receipts(args=args, authority_client=authority_client)
    policy = AuditPolicy(
        factory_app_login=args.factory_app_login,
        allow_authors=frozenset(args.allow_authors or ()),
        allow_labels=frozenset(args.allow_labels or ()),
        product_paths=resolve_product_policy(
            repo=args.repo,
            overrides=tuple(args.product_prefixes or ()),
            seam=seam,
        ),
        repository=args.repo or "",
        incident_receipts=receipts,
    )
    prs = fetch_merged_prs(
        repo=args.repo,
        limit=args.limit,
        merged_since=args.merged_since,
        seam=seam,
    )
    report = audit_pull_requests(prs=prs, policy=policy, incident_refusals=refusals)
    text = (
        render_json(report=report, policy=policy)
        if args.as_json
        else render_report(report=report, policy=policy)
    )
    _ = write_stdout(text=text)
    return 0
