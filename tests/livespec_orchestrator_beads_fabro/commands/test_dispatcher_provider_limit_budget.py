"""A provider-limit release spends no cap budget and sets no typed flag it did not observe.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Provider-limit release and re-dispatch" (`bd-ib-6itdjz`,
Scenario 127) makes two prohibitions that are about what a release must NOT
do, and Scenario 127 grades them as "no rework cap budget ... is consumed" and
"the typed provider-usage-limit flag is not set":

- "A provider-limit release MUST NOT consume any budget of the three rework
  caps, MUST NOT count as an item-attributable terminal ... and MUST NOT be
  surfaced as a needs-human decision."
- "The typed provider-usage-limit flag ... remains specific to usage or spend
  ceilings and MUST NOT be set merely because another eligible availability
  cause triggers release."

BOTH ARE ABSENCES, which is exactly why they need their own tests. Every
assertion elsewhere in this change passes whether or not these hold: a release
that also bounced the slice to `backlog`, or that stamped a rework label, or
that reported a quota ceiling for a removed model, would satisfy the status,
the record and the ledger transition identically. Nothing downstream
announces any of it.

THE NON-CONVERGENCE AND REWORK ARMS ARE ASSERTED THROUGH THE REAL GROUP, not
by reading a predicate. `dispose_terminal_routing` runs all three non-green
routes, so a release passed through it exercises the very sequence a dispatch
takes -- which is the only way to show the bounce DECLINED rather than that
somebody believed it would.

THE CONTROL IS THE SAME SEQUENCE WITH A NON-CONVERGENCE OUTCOME. Without it,
a group that had stopped calling the bounce at all would satisfy every
assertion in the first test while silently retiring a route that must still
fire for its own status.

THE FLAG TEST USES A `model_unsupported` SIGNATURE DECLARED FOR
`protocol.message`, deliberately. The built-in `model_unsupported` mapping is
sourced on the terminal diagnostic, and the terminal path carries ONE text
channel which is the ACP protocol message -- so a repository wanting that
cause released from a terminal declares it for the channel the record actually
carries. That is the live shape of this assertion, and asserting it against
the built-in source would assert a path no terminal can reach.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_cap_mutations import update_work_item_cap
from livespec_orchestrator_beads_fabro._store_rework_mutations import (
    LABEL_REWORK_PENDING,
    update_work_item_rework_pending,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidateIdentity
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    AcpAvailabilityFailure,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import AcpNodeResolution
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    NON_CONVERGED_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    ACCEPTANCE_REWORK_CAP_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    ProviderLimitRelease,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_routing import (
    dispose_terminal_routing,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    FabroPort,
    FabroTarget,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-plbudget"
_RUN = "01M52R2WND7Y"
_NOW = "2026-10-16T19:20:00Z"
# The measured ChatGPT-account diagnostic naming the requested model as
# unsupported, which `_acp_builtin_signatures` records from the v107 `pr`-node
# outage. Declared below for `protocol.message`, the one channel a terminal's
# recorded cause chain carries.
_MODEL_UNSUPPORTED = (
    "requested model gpt-5.4-mini is not supported when using codex with a chatgpt account"
)
_IDENTITY = AcpCandidateIdentity(
    display_name="Codex ACP primary",
    candidate_key="codex-primary",
    availability_key="codex-team",
)


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="A dispatched slice released on a provider limit",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _release_outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="provider-limit-release",
        stage="provider-limit-release",
        pr_number=None,
        merge_sha=None,
        detail="",
        fabro_run_id=_RUN,
        provider_limit_release=ProviderLimitRelease(
            factory="hp",
            run_id=_RUN,
            node_attempt="implement",
            matched=AcpAvailabilityFailure(
                cause="quota",
                scope="availability-domain",
                hold_key="codex-team",
                availability_key="codex-team",
                candidate_key=None,
                source="protocol.message",
            ),
            executed=_IDENTITY,
            legacy_provider=None,
            recovery_source="the tree was preserved on refs/heads/needs-human/01M52R2WND7Y",
        ),
    )


def _journal(*, tmp_path: Path) -> JournalFile:
    path = tmp_path / "journal.jsonl"
    _ = path.write_text("", encoding="utf-8")
    return JournalFile(path=path)


def _stages(*, journal: JournalFile) -> list[object]:
    return [
        json.loads(line).get("stage")
        for line in journal.path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _labels(*, item_id: str) -> list[str]:
    record = make_beads_client(config=_config()).show_issue(issue_id=item_id)
    raw = record.get("labels", [])
    return sorted(label for label in raw if isinstance(label, str))


def test_a_release_journals_no_cap_record_and_leaves_the_rework_labels(
    tmp_path: Path,
) -> None:
    """Neither cap record is written, and the cap BUDGET labels are untouched."""
    append_work_item(path=_config(), item=_item())
    # A per-item cap OVERRIDE already standing, which is what "rework-cap
    # labels" names: the budget the clause forbids a release from consuming.
    # Set to a real override so "left as they were" is a claim about a value
    # rather than about an item that carried none.
    update_work_item_cap(
        path=_config(),
        item_id=_ITEM_ID,
        label_prefix=ACCEPTANCE_REWORK_CAP_LABEL,
        value="3",
    )
    # And the rework STATE marker beside it, which this test deliberately does
    # NOT require to survive -- see the assertion at the end for why.
    update_work_item_rework_pending(path=_config(), item_id=_ITEM_ID, value=True)
    before = _labels(item_id=_ITEM_ID)
    assert f"{ACCEPTANCE_REWORK_CAP_LABEL}3" in before
    assert LABEL_REWORK_PENDING in before
    journal = _journal(tmp_path=tmp_path)

    dispose_terminal_routing(
        repo=_repo(tmp_path=tmp_path),
        item=_item(),
        outcome=_release_outcome(),
        journal=journal,
        now_iso=_NOW,
    )

    stages = _stages(journal=journal)
    assert "non-convergence-bounce" not in stages
    assert "acceptance-rework-cap-exceeded" not in stages
    # The release DID happen, so the absences above are about a route that ran
    # rather than about a disposition that never fired.
    assert "provider-limit-release" in stages
    after = _labels(item_id=_ITEM_ID)
    # THE CAP BUDGET SURVIVES, which is the clause's "MUST NOT consume any
    # budget of the three rework caps": the override an operator set is still
    # exactly what it was, so the next dispatch is graded against the same
    # allowance rather than a silently reset one.
    assert f"{ACCEPTANCE_REWORK_CAP_LABEL}3" in after
    # MEASURED, and recorded because the plausible expectation is the wrong
    # one: `rework:pending` is CLEARED, and that is correct. It is a rework
    # STATE marker rather than cap budget, and `update_work_item_status` clears
    # it on every transition out of `active` by design -- its own docstring
    # calls that "what makes the 'an item leaving `active` has the label
    # cleared' invariant structural rather than something each disposition has
    # to remember". The stall release and every operator valve move share that
    # seam, so a release that preserved the marker would be the anomaly: the
    # item would sit `ready` while advertising a rework pass that is not
    # pending on anything.
    assert LABEL_REWORK_PENDING not in after
    assert after == sorted(set(before) - {LABEL_REWORK_PENDING})


def test_the_group_still_bounces_a_genuine_non_convergence(tmp_path: Path) -> None:
    """The control: the bounce route is intact for the status it owns.

    Without this, a routing group that had stopped calling the bounce entirely
    would satisfy every absence asserted above.

    THE BOUNCE ROW IS ASSERTED PRESENT, not merely the release row absent, and
    the marker is IMPORTED rather than spelled. Both halves were measured
    wrong: this control first carried the paraphrase `NON_CONVERGED` in its
    detail, which does not contain `LIVESPEC_NON_CONVERGED`, so
    `is_non_convergence_outcome` declined and the whole routing group journaled
    NOTHING -- an empty journal that satisfied a lone "the release did not fire"
    assertion exactly as a live bounce would. A control that cannot observe the
    route it is a control for is not a control, so it asserts the row the
    bounce writes.
    """
    append_work_item(path=_config(), item=_item())
    journal = _journal(tmp_path=tmp_path)

    dispose_terminal_routing(
        repo=_repo(tmp_path=tmp_path),
        item=_item(),
        outcome=DispatchOutcome(
            work_item_id=_ITEM_ID,
            status="failed",
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail=f"{NEEDS_HUMAN_MARKER}\nreview did not converge: {NON_CONVERGED_MARKER}",
            fabro_run_id=_RUN,
        ),
        journal=journal,
        now_iso=_NOW,
    )

    stages = _stages(journal=journal)
    # THE ROUTE RAN: this is what makes the absences in the test above claims
    # about a declining predicate rather than about a sequence that calls
    # nothing.
    assert "non-convergence-bounce" in stages
    assert "provider-limit-release" not in stages


def _unsupported_payload() -> list[dict[str, object]]:
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
                "timestamp": _NOW,
                "failure": {
                    "reason": "workflow_error",
                    "detail": {
                        "message": f"ACP protocol error\n{_MODEL_UNSUPPORTED}\n{NEEDS_HUMAN_MARKER}",
                        "category": "deterministic",
                    },
                },
            },
        }
    ]


class _Runner:
    def __init__(self, *, stdout: str) -> None:
        self.stdout = stdout

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


def _inspect(*, tmp_path: Path) -> FabroInspectResult:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(),
        runner=_Runner(stdout=json.dumps(_unsupported_payload())),
        cwd=tmp_path,
    ).inspect(run_id=_RUN, timeout_seconds=1)


def _write_repo(*, repo: Path) -> None:
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "fabro-sandbox"\n\n'
        "[run.inputs]\nimplement_adapter = 'codex-acp'\n",
        encoding="utf-8",
    )
    (workflow / "workflow.fabro").write_text(
        'digraph ImplementWorkItem {\n    implement [\n        timeout="60s"\n    ]\n}\n',
        encoding="utf-8",
    )
    (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "acp_nodes": {
                            "implement": {
                                "command": "codex-acp",
                                "display_name": _IDENTITY.display_name,
                                "candidate_key": _IDENTITY.candidate_key,
                                "availability_key": _IDENTITY.availability_key,
                                "availability_signatures": [
                                    {
                                        "source": "protocol.message",
                                        "cause": "model_unsupported",
                                        "scope": "candidate",
                                        "all_literals": [
                                            "requested model",
                                            "is not supported when using codex with a "
                                            "chatgpt account",
                                        ],
                                    }
                                ],
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_a_candidate_scoped_model_unsupported_release_sets_no_usage_limit_flag(
    tmp_path: Path,
) -> None:
    """An eligible cause that is NOT a ceiling releases without claiming one."""
    repo = tmp_path / "unsupported"
    repo.mkdir()
    _write_repo(repo=repo)

    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=DispatchPlan(
            repo=repo,
            work_item_id=_ITEM_ID,
            branch=f"feat/{_ITEM_ID}",
            workflow_toml=repo / "workflow.toml",
            goal_file=repo / "goal.txt",
            fabro_bin="fabro",
            fabro_factory_name="hp",
            fabro_factory_server=None,
            fabro_factory_dev_token=None,
            janitor=("just", "check"),
            janitor_checkout=repo / ".janitor",
            janitor_core_checkout=repo / ".janitor" / ".livespec-core",
            janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
            janitor_core_ref="master",
            review_fix_visit_cap=3,
            merge_on_review_cap_outcome="succeeded",
            # The identity this dispatch SELECTED, which is what lets the
            # declared signature grade the attempt at all.
            acp_nodes=AcpNodeResolution(
                nodes={}, inputs={}, run_inputs=(), candidates={"implement": _IDENTITY}
            ),
        ),
        run_id=_RUN,
        inspect=_inspect(tmp_path=tmp_path),
        exit_code=1,
        stderr="",
    )

    assert outcome is not None
    # It IS released -- an eligible availability cause, so the clause applies.
    assert outcome.stage == "provider-limit-release"
    release = outcome.provider_limit_release
    assert release is not None
    assert release.matched is not None
    assert release.matched.cause == "model_unsupported"
    # CANDIDATE-scoped: the account is fine and one model is not, so a domain
    # hold would strand every sibling candidate on the same provider.
    assert release.matched.scope == "candidate"
    assert release.matched.candidate_key == _IDENTITY.candidate_key
    # AND THE POINT OF THIS TEST: the typed provider-usage-limit flag stays
    # FALSE. A removed model is not a spent allowance, and the clause forbids
    # setting the flag "merely because another eligible availability cause
    # triggers release". A release that set it would make
    # `record_provider_exhaustion_if_observed` mint a legacy ceiling record for
    # an account that never hit one, refusing later dispatches on an intact
    # allowance.
    assert outcome.provider_usage_limit is False
    assert outcome.provider_usage_limit_provider is None
