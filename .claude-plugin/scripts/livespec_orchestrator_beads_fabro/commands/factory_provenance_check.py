"""factory-provenance merge gate — the server-side factory-App authorship wall.

R6a of plan `mechanically-enforce-factory-usage`. This is the MERGE-TIME half
of the pair whose commit-time half is the `Factory-Override` trailer the
factory-bypass audit already counts: a pull request that changes PRODUCT
PYTHON must have been authored by the factory GitHub App, must match an exact
retained incident receipt, or must carry the `factory-override` label
declaring the exception. Everything else merges untouched — spec, plan, docs,
workflow and config changes are out of scope by construction, exactly as the
Red-Green-Replay scope is.

WHY THIS IS THE HARD WALL. The author identity comes from the forge's own
event payload, so no local marker can forge it; the commit-time trailer stays
spoofable-but-audited. Measured over the last 100 merged pull requests on this
repository (research note 006 of the plan): 69 App-authored, 31
maintainer-authored, and just THREE of those 31 changed product Python. Those
three are the whole population this wall exists for.

WHY THE LOGIN IS CHECKED TWICE. The forge spells the same App two ways: the
webhook payload says `thewoolleyman-factory-bot[bot]`, while `gh` renders it
`app/thewoolleyman-factory-bot`. `auto-enable-merge.yml` already composes a
login gate on the second spelling; accepting only one spelling would turn this
gate into a wall against the factory itself, which is the failure mode that
costs the most and announces itself the least.

WHY A ZERO-PRODUCT-PYTHON DIFF REPORTS VACUITY AND STILL PERMITS THE MERGE.
This is a FILE-SCOPED check: it SELECTS the diff files it judges. Under the
ratified scoped-check vacuity clause (`SPECIFICATION/contracts.md`), a scope
that matched zero files has OBSERVED NOTHING and MUST NOT report a pass — so
the outcome is `vacuous-match`, not `pass`. That is a statement about
EVIDENCE, never about admission: `permits_merge` is True and the exit code is
0, because a pull request carrying no product Python is not blocked on
factory-provenance grounds. Collapsing the two would hide a broken probe
inside a green result, which is how a scoped guard once passed over an empty
diff for four review rounds.

THE INCIDENT EXCEPTION IS EXACT AND READ, NEVER DECLARED. Under the
expedited incident lifecycle contract in `SPECIFICATION/contracts.md`, a
trusted incident repair receipt admits only the exact authorized carrier. The gate
locates candidates ONLY through `--incident-item <id>` and authorizes them
ONLY through the canonical incident-authority reader over the retained ledger
chain, binding repository, pull request number, head and the complete landed
commit set (`git rev-list base..head`). A named item whose chain cannot be
read, an event that names no repository, or a commit range that cannot be
listed is UNOBSERVABLE (exit 2), never a pass and never "no receipt". The
ordinary CI invocation names no item and stays hermetic in the forge sense:
the event payload and the diff, never the ledger.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_scoped_check_vacuity import (
    scoped_check_outcome,
)
from livespec_orchestrator_beads_fabro.commands._factory_bypass_product_paths import (
    ProductPathPolicy,
    is_product_py,
    product_policy,
)
from livespec_orchestrator_beads_fabro.commands._factory_provenance_event import (
    PullRequestEvent,
    diff_range,
    read_changed_paths,
    read_event,
    read_landed_commits,
)
from livespec_orchestrator_beads_fabro.commands._factory_provenance_verdict import (
    FACTORY_APP_LOGINS,
    FACTORY_OVERRIDE_LABEL,
    ProvenanceVerdict,
    exit_code,
    permits_merge,
    render_verdict,
)
from livespec_orchestrator_beads_fabro.commands._incident_provenance import (
    IncidentReceipt,
    matching_incident_receipt,
    matching_repayment_carrier,
)
from livespec_orchestrator_beads_fabro.commands._incident_receipt_source import (
    IncidentReceiptRefusal,
    add_incident_item_argument,
    describe_refusal,
    incident_authority_client,
    resolve_incident_receipts,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "DEFAULT_RUNNER",
    "FACTORY_APP_LOGINS",
    "FACTORY_OVERRIDE_LABEL",
    "ProvenanceVerdict",
    "decide",
    "exit_code",
    "main",
    "permits_merge",
    "render_verdict",
    "resolve_product_policy",
]

DEFAULT_RUNNER: CommandRunner = ShellCommandRunner()

_EXIT_UNOBSERVABLE = 2


def resolve_product_policy(*, repo: Path) -> ProductPathPolicy:
    """Derive the repository's product-path prefixes from its own declaration."""
    pyproject = repo / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8") if pyproject.is_file() else None
    return product_policy(pyproject_text=text)


def decide(
    *,
    event: PullRequestEvent,
    changed_paths: tuple[str, ...],
    policy: ProductPathPolicy,
    landed_commits: tuple[str, ...] = (),
    incident_receipts: tuple[IncidentReceipt, ...] = (),
) -> ProvenanceVerdict:
    """Decide whether this pull request may merge on factory-provenance grounds."""
    product_paths = tuple(path for path in changed_paths if is_product_py(path=path, policy=policy))
    factory_authored = event.author_login in FACTORY_APP_LOGINS
    override_labeled = FACTORY_OVERRIDE_LABEL in event.labels
    receipt = matching_incident_receipt(
        receipts=incident_receipts,
        repository=event.repository,
        pr_number=event.pr_number,
        head_sha=event.head_sha,
        landed_commits=landed_commits,
    )
    repayment = matching_repayment_carrier(
        receipts=incident_receipts,
        repository=event.repository,
        pr_number=event.pr_number,
        head_sha=event.head_sha,
        landed_commits=landed_commits,
    )
    admitted = factory_authored or receipt is not None or (override_labeled and repayment is None)
    return ProvenanceVerdict(
        outcome=scoped_check_outcome(matched_file_count=len(product_paths), failing=not admitted),
        author_login=event.author_login,
        product_paths=product_paths,
        judged_path_count=len(changed_paths),
        factory_authored=factory_authored,
        override_labeled=override_labeled,
        incident_receipt=receipt,
        repayment_carrier=repayment,
    )


def _build_parser() -> argparse.ArgumentParser:
    """The CLI surface; `--changed-file` replaces the git diff read for tests."""
    parser = argparse.ArgumentParser(prog="factory-provenance-check")
    _ = parser.add_argument("--event-path", dest="event_path", default=None)
    _ = parser.add_argument("--repo", dest="repo", default=".")
    _ = parser.add_argument("--changed-file", dest="changed_files", action="append", default=None)
    add_incident_item_argument(parser=parser)
    return parser


def _resolve_event_path(*, declared: str | None) -> str | None:
    """The event payload path: the flag, else the Actions environment variable."""
    return declared if declared is not None else os.environ.get("GITHUB_EVENT_PATH")


def _unobservable(*, text: str) -> int:
    """Refuse without a verdict: the gate could not observe what it must judge."""
    write_stderr(
        text=f"factory-provenance check {text}; it refuses rather than passing unobserved.\n"
    )
    return _EXIT_UNOBSERVABLE


def _incident_evidence(
    *,
    item_ids: tuple[str, ...],
    event: PullRequestEvent,
    repo: Path,
    runner: CommandRunner,
    authority_client: BeadsClient | None,
) -> tuple[tuple[IncidentReceipt, ...], tuple[str, ...]] | str:
    """The named items' retained receipts and this PR's landed commits, or why not."""
    if not item_ids:
        return (), ()
    if not event.repository:
        return "cannot bind an incident receipt because the event payload names no repository"
    resolved = resolve_incident_receipts(
        client=incident_authority_client(repo=repo, client=authority_client),
        repository=event.repository,
        item_ids=item_ids,
    )
    if isinstance(resolved, IncidentReceiptRefusal):
        return describe_refusal(refusal=resolved)
    landed = read_landed_commits(event=event, repo=repo, runner=runner)
    if landed is None:
        return (
            f"could not read the commits for {diff_range(event=event)}; a shallow "
            "checkout needs fetch-depth: 0"
        )
    return resolved, landed


def main(
    *,
    argv: list[str] | None = None,
    runner: CommandRunner = DEFAULT_RUNNER,
    authority_client: BeadsClient | None = None,
) -> int:
    """Supervisor for the factory-provenance merge gate. Fails CLOSED, never open."""
    args = _build_parser().parse_args(argv)
    event_path = _resolve_event_path(declared=args.event_path)
    if event_path is None:
        return _unobservable(
            text="has no event payload to read: pass --event-path or set GITHUB_EVENT_PATH"
        )
    event = read_event(path=Path(event_path))
    if event is None:
        return _unobservable(text=f"could not read a pull_request event payload at {event_path}")
    repo = Path(args.repo)
    declared_files: list[str] | None = args.changed_files
    changed_paths = (
        tuple(declared_files)
        if declared_files is not None
        else read_changed_paths(event=event, repo=repo, runner=runner)
    )
    if changed_paths is None:
        return _unobservable(
            text=(
                f"could not read the diff for {diff_range(event=event)}; a shallow "
                "checkout needs fetch-depth: 0"
            )
        )
    evidence = _incident_evidence(
        item_ids=tuple(args.incident_items or ()),
        event=event,
        repo=repo,
        runner=runner,
        authority_client=authority_client,
    )
    if isinstance(evidence, str):
        return _unobservable(text=evidence)
    receipts, landed_commits = evidence
    verdict = decide(
        event=event,
        changed_paths=changed_paths,
        policy=resolve_product_policy(repo=repo),
        landed_commits=landed_commits,
        incident_receipts=receipts,
    )
    message = f"{render_verdict(verdict=verdict)}\n"
    if permits_merge(verdict=verdict):
        write_stdout(text=message)
    else:
        write_stderr(text=message)
    return exit_code(verdict=verdict)
