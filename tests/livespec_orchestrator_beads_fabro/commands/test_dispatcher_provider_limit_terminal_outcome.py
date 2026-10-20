"""A terminated provider-limit run yields a RELEASE outcome, not a blocked one.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Provider-limit release and re-dispatch" (`bd-ib-6itdjz`,
Scenario 127): when a run terminates "through any terminal, the workflow's
`needs_human` terminal included" and the failing node's recorded failure
classifies as an eligible cause, the item is released rather than rested at
`blocked / needs-human`. This is the terminal mapper's half of that.

THE FIXTURE IS THE MEASURED OUTAGE. Run 01M52R2WND7Y of `bd-ib-26deyw` ended
2026-10-16 with the implement node's `causes[-1]` reading "You have hit your
session limit", routed to the `needs_human` terminal, and rested at
`blocked / needs-human` with 952 lines of preserved work across 7 files; the
plain re-dispatch then started from master and discarded about 80 minutes of
implement work. Four runs ended that way in one day (ledger rider on this
item). So the payload below carries the marker that ROUTES to blocked today,
and the test's whole claim is that the release now outranks it.

THE CONFIGURATION IS REAL, NOT INJECTED. The candidate's signatures are read
through `resolve_dispatch_candidates` off a `.livespec.jsonc` and a workflow
manifest written into `tmp_path`, which is the same resolution a dispatch
takes. A stub reader would prove the mapper calls something; this proves an
operator's own declared signature reaches the decision.

THE UNCHANGED-ROUTE CONTROL IS WHAT GIVES THE POSITIVE ONE MEANING. Without
it, a mapper that released EVERY needs-human ending would satisfy the positive
assertion while destroying the human route the contract keeps for an
unclassifiable failure. Its cause is the measured infrastructure fault that
ended this item's own earlier dispatch, and it carries neither an eligible
signature match nor the typed flag -- the exact conjunction the Definition of
Done names for keeping the existing route.

WHAT THIS FILE MEASURED AND THEN HAD TO CORRECT, recorded because the wrong
expectation is the plausible one. Two cases here first asserted that a release
does NOT happen when the candidate resolution is unreadable or absent. That is
wrong: `fabro_failure_detail_from_payload` already sets the typed
provider-usage-limit flag, with provider `anthropic`, for this very sentence,
and the clause releases a typed provider-limit failure on that alone "without
inventing a candidate identity". So those two cases now assert the LEGACY arm
-- released, with `matched is None` so no typed hold is minted and no
entitlement nobody observed is named. The blinded-gauge concern is real and
sits exactly there: the thing that must never happen is a TYPED hold scoped to
an entitlement that was never measured.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import AcpNodeResolution
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
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    FabroPort,
    FabroTarget,
)

_RUN = "01M52R2WND7Y"
_SESSION_LIMIT = "You have hit your session limit, resets 7:20pm (UTC)"
_MARKER = f"{NEEDS_HUMAN_MARKER}: the implement node failed"
_PRESERVED = f"{NEEDS_HUMAN_MARKER}_PRESERVED: refs/heads/needs-human/{_RUN}"

_AVAILABILITY_KEY = "anthropic-team"
_CANDIDATE_KEY = "claude-primary"

_IDENTITY = AcpCandidateIdentity(
    display_name="Claude ACP primary",
    candidate_key=_CANDIDATE_KEY,
    availability_key=_AVAILABILITY_KEY,
)

_DECLARED_QUOTA = {
    "source": "protocol.message",
    "cause": "quota",
    "scope": "availability-domain",
    "all_literals": ["hit your session limit"],
}
_TURN_CAPACITY = "Selected model is at capacity. Please try a different model."
_REVIEW_IDENTITY = AcpCandidateIdentity(
    display_name="Codex ACP review fallback",
    candidate_key="gpt-5.6-terra",
    availability_key="codex",
)


def _payload(*, cause: str) -> list[dict[str, Any]]:
    """One terminated run whose implement node failed, routed to needs_human."""
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed", "reason": "workflow_error"},
            "checkpoint": {
                "current_node": "needs_human",
                "next_node_id": None,
                "completed_nodes": ["implement"],
                "node_outcomes": {"implement": {"status": "failed"}},
            },
            "conclusion": {
                "status": "failed",
                "timestamp": "2026-10-16T19:20:00Z",
                "failure": {
                    "reason": "workflow_error",
                    "detail": {
                        "message": f"ACP protocol error\n{cause}\n{_PRESERVED}\n{_MARKER}",
                        "category": "transient_infra",
                    },
                },
            },
        }
    ]


def _succeeded_turn_payload(*, later_test_failure: bool) -> list[dict[str, Any]]:
    """A needs-human terminal reached from a success-booked Codex review turn."""
    outcomes: dict[str, dict[str, object]] = {
        # Petri retains a succeeded ACP turn's text under `response`, not
        # `output`.  The terminal has no failure payload that repeats it.
        "review": {"status": "succeeded", "response": "Review begins." + _TURN_CAPACITY},
        "needs_human": {"status": "failed"},
    }
    completed = ["review"]
    if later_test_failure:
        outcomes["janitor"] = {"status": "failed"}
        completed.append("janitor")
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed", "reason": "workflow_error"},
            "checkpoint": {
                "current_node": "needs_human",
                "next_node_id": None,
                "completed_nodes": completed,
                "node_outcomes": outcomes,
            },
            "conclusion": {
                "status": "failed",
                "failure": {"reason": "workflow_error", "detail": {"message": _MARKER}},
            },
        }
    ]


@dataclass(kw_only=True)
class _Runner:
    stdout: str

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def _inspect(*, tmp_path: Path, cause: str) -> FabroInspectResult:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(),
        runner=_Runner(stdout=json.dumps(_payload(cause=cause))),
        cwd=tmp_path,
    ).inspect(run_id=_RUN, timeout_seconds=1)


def _write_repo(
    *,
    repo: Path,
    declare_signature: bool,
    parameterize: bool = True,
    candidate_key: str = _CANDIDATE_KEY,
) -> None:
    """A repository whose `implement` node declares the candidate that ran.

    `candidate_key` is a parameter so one case can declare a DIFFERENT
    entitlement than the plan selected, which is what configuration moving
    mid-run looks like from the terminal.
    """
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    inputs = "[run.inputs]\nimplement_adapter = 'claude-code-acp'\n" if parameterize else ""
    (workflow / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "fabro-sandbox"\n\n'
        + inputs,
        encoding="utf-8",
    )
    (workflow / "workflow.fabro").write_text(
        'digraph ImplementWorkItem {\n    implement [\n        timeout="60s"\n    ]\n}\n',
        encoding="utf-8",
    )
    entry: dict[str, object] = {
        "command": "claude-code-acp",
        "display_name": _IDENTITY.display_name,
        "candidate_key": candidate_key,
        "availability_key": _AVAILABILITY_KEY,
    }
    if declare_signature:
        entry["availability_signatures"] = [_DECLARED_QUOTA]
    (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"acp_nodes": {"implement": entry}}
                }
            }
        ),
        encoding="utf-8",
    )


def _plan(*, tmp_path: Path, resolved: bool = True) -> DispatchPlan:
    """A plan carrying the identity the dispatch SELECTED for `implement`.

    The identity rides the plan rather than being re-read from configuration,
    because that is the resolve-once value the run's own entitlement labels were
    stamped from -- the same source, so the two cannot disagree about which
    candidate ran.
    """
    return DispatchPlan(
        repo=tmp_path,
        work_item_id="bd-ib-26deyw",
        branch="feat/bd-ib-26deyw",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server=None,
        fabro_factory_dev_token=None,
        janitor=("just", "check"),
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
        acp_nodes=(
            AcpNodeResolution(
                nodes={},
                inputs={},
                run_inputs=(),
                candidates={"implement": _IDENTITY},
            )
            if resolved
            else None
        ),
    )


def _outcome(*, tmp_path: Path, cause: str, plan: DispatchPlan) -> DispatchOutcome | None:
    return fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=plan,
        run_id=_RUN,
        inspect=_inspect(tmp_path=tmp_path, cause=cause),
        exit_code=1,
        stderr="",
    )


def test_a_needs_human_terminal_on_a_provider_limit_yields_a_release(
    tmp_path: Path,
) -> None:
    """The measured session-limit ending releases instead of resting blocked."""
    _write_repo(repo=tmp_path, declare_signature=True)

    outcome = _outcome(tmp_path=tmp_path, cause=_SESSION_LIMIT, plan=_plan(tmp_path=tmp_path))

    assert outcome is not None
    assert outcome.stage == "provider-limit-release"
    # NOT a blocked outcome: the clause forbids surfacing this as a needs-human
    # decision, and `escalate_needs_human_block` fires on the `blocked` status
    # alone -- so the status is what keeps the ledger write away from it.
    assert outcome.status != "blocked"
    assert outcome.fabro_run_id == _RUN
    release = outcome.provider_limit_release
    assert release is not None
    assert release.matched is not None
    assert release.matched.cause == "quota"
    assert release.matched.scope == "availability-domain"
    assert release.matched.hold_key == _AVAILABILITY_KEY
    assert release.executed == _IDENTITY
    assert release.factory == "hp"
    assert release.node_attempt == "implement"
    # The preserved-work reference the release OBSERVED, read off the
    # terminal's own sentinel rather than derived from the run id.
    assert f"refs/heads/needs-human/{_RUN}" in release.recovery_source


def test_an_unclassifiable_failure_still_rests_at_blocked_needs_human(
    tmp_path: Path,
) -> None:
    """The control: the human route survives for a failure nothing classifies.

    Same repository, same declared signature, same needs-human terminal -- only
    the recorded cause differs, and it is the measured infrastructure fault
    that ended this item's own earlier dispatch (run 01M54MHMQKXG, "the socket
    connection was closed unexpectedly").
    """
    _write_repo(repo=tmp_path, declare_signature=True)

    outcome = _outcome(
        tmp_path=tmp_path,
        cause="The socket connection was closed unexpectedly",
        plan=_plan(tmp_path=tmp_path),
    )

    assert outcome is not None
    assert outcome.status == "blocked"
    assert outcome.stage == "fabro-run"
    assert outcome.provider_limit_release is None


def test_an_unreadable_candidate_resolution_mints_no_typed_hold(tmp_path: Path) -> None:
    """A resolution that could not be READ still releases, on the legacy arm.

    MEASURED, and it corrected this test's own first expectation. A workflow
    parameterizing no adapter yields no chains, which
    `resolve_dispatch_candidates` reports as unreadable rather than empty, so
    no signature table can grade the failure. But the recorded cause already
    carries the TYPED provider-usage-limit flag -- `fabro_failure_detail_from_
    payload` sets it, with provider `anthropic`, for this very sentence -- and
    the clause releases a typed provider-limit failure "without inventing a
    candidate identity". So the item is released and NO typed hold is minted:
    there is no entitlement one could be scoped by, and the existing legacy
    provider observation is what covers it.

    The blinded-gauge worry the first draft of this test encoded is real but
    belongs one level down: what must not happen is a TYPED hold scoped to an
    entitlement nobody observed, and `matched is None` is that assertion.
    """
    _write_repo(repo=tmp_path, declare_signature=True, parameterize=False)

    outcome = _outcome(tmp_path=tmp_path, cause=_SESSION_LIMIT, plan=_plan(tmp_path=tmp_path))

    assert outcome is not None
    assert outcome.stage == "provider-limit-release"
    release = outcome.provider_limit_release
    assert release is not None
    assert release.matched is None
    assert release.legacy_provider == "anthropic"


def test_a_dispatch_carrying_no_acp_resolution_invents_no_identity(tmp_path: Path) -> None:
    """A plan naming no selected candidate releases without inventing one.

    The plan is what records which candidate the dispatch selected, so a plan
    carrying no resolution names none. The typed flag still releases it, and
    the release records no executed entitlement at all rather than guessing
    one from configuration -- which is the difference between reporting what
    ran and reporting what would run today.
    """
    _write_repo(repo=tmp_path, declare_signature=True)

    outcome = _outcome(
        tmp_path=tmp_path, cause=_SESSION_LIMIT, plan=_plan(tmp_path=tmp_path, resolved=False)
    )

    assert outcome is not None
    assert outcome.stage == "provider-limit-release"
    release = outcome.provider_limit_release
    assert release is not None
    assert release.matched is None
    assert release.executed is None
    assert release.legacy_provider == "anthropic"


def test_a_candidate_declaring_no_signature_takes_the_legacy_arm(tmp_path: Path) -> None:
    """A declared candidate with no signature table mints no typed hold.

    The entitlement IS known here -- the plan selected it and configuration
    declares it -- so this is not the identity-less posture. What is missing is
    the operator's own measurement, so nothing can classify the failure and no
    scoped hold may be invented. The typed flag still releases the item.

    This is the LIVE arm for this repository today, which is why it is asserted
    rather than left implicit: measured 2026-10-17, its eight structured
    `acp_nodes` candidates all resolve `builtin=False` and declare no
    `availability_signatures`, so every one of them lands here.
    """
    _write_repo(repo=tmp_path, declare_signature=False)

    outcome = _outcome(tmp_path=tmp_path, cause=_SESSION_LIMIT, plan=_plan(tmp_path=tmp_path))

    assert outcome is not None
    assert outcome.stage == "provider-limit-release"
    release = outcome.provider_limit_release
    assert release is not None
    assert release.matched is None
    assert release.legacy_provider == "anthropic"
    # The entitlement that ran is still REPORTED, because the plan recorded it;
    # only the typed hold is withheld.
    assert release.executed == _IDENTITY


def test_a_resolution_declaring_a_different_entitlement_mints_no_typed_hold(
    tmp_path: Path,
) -> None:
    """Configuration that moved since dispatch cannot grade the attempt that ran.

    The resolution is perfectly readable and carries a fully-signatured
    candidate -- it simply is not the one the dispatch selected. Grading the
    failing attempt against it would apply one entitlement's measurements to
    another's refusal and could mint a hold scoped to a candidate that never
    ran, so the match is by entitlement PAIR and a miss falls to the legacy arm.
    """
    _write_repo(repo=tmp_path, declare_signature=True, candidate_key="claude-successor")

    outcome = _outcome(tmp_path=tmp_path, cause=_SESSION_LIMIT, plan=_plan(tmp_path=tmp_path))

    assert outcome is not None
    assert outcome.stage == "provider-limit-release"
    release = outcome.provider_limit_release
    assert release is not None
    assert release.matched is None
    assert release.legacy_provider == "anthropic"


def test_a_green_run_is_not_examined_for_a_release_at_all(tmp_path: Path) -> None:
    """A succeeded run has no unrecovered failing attempt to release on.

    The clause selects "the unrecovered failure responsible for the run's
    terminal disposition", and says an earlier failed attempt that later
    succeeded "MUST NOT release a successful run".
    """
    _write_repo(repo=tmp_path, declare_signature=True)

    assert (
        fabro_run_terminal_outcome(
            outcome_type=DispatchOutcome,
            plan=_plan(tmp_path=tmp_path),
            run_id=_RUN,
            inspect=None,
            exit_code=0,
            stderr="",
        )
        is None
    )


def test_a_success_booked_codex_capacity_turn_releases_from_needs_human(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The review's final output, rather than terminal failure data, selects release."""
    signatures = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._acp_builtin_signatures"
    )
    rendered = RenderedCandidate(
        candidate=AcpCandidate(
            adapter=AcpAdapter(command="codex-acp", args=(), env={}),
            identity=_REVIEW_IDENTITY,
            signatures=signatures.builtin_availability_signatures(availability_key="codex"),
        ),
        builtin=True,
    )
    outcome_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_outcome"
    )
    monkeypatch.setattr(outcome_module, "_rendered_for", lambda **_: rendered)
    plan = replace(
        _plan(tmp_path=tmp_path),
        acp_nodes=AcpNodeResolution(
            nodes={}, inputs={}, run_inputs=(), candidates={"review": _REVIEW_IDENTITY}
        ),
    )
    inspect = FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(),
        runner=_Runner(stdout=json.dumps(_succeeded_turn_payload(later_test_failure=False))),
        cwd=tmp_path,
    ).inspect(run_id=_RUN, timeout_seconds=1)

    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=plan,
        run_id=_RUN,
        inspect=inspect,
        exit_code=1,
        stderr="",
    )

    assert outcome is not None
    assert outcome.stage == "provider-limit-release"
    assert outcome.provider_limit_release is not None
    assert outcome.provider_limit_release.source == "turn.final_output"


def test_a_later_command_failure_keeps_its_route_after_a_capacity_turn(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A later failed janitor is the terminal cause, so the review cannot release it."""
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_outcome._rendered_for",
        lambda **_: None,
    )
    plan = replace(
        _plan(tmp_path=tmp_path),
        acp_nodes=AcpNodeResolution(
            nodes={}, inputs={}, run_inputs=(), candidates={"review": _REVIEW_IDENTITY}
        ),
    )
    inspect = FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(),
        runner=_Runner(stdout=json.dumps(_succeeded_turn_payload(later_test_failure=True))),
        cwd=tmp_path,
    ).inspect(run_id=_RUN, timeout_seconds=1)

    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=plan,
        run_id=_RUN,
        inspect=inspect,
        exit_code=1,
        stderr="",
    )

    assert outcome is not None
    assert outcome.stage == "fabro-run"
    assert outcome.provider_limit_release is None
