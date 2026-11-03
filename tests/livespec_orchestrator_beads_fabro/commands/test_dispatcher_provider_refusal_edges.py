"""Structured-provider-refusal parsing keeps only a validated error payload."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import AcpNodeResolution
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    needs_human_cause_body,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_refusal import (
    ProviderRefusal,
    provider_refusal_detail,
    provider_refusal_from_turns,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import STAGE_FAILURE

_ERROR = {
    "type": "error",
    "status": 400,
    "error": {"type": "invalid_request_error", "message": "model refused"},
}


def _plan(*, tmp_path: Path, run_inputs: tuple[str, ...] = ()) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id="bd-ib-piclal",
        branch="feat/bd-ib-piclal",
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
        acp_nodes=AcpNodeResolution(nodes={}, inputs={}, run_inputs=run_inputs, candidates={}),
    )


def _payload(*, response: str | None) -> list[dict[str, Any]]:
    return [
        {
            "stages": {
                "implement@1": {
                    "handler": "agent",
                    "state": "succeeded",
                    "response": response,
                }
            }
        }
    ]


@pytest.mark.parametrize(
    "response",
    [
        "plain prose that is not a provider error",
        None,
        "{not-json",
        "[]",
        json.dumps({"type": "error", "status": True, "error": {"message": "no"}}),
        json.dumps({"type": "error", "status": 400, "error": "no"}),
        json.dumps({"type": "error", "status": 400, "error": {"message": "   "}}),
    ],
)
def test_only_a_structured_provider_error_is_a_refusal(tmp_path: Path, response: str) -> None:
    refusal = provider_refusal_from_turns(
        plan=_plan(tmp_path=tmp_path, run_inputs=("implement_adapter=codex-acp",)),
        payload=_payload(response=response),
    )

    assert refusal is None


def test_a_refusal_needs_a_resolved_adapter_and_keeps_an_unreadable_model(tmp_path: Path) -> None:
    response = f"metadata warning\n{json.dumps(_ERROR)}"
    without_adapter = provider_refusal_from_turns(
        plan=_plan(tmp_path=tmp_path), payload=_payload(response=response)
    )
    unreadable_model = provider_refusal_from_turns(
        plan=_plan(
            tmp_path=tmp_path,
            run_inputs=("implement_adapter=CODEX_CONFIG='{not-json' codex-acp",),
        ),
        payload=_payload(response=response),
    )
    non_mapping_model = provider_refusal_from_turns(
        plan=_plan(
            tmp_path=tmp_path,
            run_inputs=("implement_adapter=CODEX_CONFIG='[]' codex-acp",),
        ),
        payload=_payload(response=response),
    )
    no_resolution = provider_refusal_from_turns(
        plan=replace(_plan(tmp_path=tmp_path), acp_nodes=None),
        payload=_payload(response=response),
    )
    unconfigured_adapter = provider_refusal_from_turns(
        plan=_plan(tmp_path=tmp_path, run_inputs=("implement_adapter=codex-acp",)),
        payload=_payload(response=response),
    )

    assert without_adapter is None
    assert unreadable_model is not None
    assert unreadable_model.model is None
    assert non_mapping_model is not None
    assert non_mapping_model.model is None
    assert no_resolution is None
    assert unconfigured_adapter is not None
    assert unconfigured_adapter.model is None


def test_the_durable_cause_names_the_refused_adapter_and_model() -> None:
    outcome = DispatchOutcome(
        work_item_id="bd-ib-piclal",
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="provider refusal",
        fabro_run_id="01M592CTREYPGA1GZNPND1TXAY",
        needs_human_kind=STAGE_FAILURE,
        provider_refusal=ProviderRefusal(
            node="implement",
            message="model refused",
            adapter="codex-acp",
            model="gpt-6-sol",
        ),
    )

    body = needs_human_cause_body(outcome=outcome)

    assert "provider refusal: model refused" in body
    assert "refused ACP node: implement" in body
    assert "refused adapter: codex-acp" in body
    assert "refused model: gpt-6-sol" in body
    assert "(model not recorded)" in provider_refusal_detail(
        refusal=ProviderRefusal(
            node="implement",
            message="model refused",
            adapter="codex-acp",
            model=None,
        )
    )
