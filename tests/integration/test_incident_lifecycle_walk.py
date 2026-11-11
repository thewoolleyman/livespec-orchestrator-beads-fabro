"""One incident walked through its whole expedited chain on real code, across both repositories.

The plan's acceptance for arming. One canonical item walks attempt 1 from genesis
through its merge, its first required-leaf failure, the revert and the collected
evidence; attempt 2 from a staged-tree correction through a green merge and
repayment entry; a regression reopen that supersedes that repayment; attempt 3
from `correct-attempt`, whose expedited PR fails a retained fast check and is
closed unmerged; attempt 4 from `correct-unmerged-attempt`; and the one
repayment that survives, through its merge and closure.

Real, end to end: the orchestrator's `incident_authority.py` process boundary,
its reader, writers and transition validator; livespec-dev-tooling's observer
control routes (`/arm`, `/current`, `/bind`), the merged-run verifier `/bind`
calls, the current reader, the signed-callback handler, the inverse planner, the
`/recover` route, the hook scope, the original-run entrance on its installed
ports and its run reader; and git, in a real clone of a real bare repository.

Faked, and nothing else:
- `bd`, by `FakeBeadsClient`;
- the forge: `gh pr view` and `gh run view` for the orchestrator, and the REST
  GETs the recovery App's read-only token would make for dev-tooling (`_Forge`);
- the recovery principal's forge effects (`_Principal`): it publishes the inverse
  the real planner built, and stands in for the principal's own authorization;
- the controller host's protected configuration, which `ControllerInstallation.load`
  would validate (the installation itself is built in full).
A subprocess hop into the reader or the authority is a direct call of the same
`main`. A step that cannot run on the real chain fails this test.

Steps no named action writes yet, and the ordinary-policy moves the factory and
admission would make, are marked `HAND:` where the walk takes them.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import io
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from livespec_dev_tooling import incident_original_run_entry
from livespec_dev_tooling._incident_inverse_types import (
    InversePublishRequest,
    InversePublishResult,
    LandedIncident,
)
from livespec_dev_tooling._incident_observer_types import JobCallback, RecoveryIntent
from livespec_dev_tooling._incident_recovery_git import LandedGit
from livespec_dev_tooling.config import derive_source_prefixes, load_config
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_execution import (
    Invocation,
    OperationIdentity,
    resolve_execution_context,
)
from livespec_dev_tooling.incident_forge_reads import ForgeReads
from livespec_dev_tooling.incident_hook_scope import HookCall, validate_scope
from livespec_dev_tooling.incident_inverse import observer_inverse_callback
from livespec_dev_tooling.incident_observer import handle_job_callback
from livespec_dev_tooling.incident_observer_control import ObserverControl
from livespec_dev_tooling.incident_observer_query import ObserverQuery
from livespec_dev_tooling.incident_observer_recovery import ObserverRecovery
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    attempt_record,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    claim_stamp_metadata,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import incident_authority as command
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._incident_provenance import (
    matching_incident_receipt,
    receipts_from_history,
)
from livespec_orchestrator_beads_fabro.incident_completion import read_incident_standing

REPOSITORY = "owner/repository"
ITEM = "test-incident"
OWNER = "operator:alice"
SOURCE_TREE = "src"
APP = f"{SOURCE_TREE}/app.py"
# The committed configuration at the base and at every attempt head. From dev-tooling
# v1.195.0 (livespec-dev-tooling-6ou5m2) `/arm` reads it at the target ref and at the head
# to derive the source prefixes, and refuses a record that omits a changed product file.
PYPROJECT_SOURCE = f'[tool.livespec_dev_tooling]\nsource_trees = ["{SOURCE_TREE}"]\n'
WORKFLOW = ".github/workflows/ci.yml"
# The workflow at the merge, from which dev-tooling derives the expected job graph of an
# original run (livespec-dev-tooling-zapgpu, v1.192.x): one block-style job per JOBS entry.
WORKFLOW_SOURCE = (
    "name: ci\n"
    "on: push\n"
    "jobs:\n"
    "  check-lint:\n"
    "    runs-on: ubuntu-latest\n"
    "  check-metadata-batch:\n"
    "    runs-on: ubuntu-latest\n"
)
LEAF = "check-metadata-batch"
JOBS = ("check-lint", LEAF)
WEBHOOK_SECRET = b"webhook-secret"
EMPTY = "0" * 40
GIT_IDENTITY = (
    "-c",
    "user.name=walk",
    "-c",
    "user.email=walk@example.invalid",
    "-c",
    "commit.gpgsign=false",
    "-c",
    f"core.hooksPath={os.devnull}",
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


# The focused-evidence row and receipt-id derivation of dev-tooling's `/arm` gate
# (livespec_dev_tooling.incident_focused_admission, livespec-dev-tooling-4aksht, v1.192.2):
# one slot's id is the sha256 of the canonical JSON of [row, subject, slot]. The walk
# derives it itself so the same steps run against a pin that predates the gate, where the
# record is stored and simply never read; a changed derivation fails loudly at the arm.
FOCUSED_EVIDENCE_ROW = "incident-focused-evidence"


def _evidence_receipt_id(*, subject: dict[str, object], slot: int) -> str:
    return hashlib.sha256(_canonical([FOCUSED_EVIDENCE_ROW, subject, slot]).encode()).hexdigest()


def _flags(attempt: IncidentAttempt) -> list[str]:
    return [
        *("--repository", attempt.repository, "--item", attempt.item_id),
        *("--attempt", attempt.attempt_id, "--phase", attempt.phase),
        *("--operation", attempt.operation_id, "--generation", str(attempt.generation)),
        *("--owner", attempt.owner),
    ]


@dataclass
class _Forge:
    """The forge: `gh pr view` and `gh run view` for the orchestrator, REST GETs for dev-tooling."""

    prs: dict[str, dict[str, object]] = field(default_factory=dict)
    runs: dict[str, dict[str, str]] = field(default_factory=dict)
    rest: dict[str, object] = field(default_factory=dict)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        if argv[0] == "git":
            return ShellCommandRunner().run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds)
        table: dict[str, Any] = self.prs if argv[1] == "pr" else self.runs
        return CommandResult(exit_code=0, stdout=json.dumps(table[argv[3]]), stderr="")

    def api(self, path: str) -> object:
        """One read-only GET under `repos/<repository>/`; anything unpublished is absent."""
        return self.rest.get(path)

    def publish_run(
        self, *, run_id: int, head: str, status: str, jobs: list[dict[str, object]]
    ) -> None:
        """A master push run as the Actions API reports it, with its original attempt's jobs."""
        repository = {"full_name": REPOSITORY}
        base = f"repos/{REPOSITORY}/actions/runs/{run_id}"
        run = {
            "id": run_id,
            "run_attempt": 1,
            "event": "push",
            "head_branch": "master",
            "head_sha": head,
            "path": WORKFLOW,
            "status": status,
            "repository": repository,
            "head_repository": repository,
        }
        self.rest[base] = run
        self.rest[f"{base}/attempts/1"] = run
        self.rest[f"{base}/attempts/1/jobs?per_page=100&page=1"] = {
            "total_count": len(jobs),
            "jobs": jobs,
        }
        source = base64.b64encode(WORKFLOW_SOURCE.encode()).decode()
        self.rest[f"repos/{REPOSITORY}/contents/{WORKFLOW}?ref={head}"] = {
            "encoding": "base64",
            "content": source,
        }


@dataclass
class _Walk:
    """One tenant, one clone, one observer state directory and one forge."""

    client: FakeBeadsClient
    forge: _Forge
    root: Path
    state: Path
    runs: int = 9000

    def git(self, *args: str, env: dict[str, str] | None = None) -> str:
        return subprocess.run(
            ["git", "-C", str(self.root), *GIT_IDENTITY, *args],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, **(env or {})},
        ).stdout.strip()

    def process(self, argv: list[str]) -> tuple[int, dict[str, Any]]:
        """One `incident_authority.py` process, as the installed reader and writer are called."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = command.main(argv=argv)
        return code, json.loads(out.getvalue())

    def act(self, action: str, current: IncidentAttempt, *payload: str) -> IncidentAttempt:
        code, reply = self.process([action, "--repo", str(self.root), *_flags(current), *payload])
        assert (code, reply["status"]) == (0, "verified"), reply
        body = reply["result"]
        recorded = decode_attempt(
            value=body["reading"]["attempt"] if "reading" in body else body["attempt"]
        )
        assert recorded is not None
        assert self.head() == recorded, "the reply is the chain's new head"
        return recorded

    def refused(self, action: str, current: IncidentAttempt, *payload: str) -> str:
        code, reply = self.process([action, "--repo", str(self.root), *_flags(current), *payload])
        assert (code, reply["status"]) == (78, "refused"), reply
        return reply["result"]["code"]

    def head(self) -> IncidentAttempt:
        return read_incident_standing(client=self.client, item_id=ITEM).history[-1]

    def installation(self) -> ControllerInstallation:
        return ControllerInstallation(
            repository=REPOSITORY,
            repo=self.root,
            state=self.state,
            reader=("reader",),
            reader_release="reader-1",
            principal=("principal",),
            release="dt-1",
            revision="c" * 40,
            jobs=JOBS,
            webhook_secret=WEBHOOK_SECRET,
            control_secret=b"c",
            query_secret=b"q",
            port=1,
            config=self.state.parent / "controller.json",
        )

    # Every expedited attempt's own steps, in the order an operator takes them.

    def write_marked(self, text: str) -> str:
        """Stage the repair with its marker comment; return the staged tree."""
        _ = (self.root / APP).write_text(
            f"# EXPEDITED_INCIDENT_RESPONSE flag: {ITEM}\nVALUE = {text!r}\n"
        )
        _ = self.git("add", APP)
        return self.git("write-tree")

    def hook(
        self, *, hook: str, attempt: IncidentAttempt, stdin: str, extra: tuple[str, ...]
    ) -> None:
        """The real expedited hook scope over the attempt the real reader returns."""
        code, reply = self.process(["read-current", "--repo", str(self.root), *_flags(attempt)])
        assert code == 0, reply
        context = resolve_execution_context(
            environ={"EXPEDITED_INCIDENT_RESPONSE": "1"},
            invocation=Invocation.ORDINARY,
            identity=OperationIdentity(
                incident_item_id=ITEM,
                attempt_id=attempt.attempt_id,
                phase=attempt.phase,
                repository=REPOSITORY,
                base_sha=attempt.base,
                head_sha=attempt.head,
                operation_id=attempt.operation_id,
                recorded_incident_merge_sha=None,
            ),
        ).unwrap()
        _ = validate_scope(
            repo=self.root,
            context=context,
            reading=reply["result"],
            query={"repository": REPOSITORY},
            tree=self.git("rev-parse", "HEAD^{tree}")
            if hook == "pre-push"
            else self.git("write-tree"),
            call=HookCall(hook=hook, extra=extra, stdin=stdin),
        )

    def publish(self, attempt: IncidentAttempt, *, number: int) -> IncidentAttempt:
        """Commit the staged tree, advance the head, push, open the PR and bind it."""
        reserved = attempt.carrier
        assert reserved is not None
        self.hook(hook="pre-commit", attempt=attempt, stdin="", extra=())
        _ = self.git("commit", "-q", "-m", f"fix: incident repair for pull request {number}")
        commit = self.git("rev-parse", "HEAD")
        assert self.git("rev-parse", "HEAD^{tree}") == reserved.staged_tree
        record = json.loads(_canonical(attempt_record(attempt=attempt)))
        # HAND: the head advance between commit and push; `commit-transition` writes it.
        advanced = self.transition(
            attempt, record | {"operation_id": f"{attempt.attempt_id}#head", "head": commit}
        )
        ref = reserved.target_ref
        self.hook(
            hook="pre-push",
            attempt=advanced,
            stdin=f"{ref} {commit} {ref} {EMPTY}\n",
            extra=("origin", f"https://github.com/{REPOSITORY}"),
        )
        _ = self.git("push", "-q", "origin", f"HEAD:{ref}")
        # HAND: the PR bind once the PR exists; `commit-transition` writes it.
        carrier = {
            "state": "pr-bound",
            "target_ref": ref,
            "input_parent": reserved.input_parent,
            "staged_tree": reserved.staged_tree,
            "remote_head": commit,
        }
        return self.transition(
            advanced,
            json.loads(_canonical(attempt_record(attempt=advanced)))
            | {"operation_id": f"{attempt.attempt_id}#pr", "pr_number": number, "carrier": carrier},
        )

    def transition(self, current: IncidentAttempt, record: dict[str, Any]) -> IncidentAttempt:
        successor = record | {"generation": current.generation + 1}
        return self.act("commit-transition", current, "--successor-json", _canonical(successor))

    def record_focused_evidence(self, attempt: IncidentAttempt) -> dict[str, Any]:
        """Record the head tree's focused evidence through the real `record-local-gates`.

        The record is what the real collector would emit for this head: its paths are
        the attempt's own base..head diff, each Python path executable and fully
        covered, the focused tests and the coverage run finished at exit 0, and the
        manual reproduction passed. So it leaves no member awaiting a disposition.
        The forge answers the head commit's tree, which the gate reads itself.
        Returns the recorded receipt.
        """
        tree = self.git("rev-parse", f"{attempt.head}^{{tree}}")
        self.forge.rest[f"repos/{REPOSITORY}/git/commits/{attempt.head}"] = {
            "sha": attempt.head,
            "tree": {"sha": tree},
        }
        changed = self.git("diff", "--name-only", attempt.base, attempt.head).splitlines()
        executable = [path for path in changed if path.endswith(".py")]
        subject: dict[str, object] = {
            "repository": REPOSITORY,
            "item": ITEM,
            "attempt": attempt.attempt_id,
            "operation": attempt.operation_id,
            "generation": attempt.generation,
            "head": attempt.head,
            "tree": tree,
        }
        finished = {"timed_out": False, "returncode": 0}
        record = {
            "mode": "expedited-repair",
            "scope": "focused-tests-and-touched-files",
            "tree_hash": tree,
            "outcome": "passed",
            "identity": {
                "repository": REPOSITORY,
                "incident_item_id": ITEM,
                "attempt_id": attempt.attempt_id,
                "operation_id": attempt.operation_id,
                "head_sha": attempt.head,
            },
            "manual": {
                "outcome": "passed",
                "procedure": f"run {APP} on the repaired head",
                "expected": "the incident no longer reproduces",
                "observed": "the incident no longer reproduces",
            },
            "tests": finished,
            "coverage_command": finished,
            "paths": {
                path: "executable" if path in executable else "non-executable" for path in changed
            },
            "coverage": {path: {"summary": {"percent_covered": 100}} for path in executable},
            "selection": {"deferred_tests": {}},
            "risks": [],
        }
        row = {
            "name": FOCUSED_EVIDENCE_ROW,
            "status": "passed",
            "reason": "focused evidence passed",
            "returncode": 0,
            "duration_seconds": 1.0,
            "output": _canonical(record),
        }
        receipt = {
            "receipt_id": _evidence_receipt_id(subject=subject, slot=0),
            "hook": "pre-push",
            "tree": tree,
            "mode": "expedited-repair",
            "evidence_kind": "expedited-local-partial",
            "exit_status": 0,
            "results": [row],
        }
        code, reply = self.process(
            [
                "record-local-gates",
                "--repo",
                str(self.root),
                *_flags(attempt),
                "--receipt-json",
                _canonical(receipt),
            ]
        )
        assert (code, reply["status"]) == (0, "verified"), reply
        return receipt

    def arm(self, attempt: IncidentAttempt, *, expected: str | None) -> str:
        """`POST /arm` with the attempt the reader returns, as the arming procedure builds it."""
        code, reply = self.process(["read-current", "--repo", str(self.root), *_flags(attempt)])
        assert code == 0, reply
        evidence = self.record_focused_evidence(attempt)
        # The arm is judged over a real changed product file: the attempt touches APP,
        # which lies under the source prefixes the committed configuration declares, and
        # the record names it executable with a coverage row, so the focused-evidence
        # comparison of `/arm` has a product file to compare.
        prefixes = derive_source_prefixes(config=load_config(repo_root=self.root))
        changed = self.git("diff", "--name-only", attempt.base, attempt.head).splitlines()
        assert [path for path in changed if path.startswith(prefixes)] == [APP], changed
        recorded = json.loads(evidence["results"][0]["output"])
        assert recorded["paths"][APP] == "executable", recorded
        assert APP in recorded["coverage"], recorded
        receipt = _canonical(reply["result"]["attempt"]).encode().hex()
        payload = {
            "repository": REPOSITORY,
            "incident_item_id": ITEM,
            "attempt_id": attempt.attempt_id,
            "operation_id": attempt.operation_id,
            "generation": attempt.generation,
            "owner": attempt.owner,
            "phase": attempt.phase,
            "pr_number": attempt.pr_number,
            "base_sha": attempt.base,
            "head_sha": attempt.head,
            "authority_receipt": receipt,
            "expected_arm_id": expected,
        }
        armed = ObserverControl(installation=self.installation()).execute(
            path="/arm", payload=payload
        )
        assert armed["status"] == "armed", armed
        # The arm admitted THIS record: the gate's own read of the head tree returns it.
        code, lookup = self.process(
            [
                "read-local-gates",
                "--repo",
                str(self.root),
                *_flags(attempt),
                "--receipt-id",
                evidence["receipt_id"],
            ]
        )
        assert (code, lookup["result"]["status"]) == (0, "recorded"), lookup
        assert lookup["result"]["receipt"] == evidence, lookup
        query = {
            "repository": REPOSITORY,
            "arm_id": armed["receipt"],
            "pr_number": attempt.pr_number,
            "base_sha": attempt.base,
            "head_sha": attempt.head,
            "receipt_digest": hashlib.sha256(bytes.fromhex(receipt)).hexdigest(),
        }
        # What an expedited PR's CI asks before each job: the arm is current on the real chain.
        current = ObserverQuery(installation=self.installation()).execute(
            path="/current", payload=query
        )
        assert current["status"] == "current", current
        return armed["receipt"]

    def merge(self, attempt: IncidentAttempt) -> tuple[str, int]:
        """The forge rebase-merges the PR; the merge script then runs `POST /bind`.

        HAND: that script, which sends `/bind` within seconds of the push run's
        creation and then runs `record-merge` (each caller here runs it next).
        """
        carrier = attempt.carrier
        assert carrier is not None
        _ = self.git("fetch", "-q", "origin")
        branch_head = attempt.head
        _ = self.git("checkout", "-q", "--detach", "origin/master")
        _ = self.git("cherry-pick", branch_head, env={"GIT_COMMITTER_DATE": "2026-11-07T12:00:00Z"})
        merged = self.git("rev-parse", "HEAD")
        _ = self.git("push", "-q", "origin", f"{merged}:refs/heads/master")
        _ = self.git("fetch", "-q", "origin")
        self.forge.prs[str(attempt.pr_number)] = {
            "number": attempt.pr_number,
            "state": "MERGED",
            "headRefName": carrier.target_ref.removeprefix("refs/heads/"),
            "headRefOid": branch_head,
            "mergeCommit": {"oid": merged},
            "commits": [{"messageHeadline": self.git("show", "-s", "--format=%s", merged)}],
        }
        self.runs += 1
        self.forge.rest[f"repos/{REPOSITORY}/pulls/{attempt.pr_number}"] = {
            "number": attempt.pr_number,
            "merged": True,
            "state": "closed",
            "merge_commit_sha": merged,
            "head": {"sha": branch_head},
            "base": {"ref": "master", "repo": {"full_name": REPOSITORY}},
        }
        self.forge.publish_run(run_id=self.runs, head=merged, status="in_progress", jobs=[])
        bound = ObserverControl(installation=self.installation()).execute(
            path="/bind",
            payload={"repository": REPOSITORY, "head_sha": merged, "run_id": self.runs},
        )
        assert bound["status"] == "admitted", bound
        return merged, self.runs

    def leaf_failure(self, *, merged: str, run_id: int, principal: _Principal) -> str:
        """The real signed callback: the first failing required leaf reverts through the planner."""
        body = json.dumps(
            {
                "action": "completed",
                "repository": {"full_name": REPOSITORY},
                "workflow_job": {
                    "id": run_id + 1,
                    "run_id": run_id,
                    "name": LEAF,
                    "head_sha": merged,
                    "head_branch": "master",
                    "status": "completed",
                    "conclusion": "failure",
                },
            }
        ).encode()
        result = handle_job_callback(
            directory=self.state,
            delivery=JobCallback(
                body=body,
                signature="sha256=" + hmac.new(WEBHOOK_SECRET, body, hashlib.sha256).hexdigest(),
                event="workflow_job",
                delivery_id=f"delivery-{run_id}",
            ),
            webhook_secret=WEBHOOK_SECRET,
            recover=observer_inverse_callback(repo_root=self.root, forge=principal),
        )
        assert result.status == "completed", result
        return principal.published[-1]

    def receipt_flags(self, attempt: IncidentAttempt) -> dict[str, Any]:
        """The reopened-chain receipt `POST /recover` takes."""
        code, reply = self.process(["read-current", "--repo", str(self.root), *_flags(attempt)])
        assert code == 0, reply
        return {
            "repository": REPOSITORY,
            "incident_item_id": ITEM,
            "attempt_id": attempt.attempt_id,
            "phase": attempt.phase,
            "operation_id": attempt.operation_id,
            "generation": attempt.generation,
            "owner": attempt.owner,
            "authority_receipt": _canonical(reply["result"]["attempt"]).encode().hex(),
        }

    def recover(self, attempt: IncidentAttempt, *, principal: _Principal) -> dict[str, Any]:
        return ObserverRecovery(
            installation=self.installation(),
            recover=observer_inverse_callback(repo_root=self.root, forge=principal),
        ).execute(payload=self.receipt_flags(attempt))

    def entrance(self, *args: str) -> tuple[int, dict[str, Any]]:
        """The original-run entrance, run as the controller account on its installed ports."""
        config = ("--config", str(self.installation().config))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = incident_original_run_entry.main(argv=[args[0], *config, *args[1:]])
        return code, json.loads(out.getvalue())


@dataclass
class _Principal:
    """The scoped recovery principal's forge effects, over the real clone and the real planner."""

    walk: _Walk
    published: list[str] = field(default_factory=list)
    receipts: dict[str, str] = field(default_factory=dict)
    record_conflict: Mock = field(default_factory=Mock)

    def landed_incident(self, *, intent: RecoveryIntent) -> LandedIncident:
        registration, arm = intent.registration, intent.observer_arm
        assert arm is not None
        facts = LandedGit.facts(root=self.walk.root, merge_sha=registration.head_sha, count=1)
        return LandedIncident(
            repository=registration.repository,
            pr_number=arm.pr_number,
            original_base_sha=arm.base_sha,
            original_head_sha=arm.head_sha,
            before_sha=facts.before_sha,
            merge_sha=registration.head_sha,
            landed_commits=facts.landed_commits,
            landed_trees=facts.landed_trees,
            patch_sha256=facts.patch_sha256,
            changed_paths=facts.changed_paths,
            authority_sha256=hashlib.sha256(registration.authority_receipt).hexdigest(),
        )

    def authorize_inverse(self, *, intent: RecoveryIntent, scope: LandedIncident) -> bool:
        return bool(intent.action_id and scope.pr_number)

    def read_master_head(self, *, repository: str, branch: str) -> str:
        assert repository == REPOSITORY
        return self.walk.git("rev-parse", f"refs/remotes/origin/{branch}")

    def read_exact_receipt(self, *, intent: RecoveryIntent) -> str | None:
        return self.receipts.get(intent.action_id)

    def publish_inverse(self, *, request: InversePublishRequest) -> InversePublishResult:
        plan = request.plan
        revert = self.walk.git(
            "commit-tree", plan.tree_sha, "-p", plan.expected_head, "-m", request.message
        )
        _ = self.walk.git("push", "-q", "origin", f"{revert}:refs/heads/master")
        _ = self.walk.git("fetch", "-q", "origin")
        self.published.append(revert)
        self.receipts[request.intent.action_id] = f"receipt-{revert}"
        return InversePublishResult(status="committed", merge_sha=revert, tree_sha=plan.tree_sha)


def _clone(*, tmp_path: Path) -> tuple[Path, Path]:
    """A real clone of a real bare repository, with the repository before the incident."""
    origin, root, state = tmp_path / "origin.git", tmp_path / "primary", tmp_path / "state"
    _ = subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(origin)], check=True)
    _ = subprocess.run(
        ["git", "clone", "-q", str(origin), str(root)], check=True, capture_output=True
    )
    state.mkdir(mode=0o700)
    _ = (tmp_path / "reader.env").write_text("BEADS_DOLT_PASSWORD=tenant-credential\n")
    (root / ".github/workflows").mkdir(parents=True)
    _ = (root / WORKFLOW).write_text(WORKFLOW_SOURCE)
    _ = (root / "pyproject.toml").write_text(PYPROJECT_SOURCE)
    (root / SOURCE_TREE).mkdir()
    _ = (root / APP).write_text("VALUE = 'broken'\n")
    config = {"livespec-orchestrator-beads-fabro": {"dispatcher": {"claim_tokens": True}}}
    _ = (root / ".livespec.jsonc").write_text(json.dumps(config))
    return root, state


def _tenant() -> FakeBeadsClient:
    client = FakeBeadsClient()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-07T00:00:00Z",
        )
    )
    return client


_REAL_SUBPROCESS_RUN = subprocess.run


def _cross_the_process_boundaries(monkeypatch: pytest.MonkeyPatch, walk: _Walk) -> None:
    """Each subprocess hop into the reader or authority becomes a call of the same `main`.

    The hops are replaced at the public `subprocess.run` seam, never at a private
    dev-tooling helper: dev-tooling is free to reroute its calls between releases
    (v1.190.1 moved every authority call onto `incident_authority_client`), and a
    patch naming a private symbol breaks every pin bump past the release that
    removed it (bd-ib-elrodm). Every other argv, such as git, runs for real.
    """

    def run(argv: Any, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        if not isinstance(argv, list | tuple) or not argv or argv[0] not in {"bd", "reader"}:
            return _REAL_SUBPROCESS_RUN(argv, *args, **kwargs)
        assert Path(kwargs["cwd"]) == walk.root
        if argv[0] == "bd":
            assert kwargs["env"]["BEADS_DOLT_PASSWORD"] == "tenant-credential"
            code, stdout = 0, _bd(walk.client, list(argv[1:]))
        else:
            code, reply = walk.process(list(argv[1:]))
            stdout = json.dumps(reply).encode()
        if kwargs.get("text"):
            return subprocess.CompletedProcess(
                args=argv, returncode=code, stdout=stdout.decode(), stderr=""
            )
        return subprocess.CompletedProcess(args=argv, returncode=code, stdout=stdout, stderr=b"")

    def installed(**_: object) -> ControllerInstallation:
        return walk.installation()

    def forge_reads(**_: object) -> Any:
        return walk.forge.api

    monkeypatch.setattr(subprocess, "run", run)
    # The protected configuration's own validation is the host's; this walk owns the rest.
    monkeypatch.setattr(ControllerInstallation, "load", staticmethod(installed))
    # The recovery App's read-only token: every forge GET goes to `_Forge.api`.
    monkeypatch.setattr(ForgeReads, "installed", staticmethod(forge_reads))


@pytest.fixture
def walk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Walk:
    # A commit hook runs this test with its own repository named in the environment.
    # One statement, so the line runs whether or not this environment has any.
    _ = [monkeypatch.delenv(name) for name in list(os.environ) if name.startswith("GIT_")]
    root, state = _clone(tmp_path=tmp_path)
    client = _tenant()
    created = _Walk(client=client, forge=_Forge(), root=root, state=state)
    _ = created.git("add", ".")
    _ = created.git("commit", "-q", "-m", "chore: the repository before the incident")
    _ = created.git("push", "-q", "origin", "HEAD:refs/heads/master")
    _ = created.git("fetch", "-q", "origin")

    def no_config(**_: object) -> None:
        return None

    def tenant_client(**_: object) -> FakeBeadsClient:
        return client

    monkeypatch.setattr(command, "store_config", no_config)
    monkeypatch.setattr(command, "make_beads_client", tenant_client)
    monkeypatch.setattr(command, "ShellCommandRunner", lambda: created.forge)
    _cross_the_process_boundaries(monkeypatch, created)
    return created


def _bd(client: FakeBeadsClient, args: list[str]) -> bytes:
    """The two `bd comments` forms the original-run ledger port uses."""
    if args[:2] == ["comments", "add"]:
        client.add_comment(issue_id=args[2], body=args[3])
        return b""
    assert args[0] == "comments"
    assert args[2] == "--json"
    return json.dumps(client.list_comments(issue_id=args[1])).encode()


def _genesis(walk: _Walk) -> IncidentAttempt:
    """Filing is out of scope; the item names a claim token, and genesis takes it over."""
    client = walk.client
    token = create_claim_token(client=client)
    client.update_issue(
        issue_id=ITEM,
        status="ready",
        metadata={"rank": "a0", CLAIM_TOKEN_METADATA_KEY: token},
        names_claim_token=True,
    )
    base = walk.git("rev-parse", "HEAD")
    _ = walk.git("checkout", "-q", "-b", "incident/test-incident-attempt-1")
    tree = walk.write_marked("attempt 1")
    attempt = {
        "repository": REPOSITORY,
        "item_id": ITEM,
        "attempt_id": "attempt-1",
        "phase": "repair",
        "operation_id": "operation-1",
        "generation": 1,
        "owner": OWNER,
        "base": base,
        "head": base,
        "pr_number": 0,
        "landed_commits": [],
        "landed_trees": [],
        "original_paths": [APP],
        "deferred_work": ["normal-factory-proof"],
        "repayment_required": True,
        "carrier": {
            "state": "branch-reserved",
            "target_ref": "refs/heads/incident/test-incident-attempt-1",
            "input_parent": base,
            "staged_tree": tree,
        },
    }
    request = _canonical(
        {"schema": 1, "principal": OWNER, "expected_claim": token, "attempt": attempt}
    )
    code, reply = walk.process(
        [
            "publish-genesis",
            "--repo",
            str(walk.root),
            "--repository",
            REPOSITORY,
            "--item",
            ITEM,
            "--attempt",
            "attempt-1",
            "--phase",
            "repair",
            "--operation",
            "operation-1",
            "--generation",
            "1",
            "--owner",
            OWNER,
            "--genesis-json",
            request,
        ]
    )
    assert (code, reply["status"]) == (0, "verified"), reply
    return walk.head()


def _finding(*, merged: str, run_id: int, surface: str = "trunk") -> str:
    return _canonical(
        {
            "surface": surface,
            "subject": LEAF,
            "run_id": str(run_id),
            "failed_head": merged,
            "attributed_commit": merged,
            "master_healthy": False,
        }
    )


def _reopen(
    walk: _Walk, *, current: IncidentAttempt, attributed: IncidentAttempt, finding: str
) -> IncidentAttempt:
    return walk.act(
        "reopen-regression",
        current,
        *("--attributed-json", _canonical(attempt_record(attempt=attributed))),
        *("--finding-json", finding, "--principal", OWNER),
    )


def _revert_receipt(walk: _Walk, current: IncidentAttempt, *, revert: str) -> IncidentAttempt:
    """HAND: `record-revert-receipt`, until the controller reconciles its receipt itself."""
    return walk.act(
        "record-revert-receipt",
        current,
        "--revert-receipt-json",
        _canonical({"receipt_id": f"receipt-{revert}", "revert_commit": revert}),
    )


def _collect_args(*, revert: str, tmp_path: Path) -> tuple[str, ...]:
    graph = tmp_path / "graph.json"
    _ = graph.write_text(json.dumps([{"name": job, "needs": []} for job in JOBS]))
    return ("collect", "--revert-sha", revert, "--expected-graph", str(graph))


def _attempt_one(
    walk: _Walk, principal: _Principal, tmp_path: Path
) -> tuple[IncidentAttempt, str, int, str]:
    """Genesis to the revert: the first leaf fails, and the merge is recorded only afterwards."""
    genesis = _genesis(walk)
    assert (genesis.phase, genesis.generation, genesis.owner) == ("repair", 1, OWNER)
    bound = walk.publish(genesis, number=101)
    assert (bound.phase, bound.generation, bound.pr_number) == ("repair", 3, 101)
    arm_id = walk.arm(bound, expected=None)
    # Before the merge the action refuses: the forge says the PR is still open.
    walk.forge.prs["101"] = {
        "number": 101,
        "state": "OPEN",
        "headRefName": "incident/test-incident-attempt-1",
        "headRefOid": bound.head,
        "commits": [{"messageHeadline": "x"}],
    }
    assert walk.refused("record-merge", bound) == "incident-merge-pr-unmerged"
    merged, run_id = walk.merge(bound)
    # A reopen cannot jump the record: the attempt it would attribute is not merged yet.
    assert (
        walk.refused(
            "reopen-regression",
            bound,
            *("--attributed-json", _canonical(attempt_record(attempt=bound))),
            *("--finding-json", _finding(merged=merged, run_id=run_id), "--principal", OWNER),
        )
        == "incident-reopen-not-eligible"
    )
    # The leaf can fail ninety seconds after the merge, with no ledger write yet. The
    # observer reverts on its retained arm alone, and the record is still possible after.
    revert = walk.leaf_failure(merged=merged, run_id=run_id, principal=principal)
    assert walk.git("rev-parse", "origin/master") == revert
    # Collection authenticates the merge against the chain, so it names the missing record.
    _ = walk.git("fetch", "-q", "origin")
    code, reply = walk.entrance(*_collect_args(revert=revert, tmp_path=tmp_path))
    assert (code, reply["code"]) == (78, "incident-authority-identity-mismatch"), reply
    recorded = walk.act("record-merge", bound)
    assert (recorded.phase, recorded.generation) == ("master-observation", 4)
    assert recorded.landed_commits == (merged,)
    assert recorded.head == bound.head != merged
    # An exact retry recovers the recorded generation and writes nothing.
    assert (
        walk.process(["record-merge", "--repo", str(walk.root), *_flags(bound)])[1]["result"][
            "recovered"
        ]
        is True
    )
    assert walk.head() == recorded
    return recorded, merged, run_id, arm_id


def _collect_and_correct(
    walk: _Walk,
    *,
    collecting: IncidentAttempt,
    merged: str,
    run_id: int,
    revert: str,
    tmp_path: Path,
) -> IncidentAttempt:
    collect = _collect_args(revert=revert, tmp_path=tmp_path)
    code, reply = walk.entrance(*collect)
    assert (code, reply["code"]) == (78, "incident-original-run-in-progress"), reply
    walk.forge.publish_run(
        run_id=run_id,
        head=merged,
        status="completed",
        jobs=[
            {
                "id": 1,
                "name": "check-lint",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://forge.invalid/job/1",
            },
            {
                "id": 2,
                "name": LEAF,
                "status": "completed",
                "conclusion": "failure",
                "html_url": "https://forge.invalid/job/2",
            },
        ],
    )
    code, reply = walk.entrance(*collect)
    assert (code, reply["status"]) == (0, "collected"), reply
    digest = reply["evidence_digest"]
    # The operator stages the fix on the revert, then proposes before committing it.
    base = walk.git("rev-parse", "origin/master")
    assert base == revert
    _ = walk.git("checkout", "-q", "-b", "incident/test-incident-attempt-2", base)
    tree = walk.write_marked("attempt 2")
    code, reply = walk.entrance(
        "propose-correction",
        *("--evidence-digest", digest, "--next-head-sha", base, "--staged-tree", tree),
        *("--target-ref", "refs/heads/incident/test-incident-attempt-2"),
        *("--current-attempt", collecting.attempt_id, "--current-owner", collecting.owner),
        *("--current-generation", str(collecting.generation)),
    )
    assert (code, reply["status"]) == (0, "proposed"), reply
    corrected = walk.head()
    assert (corrected.phase, corrected.head, corrected.base) == ("repair", base, base)
    assert corrected.carrier is not None
    assert corrected.carrier.staged_tree == tree
    assert corrected.attempt_id == reply["receipt"]
    return corrected


def _attempt_two(
    walk: _Walk, *, corrected: IncidentAttempt, arm_id: str
) -> tuple[IncidentAttempt, str, str]:
    """The corrected attempt merges green, enters repayment, and owes one repayment."""
    bound = walk.publish(corrected, number=102)
    second_arm = walk.arm(bound, expected=arm_id)
    merged, run_id = walk.merge(bound)
    recorded = walk.act("record-merge", bound)
    assert recorded.landed_commits == (merged,)
    walk.forge.runs[str(run_id)] = {"headSha": merged, "status": "in_progress", "conclusion": ""}
    feat = ("--target-ref", f"refs/heads/feat/{ITEM}")
    assert walk.refused("enter-repayment", recorded, "--master-run", str(run_id), *feat) == (
        "incident-repayment-master-ci-outstanding"
    )
    walk.forge.runs[str(run_id)] = {
        "headSha": merged,
        "status": "completed",
        "conclusion": "success",
    }
    admission = walk.act("enter-repayment", recorded, "--master-run", str(run_id), *feat)
    assert (admission.phase, admission.owner) == ("repayment-admission", "fabro")
    assert walk.client.show_issue(issue_id=ITEM)["status"] == "pending-approval"
    return admission, merged, second_arm


def _attempt_three(
    walk: _Walk, *, collecting: IncidentAttempt, arm_id: str, revert: str
) -> IncidentAttempt:
    """`correct-attempt` directly: no failed master run, so nothing to collect.

    Its first PR fails a retained fast check and is closed unmerged, so the
    corrected attempt that merges comes from `correct-unmerged-attempt`.
    """
    _ = walk.git("checkout", "-q", "-b", "incident/test-incident-attempt-3", revert)
    tree = walk.write_marked("attempt 3")
    corrected = walk.act(
        "correct-attempt",
        collecting,
        "--correction-json",
        _canonical(
            {
                "base": revert,
                "evidence_id": "probe-pr-test",
                "head": revert,
                "kind": "repair",
                "staged_tree": tree,
            }
        ),
        *("--target-ref", "refs/heads/incident/test-incident-attempt-3"),
    )
    failed = walk.publish(corrected, number=106)
    failed_arm = walk.arm(failed, expected=arm_id)
    bound, arm_id = _unmerged_correction(walk, failed=failed, arm_id=failed_arm, revert=revert)
    _ = walk.arm(bound, expected=arm_id)
    merged, run_id = walk.merge(bound)
    recorded = walk.act("record-merge", bound)
    walk.forge.runs[str(run_id)] = {
        "headSha": merged,
        "status": "completed",
        "conclusion": "success",
    }
    master = ("--master-run", str(run_id))
    # The repayment carrier needs its own ref: the expedited branch cannot be reserved again.
    expedited = ("--target-ref", "refs/heads/incident/test-incident-attempt-4")
    assert walk.refused("enter-repayment", recorded, *master, *expedited) == (
        "incident-transition-invalid-successor"
    )
    return walk.act("enter-repayment", recorded, *master, "--target-ref", f"refs/heads/feat/{ITEM}")


def _unmerged_correction(
    walk: _Walk, *, failed: IncidentAttempt, arm_id: str, revert: str
) -> tuple[IncidentAttempt, str]:
    """PR 106 fails a retained fast check on its head and is closed; attempt 4 corrects it."""
    carrier = failed.carrier
    assert carrier is not None
    branch = carrier.target_ref.removeprefix("refs/heads/")
    walk.forge.runs["8801"] = {
        "headSha": failed.head,
        "status": "completed",
        "conclusion": "failure",
    }
    walk.forge.prs["106"] = {
        "number": 106,
        "state": "OPEN",
        "headRefName": branch,
        "headRefOid": failed.head,
    }
    _ = walk.git("checkout", "-q", "-b", "incident/test-incident-attempt-4", revert)
    tree = walk.write_marked("attempt 4")
    correction = (
        "--correction-json",
        _canonical(
            {
                "base": revert,
                "evidence_id": "split-the-lloc-overflow",
                "head": revert,
                "kind": "repair",
                "staged_tree": tree,
            }
        ),
        *("--target-ref", "refs/heads/incident/test-incident-attempt-4"),
    )
    # An open PR is no unmerged failure: nothing is recorded until the forge says closed.
    assert walk.refused(
        "correct-unmerged-attempt", failed, "--failed-run", "8801", *correction
    ) == ("incident-correction-pr-not-closed-unmerged")
    walk.forge.prs["106"]["state"] = "CLOSED"
    corrected = walk.act("correct-unmerged-attempt", failed, "--failed-run", "8801", *correction)
    assert (corrected.phase, corrected.pr_number, corrected.base) == ("repair", 0, revert)
    assert corrected.attempt_id != failed.attempt_id
    history = read_incident_standing(client=walk.client, item_id=ITEM).history
    assert history[-2] == failed, "the failed bound carrier stays in the history as recorded"
    return walk.publish(corrected, number=103), arm_id


def _repayment(walk: _Walk, admission: IncidentAttempt) -> IncidentAttempt:
    """HAND: ordinary admission and the factory claim, then the hand advance verbs and the bind."""
    client = walk.client
    client.update_issue(issue_id=ITEM, status="ready")
    ready = walk.act(
        "advance-repayment", admission, "--to-phase", "repayment-ready", "--admission-complete"
    )
    stamp = ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host="hp",
        run_id="run-1",
        factory_name="petri",
        factory_server="http://petri",
    )
    client.update_issue(
        issue_id=ITEM, status="active", assignee="fabro", metadata=claim_stamp_metadata(stamp=stamp)
    )
    active = walk.act("advance-repayment", ready, "--to-phase", "repayment-active")
    # The factory run publishes `feat/<item>`, and only that branch's PR binds.
    _ = walk.git("checkout", "-q", "-b", f"feat/{ITEM}", "origin/master")
    _ = (walk.root / APP).write_text("VALUE = 'repaid'\n")
    _ = walk.git("commit", "-q", "-am", "fix: repay the incident")
    head = walk.git("rev-parse", "HEAD")
    _ = walk.git("push", "-q", "origin", f"HEAD:refs/heads/feat/{ITEM}")
    _ = walk.git("push", "-q", "origin", "HEAD:refs/heads/master")
    _ = walk.git("fetch", "-q", "origin")
    walk.forge.prs["104"] = {
        "number": 104,
        "state": "MERGED",
        "headRefName": "other-branch",
        "headRefOid": head,
        "mergeCommit": {"oid": head},
        "commits": [{"messageHeadline": "fix: repay the incident"}],
    }
    client.update_issue(issue_id=ITEM, status="acceptance")
    assert (
        walk.refused("bind-repayment-acceptance", active, "--pr", "104")
        == "incident-repayment-carrier-mismatch"
    )
    walk.forge.prs["104"]["headRefName"] = f"feat/{ITEM}"
    return walk.act("bind-repayment-acceptance", active, "--pr", "104")


def _close(walk: _Walk, acceptance: IncidentAttempt) -> IncidentAttempt:
    """HAND: `complete-incident`, with the operator's attestation, on the repayment's green run."""
    walk.forge.runs["9999"] = {
        "headSha": acceptance.landed_commits[-1],
        "status": "completed",
        "conclusion": "success",
    }
    standing = read_incident_standing(client=walk.client, item_id=ITEM)
    attestation = _canonical(
        {
            "manual_outcome": True,
            "repaid_debt": list(acceptance.deferred_work),
            "undisposed_failures": [],
            "validated_paths": list(acceptance.original_paths),
        }
    )
    assert standing.history[-1] == acceptance
    return walk.act(
        "complete-incident", acceptance, "--master-run", "9999", "--completion-json", attestation
    )


def _assert_every_expedited_carrier_keeps_its_receipt(walk: _Walk) -> None:
    """The bypass audit's own match, over the chain as it really ends up."""
    history = read_incident_standing(client=walk.client, item_id=ITEM).history
    receipts = receipts_from_history(history=history)
    for number in (101, 102, 103):
        carrier = next(
            attempt
            for attempt in history
            if attempt.pr_number == number and attempt.phase == "master-observation"
        )
        receipt = matching_incident_receipt(
            receipts=receipts,
            repository=REPOSITORY,
            pr_number=number,
            head_sha=carrier.head,
            landed_commits=carrier.landed_commits,
        )
        assert receipt is not None, number


def _regression_and_attempt_three(
    walk: _Walk,
    *,
    principal: _Principal,
    admission: IncidentAttempt,
    second_merge: str,
    second_arm: str,
) -> IncidentAttempt:
    # A regression another pull request's CI demonstrated supersedes that repayment.
    attributed = next(
        attempt
        for attempt in read_incident_standing(client=walk.client, item_id=ITEM).history
        if attempt.landed_commits == (second_merge,) and attempt.phase == "master-observation"
    )
    regression = _reopen(
        walk,
        current=admission,
        attributed=attributed,
        finding=_finding(merged=second_merge, run_id=7777, surface="pull-request"),
    )
    assert regression.phase == "reverting"
    assert walk.client.show_issue(issue_id=ITEM)["status"] == "active"
    assert (
        walk.refused(
            "advance-repayment", admission, "--to-phase", "repayment-ready", "--admission-complete"
        )
        == "incident-repayment-stale-observation"
    )
    recovered = walk.recover(regression, principal=principal)
    assert recovered["status"] == "completed", recovered
    second_revert = principal.published[-1]
    assert walk.git("rev-parse", "origin/master") == second_revert
    collecting = _revert_receipt(walk, regression, revert=second_revert)
    final = _attempt_three(walk, collecting=collecting, arm_id=second_arm, revert=second_revert)
    assert (final.phase, final.owner) == ("repayment-admission", "fabro")
    return final


def test_one_incident_walks_every_attempt_and_its_repayment_on_the_real_chain(
    walk: _Walk, tmp_path: Path
) -> None:
    principal = _Principal(walk=walk)
    recorded, merged, run_id, arm_id = _attempt_one(walk, principal, tmp_path)
    revert = principal.published[-1]
    # The first failure reaches a corrected attempt: the merged attempt reopens.
    reverting = _reopen(
        walk, current=recorded, attributed=recorded, finding=_finding(merged=merged, run_id=run_id)
    )
    assert (reverting.phase, reverting.generation, reverting.owner) == ("reverting", 5, OWNER)
    assert reverting.landed_commits == (merged,)
    # The leaf failure and this reopen share one immutable action: no second revert.
    assert walk.recover(reverting, principal=principal)["reason"] == (
        "existing immutable action; no duplicate effect"
    )
    assert principal.published == [revert]
    collecting = _revert_receipt(walk, reverting, revert=revert)
    corrected = _collect_and_correct(
        walk, collecting=collecting, merged=merged, run_id=run_id, revert=revert, tmp_path=tmp_path
    )
    admission, second_merge, second_arm = _attempt_two(walk, corrected=corrected, arm_id=arm_id)
    final = _regression_and_attempt_three(
        walk,
        principal=principal,
        admission=admission,
        second_merge=second_merge,
        second_arm=second_arm,
    )
    acceptance = _repayment(walk, final)
    assert acceptance.phase == "repayment-acceptance"
    assert acceptance.carrier is not None
    assert acceptance.carrier.target_ref == f"refs/heads/feat/{ITEM}"
    closed = _close(walk, acceptance)
    assert (closed.phase, closed.pr_number) == ("closed", 104)
    assert read_incident_standing(client=walk.client, item_id=ITEM).outstanding == ()
    _assert_every_expedited_carrier_keeps_its_receipt(walk)
    phases = [
        attempt.phase
        for attempt in read_incident_standing(client=walk.client, item_id=ITEM).history
    ]
    assert phases == [
        *("repair", "repair", "repair", "master-observation", "reverting", "collecting-failures"),
        *("repair", "repair", "repair", "master-observation", "repayment-admission", "reverting"),
        *("collecting-failures", "repair", "repair", "repair"),
        *("repair", "repair", "repair", "master-observation"),
        *("repayment-admission", "repayment-ready", "repayment-active", "repayment-acceptance"),
        "closed",
    ]
