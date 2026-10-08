"""Tests for the posting primitive: the one route by which a host record is published.

The host-leg clause of `SPECIFICATION/contracts.md` (v115) requires that "the
implementation MUST provide one posting primitive that renders these records, so that
no session hand-formats one"; that the primitive "MUST compute the publishing identity
itself ... and MUST NOT accept it as a caller-supplied string"; that it "MUST refuse a
`host_verified` or `host_not_reproduced` post whose computed identity equals that of
the `host_recorded` record it replays"; and that "on publishing `host_verified` or
`host_not_reproduced`, it MUST drive `reconcile-merged --item <id>`".

WHAT THE CALLER SUPPLIES, AND WHAT IT CANNOT. The caller supplies only the evidence it
alone has: the build it exercised, and per assertion the steps it ran, the proof they
produced and whether they reproduced. Everything the clause makes a REQUIREMENT of the
record — the verdict word, the header shape, the identity, the timestamp, the target
pull request, and each assertion's declared proof MODE — is computed. A caller that
could supply the mode could publish a `factory_captured` assertion as a host one, and
a caller that could supply the identity could defeat the independence refusal with a
flag.

THE REFUSALS ARE ASSERTED ON THEIR TEXT, not only on the exit code. A refusal an
operator cannot act on is as expensive as no refusal: each one here names the record it
collided with and what would clear it.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    RELEASE_TAG_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_cli import (
    add_post_host_record_arguments,
    reconcile_for,
    reconcile_merged_for_item,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_post import (
    HOST_RECORD_STAGE,
    HOST_RECORD_SURFACE,
    NO_CAPTURE_REFUSAL,
    NO_IDENTITY_REFUSAL,
    SELF_REPLAY_REFUSAL,
    HostRecordPost,
    host_record_argv,
    run_post_host_record_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_budget import (
    FORGE_COMMENT_CEILING_BYTES,
    PROOF_RECORD_BUDGET_BYTES,
    measured_bytes,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HOST_NOT_REPRODUCED,
    VERDICT_HOST_RECORDED,
    VERDICT_HOST_VERIFIED,
    proof_records,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main as dispatcher_main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-postrec"
_PR_NUMBER = 42
_MERGE_SHA = "ac7ebb0f36026f9789997f93aaaabbbbccccdddd"
_RELEASE_TAG = "v0.166.0"
_SESSION = "01M44THISSESSION"
_OTHER_SESSION = "01M44OTHERSESSION"
_HOST_ASSERTION = "The released build resolves the host mode on an operator host."
_FACTORY_ASSERTION = "The dispatch result reports the parked verdict."
_DESCRIPTION = f"""Implement the slice.

## Definition of Done

- {_FACTORY_ASSERTION}

### Host-captured

Reason: the proof needs the released build installed on an operator host.

- {_HOST_ASSERTION}

References: ## Scenario 136 — A host-captured assertion holds the item in acceptance
"""


@dataclass(kw_only=True)
class _Runner:
    """A runner answering by argv SHAPE rather than by call order.

    Shape-keyed because the command's call sequence is not the subject of these tests
    and an order-keyed double would have to be re-sequenced for every refusal case —
    each of which stops at a different point. `calls` keeps the order for the few
    assertions that are about it.
    """

    comments: str
    comment_exit: int = 0
    comments_exit: int = 0
    merged: bool = True
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.calls.append(list(argv))
        joined = " ".join(argv)
        return self._answer(argv=argv, joined=joined)

    def _answer(self, *, argv: list[str], joined: str) -> CommandResult:
        """The shape ladder, split out so the ladder itself stays under the return cap."""
        # The default branch is resolved before the merge search, and the search PINS
        # `--base` to it: an unstubbed resolution reaches the forge as a literal
        # placeholder, the search returns no candidate, and the primitive refuses for
        # "no merged pull request" — a refusal manufactured by the double rather than
        # earned by the item.
        if "defaultBranchRef" in joined or "refs/remotes/origin/HEAD" in joined:
            return CommandResult(exit_code=0, stdout="master\n", stderr="")
        if "--json" in argv and "comments" in joined:
            return CommandResult(exit_code=self.comments_exit, stdout=self.comments, stderr="")
        if argv[:3] == ["gh", "pr", "comment"]:
            return CommandResult(exit_code=self.comment_exit, stdout="posted\n", stderr="")
        if argv[:3] == ["gh", "pr", "list"]:
            return CommandResult(exit_code=0, stdout=self._merged_search(), stderr="")
        return CommandResult(exit_code=1, stdout="", stderr="unstubbed")

    def _merged_search(self) -> str:
        """The merge search's payload: the item's merged pull request, or none at all."""
        if not self.merged:
            return "[]"
        return json.dumps(
            [
                {
                    "number": _PR_NUMBER,
                    "title": f"feat: {_ITEM_ID}",
                    "headRefName": f"feat/{_ITEM_ID}",
                    "baseRefName": "master",
                    "state": "MERGED",
                    "mergeCommit": {"oid": _MERGE_SHA},
                }
            ]
        )


def _comments(*, records: tuple[dict[str, str], ...] = ()) -> str:
    return json.dumps({"comments": list(records)})


def _capture_comment(*, identity: str) -> dict[str, str]:
    return {
        "url": f"https://example.test/c/{identity}",
        "body": (
            f"Proof of Done — {VERDICT_HOST_RECORDED} — session {identity} — t\n\n"
            f"- {RELEASE_TAG_LABEL}: {_RELEASE_TAG}\n\n"
            f"## Assertion 1 — {_HOST_ASSERTION}\n"
        ),
    }


def _record_file(*, path: Path, reproduced: bool | None = None) -> Path:
    payload: dict[str, object] = {
        "build": {
            "release_tag": _RELEASE_TAG,
            "installed_build": "livespec-orchestrator-beads-fabro 0.166.0",
        },
        "assertions": [
            {
                "text": _HOST_ASSERTION,
                "steps": ["Install the released build.", "Drive the valve."],
                "proof": "$ drive --action accept:x\nrefused\n",
                "reproduced": reproduced,
            }
        ],
    }
    target = path / "record.json"
    _ = target.write_text(json.dumps(payload), encoding="utf-8")
    return target


@pytest.fixture(autouse=True)
def _fake_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Reconciles:
    """Records every item the post drove `reconcile-merged` for.

    ONE recorder serves both kinds of case. The cases where a replay IS published
    exercise its body, so the cases that assert `driven == []` are asserting against an
    instrument demonstrated to record — not against a stub that nothing ever ran, which
    would satisfy an emptiness check vacuously.
    """

    driven: list[str] = field(default_factory=list)

    def drive(self, *, work_item_id: str) -> int:
        self.driven.append(work_item_id)
        return 0


def _config() -> StoreConfig:
    """The hermetic tenant descriptor, matching what the committed config resolves to."""
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _govern(*, repo: Path) -> None:
    """The minimum committed configuration a governed repository carries.

    The primitive reads the ledger and resolves the dispatch target's contract through
    the production config path, so a bare temporary directory is refused before any of
    the behaviour under test runs. Writing the real file keeps the refusal ladder these
    tests assert about the RECORD rather than about the fixture.
    """
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}, '
        '"compat": {"pinned": "master"}}}',
        encoding="utf-8",
    )


def _work_item(*, description: str, title: str) -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="acceptance",
        title=title,
        description=description,
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-04T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _file_item(*, repo: Path) -> None:
    _govern(repo=repo)
    append_work_item(
        path=_config(),
        item=_work_item(description=_DESCRIPTION, title="A host-captured slice"),
    )


def _post(
    *,
    repo: Path,
    verdict: str,
    runner: _Runner,
    env: dict[str, str],
    reproduced: bool | None = None,
    reconciles: _Reconciles | None = None,
) -> tuple[int, str]:
    """Drive the command and return its exit code with the emitted stdout."""
    emitted: list[str] = []
    recorder = reconciles if reconciles is not None else _Reconciles()
    return (
        run_post_host_record_command(
            post=HostRecordPost(
                repo=repo,
                work_item_id=_ITEM_ID,
                verdict=verdict,
                record_path=_record_file(path=repo, reproduced=reproduced),
            ),
            runner=runner,
            env=env,
            emit=emitted.append,
            reconcile=recorder.drive,
        ),
        "".join(emitted),
    )


def test_a_host_recorded_post_renders_the_ratified_record_and_computes_the_identity(
    tmp_path: Path,
) -> None:
    """The capture leg: the body is rendered, the identity computed, the record posted.

    The posted body is re-parsed through the production reader, which is the only
    check that the primitive published something the acceptance pass can read — a
    body assertion alone would pass against a record the pass treats as prose.
    """
    _file_item(repo=tmp_path)
    runner = _Runner(comments=_comments())

    exit_code, emitted = _post(
        repo=tmp_path,
        verdict=VERDICT_HOST_RECORDED,
        runner=runner,
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
    )

    assert exit_code == 0
    posted = [call for call in runner.calls if call[:3] == ["gh", "pr", "comment"]]
    assert len(posted) == 1
    body_file = Path(posted[0][-1])
    assert posted[0] == host_record_argv(pr_number=_PR_NUMBER, body_file=body_file)
    body = body_file.read_text(encoding="utf-8")
    records = proof_records(comments=[{"body": body, "url": "u"}])
    assert len(records) == 1
    assert records[0].verdict == VERDICT_HOST_RECORDED
    assert records[0].run_id == _SESSION
    assert _RELEASE_TAG in body
    # The MODE is computed from the item's Definition of Done, never supplied.
    assert "host_captured" in body
    assert body in emitted


def test_the_capture_record_claims_no_reproduction_and_the_replay_claims_one(
    tmp_path: Path,
) -> None:
    """A capture is not its own replay, so its record carries no reproduction verdict."""
    _file_item(repo=tmp_path)
    capture_runner = _Runner(comments=_comments())
    _ = _post(
        repo=tmp_path,
        verdict=VERDICT_HOST_RECORDED,
        runner=capture_runner,
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        reproduced=True,
    )
    captured = Path(
        next(c for c in capture_runner.calls if c[:3] == ["gh", "pr", "comment"])[-1]
    ).read_text(encoding="utf-8")

    replay_runner = _Runner(comments=_comments(records=(_capture_comment(identity=_SESSION),)))
    _ = _post(
        repo=tmp_path,
        verdict=VERDICT_HOST_VERIFIED,
        runner=replay_runner,
        env={"CLAUDE_CODE_SESSION_ID": _OTHER_SESSION},
        reproduced=True,
    )
    replayed = Path(
        next(c for c in replay_runner.calls if c[:3] == ["gh", "pr", "comment"])[-1]
    ).read_text(encoding="utf-8")

    assert (
        proof_records(comments=[{"body": captured, "url": "u"}])[0].reproduced(
            assertion=_HOST_ASSERTION
        )
        is None
    )
    assert (
        proof_records(comments=[{"body": replayed, "url": "u"}])[0].reproduced(
            assertion=_HOST_ASSERTION
        )
        is True
    )


def test_a_replay_from_the_recording_identity_is_refused_before_anything_is_posted(
    tmp_path: Path,
) -> None:
    """The independence refusal, and it refuses BEFORE the post.

    Refusing after posting would leave the very record the clause calls not evidence
    permanently on the pull request — a comment "MUST NOT be edited after posting" —
    so the ordering is the substance of the guarantee, not a nicety. The absence of a
    `gh pr comment` call is what asserts it.
    """
    _file_item(repo=tmp_path)
    runner = _Runner(comments=_comments(records=(_capture_comment(identity=_SESSION),)))
    reconciled = _Reconciles()

    exit_code, emitted = _post(
        repo=tmp_path,
        verdict=VERDICT_HOST_VERIFIED,
        runner=runner,
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        reproduced=True,
        reconciles=reconciled,
    )

    assert exit_code != 0
    assert SELF_REPLAY_REFUSAL in emitted
    assert _SESSION in emitted
    assert [call for call in runner.calls if call[:3] == ["gh", "pr", "comment"]] == []
    assert reconciled.driven == []


def test_a_not_reproduced_replay_from_the_recording_identity_is_refused_too(
    tmp_path: Path,
) -> None:
    """Both replay verdicts carry the refusal; the clause names them together.

    A primitive that guarded only `host_verified` would let the same session publish
    its own `host_not_reproduced` record — which is a FAIL that sends the item to
    rework, so the self-replay would be destructive rather than merely unearned.
    """
    _file_item(repo=tmp_path)
    runner = _Runner(comments=_comments(records=(_capture_comment(identity=_SESSION),)))

    exit_code, emitted = _post(
        repo=tmp_path,
        verdict=VERDICT_HOST_NOT_REPRODUCED,
        runner=runner,
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        reproduced=False,
    )

    assert exit_code != 0
    assert SELF_REPLAY_REFUSAL in emitted
    assert [call for call in runner.calls if call[:3] == ["gh", "pr", "comment"]] == []


def test_a_replay_with_no_capture_to_replay_is_refused(tmp_path: Path) -> None:
    """A replay replays something; with no `host_recorded` record there is nothing.

    The identity check alone cannot catch this — there is no recording identity to
    collide with — so an unguarded primitive would publish a `host_verified` record
    for steps nobody had published, and the acceptance pass would then pass the
    assertion on a replay of nothing.
    """
    _file_item(repo=tmp_path)
    runner = _Runner(comments=_comments())

    exit_code, emitted = _post(
        repo=tmp_path,
        verdict=VERDICT_HOST_VERIFIED,
        runner=runner,
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        reproduced=True,
    )

    assert exit_code != 0
    assert NO_CAPTURE_REFUSAL in emitted
    assert [call for call in runner.calls if call[:3] == ["gh", "pr", "comment"]] == []


def test_an_unresolvable_publishing_identity_refuses_rather_than_posting(
    tmp_path: Path,
) -> None:
    """With no agent session and no forge login there is no identity to publish under."""
    _file_item(repo=tmp_path)
    runner = _Runner(comments=_comments())

    exit_code, emitted = _post(repo=tmp_path, verdict=VERDICT_HOST_RECORDED, runner=runner, env={})

    assert exit_code != 0
    assert NO_IDENTITY_REFUSAL in emitted
    assert [call for call in runner.calls if call[:3] == ["gh", "pr", "comment"]] == []


def test_publishing_an_independent_replay_drives_reconcile_merged_for_the_item(
    tmp_path: Path,
) -> None:
    """The clause's own consequence: the post RE-RUNS the acceptance pass.

    Driving `reconcile-merged` is what turns a published record into a disposition;
    without it the item rests in `acceptance` until something else happens to re-run
    the pass, which is the stranding the reopening analysis recorded.
    """
    _file_item(repo=tmp_path)
    runner = _Runner(comments=_comments(records=(_capture_comment(identity=_OTHER_SESSION),)))
    reconciled = _Reconciles()

    exit_code, _ = _post(
        repo=tmp_path,
        verdict=VERDICT_HOST_VERIFIED,
        runner=runner,
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        reproduced=True,
        reconciles=reconciled,
    )

    assert exit_code == 0
    assert reconciled.driven == [_ITEM_ID]


def test_a_capture_post_does_not_drive_reconcile_merged(tmp_path: Path) -> None:
    """Only the two REPLAY verdicts re-run the pass, which is what the clause says.

    A capture changes no verdict — the assertion stays pending until an independent
    replay lands — so re-running the pass for one would spend a janitor-free
    acceptance cycle to reach the identical answer.
    """
    _file_item(repo=tmp_path)
    runner = _Runner(comments=_comments())
    reconciled = _Reconciles()

    exit_code, _ = _post(
        repo=tmp_path,
        verdict=VERDICT_HOST_RECORDED,
        runner=runner,
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        reconciles=reconciled,
    )

    assert exit_code == 0
    assert reconciled.driven == []


def test_a_failed_post_reports_non_zero_and_drives_no_reconcile(tmp_path: Path) -> None:
    """A record that did not land must not trigger a pass that would find nothing."""
    _file_item(repo=tmp_path)
    runner = _Runner(
        comments=_comments(records=(_capture_comment(identity=_OTHER_SESSION),)), comment_exit=1
    )
    reconciled = _Reconciles()

    exit_code, _ = _post(
        repo=tmp_path,
        verdict=VERDICT_HOST_VERIFIED,
        runner=runner,
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        reproduced=True,
        reconciles=reconciled,
    )

    assert exit_code != 0
    assert reconciled.driven == []


def test_an_item_with_no_host_captured_assertion_is_refused(tmp_path: Path) -> None:
    """A host record belongs to an item that declares a host leg; otherwise it is noise."""
    _govern(repo=tmp_path)
    append_work_item(
        path=_config(),
        item=_work_item(
            description=f"Implement it.\n\n## Definition of Done\n\n- {_FACTORY_ASSERTION}\n",
            title="A factory-only slice",
        ),
    )
    runner = _Runner(comments=_comments())

    exit_code, emitted = _post(
        repo=tmp_path,
        verdict=VERDICT_HOST_RECORDED,
        runner=runner,
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
    )

    assert exit_code != 0
    assert _HOST_ASSERTION not in emitted
    assert [call for call in runner.calls if call[:3] == ["gh", "pr", "comment"]] == []


def test_a_record_payload_naming_an_undeclared_assertion_is_refused(tmp_path: Path) -> None:
    """The payload's assertions must be the item's own, so the mode can be computed.

    An assertion the Definition of Done does not declare has no proof mode to
    compute, and publishing it under a guessed one would let a record assert a mode
    the item never declared — which the acceptance pass would then grade against.
    """
    _file_item(repo=tmp_path)
    runner = _Runner(comments=_comments())
    payload = {
        "build": {"release_tag": _RELEASE_TAG},
        "assertions": [
            {"text": "An assertion nobody declared.", "steps": ["Do it."], "proof": "out\n"}
        ],
    }
    target = tmp_path / "bad.json"
    _ = target.write_text(json.dumps(payload), encoding="utf-8")
    emitted: list[str] = []

    exit_code = run_post_host_record_command(
        post=HostRecordPost(
            repo=tmp_path,
            work_item_id=_ITEM_ID,
            verdict=VERDICT_HOST_RECORDED,
            record_path=target,
        ),
        runner=runner,
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        emit=emitted.append,
        reconcile=_Reconciles().drive,
    )

    assert exit_code != 0
    assert "An assertion nobody declared." in "".join(emitted)
    assert [call for call in runner.calls if call[:3] == ["gh", "pr", "comment"]] == []


def test_an_unreadable_record_payload_is_refused(tmp_path: Path) -> None:
    """A payload that is not an object with the two keys cannot render a record."""
    _file_item(repo=tmp_path)
    target = tmp_path / "broken.json"
    _ = target.write_text("not json at all", encoding="utf-8")
    emitted: list[str] = []

    exit_code = run_post_host_record_command(
        post=HostRecordPost(
            repo=tmp_path,
            work_item_id=_ITEM_ID,
            verdict=VERDICT_HOST_RECORDED,
            record_path=target,
        ),
        runner=_Runner(comments=_comments()),
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        emit=emitted.append,
        reconcile=_Reconciles().drive,
    )

    assert exit_code != 0
    assert str(target) in "".join(emitted)


def test_a_never_filed_item_is_refused(tmp_path: Path) -> None:
    """The item is read before anything else, so an unknown id posts nothing."""
    _govern(repo=tmp_path)
    emitted: list[str] = []

    exit_code = run_post_host_record_command(
        post=HostRecordPost(
            repo=tmp_path,
            work_item_id="bd-ib-nosuch",
            verdict=VERDICT_HOST_RECORDED,
            record_path=_record_file(path=tmp_path),
        ),
        runner=_Runner(comments=_comments()),
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        emit=emitted.append,
        reconcile=_Reconciles().drive,
    )

    assert exit_code != 0
    assert "bd-ib-nosuch" in "".join(emitted)


def test_the_stage_name_is_published_for_the_journal() -> None:
    """The journal stage is a published constant, so no second literal can drift."""
    assert HOST_RECORD_STAGE == "host-record-post"


def test_an_item_with_no_merged_pull_request_is_refused(tmp_path: Path) -> None:
    """With no merge resolved there is no pull request the record would be evidence on.

    The clause binds a host record to "the pull request of the latest merged run", so an
    item whose merge cannot be resolved has no valid target at all. Publishing onto a
    guess would produce a record the acceptance pass refuses as sitting on an earlier
    pull request — for a reason the successful post would not reveal.
    """
    _file_item(repo=tmp_path)
    runner = _Runner(comments=_comments(), merged=False)

    exit_code, emitted = _post(
        repo=tmp_path,
        verdict=VERDICT_HOST_RECORDED,
        runner=runner,
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
    )

    assert exit_code != 0
    assert "no single merged pull request" in emitted
    assert [call for call in runner.calls if call[:3] == ["gh", "pr", "comment"]] == []


def test_a_replay_against_an_unreadable_pull_request_is_refused(tmp_path: Path) -> None:
    """An unread pull request cannot establish the identity the replay must differ from.

    This is the fail-CLOSED arm of the independence rule: a primitive that posted anyway
    would publish a replay whose independence nobody had checked, and the record is
    permanent. "Could not read" is not "no capture exists".
    """
    _file_item(repo=tmp_path)
    runner = _Runner(comments=_comments(), comments_exit=1)

    exit_code, emitted = _post(
        repo=tmp_path,
        verdict=VERDICT_HOST_VERIFIED,
        runner=runner,
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        reproduced=True,
    )

    assert exit_code != 0
    assert "comments could not be read" in emitted
    assert [call for call in runner.calls if call[:3] == ["gh", "pr", "comment"]] == []


def test_a_payload_whose_assertion_list_is_empty_is_refused(tmp_path: Path) -> None:
    """A record with no assertion section asserts nothing, so there is nothing to post."""
    _file_item(repo=tmp_path)
    target = tmp_path / "empty.json"
    _ = target.write_text(
        json.dumps({"build": {"release_tag": _RELEASE_TAG}, "assertions": []}), encoding="utf-8"
    )
    emitted: list[str] = []

    exit_code = run_post_host_record_command(
        post=HostRecordPost(
            repo=tmp_path,
            work_item_id=_ITEM_ID,
            verdict=VERDICT_HOST_RECORDED,
            record_path=target,
        ),
        runner=_Runner(comments=_comments()),
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        emit=emitted.append,
        reconcile=_Reconciles().drive,
    )

    assert exit_code != 0
    assert "names no assertion" in "".join(emitted)


def test_a_payload_missing_either_required_key_is_refused(tmp_path: Path) -> None:
    """Both halves are required: the build identity and the assertions.

    Each absence is checked because each produces a DIFFERENT malformed record rather
    than a failure — a payload with no build renders a record the pass refuses for
    naming none, and one with no assertions renders a header with no body.
    """
    _file_item(repo=tmp_path)
    for payload in ({"assertions": []}, {"build": {"release_tag": _RELEASE_TAG}}):
        target = tmp_path / "partial.json"
        _ = target.write_text(json.dumps(payload), encoding="utf-8")
        emitted: list[str] = []

        exit_code = run_post_host_record_command(
            post=HostRecordPost(
                repo=tmp_path,
                work_item_id=_ITEM_ID,
                verdict=VERDICT_HOST_RECORDED,
                record_path=target,
            ),
            runner=_Runner(comments=_comments()),
            env={"CLAUDE_CODE_SESSION_ID": _SESSION},
            emit=emitted.append,
            reconcile=_Reconciles().drive,
        )

        assert exit_code != 0
        assert str(target) in "".join(emitted)


def test_a_record_payload_that_cannot_be_read_at_all_is_refused(tmp_path: Path) -> None:
    """A path that is not a readable file is refused, not treated as an empty payload.

    A DIRECTORY is the fixture because it reaches the read as an `OSError` rather than
    as absent text, which is the arm a missing-file fixture would not exercise.
    """
    _file_item(repo=tmp_path)
    target = tmp_path / "a-directory"
    target.mkdir()
    emitted: list[str] = []

    exit_code = run_post_host_record_command(
        post=HostRecordPost(
            repo=tmp_path,
            work_item_id=_ITEM_ID,
            verdict=VERDICT_HOST_RECORDED,
            record_path=target,
        ),
        runner=_Runner(comments=_comments()),
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        emit=emitted.append,
        reconcile=_Reconciles().drive,
    )

    assert exit_code != 0
    assert str(target) in "".join(emitted)


def test_the_cli_entry_point_builds_the_invocation_and_refuses_an_unknown_item(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The REAL command line, end to end: `dispatcher.py post-host-record ...`.

    Driven through `dispatcher.main` rather than through the command function, so the
    subparser, the argument names and the handler wiring are all exercised — a test that
    called the function directly would pass against a subcommand nobody had registered.

    The unknown-item refusal is chosen deliberately as the case to drive: it fires before
    the primitive touches the forge, so the adapter's real `ShellCommandRunner` is
    constructed and never used, and the test spawns no subprocess.
    """
    _govern(repo=tmp_path)
    record = _record_file(path=tmp_path)

    exit_code = dispatcher_main(
        argv=[
            "post-host-record",
            "--repo",
            str(tmp_path),
            "--item",
            "bd-ib-unfiled",
            "--verdict",
            VERDICT_HOST_RECORDED,
            "--record",
            str(record),
        ]
    )

    assert exit_code != 0
    assert "bd-ib-unfiled" in capsys.readouterr().out


def test_the_cli_refuses_a_verdict_outside_the_three_host_leg_words(tmp_path: Path) -> None:
    """The verdict is a CLOSED choice, so a factory verdict cannot be published as one.

    `verified` is the control: it is a real Proof-of-Done verdict word, just not a
    host-leg one, so a primitive accepting any string would publish a record the
    acceptance pass reads as the merging run's factory evidence.
    """
    _govern(repo=tmp_path)
    with pytest.raises(SystemExit):
        _ = dispatcher_main(
            argv=[
                "post-host-record",
                "--repo",
                str(tmp_path),
                "--item",
                _ITEM_ID,
                "--verdict",
                "verified",
                "--record",
                str(_record_file(path=tmp_path)),
            ]
        )


def test_the_reconcile_wiring_reaches_the_ordinary_reconcile_merged_valve(
    tmp_path: Path,
) -> None:
    """The post drives the SAME valve an operator drives by hand, not a private copy.

    Asserted by reaching it with an invocation that valve refuses on its own
    preflight — an unknown item — so the wiring is proven without running an acceptance
    pass. The clause says "`reconcile-merged` driven by hand is the same route", which is
    only true if there is one route.
    """
    _govern(repo=tmp_path)

    exit_code = reconcile_merged_for_item(
        args=argparse.Namespace(
            repo=str(tmp_path),
            item="bd-ib-unfiled",
            janitor=None,
            journal=None,
            invoker="human:test",
            force=False,
            regrade=False,
            as_json=False,
        )
    )

    assert exit_code != 0


def test_the_bound_reconcile_carries_the_invocations_repository_to_the_valve(
    tmp_path: Path,
) -> None:
    """The closure the CLI binds reaches the valve with THIS invocation's repository.

    Exercised by calling the bound closure directly, because the only other route to it
    is a successful replay post — which needs a live forge. The item is unknown, so the
    valve refuses on its own preflight and no acceptance pass runs; what is proven is the
    binding, which is the part a successful post would otherwise be the first to test.
    """
    _govern(repo=tmp_path)

    drive = reconcile_for(
        repo=tmp_path, args=argparse.Namespace(journal=None, invoker="human:test")
    )

    assert drive(work_item_id="bd-ib-unfiled") != 0


_RECORD_FILE_KEYS = (
    "build",
    "release_tag",
    "installed_build",
    "commit",
    "assertions",
    "text",
    "governing_scenario",
    "steps",
    "proof",
    "reproduced",
)


def _help_text() -> str:
    """The help `dispatcher.py post-host-record --help` renders, for this surface alone.

    Built from a bare parser rather than driven through `dispatcher.main`, because
    `--help` exits the process and the thing under test is what THIS subcommand's
    argument builder puts on the page.
    """
    parser = argparse.ArgumentParser(prog="dispatcher.py post-host-record")
    add_post_host_record_arguments(parser=parser)
    return parser.format_help()


def _json_block(*, text: str) -> str:
    """The outermost brace-delimited block of `text`, found by its own line framing.

    Keyed on a line that is exactly `{` or `}` after stripping, which the usage line's
    `{host_recorded,host_verified,host_not_reproduced}` choice list cannot be: that brace
    is followed by a word on its own line. The LAST bare `}` closes the outermost object,
    the inner one closing an assertion entry being indented but equally bare.
    """
    lines = text.splitlines()
    opening = min(index for index, line in enumerate(lines) if line.strip() == "{")
    closing = max(index for index, line in enumerate(lines) if line.strip() == "}")
    return "\n".join(lines[opening : closing + 1])


def test_the_help_prints_the_record_files_json_shape() -> None:
    """`--help` renders the shape of the `--record` file, as a parseable skeleton.

    The first session to publish a host record in this repository had to read
    `_dispatcher_host_record_payload` to learn the file's keys, because `--help`
    described it only as "a JSON object carrying the build identity exercised and, per
    assertion, the numbered steps, the proof and whether they reproduced" — true, and
    not something anyone can write a file from.

    Asserted as a PARSE and not as a word hunt, because a skeleton that names every key
    and is not valid JSON is exactly the failure a substring check passes and the one a
    publisher copying the block hits first. The parse is also what makes this test
    load-bearing for the FORMATTER: argparse's default help formatter re-wraps the
    epilog, collapsing a skeleton into a paragraph that no longer parses.
    """
    help_text = _help_text()

    missing = [name for name in _RECORD_FILE_KEYS if f'"{name}"' not in help_text]
    assert missing == [], f"--help names no record-file key {missing}"

    document = json.loads(_json_block(text=help_text))
    assert set(document) == {"build", "assertions"}
    assert set(document["build"]) == {"release_tag", "installed_build", "commit"}
    assert set(document["assertions"][0]) == {
        "text",
        "governing_scenario",
        "steps",
        "proof",
        "reproduced",
    }


def test_the_help_states_the_two_rules_the_skeleton_alone_cannot_carry() -> None:
    """`--help` states which `text` is admissible, and when `reproduced` is read at all.

    Both rules are invisible in a skeleton, and both fail SILENTLY when broken. An
    assertion whose `text` is not one the item declares has no computable proof mode, so
    it is refused rather than published under a guess — and the refusal names a payload
    the publisher believed was right. A `reproduced` claim on a `host_recorded` capture
    is DROPPED, whatever the file says, because a first leg has nothing yet to have
    reproduced; a publisher who copied a replay payload would never see that it went.

    Whitespace is normalized because the epilog reaches the page raw, so the authored
    line breaks survive and any phrase worth asserting straddles one.
    """
    normalized = " ".join(_help_text().split())

    assert '"text" MUST match, verbatim, an assertion' in normalized
    assert "the item's own Definition of Done declares" in normalized
    assert '"reproduced" is read ONLY for a replay verdict' in normalized


# ---------------------------------------------------------------------------
# bd-ib-555xcd: the record is measured against the declared budget before the
# post, and an over-budget record is refused rather than published.
#
# WHY THESE ASSERTIONS ARE MANY AND MODEST RATHER THAN ONE ENORMOUS ONE. A
# single over-allowance proof does not reach this refusal at all once the
# attachment path exists: it travels as a digest-named asset and the record
# comes back under budget. The durable way to be over budget is in AGGREGATE —
# every proof under the per-assertion inline allowance, their SUM over the
# budget — which is also the arm whose remedy is not an attachment, and so the
# arm that must stay refusable for good.
# ---------------------------------------------------------------------------

_BULK_ASSERTIONS = tuple(
    f"The bounded-record arm number {index} holds on an operator host." for index in range(7)
)
_BULK_BULLETS = "\n".join(f"- {one}" for one in _BULK_ASSERTIONS)
_BULK_DESCRIPTION = f"""Implement the slice.

## Definition of Done

### Host-captured

Reason: the proof needs the released build installed on an operator host.

{_BULK_BULLETS}

References: ## Scenario 136 — A host-captured assertion holds the item in acceptance
"""


def _bulk_item(*, repo: Path) -> None:
    """File an item declaring seven host-captured assertions."""
    _govern(repo=repo)
    append_work_item(
        path=_config(),
        item=_work_item(description=_BULK_DESCRIPTION, title="A bounded-record slice"),
    )


def _bulk_record_file(*, path: Path, proof_bytes: int) -> Path:
    """A payload carrying one equally-sized proof per declared assertion."""
    payload: dict[str, object] = {
        "build": {
            "release_tag": _RELEASE_TAG,
            "installed_build": "livespec-orchestrator-beads-fabro 0.173.7",
        },
        "assertions": [
            {
                "text": text,
                "steps": ["Install the released build.", "Drive the valve."],
                "proof": "p" * proof_bytes,
                "reproduced": None,
            }
            for text in _BULK_ASSERTIONS
        ],
    }
    target = path / "bulk-record.json"
    _ = target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _post_bulk(*, repo: Path, runner: _Runner, proof_bytes: int) -> tuple[int, str]:
    emitted: list[str] = []
    code = run_post_host_record_command(
        post=HostRecordPost(
            repo=repo,
            work_item_id=_ITEM_ID,
            verdict=VERDICT_HOST_RECORDED,
            record_path=_bulk_record_file(path=repo, proof_bytes=proof_bytes),
        ),
        runner=runner,
        env={"CLAUDE_CODE_SESSION_ID": _SESSION},
        emit=emitted.append,
        reconcile=_Reconciles().drive,
    )
    return code, "".join(emitted)


def test_an_under_budget_record_of_the_same_shape_still_posts(tmp_path: Path) -> None:
    """The control, and it is the load-bearing half of this pair.

    Without it, the refusal below is equally consistent with "the budget refused an
    over-budget record" and with "this seven-assertion fixture cannot post at all",
    and nothing in either output distinguishes those. The two cases differ ONLY in
    the per-assertion proof size, so a green here localizes the refusal to the size.
    """
    _bulk_item(repo=tmp_path)
    runner = _Runner(comments=_comments())

    exit_code, emitted = _post_bulk(repo=tmp_path, runner=runner, proof_bytes=4096)

    assert exit_code == 0
    posted = [call for call in runner.calls if call[:3] == ["gh", "pr", "comment"]]
    assert len(posted) == 1
    body = Path(posted[0][-1]).read_text(encoding="utf-8")
    assert measured_bytes(text=body) <= PROOF_RECORD_BUDGET_BYTES
    assert body in emitted


def test_an_over_budget_record_is_refused_and_never_reaches_the_forge(tmp_path: Path) -> None:
    """The refusal fires BEFORE the post, and names the size, the budget and an assertion.

    The absence of the `gh pr comment` call is the assertion that matters most. A
    record comment must not be edited after posting, so a refusal that fired after
    the forge call would leave the oversize record permanently on the pull request —
    and the budget would have measured a record it could no longer withhold.
    """
    _bulk_item(repo=tmp_path)
    runner = _Runner(comments=_comments())

    exit_code, emitted = _post_bulk(repo=tmp_path, runner=runner, proof_bytes=30000)

    assert exit_code == 3
    assert [call for call in runner.calls if call[:3] == ["gh", "pr", "comment"]] == []
    assert HOST_RECORD_SURFACE in emitted
    # The measured size, the declared budget, and the measured ceiling.
    assert str(PROOF_RECORD_BUDGET_BYTES) in emitted
    assert str(FORGE_COMMENT_CEILING_BYTES) in emitted
    # The aggregate arm names an assertion AND says no single proof overflowed, so
    # the named one does not read as the culprit when the remedy is a smaller item.
    assert "No single proof" in emitted
    assert any(one in emitted for one in _BULK_ASSERTIONS)
    assert "Nothing was published" in emitted
