"""Tests for the `dispatcher` CLI (ledger-check / dispatch / loop) and its
private planning, engine, ledger-check, and io layers.

The hermetic `FakeBeadsClient` is the Ledger backend (autouse fixture).
The engine is driven through a scripted in-memory `CommandRunner`; the
production `ShellCommandRunner` is exercised with real `sys.executable -c`
subprocesses, mirroring `test_orchestrator`'s injected-CLI approach.

C-mode (Architecture C, Fabro-owned docker sandbox) specifics covered
here: the run-config overlay materialization (mode-600, absolute graph
rewrite, post-run cleanup, and the appended env table carrying the
CLAUDE_CODE_OAUTH_TOKEN value read from the Dispatcher's process env —
the overlay IS the run-scoped credential projection; fabro `{{ env }}`
interpolation cannot deliver it because the server spawns the
resolving worker under a fail-closed env allowlist), the
CLAUDE_CODE_OAUTH_TOKEN fail-fast (an absent variable leaves nothing
to project, so the Dispatcher refuses to dispatch without it), the
sandbox sibling-clone provisioning (fleet-manifest-derived depth-1
clone prepare steps plus the LIVESPEC_SIBLING_CLONES_ROOT env key in
the same overlay, so cross-repo checks resolve family siblings inside
the sandbox), the dispatch lifecycle (fabro run from the repo's
primary checkout with no host worktree prep BEFORE the run; the
post-merge janitor runs in a fresh detached worktree of the merged
ref — never the host primary's working tree — with provisioning
failures classifying as `janitor-env-degraded` green outcomes rather
than work-item failures, per livespec-impl-beads-cgd), and the
`blocked` third terminal state (run parked at the in-loop human gate;
`fabro attach` is the answer path, never auto-resumed).
"""

import argparse
import inspect
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast

import pytest
from coverage import Coverage
from coverage.files import GlobMatcher, prep_patterns
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission,
    _dispatcher_admission_eligibility,
    _dispatcher_completion,
    _dispatcher_dispatch_lock,
    _dispatcher_goal,
    _dispatcher_ledger_close,
    _dispatcher_loop,
    _dispatcher_loop_command,
    _dispatcher_loop_selection,
    _dispatcher_provider_exhaustion,
    _dispatcher_reflection,
    _dispatcher_run_commands,
    _dispatcher_self_update,
    _dispatcher_sibling_clones,
    _sibling_status_lookup,
    dispatcher,
)
from livespec_orchestrator_beads_fabro.commands import next as next_command
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_check_suite_view import (
    janitor_check_suite_from_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim import (
    ActiveClaimAccounting,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_core_provisioning_view import (
    FLEET_JANITOR_CORE_REPO_URL,
    UNRESOLVED_JANITOR_CORE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    DEFAULT_SANDBOX_GH_REFRESH_ROOT,
    MAX_PREPARE_STEP_BYTES,
    SANDBOX_GH_REFRESH_ROOT_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_install_recipe import (
    janitor_bootstrap_recipe_from_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GithubTokenEnvRunner,
    JournalFile,
    ShellCommandRunner,
    WatchedFabroLauncher,
    _decode,  # pyright: ignore[reportPrivateUsage]
    utc_now_iso,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_checks import run_janitor_checks
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import (
    LedgerFinding,
    run_ledger_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import ready_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    FleetMembers,
    SiblingClones,
    build_plan,
    item_sizing_warnings,
    janitor_argv,
    janitor_bootstrap_argv,
    janitor_checkout_path,
    janitor_core_clone_argv,
    janitor_core_ref_from_config,
    janitor_core_repo_url_from_config,
    janitor_trust_argv,
    janitor_venue_contains_merge_argv,
    janitor_worktree_add_argv,
    janitor_worktree_remove_argv,
    parse_fleet_members,
    parse_pr_view,
    pr_arm_argv,
    pr_update_branch_argv,
    pr_view_argv,
    pull_primary_argv,
    render_goal,
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_run_claim import (
    release_pre_run_claim_if_needed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_gate import (
    ReviewGateEmission,
    ReviewGateTelemetry,
    review_gate_request_line,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    github_token_supplier,
    post_verdict_runner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones import (
    fetch_fleet_manifest_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_spec_checks import run_spec_checks
from livespec_orchestrator_beads_fabro.commands._dispatcher_spec_commitments import (
    Obligation,
    collect_obligations_and_supersedes,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    FabroPort,
    FabroTarget,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
    fabro_status_kind_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    default_node_timeouts,
    derive_fabro_timeout_seconds,
)
from livespec_orchestrator_beads_fabro.commands._otel_enrich import (
    CorrelationJoin,
    correlation_keys_from_attrs,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import (
    ATTRIBUTE_ALLOWLIST,
    is_allowed_attr,
)
from livespec_orchestrator_beads_fabro.commands.detect_impl_gaps import detect_rules
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import (
    WorkItemComment,
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.cross_repo.types import CrossRepoManifest
from livespec_runtime.github_auth.errors import GithubAppAuthError

_GITHUB_APP_ENV_KEYS = (
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_API_URL",
)


@pytest.fixture(autouse=True)
def _clear_github_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep overlay assertions independent from factory credential injection."""
    for key in _GITHUB_APP_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_dispatcher_plan_decomposition_contract() -> None:
    base = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    assert (base / "_dispatcher_fabro_argv.py").is_file()
    assert (base / "_dispatcher_run_status.py").is_file()
    assert (base / "_dispatcher_overlay.py").is_file()

    from livespec_orchestrator_beads_fabro.commands import (
        _dispatcher_fabro_argv,
        _dispatcher_goal,
        _dispatcher_host_only,
        _dispatcher_overlay,
        _dispatcher_plan,
        _dispatcher_run_status,
    )

    assert set(_dispatcher_fabro_argv.__all__) == {
        "CODEX_ADAPTER_BASE",
        "CODEX_ADAPTER_COMMAND",
        "CODEX_AGENT_MODE_READ_ONLY",
        "CODEX_AGENT_MODE_WRITE",
        "CODEX_IMPLEMENTER_ADAPTER",
        "FleetMembers",
        "codex_adapter",
        "janitor_argv",
        "janitor_bootstrap_argv",
        "janitor_checkout_path",
        "janitor_checkout_provision_argv",
        "janitor_core_checkout_path",
        "janitor_core_clone_argv",
        "janitor_core_ref_from_config",
        "janitor_core_repo_url_from_config",
        "janitor_reconcile_checkout_path",
        "janitor_trust_argv",
        "janitor_venue_contains_merge_argv",
        "janitor_worktree_add_argv",
        "janitor_worktree_remove_argv",
        "parse_fleet_members",
        "pr_arm_argv",
        "pr_update_branch_argv",
        "pr_view_argv",
        "pull_primary_argv",
    }
    assert set(_dispatcher_run_status.__all__) == {
        "PrView",
        "parse_pr_view",
    }
    assert set(_dispatcher_overlay.__all__) == {
        "CORE_PLUGIN_ROOT_ENV_VAR",
        "CURRENCY_GATE_ENV_VALUE",
        "CURRENCY_GATE_ENV_VAR",
        "SIBLING_CLONES_ROOT_ENV_VAR",
        "SiblingClones",
        "escape_minijinja_literal",
        "render_run_config_overlay",
        "workflow_graph_path",
    }
    assert set(_dispatcher_goal.__all__) == {
        "GoalBriefMiniJinjaFinding",
        "minijinja_findings_detail",
        "minijinja_openers_in_goal_sources",
        "minijinja_openers_in_text",
        "render_goal",
    }
    assert set(_dispatcher_host_only.__all__) == {
        "WORKFLOW_SCOPE_OVERRIDE_LABEL",
        "declares_workflow_scope_refusal",
        "host_only_refusal_detail",
        "is_host_only_item",
    }
    assert set(_dispatcher_plan.__all__).issuperset(
        set(_dispatcher_fabro_argv.__all__)
        | set(_dispatcher_goal.__all__)
        | set(_dispatcher_host_only.__all__)
        | set(_dispatcher_run_status.__all__)
        | set(_dispatcher_overlay.__all__)
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Canned .livespec-fleet-manifest.jsonc payload the autouse fixture serves in
# place of the real `gh api` fetch (which must never run in the
# hermetic tier). Mirrors the committed shape on livespec master
# (owner + classed members, `//` comments). It includes a member named
# "repo" because `_repo_with_workflow` creates the dispatch-target
# checkout under that basename — letting dispatch-level tests assert
# the target's own clone step is excluded from the overlay.
_FLEET_MANIFEST_TEXT = (
    "// .livespec-fleet-manifest.jsonc — canned test copy\n"
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "fleet": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "livespec-dev-tooling", "class": "enforcement-suite" },\n'
    '    { "repo": "repo", "class": "impl-plugin" }\n'
    "  ]\n"
    "}\n"
)

# The `fetch_fleet_manifest_text` / `github_token_supplier` imports above
# bind the production function objects at import time, BEFORE the autouse
# fixture swaps the dispatcher module attributes for canned stand-ins — so
# the real implementations stay directly testable.
_real_fetch_fleet_manifest_text = fetch_fleet_manifest_text
_real_github_token_supplier = github_token_supplier


_STAMPED_ENVELOPE_KEYS = ("at", "invoker", "invoker_source")


def _journal_payload(*, record: dict[str, object]) -> dict[str, object]:
    """Drop the append layer's stamped envelope, leaving the writer's payload.

    The stamped `at` / `invoker` / `invoker_source` values depend on the clock
    and the invoking environment, so an exact-equality assertion about a
    record's PAYLOAD strips them rather than pinning them. The stamping itself
    is asserted where it is the subject — `test_dispatcher_journal_stamping.py`
    and the invoker integration tier — never accidentally here.
    """
    return {key: value for key, value in record.items() if key not in _STAMPED_ENVELOPE_KEYS}


def _span_attrs(*, line: str) -> dict[str, object]:
    request = json.loads(line)
    resource_spans = cast("list[dict[str, object]]", request["resourceSpans"])
    scope_spans = cast("list[dict[str, object]]", resource_spans[0]["scopeSpans"])
    spans = cast("list[dict[str, object]]", scope_spans[0]["spans"])
    entries = cast("list[dict[str, object]]", spans[0]["attributes"])
    attrs: dict[str, object] = {}
    for entry in entries:
        value = cast("dict[str, object]", entry["value"])
        attrs[str(entry["key"])] = value.get(
            "stringValue", value.get("intValue", value.get("boolValue"))
        )
    return attrs


@pytest.fixture(autouse=True)
def fabro_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Hermetic C-mode dispatch environment for every test: an obviously
    fake CLAUDE_CODE_OAUTH_TOKEN in the process env (the Dispatcher
    fail-fasts without one, and projects the value into the run-config
    overlay's env table at dispatch), a canned GitHub App token supplier
    (the production one resolves GITHUB_APP_ID + GITHUB_PRIVATE_KEY from
    the wrapper-injected env and mints over the network, which must never
    happen in the hermetic tier), a canned fleet-manifest fetch (the
    production one shells out to `gh api`), plus a per-test temp dir so
    parallel pytest-xdist workers never collide on the dispatcher's
    goal/overlay temp files."""
    scratch = tmp_path_factory.mktemp("fabro-dispatch")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )


@pytest.fixture(autouse=True)
def _tmp_repo_connection_config(tmp_path: Path) -> None:
    """Give each test's `tmp_path` a `.livespec.jsonc` with a `prefix`.

    The CLI surfaces (`ledger-check` / `spec-check`) and the dispatcher
    resolve the tenant connection via `resolve_store_config(cwd=...)`, which
    now REQUIRES an explicit `connection.prefix` (decoupled from the tenant
    DB name). A real governed repo always carries one; this fixture mirrors
    that for the bare-`tmp_path` CLI tests (the `tmp_path / "repo"` dispatch
    repos get their own copy in `_repo_with_workflow`).
    """
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="livespec-impl-beads-t1",
        type="task",
        status="ready",
        title="A ready task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        # Admission-eligible + autonomously acceptable by default so a green
        # dispatch flows admit (ready -> active) -> complete (-> acceptance) ->
        # accept (ai-only -> done); cases that exercise the admission hold or
        # the human-confirm park override these.
        admission_policy="auto",
        acceptance_policy="ai-only",
        # The pre-dispatch wall (the effective-acceptance-criteria clause of contracts.md)
        # refuses an AI-dispositive item whose effective criteria parse to zero
        # gradeable assertions, so a DISPATCHABLE fixture has to carry one.
        # Cases that exercise the wall itself override this.
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


# A DECLARED pin and a resolved default branch, because either left
# unresolved degrades the post-merge provisioning before the janitor is
# reached -- which is its own case, in the venue tests.
_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="x-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=_DECLARED_CONFIG,
        default_branch="master",
    )


@dataclass(kw_only=True)
class _FakeRunner:
    """Scripted CommandRunner: consumes queued results, logs invocations."""

    queue: list[CommandResult]
    calls: list[tuple[list[str], Path]] = field(default_factory=list)
    timeouts: list[float] = field(default_factory=list)
    envs: list[dict[str, str] | None] = field(default_factory=list)

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
        _ = (env, stdin)
        self.calls.append((argv, cwd))
        self.timeouts.append(timeout_seconds)
        self.envs.append(env)
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _pr_association() -> CommandResult:
    """The forge answering "which PRs contain this merge sha" with the
    branch-resolved one — the healthy case, where the recorded number is
    CONFIRMED rather than corrected. Every merged dispatch asks this once,
    between the last `gh pr view` and pull-primary."""
    return _ok(stdout=json.dumps([{"number": 7}]))


def _venue_resolution() -> list[CommandResult]:
    """The ONE venue read between pull-primary and the preclean: the probe
    confirming the tip contains the merge. The branch itself is read off the
    plan's resolved integration contract rather than re-probed here, so the
    janitor venue is that declared tip, never the item's merge sha."""
    return [_ok()]


def _post_merge_green_tail() -> list[CommandResult]:
    """The ten all-green post-merge results: pull-primary, the venue
    containment probe, then the janitor-checkout lifecycle (preclean, add,
    trust, bootstrap, the per-checkout bootstrap leg, core clone, janitor run,
    remove)."""
    return [_ok(), *_venue_resolution(), *[_ok() for _ in range(8)]]


def _err(stderr: str = "boom") -> CommandResult:
    return CommandResult(exit_code=1, stdout="", stderr=stderr)


def test_acceptance_pass_ignores_description_headings_before_exit_criteria(
    tmp_path: Path,
) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(stdout="diff --git a/x b/x\n+description exit criterion landed\n"),
        ]
    )

    result = run_acceptance_pass(
        repo=tmp_path,
        item=_item(
            acceptance_criteria=None,
            description=(
                "## Context\n\n"
                "- not acceptance\n\n"
                "## Exit criteria\n\n"
                "- description exit criterion landed\n"
            ),
        ),
        outcome=_green_outcome(item_id="livespec-impl-beads-t1"),
        runner=runner,
    )

    assert result.verdict == "PASS"
    assert [check.text for check in result.criteria] == ["description exit criterion landed"]


def _pr_json(
    *,
    state: str = "OPEN",
    armed: bool = True,
    merge_state: str = "CLEAN",
    sha: str | None = None,
    checks: list[dict[str, object]] | None = None,
) -> str:
    return json.dumps(
        {
            "number": 7,
            "state": state,
            "autoMergeRequest": {"enabledAt": "now"} if armed else None,
            "mergeStateStatus": merge_state,
            "mergeCommit": {"oid": sha} if sha is not None else None,
            "statusCheckRollup": checks if checks is not None else [],
        }
    )


def _dispatch(
    *,
    runner: _FakeRunner,
    repo: Path,
    attempts: int = 3,
) -> tuple[DispatchOutcome, _RecordingJournal, list[float]]:
    journal = _RecordingJournal()
    naps: list[float] = []
    outcome = run_dispatch(
        plan=_plan(repo=repo),
        runner=runner,
        journal=journal,
        sleep=naps.append,
        poll=PollPolicy(attempts=attempts, interval_seconds=0.5),
    )
    return outcome, journal, naps


# ---------------------------------------------------------------------------
# Ledger checks
# ---------------------------------------------------------------------------


def test_ledger_checks_pass_on_clean_items() -> None:
    items = [
        _item(),
        _item(id="b-2", depends_on=("livespec-impl-beads-t1",), gap_id="gap-1"),
        _item(id="b-3", status="done", gap_id="gap-1"),
    ]
    assert run_ledger_checks(items=items) == []


def test_ledger_checks_flag_unparseable_depends_on_entry() -> None:
    items = [_item(depends_on=({"bogus": "shape"},))]
    findings = run_ledger_checks(items=items)
    assert [finding.check for finding in findings] == ["depends-on-ref-wellformedness"]
    assert "bogus" in findings[0].message


def test_ledger_checks_flag_orphan_dependency() -> None:
    items = [_item(depends_on=("nope-99",))]
    findings = run_ledger_checks(items=items)
    assert [finding.check for finding in findings] == ["no-orphan-dependency"]
    assert "nope-99" in findings[0].message


def test_ledger_checks_flag_duplicate_gap_ids_sorted() -> None:
    items = [
        _item(id="z-2", gap_id="gap-x"),
        _item(id="a-1", gap_id="gap-x"),
        _item(id="m-3", gap_id="gap-solo"),
    ]
    findings = run_ledger_checks(items=items)
    assert [finding.item_id for finding in findings] == ["a-1", "z-2"]
    assert all(finding.check == "no-duplicate-gap-id" for finding in findings)
    assert "a-1, z-2" in findings[0].message


def test_ledger_checks_flag_out_of_lifecycle_live_status() -> None:
    items = [
        _item(id="ok-ready", status="ready"),
        _item(id="parked-deferred", status="deferred"),
        _item(id="bad-open", status="open"),
        _item(id="closed-deferred", status="done"),
    ]
    findings = run_ledger_checks(items=items)
    assert [(finding.check, finding.item_id) for finding in findings] == [
        ("status-conformance", "bad-open"),
    ]
    assert "status 'open' is outside the livespec lifecycle" in findings[0].message


def test_ledger_checks_flag_minijinja_openers_in_goal_sources() -> None:
    items = [
        _item(id="field-hit", description="recipe uses {{ value }}"),
        _item(id="comment-hit"),
    ]
    comments_by_item = {
        "comment-hit": (
            WorkItemComment(
                text="rider contains {% statement",
                author="operator",
                created_at="2026-08-22T10:11:12Z",
                comment_id="comment-9",
            ),
        ),
    }

    findings = run_ledger_checks(items=items, comments_by_item=comments_by_item)

    assert [(finding.check, finding.item_id, finding.severity) for finding in findings] == [
        ("goal-source-minijinja-opener", "comment-hit", "fail"),
        ("goal-source-minijinja-opener", "field-hit", "warn"),
    ]
    assert "permanent comment contamination" in findings[0].message
    assert "ledger comment comment-9 created 2026-08-22T10:11:12Z" in findings[0].message
    assert "recoverable-by-editing" in findings[1].message
    assert "description" in findings[1].message


def test_ledger_checks_do_not_flag_clean_goal_sources() -> None:
    items = [
        _item(id="clean-field", description="recipe uses square brackets"),
        _item(id="clean-comment"),
    ]
    comments_by_item = {
        "clean-comment": (
            WorkItemComment(
                text="plain rider",
                author="operator",
                created_at="2026-08-22T10:11:12Z",
                comment_id="comment-10",
            ),
        ),
    }

    assert run_ledger_checks(items=items, comments_by_item=comments_by_item) == []


def test_dispatch_gate_auto_normalizes_beads_native_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    items = [
        _item(id="native-open", status="open"),
        _item(id="parked-deferred", status="deferred"),
        _item(id="bad-hooked", status="hooked"),
    ]

    def fake_update_work_item_status(
        *,
        path: StoreConfig,
        item_id: str,
        status: str,
        assignee: str | None = None,
        rank: str | None = None,
    ) -> None:
        assert path.prefix == "bd-ib"
        assert assignee is None
        # Every fixture row already carries a real `rank`, so the adoption
        # writes the status alone: `rank` is the assignment an already-ranked
        # row must NOT receive.
        assert rank is None
        calls.append((item_id, status))

    def fake_read_work_items(*, path: StoreConfig) -> object:
        _ = path
        return iter(items)

    monkeypatch.setattr(_dispatcher_ledger_close, "read_work_items", fake_read_work_items)
    monkeypatch.setattr(
        _dispatcher_ledger_close,
        "update_work_item_status",
        fake_update_work_item_status,
    )
    # Neutralize the whole OTel egress arming (receiver + file-tail driver) so a
    # real dispatch binds no socket and spawns no background thread.
    monkeypatch.setattr(_dispatcher_run_commands, "arm_otel_egress", lambda **_: None)
    workflow = tmp_path / "workflow.toml"
    workflow.write_text("[workflow]\n", encoding="utf-8")
    journal = tmp_path / "journal.jsonl"

    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(tmp_path),
            "--workflow",
            str(workflow),
            "--fabro-bin",
            sys.executable,
            "--journal",
            str(journal),
            "--item",
            "native-open",
        ]
    )

    assert exit_code == 1
    assert calls == [("native-open", "backlog")]
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    # The normalization note now routes through the append layer, so it carries
    # the stamped envelope (`at` + the resolved invoker) alongside its payload.
    # ALL THREE pre-dispatch steps journal their pass ahead of it: both step-gate
    # preflights and the automatic reconciliation pass run inside the preamble,
    # which is ahead of the ledger gate, and each pass is a sanctioned journaled
    # outcome.
    assert [record["stage"] for record in records[:4]] == [
        "source-checkout-origin-reachability",
        "master-ci-preflight",
        "reconcile-runs-pass",
        "status-normalization",
    ]
    assert records[3]["normalized"] == [
        {
            "from": "open",
            "item_id": "native-open",
            "reason": "beads-native intake default",
            "to": "backlog",
        }
    ]
    assert records[3]["at"]
    assert records[3]["invoker"]
    assert records[3]["invoker_source"] in {"flag", "env", "fallback"}
    assert records[4]["stage"] == "ledger-check"
    assert records[4]["findings"] == [
        {
            "check": "status-conformance",
            "item_id": "bad-hooked",
            "message": (
                "status 'hooked' is outside the livespec lifecycle "
                "(allowed: acceptance, active, backlog, blocked, closed, deferred, pending-approval, ready)"
            ),
            "severity": "fail",
        }
    ]


def test_ledger_checks_ignore_closed_items() -> None:
    items = [_item(status="done", depends_on=("nope-99", {"bad": True}))]
    assert run_ledger_checks(items=items) == []


# ---------------------------------------------------------------------------
# Spec checks (the re-homed spec-context invariants)
# ---------------------------------------------------------------------------


def _manifest() -> CrossRepoManifest:
    return CrossRepoManifest(targets={})


def _write_pc(*, directory: Path, stem: str, pc_text: str, revision_text: str | None) -> None:
    _ = (directory / f"{stem}.md").write_text(pc_text, encoding="utf-8")
    if revision_text is not None:
        _ = (directory / f"{stem}-revision.md").write_text(revision_text, encoding="utf-8")


def _revision(*, decision: str) -> str:
    return f"---\ndecision: {decision}\n---\nNarration.\n"


def _spec_tree(*, tmp_path: Path) -> Path:
    """Build a SPECIFICATION tree with one live MUST rule + a rich history walk."""
    spec = tmp_path / "SPECIFICATION"
    v1 = spec / "history" / "v001" / "proposed_changes"
    v1.mkdir(parents=True)
    _ = (spec / "spec.md").write_text(
        "# Spec\n\n## Rules\n\nThe system MUST frobnicate.\n", encoding="utf-8"
    )
    covered_pc = (
        "---\n"
        "topic: covered\n"
        "spec_commitments:\n"
        "  impl_followups:\n"
        "    - id_hint: hint-filed\n"
        "      description: tracked by a filed work-item\n"
        "\n"
        "    - id_hint: hint-unfiled\n"
        "    - id_hint:\n"
        "    - id_hint: hint-old\n"
        "status: pending\n"
        "---\nBody.\n"
    )
    _write_pc(
        directory=v1, stem="covered", pc_text=covered_pc, revision_text=_revision(decision="accept")
    )
    rejected_pc = (
        "---\nspec_commitments:\n  impl_followups:\n    - id_hint: hint-rejected\n---\nBody.\n"
    )
    _write_pc(
        directory=v1,
        stem="rejected",
        pc_text=rejected_pc,
        revision_text=_revision(decision="reject"),
    )
    _write_pc(
        directory=v1,
        stem="plain",
        pc_text="No front matter here.\n",
        revision_text=_revision(decision="accept"),
    )
    _write_pc(
        directory=v1,
        stem="unclosed",
        pc_text="---\nspec_commitments:\n",
        revision_text=_revision(decision="accept"),
    )
    _write_pc(
        directory=v1,
        stem="no-commitments",
        pc_text="---\ntopic: bare\n---\nBody.\n",
        revision_text=_revision(decision="accept"),
    )
    _write_pc(
        directory=v1,
        stem="no-decision",
        pc_text="---\ntopic: x\n---\n",
        revision_text="---\ntopic: undecided\n---\n",
    )
    _write_pc(
        directory=v1,
        stem="bare-rev",
        pc_text="---\ntopic: y\n---\n",
        revision_text="No front matter either.\n",
    )
    _write_pc(directory=v1, stem="orphan", pc_text="---\ntopic: z\n---\n", revision_text=None)
    _ = (v1 / "notes.txt").write_text("not a pc\n", encoding="utf-8")
    (v1 / "drafts").mkdir()
    v2 = spec / "history" / "v002"
    (v2 / "proposed_changes").mkdir(parents=True)
    _ = (v2 / "PRUNED_HISTORY.json").write_text("{}\n", encoding="utf-8")
    pruned_pc = "---\nspec_commitments:\n  impl_followups:\n    - id_hint: hint-pruned\n---\n"
    _write_pc(
        directory=v2 / "proposed_changes",
        stem="pruned",
        pc_text=pruned_pc,
        revision_text=_revision(decision="accept"),
    )
    v3 = spec / "history" / "v003" / "proposed_changes"
    v3.mkdir(parents=True)
    superseder_pc = (
        "---\n"
        "spec_commitments:\n"
        "  supersedes:\n"
        "    - hint-old\n"
        "      reason: replaced by the v003 wiring\n"
        "  impl_followups:\n"
        "---\n"
    )
    _write_pc(
        directory=v3,
        stem="superseder",
        pc_text=superseder_pc,
        revision_text=_revision(decision="modify"),
    )
    (spec / "history" / "v004").mkdir()
    (spec / "history" / "not-a-version").mkdir()
    _ = (spec / "history" / "stray.txt").write_text("not a version dir\n", encoding="utf-8")
    return spec


def test_collect_obligations_walks_accepted_history(tmp_path: Path) -> None:
    spec = _spec_tree(tmp_path=tmp_path)
    obligations, superseded = collect_obligations_and_supersedes(spec_root=spec)
    assert obligations == [
        Obligation(id_hint="hint-filed", version_label="v001", pc_stem="covered"),
        Obligation(id_hint="hint-unfiled", version_label="v001", pc_stem="covered"),
        Obligation(id_hint="hint-old", version_label="v001", pc_stem="covered"),
    ]
    assert superseded == {"hint-old"}


def test_collect_obligations_empty_without_history(tmp_path: Path) -> None:
    assert collect_obligations_and_supersedes(spec_root=tmp_path) == ([], set())


def test_spec_checks_flag_stalled_epics() -> None:
    items = [
        _item(id="dep-1", status="done"),
        _item(id="dep-2", status="done"),
        _item(
            id="epic-stalled",
            type="epic",
            depends_on=("dep-1", {"kind": "local", "work_item_id": "dep-2"}),
        ),
        _item(id="epic-rolling", type="epic", status="active", depends_on=("dep-1",)),
    ]
    findings = run_spec_checks(items=items, spec_root=Path("/nonexistent"), manifest=_manifest())
    stalled = [finding for finding in findings if finding.check == "no-stalled-epic"]
    assert [(finding.item_id, finding.severity) for finding in stalled] == [
        ("epic-rolling", "fail"),
        ("epic-stalled", "fail"),
    ]
    assert "still ready" in stalled[1].message


def test_spec_checks_epic_not_stalled_when_any_dep_unresolved_or_open() -> None:
    items = [
        _item(id="dep-open"),
        _item(id="dep-closed", status="done"),
        _item(id="epic-open-dep", type="epic", depends_on=("dep-open", "dep-closed")),
        _item(id="epic-missing-dep", type="epic", depends_on=("ghost-1",)),
        _item(id="epic-bad-dep", type="epic", depends_on=({"bogus": True},)),
        _item(
            id="epic-sibling-dep",
            type="epic",
            depends_on=(
                {"kind": "sibling_work_item", "repo": "unconfigured", "work_item_id": "x-1"},
            ),
        ),
        _item(id="epic-empty", type="epic"),
        _item(id="epic-closed", type="epic", status="done", depends_on=("dep-closed",)),
        _item(id="task-done-deps", depends_on=("dep-closed",)),
    ]
    findings = run_spec_checks(items=items, spec_root=Path("/nonexistent"), manifest=_manifest())
    assert [finding for finding in findings if finding.check == "no-stalled-epic"] == []


def test_spec_checks_skip_spec_tree_checks_without_spec_root(tmp_path: Path) -> None:
    findings = run_spec_checks(items=[], spec_root=tmp_path / "missing", manifest=_manifest())
    assert [(finding.check, finding.severity) for finding in findings] == [
        ("no-stale-gap-tied", "skipped"),
        ("unresolved-spec-commitment", "skipped"),
    ]
    assert all(finding.item_id == "-" for finding in findings)


def test_spec_checks_warn_only_for_stale_gap_tied_items(tmp_path: Path) -> None:
    spec = _spec_tree(tmp_path=tmp_path)
    fresh_gap = detect_rules(spec_root=spec)[0].gap_id
    items = [
        _item(id="g-fresh", origin="gap-tied", gap_id=fresh_gap),
        _item(id="g-stale", origin="gap-tied", gap_id="gap-gone1234", status="active"),
        _item(id="g-closed", origin="gap-tied", gap_id="gap-gone1234", status="done"),
        _item(id="g-none", origin="gap-tied", gap_id=None),
        _item(id="f-free", gap_id="gap-gone1234"),
    ]
    findings = run_spec_checks(items=items, spec_root=spec, manifest=_manifest())
    stale = [finding for finding in findings if finding.check == "no-stale-gap-tied"]
    assert [(finding.item_id, finding.severity) for finding in stale] == [("g-stale", "warn")]
    assert "gap-gone1234" in stale[0].message
    assert "non-fix disposition" in stale[0].message


def test_spec_checks_no_gap_findings_without_open_gap_tied_items(tmp_path: Path) -> None:
    spec = _spec_tree(tmp_path=tmp_path)
    findings = run_spec_checks(items=[_item()], spec_root=spec, manifest=_manifest())
    assert [finding for finding in findings if finding.check == "no-stale-gap-tied"] == []


def test_spec_checks_flag_unresolved_commitments(tmp_path: Path) -> None:
    spec = _spec_tree(tmp_path=tmp_path)
    items = [
        _item(id="filed-1", spec_commitment_hint="hint-filed"),
        _item(id="empty-hint", spec_commitment_hint=""),
    ]
    findings = run_spec_checks(items=items, spec_root=spec, manifest=_manifest())
    unresolved = [finding for finding in findings if finding.check == "unresolved-spec-commitment"]
    assert [(finding.item_id, finding.severity) for finding in unresolved] == [
        ("hint-unfiled", "fail")
    ]
    assert "v001/proposed_changes/covered.md" in unresolved[0].message
    assert "--spec-commitment-hint hint-unfiled" in unresolved[0].message


# ---------------------------------------------------------------------------
# Janitor checks (the re-homed stale-cleanup checks)
# ---------------------------------------------------------------------------

_JANITOR_PROBE_COUNT = 7


def _janitor_results(*, fail_at: int | None = None) -> list[CommandResult]:
    """Script the seven janitor probes; `fail_at` makes that probe exit 1."""
    worktrees = (
        "worktree /repo\nHEAD aaa\nbranch refs/heads/master\n\n"
        "worktree /repo/worktrees/merged\nHEAD bbb\nbranch refs/heads/feat/x\n\n"
        "worktree /repo/worktrees/gone\nHEAD ccc\nbranch refs/heads/feat/y\n\n"
        "worktree /repo/worktrees/detached\nHEAD ddd\ndetached\n\n"
        "worktree /repo/worktrees/ondefault\nHEAD eee\nbranch refs/heads/master\n\n"
        "worktree /repo/worktrees/active\nHEAD fff\nbranch refs/heads/feat/z\n"
    )
    remote = (
        "aaa\trefs/heads/master\n"
        "bbb\trefs/heads/feat/x\n"
        "fff\trefs/heads/feat/z\n"
        "malformed-line-without-tab\n"
    )
    results = [
        _ok("true\n"),
        _ok("origin/master\n"),
        _ok("master\nfeat/x\n"),
        _ok(remote),
        _ok(worktrees),
        _ok("thewoolleyman/livespec-orchestrator-beads-fabro\n"),
        _ok("feat/x\nmaster\n"),
    ]
    if fail_at is not None:
        results[fail_at] = _err()
    return results


def test_janitor_checks_skip_outside_git_repo(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=[_err()])
    findings = run_janitor_checks(repo=tmp_path, runner=runner)
    assert [(finding.check, finding.severity) for finding in findings] == [
        ("no-stale-merged-branch", "skipped"),
        ("no-stale-merged-pr-branch", "skipped"),
        ("no-stale-worktree", "skipped"),
    ]
    assert len(runner.calls) == 1
    assert runner.calls[0][0] == ["git", "rev-parse", "--is-inside-work-tree"]


def test_janitor_checks_skip_without_default_branch(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=[_ok("true\n"), _err()])
    findings = run_janitor_checks(repo=tmp_path, runner=runner)
    assert {finding.severity for finding in findings} == {"skipped"}
    assert "default branch undetermined" in findings[0].message
    assert len(runner.calls) == 2


def test_janitor_checks_clean_state_yields_no_findings(tmp_path: Path) -> None:
    results = _janitor_results()
    results[2] = _ok("master\n")
    results[4] = _ok("worktree /repo\nHEAD aaa\nbranch refs/heads/master\n")
    results[6] = _ok("")
    runner = _FakeRunner(queue=results)
    findings = run_janitor_checks(repo=tmp_path, runner=runner)
    assert findings == []
    assert len(runner.calls) == _JANITOR_PROBE_COUNT
    assert runner.calls[2][0] == [
        "git",
        "for-each-ref",
        "--format=%(refname:short)",
        "--merged",
        "master",
        "refs/heads",
    ]


def test_janitor_checks_tolerate_empty_worktree_listing(tmp_path: Path) -> None:
    results = _janitor_results()
    results[4] = _ok("")
    runner = _FakeRunner(queue=results)
    findings = run_janitor_checks(repo=tmp_path, runner=runner)
    assert [finding for finding in findings if finding.check == "no-stale-worktree"] == []


def test_janitor_checks_flag_stale_branches_prs_and_worktrees(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=_janitor_results())
    findings = run_janitor_checks(repo=tmp_path, runner=runner)
    assert [(finding.check, finding.item_id, finding.severity) for finding in findings] == [
        ("no-stale-merged-branch", "feat/x", "warn"),
        ("no-stale-merged-pr-branch", "feat/x", "warn"),
        ("no-stale-worktree", "/repo/worktrees/gone", "warn"),
        ("no-stale-worktree", "/repo/worktrees/merged", "warn"),
    ]
    assert "git branch -d feat/x" in findings[0].message
    delete_action = "gh api -X DELETE repos/thewoolleyman/livespec-orchestrator-beads-fabro/git/refs/heads/feat/x"
    assert delete_action in findings[1].message
    assert "git worktree remove /repo/worktrees/gone" in findings[2].message


@pytest.mark.parametrize(
    ("fail_at", "expected_skipped"),
    [
        (2, {"no-stale-merged-branch", "no-stale-worktree"}),
        (3, {"no-stale-merged-pr-branch", "no-stale-worktree"}),
        (4, {"no-stale-worktree"}),
        (5, {"no-stale-merged-pr-branch"}),
        (6, {"no-stale-merged-pr-branch"}),
    ],
)
def test_janitor_checks_skip_per_failed_probe(
    tmp_path: Path,
    fail_at: int,
    expected_skipped: set[str],
) -> None:
    runner = _FakeRunner(queue=_janitor_results(fail_at=fail_at))
    findings = run_janitor_checks(repo=tmp_path, runner=runner)
    skipped = {finding.check for finding in findings if finding.severity == "skipped"}
    assert skipped == expected_skipped
    assert len(runner.calls) == _JANITOR_PROBE_COUNT


# ---------------------------------------------------------------------------
# Plan layer — builders and parsers
# ---------------------------------------------------------------------------


def test_build_plan_derives_publish_branch_and_default_janitor(tmp_path: Path) -> None:
    plan = _plan(repo=tmp_path)
    assert plan.branch == "feat/x-1"
    assert plan.janitor == (
        "mise",
        "exec",
        "--",
        "just",
        "check-no-workflow-edits",
        "install-worktree-pack",
        "check",
    )
    assert plan.janitor_checkout == tmp_path / "janitor-co"
    assert plan.review_fix_visit_cap == 4
    assert plan.merge_on_review_cap_outcome == "__merge_on_review_cap_disabled__"


def test_dispatch_factory_selection_reaches_fabro_port_run_and_env(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit) as exc:
        dispatcher.main(argv=["dispatch", "--help"])
    assert exc.value.code == 0
    assert "--factory" in capsys.readouterr().out

    runner = _FakeRunner(queue=[_ok()])
    port = FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url="https://factory.example.test"),
        runner=runner,
        cwd=tmp_path,
    )
    _ = port.run(
        workflow_toml=tmp_path / "wf.toml",
        goal_file=tmp_path / "goal.md",
        inputs=("acp_adapter=codex",),
        timeout_seconds=10,
    )

    # The pinned fabro CLI (0.254.0) only accepts `--server` as a
    # per-subcommand flag, never before the subcommand — `fabro --server
    # <url> run ...` is a hard CLI parse error. See bd-ib-1g01.
    assert runner.calls[0][0][:2] == ["fabro", "run"]
    assert runner.calls[0][0][-2:] == [
        "--server",
        "https://factory.example.test",
    ]
    assert runner.envs == [{"FABRO_SERVER": "https://factory.example.test"}]


def test_fabro_argv_builders_place_server_after_their_subcommand(tmp_path: Path) -> None:
    """`--server` must follow the subcommand for every fabro invocation.

    The pinned fabro CLI (0.254.0) rejects `fabro --server <url> <cmd>` as
    a top-level-flag parse error; `--server` is per-subcommand only. See
    bd-ib-1g01 for the live repro.
    """
    runner = _FakeRunner(queue=[_ok("{}"), _ok("{}"), _ok("[]"), _ok()])
    port = FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url="https://factory.example.test"),
        runner=runner,
        cwd=tmp_path,
    )
    _ = port.inspect(run_id="01RUNID", timeout_seconds=1)
    _ = port.events(run_id="01RUNID", timeout_seconds=1)
    _ = port.ps(timeout_seconds=1)
    _ = port.rm(run_id="01RUNID", timeout_seconds=1)

    assert [call[0] for call in runner.calls] == [
        [
            "fabro",
            "inspect",
            "01RUNID",
            "--json",
            "--server",
            "https://factory.example.test",
        ],
        [
            "fabro",
            "events",
            "01RUNID",
            "--json",
            "--server",
            "https://factory.example.test",
        ],
        [
            "fabro",
            "ps",
            "-a",
            "--json",
            "--server",
            "https://factory.example.test",
        ],
        [
            "fabro",
            "rm",
            "-f",
            "01RUNID",
            "--server",
            "https://factory.example.test",
        ],
    ]


def test_dispatch_logs_into_dev_token_factory_before_fabro_run(tmp_path: Path) -> None:
    factory_credential = "fixture-value"
    plan = build_plan(
        repo=tmp_path,
        work_item_id="x-1",
        workflow_toml=tmp_path / "wf.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor-co",
        fabro_factory_name="remote",
        fabro_factory_server="https://factory.example.test",
        fabro_factory_dev_token=factory_credential,
    )
    runner = _FakeRunner(queue=[_ok(), _err()])
    journal = _RecordingJournal()

    outcome = run_dispatch(
        plan=plan,
        runner=runner,
        journal=journal,
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=1, interval_seconds=0.5),
    )

    assert outcome.status == "failed"
    assert runner.calls[0] == (
        [
            "fabro",
            "auth",
            "login",
            "--dev-token",
            factory_credential,
            "--server",
            "https://factory.example.test",
        ],
        tmp_path,
    )
    assert runner.calls[1][0][:2] == ["fabro", "run"]
    assert runner.calls[1][0][-2:] == [
        "--server",
        "https://factory.example.test",
    ]


def test_janitor_argv_is_the_resolved_check_suite_verbatim() -> None:
    """The builder imposes nothing of its own: the resolved command IS the argv."""
    assert janitor_argv(
        check_suite=janitor_check_suite_from_block(block={}, janitor=("echo", "hi"))
    ) == ("echo", "hi")
    assert janitor_argv(check_suite=janitor_check_suite_from_block(block={}, janitor=())) == (
        "mise",
        "exec",
        "--",
        "just",
        "check-no-workflow-edits",
        "install-worktree-pack",
        "check",
    )


def test_default_janitor_provisions_the_worktree_pack_before_checks() -> None:
    """The janitor checkout must MATERIALIZE the pack, not be exempted from it.

    The post-merge janitor runs in a FRESH worktree that never ran
    `just bootstrap`, and the worktree-discipline pack is gitignored — so it is
    absent there by construction. Since livespec-dev-tooling v0.54.24 an absent
    pack is a FAIL by default, which reds the janitor's own `just check` on a
    conformant repo. This surfaced for real on the reconcile of `bd-ib-hvuhxp`.

    The janitor is a normal worktree-equivalent, NOT a declared sandbox, so the
    fix is to PROVISION the pack here rather than to exempt the venue: the
    assertion must become TRUE, not skipped. `install-worktree-pack` therefore
    precedes `check`, and presence enforcement is left untouched.
    """
    argv = janitor_argv(check_suite=janitor_check_suite_from_block(block={}, janitor=()))
    assert (
        "install-worktree-pack" in argv
    ), f"the default janitor must materialize the gitignored pack; got {argv!r}"
    assert argv.index("install-worktree-pack") < argv.index(
        "check"
    ), f"the pack must be installed BEFORE `check` reads it; got {argv!r}"


def test_janitor_checkout_path_lives_under_home_worktrees(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The venue derives from the target repo name under the family worktree root."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    checkout = janitor_checkout_path(repo=tmp_path / "primary", work_item_id="x-1")
    assert checkout == tmp_path / "home" / ".worktrees" / "primary" / "janitor-x-1"
    assert tmp_path / "primary" / "worktrees" not in checkout.parents
    assert not str(checkout).startswith(tempfile.gettempdir())


def test_janitor_checkout_venue_matches_no_coverage_omit_glob() -> None:
    """The tpu janitor false-red RCA: the venue used to be
    `/tmp/fabro-janitor-<item-id>` while pyproject's `[tool.coverage.run]`
    omit carries `/tmp/*` (a guard against measured tempfile artifacts
    that must STAY), so every source file inside the janitor checkout
    was omitted — coverage measured zero files and
    check-per-file-coverage died with NoDataError, false-redding a
    merged-green change. Pin the venue against the REAL committed omit
    configuration (read from this repo's pyproject.toml, never
    hardcoded) using coverage's own matcher: a product file inside the
    relocated janitor checkout matches no omit glob, while the same
    file under the old /tmp venue still does."""
    repo_root = Path(__file__).resolve().parents[3]
    omit = Coverage(config_file=str(repo_root / "pyproject.toml")).get_option("run:omit")
    assert isinstance(omit, list)
    matcher = GlobMatcher(prep_patterns(omit), "omit")
    probe = Path(
        ".claude-plugin",
        "scripts",
        "livespec_orchestrator_beads_fabro",
        "commands",
        "dispatcher.py",
    )
    checkout = janitor_checkout_path(repo=repo_root, work_item_id="livespec-impl-beads-tpu")
    assert not matcher.match(str(checkout / probe))
    assert matcher.match(str(Path("/tmp", "fabro-janitor-livespec-impl-beads-tpu") / probe))


def test_render_goal_includes_item_fields_and_optional_gap(tmp_path: Path) -> None:
    with_gap = render_goal(item=_item(gap_id="gap-9"), repo=tmp_path, branch="feat/t")
    assert "Gap id: gap-9" in with_gap
    assert "Work-item: livespec-impl-beads-t1" in with_gap
    assert "Publish branch" in with_gap
    assert "feat/t" in with_gap
    assert "A ready task" in with_gap
    assert "Do the thing." in with_gap
    without_gap = render_goal(item=_item(), repo=tmp_path, branch="feat/t")
    assert "Gap id" not in without_gap


def test_render_goal_includes_optional_spec_id(tmp_path: Path) -> None:
    with_spec_id = render_goal(
        item=_item(spec_commitment_hint="spec-topic-9"),
        repo=tmp_path,
        branch="feat/t",
    )
    assert "Spec id: spec-topic-9" in with_spec_id

    without_spec_id = render_goal(item=_item(), repo=tmp_path, branch="feat/t")
    assert "Spec id" not in without_spec_id


def test_render_goal_omits_the_spec_id_line_for_a_plan_anchored_item(tmp_path: Path) -> None:
    """A plan anchor names where work is TRACKED, not what the spec REQUIRES.

    The rendered brief is the prompt EVERY phase of the dispatched workflow
    reads, so a presence-only test on the overloaded hint injected the false
    value straight into the agent's instructions: every plan-stamped item ever
    dispatched was told `Spec id: plan:<slug>`, presenting a plan anchor as a
    commitment to ratified spec text.
    """
    goal = render_goal(
        item=_item(spec_commitment_hint="plan:codex-yolo-sandbox"),
        repo=tmp_path,
        branch="feat/t",
    )

    assert "Spec id" not in goal
    assert "plan:codex-yolo-sandbox" not in goal


def test_render_goal_renders_the_spec_id_line_for_a_real_spec_clause_commitment(
    tmp_path: Path,
) -> None:
    """Narrowing the predicate must not cost a genuine commitment its brief line."""
    # A genuine obligation id_hint, of the bare-slug shape the Spec Reader
    # parses out of proposed-change front-matter. No obligation slug begins
    # with the plan prefix, which is what makes the prefix a sound
    # discriminator; the expected rendered line is stated in full below.
    commitment = "contracts-dispatcher-admission"

    goal = render_goal(
        item=_item(spec_commitment_hint=commitment),
        repo=tmp_path,
        branch="feat/t",
    )

    assert "Spec id: contracts-dispatcher-admission\n" in goal


def test_render_goal_includes_acceptance_criteria_and_notes_when_present(tmp_path: Path) -> None:
    goal = render_goal(
        item=_item(
            acceptance_criteria="Run just check.",
            notes="Prompt files are audit-only in this slice.",
        ),
        repo=tmp_path,
        branch="feat/t",
    )
    assert "Description:\nDo the thing." in goal
    assert "Acceptance criteria:\nRun just check." in goal
    assert "Notes:\nPrompt files are audit-only in this slice." in goal


def test_render_goal_omits_acceptance_criteria_and_notes_when_absent(tmp_path: Path) -> None:
    goal = render_goal(item=_item(acceptance_criteria=None), repo=tmp_path, branch="feat/t")
    assert "Acceptance criteria:" not in goal
    assert "Notes:" not in goal


def test_render_goal_injects_ratified_lessons_when_present(tmp_path: Path) -> None:
    # Scenario 39: a ratified lesson reaches the composed brief in a clearly
    # delimited lessons section.
    goal = render_goal(
        item=_item(),
        repo=tmp_path,
        branch="feat/t",
        lessons="Prefer explicit kw-only args in new dispatcher helpers.",
    )
    assert "Ratified lessons" in goal
    assert "Prefer explicit kw-only args in new dispatcher helpers." in goal


def test_render_goal_leaves_brief_unchanged_without_lessons(tmp_path: Path) -> None:
    # Scenario 40: empty lessons leave the brief byte-identical to one composed
    # with no lessons at all — no heading or placeholder bleed-through.
    without = render_goal(item=_item(), repo=tmp_path, branch="feat/t")
    with_empty = render_goal(item=_item(), repo=tmp_path, branch="feat/t", lessons="")
    assert with_empty == without
    assert "Ratified lessons" not in with_empty


def test_render_goal_anchors_repo_to_sandbox_cwd_not_host_path(tmp_path: Path) -> None:
    """The brief must never present `repo` as a path the sandbox agent cds into.

    Every ACP node runs with cwd = the Fabro sandbox clone; the `repo`
    argument is the Dispatcher's HOST-side checkout (e.g.
    `/workspace/dispatch-target`), which does NOT exist inside the sandbox.
    A bare `Repo: <path>` line let the PR-stage agent honor that wrong path
    and report "no committed work to PR" (the intermittent livespec-vtxt
    PR-stage failure: n70w succeeded on the same repo/path minutes earlier).
    The brief keeps the path for provenance but frames it unmistakably as
    NOT a cd target, anchoring the agent to its current working directory.
    """
    goal = render_goal(item=_item(), repo=tmp_path, branch="feat/t")
    assert str(tmp_path) in goal  # path retained for provenance/debugging
    assert "CURRENT WORKING DIRECTORY" in goal
    assert "NEVER cd to this path" in goal


def test_argv_builders_encode_family_discipline(tmp_path: Path) -> None:
    plan = _plan(repo=tmp_path)
    assert pr_view_argv(plan=plan)[:3] == ["gh", "pr", "view"]
    assert pr_view_argv(plan=plan)[3] == "feat/x-1"
    assert "statusCheckRollup" in pr_view_argv(plan=plan)[5]
    assert pr_arm_argv(plan=plan, number=7) == [
        "gh",
        "pr",
        "merge",
        "7",
        "--rebase",
        "--auto",
        "--delete-branch",
    ]
    assert pr_update_branch_argv(plan=plan, number=7) == ["gh", "pr", "update-branch", "7"]
    # Plain `git`, and the branch READ OFF the plan's resolved contract: no fleet
    # runner wrapper, and no bare branch-name fallback inside a shell string.
    assert pull_primary_argv(plan=plan) == [
        "git",
        "-C",
        str(tmp_path),
        "pull",
        "--ff-only",
        "origin",
        plan.integration.contract.default_branch,
    ]
    # The venue is a resolved default-branch TIP, never the item's merge sha.
    assert janitor_worktree_add_argv(plan=plan, tip="origin/main") == [
        "git",
        "-C",
        str(tmp_path),
        "worktree",
        "add",
        "--detach",
        str(tmp_path / "janitor-co"),
        "origin/main",
    ]
    assert janitor_venue_contains_merge_argv(plan=plan, tip="origin/main", merge_sha="cafe01") == [
        "git",
        "-C",
        str(tmp_path),
        "merge-base",
        "--is-ancestor",
        "cafe01",
        "origin/main",
    ]
    assert janitor_worktree_remove_argv(plan=plan) == [
        "git",
        "-C",
        str(tmp_path),
        "worktree",
        "remove",
        "--force",
        str(tmp_path / "janitor-co"),
    ]
    assert janitor_trust_argv() == ["mise", "trust"]
    # The bootstrap argv is the RESOLVED recipe's own command, so an undeclared
    # key still produces this fleet's shipped invocation and a declared one
    # produces the adopter's, verbatim.
    assert janitor_bootstrap_argv(recipe=janitor_bootstrap_recipe_from_block(block={})) == [
        "mise",
        "exec",
        "--",
        "just",
        "install-commit-refuse-hooks",
    ]
    assert janitor_bootstrap_argv(
        recipe=janitor_bootstrap_recipe_from_block(
            block={"janitor_bootstrap": {"recipe": "make install-hooks"}}
        )
    ) == ["make", "install-hooks"]
    assert janitor_core_clone_argv(plan=plan) == [
        "git",
        "clone",
        "--quiet",
        "--depth",
        "1",
        "--branch",
        "master",
        "https://github.com/thewoolleyman/livespec.git",
        str(tmp_path / "janitor-co" / ".livespec-core"),
    ]


def test_janitor_core_ref_from_config_reads_compat_pin(tmp_path: Path) -> None:
    """A declared pin is honored; an undeclared one resolves to the unresolved sentinel.

    The `master` these arms used to answer is exactly the silent moving-tip
    default the janitor-core-provisioning-resolution clause forbids.
    """
    assert (
        janitor_core_ref_from_config(
            config_text='{ "livespec-orchestrator-beads-fabro": { "compat": { "pinned": "v1" } } }'
        )
        == "v1"
    )
    assert janitor_core_ref_from_config(config_text="{}") == UNRESOLVED_JANITOR_CORE
    assert janitor_core_ref_from_config(config_text="not-jsonc") == UNRESOLVED_JANITOR_CORE
    assert janitor_core_ref_from_config(config_text="[]") == UNRESOLVED_JANITOR_CORE
    assert (
        janitor_core_ref_from_config(
            config_text='{ "livespec-orchestrator-beads-fabro": { "compat": { "pinned": "" } } }'
        )
        == UNRESOLVED_JANITOR_CORE
    )
    assert dispatcher.janitor_core_ref(repo=tmp_path / "missing-config") == UNRESOLVED_JANITOR_CORE
    # The clone repository keeps a fleet default, because an ABSENT `core_repo`
    # is a complete answer where an absent pin is not.
    assert janitor_core_repo_url_from_config(config_text="{}") == FLEET_JANITOR_CORE_REPO_URL


def test_parse_pr_view_rejects_unusable_shapes() -> None:
    assert parse_pr_view(stdout="not json") is None
    assert parse_pr_view(stdout="[1, 2]") is None
    assert parse_pr_view(stdout=json.dumps({"state": "OPEN"})) is None


def test_parse_pr_view_reads_fields_and_defaults() -> None:
    full = parse_pr_view(stdout=_pr_json(state="MERGED", armed=True, sha="abc123"))
    assert full is not None
    assert (full.number, full.state, full.auto_merge_armed) == (7, "MERGED", True)
    assert full.merge_sha == "abc123"
    assert full.terminal_required_check_failures == ()
    sparse = parse_pr_view(stdout=json.dumps({"number": 3}))
    assert sparse is not None
    assert (sparse.state, sparse.merge_state_status) == ("UNKNOWN", "UNKNOWN")
    assert sparse.auto_merge_armed is False
    assert sparse.merge_sha is None
    assert sparse.terminal_required_check_failures == ()
    weird = parse_pr_view(stdout=json.dumps({"number": 3, "mergeCommit": {"oid": ""}}))
    assert weird is not None
    assert weird.merge_sha is None
    nonsense = parse_pr_view(stdout=json.dumps({"number": 3, "mergeCommit": "abc"}))
    assert nonsense is not None
    assert nonsense.merge_sha is None


def test_parse_pr_view_records_only_required_terminal_check_failures() -> None:
    view = parse_pr_view(
        stdout=_pr_json(
            checks=[
                {"name": "check-coverage", "isRequired": True, "conclusion": "FAILURE"},
                {"name": "lint", "required": True, "conclusion": "success"},
                {"name": "docs", "isRequired": False, "conclusion": "failure"},
                {"name": "slow-ci", "isRequired": True, "status": "IN_PROGRESS"},
                {"context": "startup", "isRequired": True, "conclusion": "startup_failure"},
            ]
        )
    )
    assert view is not None
    assert view.terminal_required_check_failures == ("check-coverage", "startup")


def test_parse_pr_view_reads_connection_shaped_status_check_rollup() -> None:
    view = parse_pr_view(
        stdout=json.dumps(
            {
                "number": 7,
                "statusCheckRollup": {
                    "nodes": [
                        {
                            "name": "check-coverage",
                            "isRequired": True,
                            "conclusion": "FAILURE",
                        }
                    ]
                },
            }
        )
    )
    assert view is not None
    assert view.terminal_required_check_failures == ("check-coverage",)


def test_parse_pr_view_reads_context_connection_shaped_status_check_rollup() -> None:
    view = parse_pr_view(
        stdout=json.dumps(
            {
                "number": 7,
                "statusCheckRollup": {
                    "contexts": {
                        "nodes": [
                            {
                                "name": "check-coverage",
                                "isRequired": True,
                                "conclusion": "FAILURE",
                            }
                        ]
                    }
                },
            }
        )
    )
    assert view is not None
    assert view.terminal_required_check_failures == ("check-coverage",)


# The fake token the autouse fixture plants in the process env; the
# overlay must carry it VERBATIM (and nothing else may — journals,
# argvs, and the committed config stay token-free).
_FAKE_TOKEN_LINE = 'CLAUDE_CODE_OAUTH_TOKEN = "test-oauth-token"'
_FAKE_GITHUB_TOKEN = "test-github-token"
# Projected under the FULL name GITHUB_TOKEN, never the short GH_TOKEN:
# gh/git prefer GH_TOKEN, so a projected GH_TOKEN would shadow Fabro's
# fresh per-exec GITHUB_TOKEN and go stale past the ~60-min token TTL.
_FAKE_GITHUB_TOKEN_LINE = 'GITHUB_TOKEN = "test-github-token"'
_FAKE_GITHUB_APP_ID_LINE = 'GITHUB_APP_ID = "42"'
_FAKE_GITHUB_PRIVATE_KEY_LINE = 'GITHUB_PRIVATE_KEY = "stub-pem"'
_GH_REFRESH_BIN = "/workspace/.livespec-github-bin"

# The dead interpolation channel: fabro resolves {{ env.* }} in the
# server-spawned WORKER, whose env is a fail-closed allowlist
# (fabro-server/src/spawn_env.rs), so this literal must never appear in
# a materialized overlay — it would flow through to the sandbox as-is.
_ENV_INTERPOLATION_LITERAL = "{{ env.CLAUDE_CODE_OAUTH_TOKEN }}"
_GH_ENV_INTERPOLATION_LITERAL = "{{ env.GITHUB_TOKEN }}"

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)

# A minimal workflow graph for the payload materializer to render: one node
# timeout plus the run-level stall watchdog, which is the shape the literal-
# duration rewrite requires (commands/_dispatcher_graph_render.py).
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


def test_render_run_config_overlay_rewrites_graph_and_appends_env_token(
    tmp_path: Path,
) -> None:
    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=overlay_token,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None
    assert f'graph = "{tmp_path / "workflow.fabro"}"' in rendered
    assert 'graph = "workflow.fabro"' not in rendered
    # The overlay IS the run-scoped credential projection: it appends
    # the [environments.<id>.env] table carrying the real token value
    # read from the Dispatcher's process env. No interpolation literal
    # may survive into it.
    assert "[environments.livespec-ci.env]" in rendered
    assert _FAKE_TOKEN_LINE in rendered
    assert _FAKE_GITHUB_TOKEN_LINE in rendered
    assert _ENV_INTERPOLATION_LITERAL not in rendered
    assert _GH_ENV_INTERPOLATION_LITERAL not in rendered


def test_render_run_config_overlay_prepares_refreshing_gh_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Long-lived agent sessions must not depend on the one-shot overlay token.

    The sandbox receives the GitHub App inputs plus a `gh` wrapper that
    replaces the sandbox-local `gh` binary after reading the sandbox's
    live PATH. That makes an in-session `just check` past the
    installation-token TTL use a fresh token without replacing the
    container's mise/just/uv/node/npx PATH with the Fabro worker PATH.
    """
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    overlay_token = "test-oauth-token"

    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=overlay_token,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )

    assert rendered is not None
    env_table_at = rendered.index("[environments.livespec-ci.env]")
    assert "livespec-refreshing-gh-wrapper" in rendered[:env_table_at]
    assert "mint_app_token.py" in rendered[:env_table_at]
    assert 'token="$(python3 ' in rendered[:env_table_at]
    assert 'real_gh="$(command -v gh)"' in rendered[:env_table_at]
    assert 'mv "$real_gh" "$wrapped_gh"' in rendered[:env_table_at]
    env_table = rendered[env_table_at:]
    assert "\nPATH = " not in env_table
    assert "{{ env.PATH }}" not in rendered
    assert _FAKE_GITHUB_APP_ID_LINE in rendered
    assert _FAKE_GITHUB_PRIVATE_KEY_LINE in rendered


def test_render_run_config_overlay_projects_gh_mint_helper_for_target_without_scripts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gh wrapper must not resolve helpers from the target repo checkout."""
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    overlay_token = "test-oauth-token"

    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=overlay_token,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )

    assert rendered is not None
    env_table_at = rendered.index("[environments.livespec-ci.env]")
    prepare_steps = rendered[:env_table_at]
    assert "/workspace/.livespec-gh-refresh/bin/mint_app_token.py" in prepare_steps
    assert "$PWD/.claude-plugin/scripts/bin/mint_app_token.py" not in prepare_steps
    assert 'token="$(python3 "$mint")"' in prepare_steps
    assert 'tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz")' in prepare_steps


def test_render_run_config_overlay_ignores_target_repo_mint_helper_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Control: repos shipping the old helper still use the projected helper."""
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    target_helper = tmp_path / ".claude-plugin" / "scripts" / "bin" / "mint_app_token.py"
    target_helper.parent.mkdir(parents=True)
    target_helper.write_text("raise SystemExit('target helper must not run')\n", encoding="utf-8")
    overlay_token = "test-oauth-token"

    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=overlay_token,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )

    assert rendered is not None
    env_table_at = rendered.index("[environments.livespec-ci.env]")
    prepare_steps = rendered[:env_table_at]
    assert str(target_helper) not in prepare_steps
    assert "/workspace/.livespec-gh-refresh/bin/mint_app_token.py" in prepare_steps


def test_projected_gh_wrapper_publishes_for_target_without_scripts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A target without the orchestrator scripts tree still reaches PR create."""
    _assert_projected_gh_wrapper_publishes(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        target_helper_source=None,
    )


def test_projected_gh_wrapper_publishes_when_target_helper_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Control: a target-local helper cannot shadow the projected helper."""
    _assert_projected_gh_wrapper_publishes(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        target_helper_source="echo target-helper-token\n",
    )


def _assert_projected_gh_wrapper_publishes(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_helper_source: str | None,
) -> None:
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    # The production bundle root is the absolute in-sandbox path
    # /workspace/.livespec-gh-refresh. This test EXECUTES the rendered prepare
    # script for real, so without redirecting that root the script would
    # `rm -rf` and `mkdir` at the RUNNER's filesystem root: refused under uid
    # 1000 (`mkdir: Permission denied`, measured), and under uid 0 it would
    # succeed by deleting a real /workspace. Redirect it into tmp_path so the
    # script stays hermetic under both uids.
    sandbox_root = tmp_path / "sandbox-bundle"
    monkeypatch.setenv(SANDBOX_GH_REFRESH_ROOT_ENV_VAR, str(sandbox_root))
    if target_helper_source is not None:
        target_helper = tmp_path / ".claude-plugin" / "scripts" / "bin" / "mint_app_token.py"
        target_helper.parent.mkdir(parents=True)
        target_helper.write_text(target_helper_source, encoding="utf-8")

    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_GITHUB_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )

    assert rendered is not None
    scripts = _gh_refresh_prepare_scripts(rendered=rendered)
    # Guard against a regression to a hardcoded root: with the lever set, the
    # production path must not appear in any emitted step.
    for script in scripts:
        assert DEFAULT_SANDBOX_GH_REFRESH_ROOT not in script
    # The payload must never ride in one argv slot again (bd-ib-gnli): fabro
    # runs each step as `bash -c <script>`, and Linux caps a SINGLE argument at
    # MAX_ARG_STRLEN (131072), not the total. One 186KB step killed every
    # dispatch at exec with "argument list too long".
    for script in scripts:
        assert len(script.encode()) <= MAX_PREPARE_STEP_BYTES
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture = tmp_path / "gh-calls.txt"
    mint_arg_log = tmp_path / "mint-args.txt"
    _write_executable(
        path=bin_dir / "gh",
        source="#!/usr/bin/env bash\n"
        "set -eu\n"
        "{\n"
        '  printf "args=%s\\n" "$*"\n'
        '  printf "GH_TOKEN=%s\\n" "${GH_TOKEN:-}"\n'
        '  printf "GITHUB_TOKEN=%s\\n" "${GITHUB_TOKEN:-}"\n'
        '} >> "$GH_CAPTURE"\n'
        'if [ "$1" = "auth" ] && [ "$2" = "status" ]; then exit 0; fi\n'
        'if [ "$1" = "pr" ] && [ "$2" = "create" ]; then exit 0; fi\n'
        "exit 64\n",
    )
    env = {
        **os.environ,
        "GH_CAPTURE": str(capture),
        "MINT_ARG_LOG": str(mint_arg_log),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
    }

    for index, step in enumerate(scripts):
        prepare_script = tmp_path / f"prepare-gh-{index}.sh"
        prepare_script.write_text(step, encoding="utf-8")
        subprocess.run(
            ["/bin/bash", str(prepare_script)],
            cwd=tmp_path,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
    assert (bin_dir / "gh.livespec-real").is_file()

    _write_executable(
        path=bin_dir / "python3",
        source="#!/usr/bin/env bash\n"
        "set -eu\n"
        'printf "%s\\n" "$1" >> "$MINT_ARG_LOG"\n'
        "printf minted-token\n",
    )

    for argv in (["gh", "auth", "status"], ["gh", "pr", "create", "--title", "x"]):
        subprocess.run(
            argv,
            cwd=tmp_path,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    assert capture.read_text(encoding="utf-8").splitlines() == [
        "args=auth status",
        "GH_TOKEN=minted-token",
        "GITHUB_TOKEN=minted-token",
        "args=pr create --title x",
        "GH_TOKEN=minted-token",
        "GITHUB_TOKEN=minted-token",
    ]
    projected_mint = sandbox_root / "bin" / "mint_app_token.py"
    # The bundle materialized under the redirected root, not at the runner root.
    assert projected_mint.is_file()
    # And `gh` invoked THAT helper both times -- the projected bundle's, never
    # the target repo's, which is the property this pair of tests exists for.
    assert mint_arg_log.read_text(encoding="utf-8").splitlines() == [
        str(projected_mint),
        str(projected_mint),
    ]


def _write_executable(*, path: Path, source: str) -> None:
    """Materialize an executable stub on the fake PATH."""
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _gh_refresh_prepare_scripts(*, rendered: str) -> list[str]:
    """Every prepare-step script the gh-refresh block emits, in order.

    Bounded at the NEXT dispatcher-materialized block, not at the environment
    table: the overlay appends further blocks after this one, and the caller
    EXECUTES what this returns against the runner's own environment. Reading to
    the table therefore handed a later block's steps to a `bash` that has the
    real `$HOME` — the plugin-cache gate then materialized its program under
    `~/.claude/plugins` on every suite run, which is both a write outside the
    fixture and a Python file the coverage gate then measured.
    """
    marker = "# --- Dispatcher-materialized livespec-refreshing-gh-wrapper ---"
    start = rendered.index(marker)
    tail = rendered[start + len(marker) :]
    boundaries = [
        offset
        for offset in (tail.find("\n# --- Dispatcher-materialized"), tail.find("[environments."))
        if offset != -1
    ]
    end = min(boundaries) if boundaries else len(tail)
    found = re.findall(r"script = '''\n(.*?)\n'''", tail[:end], re.DOTALL)
    assert found
    return list(found)


def test_render_run_config_overlay_keeps_absolute_graph_path(tmp_path: Path) -> None:
    absolute_graph = tmp_path / "elsewhere" / "g.fabro"
    committed = _COMMITTED_WORKFLOW_TOML.replace(
        'graph = "workflow.fabro"', f'graph = "{absolute_graph}"'
    )
    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=committed,
        workflow_dir=tmp_path / "workflow-dir",
        token=overlay_token,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None
    assert f'graph = "{absolute_graph}"' in rendered
    assert str(tmp_path / "workflow-dir") not in rendered.split("[environments")[0]


def test_render_run_config_overlay_rejects_unusable_shapes(tmp_path: Path) -> None:
    overlay_token = "test-oauth-token"
    assert (
        render_run_config_overlay(
            committed_text="_version = 1\n",
            workflow_dir=tmp_path,
            token=overlay_token,
            github_token=_FAKE_GITHUB_TOKEN,
            siblings=None,
        )
        is None
    )
    no_graph = '[workflow]\n\n[run.environment]\nid = "livespec-ci"\n'
    assert (
        render_run_config_overlay(
            committed_text=no_graph,
            workflow_dir=tmp_path,
            token=overlay_token,
            github_token=_FAKE_GITHUB_TOKEN,
            siblings=None,
        )
        is None
    )
    # The env-table append targets [environments.<id>.env], so a config
    # without a [run.environment] id has nowhere to project the token.
    no_environment = '[workflow]\ngraph = "workflow.fabro"\n'
    assert (
        render_run_config_overlay(
            committed_text=no_environment,
            workflow_dir=tmp_path,
            token=overlay_token,
            github_token=_FAKE_GITHUB_TOKEN,
            siblings=None,
        )
        is None
    )
    # Non-canonical whitespace: the graph value parses but the canonical
    # `graph = "<value>"` rewrite needle is absent, so the shape is refused
    # rather than silently shipping a relative graph path.
    spaced = '[workflow]\ngraph =  "workflow.fabro"\n\n[run.environment]\nid = "livespec-ci"\n'
    assert (
        render_run_config_overlay(
            committed_text=spaced,
            workflow_dir=tmp_path,
            token=overlay_token,
            github_token=_FAKE_GITHUB_TOKEN,
            siblings=None,
        )
        is None
    )


# The sandbox sibling-clone plan the render tests exercise: clones land
# under the fabro sandbox workspace root, mirroring how livespec CI
# provisions LIVESPEC_SIBLING_CLONES_ROOT for the cross-repo wiring
# check.
_SIBLINGS = SiblingClones(
    owner="thewoolleyman",
    repos=("livespec", "livespec-dev-tooling"),
    clones_root="/workspace/siblings",
)


def _expected_clone_script(repo_name: str) -> str:
    """The per-member sibling-clone script the overlay MUST render.

    Tolerant by construction: a member that cannot be cloned is reported
    on stderr and skipped (`exit 0`) rather than failing the whole
    prepare step and killing every dispatch, and `GIT_TERMINAL_PROMPT=0`
    keeps a missing/unreachable repo from falling back to git's
    credential prompt (which in the TTY-less sandbox surfaces as a
    misleading `could not read Username` auth error).
    """
    url = f"https://github.com/thewoolleyman/{repo_name}.git"
    prefix = (
        "livespec-orchestrator-beads-fabro dispatcher: sibling clone skipped" f" for {repo_name}: "
    )
    return (
        "mkdir -p /workspace/siblings || exit 1;"
        f" GIT_TERMINAL_PROMPT=0 git ls-remote --exit-code {url} HEAD"
        " >/dev/null 2>&1 ||"
        f" {{ echo '{prefix}repository not reachable (nonexistent or no access)'"
        " >&2; exit 0; };"
        f" GIT_TERMINAL_PROMPT=0 git clone --quiet --depth 1 {url}"
        f" /workspace/siblings/{repo_name} ||"
        f" {{ echo '{prefix}clone failed after a successful reachability probe"
        " (transient)' >&2; exit 0; }"
    )


_LIVESPEC_CLONE_STEP_LINE = "script = " + json.dumps(_expected_clone_script("livespec"))

_DEV_TOOLING_CLONE_STEP_LINE = "script = " + json.dumps(
    _expected_clone_script("livespec-dev-tooling")
)

_SIBLING_ENV_LINE = 'LIVESPEC_SIBLING_CLONES_ROOT = "/workspace/siblings"'
_CURRENCY_GATE_ENV_LINE = 'LIVESPEC_CURRENCY_GATE = "fail"'
_TMUX_TMPDIR_ENV_LINE = 'TMUX_TMPDIR = "/workspace/.tmux"'
_TMUX_TMPDIR_PREPARE_STEP_LINE = (
    'script = "mkdir -p /workspace/.tmux && chmod 700 /workspace/.tmux"'
)

# The console's `check-doctor-static` resolves livespec CORE inside the Fabro
# sandbox via this projected env key, valued at the in-sandbox core-sibling
# clone path (`<clones_root>/livespec/.claude-plugin`).
_CORE_PLUGIN_ROOT_ENV_LINE = (
    'LIVESPEC_CORE_PLUGIN_ROOT = "/workspace/siblings/livespec/.claude-plugin"'
)


def test_parse_fleet_members_reads_owner_and_member_repos() -> None:
    members = parse_fleet_members(manifest_text=_FLEET_MANIFEST_TEXT)
    assert members == FleetMembers(
        owner="thewoolleyman",
        repos=("livespec", "livespec-dev-tooling", "repo"),
    )


def test_parse_fleet_members_rejects_malformed_manifests() -> None:
    """Fail-fast philosophy: a manifest that does not parse into an
    owner plus a non-empty members list (with GitHub-slug-shaped names —
    the values are spliced into prepare-step scripts, so anything else
    is refused) yields None, and the caller refuses the dispatch with an
    actionable error instead of cloning from a guessed list."""
    bad_manifests = [
        "not json {{",
        json.dumps([1, 2]),
        json.dumps({"members": [{"repo": "livespec"}]}),
        json.dumps({"owner": "bad owner!", "members": [{"repo": "livespec"}]}),
        json.dumps({"owner": "o", "members": {}}),
        json.dumps({"owner": "o", "members": ["livespec"]}),
        json.dumps({"owner": "o", "members": [{"class": "core"}]}),
        json.dumps({"owner": "o", "members": [{"repo": "bad repo"}]}),
        json.dumps({"owner": "o", "members": []}),
    ]
    for manifest_text in bad_manifests:
        assert parse_fleet_members(manifest_text=manifest_text) is None


def test_parse_fleet_members_accepts_legacy_members_key() -> None:
    """The livespec v148 rename made `fleet` the canonical manifest key
    (the canned `_FLEET_MANIFEST_TEXT` above mirrors it). The parser MUST
    still accept the pre-rename `members` key as a fallback so a
    not-yet-migrated manifest copy keeps resolving sibling clones instead
    of failing every dispatch — the gap that the rename regressed."""
    legacy = (
        "{\n"
        '  "owner": "thewoolleyman",\n'
        '  "members": [{ "repo": "livespec", "class": "core" }]\n'
        "}\n"
    )
    assert parse_fleet_members(manifest_text=legacy) == FleetMembers(
        owner="thewoolleyman",
        repos=("livespec",),
    )


def test_render_run_config_overlay_appends_sibling_clone_steps_and_env_root(
    tmp_path: Path,
) -> None:
    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=overlay_token,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=_SIBLINGS,
    )
    assert rendered is not None
    assert rendered.count("[[run.prepare.steps]]") == 4
    assert _LIVESPEC_CLONE_STEP_LINE in rendered
    assert _DEV_TOOLING_CLONE_STEP_LINE in rendered
    assert _TMUX_TMPDIR_PREPARE_STEP_LINE in rendered
    # The clone prepare steps are appended BEFORE the env table header,
    # and the clones-root env key lands INSIDE [environments.<id>.env]
    # (after the header) so it reaches the sandbox as container-level
    # environment alongside the credential — the single declaration
    # point TOML allows for that table.
    env_table_at = rendered.index("[environments.livespec-ci.env]")
    assert rendered.index(_LIVESPEC_CLONE_STEP_LINE) < env_table_at
    assert rendered.index(_DEV_TOOLING_CLONE_STEP_LINE) < env_table_at
    assert rendered.index(_TMUX_TMPDIR_PREPARE_STEP_LINE) < env_table_at
    assert rendered.index(_SIBLING_ENV_LINE) > env_table_at
    assert _FAKE_TOKEN_LINE in rendered
    assert _FAKE_GITHUB_TOKEN_LINE in rendered


def test_render_run_config_overlay_sibling_clone_steps_are_valid_bash(
    tmp_path: Path,
) -> None:
    """Every rendered sibling-clone step MUST be syntactically valid bash.

    A string-equality test against a hand-written expected fixture cannot
    catch a bug that was introduced in BOTH the implementation and the
    fixture at once (exactly what happened: the implementation's closing
    diagnostic clause emitted an extra literal `}` from a non-f-string
    `}}`, and `_expected_clone_script` mirrored the same defect, so the
    two sides always agreed with each other while both were wrong). This
    test instead decodes each rendered step's `script` value and asks bash
    itself whether it is well-formed — a property no fixture can
    accidentally get wrong in lockstep with the implementation.
    """
    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=overlay_token,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=_SIBLINGS,
    )
    assert rendered is not None
    # Each rendered `[[run.prepare.steps]]` table's `script` value is written as
    # `f"script = {json.dumps(script)}"` (a JSON string literal on its own
    # line) -- decode those lines directly rather than pulling in a TOML
    # parser dependency this repo does not otherwise need.
    script_lines = [line for line in rendered.splitlines() if line.startswith("script = ")]
    clone_scripts = [
        json.loads(line.removeprefix("script = "))
        for line in script_lines
        if "clone --quiet --depth 1" in line
    ]
    assert len(clone_scripts) == len(_SIBLINGS.repos)
    for script in clone_scripts:
        completed = subprocess.run(
            ["bash", "-n", "-c", script],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, (script, completed.stderr)


def test_render_run_config_overlay_sibling_clone_steps_tolerate_bad_members(
    tmp_path: Path,
) -> None:
    """Each rendered per-member clone step MUST degrade per-member.

    A manifest entry naming a repo that does not exist yet (the
    2026-08-15 livespec-driver-pi birth race) previously failed the whole
    prepare step and killed EVERY dispatch, after git fell back to a
    credential prompt the TTY-less sandbox reported as
    `could not read Username`. The rendered script therefore pins
    `GIT_TERMINAL_PROMPT=0` on every git invocation, probes reachability
    with `git ls-remote --exit-code` so a missing repo is named as such
    rather than as an auth failure, and exits 0 on either failure so the
    surviving members still clone.
    """
    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=overlay_token,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=_SIBLINGS,
    )
    assert rendered is not None
    for repo_name in _SIBLINGS.repos:
        script = _expected_clone_script(repo_name)
        assert "script = " + json.dumps(script) in rendered
        # Never prompt: a missing/unreachable repo fails immediately.
        assert script.count("GIT_TERMINAL_PROMPT=0 git ") == 2
        # An explicit reachability probe separates the two diagnostics.
        assert "git ls-remote --exit-code" in script
        assert (
            f"sibling clone skipped for {repo_name}:"
            " repository not reachable (nonexistent or no access)" in script
        )
        assert (
            f"sibling clone skipped for {repo_name}:"
            " clone failed after a successful reachability probe (transient)" in script
        )
        # Both failure branches surface on stderr and then continue.
        assert script.count(">&2; exit 0; }") == 2
        # Only the mkdir may fail the step.
        assert script.count("exit 1") == 1
        # NON-BREAKING: the healthy path still runs the identical clone.
        assert (
            "git clone --quiet --depth 1 https://github.com/thewoolleyman/"
            f"{repo_name}.git /workspace/siblings/{repo_name}" in script
        )


def test_render_run_config_overlay_without_siblings_appends_no_clone_steps(
    tmp_path: Path,
) -> None:
    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=overlay_token,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None
    assert rendered.count("[[run.prepare.steps]]") == 2
    assert _TMUX_TMPDIR_PREPARE_STEP_LINE in rendered
    assert "LIVESPEC_SIBLING_CLONES_ROOT" not in rendered


def test_render_run_config_overlay_projects_core_plugin_root(tmp_path: Path) -> None:
    """The overlay MUST project LIVESPEC_CORE_PLUGIN_ROOT at the in-sandbox
    core-sibling clone path.

    The sandbox is spawned with a fail-closed env allowlist
    (fabro-server/src/spawn_env.rs) and carries no installed-plugin registry,
    so a fleet repo whose janitor resolves the livespec CORE plugin (the
    console's `check-doctor-static`) has no way to find core unless the overlay
    projects LIVESPEC_CORE_PLUGIN_ROOT — the SAME container-level env-table
    mechanism that carries GH_TOKEN. The value is derived from the siblings
    clones root (`<clones_root>/livespec/.claude-plugin`), and the key lands
    INSIDE [environments.<id>.env] alongside the credential so it reaches every
    node's `just check` subprocesses.
    """
    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=overlay_token,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=_SIBLINGS,
    )
    assert rendered is not None
    env_table_at = rendered.index("[environments.livespec-ci.env]")
    assert _CORE_PLUGIN_ROOT_ENV_LINE in rendered
    assert rendered.index(_CORE_PLUGIN_ROOT_ENV_LINE) > env_table_at


def test_render_run_config_overlay_without_core_sibling_omits_core_plugin_root(
    tmp_path: Path,
) -> None:
    """No `livespec` core sibling cloned → no core-plugin-root projection (the
    derived path would not resolve), mirroring the sibling-clones-root guard."""
    siblings = SiblingClones(
        owner="thewoolleyman",
        repos=("livespec-dev-tooling",),
        clones_root="/workspace/siblings",
    )
    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=overlay_token,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=siblings,
    )
    assert rendered is not None
    assert "LIVESPEC_CORE_PLUGIN_ROOT" not in rendered


def test_committed_implement_workflow_overlay_carries_full_fleet_sandbox_env() -> None:
    """Factory-artifact guard: the SHIPPED implement-work-item workflow's
    materialized run-config overlay MUST carry EVERY env key a fleet repo's
    sandbox janitor needs.

    The hermetic and live golden masters don't exercise this seam — the live
    fixture's `just check` is core-independent (the Slice-6 / VP4 residual gap) —
    so a missing sandbox-env projection sails through them. This deterministic
    test binds the REAL committed workflow artifact to overlay completeness: it
    fails on a pre-fix overlay that omits LIVESPEC_CORE_PLUGIN_ROOT (the gap that
    broke the console's E-3a dispatch in the sandbox janitor), and guards against
    dropping ANY required key as the fleet janitor's needs grow.
    """
    repo_root = Path(__file__).resolve().parents[3]
    workflow_toml = (
        repo_root
        / ".claude-plugin"
        / ".fabro"
        / "workflows"
        / "implement-work-item"
        / "workflow.toml"
    )
    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=workflow_toml.read_text(encoding="utf-8"),
        workflow_dir=workflow_toml.parent,
        token=overlay_token,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=_SIBLINGS,
    )
    assert rendered is not None
    env_table_at = rendered.index("[environments.livespec-ci.env]")
    required_sandbox_env_lines = (
        _FAKE_TOKEN_LINE,
        _FAKE_GITHUB_TOKEN_LINE,
        _SIBLING_ENV_LINE,
        _CORE_PLUGIN_ROOT_ENV_LINE,
        _CURRENCY_GATE_ENV_LINE,
        _TMUX_TMPDIR_ENV_LINE,
    )
    for line in required_sandbox_env_lines:
        assert line in rendered, f"overlay missing required sandbox env line: {line}"
        assert rendered.index(line) > env_table_at


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


_BLOCKED_INSPECT_JSON = json.dumps(
    {
        "run_id": "01RUNBLOCKED",
        "status": {"kind": "blocked", "blocked_reason": "human_input_required"},
    }
)
_HUMAN_INPUT_REQUIRED_INSPECT_JSON = json.dumps(
    {
        "run_id": "01RUNPARKED",
        "status": {"kind": "human_input_required"},
    }
)


def test_engine_green_runs_janitor_in_fresh_checkout(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(stdout="fabro done"),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe01")),
            _pr_association(),
            _ok(),  # pull-primary
            *_venue_resolution(),
            _ok(),  # janitor-checkout-preclean
            _ok(),  # janitor-checkout-add
            _ok(),  # janitor-checkout-trust
            _ok(),  # janitor-checkout-bootstrap
            _ok(),  # janitor-checkout-bootstrap-in-checkout
            _ok(),  # janitor-core-provision
            _ok(),  # janitor-post-merge
            _ok(),  # janitor-checkout-remove
        ]
    )
    outcome, journal, naps = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("green", "done")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe01")
    assert naps == []
    first_argv, first_cwd = runner.calls[0]
    assert first_argv[:2] == ["fabro", "run"]
    assert first_cwd == tmp_path
    # No host worktree prep BEFORE the fabro run (Architecture C): the
    # only worktree commands belong to the post-merge janitor checkout.
    assert all("worktree" not in argv for argv, _ in runner.calls[:4])
    stages = [record["stage"] for record in journal.records]
    assert stages == [
        "fabro-run",
        "pr-view",
        "pr-view",
        "pr-merge-sha-recording",
        "pull-primary",
        "janitor-checkout-preclean",
        "janitor-checkout-add",
        "janitor-checkout-trust",
        "janitor-checkout-bootstrap",
        "janitor-checkout-bootstrap-in-checkout",
        "janitor-core-provision",
        "janitor-post-merge",
        "janitor-checkout-remove",
    ]
    checkout = tmp_path / "janitor-co"
    # The venue read sits between pull-primary (4) and the preclean (6): the
    # merge-containment probe proving the tip carries `cafe01`. The branch it
    # names comes off the plan's resolved contract rather than a probe of its
    # own. The checkout is added at that TIP, not at the sha.
    assert runner.calls[5][0] == [
        "git",
        "-C",
        str(tmp_path),
        "merge-base",
        "--is-ancestor",
        "cafe01",
        "origin/master",
    ]
    add_argv, add_cwd = runner.calls[7]
    assert add_argv == [
        "git",
        "-C",
        str(tmp_path),
        "worktree",
        "add",
        "--detach",
        str(checkout),
        "origin/master",
    ]
    assert add_cwd == tmp_path
    remove_argv = ["git", "-C", str(tmp_path), "worktree", "remove", "--force", str(checkout)]
    assert runner.calls[6][0] == remove_argv
    assert runner.calls[13][0] == remove_argv
    assert runner.envs[12] == {
        "LIVESPEC_CORE_PLUGIN_ROOT": str(checkout / ".livespec-core" / ".claude-plugin")
    }


def test_engine_fails_when_green_janitor_checkout_cleanup_fails(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(stdout="fabro done"),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe01")),
            _pr_association(),
            _ok(),  # pull-primary
            *_venue_resolution(),
            _ok(),  # janitor-checkout-preclean
            _ok(),  # janitor-checkout-add
            _ok(),  # janitor-checkout-trust
            _ok(),  # janitor-checkout-bootstrap
            _ok(),  # janitor-checkout-bootstrap-in-checkout
            _ok(),  # janitor-core-provision
            _ok(),  # janitor-post-merge
            _err(stderr="checkout has vanished"),  # janitor-checkout-remove
        ]
    )
    outcome, journal, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "janitor-checkout-remove")
    assert outcome.detail == "checkout has vanished"
    assert [record["stage"] for record in journal.records][-1] == "janitor-checkout-remove"


def test_engine_fails_when_fabro_run_fails_and_trims_detail(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=[_err(stderr="x" * 3000)])
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "fabro-run")
    assert len(outcome.detail) == 2000


def test_engine_fabro_run_failure_surfaces_inspect_failure_detail(tmp_path: Path) -> None:
    failed_inspect = json.dumps(
        {
            "status": {"kind": "failed", "reason": "workflow_error"},
            "failure": {
                "causes": ["script failed with exit 2: pytest fixture broke"],
                "category": "deterministic",
                "signature": "fix|deterministic|script failed with exit 2",
            },
        }
    )
    runner = _FakeRunner(
        queue=[
            CommandResult(
                exit_code=1,
                stdout="Run: 01RUNCAUSE\n",
                stderr="ACP turn failed",
            ),
            _ok(stdout=failed_inspect),
        ]
    )

    outcome, journal, _ = _dispatch(runner=runner, repo=tmp_path)

    assert (outcome.status, outcome.stage) == ("failed", "fabro-run")
    assert outcome.fabro_run_id == "01RUNCAUSE"
    assert "script failed with exit 2: pytest fixture broke" in outcome.detail
    assert "category=deterministic" in outcome.detail
    assert "signature=fix|deterministic|script failed with exit 2" in outcome.detail
    assert [record["stage"] for record in journal.records] == ["fabro-run", "fabro-inspect"]


def test_engine_blocked_run_is_a_third_terminal_state(tmp_path: Path) -> None:
    parked = CommandResult(
        exit_code=1,
        stdout="",
        stderr=(
            "    Run: 01RUNBLOCKED\n"
            "Interview ended without an answer. The run is still waiting "
            "for input; reattach to answer it.\n"
        ),
    )
    runner = _FakeRunner(queue=[parked, _ok(stdout=_BLOCKED_INSPECT_JSON)])
    outcome, journal, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("blocked", "fabro-run")
    assert (outcome.pr_number, outcome.merge_sha) == (None, None)
    assert "fabro attach 01RUNBLOCKED" in outcome.detail
    inspect_argv, inspect_cwd = runner.calls[1]
    assert inspect_argv == ["fabro", "inspect", "01RUNBLOCKED", "--json"]
    assert inspect_cwd == tmp_path
    assert len(runner.calls) == 2
    assert [record["stage"] for record in journal.records] == ["fabro-run", "fabro-inspect"]


def test_engine_human_input_required_run_is_blocked_not_failed(tmp_path: Path) -> None:
    parked = CommandResult(
        exit_code=1,
        stdout="Run: 01RUNPARKED\n",
        stderr="Needs human: R/I/A\n",
    )
    runner = _FakeRunner(queue=[parked, _ok(stdout=_HUMAN_INPUT_REQUIRED_INSPECT_JSON)])

    outcome, journal, _ = _dispatch(runner=runner, repo=tmp_path)

    assert (outcome.status, outcome.stage) == ("blocked", "fabro-run")
    assert outcome.fabro_run_id == "01RUNPARKED"
    assert "fabro attach 01RUNPARKED" in outcome.detail
    assert "failed" not in outcome.status
    assert [record["stage"] for record in journal.records] == ["fabro-run", "fabro-inspect"]


def test_engine_blocked_check_falls_back_to_exit_code_routing(tmp_path: Path) -> None:
    failed_inspect = json.dumps({"status": {"kind": "failed", "reason": "workflow_error"}})
    runner = _FakeRunner(
        queue=[
            CommandResult(exit_code=1, stdout="Run: 01RUNDEAD\n", stderr="agent died"),
            _ok(stdout=failed_inspect),
            _ok(stdout=failed_inspect),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "fabro-run")
    runner = _FakeRunner(queue=[_err(stderr="hard crash, no run line")])
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "fabro-run")
    assert len(runner.calls) == 1
    runner = _FakeRunner(
        queue=[
            CommandResult(exit_code=1, stdout="Run: 01RUNGONE\n", stderr="boom"),
            _err(stderr="inspect broke"),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "fabro-run")


def test_engine_succeeded_run_with_run_id_proceeds_to_pr_flow(tmp_path: Path) -> None:
    succeeded_inspect = json.dumps({"status": {"kind": "succeeded", "reason": "completed"}})
    runner = _FakeRunner(
        queue=[
            _ok(stdout="    Run: 01RUNGREEN\n"),
            _ok(stdout=succeeded_inspect),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe07")),
            _pr_association(),
            *_post_merge_green_tail(),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("green", "done")


def test_engine_fails_when_no_pr_found(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=[_ok(), _err(stderr="no pr")])
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "pr-view")
    runner = _FakeRunner(queue=[_ok(), _ok(stdout="garbage")])
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "pr-view")


def test_engine_arms_auto_merge_as_fallback(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=False)),
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe02")),
            _pr_association(),
            *_post_merge_green_tail(),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert outcome.status == "green"
    armed_call = runner.calls[2][0]
    assert armed_call[:3] == ["gh", "pr", "merge"]


def test_engine_skips_arming_when_pr_already_merged(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(state="MERGED", armed=False, sha="cafe03")),
            _ok(stdout=_pr_json(state="MERGED", armed=False, sha="cafe03")),
            _pr_association(),
            *_post_merge_green_tail(),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert outcome.status == "green"
    assert all(call[0][:3] != ["gh", "pr", "merge"] for call in runner.calls)


def test_engine_fails_when_review_after_arming_fails(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=False)),
            _ok(),
            _err(stderr="gh broke"),
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "pr-view")


def test_engine_updates_branch_when_behind_then_merges(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(
                stdout=_pr_json(
                    armed=True,
                    merge_state="BEHIND",
                    checks=[
                        {
                            "name": "check-coverage",
                            "isRequired": True,
                            "status": "IN_PROGRESS",
                        }
                    ],
                )
            ),
            _ok(),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe04")),
            _pr_association(),
            *_post_merge_green_tail(),
        ]
    )
    outcome, _, naps = _dispatch(runner=runner, repo=tmp_path)
    assert outcome.status == "green"
    assert naps == [0.5]
    update_call = runner.calls[3][0]
    assert update_call == ["gh", "pr", "update-branch", "7"]


def test_engine_fails_fast_when_required_check_terminally_fails(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(
                stdout=_pr_json(
                    armed=True,
                    merge_state="BLOCKED",
                    checks=[
                        {
                            "name": "check-coverage",
                            "isRequired": True,
                            "conclusion": "failure",
                        },
                        {"name": "docs", "isRequired": False, "conclusion": "failure"},
                    ],
                )
            ),
        ]
    )
    outcome, journal, naps = _dispatch(runner=runner, repo=tmp_path, attempts=80)
    assert (outcome.status, outcome.stage) == ("failed", "merge-poll")
    assert outcome.pr_number == 7
    assert "check-coverage" in outcome.detail
    assert "docs" not in outcome.detail
    assert naps == []
    assert [record["stage"] for record in journal.records] == ["fabro-run", "pr-view", "pr-view"]


def test_engine_keeps_polling_when_required_checks_are_pending(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(
                stdout=_pr_json(
                    armed=True,
                    merge_state="BLOCKED",
                    checks=[{"name": "check-coverage", "isRequired": True, "status": "QUEUED"}],
                )
            ),
            _ok(
                stdout=_pr_json(
                    armed=True,
                    merge_state="BLOCKED",
                    checks=[
                        {
                            "name": "check-coverage",
                            "isRequired": True,
                            "status": "IN_PROGRESS",
                        }
                    ],
                )
            ),
        ]
    )
    outcome, _, naps = _dispatch(runner=runner, repo=tmp_path, attempts=2)
    assert (outcome.status, outcome.stage) == ("failed", "merge-poll")
    assert outcome.detail == "PR did not reach MERGED within the poll budget"
    assert naps == [0.5]


def test_engine_poll_budget_exhaustion_keeps_pr_number(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _err(stderr="transient gh failure"),
            _ok(stdout=_pr_json(armed=True)),
        ]
    )
    outcome, _, naps = _dispatch(runner=runner, repo=tmp_path, attempts=2)
    assert (outcome.status, outcome.stage) == ("failed", "merge-poll")
    assert outcome.pr_number == 7
    assert naps == [0.5]


def test_engine_post_merge_failures_carry_merge_evidence(tmp_path: Path) -> None:
    cases = [([None, None, None, None, None, None, None, "janitor broke"], "janitor-post-merge")]
    for tail_specs, stage in cases:
        tail = [_ok() if spec is None else _err(stderr=spec) for spec in tail_specs]
        runner = _FakeRunner(
            queue=[
                _ok(),
                _ok(stdout=_pr_json(armed=True)),
                _ok(stdout=_pr_json(state="MERGED", sha="cafe05")),
                _pr_association(),
                tail[0],
                *_venue_resolution(),
                *tail[1:],
            ]
        )
        outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
        assert (outcome.status, outcome.stage) == ("failed", stage)
        assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe05")


def test_engine_primary_pull_failure_after_merge_is_degraded(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe05")),
            _pr_association(),
            _err(stderr="error: would overwrite plan/foreman/handoff.md"),
        ]
    )

    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)

    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe05")
    assert "refreshing the primary checkout" in outcome.detail
    assert "plan/foreman/handoff.md" in outcome.detail


def test_engine_janitor_red_keeps_checkout_for_diagnosis(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe05")),
            _pr_association(),
            _ok(),  # pull-primary
            *_venue_resolution(),
            _ok(),  # janitor-checkout-preclean
            _ok(),  # janitor-checkout-add
            _ok(),  # janitor-checkout-trust
            _ok(),  # janitor-checkout-bootstrap
            _ok(),  # janitor-checkout-bootstrap-in-checkout
            _ok(),  # janitor-core-provision
            _err(stderr="2 failed, 1 passed"),  # janitor red in the fresh checkout
        ]
    )
    outcome, journal, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "janitor-post-merge")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe05")
    checkout = tmp_path / "janitor-co"
    assert str(checkout) in outcome.detail
    assert "kept for diagnosis" in outcome.detail
    assert "2 failed, 1 passed" in outcome.detail
    # A red checkout is PRESERVED (no remove after the janitor ran):
    # the working tree is the diagnosis evidence.
    assert len(runner.calls) == 13
    assert [record["stage"] for record in journal.records][-1] == "janitor-post-merge"


def test_engine_degrades_when_janitor_checkout_provisioning_fails(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe08")),
            _pr_association(),
            _ok(),  # pull-primary
            *_venue_resolution(),
            _err(stderr="not a working tree"),  # preclean (deliberately ignored)
            _err(stderr="disk full"),  # janitor-checkout-add
        ]
    )
    outcome, journal, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe08")
    assert "DID NOT RUN" in outcome.detail
    assert "disk full" in outcome.detail
    assert "mise exec -- just check" in outcome.detail
    assert "not a work-item failure" in outcome.detail
    # The janitor itself never ran: the dispatch ends at the failed add.
    assert len(runner.calls) == 8
    assert [record["stage"] for record in journal.records][-1] == "janitor-checkout-add"


def test_engine_degrades_when_mise_trust_fails(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe09")),
            _pr_association(),
            _ok(),  # pull-primary
            *_venue_resolution(),
            _ok(),  # janitor-checkout-preclean
            _ok(),  # janitor-checkout-add
            _err(stderr="config not trusted"),  # janitor-checkout-trust
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert "trusting the fleet toolchain config" in outcome.detail
    assert "config not trusted" in outcome.detail
    trust_argv, trust_cwd = runner.calls[8]
    assert trust_argv == ["mise", "trust"]
    assert trust_cwd == tmp_path / "janitor-co"


def test_engine_degrades_when_janitor_bootstrap_fails(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafeab")),
            _pr_association(),
            _ok(),  # pull-primary
            *_venue_resolution(),
            _ok(),  # janitor-checkout-preclean
            _ok(),  # janitor-checkout-add
            _ok(),  # janitor-checkout-trust
            _err(stderr="no hook-install recipe"),  # janitor-checkout-bootstrap
        ]
    )
    outcome, journal, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafeab")
    assert "DID NOT RUN" in outcome.detail
    assert "no hook-install recipe" in outcome.detail
    assert "not a work-item failure" in outcome.detail
    bootstrap_argv, bootstrap_cwd = runner.calls[9]
    assert bootstrap_argv == ["mise", "exec", "--", "just", "install-commit-refuse-hooks"]
    assert bootstrap_cwd == tmp_path  # runs in plan.repo, not janitor_checkout
    assert [record["stage"] for record in journal.records][-1] == "janitor-checkout-bootstrap"
    # The STRUCTURED half of the degraded outcome: the next dispatch's
    # pre-dispatch gate matches on these, never on the prose in `detail`.
    assert outcome.step == "janitor-bootstrap"
    assert outcome.missing_integration_point is not None
    assert "install-commit-refuse-hooks" in outcome.missing_integration_point
    assert outcome.remedy is not None
    assert "dispatcher.step_waivers" in outcome.remedy


def test_engine_degrades_when_janitor_core_provisioning_fails(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafec0")),
            _pr_association(),
            _ok(),  # pull-primary
            *_venue_resolution(),
            _ok(),  # janitor-checkout-preclean
            _ok(),  # janitor-checkout-add
            _ok(),  # janitor-checkout-trust
            _ok(),  # janitor-checkout-bootstrap
            _ok(),  # janitor-checkout-bootstrap-in-checkout
            _err(stderr="core clone failed"),  # janitor-core-provision
        ]
    )
    outcome, journal, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafec0")
    assert "provisioning livespec core" in outcome.detail
    assert "core clone failed" in outcome.detail
    # NOT a step of the closed vocabulary: a host-environment failure with no
    # integration point for an adopter to provide carries no structured id, so
    # it cannot persist into a refusal the adopter has no way to clear.
    assert (outcome.step, outcome.missing_integration_point, outcome.remedy) == (None, None, None)
    assert len(runner.calls) == 12
    assert [record["stage"] for record in journal.records][-1] == "janitor-core-provision"


def test_engine_janitor_checkout_uses_the_resolved_tip_without_a_merge_sha(
    tmp_path: Path,
) -> None:
    """No merge sha is nothing to confirm, so the venue is the tip unprobed."""
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha=None)),
            _ok(),  # pull-primary
            _ok(stdout="origin/master"),  # the resolved default branch
            _ok(),  # janitor-checkout-preclean
            _ok(),  # janitor-checkout-add
            _ok(),  # janitor-checkout-trust
            _ok(),  # janitor-checkout-bootstrap
            _ok(),  # janitor-checkout-bootstrap-in-checkout
            _ok(),  # janitor-core-provision
            _ok(),  # janitor-post-merge
            _ok(),  # janitor-checkout-remove
        ]
    )
    outcome, _, _ = _dispatch(runner=runner, repo=tmp_path)
    assert (outcome.status, outcome.stage) == ("green", "done")
    add_calls = [argv for argv, _ in runner.calls if "worktree" in argv and "add" in argv]
    assert len(add_calls) == 1
    assert add_calls[0][-1] == "origin/master"
    assert not [argv for argv, _ in runner.calls if "merge-base" in argv]


def test_engine_runs_configured_janitor_in_fresh_checkout(tmp_path: Path) -> None:
    runner = _FakeRunner(
        queue=[
            _ok(),
            _ok(stdout=_pr_json(armed=True)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe06")),
            _pr_association(),
            _ok(),  # pull-primary
            *_venue_resolution(),
            _ok(),  # janitor-checkout-preclean
            _ok(),  # janitor-checkout-add
            _ok(),  # janitor-checkout-trust
            _ok(),  # janitor-checkout-bootstrap
            _ok(),  # janitor-checkout-bootstrap-in-checkout
            _ok(),  # janitor-core-provision
            _ok(),  # janitor-post-merge
            _ok(),  # janitor-checkout-remove
        ]
    )
    _, _, _ = _dispatch(runner=runner, repo=tmp_path)
    janitor_calls = [
        (argv, cwd)
        for argv, cwd in runner.calls
        if argv
        == [
            "mise",
            "exec",
            "--",
            "just",
            "check-no-workflow-edits",
            "install-worktree-pack",
            "check",
        ]
    ]
    assert len(janitor_calls) == 1
    assert janitor_calls[0][1] == tmp_path / "janitor-co"


# ---------------------------------------------------------------------------
# IO seams
# ---------------------------------------------------------------------------


def test_shell_runner_captures_exit_and_streams(tmp_path: Path) -> None:
    runner = ShellCommandRunner()
    code = "import sys; sys.stdout.write('out'); sys.stderr.write('err'); sys.exit(3)"
    result = runner.run(argv=[sys.executable, "-c", code], cwd=tmp_path, timeout_seconds=30.0)
    assert (result.exit_code, result.stdout, result.stderr) == (3, "out", "err")


def test_shell_runner_converts_timeouts(tmp_path: Path) -> None:
    runner = ShellCommandRunner()
    result = runner.run(
        argv=[sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        timeout_seconds=0.2,
    )
    assert result.exit_code == 124
    assert "timeout after" in result.stderr


def test_shell_runner_converts_a_missing_executable_into_127(tmp_path: Path) -> None:
    """An ABSENT executable degrades like any other failing command.

    A `FileNotFoundError` escaping the runner CRASHES the dispatch on any
    host whose PATH lacks an optional helper. 127 is the POSIX
    command-not-found convention, and callers already read any non-zero exit
    as a failure.
    """
    runner = ShellCommandRunner()
    result = runner.run(
        argv=["livespec-no-such-binary-xyz"],
        cwd=tmp_path,
        timeout_seconds=5.0,
    )
    assert result.exit_code == 127
    assert result.stdout == ""
    assert "executable not found: livespec-no-such-binary-xyz" in result.stderr


def test_decode_handles_bytes_str_and_none() -> None:
    assert _decode(raw=b"x") == "x"
    assert _decode(raw="y") == "y"
    assert _decode(raw=None) == ""


def test_github_token_env_runner_refreshes_gh_token_before_each_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pillar 1 (first-class remint): EVERY delegated command sees the
    supplier's CURRENT token in GH_TOKEN — a fresh value per call, never a
    once-at-start export that could expire mid-merge-poll."""
    monkeypatch.setenv("GH_TOKEN", "seed-to-restore")
    seen_tokens: list[str | None] = []

    @dataclass
    class _RecordingRunner:
        def run(
            self,
            *,
            argv: list[str],
            cwd: Path,
            timeout_seconds: float,
            env: dict[str, str] | None = None,
        ) -> CommandResult:
            _ = (argv, cwd, timeout_seconds, env)
            seen_tokens.append(os.environ.get("GH_TOKEN"))
            return CommandResult(exit_code=0, stdout="ok", stderr="")

    minted = iter(["ghs_tok-1", "ghs_tok-2"])
    runner = GithubTokenEnvRunner(inner=_RecordingRunner(), token=lambda: next(minted))
    first = runner.run(argv=["gh", "pr", "view"], cwd=tmp_path, timeout_seconds=1.0)
    second = runner.run(argv=["gh", "pr", "view"], cwd=tmp_path, timeout_seconds=1.0)
    assert (first.exit_code, second.exit_code) == (0, 0)
    assert first.stdout == "ok"
    assert seen_tokens == ["ghs_tok-1", "ghs_tok-2"]


def test_github_token_env_runner_forwards_explicit_stdin(tmp_path: Path) -> None:
    seen_stdin: list[int | None] = []

    @dataclass
    class _RecordingRunner:
        def run(
            self,
            *,
            argv: list[str],
            cwd: Path,
            timeout_seconds: float,
            env: dict[str, str] | None = None,
            stdin: int | None = None,
        ) -> CommandResult:
            _ = (argv, cwd, timeout_seconds, env)
            seen_stdin.append(stdin)
            return CommandResult(exit_code=0, stdout="ok", stderr="")

    runner = GithubTokenEnvRunner(inner=_RecordingRunner(), token=lambda: "ghs_tok")

    result = runner.run(
        argv=["codex", "exec", "reply OK"],
        cwd=tmp_path,
        timeout_seconds=1.0,
        stdin=subprocess.DEVNULL,
    )

    assert result.exit_code == 0
    assert seen_stdin == [subprocess.DEVNULL]


def test_github_token_env_runner_fails_closed_on_refresh_error(tmp_path: Path) -> None:
    """A mint failure never runs the command and never falls back — it is
    routed as a non-zero CommandResult carrying the actionable detail."""

    @dataclass
    class _MustNotRun:
        def run(  # pragma: no cover - reaching this body is the failure being tested
            self,
            *,
            argv: list[str],
            cwd: Path,
            timeout_seconds: float,
            env: dict[str, str] | None = None,
        ) -> CommandResult:
            _ = (argv, cwd, timeout_seconds, env)
            raise AssertionError("inner runner must not run on a refresh failure")

    def _raising_token() -> str:
        raise GithubAppAuthError(detail="mint exploded")

    runner = GithubTokenEnvRunner(inner=_MustNotRun(), token=_raising_token)
    result = runner.run(argv=["gh", "pr", "view"], cwd=tmp_path, timeout_seconds=1.0)
    assert result.exit_code == 1
    assert "fail-closed" in result.stderr
    assert "mint exploded" in result.stderr


def test_post_verdict_runner_routes_supplier_resolution_error_through_token_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_dispatcher_self_update, "github_token_supplier", lambda: "missing app env")
    runner = post_verdict_runner(runner=None)

    result = runner.run(argv=["gh", "pr", "view"], cwd=tmp_path, timeout_seconds=1.0)

    assert result.exit_code == 1
    assert "fail-closed" in result.stderr
    assert "missing app env" in result.stderr


def test_post_verdict_runner_returns_injected_runner_without_token_wrapper() -> None:
    runner = ShellCommandRunner()

    assert post_verdict_runner(runner=runner) is runner


def test_github_token_supplier_returns_a_provider_accessor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the App env present the REAL supplier resolves the config and
    hands back the caching provider's `token` accessor (no mint yet)."""
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    supplier = _real_github_token_supplier()
    assert callable(supplier)


def test_journal_file_appends_jsonl_with_timestamps(tmp_path: Path) -> None:
    journal = JournalFile(path=tmp_path / "nested" / "journal.jsonl")
    journal.append(record={"stage": "one"})
    journal.append(record={"stage": "two"})
    lines = (tmp_path / "nested" / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    assert [record["stage"] for record in parsed] == ["one", "two"]
    assert all(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", record["at"]) for record in parsed
    )


def test_utc_now_iso_shape() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", utc_now_iso())


# ---------------------------------------------------------------------------
# CLI surface — ledger-check
# ---------------------------------------------------------------------------


def test_ledger_check_clean_human_and_json(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(argv=["ledger-check"]) == 0
    assert "(no ledger findings)" in capsys.readouterr().out
    assert main(argv=["ledger-check", "--project-root", str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_ledger_check_reports_findings(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    append_work_item(path=_config(), item=_item(depends_on=("ghost-1",)))
    assert main(argv=["ledger-check", "--project-root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "no-orphan-dependency" in out
    assert main(argv=["ledger-check", "--project-root", str(tmp_path), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["check"] == "no-orphan-dependency"
    assert payload[0]["severity"] == "fail"


# ---------------------------------------------------------------------------
# CLI surface — spec-check
# ---------------------------------------------------------------------------


def test_spec_check_cli_skips_without_spec_tree(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(argv=["spec-check"]) == 0
    out = capsys.readouterr().out
    assert "SKIPPED" in out
    assert "no-stale-gap-tied" in out
    assert main(argv=["spec-check", "--project-root", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {entry["severity"] for entry in payload} == {"skipped"}


def test_spec_check_cli_reports_findings(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    spec = _spec_tree(tmp_path=tmp_path)
    append_work_item(
        path=_config(),
        item=_item(id="g-stale", origin="gap-tied", gap_id="gap-gone1234"),
    )
    assert main(argv=["spec-check", "--project-root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "WARN  no-stale-gap-tied  g-stale" in out
    assert "FAIL  unresolved-spec-commitment  hint-filed" in out
    exit_code = main(
        argv=["spec-check", "--project-root", str(tmp_path), "--spec-root", str(spec), "--json"]
    )
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    checks = {entry["check"] for entry in payload}
    assert checks == {"no-stale-gap-tied", "unresolved-spec-commitment"}


# ---------------------------------------------------------------------------
# CLI surface — janitor-check
# ---------------------------------------------------------------------------


def test_janitor_check_cli_skips_outside_git_repo(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(argv=["janitor-check"]) == 0
    out = capsys.readouterr().out
    assert "SKIPPED" in out
    assert "no-stale-worktree" in out
    assert main(argv=["janitor-check", "--repo", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {entry["severity"] for entry in payload} == {"skipped"}


# ---------------------------------------------------------------------------
# CLI surface — dispatch and loop
# ---------------------------------------------------------------------------


def _repo_with_workflow(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    # The dispatcher resolves the tenant connection via
    # resolve_store_config(cwd=repo), which REQUIRES an explicit
    # connection.prefix (decoupled from the tenant DB name); a real governed
    # repo always carries one, so the hermetic repo mirrors that.
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return repo, workflow


def _green_outcome(*, item_id: str, sha: str | None = "feed01") -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=item_id,
        status="green",
        stage="done",
        pr_number=11,
        merge_sha=sha,
        detail="merged",
    )


@dataclass(frozen=True, kw_only=True)
class _FakeAcceptancePass:
    verdict: str
    absent_evidence: tuple[str, ...] = ()

    def journal_record(self, *, work_item_id: str, policy: str) -> dict[str, object]:
        return {
            "stage": "acceptance-ai-pass",
            "work_item_id": work_item_id,
            "verdict": self.verdict,
            "acceptance_policy": policy,
            "diff": {"observed": True},
            "criteria": {"observed": True},
            "telemetry": {"observed": True},
        }


@dataclass(kw_only=True)
class _FakeRunDispatch:
    """Stand-in for run_dispatch: records kwargs plus the materialized
    overlay (content + mode) as observed AT CALL TIME, since the real
    dispatcher deletes the overlay after the run returns."""

    outcomes: dict[str, DispatchOutcome]
    seen: list[dict[str, object]] = field(default_factory=list)
    overlay_texts: list[str] = field(default_factory=list)
    overlay_modes: list[int] = field(default_factory=list)

    def __call__(self, **kwargs: object) -> DispatchOutcome:
        self.seen.append(kwargs)
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        # The dispatcher materializes the overlay before every run it
        # launches, so the file always exists here (and is gone again
        # once the dispatch returns).
        self.overlay_texts.append(plan.workflow_toml.read_text(encoding="utf-8"))
        self.overlay_modes.append(stat.S_IMODE(plan.workflow_toml.stat().st_mode))
        return self.outcomes[plan.work_item_id]


@dataclass(kw_only=True)
class _CostGateCall:
    args: argparse.Namespace
    repo: Path
    outcomes: list[DispatchOutcome]
    journal: object
    runner: object


@dataclass(kw_only=True)
class _RecordingCostGate:
    calls: list[_CostGateCall] = field(default_factory=list)

    def __call__(self, **kwargs: object) -> None:
        args = kwargs["args"]
        repo = kwargs["repo"]
        outcomes = kwargs["outcomes"]
        assert isinstance(args, argparse.Namespace)
        assert isinstance(repo, Path)
        assert isinstance(outcomes, list)
        assert all(isinstance(outcome, DispatchOutcome) for outcome in outcomes)
        self.calls.append(
            _CostGateCall(
                args=args,
                repo=repo,
                outcomes=outcomes,
                journal=kwargs["journal"],
                runner=kwargs["runner"],
            )
        )


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def test_admission_reclaims_dead_active_claim_and_journals_abandonment(
    tmp_path: Path,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    active = _item(id="bd-dead-claim", status="active")
    ready = _item(id="bd-ready-claim", status="ready", rank="a1")
    append_work_item(path=_config(), item=active)
    append_work_item(path=_config(), item=ready)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 1}}}',
        encoding="utf-8",
    )
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": active.id, "assignee": "ai"})

    admission = _dispatcher_admission.admit_and_select(
        repo=repo,
        items=[active, ready],
        candidates=[ready],
        journal=journal,
        enforce_cap=True,
    )

    assert [item.id for item in admission.admitted] == [ready.id]
    assert _stored()[active.id].status == "active"
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    abandoned = [
        record
        for record in records
        if record["stage"] == "dispatch-claim-abandoned" and record["work_item_id"] == active.id
    ]
    assert len(abandoned) == 1


def test_admission_reclaims_green_terminal_claim_before_capacity_deferral(
    tmp_path: Path,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    active = _item(id="bd-green-park", status="active")
    ready = _item(id="bd-ready-admitted", status="ready", rank="a1")
    append_work_item(path=_config(), item=active)
    append_work_item(path=_config(), item=ready)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 1}}}',
        encoding="utf-8",
    )
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": active.id, "assignee": "ai"})
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {
                "work_item_id": active.id,
                "status": "green",
                "stage": "done",
            },
        }
    )
    journal.append(record={"stage": "acceptance-auto-rework", "work_item_id": active.id})

    admission = _dispatcher_admission.admit_and_select(
        repo=repo,
        items=[active, ready],
        candidates=[ready],
        journal=journal,
        enforce_cap=True,
    )

    assert [item.id for item in admission.admitted] == [ready.id]
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    abandoned = [
        record
        for record in records
        if record["stage"] == "dispatch-claim-abandoned" and record["work_item_id"] == active.id
    ]
    assert [record["reason"] for record in abandoned] == ["green-terminal-active-reclaimed"]


def test_admission_counts_live_dispatch_lock_against_cap(tmp_path: Path) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    active = _item(id="bd-live-claim", status="active")
    ready = _item(id="bd-ready-blocked", status="ready", rank="a1")
    append_work_item(path=_config(), item=active)
    append_work_item(path=_config(), item=ready)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 1}}}',
        encoding="utf-8",
    )
    _ = _dispatcher_dispatch_lock.write_dispatch_lock(
        repo=repo,
        work_item_id=active.id,
        dispatch_id="live-dispatch",
    )
    journal = JournalFile(path=repo / "journal.jsonl")

    admission = _dispatcher_admission.admit_and_select(
        repo=repo,
        items=[active, ready],
        candidates=[ready],
        journal=journal,
        enforce_cap=True,
    )

    assert admission.admitted == []
    records = (
        []
        if not journal.path.exists()
        else [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    )
    assert "dispatch-claim-abandoned" not in {record["stage"] for record in records}


def test_capacity_deferral_detail_names_live_slots_after_green_reclamation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    live = _item(id="bd-live-claim", status="active")
    green = _item(id="bd-green-park", status="active")
    unreadable = _item(id="bd-unreadable-claim", status="active")
    ready = _item(id="bd-ready-blocked", status="ready", rank="a1")
    append_work_item(path=_config(), item=live)
    append_work_item(path=_config(), item=green)
    append_work_item(path=_config(), item=unreadable)
    append_work_item(path=_config(), item=ready)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 2}}}',
        encoding="utf-8",
    )
    _ = _dispatcher_dispatch_lock.write_dispatch_lock(
        repo=repo,
        work_item_id=live.id,
        dispatch_id="live-dispatch",
    )
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": green.id, "assignee": "ai"})
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {
                "work_item_id": green.id,
                "status": "green",
                "stage": "done",
            },
        }
    )
    monkeypatch.setattr(
        _dispatcher_admission,
        "claimed_active_accounting",
        lambda **_kwargs: ActiveClaimAccounting(
            active_count=2,
            live_lock_active_ids=(live.id,),
            journal_unreadable_active_ids=(unreadable.id,),
            green_terminal_active_ids=(green.id,),
        ),
    )

    admission = _dispatcher_admission.admit_and_select(
        repo=repo,
        items=[live, green, unreadable, ready],
        candidates=[ready],
        journal=journal,
        enforce_cap=True,
    )

    assert admission.admitted == []
    assert [outcome.detail for outcome in admission.deferred] == [
        "capacity deferred: active_count=2 wip_cap=2 free_slots=0 "
        "live_lock_active_ids=bd-live-claim "
        "journal_unreadable_active_ids=bd-unreadable-claim "
        "operator_response=wait_for_live_locks,inspect_unreadable_journals "
        "green_terminal_active_ids=bd-green-park "
        "green_terminal_active_status=already_reclaimed_no_slot "
        "single_item_override=dispatcher.py dispatch --item bd-ready-blocked "
        "single_item_override_enforces_cap=false "
        "single_item_override_cost=deliberately_exceeds_wip_cap_bound_for_same_repo_"
        "merge_rebase_contention_during_unattended_draining"
    ]


def test_admission_docstring_names_cap_override_surfaces() -> None:
    doc = inspect.getdoc(_dispatcher_admission.admit_and_select)

    assert doc is not None
    assert "targeted `dispatch --item` is an operator override" in doc
    assert "`dispatcher.py dispatch --item` reaches that override" in doc
    assert "`drive --action impl:` does not" in doc
    assert "cap-enforcing `loop` path" in doc


def test_capacity_recovers_when_green_terminal_row_is_only_active_slot(
    tmp_path: Path,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    green = _item(id="bd-green-only", status="active")
    ready = _item(id="bd-ready-admitted", status="ready", rank="a1")
    append_work_item(path=_config(), item=green)
    append_work_item(path=_config(), item=ready)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 1}}}',
        encoding="utf-8",
    )
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": green.id, "assignee": "ai"})
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {
                "work_item_id": green.id,
                "status": "green",
                "stage": "done",
            },
        }
    )

    admission = _dispatcher_admission.admit_and_select(
        repo=repo,
        items=[green, ready],
        candidates=[ready],
        journal=journal,
        enforce_cap=True,
    )

    assert [item.id for item in admission.admitted] == [ready.id]
    assert admission.deferred == []
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    abandoned = [
        record
        for record in records
        if record["stage"] == "dispatch-claim-abandoned" and record["work_item_id"] == green.id
    ]
    assert [record["reason"] for record in abandoned] == ["green-terminal-active-reclaimed"]


def test_capacity_deferral_detail_omits_absent_green_terminal_branch(
    tmp_path: Path,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    live = _item(id="bd-live-only", status="active")
    ready = _item(id="bd-ready-blocked", status="ready", rank="a1")
    append_work_item(path=_config(), item=live)
    append_work_item(path=_config(), item=ready)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 1}}}',
        encoding="utf-8",
    )
    _ = _dispatcher_dispatch_lock.write_dispatch_lock(
        repo=repo,
        work_item_id=live.id,
        dispatch_id="live-dispatch",
    )
    journal = JournalFile(path=repo / "journal.jsonl")

    admission = _dispatcher_admission.admit_and_select(
        repo=repo,
        items=[live, ready],
        candidates=[ready],
        journal=journal,
        enforce_cap=True,
    )

    detail = admission.deferred[0].detail
    assert "live_lock_active_ids=bd-live-only" in detail
    assert "green_terminal_active_ids=" not in detail
    assert "advance_rows=" not in detail


def test_admission_time_lock_protects_queued_batch_items(tmp_path: Path) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    first = _item(id="bd-ready-first", status="ready", rank="a1")
    second = _item(id="bd-ready-second", status="ready", rank="a2")
    append_work_item(path=_config(), item=first)
    append_work_item(path=_config(), item=second)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 2}}}',
        encoding="utf-8",
    )
    journal = JournalFile(path=repo / "journal.jsonl")

    admission = _dispatcher_admission.admit_and_select(
        repo=repo,
        items=[first, second],
        candidates=[first, second],
        journal=journal,
        enforce_cap=True,
    )

    assert [item.id for item in admission.admitted] == [first.id, second.id]
    assert _dispatcher_dispatch_lock.live_dispatch_lock(repo=repo, work_item_id=first.id)
    assert _dispatcher_dispatch_lock.live_dispatch_lock(repo=repo, work_item_id=second.id)
    second_pass = _dispatcher_admission.admit_and_select(
        repo=repo,
        items=admission.admitted,
        candidates=[],
        journal=journal,
        enforce_cap=False,
    )
    assert second_pass.admitted == []
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    assert "dispatch-claim-abandoned" not in {record["stage"] for record in records}


# The two vendors' ceilings verbatim, from real `fabro inspect --json` payloads
# measured on the hp factory (2026-08-22). These are the INPUT the production
# classifier is fed; no test below writes a provider NAME into an outcome.
_ACP_WRAPPER = "ACP protocol error"
_CODEX_CEILING = (
    "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
    "to purchase more credits or try again at Aug 27th, 2026 1:20 AM."
)
_ANTHROPIC_CEILING = (
    "Internal error: You've hit your org's monthly spend limit "
    "· ask your admin to raise it at claude.ai/settings/usage"
)


def _ceiling_outcome(*, work_item_id: str, cause: str) -> DispatchOutcome:
    """A terminal outcome for an observed ceiling, built by PRODUCTION code.

    The vendor is classified from the payload by
    `fabro_run_terminal_outcome`, exactly as it is for a live run, so the
    exhaustion record this drives is written from an input the system genuinely
    produces rather than from a provider value hand-written here.
    """
    payload: list[object] = [
        {
            "status": {"kind": "failed"},
            "failure": {"causes": [_ACP_WRAPPER, cause], "category": "transient_infra"},
        }
    ]
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=build_plan(
            repo=Path("/nonexistent"),
            work_item_id=work_item_id,
            workflow_toml=Path("/nonexistent/wf.toml"),
            goal_file=Path("/nonexistent/goal.md"),
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=Path("/nonexistent/janitor-co"),
        ),
        run_id="01LIMIT",
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=payload,
            status_kind=fabro_status_kind_from_payload(payload=payload),
            failure=fabro_failure_detail_from_payload(payload=payload),
        ),
        exit_code=1,
        stderr="",
    )
    assert outcome is not None
    return outcome


def test_provider_usage_limit_refuses_matching_provider_before_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    blocked = _item(id="bd-ready-codex", status="ready", rank="a1")
    append_work_item(path=_config(), item=blocked)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 1}}}',
        encoding="utf-8",
    )
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(
        record={
            "stage": "provider-exhaustion-observed",
            "provider": "codex",
            "governing_condition": "provider_usage_limit",
            "record_expires_at": "2026-08-23T10:15:00Z",
            "work_item_id": "bd-earlier",
        }
    )
    monkeypatch.setattr(
        _dispatcher_admission_eligibility,
        "utc_now_iso",
        lambda: "2026-08-23T10:10:00Z",
        raising=False,
    )

    admission = _dispatcher_admission.admit_and_select(
        repo=repo,
        items=[blocked],
        candidates=[blocked],
        journal=journal,
        enforce_cap=True,
    )

    assert admission.admitted == []
    assert admission.deferred == []
    assert [outcome.stage for outcome in admission.refused] == ["provider-exhaustion"]
    assert _stored()[blocked.id].status == "ready"
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    refusal = records[-1]
    assert (
        refusal.items()
        >= {
            "stage": "provider-exhaustion-refusal",
            "work_item_id": blocked.id,
            "provider": "codex",
            "governing_condition": "provider_usage_limit",
            "record_expires_at": "2026-08-23T10:15:00Z",
        }.items()
    )
    assert "ledger-admit" not in {record["stage"] for record in records}


def test_provider_usage_limit_gate_recovers_after_derived_expiry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    ready = _item(id="bd-ready-after-expiry", status="ready", rank="a1")
    append_work_item(path=_config(), item=ready)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 1}}}',
        encoding="utf-8",
    )
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(
        record={
            "stage": "provider-exhaustion-observed",
            "provider": "codex",
            "governing_condition": "provider_usage_limit",
            "record_expires_at": "2026-08-23T10:15:00Z",
            "work_item_id": "bd-earlier",
        }
    )
    monkeypatch.setattr(
        _dispatcher_admission_eligibility,
        "utc_now_iso",
        lambda: "2026-08-23T10:16:00Z",
        raising=False,
    )

    admission = _dispatcher_admission.admit_and_select(
        repo=repo,
        items=[ready],
        candidates=[ready],
        journal=journal,
        enforce_cap=True,
    )

    assert [item.id for item in admission.admitted] == [ready.id]
    assert admission.refused == []
    assert _stored()[ready.id].status == "active"


def test_provider_usage_limit_gate_is_provider_selective(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A record covers the vendor that refused and no other.

    The record is WRITTEN by the production path from the measured Anthropic
    ceiling, so the provider under test is one the system genuinely produces.
    Hand-writing it proved selectivity against a value nothing could emit.
    """
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    ready = _item(id="bd-ready-uncovered-provider", status="ready", rank="a1")
    append_work_item(path=_config(), item=ready)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 1}}}',
        encoding="utf-8",
    )
    journal = JournalFile(path=repo / "journal.jsonl")
    monkeypatch.setattr(
        _dispatcher_loop_selection,
        "utc_now_iso",
        lambda: "2026-08-23T10:00:00Z",
        raising=False,
    )
    _dispatcher_loop_selection.post_run_dispositions(
        args=argparse.Namespace(close_on_merge=False),
        repo=repo,
        item=_item(id="bd-observed-anthropic", status="active", assignee="fabro"),
        outcome=_ceiling_outcome(work_item_id="bd-observed-anthropic", cause=_ANTHROPIC_CEILING),
        journal=journal,
        wall_clock_seconds=42.0,
        dispatch_context_size=100,
        token_supplier=lambda: "token",
    )

    covered = _dispatcher_provider_exhaustion.active_provider_exhaustion(
        provider="anthropic",
        journal_path=journal.path,
        now_iso="2026-08-23T10:10:00Z",
    )
    uncovered = _dispatcher_provider_exhaustion.active_provider_exhaustion(
        provider="codex",
        journal_path=journal.path,
        now_iso="2026-08-23T10:10:00Z",
    )

    # The vendor that refused is covered; the vendor that did not holds nothing.
    assert covered is not None
    assert covered.provider == "anthropic"
    assert uncovered is None
    monkeypatch.setattr(
        _dispatcher_admission_eligibility,
        "utc_now_iso",
        lambda: "2026-08-23T10:10:00Z",
        raising=False,
    )

    admission = _dispatcher_admission.admit_and_select(
        repo=repo,
        items=[ready],
        candidates=[ready],
        journal=journal,
        enforce_cap=True,
    )

    # And the dispatch is refused against THAT vendor, not a fixed one.
    assert admission.admitted == []
    assert [outcome.stage for outcome in admission.refused] == ["provider-exhaustion"]
    assert "provider=anthropic" in admission.refused[0].detail


def test_provider_usage_limit_outcome_records_dispatcher_owned_expiry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(id="bd-observed-limit", status="active", assignee="fabro")
    journal = JournalFile(path=repo / "journal.jsonl")
    monkeypatch.setattr(
        _dispatcher_loop_selection,
        "utc_now_iso",
        lambda: "2026-08-23T10:00:00Z",
        raising=False,
    )
    outcome = _ceiling_outcome(work_item_id=item.id, cause=_CODEX_CEILING)

    _dispatcher_loop_selection.post_run_dispositions(
        args=argparse.Namespace(close_on_merge=False),
        repo=repo,
        item=item,
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=42.0,
        dispatch_context_size=100,
        token_supplier=lambda: "token",
    )

    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    observed = [record for record in records if record["stage"] == "provider-exhaustion-observed"]
    assert [record["at"] for record in observed] == ["2026-08-23T10:00:00Z"]
    assert [_journal_payload(record=record) for record in observed] == [
        {
            "stage": "provider-exhaustion-observed",
            "work_item_id": item.id,
            "provider": "codex",
            "governing_condition": "provider_usage_limit",
            "record_expires_at": "2026-08-23T10:15:00Z",
        }
    ]


def test_admission_reclaims_dead_active_claim_when_cap_not_enforced(
    tmp_path: Path,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    active = _item(id="bd-dead-claim", status="active")
    ready = _item(id="bd-targeted-ready", status="ready", rank="a1")
    append_work_item(path=_config(), item=active)
    append_work_item(path=_config(), item=ready)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"wip_cap": 0}}}',
        encoding="utf-8",
    )
    journal = JournalFile(path=repo / "journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": active.id, "assignee": "ai"})

    admission = _dispatcher_admission.admit_and_select(
        repo=repo,
        items=[active, ready],
        candidates=[ready],
        journal=journal,
        enforce_cap=False,
    )

    assert [item.id for item in admission.admitted] == [ready.id]
    assert _stored()[active.id].status == "active"
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    abandoned = [
        record
        for record in records
        if record["stage"] == "dispatch-claim-abandoned" and record["work_item_id"] == active.id
    ]
    assert len(abandoned) == 1


def test_dispatch_green_closes_item_and_journals(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _FakeAcceptancePass(verdict="PASS"),
        raising=False,
    )
    monkeypatch.setattr(_dispatcher_run_commands, "cost_gate_after_verdict", lambda **_: None)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop_plan.tempfile.gettempdir",
        lambda: str(tmp_path),
    )
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["status"] == "green"
    stored = _stored()[item.id]
    assert (stored.status, stored.resolution) == ("done", "completed")
    assert stored.audit is not None
    assert (stored.audit.merge_sha, stored.audit.pr_number) == ("feed01", 11)
    goal_text = (tmp_path / f"fabro-goal-{item.id}.md").read_text(encoding="utf-8")
    assert "A ready task" in goal_text
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    stages = [json.loads(line)["stage"] for line in journal_text.splitlines()]
    # The master-CI preflight records its PASS first, before anything is admitted:
    # a pre-dispatch step has exactly three sanctioned outcomes and a pass is a
    # journaled one, so the evidence the step ran precedes the first state write.
    # Then the admission valve fires (`ledger-admit`: ready -> active +
    # assignee), then the per-dispatch workflow payload is materialized and
    # its resolved node timeouts journaled (`node-timeouts`, naming the layer
    # that supplied each one) and every ACP node's resolved adapter journaled
    # (`acp-nodes`, naming the layer behind each field), then the dispatch
    # journals the correlation id
    # (29f.3 — projected into the sandbox's CC OTel OTEL_RESOURCE_ATTRIBUTES
    # so telemetry joins to this dispatch). This hermetic fake outcome has no
    # Fabro run id, but review-gate telemetry is ordered after dispositions so
    # telemetry cannot skip the critical state writes. On a green run the
    # post-merge acceptance valve runs: `ledger-complete` (active -> acceptance) then the
    # `acceptance-ai-pass` confirm then `ledger-accept` (ai-only -> done; the
    # default factory item is ai-only). After `outcome` come the post-verdict
    # fail-open stages. First comes yfsv4j's `calibration` record (the
    # per-dispatch outcome signal + mechanical size proxies on the existing
    # journal — here the merged-PR diff-size probe returns None because `gh pr
    # view` fails on the hermetic non-repo, but the record is still
    # journaled). The cost-gate stage is stubbed in this dispatcher-level
    # test; its fail-open behavior is covered in the mirrored cost-gate tests.
    # Then ddu's staged-self-update gate runs (here `self-update-skipped`
    # because the running release already matches the provisioned payload),
    # then the run_turn telemetry assertion journals the absence/presence
    # signal for reflection to scan, then the mechanical reflection stage at
    # the default `observe` lever (work-item 29f.2).
    # `reconcile-runs-pass` closes the preamble: reconciliation runs after both
    # step-gate preflights and before admission, and it records its pass even
    # when there is no declared factory to survey.
    # `conformance-premise-undeclared` sits between the plan build and the
    # correlation id: this fixture's `.livespec.jsonc` declares none of the three
    # `dispatcher.conformance.*` premises, so each resolves to the fleet-default
    # no-op and the Dispatcher says so once. It is informational — the dispatch
    # runs to `green` with the record present.
    assert stages == [
        "source-checkout-origin-reachability",
        "master-ci-preflight",
        "reconcile-runs-pass",
        "ledger-admit",
        "node-timeouts",
        "acp-nodes",
        "conformance-premise-undeclared",
        "dispatch-id",
        "ledger-complete",
        "acceptance-ai-pass",
        "ledger-accept",
        "auto-disposition",
        "outcome",
        "calibration",
        "review-gate-telemetry-skipped",
        "self-update-skipped",
        "run-turn-telemetry-check",
        "reflection",
    ]
    poll = fake.seen[0]["poll"]
    assert isinstance(poll, PollPolicy)
    assert (poll.attempts, poll.interval_seconds) == (80, 30.0)


def test_dispatch_id_journal_records_resolved_factory_without_rewriting_existing_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")
    existing = {
        "stage": "dispatch-id",
        "work_item_id": "older",
        "dispatch_id": "older-dispatch",
    }
    journal.append(record=existing)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    monkeypatch.setattr(_dispatcher_loop, "post_run_dispositions", lambda **_: None)
    review_gate_emissions: list[ReviewGateEmission] = []
    monkeypatch.setattr(
        _dispatcher_loop,
        "emit_review_gate_from_fabro_events",
        lambda *, emission: review_gate_emissions.append(emission),
    )

    outcome = _dispatcher_loop.dispatch_one(
        args=argparse.Namespace(
            fabro_bin="fabro",
            workflow=workflow,
            repo=repo,
            journal=None,
            poll_attempts=1,
            poll_interval_seconds=0.1,
            fabro_factory_target=FactoryTarget(
                name="resolved-hp",
                server="https://hp.example.test",
                dev_token=None,
            ),
        ),
        repo=repo,
        item=item,
        journal=journal,
        janitor=None,
    )

    assert outcome.status == "green"
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    assert records[0]["work_item_id"] == existing["work_item_id"]
    assert records[0]["dispatch_id"] == existing["dispatch_id"]
    assert "dispatch_factory" not in records[0]
    dispatch_records = [record for record in records if record["stage"] == "dispatch-id"]
    assert dispatch_records[1]["dispatch_factory"] == "resolved-hp"
    assert len(review_gate_emissions) == 1
    assert review_gate_emissions[0].dispatch_factory == "resolved-hp"


def test_dispatch_threads_its_dispatch_id_into_the_watchdog_launcher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The launcher's heartbeat probe gets THIS dispatch's id, not None.

    The heartbeat sink keys every beat by `livespec.dispatch.id` (the only
    specific id `cc_otel_overlay_env` projects into the sandbox), so a
    launcher constructed without the dispatch id can never match a beat —
    the probe silently reads "no signal" and the watchdog permanently
    degrades to its coarse wall-clock fallback. Asserting the id EQUALS
    the one the dispatch journaled is what makes this a real check: a
    launcher carrying None would look identical to every other test.
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    monkeypatch.setattr(_dispatcher_loop, "post_run_dispositions", lambda **_: None)
    monkeypatch.setattr(_dispatcher_loop, "emit_review_gate_from_fabro_events", lambda **_: None)

    outcome = _dispatcher_loop.dispatch_one(
        args=argparse.Namespace(
            fabro_bin="fabro",
            workflow=workflow,
            repo=repo,
            journal=None,
            poll_attempts=1,
            poll_interval_seconds=0.1,
        ),
        repo=repo,
        item=item,
        journal=journal,
        janitor=None,
    )

    assert outcome.status == "green"
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    journaled = next(record for record in records if record["stage"] == "dispatch-id")
    launcher = fake.seen[0]["fabro_launcher"]
    assert isinstance(launcher, WatchedFabroLauncher)
    assert launcher.dispatch_id == journaled["dispatch_id"]
    assert launcher.dispatch_id is not None


def test_dispatch_factory_telemetry_is_allowlisted_and_backfilled() -> None:
    assert "livespec.dispatch.factory" in ATTRIBUTE_ALLOWLIST
    assert is_allowed_attr(key="livespec.dispatch.factory") is True
    dispatcher_span = {
        "attributes": [
            {"key": "work.item.id", "value": {"stringValue": "bd-1"}},
            {"key": "livespec.dispatch.id", "value": {"stringValue": "dispatch-1"}},
            {"key": "fabro.run_id", "value": {"stringValue": "run-1"}},
            {"key": "livespec.dispatch.factory", "value": {"stringValue": "hp"}},
        ]
    }

    keys = correlation_keys_from_attrs(span=dispatcher_span)
    join = CorrelationJoin()
    join.observe(keys=keys)

    assert keys == {
        "work.item.id": "bd-1",
        "livespec.dispatch.id": "dispatch-1",
        "fabro.run_id": "run-1",
        "livespec.dispatch.factory": "hp",
    }
    assert join.backfill(keys={"fabro.run_id": "run-1"}) == {
        "work.item.id": "bd-1",
        "livespec.dispatch.id": "dispatch-1",
        "fabro.run_id": "run-1",
        "livespec.dispatch.factory": "hp",
    }


def test_review_gate_span_emits_resolved_dispatch_factory_and_omits_unknown() -> None:
    resolved_line = review_gate_request_line(
        telemetry=ReviewGateTelemetry(
            verdict="fix",
            fix_rounds=1,
            hit_cap=False,
            shipped_on_cap=False,
        ),
        work_item_id="bd-1",
        dispatch_id="dispatch-1",
        run_id="run-1",
        dispatch_factory="hp",
        now_ns=123,
    )
    unresolved_line = review_gate_request_line(
        telemetry=ReviewGateTelemetry(
            verdict="fix",
            fix_rounds=1,
            hit_cap=False,
            shipped_on_cap=False,
        ),
        work_item_id="bd-1",
        dispatch_id="dispatch-1",
        run_id="run-1",
        dispatch_factory=None,
        now_ns=123,
    )

    resolved_attrs = _span_attrs(line=resolved_line)
    unresolved_attrs = _span_attrs(line=unresolved_line)

    assert resolved_attrs["livespec.dispatch.factory"] == "hp"
    assert "livespec.dispatch.factory" not in unresolved_attrs


def test_dispatch_id_journal_omits_factory_when_target_was_not_resolved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    monkeypatch.setattr(_dispatcher_loop, "post_run_dispositions", lambda **_: None)
    review_gate_emissions: list[ReviewGateEmission] = []
    monkeypatch.setattr(
        _dispatcher_loop,
        "emit_review_gate_from_fabro_events",
        lambda *, emission: review_gate_emissions.append(emission),
    )

    outcome = _dispatcher_loop.dispatch_one(
        args=argparse.Namespace(
            fabro_bin="fabro",
            workflow=workflow,
            repo=repo,
            journal=None,
            poll_attempts=1,
            poll_interval_seconds=0.1,
        ),
        repo=repo,
        item=item,
        journal=journal,
        janitor=None,
    )

    assert outcome.status == "green"
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    dispatch_record = next(record for record in records if record["stage"] == "dispatch-id")
    assert "dispatch_factory" not in dispatch_record
    assert len(review_gate_emissions) == 1
    assert review_gate_emissions[0].dispatch_factory is None


def test_dispatch_pre_run_failure_releases_admitted_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(status="active", assignee="fabro")
    append_work_item(path=_config(), item=item)
    journal = JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": item.id, "assignee": "fabro"})
    monkeypatch.setattr(_dispatcher_loop, "read_dispatch_comments", lambda **_: "factory refused")

    outcome = _dispatcher_loop.dispatch_one(
        args=argparse.Namespace(
            fabro_bin="fabro",
            workflow=workflow,
            repo=repo,
            journal=None,
            poll_attempts=1,
            poll_interval_seconds=0.1,
        ),
        repo=repo,
        item=item,
        journal=journal,
        janitor=None,
    )

    assert (outcome.status, outcome.stage, outcome.fabro_run_id) == (
        "failed",
        "ledger-comments",
        None,
    )
    stored = _stored()[item.id]
    assert (stored.status, stored.assignee) == ("ready", None)
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    assert (
        records[-1].items()
        >= {
            "stage": "ledger-admit-release",
            "work_item_id": item.id,
            "status": "ready",
            "reason": "pre-run-failure-without-fabro-run-id",
            "outcome_stage": "ledger-comments",
        }.items()
    )


def test_dispatch_fabro_run_failure_without_run_id_releases_admitted_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(status="active", assignee="fabro")
    append_work_item(path=_config(), item=item)
    journal = JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": item.id, "assignee": "fabro"})
    journal.append(
        record={
            "stage": "fabro-run",
            "work_item_id": item.id,
            "exit_code": 1,
            "detail": "factory refused before run creation",
        }
    )
    fake = _FakeRunDispatch(
        outcomes={
            item.id: DispatchOutcome(
                work_item_id=item.id,
                status="failed",
                stage="fabro-run",
                pr_number=None,
                merge_sha=None,
                detail="factory refused before run creation",
                fabro_run_id=None,
            )
        }
    )
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    monkeypatch.setattr(_dispatcher_loop, "post_run_dispositions", lambda **_: None)
    monkeypatch.setattr(_dispatcher_loop, "emit_review_gate_from_fabro_events", lambda **_: None)

    outcome = _dispatcher_loop.dispatch_one(
        args=argparse.Namespace(
            fabro_bin="fabro",
            workflow=workflow,
            repo=repo,
            journal=None,
            poll_attempts=1,
            poll_interval_seconds=0.1,
        ),
        repo=repo,
        item=item,
        journal=journal,
        janitor=None,
    )

    assert (outcome.status, outcome.stage, outcome.fabro_run_id) == ("failed", "fabro-run", None)
    stored = _stored()[item.id]
    assert (stored.status, stored.assignee) == ("ready", None)
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    assert (
        records[-1].items()
        >= {
            "stage": "ledger-admit-release",
            "work_item_id": item.id,
            "status": "ready",
            "reason": "pre-run-failure-without-fabro-run-id",
            "outcome_stage": "fabro-run",
        }.items()
    )


def test_dispatch_fabro_run_claim_release_fails_closed_on_unreadable_journal(
    tmp_path: Path,
) -> None:
    item = _item(status="active", assignee="fabro")
    journal = JournalFile(path=tmp_path)
    outcome = DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="factory refused before run creation",
        fabro_run_id=None,
    )

    release_pre_run_claim_if_needed(repo=tmp_path, item=item, outcome=outcome, journal=journal)

    assert journal.path.is_dir()


def test_dispatch_fabro_run_claim_release_fails_closed_on_malformed_journal(
    tmp_path: Path,
) -> None:
    item = _item(status="active", assignee="fabro")
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    _ = journal.path.write_text("not-json\n", encoding="utf-8")
    outcome = DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="factory refused before run creation",
        fabro_run_id=None,
    )

    release_pre_run_claim_if_needed(repo=tmp_path, item=item, outcome=outcome, journal=journal)

    assert journal.path.read_text(encoding="utf-8") == "not-json\n"


def test_dispatch_fabro_run_claim_release_fails_closed_on_non_object_journal_record(
    tmp_path: Path,
) -> None:
    item = _item(status="active", assignee="fabro")
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    _ = journal.path.write_text("[]\n", encoding="utf-8")
    outcome = DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="factory refused before run creation",
        fabro_run_id=None,
    )

    release_pre_run_claim_if_needed(repo=tmp_path, item=item, outcome=outcome, journal=journal)

    assert journal.path.read_text(encoding="utf-8") == "[]\n"


def test_dispatch_does_not_release_claim_after_fabro_run_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(status="active", assignee="fabro")
    append_work_item(path=_config(), item=item)
    journal = JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")
    fake = _FakeRunDispatch(
        outcomes={
            item.id: DispatchOutcome(
                work_item_id=item.id,
                status="failed",
                stage="fabro-run",
                pr_number=None,
                merge_sha=None,
                detail="run failed after creation",
                fabro_run_id="01RUNEXISTS",
            )
        }
    )
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    monkeypatch.setattr(_dispatcher_loop, "post_run_dispositions", lambda **_: None)
    monkeypatch.setattr(_dispatcher_loop, "emit_review_gate_from_fabro_events", lambda **_: None)

    outcome = _dispatcher_loop.dispatch_one(
        args=argparse.Namespace(
            fabro_bin="fabro",
            workflow=workflow,
            repo=repo,
            journal=None,
            poll_attempts=1,
            poll_interval_seconds=0.1,
        ),
        repo=repo,
        item=item,
        journal=journal,
        janitor=None,
    )

    assert outcome.fabro_run_id == "01RUNEXISTS"
    stored = _stored()[item.id]
    assert (stored.status, stored.assignee) == ("active", "fabro")
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    assert "ledger-admit-release" not in {record["stage"] for record in records}


def test_complete_and_accept_hands_the_acceptance_pass_the_declared_markers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(acceptance_policy="ai-only")
    append_work_item(path=_config(), item=item)
    seen: dict[str, object] = {}

    def _pass(**kwargs: object) -> _FakeAcceptancePass:
        seen.update(kwargs)
        return _FakeAcceptancePass(verdict="PASS")

    monkeypatch.setattr(
        _dispatcher_completion,
        "read_dispatch_labels",
        lambda **_: ("change-optional:true",),
    )
    monkeypatch.setattr(_dispatcher_completion, "run_acceptance_pass", _pass, raising=False)
    journal = JournalFile(path=repo / "journal.jsonl")

    dispatcher.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=journal,
    )

    assert seen["raw_labels"] == ("change-optional:true",)


def test_complete_and_accept_fails_closed_when_the_declared_markers_are_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(acceptance_policy="ai-only")
    append_work_item(path=_config(), item=item)
    seen: dict[str, object] = {}

    def _pass(**kwargs: object) -> _FakeAcceptancePass:
        seen.update(kwargs)
        return _FakeAcceptancePass(verdict="PASS")

    monkeypatch.setattr(
        _dispatcher_completion,
        "read_dispatch_labels",
        lambda **_: "ledger label read failed for bd-ib-x (BeadsMappingError: gone)",
    )
    monkeypatch.setattr(_dispatcher_completion, "run_acceptance_pass", _pass, raising=False)
    journal = JournalFile(path=repo / "journal.jsonl")

    dispatcher.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=journal,
    )

    # A label set that could not be READ cannot DECLARE the change-optional
    # exemption, so the pass is handed no markers and classifies change-implying.
    assert seen["raw_labels"] == ()


def test_complete_and_accept_ai_only_pass_journals_verdict_and_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(acceptance_policy="ai-only")
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _FakeAcceptancePass(verdict="PASS"),
        raising=False,
    )
    journal = JournalFile(path=repo / "journal.jsonl")

    dispatcher.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=journal,
    )

    stored = _stored()[item.id]
    assert (stored.status, stored.resolution) == ("done", "completed")
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    acceptance = next(record for record in records if record["stage"] == "acceptance-ai-pass")
    assert acceptance["verdict"] == "PASS"
    assert acceptance["acceptance_policy"] == "ai-only"
    assert "confirmed" not in acceptance


def test_complete_and_accept_empty_diff_closes_no_change_needed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(acceptance_policy="ai-only")
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _FakeAcceptancePass(verdict="NO_CHANGE_NEEDED"),
        raising=False,
    )
    journal = JournalFile(path=repo / "journal.jsonl")

    dispatcher.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=journal,
    )

    stored = _stored()[item.id]
    assert (stored.status, stored.resolution) == ("done", "no-longer-applicable")
    assert stored.audit is None
    assert stored.reason == (
        "Fabro dispatch produced an empty merged diff for PR #11; "
        "closed as no-change-needed, not resolution:completed. "
        "Pre-dispatch staleness detection is deferred."
    )
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    stages = [record["stage"] for record in records]
    assert stages == [
        "ledger-complete",
        "acceptance-ai-pass",
        "ledger-accept-no-change-needed",
        "auto-disposition",
    ]
    disposition = records[-1]
    assert disposition["disposition"] == "ai-auto-no-change-needed"
    assert disposition["deferred"] == "pre-dispatch staleness detection"


@pytest.mark.parametrize("verdict", ["PASS", "FAIL"])
def test_complete_and_accept_human_only_pass_is_advisory_and_parks(
    verdict: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(acceptance_policy="human-only")
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _FakeAcceptancePass(verdict=verdict),
        raising=False,
    )
    journal = JournalFile(path=repo / "journal.jsonl")

    dispatcher.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=journal,
    )

    stored = _stored()[item.id]
    assert (stored.status, stored.resolution) == ("acceptance", None)
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    stages = [record["stage"] for record in records]
    assert "ledger-accept" not in stages
    acceptance = next(record for record in records if record["stage"] == "acceptance-ai-pass")
    assert acceptance["verdict"] == verdict
    assert acceptance["acceptance_policy"] == "human-only"
    assert (
        next(record for record in records if record["stage"] == "acceptance-parked")["advisory"]
        is True
    )


def test_complete_and_accept_fail_reworks_and_persists_count_across_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(acceptance_policy="ai-then-human")
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _FakeAcceptancePass(verdict="FAIL"),
        raising=False,
    )
    first_journal = JournalFile(path=repo / "first-journal.jsonl")
    second_journal = JournalFile(path=repo / "second-journal.jsonl")

    dispatcher.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=first_journal,
    )
    first_record = make_beads_client(config=_config()).show_issue(issue_id=item.id)
    dispatcher.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=second_journal,
    )

    second_record = make_beads_client(config=_config()).show_issue(issue_id=item.id)
    assert first_record["metadata"]["acceptance_failed_ai_passes"] == 1
    assert second_record["metadata"]["acceptance_failed_ai_passes"] == 2
    stored = _stored()[item.id]
    # The under-cap rework return parks the item `active` CARRYING the marker:
    # the marker is what makes it reachable, since it is the drain's selection
    # input and `dispatch --item` accepts a marked item.
    assert (stored.status, stored.blocked_reason) == ("active", None)
    assert stored.rework_pending is True
    records = [
        json.loads(line) for line in second_journal.path.read_text(encoding="utf-8").splitlines()
    ]
    rework = next(record for record in records if record["stage"] == "acceptance-auto-rework")
    # Migrated onto the append layer: this disposition record now carries the
    # stamped envelope it previously lacked ENTIRELY — it was written by a
    # direct journal-path open, with no timestamp and no attribution.
    assert rework["at"]
    assert rework["invoker_source"] in {"flag", "env", "fallback"}
    assert _journal_payload(record=rework) == {
        "stage": "acceptance-auto-rework",
        "work_item_id": item.id,
        "policy": "ai-then-human",
        "failed_ai_passes": 2,
        "acceptance_rework_cap": 2,
        "cap_source": "dispatcher.acceptance_rework_cap",
    }


def test_complete_and_accept_fail_past_label_cap_blocks_needs_human(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(acceptance_policy="ai-only")
    append_work_item(path=_config(), item=item)
    make_beads_client(config=_config()).update_issue(
        issue_id=item.id,
        add_labels=["acceptance-rework-cap:1"],
    )
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _FakeAcceptancePass(verdict="FAIL"),
        raising=False,
    )
    first_journal = JournalFile(path=repo / "first-label-cap-journal.jsonl")
    second_journal = JournalFile(path=repo / "second-label-cap-journal.jsonl")

    dispatcher.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=first_journal,
    )
    dispatcher.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=second_journal,
    )

    stored = _stored()[item.id]
    assert (stored.status, stored.blocked_reason) == ("blocked", "needs-human")
    record = make_beads_client(config=_config()).show_issue(issue_id=item.id)
    assert record["metadata"]["acceptance_failed_ai_passes"] == 2
    records = [
        json.loads(line) for line in second_journal.path.read_text(encoding="utf-8").splitlines()
    ]
    escalation = next(
        record for record in records if record["stage"] == "acceptance-rework-cap-exceeded"
    )
    assert escalation["at"]
    assert escalation["invoker_source"] in {"flag", "env", "fallback"}
    assert _journal_payload(record=escalation) == {
        "stage": "acceptance-rework-cap-exceeded",
        "work_item_id": item.id,
        "policy": "ai-only",
        "failed_ai_passes": 2,
        "acceptance_rework_cap": 1,
        "cap_source": "acceptance-rework-cap label",
        "blocked_reason": "needs-human",
    }


def test_complete_and_accept_human_only_fail_never_auto_reworks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(acceptance_policy="human-only")
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _FakeAcceptancePass(verdict="FAIL"),
        raising=False,
    )
    journal = JournalFile(path=repo / "human-only-fail-journal.jsonl")

    dispatcher.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=journal,
    )

    stored = _stored()[item.id]
    assert (stored.status, stored.blocked_reason) == ("acceptance", None)
    record = make_beads_client(config=_config()).show_issue(issue_id=item.id)
    assert "acceptance_failed_ai_passes" not in record["metadata"]
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    parked = next(record for record in records if record["stage"] == "acceptance-parked")
    assert parked["advisory"] is True
    assert parked["acceptance_verdict"] == "FAIL"
    assert "acceptance-auto-rework" not in {record["stage"] for record in records}


@pytest.mark.parametrize("policy", ["ai-only", "ai-then-human", "human-only"])
def test_complete_and_accept_needs_attention_parks_under_every_acceptance_policy(
    policy: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(acceptance_policy=policy)
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _FakeAcceptancePass(verdict="NEEDS_ATTENTION", absent_evidence=("telemetry",)),
        raising=False,
    )
    journal = JournalFile(path=repo / f"needs-attention-{policy}-journal.jsonl")

    dispatcher.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=journal,
    )

    stored = _stored()[item.id]
    # Parked, not disposed: not accepted to done, not routed to rework, and not
    # escalated to blocked — under `ai-only` exactly as under `human-only`.
    assert (stored.status, stored.resolution, stored.blocked_reason) == ("acceptance", None, None)
    record = make_beads_client(config=_config()).show_issue(issue_id=item.id)
    # The rework:pending marker is never stamped and acceptance_rework_cap is
    # never consumed: the failed-pass counter the cap reads stays absent, which
    # is the same ledger write the FAIL route uses to stamp and count.
    assert "acceptance_failed_ai_passes" not in record["metadata"]
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    stages = {entry["stage"] for entry in records}
    assert stages == {"ledger-complete", "acceptance-ai-pass", "acceptance-parked"}
    parked = next(entry for entry in records if entry["stage"] == "acceptance-parked")
    assert parked["acceptance_verdict"] == "NEEDS_ATTENTION"
    assert parked["absent_evidence"] == ["telemetry"]


def test_dispatch_finalize_invokes_cost_gate_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    cost_gate = _RecordingCostGate()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    monkeypatch.setattr(_dispatcher_run_commands, "cost_gate_after_verdict", cost_gate)

    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )

    assert exit_code == 0
    assert len(cost_gate.calls) == 1
    call = cost_gate.calls[0]
    assert call.repo == repo
    assert [outcome.work_item_id for outcome in call.outcomes] == [item.id]
    assert hasattr(call.journal, "append")
    assert hasattr(call.runner, "run")
    assert call.args.item == item.id


def test_dispatch_materializes_mode600_overlay_and_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    plan = fake.seen[0]["plan"]
    assert isinstance(plan, DispatchPlan)
    assert plan.workflow_toml.name == f"fabro-run-config-{item.id}.toml"
    assert (
        plan.janitor_checkout == tmp_path / "home" / ".worktrees" / repo.name / f"janitor-{item.id}"
    )
    assert not plan.workflow_toml.exists()
    assert fake.overlay_modes == [0o600]
    overlay_text = fake.overlay_texts[0]
    # The overlay is the run-scoped credential projection: it carries
    # the token value read from the Dispatcher's process env (mode-600,
    # deleted when the run returns — both asserted above). The token
    # never reaches the journal, and no dead {{ env }} interpolation
    # literal survives into the overlay.
    assert _FAKE_TOKEN_LINE in overlay_text
    assert _FAKE_GITHUB_TOKEN_LINE in overlay_text
    assert _ENV_INTERPOLATION_LITERAL not in overlay_text
    assert _GH_ENV_INTERPOLATION_LITERAL not in overlay_text
    # The graph the run receives is the PER-DISPATCH payload's rendered copy,
    # carrying this dispatch's resolved node timeouts as literal durations —
    # and it is torn down with the overlay when the run returns.
    payload_graph = Path(overlay_text.split('graph = "', 1)[1].split('"', 1)[0])
    assert payload_graph.name == "workflow.fabro"
    assert payload_graph.parent.name == f"fabro-workflow-{item.id}"
    assert payload_graph.parent != workflow.parent
    assert not payload_graph.parent.exists()
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    assert "test-oauth-token" not in journal_text
    assert "test-github-token" not in journal_text


def test_dispatch_overlay_provisions_sibling_clones_for_fleet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The materialized overlay provisions every fleet member EXCEPT the
    dispatch target (already the sandbox workspace clone) as a depth-1
    prepare-step clone under /workspace/siblings, and projects
    LIVESPEC_SIBLING_CLONES_ROOT into the sandbox env table so
    cross-repo checks under `just check` resolve the siblings there —
    mirroring livespec CI's sibling-clone provisioning."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    overlay_text = fake.overlay_texts[0]
    assert _LIVESPEC_CLONE_STEP_LINE in overlay_text
    assert _DEV_TOOLING_CLONE_STEP_LINE in overlay_text
    assert _SIBLING_ENV_LINE in overlay_text
    # The canned fleet manifest registers the dispatch target itself
    # (basename "repo"); its clone step must be excluded — the sandbox
    # already holds that repo as the workspace clone.
    assert "github.com/thewoolleyman/repo" not in overlay_text


def test_dispatch_green_without_sha_parks_needs_attention_instead_of_reworking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id, sha=None)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    assert (
        main(argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)])
        == 0
    )
    stored = _stored()[item.id]
    # No merge sha means the merged diff was never read. Under the ratified
    # evidence rule that is an ABSENT leg, not observed failing evidence, so it
    # parks in acceptance rather than routing to rework (which was the pre-v072
    # behavior this case used to pin).
    assert (stored.status, stored.audit) == ("acceptance", None)
    record = make_beads_client(config=_config()).show_issue(issue_id=item.id)
    assert "acceptance_failed_ai_passes" not in record["metadata"]


def test_dispatch_failed_outcome_leaves_item_open(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    failed = DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="fabro exploded",
    )
    monkeypatch.setattr(
        _dispatcher_loop, "run_dispatch", _FakeRunDispatch(outcomes={item.id: failed})
    )
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    assert exit_code == 1
    assert "failed at fabro-run" in capsys.readouterr().out
    assert _stored()[item.id].status == "active"


def test_dispatch_no_close_on_merge_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    assert _stored()[item.id].status == "active"


def test_dispatch_rejects_not_ready_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    blocker = _item(id="blocker-1")
    blocked = _item(id="blocked-2", depends_on=("blocker-1",))
    append_work_item(path=_config(), item=blocker)
    append_work_item(path=_config(), item=blocked)
    monkeypatch.setattr(
        _dispatcher_loop,
        "run_dispatch",
        _FakeRunDispatch(outcomes={}),
    )
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", "blocked-2", "--workflow", str(workflow)]
    )
    assert exit_code == 3
    assert (
        main(argv=["dispatch", "--repo", str(repo), "--item", "ghost", "--workflow", str(workflow)])
        == 3
    )


def test_dispatch_precondition_failures(tmp_path: Path) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    assert (
        main(
            argv=[
                "dispatch",
                "--repo",
                str(tmp_path / "nope"),
                "--item",
                "x",
                "--workflow",
                str(workflow),
            ]
        )
        == 3
    )
    assert (
        main(
            argv=[
                "dispatch",
                "--repo",
                str(repo),
                "--item",
                "x",
                "--workflow",
                str(tmp_path / "missing.toml"),
            ]
        )
        == 3
    )


def test_dispatch_bad_janitor_is_usage_error(tmp_path: Path) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    base = ["dispatch", "--repo", str(repo), "--item", "x", "--workflow", str(workflow)]
    assert main(argv=[*base, "--janitor", "not json"]) == 2
    assert main(argv=[*base, "--janitor", '{"a": 1}']) == 2
    assert main(argv=[*base, "--janitor", '["ok", 1]']) == 2


def test_dispatch_passes_custom_janitor_through(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--janitor",
            '["echo", "ok"]',
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    plan = fake.seen[0]["plan"]
    assert isinstance(plan, DispatchPlan)
    assert plan.janitor == ("echo", "ok")


def test_dispatch_ledger_gate_blocks_and_skip_flag_bypasses(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    append_work_item(path=_config(), item=_item(id="orphaned-9", depends_on=("ghost-7",)))
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    base = ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    assert main(argv=base) == 1
    err = capsys.readouterr().err
    assert "pre-dispatch ledger checks failed" in err
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    assert "ledger-check" in journal_text
    assert main(argv=[*base, "--skip-ledger-check", "--no-close-on-merge"]) == 0


def test_dispatch_default_workflow_materializes_from_repo_fabro_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--no-close-on-merge"]
    )
    assert exit_code == 0
    plan = fake.seen[0]["plan"]
    assert isinstance(plan, DispatchPlan)
    assert plan.workflow_toml.name == f"fabro-run-config-{item.id}.toml"
    overlay_text = fake.overlay_texts[0]
    assert "implement-work-item" in overlay_text
    assert 'graph = "workflow.fabro"' not in overlay_text
    # The repo's committed run config carries NO secret and NO
    # {{ env }} interpolation (a dead channel for server-mediated runs:
    # the worker env is allowlist-scrubbed); the overlay appends the env
    # table with the token from the Dispatcher's process env.
    assert _FAKE_TOKEN_LINE in overlay_text
    assert _ENV_INTERPOLATION_LITERAL not in overlay_text


def test_dispatch_blocked_outcome_marks_item_blocked_needs_human(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run parked at the in-loop human gate is surfaced as terminal blocked."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    blocked = DispatchOutcome(
        work_item_id=item.id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="run 01RUNBLOCKED parked at a human gate; answer with `fabro attach 01RUNBLOCKED`",
    )
    monkeypatch.setattr(
        _dispatcher_loop, "run_dispatch", _FakeRunDispatch(outcomes={item.id: blocked})
    )

    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )

    assert exit_code == 4
    captured = capsys.readouterr()
    out = captured.out
    err = captured.err
    assert "blocked at fabro-run" in out
    assert "fabro attach 01RUNBLOCKED" in out
    stored = _stored()[item.id]
    assert stored.status == "blocked"
    assert stored.blocked_reason == "needs-human"
    assert "bounced to backlog" not in err
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    assert '"blocked"' in journal_text
    assert '"needs-human-blocked"' in journal_text
    assert '"blocked-bounce"' not in journal_text
    assert "ledger-accept" not in journal_text
    assert "ledger-complete" not in journal_text


def test_dispatch_fails_fast_when_oauth_token_env_is_absent_or_empty(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing CLAUDE_CODE_OAUTH_TOKEN refuses the dispatch outright:
    the Dispatcher's process env is the SOURCE of the run-scoped overlay
    projection, so absence means there is nothing to project into the
    sandbox. The error names the dispatch target's configured wrapper
    and the full per-wrapper credential set as the fix."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    target_wrapper = "/opt/openbrain/with-openbrain-env.sh"
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "credential_wrapper": [target_wrapper, "--"],
                "git_author": {
                    "operator_name": "Chad Woolley",
                    "operator_email": "thewoolleyman@gmail.com",
                },
                "livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}},
            }
        ),
        encoding="utf-8",
    )
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        _dispatcher_loop,
        "run_dispatch",
        _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)}),
    )
    base = ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN")
    assert main(argv=base) == 1
    out = capsys.readouterr().out
    assert "run-config-overlay" in out
    assert "GITHUB_APP_ID" in out
    assert "GITHUB_PRIVATE_KEY" in out
    assert "BEADS_DOLT_PASSWORD" in out
    assert "CLAUDE_CODE_OAUTH_TOKEN" in out
    assert target_wrapper in out
    assert "with-livespec-env.sh" not in out
    # The admission valve transitioned the item to active before the overlay
    # materialization refused, then the pre-run release returned it to the ready
    # set because Fabro never created a run. The empty-string form of "absent"
    # refuses identically.
    assert _stored()[item.id].status == "ready"
    item2 = _item(id="livespec-impl-beads-t2")
    append_work_item(path=_config(), item=item2)
    base2 = ["dispatch", "--repo", str(repo), "--item", item2.id, "--workflow", str(workflow)]
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "")
    assert main(argv=base2) == 1
    out2 = capsys.readouterr().out
    assert "CLAUDE_CODE_OAUTH_TOKEN" in out2
    assert target_wrapper in out2
    assert "with-livespec-env.sh" not in out2


def test_dispatch_fails_closed_when_github_app_env_is_absent(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing GitHub App env refuses dispatch before Fabro launches.

    The dispatch TARGET's credential_wrapper is the ONLY GitHub
    credential source (github-app-auth Pillar 2): with GITHUB_APP_ID +
    GITHUB_PRIVATE_KEY absent the dispatch fails CLOSED at the
    `github-app-auth` stage — and a still-present retired fleet PAT
    (LIVESPEC_FAMILY_GITHUB_TOKEN) must NOT rescue it, nor leak into
    the refusal output.
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        _dispatcher_loop,
        "run_dispatch",
        _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)}),
    )
    # Un-stub the supplier: exercise the REAL fail-closed resolution.
    monkeypatch.setattr(
        _dispatcher_loop.selfup, "github_token_supplier", _real_github_token_supplier
    )
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("LIVESPEC_FAMILY_GITHUB_TOKEN", "github_pat_retired")
    base = ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    assert main(argv=base) == 1
    out = capsys.readouterr().out
    assert "github-app-auth" in out
    assert "GITHUB_APP_ID" in out
    assert "credential_wrapper" in out
    assert "github_pat_retired" not in out
    # Admission moved the item to active before the refusal, then the pre-run
    # release returned it to the ready set because Fabro never created a run.
    assert _stored()[item.id].status == "ready"


def test_dispatch_routes_a_mint_failure_as_overlay_refusal(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A supplier whose MINT fails (config present, App API rejecting)
    refuses at the run-config-overlay stage with the actionable detail."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        _dispatcher_loop,
        "run_dispatch",
        _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)}),
    )

    def _raising_token() -> str:
        raise GithubAppAuthError(detail="the App API rejected the JWT")

    monkeypatch.setattr(_dispatcher_loop.selfup, "github_token_supplier", lambda: _raising_token)
    base = ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    assert main(argv=base) == 1
    out = capsys.readouterr().out
    assert "run-config-overlay" in out
    assert "the App API rejected the JWT" in out


def test_dispatch_fails_when_workflow_config_is_not_materializable(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run config declaring no graph refuses at payload materialization.

    That is one stage EARLIER than the overlay it used to refuse at — the
    payload materializer needs the declared graph to render this dispatch's
    node timeouts into, so it discovers the same unusable config first and
    names what the config must carry.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    bare = tmp_path / "bare.toml"
    _ = bare.write_text("_version = 1\n", encoding="utf-8")
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _FakeRunDispatch(outcomes={}))
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(bare)]
    )
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "workflow-payload" in out
    assert "declares no [workflow] graph" in out
    assert _stored()[item.id].status == "ready"


@dataclass(kw_only=True)
class _FakeManifestRunner:
    """Scripted ShellCommandRunner stand-in for the fleet-manifest fetch."""

    result: CommandResult
    calls: list[tuple[list[str], Path]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert timeout_seconds > 0
        _ = env
        self.calls.append((argv, cwd))
        return self.result


def test_fetch_fleet_manifest_text_shells_gh_api_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production fetch is a HOST-SIDE `gh api` raw-content read of
    .livespec-fleet-manifest.jsonc from livespec master at run-config generation
    time — the canonical fleet member registry, fetched the same way the
    other family consumers (fleet conformance, release fan-out) consume
    it."""
    fake = _FakeManifestRunner(
        result=CommandResult(exit_code=0, stdout=_FLEET_MANIFEST_TEXT, stderr="")
    )
    monkeypatch.setattr(_dispatcher_sibling_clones, "ShellCommandRunner", lambda: fake)
    assert _real_fetch_fleet_manifest_text() == _FLEET_MANIFEST_TEXT
    argv, _cwd = fake.calls[0]
    assert argv[:2] == ["gh", "api"]
    assert "Accept: application/vnd.github.raw" in argv
    assert argv[-1] == "repos/thewoolleyman/livespec/contents/.livespec-fleet-manifest.jsonc"


def test_fetch_fleet_manifest_text_returns_none_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing = _FakeManifestRunner(
        result=CommandResult(exit_code=1, stdout="", stderr="gh: HTTP 404")
    )
    monkeypatch.setattr(_dispatcher_sibling_clones, "ShellCommandRunner", lambda: failing)
    assert _real_fetch_fleet_manifest_text() is None
    empty = _FakeManifestRunner(result=CommandResult(exit_code=0, stdout="  \n", stderr=""))
    monkeypatch.setattr(_dispatcher_sibling_clones, "ShellCommandRunner", lambda: empty)
    assert _real_fetch_fleet_manifest_text() is None


def test_dispatch_proceeds_with_empty_siblings_when_fleet_manifest_is_unfetchable(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unfetchable fleet manifest (no `gh`, a non-fleet adopter) renders
    an EMPTY sibling projection and the dispatch PROCEEDS — the projection
    is OPTIONAL per the self-contained plugin dispatch contract
    (SPECIFICATION/contracts.md). The pre-v021 behavior refused the
    dispatch here; that invariant is RETIRED — only a present-but-MALFORMED
    manifest still refuses (see the sibling test below)."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: None,
    )
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    # The dispatch ran (it was NOT refused for the missing manifest).
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "sibling-clone provisioning refused" not in out
    # The materialized overlay carries an EMPTY sibling set — no per-member
    # depth-1 clone steps were appended.
    assert "git clone --quiet --depth 1" not in fake.overlay_texts[0]


def test_dispatch_fails_fast_when_fleet_manifest_is_malformed(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _FakeRunDispatch(outcomes={}))
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: "not a fleet manifest {{",
    )
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "run-config-overlay" in out
    assert ".livespec-fleet-manifest.jsonc" in out
    assert _stored()[item.id].status == "ready"


def test_dispatch_custom_journal_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    journal_path = tmp_path / "elsewhere.jsonl"
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--journal",
            str(journal_path),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    assert journal_path.is_file()


def test_loop_without_item_drains_ranked_queue(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "5",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    payload = capsys.readouterr().out
    assert item.id in payload
    seen_plan = fake.seen[0]["plan"]
    assert isinstance(seen_plan, DispatchPlan)
    assert seen_plan.work_item_id == item.id


def test_loop_refuses_missing_requested_item_before_dispatching(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--workflow",
            str(workflow),
            "--item",
            "missing-item",
        ]
    )

    assert exit_code == 3
    assert "work-item(s) missing-item not found in the target-tenant" in capsys.readouterr().err
    assert fake.seen == []


def test_loop_dispatches_named_items_within_budget(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    first = _item(id="a-1", rank="a1")
    second = _item(id="b-2", rank="a2")
    append_work_item(path=_config(), item=first)
    append_work_item(path=_config(), item=second)
    fake = _FakeRunDispatch(outcomes={"a-1": _green_outcome(item_id="a-1")})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--workflow",
            str(workflow),
            "--item",
            "a-1",
            "--item",
            "b-2",
            "--no-close-on-merge",
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [entry["work_item_id"] for entry in payload] == ["a-1"]
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    pick = next(
        json.loads(line)
        for line in journal_text.splitlines()
        if json.loads(line)["stage"] == "loop-pick"
    )
    assert pick["picked"] == ["a-1"]
    assert pick["dry_run"] is False


def test_loop_finalize_invokes_cost_gate_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(id="a-1", rank="a1")
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    cost_gate = _RecordingCostGate()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    monkeypatch.setattr(_dispatcher_loop_command, "cost_gate_after_verdict", cost_gate)

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--workflow",
            str(workflow),
            "--item",
            item.id,
            "--no-close-on-merge",
        ]
    )

    assert exit_code == 0
    assert len(cost_gate.calls) == 1
    call = cost_gate.calls[0]
    assert call.repo == repo
    assert [outcome.work_item_id for outcome in call.outcomes] == [item.id]
    assert hasattr(call.journal, "append")
    assert hasattr(call.runner, "run")
    assert call.args.items == [item.id]


def test_loop_autonomous_parallel_mixed_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    first = _item(id="a-1", rank="a1")
    second = _item(id="b-2", rank="a2")
    append_work_item(path=_config(), item=first)
    append_work_item(path=_config(), item=second)
    failed = DispatchOutcome(
        work_item_id="b-2",
        status="failed",
        stage="merge-poll",
        pr_number=12,
        merge_sha=None,
        detail="poll budget",
    )
    fake = _FakeRunDispatch(outcomes={"a-1": _green_outcome(item_id="a-1"), "b-2": failed})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "5",
            "--parallel",
            "2",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 1
    assert len(fake.seen) == 2


def test_loop_precondition_usage_and_ledger_gate(
    tmp_path: Path,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    assert (
        main(
            argv=[
                "loop",
                "--repo",
                str(tmp_path / "nope"),
                "--budget",
                "1",
                "--workflow",
                str(workflow),
            ]
        )
        == 3
    )
    assert (
        main(
            argv=[
                "loop",
                "--repo",
                str(repo),
                "--budget",
                "1",
                "--workflow",
                str(workflow),
                "--janitor",
                "broken",
            ]
        )
        == 2
    )
    append_work_item(path=_config(), item=_item(id="orphaned-9", depends_on=("ghost-7",)))
    assert (
        main(argv=["loop", "--repo", str(repo), "--budget", "1", "--workflow", str(workflow)]) == 1
    )


def test_loop_parallel_floor_of_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--parallel",
            "0",
            "--workflow",
            str(workflow),
            "--item",
            item.id,
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0


def test_ledger_finding_dataclass_shape() -> None:
    finding = LedgerFinding(check="c", item_id="i", message="m")
    assert (finding.check, finding.item_id, finding.message, finding.severity) == (
        "c",
        "i",
        "m",
        "fail",
    )
    skipped = LedgerFinding(check="c", item_id="i", message="m", severity="skipped")
    assert skipped.severity == "skipped"


# ---------------------------------------------------------------------------
# bn4 — ledger comments in the goal, sizing warnings, long-haul fabro budget
# ---------------------------------------------------------------------------


def test_render_goal_renders_labeled_comments_section(tmp_path: Path) -> None:
    """Comments are operator riders (finding (c) of bn4): they must reach the
    sandbox brief under a clearly-labeled section, with per-entry provenance
    when the record carries it."""
    comments = (
        WorkItemComment(text="first rider", author="operator", created_at="2026-06-12T00:00:00Z"),
        WorkItemComment(text="author only", author="operator", created_at=None),
        WorkItemComment(text="date only", author=None, created_at="2026-06-13T00:00:00Z"),
        WorkItemComment(text="bare", author=None, created_at=None),
    )
    goal = render_goal(item=_item(), repo=tmp_path, branch="feat/t", comments=comments)
    assert "Ledger comments" in goal
    assert "treat them as part of the brief" in goal
    assert "[1] (operator, 2026-06-12T00:00:00Z) first rider" in goal
    assert "[2] (operator) author only" in goal
    assert "[3] (2026-06-13T00:00:00Z) date only" in goal
    assert "[4] bare" in goal


def test_render_goal_omits_comments_section_when_none(tmp_path: Path) -> None:
    goal = render_goal(item=_item(), repo=tmp_path, branch="feat/t")
    assert "Ledger comments" not in goal


# MiniJinja's three opening delimiters: expression `{{`, statement `{%`,
# comment `{#`. Fabro renders the run goal through MiniJinja (the graph's
# `goal` attribute) and into the prompts as `{{ goal }}`, so any one of
# these in untrusted item prose would re-enter template mode and the
# undefined name would raise `template_undefined_variable` at validation
# (livespec-impl-beads-ajv: three v5k-leg dispatches failed pre-flight on
# justfile recipe `{{ }}` syntax in the description). The escape
# neutralizes the OPENING delimiters, so the lexer never enters a tag.
_MINIJINJA_OPENERS = ("{{", "{%", "{#")


def _live_minijinja_openers(*, rendered: str) -> list[str]:
    """Return MiniJinja openers still LIVE in `rendered` after stripping the
    literal-emitting escape expressions render_goal inserts.

    render_goal neutralizes each opener into a literal-emitting expression
    that ALWAYS opens with `{{` (only `{{ ... }}` emits a value): `{{` ->
    `{{ "{{" }}`, `{%` -> `{{ "{%" }}`, `{#` -> `{{ "{#" }}`. Removing every
    such escape expression must leave NO opener behind: any `{{`/`{%`/`{#`
    that survives the strip is a live template construct that would
    re-enter template mode and raise `template_undefined_variable` at
    validation. Stripping the full expressions first is necessary because
    each escape itself contains the two literal opener characters inside
    its quoted string.
    """
    stripped = rendered
    for opener in _MINIJINJA_OPENERS:
        stripped = stripped.replace(f'{{{{ "{opener}" }}}}', "")
    return [opener for opener in _MINIJINJA_OPENERS if opener in stripped]


def test_render_goal_escapes_minijinja_delimiters_in_arbitrary_prose(tmp_path: Path) -> None:
    """Untrusted item prose (justfile `{{ }}`, statement/comment tags, a raw-block
    breaker, backslashes, quotes, newlines) must NOT survive into the rendered goal
    as live MiniJinja syntax — otherwise fabro raises `template_undefined_variable`
    in graph attribute `goal` (livespec-impl-beads-ajv). The escape neutralizes
    every opening delimiter into a literal-emitting expression; fabro renders those
    back to the original text, so no live `{{`/`{%`/`{#` remains."""
    adversarial = (
        'recipe target: just {{ build_dir }} && echo "go"\n'
        "stmt {% if x %}body{% endif %} comment {# note #}\n"
        "raw-block breaker {% endraw %} then {{ another }}\n"
        "backslash \\ path C:\\tmp and nested {{ {{ inner }} }}"
    )
    item = _item(title="curly {{ title_var }} bug", description=adversarial)
    comments = (WorkItemComment(text="rider with {{ comment_var }}", author=None, created_at=None),)
    goal = render_goal(item=item, repo=tmp_path, branch="feat/t", comments=comments)
    assert _live_minijinja_openers(rendered=goal) == []
    # The escape is literal-emitting (not lossy): each neutralized opener
    # is still present as the start of its escape expression.
    assert '{{ "{{" }}' in goal
    assert '{{ "{%" }}' in goal
    assert '{{ "{#" }}' in goal


@pytest.mark.parametrize(
    ("field", "opener"),
    [
        ("description", "{{"),
        ("acceptance_criteria", "{%"),
        ("notes", "{#"),
    ],
)
def test_goal_source_preflight_flags_each_minijinja_opener_kind(
    field: str,
    opener: str,
) -> None:
    item = _item(**{field: f"bad {opener} token"})

    [finding] = _dispatcher_goal.minijinja_openers_in_goal_sources(
        item=item,
        comments=(),
        lessons="",
    )

    expected_field = "acceptance" if field == "acceptance_criteria" else field
    assert finding.source == expected_field
    assert finding.opener == opener
    assert expected_field in _dispatcher_goal.minijinja_findings_detail(findings=(finding,))


def test_goal_source_preflight_names_comment_id_and_created_at() -> None:
    comments = (
        WorkItemComment(
            text="poisoned {# comment",
            author="operator",
            created_at="2026-08-22T10:11:12Z",
            comment_id="comment-9",
        ),
    )

    [finding] = _dispatcher_goal.minijinja_openers_in_goal_sources(
        item=_item(),
        comments=comments,
        lessons="",
    )

    detail = _dispatcher_goal.minijinja_findings_detail(findings=(finding,))
    assert finding.source == "ledger comment comment-9 created 2026-08-22T10:11:12Z"
    assert "ledger comment comment-9 created 2026-08-22T10:11:12Z" in detail


def test_goal_source_preflight_runs_before_escape_false_negative(tmp_path: Path) -> None:
    item = _item(description="bad {{ token")
    goal = render_goal(item=item, repo=tmp_path, branch="feat/t")

    assert _dispatcher_goal.minijinja_openers_in_goal_sources(
        item=item,
        comments=(),
        lessons="",
    )
    assert "{{ token" not in goal


def test_goal_source_preflight_allows_healthy_item() -> None:
    assert (
        _dispatcher_goal.minijinja_openers_in_goal_sources(
            item=_item(),
            comments=(
                WorkItemComment(
                    text="plain rider",
                    author="operator",
                    created_at="2026-08-22T10:11:12Z",
                    comment_id="comment-9",
                ),
            ),
            lessons="plain lesson",
        )
        == ()
    )


def test_item_sizing_warnings_empty_for_small_item() -> None:
    assert item_sizing_warnings(item=_item()) == ()


def test_item_sizing_warnings_flags_long_description() -> None:
    [warning] = item_sizing_warnings(item=_item(description="y" * 1501))
    assert "1501" in warning
    assert "splitting" in warning


def test_item_sizing_warnings_flags_multi_part_marker() -> None:
    [warning] = item_sizing_warnings(item=_item(title="A multi-RGR refactor"))
    assert "multi-part/multi-RGR" in warning


def test_item_sizing_warnings_flags_enumerated_parts() -> None:
    enumerated = _item(description="Do (1) the first, (2) the second, (3) the third thing.")
    [warning] = item_sizing_warnings(item=enumerated)
    assert "3 enumerated parts" in warning
    two_parts = _item(description="Do (1) the first and (2) the second thing.")
    assert item_sizing_warnings(item=two_parts) == ()


def test_fabro_run_uses_the_derived_subprocess_timeout(tmp_path: Path) -> None:
    """The foreground `fabro run` subprocess budget FOLLOWS the resolved graph.

    It must outlive the graph's worst-case wall clock (every node at its
    resolved timeout, taken at its worst-case visit count) plus provisioning
    slack: a budget below the graph's own ceiling kills the CLI mid-run
    while the server-side engine keeps executing. It is derived rather than
    fixed so that lengthening a node cannot outrun it and shortening one is
    not masked.
    """
    runner = _FakeRunner(queue=[_err()])
    outcome, _journal, _naps = _dispatch(runner=runner, repo=tmp_path)
    assert outcome.status == "failed"
    assert runner.timeouts[0] == derive_fabro_timeout_seconds(timeouts=default_node_timeouts())


def test_dispatch_goal_text_carries_ledger_comments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding (c) of bn4: rider instructions added as ledger comments must
    arrive in the sandbox goal text (the dispatcher previously rendered the
    description only, so pre-authorizations never reached the agent)."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    client.seed_comment(
        issue_id=item.id,
        text="pre-authorization: also bump the dev-tooling pin",
        author="operator",
        created_at="2026-06-12T08:00:00Z",
    )
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop_plan.tempfile.gettempdir",
        lambda: str(tmp_path),
    )
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    goal_text = (tmp_path / f"fabro-goal-{item.id}.md").read_text(encoding="utf-8")
    assert "Ledger comments" in goal_text
    assert "pre-authorization: also bump the dev-tooling pin" in goal_text
    assert "(operator, 2026-06-12T08:00:00Z)" in goal_text


def test_dispatch_fails_at_ledger_comments_stage_when_read_raises(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed comments read refuses the dispatch (error-as-data at the
    `ledger-comments` stage) instead of proceeding comment-blind — silently
    dropping riders is exactly the bug this stage exists to prevent."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _FakeRunDispatch(outcomes={}))

    def _boom(*, path: StoreConfig, work_item_id: str) -> tuple[WorkItemComment, ...]:
        _ = (path, work_item_id)
        raise BeadsCommandError(command="bd comments", exit_code=1, stderr="connection lost")

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_credentials.read_work_item_comments",
        _boom,
    )
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "ledger-comments" in out
    assert "BeadsCommandError" in out
    assert _stored()[item.id].status == "ready"


def test_dispatch_refuses_minijinja_goal_before_fabro_and_releases_claim(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(description="poisoned {{ goal }}")
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        _dispatcher_loop,
        "read_dispatch_comments",
        lambda **_: (
            WorkItemComment(
                text="also poisoned {% rider %}",
                author="operator",
                created_at="2026-08-22T10:11:12Z",
                comment_id="comment-9",
            ),
        ),
    )
    fake = _FakeRunDispatch(outcomes={})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)

    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )

    assert exit_code == 1
    assert fake.seen == []
    out = capsys.readouterr().out
    assert "goal-minijinja-preflight" in out
    assert "description" in out
    assert "ledger comment comment-9 created 2026-08-22T10:11:12Z" in out
    stored = _stored()[item.id]
    assert stored.status == "ready"
    assert stored.assignee is None


def test_dispatch_warns_on_oversized_item_without_blocking(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sizing heuristics are WARN-only (journal record + stderr line): an
    oversized item still dispatches — the dispatcher never blocks on them."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(description="multi-RGR scope: " + "z" * 1600)
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    err = capsys.readouterr().err
    assert "WARN: item-sizing" in err
    assert item.id in err
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    sizing = next(
        json.loads(line)
        for line in journal_text.splitlines()
        if json.loads(line)["stage"] == "sizing-warn"
    )
    assert sizing["work_item_id"] == item.id
    assert len(sizing["warnings"]) == 2


# --------------------------------------------------------------------------
# Loop-exit reflection stage wiring (work-item 29f.2). The stage runs AFTER
# the verdict is computed and is immutable by it (best-practices §6).
# --------------------------------------------------------------------------


def test_loop_runs_reflection_stage_after_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    _dispatcher_reflection.reset_auto_trip()
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(id="a-1", rank="a1")
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={"a-1": _green_outcome(item_id="a-1")})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    reflection_rec = next(
        json.loads(line)
        for line in journal_text.splitlines()
        if json.loads(line)["stage"] == "reflection"
    )
    assert reflection_rec["mode"] == "observe"
    assert reflection_rec["green_count"] == 1
    # The OTLP spans land in the journal's sibling spans file.
    spans_path = repo / "tmp" / "fabro-dispatch-journal-reflection-spans.jsonl"
    assert spans_path.is_file()


def test_loop_reflection_failure_never_changes_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reflection that raises must NOT alter the loop's exit code: the
    verdict is computed before the fail-open stage runs (best-practices
    §6). `reflect` is itself fail-open, but even a hypothetical raise out
    of it is contained because the exit code is already decided — the
    patched raise here proves reflect is the LAST thing the loop does,
    after the green verdict is already computed."""
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    _dispatcher_reflection.reset_auto_trip()
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(id="a-1", rank="a1")
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={"a-1": _green_outcome(item_id="a-1")})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)

    def _boom(**_kwargs: object) -> None:
        raise RuntimeError("reflection blew up")

    monkeypatch.setattr(_dispatcher_loop_command, "reflect", _boom)
    with pytest.raises(RuntimeError, match="reflection blew up"):
        _ = main(
            argv=[
                "loop",
                "--repo",
                str(repo),
                "--budget",
                "1",
                "--workflow",
                str(workflow),
                "--no-close-on-merge",
            ]
        )


def test_dispatch_runs_reflection_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    _dispatcher_reflection.reset_auto_trip()
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    fake = _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)})
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", fake)
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    assert exit_code == 0
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    assert any(json.loads(line)["stage"] == "reflection" for line in journal_text.splitlines())


# ---------------------------------------------------------------------------
# Dispatcher drain order composes the `next` ranking authority (i3jiny).
#
# The `next` ranker and the Fabro Dispatcher share the readiness filter
# (`lifecycle.is_item_ready`) AND the canonical ranking key
# (`lifecycle.ready_sort_key` = `(rank, id)`). If they diverged on sort,
# then under the dark factory's concurrency cap + budget + merge
# backpressure the drain ORDER (which decides which ready items run) would
# silently starve work relative to the policy `next` advertises as
# authoritative. Composing the one shared `ready_sort_key` keeps them
# identical by construction.
# ---------------------------------------------------------------------------


def test_ready_items_drain_order_equals_next_ranking(tmp_path: Path) -> None:
    # Distinct ranks (NOT id-sorted) so the assertion proves the order is
    # driven by `rank`, not by insertion or id order, on BOTH surfaces.
    fixture = [
        _item(id="li-aaa", rank="a3"),
        _item(id="li-bbb", rank="a1"),
        _item(id="li-ccc", rank="a2"),
    ]
    # tmp_path has no `.livespec.jsonc`, so `ready_items` sees an empty
    # cross-repo manifest and every ready, dependency-free item is ready.
    drain_order = [item.id for item in ready_items(items=fixture, repo=tmp_path)]
    next_order = [c["work_item_ref"] for c in next_command.rank_candidates(items=fixture)]
    assert drain_order == next_order
    # Pin the canonical (rank, id) order explicitly.
    assert drain_order == ["li-bbb", "li-ccc", "li-aaa"]


def test_ready_items_resolves_configured_sibling_terminal_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    livespec = tmp_path / "livespec"
    beads_fabro = tmp_path / "livespec-orchestrator-beads-fabro"
    overseer = tmp_path / "livespec-overseer"
    livespec.mkdir()
    beads_fabro.mkdir()
    overseer.mkdir()
    _ = (livespec / ".livespec.jsonc").write_text(
        f"""
        {{
          "cross_repo_targets": {{
            "livespec-orchestrator-beads-fabro": {{
              "github_url": "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro",
              "local_clone": "{beads_fabro}"
            }},
            "livespec-overseer": {{
              "github_url": "https://github.com/thewoolleyman/livespec-overseer",
              "local_clone": "{overseer}"
            }}
          }}
        }}
        """,
        encoding="utf-8",
    )
    item = _item(
        id="livespec-zsn2xh.5",
        status="pending-approval",
        depends_on=(
            {
                "kind": "sibling_work_item",
                "repo": "livespec-orchestrator-beads-fabro",
                "work_item_id": "bd-ib-mrqoy2",
            },
            {
                "kind": "sibling_work_item",
                "repo": "livespec-overseer",
                "work_item_id": "overseer-pfpfty",
            },
        ),
    )

    def _fetch() -> str:
        return _FLEET_MANIFEST_TEXT

    sibling_items = {
        beads_fabro: [_item(id="bd-ib-mrqoy2", status="done")],
        overseer: [_item(id="overseer-pfpfty", status="done")],
    }

    def _load(*, repo: Path) -> list[WorkItem]:
        return sibling_items[repo]

    monkeypatch.setattr(_sibling_status_lookup, "fetch_fleet_manifest_text", _fetch)
    monkeypatch.setattr(_sibling_status_lookup, "load_items", _load)

    assert [candidate.id for candidate in ready_items(items=[item], repo=livespec)] == [
        "livespec-zsn2xh.5"
    ]
