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

Factory App identity: `app/livespec-pr-bot` — the login `gh pr list --json
author` reports for this repo's GitHub App. That single App authors BOTH the
factory Dispatcher's work-item PRs AND the release-please / bump-pin PRs
(discovered from merged-PR history + `.github/workflows/`, where the
Dispatcher and release-please both mint the `livespec-pr-bot` App token via
`APP_ID`/`APP_PRIVATE_KEY`). Exempting that login therefore covers both
"went through the factory" and "the release-please bot". Configurable via
`--factory-app-login`; extend with `--allow-author` / `--allow-label` for
maintainer-overridden work.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from typing import Protocol

from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "AuditPolicy",
    "AuditReport",
    "BypassFinding",
    "GhSeam",
    "PullRequest",
    "audit_pull_requests",
    "fetch_merged_prs",
    "is_product_py",
    "main",
    "parse_pr_list",
    "render_json",
    "render_report",
]

# The discovered factory App login as `gh pr list --json author` renders it.
DEFAULT_FACTORY_APP_LOGIN = "app/livespec-pr-bot"
DEFAULT_LIMIT = 100
_GH_TIMEOUT_SECONDS = 60

# This repo's slice of the Red-Green-Replay product-impl classifier
# (`livespec_dev_tooling.checks.red_green_replay._IMPL_PREFIXES`): a changed
# path is product `.py` iff it ends in `.py` and lives under one of these
# first-party source roots. Test files, vendored code, and pycache are never
# product. Kept as a local copy — the plugin has NO runtime dependency on the
# dev-tooling package.
_PRODUCT_PY_PREFIXES = (
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/",
    ".claude-plugin/scripts/bin/",
    "dev-tooling/",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PullRequest:
    """A merged PR reduced to the fields the audit reasons over."""

    number: int
    title: str
    author_login: str
    files: tuple[str, ...]
    labels: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditPolicy:
    """The exemption policy: who / what is never flagged as a bypass."""

    factory_app_login: str
    allow_authors: frozenset[str]
    allow_labels: frozenset[str]


@dataclass(frozen=True, slots=True, kw_only=True)
class BypassFinding:
    """A merged PR that changed product code without going through the factory."""

    number: int
    title: str
    author_login: str
    product_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditReport:
    """The audit outcome: how many PRs were scanned and which were flagged."""

    scanned: int
    findings: tuple[BypassFinding, ...]


class GhRunner(Protocol):
    """Seam: run a `gh` argv and return its stdout."""

    def __call__(self, *, args: list[str]) -> str: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class GhSeam:
    """The injectable `gh` transport (defaulted to the real subprocess)."""

    run: GhRunner


def _default_gh_run(*, args: list[str]) -> str:  # pragma: no cover
    """Production `gh` seam — integration-covered, never hit hermetically."""
    completed = subprocess.run(  # noqa: S603
        ["gh", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        timeout=_GH_TIMEOUT_SECONDS,
    )
    return completed.stdout


DEFAULT_GH_SEAM = GhSeam(run=_default_gh_run)


def is_product_py(*, path: str) -> bool:
    """Classify a changed repo path as product `.py` (the bypass trigger)."""
    if not path.endswith(".py"):
        return False
    if path.startswith("tests/"):
        return False
    if "/_vendor/" in path or "/__pycache__/" in path:
        return False
    return path.startswith(_PRODUCT_PY_PREFIXES)


def parse_pr_list(*, stdout: str) -> list[PullRequest]:
    """Parse `gh pr list --json number,title,author,labels,files` stdout."""
    raw = json.loads(stdout)
    prs: list[PullRequest] = []
    for entry in raw:
        author = entry.get("author")
        login = "" if author is None else str(author.get("login", ""))
        prs.append(
            PullRequest(
                number=int(entry["number"]),
                title=str(entry.get("title", "")),
                author_login=login,
                files=tuple(str(item["path"]) for item in entry.get("files", ())),
                labels=tuple(str(label["name"]) for label in entry.get("labels", ())),
            )
        )
    return prs


def fetch_merged_prs(
    *,
    repo: str | None,
    limit: int,
    merged_since: str | None,
    seam: GhSeam = DEFAULT_GH_SEAM,
) -> list[PullRequest]:
    """Fetch the recently-merged PR window through the `gh` seam."""
    args = [
        "pr",
        "list",
        "--state",
        "merged",
        "--limit",
        str(limit),
        "--json",
        "number,title,author,labels,files",
    ]
    if repo is not None:
        args += ["--repo", repo]
    if merged_since is not None:
        args += ["--search", f"merged:>={merged_since}"]
    return parse_pr_list(stdout=seam.run(args=args))


def audit_pull_requests(*, prs: list[PullRequest], policy: AuditPolicy) -> AuditReport:
    """Flag product-code PRs whose author is not exempt under the policy."""
    findings: list[BypassFinding] = []
    for pr in prs:
        product_paths = tuple(path for path in pr.files if is_product_py(path=path))
        if not product_paths:
            continue
        if pr.author_login == policy.factory_app_login or pr.author_login in policy.allow_authors:
            continue
        if any(label in policy.allow_labels for label in pr.labels):
            continue
        findings.append(
            BypassFinding(
                number=pr.number,
                title=pr.title,
                author_login=pr.author_login,
                product_paths=product_paths,
            )
        )
    return AuditReport(scanned=len(prs), findings=tuple(findings))


def render_report(*, report: AuditReport, policy: AuditPolicy) -> str:
    """Human-readable audit report plus a summary count."""
    lines = [
        "# Factory-Bypass Audit",
        "",
        f"Factory App: {policy.factory_app_login}",
        f"Scanned {report.scanned} recently-merged PR(s).",
    ]
    if not report.findings:
        lines.append("No factory bypasses found.")
        return "\n".join(lines) + "\n"
    count = len(report.findings)
    lines.append(f"Flagged {count} product-code PR(s) not from the factory App:")
    lines.append("")
    for finding in report.findings:
        lines.append(f"- PR #{finding.number} by @{finding.author_login} — {finding.title}")
        for path in finding.product_paths:
            lines.append(f"    - {path}")
    return "\n".join(lines) + "\n"


def render_json(*, report: AuditReport, policy: AuditPolicy) -> str:
    """Machine-readable audit report (`--json`)."""
    payload = {
        "factory_app_login": policy.factory_app_login,
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
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main(*, argv: list[str] | None = None, seam: GhSeam = DEFAULT_GH_SEAM) -> int:
    """Supervisor for the factory-bypass audit. Always exits 0 (report-only)."""
    parser = argparse.ArgumentParser(prog="factory-bypass-audit")
    _ = parser.add_argument("--repo", dest="repo", default=None)
    _ = parser.add_argument("--limit", dest="limit", type=int, default=DEFAULT_LIMIT)
    _ = parser.add_argument("--merged-since", dest="merged_since", default=None)
    _ = parser.add_argument(
        "--factory-app-login", dest="factory_app_login", default=DEFAULT_FACTORY_APP_LOGIN
    )
    _ = parser.add_argument("--allow-author", dest="allow_authors", action="append", default=None)
    _ = parser.add_argument("--allow-label", dest="allow_labels", action="append", default=None)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(argv)
    policy = AuditPolicy(
        factory_app_login=args.factory_app_login,
        allow_authors=frozenset(args.allow_authors or ()),
        allow_labels=frozenset(args.allow_labels or ()),
    )
    prs = fetch_merged_prs(
        repo=args.repo,
        limit=args.limit,
        merged_since=args.merged_since,
        seam=seam,
    )
    report = audit_pull_requests(prs=prs, policy=policy)
    text = (
        render_json(report=report, policy=policy)
        if args.as_json
        else render_report(report=report, policy=policy)
    )
    _ = write_stdout(text=text)
    return 0
