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

RECORDED EXCEPTIONS. A product-code PR carrying a `Factory-Override` trailer on
any of its commits is a DECLARED, auditable in-session change, not an
undeclared bypass. It is reported separately and counted separately: suppressing
it entirely would make the override indistinguishable from work that never
touched product code, which is the opposite of an audit trail.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

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
from livespec_orchestrator_beads_fabro.commands._factory_bypass_report_types import (
    AuditPolicy,
    AuditReport,
    BypassFinding,
    RecordedException,
)
from livespec_orchestrator_beads_fabro.commands._incident_provenance import (
    IncidentReceipt,
    matching_incident_receipt,
)
from livespec_orchestrator_beads_fabro.commands._incident_receipt_loader import (
    ReceiptLoader,
    load_retained_receipts,
    refusal_text,
    resolve_receipts,
)
from livespec_orchestrator_beads_fabro.incident_authority import AuthorityRefusal
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "FACTORY_OVERRIDE_TRAILER",
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
_EXIT_UNOBSERVABLE = 2
# The git trailer key an author writes to declare an in-session product change.
FACTORY_OVERRIDE_TRAILER = "Factory-Override:"


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


def audit_pull_requests(*, prs: list[PullRequest], policy: AuditPolicy) -> AuditReport:
    """Flag product-code PRs whose author is not exempt and whose change is undeclared."""
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
        receipt = matching_incident_receipt(
            receipts=policy.incident_receipts,
            repository=policy.repository or None,
            pr_number=pr.number,
            head_sha=pr.head_sha,
            landed_commits=pr.landed_commits,
        )
        if receipt is not None:
            exceptions.append(
                RecordedException(
                    number=pr.number,
                    title=pr.title,
                    author_login=pr.author_login,
                    item_id=receipt.item_id,
                    repayment_outstanding=receipt.repayment_required,
                )
            )
            continue
        if carries_factory_override(pr=pr):
            exceptions.append(
                RecordedException(number=pr.number, title=pr.title, author_login=pr.author_login)
            )
            continue
        findings.append(
            BypassFinding(
                number=pr.number,
                title=pr.title,
                author_login=pr.author_login,
                product_paths=product_paths,
            )
        )
    return AuditReport(scanned=len(prs), findings=tuple(findings), exceptions=tuple(exceptions))


def _exception_lines(*, report: AuditReport) -> list[str]:
    """Render the recorded-exception block, which is empty when none were declared."""
    if not report.exceptions:
        return []
    lines = ["", f"Recorded {len(report.exceptions)} factory exception(s):"]
    for recorded in report.exceptions:
        repayment = (
            "normal repayment outstanding" if recorded.repayment_outstanding else "unverified"
        )
        heading = f"- PR #{recorded.number} by @{recorded.author_login} — {recorded.title}"
        lines.append(f"{heading} ({repayment})")
    return lines


def render_report(*, report: AuditReport, policy: AuditPolicy) -> str:
    """Human-readable audit report plus a summary count."""
    paths = policy.product_paths
    lines = [
        "# Factory-Bypass Audit",
        "",
        f"Factory App: {policy.factory_app_login}",
        f"Product prefixes ({paths.origin}): {', '.join(paths.prefixes)}",
        f"Scanned {report.scanned} recently-merged PR(s).",
    ]
    if report.findings:
        lines.append(f"Flagged {len(report.findings)} product-code PR(s) not from the factory App:")
        lines.append("")
        for finding in report.findings:
            lines.append(f"- PR #{finding.number} by @{finding.author_login} — {finding.title}")
            for path in finding.product_paths:
                lines.append(f"    - {path}")
    else:
        lines.append("No factory bypasses found.")
    lines += _exception_lines(report=report)
    return "\n".join(lines) + "\n"


def render_json(*, report: AuditReport, policy: AuditPolicy) -> str:
    """Machine-readable audit report (`--json`)."""
    payload = {
        "factory_app_login": policy.factory_app_login,
        "product_prefixes": list(policy.product_paths.prefixes),
        "product_prefixes_origin": policy.product_paths.origin,
        "scanned": report.scanned,
        "count": len(report.findings),
        "findings": [
            {
                "number": finding.number,
                "title": finding.title,
                "author": finding.author_login,
                "product_paths": list(finding.product_paths),
            }
            for finding in report.findings
        ],
        "exception_count": len(report.exceptions),
        "exceptions": [
            {
                "number": recorded.number,
                "title": recorded.title,
                "author": recorded.author_login,
                "item_id": recorded.item_id,
                "repayment_outstanding": recorded.repayment_outstanding,
            }
            for recorded in report.exceptions
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


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
    return parser


def _may_need_receipts(*, prs: list[PullRequest], policy: AuditPolicy) -> bool:
    """Whether any merged product-code PR is neither exempt nor already a declared override."""
    return any(
        any(is_product_py(path=path, policy=policy.product_paths) for path in pr.files)
        and pr.author_login != policy.factory_app_login
        and pr.author_login not in policy.allow_authors
        and not any(label in policy.allow_labels for label in pr.labels)
        for pr in prs
    )


def main(
    *,
    argv: list[str] | None = None,
    seam: GhSeam = DEFAULT_GH_SEAM,
    incident_receipts: tuple[IncidentReceipt, ...] | None = None,
    receipt_loader: ReceiptLoader = load_retained_receipts,
) -> int:
    """Supervisor for the factory-bypass audit. Report-only, but never blind to receipts.

    `incident_receipts` None means "read the retained chains", which happens only when
    a flagged-looking PR exists. An unreadable ledger exits 2 naming why: reporting a
    PR as a bypass, or as clean, on receipts nobody could read is a wrong answer.
    """
    args = _build_parser().parse_args(argv)
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
    )
    prs = fetch_merged_prs(
        repo=args.repo,
        limit=args.limit,
        merged_since=args.merged_since,
        seam=seam,
    )
    receipts = resolve_receipts(
        declared=incident_receipts,
        needed=_may_need_receipts(prs=prs, policy=policy),
        loader=receipt_loader,
        repo=Path.cwd(),
        repository=args.repo,
    )
    if isinstance(receipts, AuthorityRefusal):
        write_stderr(text=f"factory-bypass audit {refusal_text(refusal=receipts)}")
        return _EXIT_UNOBSERVABLE
    report = audit_pull_requests(prs=prs, policy=replace(policy, incident_receipts=receipts))
    text = (
        render_json(report=report, policy=policy)
        if args.as_json
        else render_report(report=report, policy=policy)
    )
    _ = write_stdout(text=text)
    return 0
