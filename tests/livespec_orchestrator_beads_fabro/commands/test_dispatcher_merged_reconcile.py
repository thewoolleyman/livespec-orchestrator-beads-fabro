"""The merged-reconcile ending as the Dispatcher reads it, carries it and grades it.

The sandbox prints one `LIVESPEC_MERGED_RECONCILE:` line when a run finishes because
its publication had already landed. These cases bind the three things the Dispatcher
does with that line: it parses it, it carries it on the dispatch outcome and its
detail, and the acceptance pass's proof leg grades the merged head against the records
that PROVE that head, so a `verified` record taken on another head proves nothing.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
    EffectiveCriteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_merged_reconcile import (
    MergedReconcile,
    merged_head_record,
    merged_reconcile_detail,
    merged_reconcile_from_text,
    record_published_head,
    records_proving_head,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import proof_leg
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import proof_records
from livespec_orchestrator_beads_fabro.types import WorkItem

_MERGE = "a" * 40
_MERGED_HEAD = "b" * 40
_OLD_HEAD = "c" * 40
_RUN = "01M3MERGEDRECONCILE"
_ASSERTION = "The projection carries the parent field."
_LINE = (
    "LIVESPEC_MERGED_RECONCILE: pull_request=73 merge_commit="
    f"{_MERGE} merged_head={_MERGED_HEAD} proof_head={_OLD_HEAD} heads_equal=false"
)
_HOST_BODY = "Proof of Done — host_recorded — session s-1 — 2026-10-28T09:00:00Z\n"
_TENANT_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
"""


def _record(*, verdict: str, head: str, body_extra: str = "") -> dict[str, str]:
    body = textwrap.dedent(f"""\
        Proof of Done — {verdict} — run {_RUN} — 2026-10-28T09:00:00Z

        Publish-branch head: {head}
        {body_extra}
        ## Assertion 1 — {_ASSERTION}

        Reproduced: yes.
        """)
    return {"url": f"https://example.test/{verdict}/{head[:4]}", "body": body}


def _criteria() -> EffectiveCriteria:
    return EffectiveCriteria(
        text=_ASSERTION,
        source=DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
        assertions=(_ASSERTION,),
        proof_modes=(PROOF_MODE_FACTORY_CAPTURED,),
    )


def test_the_sandbox_line_parses_into_the_five_facts_the_ending_records() -> None:
    event = merged_reconcile_from_text(text=f"noise\n{_LINE}\nmore")

    assert event == MergedReconcile(
        pull_request=73,
        merge_commit=_MERGE,
        merged_head=_MERGED_HEAD,
        proof_head=_OLD_HEAD,
        heads_equal=False,
    )


def test_an_ending_with_no_proof_record_parses_the_head_as_absent() -> None:
    line = _LINE.replace(f"proof_head={_OLD_HEAD}", "proof_head=none")

    event = merged_reconcile_from_text(text=line)

    assert event is not None
    assert event.proof_head is None


def test_the_route_classifier_line_and_ordinary_output_are_not_the_event() -> None:
    route = "LIVESPEC_MERGED_RECONCILE_ROUTE: publication already merged; bypassing pr"

    assert merged_reconcile_from_text(text=route) is None
    assert merged_reconcile_from_text(text="") is None


def test_the_last_line_wins_when_a_re_entered_stage_prints_it_again() -> None:
    first = _LINE.replace("pull_request=73", "pull_request=1")

    event = merged_reconcile_from_text(text=f"{first}\n{_LINE}")

    assert event is not None
    assert event.pull_request == 73


def test_the_detail_names_the_number_the_commits_and_whether_the_heads_are_equal() -> None:
    event = merged_reconcile_from_text(text=_LINE)
    assert event is not None

    detail = merged_reconcile_detail(event=event)

    assert "pull request #73" in detail
    assert _MERGE in detail
    assert _MERGED_HEAD in detail
    assert _OLD_HEAD in detail
    assert detail.endswith("heads equal: no")


def test_the_detail_says_when_no_record_exists_and_when_the_heads_are_equal() -> None:
    event = MergedReconcile(
        pull_request=5,
        merge_commit=_MERGE,
        merged_head=_MERGED_HEAD,
        proof_head=None,
        heads_equal=True,
    )

    detail = merged_reconcile_detail(event=event)

    assert "no verified or carried_forward record" in detail
    assert detail.endswith("heads equal: yes")


def test_a_record_declares_its_head_only_in_prose_and_only_once() -> None:
    fenced = f"```\nPublish-branch head: {_OLD_HEAD}\n```\n"
    one = f"Publish-branch head: {_MERGED_HEAD}\n{fenced}"
    two = f"Publish-branch head: {_MERGED_HEAD}\nPublish-branch head: {_OLD_HEAD}\n"
    unfinished = f"~~~\nPublish-branch head: {_OLD_HEAD}\n`````\nPublish-branch head: x\n"

    assert record_published_head(body=one) == _MERGED_HEAD
    assert record_published_head(body=two) is None
    assert record_published_head(body="Publish-branch head: not-a-sha\n") is None
    assert record_published_head(body=unfinished) is None


def test_a_verified_record_on_the_merged_head_proves_it() -> None:
    comments = [_record(verdict="verified", head=_MERGED_HEAD)]
    records = proof_records(comments=comments)

    proving = merged_head_record(records=records, run_ids=(_RUN,), merged_head=_MERGED_HEAD)

    assert proving is not None
    assert proving.verdict == "verified"


def test_a_verified_record_on_another_head_proves_nothing_for_the_merged_head() -> None:
    records = proof_records(comments=[_record(verdict="verified", head=_OLD_HEAD)])

    assert merged_head_record(records=records, run_ids=(_RUN,), merged_head=_MERGED_HEAD) is None


def test_a_record_of_another_run_proves_nothing_for_the_merged_head() -> None:
    records = proof_records(comments=[_record(verdict="verified", head=_MERGED_HEAD)])

    assert merged_head_record(records=records, run_ids=("other",), merged_head=_MERGED_HEAD) is None


def test_a_carried_forward_record_on_the_merged_head_grades_through_the_verified_record() -> None:
    comments = [
        _record(verdict="verified", head=_OLD_HEAD),
        _record(verdict="carried_forward", head=_MERGED_HEAD),
    ]
    records = proof_records(comments=comments)

    proving = merged_head_record(records=records, run_ids=(_RUN,), merged_head=_MERGED_HEAD)

    assert proving is not None
    assert proving.verdict == "verified"
    assert proving.reproduced(assertion=_ASSERTION) is True


def test_only_the_record_proving_the_merged_head_stays_among_the_anchor_records() -> None:
    comments = [
        _record(verdict="verified", head=_OLD_HEAD),
        _record(verdict="verified", head=_MERGED_HEAD),
        {"url": "https://example.test/host", "body": _HOST_BODY},
    ]
    records = proof_records(comments=comments)

    kept = records_proving_head(records=records, run_ids=(_RUN,), merged_head=_MERGED_HEAD)

    assert [one.verdict for one in kept] == ["host_recorded", "verified"]
    assert record_published_head(body=kept[-1].body) == _MERGED_HEAD


def test_no_anchor_record_stays_when_none_proves_the_merged_head() -> None:
    records = proof_records(comments=[_record(verdict="verified", head=_OLD_HEAD)])

    kept = records_proving_head(records=records, run_ids=(_RUN,), merged_head=_MERGED_HEAD)

    assert kept == ()
    leg = proof_leg(criteria=_criteria(), records=kept, run_ids=(_RUN,), reason="r")
    assert leg.record is None
    assert leg.unevidenced == (_ASSERTION,)


@dataclass(kw_only=True)
class _FakeRunner:
    queue: list[CommandResult]
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
        assert timeout_seconds > 0
        _ = (cwd, env, stdin)
        self.calls.append(argv)
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ok(stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr=stderr)


def _pr_json(*, state: str, sha: str | None) -> str:
    return json.dumps(
        {
            "number": 73,
            "state": state,
            "autoMergeRequest": {"enabledAt": "now"},
            "mergeStateStatus": "CLEAN",
            "mergeCommit": {"oid": sha} if sha is not None else None,
            "statusCheckRollup": [],
        }
    )


def _dispatch(*, repo: Path, fabro_stderr: str) -> DispatchOutcome:
    _ = (repo / ".livespec.jsonc").write_text(_TENANT_CONFIG, encoding="utf-8")
    runner = _FakeRunner(
        queue=[
            _ok(stderr=fabro_stderr),
            _ok(stdout=_pr_json(state="OPEN", sha=None)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe01")),
            _ok(stdout=json.dumps([{"number": 73}])),
            _ok(),
            _ok(stdout="master"),
            _ok(stdout="master"),
            *[_ok() for _ in range(8)],
        ]
    )
    plan = build_plan(
        repo=repo,
        work_item_id="x-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text='{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}',
        default_branch="master",
    )
    return run_dispatch(
        plan=plan,
        runner=runner,
        journal=_Journal(),
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=3, interval_seconds=0.5),
    )


def test_a_run_that_took_the_ending_carries_it_on_the_outcome_and_its_detail(
    tmp_path: Path,
) -> None:
    outcome = _dispatch(repo=tmp_path, fabro_stderr=_LINE)

    assert outcome.status == "green"
    assert outcome.merged_reconcile is not None
    assert outcome.merged_reconcile.merged_head == _MERGED_HEAD
    assert "merged-reconcile ending: pull request #73" in outcome.detail


def test_an_ordinary_run_carries_no_merged_reconcile_ending(tmp_path: Path) -> None:
    outcome = _dispatch(repo=tmp_path, fabro_stderr="")

    assert outcome.status == "green"
    assert outcome.merged_reconcile is None
    assert "merged-reconcile" not in outcome.detail


_REFERENCE_LINE = (
    "References: ## Scenario 248 — A pull request merged before its refresh ends the run"
    " as a finished publication"
)


@dataclass(kw_only=True)
class _ForgeRunner:
    comments: str

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        if "comments" in argv:
            return CommandResult(exit_code=0, stdout=self.comments, stderr="")
        return CommandResult(exit_code=0, stdout="diff --git a/x b/x\n+unrelated\n", stderr="")


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-merged-reconcile",
        type="task",
        status="active",
        title="Task",
        description=f"## Definition of Done\n\n- {_ASSERTION}\n\n{_REFERENCE_LINE}\n",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-28T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _merged_outcome(*, head: str) -> DispatchOutcome:
    ending = MergedReconcile(
        pull_request=7,
        merge_commit=_MERGE,
        merged_head=head,
        proof_head=_OLD_HEAD,
        heads_equal=head == _OLD_HEAD,
    )
    return replace(
        DispatchOutcome(
            work_item_id="bd-ib-merged-reconcile",
            status="green",
            stage="done",
            pr_number=7,
            merge_sha=_MERGE,
            detail="merged",
            fabro_run_id=_RUN,
        ),
        merged_reconcile=ending,
    )


def test_the_acceptance_pass_cannot_observe_a_merged_head_no_record_proves(
    tmp_path: Path,
) -> None:
    comments = json.dumps({"comments": [_record(verdict="verified", head=_OLD_HEAD)]})

    unproven = run_acceptance_pass(
        repo=tmp_path,
        item=_item(),
        outcome=_merged_outcome(head=_MERGED_HEAD),
        runner=_ForgeRunner(comments=comments),
    )
    proven = run_acceptance_pass(
        repo=tmp_path,
        item=_item(),
        outcome=_merged_outcome(head=_OLD_HEAD),
        runner=_ForgeRunner(comments=comments),
    )

    assert unproven.verdict == "NEEDS_ATTENTION"
    assert unproven.absent_evidence != ()
    assert proven.verdict == "PASS"
    assert proven.absent_evidence == ()
