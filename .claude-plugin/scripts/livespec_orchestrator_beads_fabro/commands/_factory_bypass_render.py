"""The factory-bypass audit's two renderings: the operator report and `--json`.

Both carry the same three blocks — flagged bypasses, recorded exceptions, and
the incident items whose retained chain could not be read.  The last block is
what keeps an unreadable receipt from passing as "no exceptions": a carrier
that might have been excepted stays in the flagged block, and the refusal is
printed beside it so the audit can never report a clean, plausible, wrong
answer when the ledger was simply unreachable.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands.factory_bypass_audit import (
        AuditPolicy,
        AuditReport,
        RecordedException,
    )

__all__: list[str] = ["render_json", "render_report"]


def _exception_status(*, recorded: RecordedException) -> str:
    """What one recorded exception still owes."""
    if recorded.kind != "incident-receipt":
        return "Factory-Override trailer, unverified"
    owed = "outstanding" if recorded.repayment_outstanding else "recorded as repaid"
    return f"incident {recorded.item_id}, deferred verification, normal repayment {owed}"


def _exception_lines(*, report: AuditReport) -> list[str]:
    """Render the recorded-exception block, which is empty when none were recorded."""
    if not report.exceptions:
        return []
    lines = ["", f"Recorded {len(report.exceptions)} factory exception(s):"]
    for recorded in report.exceptions:
        heading = f"- PR #{recorded.number} by @{recorded.author_login} — {recorded.title}"
        lines.append(f"{heading} ({_exception_status(recorded=recorded)})")
    return lines


def _refusal_lines(*, report: AuditReport) -> list[str]:
    """Render the unverifiable-incident block; its carriers remain flagged above."""
    if not report.incident_refusals:
        return []
    lines = ["", f"{len(report.incident_refusals)} incident item(s) could not be verified:"]
    lines.extend(f"- {refusal}" for refusal in report.incident_refusals)
    lines.append("  Their carriers remain flagged above; an unreadable receipt excepts nothing.")
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
            lines.extend(f"    - {path}" for path in finding.product_paths)
    else:
        lines.append("No factory bypasses found.")
    lines += _exception_lines(report=report)
    lines += _refusal_lines(report=report)
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
                "kind": recorded.kind,
                "item_id": recorded.item_id,
                "repayment_outstanding": recorded.repayment_outstanding,
            }
            for recorded in report.exceptions
        ],
        "incident_refusals": list(report.incident_refusals),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
