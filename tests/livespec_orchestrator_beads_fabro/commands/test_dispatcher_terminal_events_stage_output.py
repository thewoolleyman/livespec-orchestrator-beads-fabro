"""The failing stage's own record is the last place a needs-human cause is read from.

Work-item `bd-ib-36d3x5`. On the Petri engine a terminated run's
`fabro inspect --json` record carries NO `node_outcomes` on its checkpoint, and
the event stream is a separate, slower read that times out on a long run (the
first instance, `01M580PF02S0`, journaled `fabro-terminal-events` as a 60 s
timeout). The one record the Dispatcher ALWAYS holds is the inspect record's
top-level `stages` map, and the failing stage's entry there carries the cause —
yet `routing_stage_failure` never consulted it, so every such ending reported
`innermost cause: ABSENT` for a cause the engine had written down.

THE TWO OUTPUT SHAPES BELOW ARE MEASURED, not reconstructed. Both were read off
the gmktec factory (`:32276`, carrier `0.382.0-nightly.0 adeefec`) on
2026-10-24 with `fabro inspect --json`:

- Run `01M5QNH88NHN68ST28Y80CZJ48` (`bd-ib-8zyan`): `stages["implement@1"]` has
  keys `diff, handler, output, response, state`, `state == "failed"`, and its
  `output` is the agent's 3655-character transcript whose LAST LINE is the
  stage's structured verdict,
  `{"outcome":"failed","failure_reason":"LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS: …",
  "definition_of_done_complete":false}` — the same `failure_reason` the dump's
  `stages/050-implement@1/status.json` records. The inspect stage entry itself
  carries NO `failure_reason` key; the verdict line is where it lives.
- Run `01M5N3J02GQ1423GRX25HW0NPN` (`livespec-console-beads-fabro-rhh56m`):
  `stages["janitor@1"].output` is the literal `blob://sha256/<digest>` — a
  reference to bytes this host never fetched, not a sentence — and
  `stages["proof_capture@1"]` carries `handler` and `state` only, with no
  output at all. A reader that rendered the blob reference, or invented text
  for the missing output, would state a cause the engine did not record.

The provider-ceiling case transcribes the first instance (`bd-ib-fubkcv`,
`proof_verify@3`): the provider's sentence appeared ONLY in that stage's
`output`. The literal used here is the form the shared classifier already
recognises; mapping the weekly-limit wording is `bd-ib-ht7v4q`'s, which this
item blocks, and the control below records that the sentence is SURFACED as
the cause even where it is not yet classified as a ceiling.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_events import (
    routing_stage_failure,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
    fabro_status_kind_from_payload,
)

_RUN = "01M5QNH88NHN68ST28Y80CZJ48"
_ITEM = "bd-ib-8zyan"
_PARTIAL_PROGRESS = (
    "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS: committed Red test f81b470e; staged "
    "disagreement reader and tests are not Green-committed, and required "
    "host/preflight plus node/journal integration remains owed."
)
_TRANSCRIPT = (
    "I'll inspect the branch, repository rules, and the existing implementation "
    "to scope the changes.\n\nCommitted Red:\n- `f81b470e feat(dod): journal "
    "opposite verdicts`\n\nStaged, uncommitted:\n- disagreement receipt parser\n"
)
_VERDICT_LINE = json.dumps(
    {
        "outcome": "failed",
        "failure_reason": _PARTIAL_PROGRESS,
        "definition_of_done_complete": False,
    }
)
_PARTIAL_OUTPUT = f"{_TRANSCRIPT}\n{_VERDICT_LINE}\n"
_CODEX_CEILING = (
    "Internal error: You've hit your usage limit. "
    "Visit https://chatgpt.com/codex/settings/usage or try again at Oct 25, 3pm (UTC)"
)
_WEEKLY_CEILING = "Internal error: You've hit your weekly limit · resets Oct 23, 3pm (UTC)"
_BLOB_REFERENCE = "blob://sha256/4c9fdf4e631bbfdd11e2dc79fad223d9a23ae7c54c64e67415771122e7e10371"
_TERMINAL_OUTPUT = (
    f"{NEEDS_HUMAN_MARKER}_PRESERVED: refs/heads/needs-human/0209f2cfa52748f199e8383d99147eab\n"
    f"{NEEDS_HUMAN_MARKER}: loop cannot auto-resolve this work-item; run terminated, "
    "work preserved by reference, decision routed to the ledger (blocked / needs-human)\n"
)


def _stage(*, state: str, output: object = None, handler: str = "agent") -> dict[str, object]:
    """One Petri `stages` entry; `output` is omitted entirely when None, as measured."""
    entry: dict[str, object] = {"handler": handler, "state": state, "response": ""}
    if output is not None:
        entry["output"] = output
    return entry


def _payload(*, stages: dict[str, object]) -> list[object]:
    """One Petri `inspect` record: a three-key checkpoint at the terminal, no outcomes."""
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed", "reason": "workflow_error"},
            "stages": stages,
            "checkpoint": {
                "timestamp": "2026-10-24T20:03:39.149Z",
                "current_node": "needs_human",
                "git_commit_sha": "c4bfd246fdd84f46ea13e1a4100c1adb4189cd6a",
            },
            "conclusion": {
                "status": "failed",
                "failure": {
                    "reason": "workflow_error",
                    "detail": {
                        "message": f"script exited with status 1\n{_TERMINAL_OUTPUT}",
                        "category": "deterministic",
                    },
                },
            },
        }
    ]


def _run_stages(*, failed: str, output: object) -> dict[str, object]:
    """The measured run shape: every earlier stage succeeded, one failed, then the terminal."""
    return {
        "janitor@1": _stage(state="succeeded", handler="command", output=""),
        failed: _stage(state="failed", output=output),
        "needs_human@1": _stage(state="failed", handler="command", output=_TERMINAL_OUTPUT),
    }


def _routed(*, stages: dict[str, object], stage: str, events: object = None) -> object:
    return routing_stage_failure(
        observed=None,
        inspect_payload=_payload(stages=stages),
        events_payload=events,
        stage=stage,
    )


def test_the_stage_verdict_failure_reason_is_the_innermost_cause() -> None:
    """The transcript's last line is the stage's own verdict, and its reason is the cause."""
    failure = _routed(
        stages=_run_stages(failed="implement@1", output=_PARTIAL_OUTPUT), stage="implement@1"
    )
    assert failure is not None
    assert failure.cause == _PARTIAL_PROGRESS
    assert failure.provider_usage_limit is False


def test_a_provider_ceiling_only_in_the_stage_output_is_classified_as_one() -> None:
    """The one classification pass grades the stage output like any other cause chain."""
    failure = _routed(
        stages=_run_stages(failed="proof_verify@3", output=_CODEX_CEILING),
        stage="proof_verify@3",
    )
    assert failure is not None
    assert failure.provider_usage_limit is True
    assert failure.provider_usage_limit_provider == "codex"
    assert failure.category == "deterministic"
    assert failure.cause == _CODEX_CEILING


def test_an_unclassified_provider_sentence_is_still_surfaced_as_the_cause() -> None:
    """CONTROL for the case this item was filed on: surfaced now, classified by bd-ib-ht7v4q."""
    failure = _routed(
        stages=_run_stages(failed="proof_verify@3", output=_WEEKLY_CEILING),
        stage="proof_verify@3",
    )
    assert failure is not None
    assert failure.cause == _WEEKLY_CEILING


@pytest.mark.parametrize(
    "last_line",
    [json.dumps({"outcome": "failed"}), json.dumps({"failure_reason": None}), "[]", "not json"],
)
def test_an_output_whose_last_line_names_no_reason_is_the_cause_as_it_stands(
    *, last_line: str
) -> None:
    output = f"{_TRANSCRIPT}\n{last_line}\n"
    failure = _routed(stages=_run_stages(failed="implement@1", output=output), stage="implement@1")
    assert failure is not None
    assert failure.cause == output.strip()


@pytest.mark.parametrize("output", [None, "", "   \n", _BLOB_REFERENCE, 7])
def test_a_stage_recording_no_readable_output_leaves_the_cause_unknown(*, output: object) -> None:
    """A blob reference, blank, missing or non-text output is NOT a sentence to report."""
    assert _routed(stages=_run_stages(failed="janitor@1", output=output), stage="janitor@1") is None


def test_a_succeeded_visit_of_the_node_is_never_read() -> None:
    """Only a FAILED entry speaks for the routing stage, whatever its output says."""
    stages: dict[str, object] = {
        "implement@1": _stage(state="succeeded", output=_PARTIAL_OUTPUT),
        "needs_human@1": _stage(state="failed", handler="command", output=_TERMINAL_OUTPUT),
    }
    assert _routed(stages=stages, stage="implement@1") is None


def test_the_newest_failed_visit_wins_when_the_stage_is_named_by_node() -> None:
    """The key is matched through the shared node normalizer, newest visit last."""
    stages: dict[str, object] = {
        "implement@1": _stage(state="failed", output="first attempt failed"),
        "implement@2": _stage(state="failed", output="second attempt failed"),
        "needs_human@1": _stage(state="failed", handler="command", output=_TERMINAL_OUTPUT),
    }
    failure = _routed(stages=stages, stage="implement")
    assert failure is not None
    assert failure.cause == "second attempt failed"


def test_the_terminal_stage_output_is_never_a_routing_cause() -> None:
    stages = _run_stages(failed="implement@1", output=_PARTIAL_OUTPUT)
    assert _routed(stages=stages, stage="needs_human@1") is None


def test_an_event_cause_still_wins_over_the_stage_output() -> None:
    """The stage record is the LAST read, behind the checkpoint and the events."""
    failure = _routed(
        stages=_run_stages(failed="implement@1", output=_PARTIAL_OUTPUT),
        stage="implement@1",
        events=[
            {
                "event": "stage.failed",
                "properties": {"node_id": "implement", "failure": {"message": "the event cause"}},
            }
        ],
    )
    assert failure is not None
    assert failure.cause == "the event cause"


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id=_ITEM,
        branch=f"feat/{_ITEM}",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="petri",
        fabro_factory_server="https://gmktec.example:32276",
        fabro_factory_dev_token=None,
        janitor=None,
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _terminal_outcome(*, tmp_path: Path, stages: dict[str, object]) -> DispatchOutcome:
    payload = _payload(stages=stages)
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_RUN,
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=payload,
            status_kind=fabro_status_kind_from_payload(payload=payload),
            failure=fabro_failure_detail_from_payload(payload=payload),
            events_payload=None,
        ),
        exit_code=1,
        stderr=_TERMINAL_OUTPUT,
    )
    assert outcome is not None
    return outcome


def test_the_needs_human_outcome_names_the_stage_verdict_reason(*, tmp_path: Path) -> None:
    """End to end: the outcome row and its detail carry the reason, never ABSENT."""
    outcome = _terminal_outcome(
        tmp_path=tmp_path, stages=_run_stages(failed="implement@1", output=_PARTIAL_OUTPUT)
    )
    assert (outcome.status, outcome.needs_human_kind) == ("blocked", "stage-failure")
    assert outcome.fabro_failure_cause == _PARTIAL_PROGRESS
    assert _PARTIAL_PROGRESS in outcome.detail
    assert "ABSENT" not in outcome.detail


def test_the_needs_human_outcome_journals_a_stage_output_ceiling(*, tmp_path: Path) -> None:
    """Assertion 1: provider_usage_limit true, with the provider's own sentence."""
    outcome = _terminal_outcome(
        tmp_path=tmp_path, stages=_run_stages(failed="proof_verify@3", output=_CODEX_CEILING)
    )
    assert outcome.provider_usage_limit is True
    assert outcome.provider_usage_limit_provider == "codex"
    assert outcome.fabro_failure_cause == _CODEX_CEILING
    assert "ABSENT" not in outcome.detail
