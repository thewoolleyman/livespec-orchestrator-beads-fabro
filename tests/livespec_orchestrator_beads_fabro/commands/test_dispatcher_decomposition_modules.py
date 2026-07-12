"""Pin the public API of the extracted dispatcher planning-layer modules.

`_dispatcher_host_only` (host-only routing predicate) and `_dispatcher_goal`
(per-item goal-brief assembly) were split out of `_dispatcher_plan` /
`_dispatcher_overlay` so each stays an honest cohesive unit under the file
LLOC ceiling. This test pins that the moved public functions are importable
and callable from their NEW defining modules AND remain re-exported (as the
SAME objects) from `_dispatcher_plan`, so `dispatcher.py`'s imports are
untouched by the move.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_calibration_emit,
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_ledger_close,
    _dispatcher_plan,
    dispatcher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import (
    Admission,
    admission_held_outcome,
    admit_and_select,
    autonomous_armed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    bounce_blocked,
    bounce_non_convergence_to_backlog,
    complete_and_accept,
    host_only_refusal,
    warn_item_sizing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import render_goal
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_only import (
    host_only_refusal_detail,
    is_host_only_item,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


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
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    from dataclasses import replace

    return replace(base, **overrides)


def test_host_only_predicate_importable_and_callable_from_new_module() -> None:
    assert is_host_only_item(item=_item(title="Refactor [host-only] the hook")) is True
    assert is_host_only_item(item=_item()) is False


def test_host_only_refusal_detail_importable_and_callable_from_new_module() -> None:
    detail = host_only_refusal_detail(item_id="livespec-impl-beads-uvd")
    assert "host-only refusal" in detail
    assert "livespec-impl-beads-uvd" in detail


def test_render_goal_importable_and_callable_from_new_module(tmp_path: Path) -> None:
    goal = render_goal(item=_item(), repo=tmp_path, branch="feat/t")
    assert "Work-item: livespec-impl-beads-t1" in goal
    assert "Publish branch" in goal


def test_new_module_functions_are_re_exported_from_dispatcher_plan() -> None:
    # dispatcher.py imports these from _dispatcher_plan; the move keeps that
    # surface intact by re-exporting the SAME function objects.
    assert _dispatcher_plan.render_goal is render_goal
    assert _dispatcher_plan.is_host_only_item is is_host_only_item
    assert _dispatcher_plan.host_only_refusal_detail is host_only_refusal_detail


def test_admission_cluster_importable_from_new_module() -> None:
    assert Admission.__name__ == "Admission"
    assert admit_and_select.__name__ == "admit_and_select"
    assert admission_held_outcome(item=_item(), reason="manual").stage == "admission-held"
    assert autonomous_armed(args=object()) is False


def test_completion_cluster_importable_from_new_module_and_dispatcher() -> None:
    assert dispatcher.host_only_refusal is host_only_refusal
    assert dispatcher.complete_and_accept is complete_and_accept
    assert dispatcher.bounce_non_convergence_to_backlog is bounce_non_convergence_to_backlog
    assert dispatcher.bounce_blocked is bounce_blocked
    assert dispatcher.warn_item_sizing is warn_item_sizing


def test_credentials_cluster_importable_from_new_module_and_private_names_removed() -> None:
    credential_public_names = {
        "check_credential_env",
        "credential_wrapper_text",
        "dispatch_required_credentials_text",
        "fetch_fleet_manifest_text",
        "materialize_overlay",
        "read_dispatch_comments",
        "read_dispatch_target_credential_wrapper",
        "resolve_sibling_clones",
    }
    codex_auth_public_names = {
        "CodexProjectionRefusal",
        "project_codex_auth",
        "read_host_codex_auth",
    }
    old_private_names = {
        "_CodexProjectionRefusal",
        "_check_credential_env",
        "_credential_wrapper_text",
        "_dispatch_required_credentials_text",
        "_fetch_fleet_manifest_text",
        "_materialize_overlay",
        "_project_codex_auth",
        "_read_dispatch_comments",
        "_read_dispatch_target_credential_wrapper",
        "_read_host_codex_auth",
        "_resolve_sibling_clones",
    }

    assert set(_dispatcher_credentials.__all__) == credential_public_names
    for name in credential_public_names:
        assert hasattr(_dispatcher_credentials, name)
    assert set(_dispatcher_codex_auth.__all__) == codex_auth_public_names
    for name in codex_auth_public_names:
        assert hasattr(_dispatcher_codex_auth, name)
    for name in old_private_names:
        assert not hasattr(dispatcher, name)


def test_ledger_close_cluster_importable_from_new_module_and_private_names_removed() -> None:
    ledger_close_public_names = {
        "emit_outcomes",
        "ledger_blocked_after_normalization",
        "load_items",
    }
    old_private_names = {
        "_append_normalization_note",
        "_emit_outcomes",
        "_ledger_blocked",
        "_ledger_blocked_after_normalization",
        "_load_items",
        "_normalize_native_open_statuses",
        "_write_findings",
    }

    assert set(_dispatcher_ledger_close.__all__) == ledger_close_public_names
    for name in ledger_close_public_names:
        assert hasattr(_dispatcher_ledger_close, name)
    assert dispatcher.emit_outcomes is _dispatcher_ledger_close.emit_outcomes
    assert (
        dispatcher.ledger_blocked_after_normalization
        is _dispatcher_ledger_close.ledger_blocked_after_normalization
    )
    assert dispatcher.load_items is _dispatcher_ledger_close.load_items
    for name in old_private_names:
        assert not hasattr(dispatcher, name)


def test_calibration_emit_cluster_importable_from_new_module_and_private_names_removed() -> None:
    calibration_emit_public_names = {
        "calibration_token_cost",
        "emit_calibration",
        "merged_pr_diff_size",
        "parse_pr_diff_size",
        "read_journal_records_for",
    }
    old_private_names = {
        "_calibration_token_cost",
        "_emit_calibration",
        "_merged_pr_diff_size",
        "_parse_pr_diff_size",
        "_read_journal_records_for",
    }

    assert set(_dispatcher_calibration_emit.__all__) == calibration_emit_public_names
    for name in calibration_emit_public_names:
        assert hasattr(_dispatcher_calibration_emit, name)
    assert dispatcher.emit_calibration is _dispatcher_calibration_emit.emit_calibration
    for name in old_private_names:
        assert not hasattr(dispatcher, name)


def test_dispatch_loop_cluster_importable_from_new_module_and_private_names_removed() -> None:
    commands_dir = Path(dispatcher.__file__).parent
    loop_path = commands_dir / "_dispatcher_loop.py"
    selection_path = commands_dir / "_dispatcher_loop_selection.py"
    assert loop_path.is_file()
    assert selection_path.is_file()

    dispatch_loop = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop"
    )
    dispatch_loop_selection = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection"
    )
    selection_public_names = {
        "candidates",
        "is_dispatch_candidate",
        "janitor_core_ref",
        "post_run_dispositions",
        "prepare",
        "ready_items",
        "run_id",
    }
    old_private_names = {
        "_candidates",
        "_dispatch_one",
        "_is_dispatch_candidate",
        "_janitor_core_ref",
        "_post_run_dispositions",
        "_prepare",
        "_ready_items",
        "_run_id",
    }

    assert dispatch_loop.__all__ == ["dispatch_one"]
    assert selection_public_names <= set(dispatch_loop_selection.__all__)
    assert set(dispatch_loop.__all__).isdisjoint(selection_public_names)
    assert hasattr(dispatch_loop, "dispatch_one")
    assert dispatcher.dispatch_one is dispatch_loop.dispatch_one
    assert dispatcher.candidates is dispatch_loop_selection.candidates
    assert dispatcher.is_dispatch_candidate is dispatch_loop_selection.is_dispatch_candidate
    assert dispatcher.janitor_core_ref is dispatch_loop_selection.janitor_core_ref
    assert dispatcher.post_run_dispositions is dispatch_loop_selection.post_run_dispositions
    assert dispatcher.prepare is dispatch_loop_selection.prepare
    assert dispatcher.ready_items is dispatch_loop_selection.ready_items
    assert dispatcher.run_id is dispatch_loop_selection.run_id
    for name in old_private_names:
        assert not hasattr(dispatcher, name)


def test_otel_wiring_cluster_importable_from_new_module_and_private_names_removed() -> None:
    otel_wiring_public_names = {
        "ensure_otel_receiver",
        "parse_janitor",
    }
    old_private_names = {
        "_build_otel_receiver",
        "_ensure_otel_receiver",
        "_parse_janitor",
    }

    for name in old_private_names:
        assert not hasattr(dispatcher, name)
    otel_wiring = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring"
    )
    assert set(otel_wiring.__all__) == otel_wiring_public_names
    for name in otel_wiring_public_names:
        assert hasattr(otel_wiring, name)
    assert dispatcher.ensure_otel_receiver is otel_wiring.ensure_otel_receiver
    assert dispatcher.parse_janitor is otel_wiring.parse_janitor
    assert not hasattr(otel_wiring, "_ensure_otel_receiver")
    assert not hasattr(otel_wiring, "_parse_janitor")
    assert hasattr(otel_wiring, "_build_otel_receiver")


def test_post_verdict_reflector_cluster_importable_and_private_names_removed() -> None:
    module_path = (
        Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
        / "_dispatcher_post_verdict.py"
    )
    post_verdict_public_names = {
        "ReflectorSpawn",
        "reflector_oob_after_verdict",
    }
    old_private_names = {
        "_ReflectorSpawn",
        "_default_reflector_spawn",
        "_reflector_oob_after_verdict",
        "_spawn_daemon",
        "_spawn_daemon_joining",
    }

    assert module_path.is_file()
    post_verdict = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_post_verdict"
    )
    assert set(post_verdict.__all__) == post_verdict_public_names
    for name in post_verdict_public_names:
        assert hasattr(post_verdict, name)
    assert dispatcher.reflector_oob_after_verdict is post_verdict.reflector_oob_after_verdict
    for name in old_private_names:
        assert not hasattr(dispatcher, name)
