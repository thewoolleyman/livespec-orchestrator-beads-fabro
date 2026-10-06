"""Three run shapes carrying plan slice S4's repaired calibration signals.

Binds `SPECIFICATION/scenarios.md` "Scenario 12 — Dispatcher emits calibration
telemetry" for the fields plan slice S4 (`bd-ib-tbgxm4`) repaired, and
"Scenario 11 — Dispatcher bounces a non-converging slice to backlog" for the
bounce among them. The existing Scenario 12 journey pins the ratified field set;
this one pins what the repaired fields READ on the three shapes whose readings
used to be indistinguishable:

- a SUCCESSFUL run, which carried every proxy before and still does;
- a FAILED POST-PR run, which carried NO churn measurement at all, because
  `merged_pr_diff_size` is read only for a green outcome;
- a CAP-TRIGGERED BOUNCE, which was journaled as `bounced_to_regroom: false`
  while the Dispatcher moved the item to `backlog`.

Measured across 445 of this repository's own records (plan research,
`plan/factory-test-first-enforcement/research/opening-research-2026-09-30.md`):
the churn proxy was present on all 292 converged runs and NONE of the 153
non-converged ones, and the bounce flag was true on none of them.

BOTH PROJECTIONS, deliberately. The journal is what the analysis pass reads and
the span is what reaches Honeycomb, and they are built by different functions
over the same record — so a field can land on one and be missing from the other
with nothing failing. The span leg also has a second filter behind it: the
receive stage rebuilds attributes from `ATTRIBUTE_ALLOWLIST`, so a key absent
from that allowlist is dropped with no error and the signal arrives silently
empty. This file asserts the key reaches the span AND survives that allowlist.

Hermetic: the real `dispatcher.main(argv=["dispatch", ...])` CLI drives the real
store seam against the in-memory `FakeBeadsClient`, with `run_dispatch` replaced
by a stand-in that returns one terminal and — for the two runs that opened a
pull request — appends the PR-open record through the PRODUCTION record builder
on the real journal the engine would have used.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_non_convergence_cap import (
    FIX_LOOP_VISIT_CAP,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NON_CONVERGED_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_open_diff import (
    pr_open_diff_record,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import is_allowed_attr
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_FLEET_MANIFEST_TEXT = (
    "// .livespec-fleet-manifest.jsonc — canned test copy\n"
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "repo", "class": "impl-plugin" }\n'
    "  ]\n"
    "}\n"
)
_COMMITTED_WORKFLOW_TOML = (
    '[workflow]\ngraph = "graph.toml"\n\n[run.environment]\nid = "fabro-sandbox"\n'
)
_MINIMAL_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)

_ITEM_ID = "livespec-impl-beads-slice1"
_PR_NUMBER = 4242
_PR_OPEN_DIFF_SIZE = 145
# THREE gradeable assertions in the Definition of Done section, and three more
# bullets under a later heading that are not assertions at all. The retired
# description regex read this item as six.
_DESCRIPTION = (
    "## Definition of Done\n"
    "\n"
    "- The repaired assertion count comes from the sanctioned parser.\n"
    "- The PR-open diff size survives a failed terminal.\n"
    "- A cap-triggered bounce reports itself as bounced.\n"
    "\n"
    "References: ## Grooming and slice-size calibration\n"
    "\n"
    "## Context\n"
    "\n"
    "- a context bullet\n"
    "- another context bullet\n"
    "- a third context bullet\n"
)
_EXPECTED_ASSERTION_COUNT = 3


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment + a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("fabro-s4-proxies")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A dispatched slice",
        description=_DESCRIPTION,
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo_with_workflow(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow.parent / "graph.toml").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return repo, workflow


def _stand_in(
    *, outcome: DispatchOutcome, opened_a_pull_request: bool
) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in that records the PR-open size as the engine does.

    The record goes onto the REAL journal the stand-in is handed, through the
    PRODUCTION record builder — so the key and stage the calibration derivation
    reads back are the ones the engine writes, not a literal this test invented.
    """

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        if opened_a_pull_request:
            journal = kwargs["journal"]
            assert hasattr(journal, "append")
            journal.append(
                record=pr_open_diff_record(
                    work_item_id=plan.work_item_id,
                    pr_number=_PR_NUMBER,
                    diff_size=_PR_OPEN_DIFF_SIZE,
                )
            )
        return replace(outcome, work_item_id=plan.work_item_id)

    return _run_dispatch


def _green() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="green",
        stage="done",
        pr_number=_PR_NUMBER,
        merge_sha="cafe01",
        detail="merged, post-merge janitor green",
    )


def _failed_after_pr() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="failed",
        stage="merge-poll",
        pr_number=_PR_NUMBER,
        merge_sha=None,
        detail="PR did not reach MERGED within the poll budget",
    )


def _cap_triggered_bounce() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=f"{NON_CONVERGED_MARKER}: janitor fix-loop cap hit without converging",
    )


def _dispatch(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    outcome: DispatchOutcome,
    opened_a_pull_request: bool,
) -> tuple[int, Path]:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    monkeypatch.setattr(
        _dispatcher_loop,
        "run_dispatch",
        _stand_in(outcome=outcome, opened_a_pull_request=opened_a_pull_request),
    )
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            _ITEM_ID,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    return exit_code, repo


def _calibration_record(*, repo: Path) -> dict[str, object]:
    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    calibration = [record for record in records if record.get("stage") == "calibration"]
    assert len(calibration) == 1, f"expected one calibration record, got {len(calibration)}"
    return calibration[0]


def _span_attributes(*, repo: Path) -> dict[str, object]:
    """The `dispatcher.calibration` span's attributes, decoded from OTLP JSON.

    Selected BY SPAN NAME. The same file also receives the reconcile pass's own
    span, so a reader that took the only line, or the first, would be reading a
    different span's attributes and reporting every repaired key as absent.
    """
    spans_path = repo / "tmp" / "fabro-dispatch-journal-calibration-spans.jsonl"
    spans = [
        span
        for line in spans_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for scope in json.loads(line)["resourceSpans"][0]["scopeSpans"]
        for span in scope["spans"]
        if span["name"] == "dispatcher.calibration"
    ]
    assert len(spans) == 1, f"expected one calibration span, got {len(spans)}"
    span = spans[0]
    decoded: dict[str, object] = {}
    for entry in span["attributes"]:
        value = entry["value"]
        if "intValue" in value:
            decoded[entry["key"]] = int(value["intValue"])
        elif "boolValue" in value:
            decoded[entry["key"]] = bool(value["boolValue"])
        else:
            decoded[entry["key"]] = value["stringValue"]
    return decoded


def _stored_status() -> str:
    return materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID].status


# ---------------------------------------------------------------------------
# A SUCCESSFUL run.
# ---------------------------------------------------------------------------


def test_a_successful_run_exposes_every_repaired_field_on_both_projections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exit_code, repo = _dispatch(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        outcome=_green(),
        opened_a_pull_request=True,
    )

    assert exit_code == 0
    record = _calibration_record(repo=repo)
    assert record["converged"] is True
    assert record["acceptance_count"] == _EXPECTED_ASSERTION_COUNT
    assert record["acceptance_count_source"] == "description-definition-of-done"
    assert record["pr_open_diff_size"] == _PR_OPEN_DIFF_SIZE
    assert record["bounced_to_regroom"] is False
    assert record["bounce_cap"] is None
    assert record["bounce_cap_observed"] is None

    attributes = _span_attributes(repo=repo)
    assert attributes["acceptance_count"] == _EXPECTED_ASSERTION_COUNT
    assert attributes["acceptance_count_source"] == "description-definition-of-done"
    assert attributes["pr_open_diff_size"] == _PR_OPEN_DIFF_SIZE
    assert attributes["bounced_to_regroom"] is False


# ---------------------------------------------------------------------------
# A FAILED POST-PR run.
# ---------------------------------------------------------------------------


def test_a_failed_post_pr_run_carries_the_churn_the_merged_proxy_cannot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The repair's whole point: a non-green terminal now carries a churn reading."""
    exit_code, repo = _dispatch(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        outcome=_failed_after_pr(),
        opened_a_pull_request=True,
    )

    assert exit_code == 1
    record = _calibration_record(repo=repo)
    assert record["converged"] is False
    assert record["outcome_class"] == "failed:merge-poll"
    # The merged-PR proxy is absent — it is read only for a green outcome — and
    # the PR-open one is present. That contrast IS the repair.
    assert record["merged_pr_diff_size"] is None
    assert record["pr_open_diff_size"] == _PR_OPEN_DIFF_SIZE
    assert record["acceptance_count"] == _EXPECTED_ASSERTION_COUNT
    # A failure is not a bounce: this run is not routed back to grooming.
    assert record["bounced_to_regroom"] is False
    assert _stored_status() != "backlog"

    attributes = _span_attributes(repo=repo)
    assert attributes["pr_open_diff_size"] == _PR_OPEN_DIFF_SIZE
    assert attributes["acceptance_count"] == _EXPECTED_ASSERTION_COUNT


# ---------------------------------------------------------------------------
# A CAP-TRIGGERED BOUNCE.
# ---------------------------------------------------------------------------


def test_a_cap_triggered_bounce_reports_itself_as_bounced_and_names_its_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The item reaches `backlog` AND the record says so, which it did not before."""
    exit_code, repo = _dispatch(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        outcome=_cap_triggered_bounce(),
        opened_a_pull_request=False,
    )

    assert exit_code == 1
    # The lifecycle transition actually happened, through the store seam.
    assert _stored_status() == "backlog"
    record = _calibration_record(repo=repo)
    assert record["bounced_to_regroom"] is True
    assert record["bounce_cap"] == FIX_LOOP_VISIT_CAP
    # No observation: the visit counter lives inside the sandbox graph, so the
    # field is an explicit null rather than the configured cap restated.
    assert record["bounce_cap_observed"] is None
    assert record["acceptance_count"] == _EXPECTED_ASSERTION_COUNT
    # This run opened no pull request, so "where applicable" excludes the churn.
    assert record["pr_open_diff_size"] is None
    assert record["merged_pr_diff_size"] is None

    attributes = _span_attributes(repo=repo)
    assert attributes["bounced_to_regroom"] is True
    assert attributes["bounce_cap"] == FIX_LOOP_VISIT_CAP
    assert attributes["acceptance_count"] == _EXPECTED_ASSERTION_COUNT


def test_the_bounce_journals_the_cap_beside_the_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The escalation record itself names the cap, not only the calibration record."""
    _exit_code, repo = _dispatch(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        outcome=_cap_triggered_bounce(),
        opened_a_pull_request=False,
    )

    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    bounces = [
        json.loads(line)
        for line in text.splitlines()
        if line.strip() and json.loads(line).get("stage") == "non-convergence-bounce"
    ]

    assert len(bounces) == 1
    assert bounces[0]["bounce_cap"] == FIX_LOOP_VISIT_CAP
    assert bounces[0]["bounce_cap_observed"] is None


# ---------------------------------------------------------------------------
# The egress filter behind the span leg.
# ---------------------------------------------------------------------------


def test_every_repaired_span_key_survives_the_receive_allowlist() -> None:
    """A key absent from the allowlist is dropped with NO error at enrich time.

    Which is the failure mode this guards: the span would reach Honeycomb looking
    healthy and carrying none of the repaired fields, exactly as O4's `run_turn`
    scalars did on 2026-07-19.
    """
    for key in (
        "acceptance_count_source",
        "pr_open_diff_size",
        "bounce_cap",
        "bounce_cap_observed",
    ):
        assert is_allowed_attr(key=key) is True
