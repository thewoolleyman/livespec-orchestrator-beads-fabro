"""The `complete-incident` evidence: what the forge and tree report, and what the operator attests.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle" and its
scenario "incident completion requires final normal proof rather than an old
repair merge". `complete_incident` records `closed` only from evidence; this
module gathers that evidence for the operator entrance without trusting a
caller-typed result:

- the repayment PR's merge is `gh pr view` of the PR the named attempt binds;
- the marker scan is `git grep` of the incident marker over the named master
  run's head tree, after fetching that head; an unreadable tree stays
  unobserved, so `marker-removal-unobserved` remains an obligation;
- the manual outcome, the validated original paths, the repaid debt and the
  related failures still undisposed are one canonical operator attestation.

The master run is read by `observe_master_run`, the same forge read
`enter-repayment` takes.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro._incident_repayment_scope import incident_marker
from livespec_orchestrator_beads_fabro.commands._incident_authority_decode import invalid_payload
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.incident_completion import (
    IncidentCompletion,
    IncidentCompletionEvidence,
    complete_incident,
)
from livespec_orchestrator_beads_fabro.incident_normal_repayment import MasterCiRun

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentReading
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = [
    "ATTESTATION_FIELDS",
    "COMPLETION_OUTSTANDING",
    "MASTER_CI_UNOBSERVABLE",
    "REPAYMENT_PR_UNOBSERVABLE",
    "CompletionAttestation",
    "CompletionRequest",
    "complete_action",
    "complete_from_forge",
    "completion_reply",
    "decode_attestation",
    "observe_marker_paths",
    "observe_master_run",
    "observe_repayment_merge",
    "pr_head_marker_paths",
]

COMPLETION_OUTSTANDING = "incident-completion-outstanding"
MASTER_CI_UNOBSERVABLE = "incident-repayment-master-ci-unobservable"
REPAYMENT_PR_UNOBSERVABLE = "incident-completion-repayment-pr-unobservable"
_LISTS = ("repaid_debt", "undisposed_failures", "validated_paths")
ATTESTATION_FIELDS: tuple[str, ...] = tuple(sorted(("manual_outcome", *_LISTS)))
_PR_FIELDS = "number,state"
_PR_HEAD_FIELD = "headRefOid"
_RUN_FIELDS = "headSha,status,conclusion"
_COMPLETED = "completed"
_MERGED = "MERGED"
_NO_MATCH = 1
_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class CompletionAttestation:
    """What the operator attests: the facts no forge or tree read can establish."""

    manual_outcome: bool
    repaid_debt: tuple[str, ...]
    undisposed_failures: tuple[str, ...]
    validated_paths: tuple[str, ...]


def _strings(*, value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    items = cast("list[object]", value)
    return tuple(cast("list[str]", items)) if all(type(v) is str for v in items) else None


@dataclass(frozen=True, kw_only=True)
class CompletionRequest:
    """What the operator names: the master run to read and the attestation."""

    run_id: str
    attestation: CompletionAttestation


def observe_master_run(
    *, runner: CommandRunner, repo: Path, repository: str, run_id: str
) -> MasterCiRun | AuthorityRefusal:
    """The named master run exactly as the forge reports it now; unreadable is a refusal."""
    result = runner.run(
        argv=["gh", "run", "view", run_id, "--repo", repository, "--json", _RUN_FIELDS],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    raw = parse_json(text=result.stdout) if result.exit_code == 0 else None
    value = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
    head, status, conclusion = (value.get(k) for k in ("headSha", "status", "conclusion"))
    if not (isinstance(head, str) and isinstance(status, str) and isinstance(conclusion, str)):
        reason = result.stderr.strip() or "no headSha, status and conclusion in the reply"
        return AuthorityRefusal(code=MASTER_CI_UNOBSERVABLE, detail=f"run {run_id}: {reason}")
    return MasterCiRun(
        run_id=run_id,
        head=head,
        conclusion=conclusion or status,
        complete=status == _COMPLETED,
    )


def decode_attestation(*, text: str) -> CompletionAttestation | None:
    """Exactly one canonical attestation record, or None for anything else."""
    raw = parse_json(text=text)
    if not isinstance(raw, dict):
        return None
    value = cast("dict[str, object]", raw)
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if text != canonical or tuple(value) != ATTESTATION_FIELDS:
        return None
    lists = {name: _strings(value=value[name]) for name in _LISTS}
    manual = value["manual_outcome"]
    if type(manual) is not bool or any(v is None for v in lists.values()):
        return None
    return CompletionAttestation(
        manual_outcome=manual,
        repaid_debt=lists["repaid_debt"] or (),
        undisposed_failures=lists["undisposed_failures"] or (),
        validated_paths=lists["validated_paths"] or (),
    )


def observe_repayment_merge(
    *, runner: CommandRunner, repo: Path, repository: str, pr_number: int
) -> int | None | AuthorityRefusal:
    """The bound PR's number when the forge reports it merged; None when unbound or unmerged."""
    if pr_number <= 0:
        return None
    result = runner.run(
        argv=["gh", "pr", "view", str(pr_number), "--repo", repository, "--json", _PR_FIELDS],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    raw = parse_json(text=result.stdout) if result.exit_code == 0 else None
    value = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
    number, state = value.get("number"), value.get("state")
    if type(number) is not int or not isinstance(state, str):
        reason = result.stderr.strip() or "no number and state in the reply"
        return AuthorityRefusal(code=REPAYMENT_PR_UNOBSERVABLE, detail=f"PR #{pr_number}: {reason}")
    return number if state == _MERGED else None


def observe_marker_paths(
    *, runner: CommandRunner, repo: Path, head: str, item_id: str
) -> tuple[str, ...] | None:
    """The paths of `head`'s tree that still carry the incident marker; None when unreadable."""
    _ = runner.run(
        argv=["git", "fetch", "--quiet", "--no-tags", "origin", head],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    result = runner.run(
        argv=["git", "grep", "-l", "-F", "-e", incident_marker(item_id=item_id), head, "--"],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    if result.exit_code == _NO_MATCH and not result.stdout and not result.stderr.strip():
        return ()
    if result.exit_code != 0:
        return None
    prefix = f"{head}:"
    return tuple(line.removeprefix(prefix) for line in result.stdout.splitlines() if line)


def pr_head_marker_paths(
    *, runner: CommandRunner, repo: Path, repository: str, pr_number: int, item_id: str
) -> tuple[str, ...] | None:
    """The paths of PR `pr_number`'s head tree carrying the incident marker; None if unreadable."""
    result = runner.run(
        argv=[
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repository,
            "--json",
            _PR_HEAD_FIELD,
        ],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    raw = parse_json(text=result.stdout) if result.exit_code == 0 else None
    value = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
    head = value.get(_PR_HEAD_FIELD)
    if not (isinstance(head, str) and head):
        return None
    return observe_marker_paths(runner=runner, repo=repo, head=head, item_id=item_id)


def completion_reply(
    *, completion: IncidentCompletion | AuthorityRefusal
) -> IncidentCompletion | AuthorityRefusal:
    """A completion that recorded nothing is a refusal naming every outstanding obligation."""
    if isinstance(completion, AuthorityRefusal) or completion.recorded:
        return completion
    return AuthorityRefusal(
        code=COMPLETION_OUTSTANDING,
        detail=f"{completion.item_id}: {'; '.join(completion.outstanding)}",
    )


def complete_from_forge(
    *,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
    repo: Path,
    repository: str,
    completion: CompletionRequest,
) -> IncidentCompletion | AuthorityRefusal:
    """Read the master run, the bound PR and the run head's tree, then call `complete_incident`."""
    attempt = reading.attempt
    master_ci = observe_master_run(
        runner=runner, repo=repo, repository=repository, run_id=completion.run_id
    )
    if isinstance(master_ci, AuthorityRefusal):
        return master_ci
    merged = observe_repayment_merge(
        runner=runner, repo=repo, repository=repository, pr_number=attempt.pr_number
    )
    if isinstance(merged, AuthorityRefusal):
        return merged
    attestation = completion.attestation
    evidence = IncidentCompletionEvidence(
        merged_pr_number=merged,
        master_ci=master_ci,
        marker_paths=observe_marker_paths(
            runner=runner, repo=repo, head=master_ci.head, item_id=attempt.item_id
        ),
        validated_paths=attestation.validated_paths,
        repaid_debt=attestation.repaid_debt,
        manual_outcome=attestation.manual_outcome,
        undisposed_failures=attestation.undisposed_failures,
    )
    completed = complete_incident(client=client, item_id=attempt.item_id, evidence=evidence)
    return completion_reply(completion=completed)


def complete_action(
    *,
    args: argparse.Namespace,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
) -> IncidentCompletion | AuthorityRefusal:
    """Decode the operator attestation, then complete from fresh forge evidence."""
    attestation = decode_attestation(text=args.completion_json)
    if attestation is None:
        detail = f"needs exactly {list(ATTESTATION_FIELDS)} as one canonical JSON object"
        return invalid_payload(flag="--completion-json", detail=detail)
    return complete_from_forge(
        client=client,
        reading=reading,
        runner=runner,
        repo=args.repo,
        repository=args.repository,
        completion=CompletionRequest(run_id=args.master_run, attestation=attestation),
    )
