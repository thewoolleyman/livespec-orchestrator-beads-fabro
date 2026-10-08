"""`reconcile-merged` for a HOST-ONLY item whose merge names no factory run.

`SPECIFICATION/contracts.md`'s host-captured leg (v115) says the acceptance pass
judges a `host_captured` assertion passing "only from a `host_verified` record,
on the pull request of the latest merged run for the item, that lists the
assertion as reproduced and names a build identity containing the merged change",
and that "the pass MUST verify that containment itself". Its pointer clause makes
the Dispatcher write the Proof of Done pointer after merge. NOTHING in either
clause makes the FACTORY run identifier a precondition of the host leg — a host
replay is published by a session on an operator host and carries a session
identity where a factory record carries a run id.

THE LIVE INCIDENT THIS BINDS. `livespec-orchestrator-git-jsonl` item
`bd-gj-k4d6j3` merged as pull request 878, carried a `host_recorded` capture and
an independent `host_verified` replay that genuinely reproduced all three of its
assertions against the released build, and still rested in `acceptance` with its
journal reporting "merging run id unavailable", containment "could not be read",
and `proof-pointer-skipped` because there was "no verified record for the merging
run". Two host-only defects produced that: `read_proof_leg` returned on the
empty-identifier arm WITHOUT supplying a containment reader, so every replay
refused as unobservable-containment; and the pointer write required
`proof.record` — the FACTORY record — so a valid host-only proof wrote no pointer
and the `accept` valve then refused the item for having none.

WHY THE FACTORY ATTRIBUTION STAYS FAIL-CLOSED IN EVERY CASE HERE. The pull
request carries a `verified` record stamped with a run identifier the journal
names for NO dispatch of this item, which is the incident's own shape. It must
never be attributed, and it must never be promoted into the pointer: a record
from an unidentifiable dispatch describes another tree. It is the control that
makes "the pointer cites the host record" evidence of the host-only path rather
than of a reader that cites whatever `verified` comment it finds.

EVERYTHING BUT TWO SOCKETS IS PRODUCTION CODE. The real
`dispatcher.main(argv=["reconcile-merged", ...])` supervisor runs over the real
store/client seam against the in-memory `FakeBeadsClient`, writes a real on-disk
journal, and resolves the merging dispatch's identifiers out of that journal
through the real reader. Only the two seams that leave the process are stood in:
the valve's own shell `CommandRunner`, and the acceptance pass's, which answers
the comments read AND the containment comparison.

THE JOURNAL IS PRESENT AND NAMES ANOTHER ITEM. An ABSENT journal would make the
empty identifier set an artefact of a missing file, so a reader that had kept
working would look broken for the wrong reason. A readable journal naming a
sibling dispatch poses the real question: the file was read, and it names no
dispatch of THIS item.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    AcceptancePassResult,
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BUILD_IDENTITY_HEADING,
    INSTALLED_BUILD_LABEL,
    RELEASE_TAG_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_containment import compare_argv
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import (
    NOT_EVIDENCE_SELF_REPLAY,
    NOT_EVIDENCE_UNOBSERVABLE_CONTAINMENT,
    PENDING_HOST_LEG_REASON,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HOST_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_proof import (
    stale_proof_pointer_items,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-hostonlymerge"
_SIBLING_ITEM_ID = "bd-ib-anotheritem"
_PR_NUMBER = 878
_MERGE_SHA = "de291101ac8d441fa3dd49fee3d55eb966a8aacd"
# The dispatch the journal DOES name, for an item that is not this one. It is what
# makes the empty accepted set a measurement rather than a missing file.
_SIBLING_DISPATCH_ID = "aaaa1111bbbb2222cccc3333dddd4444"
# The identifier the pull request's `verified` record is stamped with. The journal
# names it for no dispatch of this item, so it must never be attributed.
_UNATTRIBUTED_RUN_ID = "01M4UNATTRIBUTEDRUN"
_CAPTURING_SESSION = "01a0f0d2-8ae8-7ec3-9c29-5ff9bef058f2"
_REPLAYING_SESSION = "724787ab-cfc0-4dc6-9123-1c706769c5ab"
# A THIRD session, which publishes the corrected replay the stale lane must see.
_CORRECTING_SESSION = "9f2c1d40-0b77-4c8e-9a51-2d6c5b7a1e33"
_RELEASE_TAG = "v0.173.8"
_ASSERTION = "Reconciliation closes a host-only item whose merge names no factory run."
_HOST_REASON = "the proof needs the released build installed on an operator host."
_VERIFIED_URL = f"https://example.test/owner/repo/pull/{_PR_NUMBER}#issuecomment-6048000000"
_CAPTURE_URL = f"https://example.test/owner/repo/pull/{_PR_NUMBER}#issuecomment-6048738746"
_REPLAY_URL = f"https://example.test/owner/repo/pull/{_PR_NUMBER}#issuecomment-6048809393"
_REPLAY_TIMESTAMP = "2026-10-07T23:18:22Z"
_CORRECTED_URL = f"https://example.test/owner/repo/pull/{_PR_NUMBER}#issuecomment-6049000000"
_PARKING_TITLE = "Acceptance parking record"
# Shares no significant term with the assertion, so a PASS cannot have come from
# the merged-diff vocabulary matcher.
_MERGED_DIFF = "diff --git a/x b/x\n+rearranged an unrelated helper\n"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> object:
    """Resolve the store onto the in-memory fake, fresh per case.

    `$HOME` is scrubbed with it, for the reason the sibling reconcile module
    records: the janitor checkout path resolves under `Path.home()/.worktrees`,
    and this arm must not be able to touch the real one if that ever breaks.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _ValveRunner:
    """The valve's own shell seam: a queue, and the full call list it consumed."""

    queue: list[CommandResult]
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _ForgeRunner:
    """The pass's seam: the comments read, the containment comparison, the diff.

    The comparison is answered EXPLICITLY rather than falling through to the diff
    payload, which parses as an unknown status and refuses. A seam that left it
    unstubbed would refuse every replay for a reason the case never posed, and the
    refusal would be indistinguishable from the defect under repair.
    """

    comments: str
    status: str = "ahead"
    compare_exit_code: int = 0
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        if any("compare" in one for one in argv):
            return CommandResult(
                exit_code=self.compare_exit_code, stdout=f"{self.status}\n", stderr=""
            )
        if "comments" in argv:
            return CommandResult(exit_code=0, stdout=self.comments, stderr="")
        return CommandResult(exit_code=0, stdout=_MERGED_DIFF, stderr="")


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _definition_of_done() -> str:
    """A HOST-ONLY section: every bullet sits under the `Host-captured` heading.

    Assembled by concatenation rather than through `textwrap.dedent`, for the
    reason the sibling host-leg module records: a multi-line interpolation into an
    indented template leaves every heading indented, and an indented
    `## Definition of Done` is not a heading at all — so the item would read as
    carrying no section and the case would pass on the wrong refusal.
    """
    return (
        "Repair the host-only proof attribution.\n"
        "\n"
        "## Definition of Done\n"
        "\n"
        "References: ## Effective acceptance criteria\n"
        "\n"
        "### Host-captured\n"
        "\n"
        f"Reason: {_HOST_REASON}\n"
        "\n"
        f"- {_ASSERTION}\n"
    )


def _item(*, acceptance_policy: str = "ai-only") -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="acceptance",
        title="A merged host-only slice whose merge names no factory run",
        description=_definition_of_done(),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        # `ai-only` is the discriminating policy for every case about RESTING: it
        # is the one policy that CLOSES a passing item, so an item that rests under
        # it rests because of its host leg and not because a human was owed the
        # acceptance. The hygiene case overrides it to a parked policy instead, so
        # the item keeps the pointer in a status the lane still reads.
        acceptance_policy=acceptance_policy,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        (
            '{"livespec-orchestrator-beads-fabro": {'
            '"connection": {"prefix": "bd-ib"}, '
            '"compat": {"pinned": "master"}'
            "}}"
        ),
        encoding="utf-8",
    )
    journal = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    _ = journal.write_text(
        json.dumps(
            {
                "stage": "dispatch-id",
                "work_item_id": _SIBLING_ITEM_ID,
                "dispatch_id": _SIBLING_DISPATCH_ID,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return repo


def _verified_record_body() -> str:
    """The factory `verified` record, stamped with an UNATTRIBUTABLE run id.

    It lists the host assertion under a heading stating it is pending the host
    leg, which is the shape the record clause requires of a `verified` record on
    an item carrying one — and which is what a host-only item's factory proof
    stages publish, since they grade no assertion of their own.
    """
    return (
        f"Proof of Done — verified — run {_UNATTRIBUTED_RUN_ID} — 2026-10-07T21:00:00Z\n"
        "\n"
        "## Pending the host leg\n"
        "\n"
        f"- {_ASSERTION}\n"
    )


def _host_record_body(
    *,
    verdict: str,
    identity: str,
    timestamp: str,
    reproduced: str | None = None,
    release_tag: str = _RELEASE_TAG,
) -> str:
    """One host-leg record, in the header and build-identity shape v115 fixes.

    The third header field is `session <identity>`: a host record is published by
    an agent SESSION on an operator host and no Fabro run exists for it.
    `reproduced` is optional because a `host_recorded` capture claims no
    reproduction verdict — it is the first leg, with nothing yet to reproduce.
    """
    verdict_line = "" if reproduced is None else f"Reproduced: {reproduced}\n"
    return (
        f"Proof of Done — {verdict} — session {identity} — {timestamp}\n"
        "\n"
        f"## {BUILD_IDENTITY_HEADING}\n"
        "\n"
        f"- {RELEASE_TAG_LABEL}: {release_tag}\n"
        f"- {INSTALLED_BUILD_LABEL}: livespec-orchestrator-beads-fabro {release_tag}\n"
        "\n"
        f"## Assertion 1 — {_ASSERTION}\n"
        "\n"
        "Proof mode: `host_captured`\n"
        "\n"
        f"{verdict_line}"
    )


def _comments_payload(*, replaying: str = _REPLAYING_SESSION) -> str:
    """The pull request as the incident left it: verified, then capture, then replay."""
    return json.dumps(
        {
            "comments": [
                {"url": _VERIFIED_URL, "body": _verified_record_body()},
                {
                    "url": _CAPTURE_URL,
                    "body": _host_record_body(
                        verdict="host_recorded",
                        identity=_CAPTURING_SESSION,
                        timestamp="2026-10-07T23:10:00Z",
                    ),
                },
                {
                    "url": _REPLAY_URL,
                    "body": _host_record_body(
                        verdict="host_verified",
                        identity=replaying,
                        timestamp=_REPLAY_TIMESTAMP,
                        reproduced="yes.",
                    ),
                },
            ]
        }
    )


def _corrected_replay_payload() -> str:
    """The same pull request, plus a LATER `host_verified` replay from a third party.

    The shape a correction takes: a record is never edited after posting, so a
    replay that supersedes an earlier one is a new comment — and a pointer naming
    the superseded record is then genuinely stale.
    """
    payload = json.loads(_comments_payload())
    comments = payload["comments"]
    assert isinstance(comments, list)
    comments.append(
        {
            "url": _CORRECTED_URL,
            "body": _host_record_body(
                verdict="host_verified",
                identity=_CORRECTING_SESSION,
                timestamp="2026-10-08T07:00:00Z",
                reproduced="yes.",
            ),
        }
    )
    return json.dumps(payload)


def _pr_view_json() -> str:
    return json.dumps(
        {
            "number": _PR_NUMBER,
            "state": "MERGED",
            "autoMergeRequest": {},
            "mergeStateStatus": "CLEAN",
            "mergeCommit": {"oid": _MERGE_SHA},
            "statusCheckRollup": [],
        }
    )


def _merged_queue() -> list[CommandResult]:
    """The plan build's default-branch probe, then the merged-PR view."""
    return [
        CommandResult(exit_code=0, stdout="origin/master", stderr=""),
        CommandResult(exit_code=0, stdout=_pr_view_json(), stderr=""),
    ]


def _reconcile(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    comments: str | None = None,
    status: str = "ahead",
    compare_exit_code: int = 0,
    acceptance_policy: str = "ai-only",
) -> tuple[int, Path, _ForgeRunner]:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(acceptance_policy=acceptance_policy))
    valve = _ValveRunner(queue=_merged_queue())
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged.ShellCommandRunner",
        lambda: valve,
    )
    forge = _ForgeRunner(
        comments=_comments_payload() if comments is None else comments,
        status=status,
        compare_exit_code=compare_exit_code,
    )

    def _call(
        *,
        repo: Path,
        item: WorkItem,
        outcome: DispatchOutcome,
        raw_labels: Sequence[str] = (),
        journal_path: Path | None = None,
    ) -> AcceptancePassResult:
        return run_acceptance_pass(
            repo=repo,
            item=item,
            outcome=outcome,
            runner=forge,
            raw_labels=raw_labels,
            journal_path=journal_path,
        )

    monkeypatch.setattr(_dispatcher_completion, "run_acceptance_pass", _call, raising=False)

    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", _ITEM_ID, "--json"])
    return exit_code, repo, forge


def _stored() -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _comment_bodies(*, item_id: str) -> list[str]:
    """The item's ledger comments, read through `bd comments` and indexed on `text`.

    Never through `bd show`, which carries only `comment_count` and no bodies at
    all — so a read through it reports every successful append as lost.
    """
    return [one.text for one in read_work_item_comments(path=_config(), work_item_id=item_id)]


def _acceptance_pass_record(*, repo: Path) -> dict[str, object]:
    return next(
        one for one in _journal_records(repo=repo) if one.get("stage") == "acceptance-ai-pass"
    )


def test_a_host_only_item_closes_when_its_merge_names_no_factory_run_identifier(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The incident's own shape, reconciled: the item closes on its host proof.

    THE CONTAINMENT COMPARISON IS READ OFF THE SEAM, not inferred from the close.
    A replay refused for unobservable containment and a replay nothing was ever
    compared against produce the SAME refusal string, so "the item rests" could
    never have told the two apart — and a gauge that was never pointed at a build
    is exactly what the defect was. Asserting the forge was asked about the named
    release, with the merge commit as the base, is what makes the close evidence of
    a measurement the pass actually took.

    The host check's own reason carries the other half of the clause: the record,
    the PARTY that published it — which must be the replaying session and not the
    capturing one — and the build it was taken against.
    """
    exit_code, repo, forge = _reconcile(monkeypatch=monkeypatch, tmp_path=tmp_path)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload[0]["status"] == "green"
    assert payload[0]["stage"] == "done"
    assert payload[0]["verdict"] == "PASS"
    assert _stored().status == "done"
    assert compare_argv(base=_MERGE_SHA, head=_RELEASE_TAG) in forge.argvs
    record = _acceptance_pass_record(repo=repo)
    proof = record["proof"]
    assert isinstance(proof, dict)
    assert proof["pending_host_captured"] == []
    # The factory leg stayed fail-closed: the `verified` record on the pull request
    # belongs to a dispatch the journal names for no dispatch of this item.
    assert proof["record_comment"] is None
    assert proof["reason"] == "merging run id unavailable"
    criteria = record["criteria"]
    assert isinstance(criteria, dict)
    checks = criteria["checks"]
    assert isinstance(checks, list)
    assert [one["passed"] for one in checks] == [True]
    reason = str(checks[0]["reason"])
    assert _REPLAY_URL in reason
    assert _REPLAYING_SESSION in reason
    assert _CAPTURING_SESSION not in reason
    assert _RELEASE_TAG in reason


def test_the_host_only_pointer_identifies_the_independently_verified_host_record(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The pointer cites the record the pass rested on, which here is the HOST one.

    The pointer write used to require `proof.record` — the FACTORY `verified`
    record — so a host-only item whose factory record was unattributable wrote no
    pointer at all, and the `accept` valve then refused the item for carrying
    none. That is the second half of the live incident, and it is a provenance
    loss rather than a verdict one: the item's own description ends up naming no
    evidence for the merge its acceptance was judged against.

    THE CITED BULLETS ARE ASSERTED AS A LIST, not by containment. A build that
    promoted the UNATTRIBUTABLE factory record instead would also leave a pointer
    section standing, and an `in`-containment check on the heading would pass for
    it — so the two records on this pull request are discriminated by which
    identifier, timestamp and verdict the section actually carries. The capture is
    excluded for the same reason in the other direction: a capture is not its own
    replay, and a pointer naming it would advertise one party's word as
    independent proof.

    The Definition of Done is compared BYTE FOR BYTE, because a build that
    rewrote the section while appending the pointer would satisfy a containment
    check just as well — and the clause requires the section preserved.
    """
    exit_code, repo, _ = _reconcile(monkeypatch=monkeypatch, tmp_path=tmp_path)

    _ = capsys.readouterr()
    assert exit_code == 0
    description = _stored().description
    head, _, pointer = description.partition("## Proof of Done")
    assert pointer != ""
    assert head.rstrip("\n") == _definition_of_done().rstrip("\n")
    assert pointer.splitlines()[1:] == [
        "",
        f"- Pull request: #{_PR_NUMBER}",
        f"- Verified record: {_REPLAY_URL}",
        f"- Run: {_REPLAYING_SESSION}",
        f"- Timestamp: {_REPLAY_TIMESTAMP}",
        "- Verdict: host_verified",
        f"- Host-verified record: {_REPLAY_URL}",
    ]
    # Neither the unattributable factory record nor the capture is cited.
    assert _VERIFIED_URL not in description
    assert _CAPTURE_URL not in description
    # The section carries the POINTER, never the proof.
    assert "Reproduced:" not in description
    written = next(
        one for one in _journal_records(repo=repo) if one.get("stage") == "proof-pointer"
    )
    assert written["run_id"] == _REPLAYING_SESSION
    assert written["record_comment"] == _REPLAY_URL
    assert written["host_verified_record"] == _REPLAY_URL


@pytest.mark.parametrize(
    ("comments", "compare_exit_code", "refusal"),
    [
        (None, 1, NOT_EVIDENCE_UNOBSERVABLE_CONTAINMENT),
        (_comments_payload(replaying=_CAPTURING_SESSION), 0, NOT_EVIDENCE_SELF_REPLAY),
    ],
    ids=["unreadable-containment", "capturing-identity"],
)
def test_a_refused_host_replay_rests_the_item_with_its_own_pending_evidence_reason(
    comments: str | None,
    compare_exit_code: int,
    refusal: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The two ways the repaired host-only path must still REFUSE, under `ai-only`.

    Both are preservation cases, and both are worth binding on the host-only path
    specifically: wiring the containment reader onto the empty-identifier arm is
    exactly the change that could have turned either refusal into a close, and
    under `ai-only` a close is what an over-permissive host leg would produce
    silently.

    The item rests rather than closing, the pass consumes no rework attempt (the
    verdict is PASS — the factory leg is green and the host assertion is PENDING,
    not failed), NO pointer is written because the leg rested on nothing, and the
    parking record names the SPECIFIC refusal. The reason is the whole content of
    the park: an operator told only "pending" would re-run the replay and meet the
    same answer, while "names a build whose containment could not be read" and
    "was published by the identity that recorded the capture" have entirely
    different remedies.

    Both legs also assert the comparison was ATTEMPTED, for the reason the closing
    case does: a refusal earned by a failed measurement and one manufactured by a
    gauge nobody pointed produce the identical string, and only the seam tells them
    apart.

    THE REASON IS ASSERTED ON BOTH SURFACES THAT CARRY IT, because they are two
    different readers' answers and neither is recoverable from the other. The
    acceptance journal carries the per-assertion CHECK reason — the standing
    "passes only from an independent host_verified record" clause, extended with
    every refusal — and the ledger's parking record carries the refusal leading the
    ACTION, which is what an operator reads to know whether to republish or to
    start. A build that dropped either would still look repaired through the other.
    """
    exit_code, repo, forge = _reconcile(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        comments=comments,
        compare_exit_code=compare_exit_code,
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload[0]["stage"] == "acceptance"
    assert payload[0]["verdict"] == "PASS"
    assert _stored().status == "acceptance"
    assert compare_argv(base=_MERGE_SHA, head=_RELEASE_TAG) in forge.argvs
    record = _acceptance_pass_record(repo=repo)
    proof = record["proof"]
    assert isinstance(proof, dict)
    assert proof["pending_host_captured"] == [_ASSERTION]
    criteria = record["criteria"]
    assert isinstance(criteria, dict)
    checks = criteria["checks"]
    assert isinstance(checks, list)
    reason = str(checks[0]["reason"])
    assert reason.startswith(PENDING_HOST_LEG_REASON)
    assert refusal in reason
    # Fail-closed provenance: a pointer is written only for a replay that PASSED,
    # so a refused one leaves the description naming no evidence at all.
    assert "## Proof of Done" not in _stored().description
    skipped = next(
        one for one in _journal_records(repo=repo) if one.get("stage") == "proof-pointer-skipped"
    )
    assert skipped["reason"] == "no verified Proof of Done record for the merging run"
    parking = [body for body in _comment_bodies(item_id=_ITEM_ID) if _PARKING_TITLE in body]
    assert len(parking) == 1
    assert refusal in parking[0]
    assert _ASSERTION in parking[0]
    # The refused record and the build it claimed are both named: the remedy
    # differs by which build was replayed, and an operator told only that the
    # record is not evidence has to open the comment to find out which.
    assert _REPLAY_URL in parking[0]
    assert _RELEASE_TAG in parking[0]


def test_a_host_only_pointer_is_not_stale_against_a_record_it_never_cited(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Staleness compares the pointer against the latest record OF ITS OWN KIND.

    A host-only pointer cites a `host_verified` record, and this pull request also
    carries the unattributable factory `verified` record the merge published. A
    lane that always compared against the latest `verified` record would report
    every host-only pointer as stale the moment it was written — a hygiene row
    against a pointer that is exactly right, and one no operator can clear, since
    the `verified` record it names is the one the pass is required NOT to cite.

    THE CONTROL IS IN THE SAME CASE, because "no fact appeared" is otherwise
    indistinguishable from a lane that reports nothing: a LATER `host_verified`
    replay from a third session — the shape a corrected replay takes, since a
    record is never edited and a correction is a new record — must still raise the
    fact. Both legs read the same pointer through the same lane and differ only in
    what the pull request carries.
    """
    exit_code, repo, _ = _reconcile(
        monkeypatch=monkeypatch, tmp_path=tmp_path, acceptance_policy="ai-then-human"
    )

    _ = capsys.readouterr()
    assert exit_code == 0
    # The lane only reads a pointer on a non-closed item, so the parked policy is
    # what keeps this case reachable at all.
    assert _stored().status == "acceptance"
    assert f"- Verdict: {VERDICT_HOST_VERIFIED}" in _stored().description
    items = list(materialize_work_items(records=read_work_items(path=_config())).values())

    unchanged = stale_proof_pointer_items(
        project_root=repo,
        repo="repo",
        items=items,
        runner=_ForgeRunner(comments=_comments_payload()),
    )
    corrected = stale_proof_pointer_items(
        project_root=repo,
        repo="repo",
        items=items,
        runner=_ForgeRunner(comments=_corrected_replay_payload()),
    )

    assert unchanged == []
    assert [one.id for one in corrected] == [f"hygiene:stale-proof-pointer:{_ITEM_ID}"]
